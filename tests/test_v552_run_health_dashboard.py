"""v5.5.2 Run Health Dashboard tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _make_client(tmp_path):
    db_path = str(tmp_path / "run_health.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def _seed_running_run(
    repo: Repository,
    project_id: str,
    chapter_number: int = 1,
    minutes_old: int = 45,
) -> str:
    if not repo.get_project(project_id):
        repo.create_project(project_id=project_id, name=f"{project_id} Project", genre="fantasy")
    repo.add_chapter(project_id, chapter_number, title=f"Ch{chapter_number}", status="drafted")
    run_id = repo.create_workflow_run(project_id, chapter_number)
    repo.update_workflow_run(run_id, current_node="author")
    started_at = (datetime.now() - timedelta(minutes=minutes_old)).strftime("%Y-%m-%d %H:%M:%S")
    conn = repo._conn()
    try:
        conn.execute("UPDATE workflow_runs SET started_at=? WHERE id=?", (started_at, run_id))
        conn.commit()
    finally:
        conn.close()
    return run_id


def _seed_blocked_run(repo: Repository, project_id: str, chapter_number: int = 2) -> str:
    if not repo.get_project(project_id):
        repo.create_project(project_id=project_id, name=f"{project_id} Project", genre="fantasy")
    repo.add_chapter(project_id, chapter_number, title=f"Ch{chapter_number}", status="blocking")
    run_id = repo.create_workflow_run(project_id, chapter_number)
    repo.update_workflow_run(run_id, status="blocked", error_message="质量门阻塞")
    return run_id


def test_run_health_lists_stuck_running_runs(tmp_path):
    client, repo = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "health_stuck", minutes_old=45)
    task_id = repo.start_task("health_stuck", 1, "create", "author", workflow_run_id=run_id)
    conn = repo._conn()
    try:
        started_at = (datetime.now() - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE task_status SET started_at=? WHERE id=?", (started_at, task_id))
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/api/runs/health")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["summary"]["stuck"] == 1
    assert data["summary"]["actionable"] == 1
    assert data["runs"][0]["run_id"] == run_id
    assert data["runs"][0]["stuck"] is True
    assert data["runs"][0]["actions"]["mark_stuck_blocked"]["enabled"] is True
    assert data["runs"][0]["running_tasks"][0]["stuck"] is True
    assert data["runs"][0]["running_tasks"][0]["task_label"] == "生成任务"
    assert data["runs"][0]["running_tasks"][0]["agent_label"] == "执笔"


def test_run_health_project_filter(tmp_path):
    client, repo = _make_client(tmp_path)
    wanted = _seed_running_run(repo, "health_filter_a", minutes_old=40)
    _seed_running_run(repo, "health_filter_b", minutes_old=40)

    resp = client.get("/api/runs/health?project_id=health_filter_a")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["project_id"] == "health_filter_a"
    assert [run["run_id"] for run in data["runs"]] == [wanted]


def test_run_health_includes_blocked_and_failed_runs(tmp_path):
    client, repo = _make_client(tmp_path)
    blocked_id = _seed_blocked_run(repo, "health_issue")
    failed_id = _seed_running_run(repo, "health_issue", chapter_number=3, minutes_old=5)
    repo.update_workflow_run(failed_id, status="failed", error_message="LLM error")

    resp = client.get("/api/runs/health?project_id=health_issue")

    assert resp.status_code == 200
    data = resp.json()["data"]
    statuses = {run["run_id"]: run["workflow_status"] for run in data["runs"]}
    assert statuses[blocked_id] == "blocked"
    assert statuses[failed_id] == "failed"
    assert data["summary"]["blocked"] == 1
    assert data["summary"]["failed"] == 1


def test_run_health_batch_mark_stuck(tmp_path):
    client, repo = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "health_batch", minutes_old=50)

    resp = client.post(
        "/api/runs/health/mark-stuck",
        json={"run_ids": [run_id], "confirm": True},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["requested"] == 1
    assert data["marked"] == 1
    assert data["failed"] == 0
    assert data["results"][0]["ok"] is True
    assert repo.get_chapter("health_batch", 1)["status"] == "blocking"


def test_run_health_batch_mark_stuck_reports_partial_failure(tmp_path):
    client, repo = _make_client(tmp_path)
    stuck_id = _seed_running_run(repo, "health_partial", chapter_number=1, minutes_old=50)
    recent_id = _seed_running_run(repo, "health_partial", chapter_number=2, minutes_old=5)

    resp = client.post(
        "/api/runs/health/mark-stuck",
        json={"run_ids": [stuck_id, recent_id], "confirm": True},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["marked"] == 1
    assert data["failed"] == 1
    by_run = {item["run_id"]: item for item in data["results"]}
    assert by_run[stuck_id]["ok"] is True
    assert by_run[recent_id]["ok"] is False
    assert by_run[recent_id]["error_code"] == "RUN_NOT_STUCK"


def test_run_health_batch_mark_requires_confirmation(tmp_path):
    client, repo = _make_client(tmp_path)
    run_id = _seed_running_run(repo, "health_confirm", minutes_old=50)

    resp = client.post(
        "/api/runs/health/mark-stuck",
        json={"run_ids": [run_id], "confirm": False},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CONFIRM_REQUIRED"
    assert repo.get_chapter("health_confirm", 1)["status"] == "drafted"


def test_settings_contains_run_health_dashboard():
    settings = Path("frontend/src/pages/Settings.tsx").read_text(encoding="utf-8")
    panel = Path("frontend/src/components/settings/RunHealthPanel.tsx").read_text(encoding="utf-8")

    assert "运行健康" in settings
    assert "RunHealthPanel" in settings
    assert "/runs/health?limit=100" in panel
    assert "/runs/health/mark-stuck" in panel
    assert "标记为阻塞" in panel
