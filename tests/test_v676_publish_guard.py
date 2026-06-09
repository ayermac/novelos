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
    repo.add_chapter(PROJECT_ID, 1, "第一章 发布校验")
    repo.save_chapter_content(
        PROJECT_ID,
        1,
        "发布校验正文已经完成，章节具备可信记忆和发布条件。",
        title="第一章 发布校验",
    )
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


def _create_trusted_memory_batch(repo: Repository):
    batch = repo.create_memory_batch(
        PROJECT_ID,
        chapter_number=1,
        run_id="memory-run",
        summary="第1章记忆提取 - 可信提取 (1项)",
    )
    repo.create_memory_item(
        batch_id=batch["id"],
        project_id=PROJECT_ID,
        target_table="story_facts",
        operation="create",
        after_json='{"fact_key":"publish_guard.memory_ready"}',
        confidence=0.9,
        evidence_text="章节已具备发布前可信记忆。",
        rationale="MemoryCurator LLM 正文复核提取",
    )
    return batch


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

    def test_blocked_memory_curator_run_blocks_publish_without_trusted_memory(self, tmp_path):
        """MemoryCurator failure still blocks publish when trusted memory is missing."""
        db_path, repo = _setup_db(tmp_path)
        run_id = _create_run(repo, "blocked")
        repo.update_workflow_run(
            run_id,
            status="blocked",
            current_node="memory_curator",
            error_message="节点 memory_curator 执行超时（>300秒），需要人工介入",
        )

        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )

        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "WORKFLOW_RECOVERY_REQUIRED"
        assert repo.get_chapter(PROJECT_ID, 1)["status"] == "reviewed"

    def test_blocked_memory_curator_run_does_not_block_reviewed_publish_with_trusted_memory(self, tmp_path):
        """Post-review MemoryCurator timeout can be ignored only after trusted memory exists."""
        db_path, repo = _setup_db(tmp_path)
        _create_trusted_memory_batch(repo)
        run_id = _create_run(repo, "blocked")
        repo.update_workflow_run(
            run_id,
            status="blocked",
            current_node="memory_curator",
            error_message="节点 memory_curator 执行超时（>300秒），需要人工介入",
        )

        with _api_client(db_path) as client:
            resp = client.post(
                "/api/publish/chapter",
                json={"project_id": PROJECT_ID, "chapter": 1},
            )

        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["chapter_status"] == "published"
        assert repo.get_chapter(PROJECT_ID, 1)["status"] == "published"
