"""Tests for v5.3.6 Workflow Trace Isolation — task_status per-run error tracking."""

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create test client with initialized database."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    test_client = TestClient(app)
    yield test_client
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture()
def project_id(client):
    """Create a project and return its ID."""
    resp = client.post("/api/onboarding/projects", json={
        "project_id": "test-trace",
        "name": "Test Trace",
        "genre": "奇幻",
        "description": "A test novel",
        "total_chapters_planned": 10,
        "target_words": 30000,
    })
    assert resp.status_code == 200
    data = resp.json()
    pid = data.get("data", {}).get("project", {}).get("project_id")
    assert pid, f"Expected project ID, got: {data}"
    return pid


class TestStartTaskRunIsolation:
    """v5.3.6: start_task should persist workflow_run_id."""

    def test_start_task_records_workflow_run_id(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        task_id = repo.start_task(
            project_id, 1, "revise", "author",
            workflow_run_id="run-abc-123",
        )
        assert task_id > 0

        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT workflow_run_id FROM task_status WHERE id=?",
                (task_id,),
            ).fetchone()
            assert row is not None
            assert row["workflow_run_id"] == "run-abc-123"
        finally:
            conn.close()

    def test_start_task_without_run_id_sets_null(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        task_id = repo.start_task(
            project_id, 1, "revise", "author",
        )
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT workflow_run_id FROM task_status WHERE id=?",
                (task_id,),
            ).fetchone()
            assert row["workflow_run_id"] is None
        finally:
            conn.close()


class TestTimelineRunIsolation:
    """v5.3.6: _build_steps_timeline must isolate by workflow_run_id."""

    def _create_run(self, repo, project_id, chapter_number, status="blocked",
                    current_node="author", error_message=""):
        """Helper to create a workflow run row."""
        import uuid
        run_id = uuid.uuid4().hex
        conn = repo._conn()
        try:
            conn.execute(
                "INSERT INTO workflow_runs "
                "(id, project_id, chapter_number, status, current_node, error_message, "
                "started_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now','+8 hours'), datetime('now','+8 hours'))",
                (run_id, project_id, chapter_number, status, current_node, error_message),
            )
            conn.commit()
        finally:
            conn.close()
        return run_id

    def _get_run_data(self, repo, run_id):
        """Helper to fetch run data as dict."""
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?", (run_id,)
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def test_timeline_prefers_run_isolated_task_errors(self, client, project_id):
        from novel_factory.db.repository import Repository
        from novel_factory.api.routes.runs import _build_steps_timeline

        repo = Repository(client.app.state.db_path)
        run1 = self._create_run(repo, project_id, 1, status="blocked", current_node="author")
        run2 = self._create_run(repo, project_id, 1, status="blocked", current_node="author")

        # Run 1 has an old error
        repo.start_task(project_id, 1, "revise", "author", workflow_run_id=run1)
        # Run 2 has a new error
        task2 = repo.start_task(project_id, 1, "revise", "author", workflow_run_id=run2)
        repo.complete_task(task2, success=False, error="run2-specific failure")

        run_data = self._get_run_data(repo, run1)
        steps = _build_steps_timeline(run_data, None, "stub", repo=repo)
        author_step = next((s for s in steps if s["key"] == "author"), None)
        assert author_step is not None
        # Run1 timeline should NOT see run2's error
        assert "run2-specific failure" not in (author_step.get("error_message") or "")

    def test_timeline_fallback_to_legacy_task_errors(self, client, project_id):
        from novel_factory.db.repository import Repository
        from novel_factory.api.routes.runs import _build_steps_timeline

        repo = Repository(client.app.state.db_path)
        run1 = self._create_run(repo, project_id, 1, status="blocked", current_node="author")

        # Legacy row without workflow_run_id
        task1 = repo.start_task(project_id, 1, "revise", "author")
        repo.complete_task(task1, success=False, error="legacy old error")

        run_data = self._get_run_data(repo, run1)
        steps = _build_steps_timeline(run_data, None, "stub", repo=repo)
        author_step = next((s for s in steps if s["key"] == "author"), None)
        assert author_step is not None
        assert author_step.get("error_message") == "legacy old error"
        assert author_step.get("error_is_legacy") is True

    def test_run_isolated_error_overrides_legacy(self, client, project_id):
        from novel_factory.db.repository import Repository
        from novel_factory.api.routes.runs import _build_steps_timeline

        repo = Repository(client.app.state.db_path)
        run1 = self._create_run(repo, project_id, 1, status="blocked", current_node="author")

        # Legacy row
        task_legacy = repo.start_task(project_id, 1, "revise", "author")
        repo.complete_task(task_legacy, success=False, error="legacy error")

        # Run-isolated row
        task_run = repo.start_task(project_id, 1, "revise", "author", workflow_run_id=run1)
        repo.complete_task(task_run, success=False, error="run-isolated error")

        run_data = self._get_run_data(repo, run1)
        steps = _build_steps_timeline(run_data, None, "stub", repo=repo)
        author_step = next((s for s in steps if s["key"] == "author"), None)
        assert author_step is not None
        assert author_step.get("error_message") == "run-isolated error"
        assert author_step.get("error_is_legacy") is not True


class TestRunDetailAPI:
    """v5.3.6: Run detail API should expose legacy/fallback flags."""

    def test_run_detail_with_legacy_error_flag(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        # Create a blocked run
        import uuid
        run_id = uuid.uuid4().hex
        conn = repo._conn()
        try:
            conn.execute(
                "INSERT INTO workflow_runs "
                "(id, project_id, chapter_number, status, current_node, error_message, "
                "started_at, completed_at) "
                "VALUES (?, ?, ?, 'blocked', 'author', '', "
                "datetime('now','+8 hours'), datetime('now','+8 hours'))",
                (run_id, project_id, 1),
            )
            conn.commit()
        finally:
            conn.close()

        # Legacy task error
        task = repo.start_task(project_id, 1, "revise", "author")
        repo.complete_task(task, success=False, error="legacy failure")

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        steps = body["data"]["steps"]
        author_step = next((s for s in steps if s["key"] == "author"), None)
        assert author_step is not None
        assert author_step.get("error_message") == "legacy failure"
        assert author_step.get("error_is_legacy") is True
