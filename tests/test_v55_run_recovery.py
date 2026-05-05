"""v5.5 Run Recovery Console tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.workflow.checkpoint import (
    checkpoint_thread_exists,
    derive_checkpoint_db_path,
    get_checkpoint_thread_id,
    get_sqlite_checkpointer,
)


def _make_client(tmp_path):
    db_path = str(tmp_path / "recovery.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path), db_path


def _seed_run(repo: Repository, project_id: str, status: str = "blocking") -> str:
    repo.create_project(project_id=project_id, name="Recovery Project", genre="fantasy")
    repo.add_chapter(project_id, 1, title="Ch1", status=status)
    run_id = repo.create_workflow_run(project_id, 1)
    repo.update_workflow_run(
        run_id,
        status="blocked" if status == "blocking" else "failed",
        error_message="字数质量门未通过",
    )
    return run_id


def test_run_recovery_preview_for_blocked_run(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_preview")
    repo.start_task("recover_preview", 1, "revise", "polisher", workflow_run_id=run_id)
    repo.start_task("recover_preview", 1, "revise", "polisher", workflow_run_id=run_id)

    resp = client.get(f"/api/runs/{run_id}/recovery")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_id"] == run_id
    assert data["chapter_status"] == "blocking"
    assert data["retry_count"] == 2
    assert data["can_reset"] is True
    assert data["actions"]["reset_to_planned"]["enabled"] is True
    assert "字数质量门未通过" in data["error_message"]


def test_run_recovery_reset_clears_retry_checkpoint_and_audits_run(tmp_path):
    client, repo, db_path = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_reset")
    repo.start_task("recover_reset", 1, "revise", "polisher", workflow_run_id=run_id)
    repo.start_task("recover_reset", 1, "revise", "polisher", workflow_run_id=run_id)

    cp_path = derive_checkpoint_db_path(db_path)
    thread_id = get_checkpoint_thread_id("recover_reset", 1)
    with get_sqlite_checkpointer(cp_path) as cp:
        cp.put(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
            {"id": "recover-cp-1", "chapter_status": "blocking"},
            {},
            {},
        )
    assert checkpoint_thread_exists(db_path, "recover_reset", 1) is True

    resp = client.post(f"/api/runs/{run_id}/recovery/reset", json={"confirm": True})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["recovered"] is True
    assert data["previous_status"] == "blocking"
    assert data["new_status"] == "planned"
    assert data["retry_count_before"] == 2
    assert data["retry_count_after"] == 0
    assert data["checkpoint_before"] is True
    assert data["checkpoint_cleared"] is True
    assert data["recovery"]["can_reset"] is False

    chapter = repo.get_chapter("recover_reset", 1)
    assert chapter["status"] == "planned"
    assert checkpoint_thread_exists(db_path, "recover_reset", 1) is False

    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT workflow_run_id, task_type, agent_id, status FROM task_status "
            "WHERE project_id=? AND chapter_number=? AND task_type='reset' "
            "ORDER BY id DESC LIMIT 1",
            ("recover_reset", 1),
        ).fetchone()
    finally:
        conn.close()
    assert row["workflow_run_id"] == run_id
    assert row["task_type"] == "reset"
    assert row["agent_id"] == "human"
    assert row["status"] == "completed"


def test_run_recovery_reset_rejects_non_recoverable_status(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_invalid", status="polished")

    preview = client.get(f"/api/runs/{run_id}/recovery").json()["data"]
    assert preview["can_reset"] is False

    resp = client.post(f"/api/runs/{run_id}/recovery/reset", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_STATUS"
    assert repo.get_chapter("recover_invalid", 1)["status"] == "polished"


def test_run_recovery_reset_requires_confirmation(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_confirm")

    resp = client.post(f"/api/runs/{run_id}/recovery/reset", json={"confirm": False})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CONFIRM_REQUIRED"
    assert repo.get_chapter("recover_confirm", 1)["status"] == "blocking"


def test_run_detail_page_contains_recovery_console():
    content = Path("frontend/src/pages/RunDetail.tsx").read_text(encoding="utf-8")

    assert "运行恢复" in content
    assert "/recovery/reset" in content
    assert "handleResetRecovery" in content
    assert "reset_to_planned" in content
