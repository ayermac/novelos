"""v5.5 Run Recovery Console tests."""

from __future__ import annotations

from datetime import datetime, timedelta
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


def _seed_running_run(repo: Repository, project_id: str, minutes_old: int) -> str:
    repo.create_project(project_id=project_id, name="Recovery Project", genre="fantasy")
    repo.add_chapter(project_id, 1, title="Ch1", status="drafted")
    run_id = repo.create_workflow_run(project_id, 1)
    repo.update_workflow_run(run_id, current_node="author")
    started_at = (datetime.now() - timedelta(minutes=minutes_old)).strftime("%Y-%m-%d %H:%M:%S")
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE workflow_runs SET started_at=? WHERE id=?",
            (started_at, run_id),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def _backdate_task(repo: Repository, task_id: int, minutes_old: int) -> None:
    started_at = (datetime.now() - timedelta(minutes=minutes_old)).strftime("%Y-%m-%d %H:%M:%S")
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE task_status SET started_at=? WHERE id=?",
            (started_at, task_id),
        )
        conn.commit()
    finally:
        conn.close()


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
    assert data["recovery"]["can_reset"] is True  # planned is now recoverable

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


def test_run_recovery_reset_survives_missing_cwd_settings_load(tmp_path, monkeypatch):
    """Reset recovery should not fail when .env/settings discovery hits missing cwd."""
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_missing_cwd")

    def missing_cwd_settings(**_kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(
        "novel_factory.api.deps.load_settings_with_cli",
        missing_cwd_settings,
    )

    resp = client.post(f"/api/runs/{run_id}/recovery/reset", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["recovered"] is True
    assert body["data"]["new_status"] == "planned"
    assert repo.get_chapter("recover_missing_cwd", 1)["status"] == "planned"


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


def test_run_recovery_reset_from_planned_clears_checkpoint_and_invalidates_runs(tmp_path):
    """Planned status should allow recovery reset (cleanup-only, no state change)."""
    client, repo, db_path = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_planned", status="planned")

    # Seed a checkpoint and an old running run
    from novel_factory.workflow.checkpoint import derive_checkpoint_db_path, get_checkpoint_thread_id
    cp_path = derive_checkpoint_db_path(db_path)
    thread_id = get_checkpoint_thread_id("recover_planned", 1)
    from novel_factory.workflow.checkpoint import get_sqlite_checkpointer
    with get_sqlite_checkpointer(cp_path) as cp:
        cp.put(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
            {"id": "recover-cp-planned", "chapter_status": "planned"},
            {},
            {},
        )
    from novel_factory.workflow.checkpoint import checkpoint_thread_exists
    assert checkpoint_thread_exists(db_path, "recover_planned", 1) is True

    old_run_id = repo.create_workflow_run("recover_planned", 1)
    repo.update_workflow_run(old_run_id, status="running", current_node="screenwriter")

    preview = client.get(f"/api/runs/{run_id}/recovery").json()["data"]
    assert preview["can_reset"] is True
    assert preview["chapter_status"] == "planned"

    resp = client.post(f"/api/runs/{run_id}/recovery/reset", json={"confirm": True})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["recovered"] is True
    assert data["previous_status"] == "planned"
    assert data["new_status"] == "planned"
    assert data["checkpoint_cleared"] is True
    assert data["invalidated_runs"] >= 1
    assert checkpoint_thread_exists(db_path, "recover_planned", 1) is False
    # Chapter status unchanged
    assert repo.get_chapter("recover_planned", 1)["status"] == "planned"


def test_run_recovery_reset_requires_confirmation(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_confirm")

    resp = client.post(f"/api/runs/{run_id}/recovery/reset", json={"confirm": False})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CONFIRM_REQUIRED"
    assert repo.get_chapter("recover_confirm", 1)["status"] == "blocking"


def test_run_recovery_preview_detects_stuck_running_run(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "recover_stuck_preview", minutes_old=45)
    task_id = repo.start_task(
        "recover_stuck_preview",
        1,
        "create",
        "author",
        workflow_run_id=run_id,
    )
    _backdate_task(repo, task_id, minutes_old=45)

    resp = client.get(f"/api/runs/{run_id}/recovery")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["workflow_status"] == "running"
    assert data["stuck"] is True
    assert data["timeout_minutes"] == 30
    assert data["elapsed_minutes"] >= 30
    assert data["actions"]["mark_stuck_blocked"]["enabled"] is True
    assert data["running_tasks"][0]["stuck"] is True


def test_run_recovery_preview_does_not_mix_legacy_running_tasks(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "recover_stuck_legacy", minutes_old=5)
    legacy_task_id = repo.start_task("recover_stuck_legacy", 1, "create", "author")
    _backdate_task(repo, legacy_task_id, minutes_old=90)

    resp = client.get(f"/api/runs/{run_id}/recovery")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stuck"] is False
    assert data["running_tasks"] == []
    assert data["actions"]["mark_stuck_blocked"]["enabled"] is False


def test_mark_stuck_run_converts_to_blocking_and_audits_run(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "recover_mark_stuck", minutes_old=50)
    task_id = repo.start_task(
        "recover_mark_stuck",
        1,
        "create",
        "author",
        workflow_run_id=run_id,
    )
    _backdate_task(repo, task_id, minutes_old=50)

    resp = client.post(f"/api/runs/{run_id}/recovery/mark-stuck", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["marked"] is True
    assert data["previous_chapter_status"] == "drafted"
    assert data["new_chapter_status"] == "blocking"
    assert data["workflow_status"] == "blocked"
    assert data["closed_running_tasks"] == 1
    assert data["recovery"]["workflow_status"] == "blocked"
    assert data["recovery"]["can_reset"] is True
    assert repo.get_chapter("recover_mark_stuck", 1)["status"] == "blocking"

    conn = repo._conn()
    try:
        run = conn.execute(
            "SELECT status, error_message, completed_at FROM workflow_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        audit = conn.execute(
            "SELECT workflow_run_id, task_type, agent_id, status, error_message FROM task_status "
            "WHERE project_id=? AND chapter_number=? AND task_type='recover' "
            "ORDER BY id DESC LIMIT 1",
            ("recover_mark_stuck", 1),
        ).fetchone()
        original_task = conn.execute(
            "SELECT status, completed_at, error_message FROM task_status WHERE id=?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()

    assert run["status"] == "blocked"
    assert "疑似卡住" in run["error_message"]
    assert run["completed_at"]
    assert audit["workflow_run_id"] == run_id
    assert audit["task_type"] == "recover"
    assert audit["agent_id"] == "system"
    assert audit["status"] == "completed"
    assert "疑似卡住" in audit["error_message"]
    assert original_task["status"] == "failed"
    assert original_task["completed_at"]
    assert "疑似卡住" in original_task["error_message"]


def test_mark_stuck_run_preserves_reviewed_chapter_status(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "recover_reviewed_memory_stuck", minutes_old=50)
    repo.update_workflow_run(run_id, current_node="memory_curator")
    repo.update_chapter_status("recover_reviewed_memory_stuck", 1, "reviewed")
    lock = repo.acquire_memory_curator_lock("recover_reviewed_memory_stuck", 1, run_id=run_id)
    assert lock["acquired"] is True
    task_id = repo.start_task(
        "recover_reviewed_memory_stuck",
        1,
        "memory",
        "memory_curator",
        workflow_run_id=run_id,
    )
    _backdate_task(repo, task_id, minutes_old=50)

    preview = client.get(f"/api/runs/{run_id}/recovery")
    assert preview.status_code == 200
    preview_data = preview.json()["data"]
    assert preview_data["chapter_status"] == "reviewed"
    assert preview_data["stuck"] is True, preview_data
    assert preview_data["actions"]["mark_stuck_blocked"]["enabled"] is True

    resp = client.post(f"/api/runs/{run_id}/recovery/mark-stuck", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["previous_chapter_status"] == "reviewed"
    assert data["new_chapter_status"] == "reviewed"
    assert data["workflow_status"] == "blocked"
    assert data["closed_running_tasks"] == 1
    assert data["released_memory_lock"] is True
    assert repo.get_chapter("recover_reviewed_memory_stuck", 1)["status"] == "reviewed"
    assert repo.get_memory_curator_lock("recover_reviewed_memory_stuck", 1) is None

    conn = repo._conn()
    try:
        run = conn.execute(
            "SELECT status, error_message, completed_at FROM workflow_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        original_task = conn.execute(
            "SELECT status, completed_at, error_message FROM task_status WHERE id=?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()

    assert run["status"] == "blocked"
    assert "疑似卡住" in run["error_message"]
    assert run["completed_at"]
    assert original_task["status"] == "failed"
    assert original_task["completed_at"]


def test_reset_recovery_rejects_blocked_reviewed_memory_run_without_rewinding_chapter(tmp_path):
    client, repo, db_path = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_reviewed_blocked", status="reviewed")
    repo.update_workflow_run(
        run_id,
        status="blocked",
        current_node="memory_curator",
        error_message="节点 memory_curator 执行超时（>300秒），需要人工介入",
    )

    cp_path = derive_checkpoint_db_path(db_path)
    thread_id = get_checkpoint_thread_id("recover_reviewed_blocked", 1)
    with get_sqlite_checkpointer(cp_path) as cp:
        cp.put(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
            {"id": "recover-reviewed-cp", "chapter_status": "reviewed"},
            {},
            {},
        )
    assert checkpoint_thread_exists(db_path, "recover_reviewed_blocked", 1) is True

    preview = client.get(f"/api/runs/{run_id}/recovery").json()["data"]
    assert preview["chapter_status"] == "reviewed"
    assert preview["can_reset"] is False
    assert preview["actions"]["reset_to_planned"]["enabled"] is False
    assert preview["actions"]["backfill_memory"]["enabled"] is True

    resp = client.post(f"/api/runs/{run_id}/recovery/reset", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "MEMORY_BACKFILL_REQUIRED"
    assert repo.get_chapter("recover_reviewed_blocked", 1)["status"] == "reviewed"
    assert checkpoint_thread_exists(db_path, "recover_reviewed_blocked", 1) is True

    run = repo.get_workflow_runs_for_project("recover_reviewed_blocked", chapter_number=1, limit=1)[0]
    assert run["status"] == "blocked"
    assert run["current_node"] == "memory_curator"


def test_retry_author_node_recovers_to_scripted_without_full_reset(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "recover_retry_author", minutes_old=50)
    repo.update_workflow_run(run_id, status="blocked", current_node="author", error_message="LLM 响应超时")
    repo.update_chapter_status("recover_retry_author", 1, "blocking")

    preview = client.get(f"/api/runs/{run_id}/recovery").json()["data"]
    assert preview["actions"]["retry_current_node"]["enabled"] is True
    assert preview["actions"]["retry_current_node"]["target_status"] == "scripted"

    resp = client.post(f"/api/runs/{run_id}/recovery/retry-node", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["recovered"] is True
    assert data["previous_status"] == "blocking"
    assert data["new_status"] == "scripted"
    assert data["retry_node"] == "author"
    assert repo.get_chapter("recover_retry_author", 1)["status"] == "scripted"

    conn = repo._conn()
    try:
        run = conn.execute(
            "SELECT status, current_node, error_message FROM workflow_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        audit = conn.execute(
            "SELECT workflow_run_id, task_type, agent_id, status, error_message FROM task_status "
            "WHERE project_id=? AND chapter_number=? AND task_type='recover' "
            "ORDER BY id DESC LIMIT 1",
            ("recover_retry_author", 1),
        ).fetchone()
    finally:
        conn.close()

    assert run["status"] == "completed"
    assert run["current_node"] == "author_retry_recovery"
    assert run["error_message"] is None
    assert audit["workflow_run_id"] == run_id
    assert audit["agent_id"] == "human"
    assert "从执笔重新继续" in audit["error_message"]


def test_retry_node_resolves_failed_author_hidden_by_human_review(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_retry_author_wrapped")
    repo.update_workflow_run(
        run_id,
        status="blocked",
        current_node="human_review",
        error_message="章节审核未通过，进入人工审核",
    )
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id="recover_retry_author_wrapped",
        chapter_number=1,
        node_name="author",
        event_type="failed",
        status="failed",
        message="Author 纯正文生成空内容（已重试一次）",
    )
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id="recover_retry_author_wrapped",
        chapter_number=1,
        node_name="human_review",
        event_type="completed",
        status="blocked",
        message="进入人工审核",
    )

    preview = client.get(f"/api/runs/{run_id}/recovery").json()["data"]
    assert preview["actions"]["retry_current_node"]["enabled"] is True
    assert preview["actions"]["retry_current_node"]["resolved_failed_node"] == "author"
    assert preview["actions"]["retry_current_node"]["target_status"] == "scripted"

    resp = client.post(f"/api/runs/{run_id}/recovery/retry-node", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["resolved_failed_node"] == "author"
    assert data["retry_node"] == "author"
    assert data["new_status"] == "scripted"
    assert repo.get_chapter("recover_retry_author_wrapped", 1)["status"] == "scripted"
    run = repo.get_workflow_runs_for_project("recover_retry_author_wrapped", chapter_number=1, limit=1)[0]
    assert run["status"] == "completed"
    assert run["current_node"] == "author_retry_recovery"


def test_retry_node_rejects_unsupported_node(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_run(repo, "recover_retry_unsupported")
    repo.update_workflow_run(run_id, current_node="quality_gate")

    resp = client.post(f"/api/runs/{run_id}/recovery/retry-node", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NODE_RETRY_UNSUPPORTED"
    assert repo.get_chapter("recover_retry_unsupported", 1)["status"] == "blocking"


def test_mark_stuck_run_rejects_recent_running_run(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "recover_mark_recent", minutes_old=3)

    resp = client.post(f"/api/runs/{run_id}/recovery/mark-stuck", json={"confirm": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "RUN_NOT_STUCK"
    assert repo.get_chapter("recover_mark_recent", 1)["status"] == "drafted"


def test_mark_stuck_run_requires_confirmation(tmp_path):
    client, repo, _ = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "recover_mark_confirm", minutes_old=45)

    resp = client.post(f"/api/runs/{run_id}/recovery/mark-stuck", json={"confirm": False})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CONFIRM_REQUIRED"
    assert repo.get_chapter("recover_mark_confirm", 1)["status"] == "drafted"


def test_run_detail_page_contains_recovery_console():
    content = Path("frontend/src/pages/RunDetail.tsx").read_text(encoding="utf-8")

    assert "运行恢复" in content
    assert "/recovery/reset" in content
    assert "handleResetRecovery" in content
    assert "reset_to_planned" in content
    assert "/recovery/mark-stuck" in content
    assert "疑似卡住" in content
    assert "handleMarkStuck" in content
