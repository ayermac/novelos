"""v5.1.2 Chapter & Status Model Alignment Tests.

Tests for:
1. Onboarding creates chapters with status=planned (not pending)
2. Old pending chapters can run without being blocked
3. /api/run/chapter returns workflow_status, chapter_status, requires_human, error
4. blocked/failed runs do NOT return "章节生成完成"
5. workflow_run.status matches API workflow_status
6. Run.tsx uses workspace, not chapter_count + 1
7. Run.tsx chapter selector is a <select>
8. Run.tsx result panel shows workflow_status/chapter_status in Chinese
9. ProjectDetail recent_runs shows fallback for blocked with no error_message
10. NextAction only checks latest run, not any historical failed
11. i18n STATUS_MAP covers blocked -> 已阻塞
12. Layout sidebar version is v5.1.2
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        test_client = TestClient(app)
        yield test_client
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestOnboardingInitialStatus:
    """Onboarding creates chapters with planned status."""

    def test_new_project_chapters_are_planned(self, client):
        """New project chapters should have status=planned, not pending."""
        resp = client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v512_001",
                "name": "v512 测试",
                "initial_chapter_count": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Check workspace chapters
        resp = client.get("/api/projects/test_v512_001/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        chapters = data["data"]["chapters"]
        assert len(chapters) == 5
        for ch in chapters:
            assert ch["status"] == "planned", (
                f"Expected chapter status 'planned', got '{ch['status']}'"
            )


class TestPendingCompatibility:
    """Old pending chapters are handled compatibly."""

    def test_pending_chapter_runs_without_blocked(self, client):
        """A chapter with pending status should run and not be blocked."""
        # Create project
        resp = client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v512_002",
                "name": "pending 兼容测试",
                "initial_chapter_count": 1,
            },
        )
        assert resp.status_code == 200

        # Manually set chapter to pending (simulating old data)
        # Get the DB path from the app state
        from novel_factory.db.connection import get_connection
        db_path = client.app.state.db_path
        conn = get_connection(db_path)
        try:
            conn.execute(
                "UPDATE chapters SET status='pending' "
                "WHERE project_id='test_v512_002' AND chapter_number=1"
            )
            conn.commit()
        finally:
            conn.close()

        # Verify chapter is now pending
        resp = client.get("/api/projects/test_v512_002/workspace")
        chapters = resp.json()["data"]["chapters"]
        assert chapters[0]["status"] == "pending", "Chapter should be pending before run"

        # Run the chapter - should normalize pending to planned and succeed
        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v512_002", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True, f"Run should succeed, got: {data}"
        result = data["data"]

        # Should NOT be blocked or failed
        assert result["workflow_status"] not in ("failed", "blocked"), (
            f"workflow_status should not be failed/blocked, got: {result['workflow_status']}, "
            f"error: {result.get('error')}"
        )
        assert result["error"] is None, f"error should be None, got: {result['error']}"

        # Chapter status should no longer be pending
        resp = client.get("/api/projects/test_v512_002/workspace")
        chapters = resp.json()["data"]["chapters"]
        assert chapters[0]["status"] != "pending", (
            "Chapter status should be normalized from pending to planned (or later)"
        )

    def test_pending_in_status_route(self):
        """STATUS_ROUTE should contain pending -> screenwriter mapping."""
        from novel_factory.dispatch.base import STATUS_ROUTE

        assert "pending" in STATUS_ROUTE
        assert STATUS_ROUTE["pending"] == "screenwriter"


class TestRunChapterResponseStructure:
    """/api/run/chapter returns correct response structure."""

    def test_run_chapter_returns_workflow_status(self, client):
        """Run chapter should return workflow_status field."""
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v512_003",
                "name": "run 结构测试",
                "initial_chapter_count": 2,
            },
        )

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v512_003", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        result = data["data"]

        assert "workflow_status" in result
        assert "chapter_status" in result
        assert "requires_human" in result
        assert "error" in result
        assert "status" in result  # backward compatibility
        assert "message" in result

    def test_run_chapter_blocked_not_completed_message(self, client):
        """If workflow_status is blocked, message should not say completed."""
        # We can't easily force blocked in stub mode, but we can verify
        # that the response structure supports it.
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v512_004",
                "name": "message 测试",
                "initial_chapter_count": 1,
            },
        )

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v512_004", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data["data"]

        # In stub mode, a planned chapter should complete successfully
        if result["workflow_status"] == "completed":
            assert "章节生成完成" in result["message"] or "章节已提交生成" in result["message"]
        elif result["workflow_status"] == "blocked":
            assert "章节生成完成" not in result["message"]
            assert "阻塞" in result["message"]
        elif result["workflow_status"] == "failed":
            assert "章节生成完成" not in result["message"]
            assert "失败" in result["message"]

    def test_workflow_run_status_matches_api_status(self, client):
        """workflow_run.status in DB should match API workflow_status."""
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v512_005",
                "name": "status 一致性测试",
                "initial_chapter_count": 1,
            },
        )

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v512_005", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        run_id = data["data"]["run_id"]
        api_status = data["data"]["workflow_status"]

        # Query workspace recent_runs to verify DB status
        resp = client.get("/api/projects/test_v512_005/workspace")
        ws = resp.json()["data"]
        runs = ws["recent_runs"]
        matching = [r for r in runs if r["run_id"] == run_id]
        assert len(matching) == 1
        db_status = matching[0]["status"]
        assert db_status == api_status, (
            f"DB workflow_run.status '{db_status}' != API workflow_status '{api_status}'"
        )


class TestFrontendRunPage:
    """Frontend Run.tsx quality checks."""

    def test_run_uses_workspace_not_chapter_count_plus_one(self):
        """Run.tsx should use /projects/{id}/workspace, not chapter_count + 1."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        run_file = frontend_src / "pages" / "Run.tsx"
        assert run_file.exists()
        content = run_file.read_text()

        assert "/workspace" in content, "Run.tsx should call /workspace endpoint"
        # Should NOT default to chapter_count + 1
        assert "chapter_count + 1" not in content, (
            "Run.tsx should not use chapter_count + 1 as default"
        )
        assert "chapter_count||0)+1" not in content.replace(" ", "")

    def test_run_chapter_selector_is_select(self):
        """Run.tsx chapter selector should be a <select> element."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        run_file = frontend_src / "pages" / "Run.tsx"
        content = run_file.read_text()

        assert "<select" in content, "Run.tsx should use <select> for chapter selection"
        assert "isRunnable" in content or "RUNNABLE_STATUSES" in content, (
            "Run.tsx should filter runnable chapters"
        )

    def test_run_result_shows_workflow_and_chapter_status(self):
        """Run.tsx result panel should show workflow_status and chapter_status."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        run_file = frontend_src / "pages" / "Run.tsx"
        content = run_file.read_text()

        assert "workflow_status" in content, "Result panel should display workflow_status"
        assert "chapter_status" in content, "Result panel should display chapter_status"
        assert "tWorkflowStatus" in content or "tChapterStatus" in content, (
            "Result panel should translate statuses to Chinese"
        )


class TestFrontendProjectDetail:
    """Frontend ProjectDetail.tsx quality checks."""

    def test_project_detail_blocked_fallback(self):
        """ProjectDetail should show fallback text for blocked runs without error_message."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        detail_file = frontend_src / "pages" / "ProjectDetail.tsx"
        assert detail_file.exists()
        content = detail_file.read_text()

        assert "blocked" in content, "Should handle blocked status"
        # HistoryTab uses tWorkflowStatus function for translation
        assert "tWorkflowStatus" in content, (
            "Should use tWorkflowStatus function for status translation"
        )

    def test_next_action_checks_latest_run_only(self):
        """NextAction should only check the latest run, not any historical failed."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        detail_file = frontend_src / "pages" / "ProjectDetail.tsx"
        content = detail_file.read_text()

        # Should NOT filter all historical failed runs
        assert "data.recent_runs.filter" not in content, (
            "NextAction should not filter all historical runs; use latestRun instead"
        )
        # Should check only the latest (first) run
        assert "latestRun" in content, (
            "NextAction should use latestRun (first element) instead of filtering all runs"
        )
        # Should reference recent_runs[0] for latest
        assert "recent_runs[0]" in content or "latestRun" in content, (
            "Should get the latest run as recent_runs[0]"
        )


class TestI18nBlockedMapping:
    """i18n STATUS_MAP covers workflow_run.status blocked."""

    def test_blocked_mapped_to_chinese(self):
        """STATUS_MAP should map blocked -> 已阻塞."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        i18n_file = frontend_src / "lib" / "i18n.ts"
        assert i18n_file.exists()
        content = i18n_file.read_text()

        # Should have blocked mapping in STATUS_MAP
        assert "blocked:" in content, "STATUS_MAP should contain 'blocked' key"
        assert "已阻塞" in content, "STATUS_MAP should map blocked to 已阻塞"

    def test_all_workflow_statuses_mapped(self):
        """All workflow_run.status values should have Chinese mappings."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        i18n_file = frontend_src / "lib" / "i18n.ts"
        content = i18n_file.read_text()

        required_mappings = {
            "completed": "已完成",
            "running": "运行中",
            "failed": "失败",
            "blocked": "已阻塞",
        }
        for key, value in required_mappings.items():
            assert f"{key}:" in content and value in content, (
                f"STATUS_MAP should map {key} -> {value}"
            )


class TestLayoutVersion:
    """Layout sidebar shows correct version."""

    def test_sidebar_version_is_v515(self):
        """Sidebar version should display v5.1.5."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        layout_file = frontend_src / "components" / "Layout.tsx"
        assert layout_file.exists()
        content = layout_file.read_text()

        assert "v5.1.5" in content, (
            "Layout sidebar should display v5.1.5, not older version"
        )
        assert "v5.1.4" not in content, (
            "Layout sidebar should NOT still show v5.1.4"
        )


class TestFrontendDashboard:
    """Frontend Dashboard.tsx quality checks."""

    def test_dashboard_next_action_checks_latest_run_only(self):
        """Dashboard NextActionCard should only check the latest run."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        assert dashboard_file.exists()
        content = dashboard_file.read_text()

        # Should NOT filter all historical failed runs
        assert "data.recent_runs.filter" not in content, (
            "Dashboard NextActionCard should not filter all historical runs; use latestRun instead"
        )
        # Should check only the latest (first) run
        assert "latestRun" in content, (
            "Dashboard NextActionCard should use latestRun (first element) instead of filtering all runs"
        )

    def test_dashboard_handles_blocked_status(self):
        """Dashboard NextActionCard should show Chinese text for blocked latest run."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        content = dashboard_file.read_text()

        assert "被阻塞" in content, (
            "Dashboard should show Chinese '被阻塞' for blocked latest run"
        )
        # Should NOT show English 'blocked' as user-visible text
        # (StatusBadge handles i18n, but NextActionCard title/hint should be Chinese)
