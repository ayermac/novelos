"""Tests for project-level modules: Style, Review, Runs.

This test file covers:
- StyleGuideModule: style console API
- ReviewModule: blocking/reviewed/published status, publish API
- RunsModule: project-level runs list API
"""

from __future__ import annotations

import tempfile
import pytest
from pathlib import Path

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.api_app import create_api_app
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create test client with isolated database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(str(db_path))
        app = create_api_app(db_path=str(db_path), llm_mode="stub")
        client = TestClient(app)
        yield client, str(db_path)


class TestStyleGuideModule:
    """Test StyleGuideModule API requirements."""

    def test_style_console_returns_required_fields(self, test_client):
        """Style console should return style_bibles, style_gate_configs, style_samples, and health."""
        client, _ = test_client
        resp = client.get("/api/style/console")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "style_bibles" in data["data"]
        assert "style_gate_configs" in data["data"]
        assert "style_samples" in data["data"]
        assert "health" in data["data"]

    def test_style_init_creates_bible(self, test_client):
        """Style init should create style bible for project."""
        client, db_path = test_client

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-style-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Init style bible
        resp = client.post("/api/style/init", json={"project_id": project_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify bible appears in console
        resp2 = client.get("/api/style/console")
        assert resp2.status_code == 200
        bibles = resp2.json()["data"]["style_bibles"]
        assert any(b["project_id"] == project_id for b in bibles)


class TestReviewModule:
    """Test ReviewModule API requirements."""

    def test_workspace_includes_recent_runs(self, test_client):
        """Workspace API should include recent_runs for blocking error display."""
        client, db_path = test_client

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-workspace-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Get workspace
        resp = client.get(f"/api/projects/{project_id}/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "recent_runs" in data["data"]

    def test_publish_endpoint_for_reviewed_chapter(self, test_client):
        """Publish API should allow publishing reviewed chapters."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to reviewed status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='reviewed', word_count=3000 WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Publish
        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify status changed to published
        chapter = repo.get_chapter(project_id, 1)
        assert chapter["status"] == "published"

    def test_publish_endpoint_backfills_memory_before_publish(self, test_client):
        """Manual publish must not skip MemoryCurator when memory evidence is missing."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-memory-project",
            "name": "Test Memory Publish Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(
            project_id,
            1,
            "林默夺回账册，并发现账册夹层里藏着铜钥匙。",
            "第一章",
        )
        repo.save_chapter_state(
            project_id,
            1,
            {
                "new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"],
                "character_status": {"林默": "掌握铜钥匙线索"},
            },
            "第1章状态卡",
        )
        repo.update_chapter_status(project_id, 1, "reviewed")

        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["chapter_status"] == "published"
        assert data["data"]["memory_curator_processed"] is True
        assert data["data"]["memory_items_count"] >= 2

        batches = repo.list_memory_batches(project_id)
        assert len(batches) == 1
        assert batches[0]["chapter_number"] == 1
        assert batches[0]["status"] == "pending"

    def test_run_detail_memory_backfill_endpoint(self, test_client):
        """Run detail page can backfill MemoryCurator for an already published chapter."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-run-memory-backfill",
            "name": "Test Run Memory Backfill",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(
            project_id,
            1,
            "林默夺回账册，并发现账册夹层里藏着铜钥匙。",
            "第一章",
        )
        repo.save_chapter_state(
            project_id,
            1,
            {"new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"]},
            "第1章状态卡",
        )
        repo.update_chapter_status(project_id, 1, "published")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="completed", current_node="publisher")
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="memory_curator",
            event_type="completed",
            status="completed",
            message="历史运行显示记忆整理完成但未创建收件箱批次",
        )

        resp = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skipped"] is False
        assert data["data"]["memory_items_count"] >= 1

        batches = repo.list_memory_batches(project_id)
        assert len(batches) == 1
        assert batches[0]["chapter_number"] == 1

    def test_run_detail_memory_backfill_uses_memory_curator_llm_route(self, monkeypatch):
        """Memory backfill should honor agent_llm.memory_curator instead of generic default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config_path = Path(tmpdir) / "config.yaml"
            init_db(str(db_path))
            config_path.write_text(
                """
db_path: "{db_path}"
default_llm: default
llm_profiles:
  default:
    provider: openai_compatible
    base_url: http://default.invalid/v1
    api_key: default-key
    model: wrong-default-model
  memory:
    provider: openai_compatible
    base_url: http://memory.invalid/v1
    api_key: memory-key
    model: memory-route-model
agent_llm:
  memory_curator: memory
""".format(db_path=str(db_path)),
                encoding="utf-8",
            )
            app = create_api_app(
                db_path=str(db_path),
                config_path=str(config_path),
                llm_mode="real",
            )
            client = TestClient(app)
            repo = Repository(str(db_path))
            seen: dict[str, str] = {}

            def fake_run(self, state):
                seen["model"] = getattr(getattr(self.llm, "config", None), "model", "")
                seen["base_url"] = getattr(getattr(self.llm, "config", None), "base_url", "")
                return {
                    "memory_batch_id": "batch-memory-route",
                    "memory_items_count": 1,
                    "memory_curator_degraded": False,
                }

            monkeypatch.setattr("novel_factory.agents.memory_curator.MemoryCuratorAgent.run", fake_run)

            resp = client.post("/api/onboarding/projects", json={
                "project_id": "test-memory-route",
                "name": "Test Memory Route",
                "genre": "fantasy",
                "target_words": 100000,
                "total_chapters_planned": 50,
            })
            assert resp.status_code == 200
            project_id = resp.json()["data"]["project"]["project_id"]
            repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
            repo.update_chapter_status(project_id, 1, "published")
            run_id = repo.create_workflow_run(project_id, 1)
            repo.update_workflow_run(run_id, status="completed", current_node="publisher")

            resp = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["data"]["skipped"] is False
            assert data["data"]["memory_batch_id"] == "batch-memory-route"
            assert seen["model"] == "memory-route-model"
            assert seen["base_url"] == "http://memory.invalid/v1"

    def test_reset_blocking_chapter(self, test_client):
        """Reset API should allow resetting blocking chapters."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-reset-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to blocking status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Reset
        resp = client.post(f"/api/projects/{project_id}/chapters/1/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify status changed to planned
        chapter = repo.get_chapter(project_id, 1)
        assert chapter["status"] == "planned"


class TestRunsModule:
    """Test RunsModule API requirements."""

    def test_project_runs_list(self, test_client):
        """Project runs API should return list of runs with required fields."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-runs-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Create a workflow run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(
            run_id,
            status="completed",
            prompt_tokens=1000,
            completion_tokens=2000,
            total_tokens=3000,
            duration_ms=5000,
        )

        # Get project runs
        resp = client.get(f"/api/projects/{project_id}/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

        # Check required fields
        run = data["data"][0]
        assert "run_id" in run or "id" in run
        assert "chapter_number" in run
        assert "status" in run
        assert "total_tokens" in run
        assert "duration_ms" in run

    def test_run_detail_includes_steps_and_artifacts(self, test_client):
        """Run detail API should include steps with artifacts."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-steps-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to published status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='published', word_count=3000 WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Create run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="completed")

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Check steps
        assert "steps" in data["data"]
        steps = data["data"]["steps"]
        assert len(steps) >= 1

        # Each step should have key, label, status
        for step in steps:
            assert "key" in step
            assert "label" in step
            assert "status" in step

    def test_run_detail_includes_error_message(self, test_client):
        """Run detail API should include error_message for failed runs."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-error-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to blocking status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Create failed run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="failed", error_message="Test error message")

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "error_message" in data["data"]
        assert data["data"]["error_message"] == "Test error message"

    def test_run_detail_explains_empty_blocked_run(self, test_client):
        """Blocked run detail should explain already-blocked chapters even for legacy empty errors."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-empty-blocked-run",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        previous_run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(
            previous_run_id,
            status="blocked",
            current_node="human_review",
            error_message="LLM provider overloaded",
        )

        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="blocked", current_node="human_review")

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "已处于阻塞状态" in data["data"]["error_message"]
        assert "LLM provider overloaded" in data["data"]["error_message"]
        blocked_steps = [s for s in data["data"]["steps"] if s["status"] == "blocked"]
        assert blocked_steps
        assert "已处于阻塞状态" in blocked_steps[0]["error_message"]
