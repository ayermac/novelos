"""Tests for v6.7.6 Publish Guard — blocks publish when workflow is broken.

POST /api/publish/chapter should return WORKFLOW_RECOVERY_REQUIRED when
the latest run is blocked, failed, or stale-running.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


PROJECT_ID = "guard-test-proj"


def _setup_db(tmp_path: Path):
    db_path = tmp_path / "publish_guard.db"
    init_db(db_path)
    repo = Repository(str(db_path))
    repo.create_project(PROJECT_ID, "测试项目", "")
    repo.add_chapter(PROJECT_ID, 1, "第一章")
    repo.update_chapter_status(PROJECT_ID, 1, "reviewed")
    return str(db_path), repo


def _create_run(repo: Repository, status: str, started_hours_ago: float | None = None):
    run_id = repo.create_workflow_run(PROJECT_ID, 1)
    if started_hours_ago is not None:
        started_at = (datetime.utcnow() + timedelta(hours=8) - timedelta(hours=started_hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_runs SET started_at = ? WHERE id = ?",
                (started_at, run_id),
            )
            conn.commit()
        finally:
            conn.close()
    repo.update_workflow_run(run_id, status=status)
    return run_id


def _api_client(db_path: str):
    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app
    return TestClient(create_api_app(db_path=db_path, llm_mode="stub"))


class TestPublishGuardWorkflowRecovery:
    """POST /api/publish/chapter blocks when workflow needs recovery."""

    def test_blocked_run_blocks_publish(self, tmp_path):
        db_path, repo = _setup_db(tmp_path)
        _create_run(repo, "blocked")
        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "WORKFLOW_RECOVERY_REQUIRED"
        assert body["error"]["details"]["run_status"] == "blocked"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "blocked"
        assert domain["flags"]["workflow_needs_recovery"] is True

    def test_failed_run_blocks_publish(self, tmp_path):
        db_path, repo = _setup_db(tmp_path)
        _create_run(repo, "failed")
        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "WORKFLOW_RECOVERY_REQUIRED"
        assert body["error"]["details"]["run_status"] == "failed"

    def test_stale_running_run_blocks_publish(self, tmp_path):
        db_path, repo = _setup_db(tmp_path)
        _create_run(repo, "running", started_hours_ago=5)
        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "WORKFLOW_RECOVERY_REQUIRED"
        assert body["error"]["details"]["run_status"] == "running"

    def test_recent_running_does_not_block_publish(self, tmp_path):
        """A recent running run (within 2h) should NOT block publish."""
        db_path, repo = _setup_db(tmp_path)
        _create_run(repo, "running", started_hours_ago=0.5)
        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )
        body = resp.json()
        # Should NOT be WORKFLOW_RECOVERY_REQUIRED — may succeed or fail for other reasons
        error_code = (body.get("error") or {}).get("code")
        assert error_code != "WORKFLOW_RECOVERY_REQUIRED"

    def test_completed_run_allows_publish(self, tmp_path):
        db_path, repo = _setup_db(tmp_path)
        _create_run(repo, "completed")
        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )
        body = resp.json()
        # Should NOT be WORKFLOW_RECOVERY_REQUIRED
        error_code = (body.get("error") or {}).get("code")
        assert error_code != "WORKFLOW_RECOVERY_REQUIRED"

    def test_no_run_allows_publish(self, tmp_path):
        """No runs at all should not block publish."""
        db_path, repo = _setup_db(tmp_path)
        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )
        body = resp.json()
        error_code = (body.get("error") or {}).get("code")
        assert error_code != "WORKFLOW_RECOVERY_REQUIRED"
