"""v5.5.14 release stabilization tests."""

from __future__ import annotations

import os
import tempfile

from fastapi.testclient import TestClient


def _client_with_repo():
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path), db_path


def test_health_summary_reports_stale_run_and_obsolete_session():
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "stabilize-health"
        repo.create_project(
            project_id=project_id,
            name="Stabilize Health",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="published")
        repo.add_chapter(project_id, 2, "第二章", status="reviewed")

        run_id = repo.create_workflow_run(project_id, 2)
        repo.update_workflow_run(run_id, status="running", current_node="polisher")
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_runs SET started_at=datetime('now','-2 hours','+8 hours') WHERE id=?",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()

        session = repo.create_auto_run_session(
            project_id,
            chapter_start=1,
            chapter_end=10,
            max_steps=5,
            dry_run=False,
            stop_on_review=True,
        )
        repo.create_auto_run_step(
            session["id"],
            step_number=1,
            action="continue_next_chapter",
            label="继续生成第 2 章",
            target_chapter=2,
        )
        repo.update_auto_run_session_status(
            session["id"],
            "paused",
            stop_reason="client_disconnected",
            last_event="step_started",
        )

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "blocking"
        assert data["summary"]["stale_runs"] == 1
        assert data["summary"]["obsolete_sessions"] == 1
        keys = {item["key"].split(":")[0] for item in data["items"]}
        assert "stale_run" in keys
        assert "obsolete_session" in keys
        obsolete_item = next(item for item in data["items"] if item["key"].startswith("obsolete_session:"))
        assert obsolete_item["action_url"].endswith(f"/sessions/{session['id']}")
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_health_summary_keeps_live_disconnected_session_when_workflow_is_running():
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "live-session"
        repo.create_project(
            project_id=project_id,
            name="Live Session",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="planned")

        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="author")

        session = repo.create_auto_run_session(
            project_id,
            chapter_start=1,
            chapter_end=10,
            max_steps=5,
            dry_run=False,
            stop_on_review=True,
        )
        repo.create_auto_run_step(
            session["id"],
            step_number=1,
            action="generate_chapter",
            label="生成第 1 章",
            target_chapter=1,
        )
        repo.update_auto_run_session_status(
            session["id"],
            "paused",
            stop_reason="client_disconnected",
            last_event="step_started",
        )

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["obsolete_sessions"] == 0
        keys = {item["key"].split(":")[0] for item in data["items"]}
        assert "obsolete_session" not in keys
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_health_summary_reports_pending_memory_updates():
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "pending-memory"
        repo.create_project(
            project_id=project_id,
            name="Pending Memory",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="new facts")
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="characters",
            operation="update",
            after_json='{"name":"Test"}',
            target_id="1",
        )

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "attention"
        assert data["summary"]["pending_memory_items"] == 1
        memory_item = next(item for item in data["items"] if item["key"] == "pending_memory_updates")
        assert memory_item["action_url"] == f"/projects/{project_id}?module=memory"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
