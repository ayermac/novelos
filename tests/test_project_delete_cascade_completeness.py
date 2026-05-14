"""Project deletion cascade coverage for newer production tables."""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _make_client(tmp_path):
    db_path = str(tmp_path / "delete_project.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def _seed_newer_project_rows(repo: Repository, project_id: str) -> None:
    """Seed rows from tables added after the original project delete tests."""
    repo.create_project(project_id=project_id, name="Delete Cascade")
    repo.add_chapter(project_id, 1, title="Ch1", status="drafted")
    run_id = repo.create_workflow_run(project_id, 1)

    conn = repo._conn()
    try:
        conn.execute(
            "INSERT INTO style_bibles (id, project_id, name, bible_json) "
            "VALUES ('style-1', ?, 'Main Style', '{}')",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO style_bible_versions "
            "(id, project_id, style_bible_id, version, bible_json) "
            "VALUES ('style-v1', ?, 'style-1', '1.0.0', '{}')",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO style_evolution_proposals "
            "(id, project_id, proposal_type, source, proposal_json) "
            "VALUES ('style-proposal-1', ?, 'tone', 'test', '{}')",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO style_samples "
            "(id, project_id, name, source_type, content_hash, created_at) "
            "VALUES ('sample-1', ?, 'Sample', 'text', 'hash-1', datetime('now','+8 hours'))",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO project_skill_overrides (project_id, overrides_json) VALUES (?, '{}')",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO genesis_runs (id, project_id, status, input_json) "
            "VALUES ('genesis-1', ?, 'approved', '{}')",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO memory_update_batches (id, project_id, chapter_number, run_id) "
            "VALUES ('mem-batch-1', ?, 1, ?)",
            (project_id, run_id),
        )
        conn.execute(
            "INSERT INTO memory_update_items "
            "(id, batch_id, project_id, target_table, operation, after_json) "
            "VALUES ('mem-item-1', 'mem-batch-1', ?, 'characters', 'update', '{}')",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO story_facts "
            "(id, project_id, fact_key, fact_type, value_json) "
            "VALUES ('fact-1', ?, 'fuel', 'resource', '{}')",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO story_fact_events "
            "(id, fact_id, project_id, chapter_number, run_id, agent_id, event_type) "
            "VALUES ('fact-event-1', 'fact-1', ?, 1, ?, 'author', 'create')",
            (project_id, run_id),
        )
        conn.execute(
            "INSERT INTO workflow_node_events "
            "(run_id, project_id, chapter_number, node_name, event_type, status) "
            "VALUES (?, ?, 1, 'author', 'started', 'running')",
            (run_id, project_id),
        )
        conn.execute(
            "INSERT INTO skill_runs "
            "(project_id, chapter_number, skill_id, skill_type, ok) "
            "VALUES (?, 1, 'style-bible-checker', 'validator', 1)",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO production_runs "
            "(id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
            "VALUES ('prod-1', ?, 1, 1, 'awaiting_review', 1, datetime('now','+8 hours'), datetime('now','+8 hours'))",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO production_run_items "
            "(id, run_id, project_id, chapter_number, workflow_run_id, status, created_at, updated_at) "
            "VALUES ('prod-item-1', 'prod-1', ?, 1, ?, 'blocked', datetime('now','+8 hours'), datetime('now','+8 hours'))",
            (project_id, run_id),
        )
        conn.execute(
            "INSERT INTO batch_continuity_gates "
            "(id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
            "VALUES ('gate-1', 'prod-1', ?, 1, 1, 'passed', datetime('now','+8 hours'), datetime('now','+8 hours'))",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO human_review_sessions "
            "(id, run_id, project_id, decision, created_at) "
            "VALUES ('review-session-1', 'prod-1', ?, 'request_changes', datetime('now','+8 hours'))",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO batch_revision_runs "
            "(id, source_run_id, project_id, status, decision_session_id, plan_json, affected_chapters_json, created_at, updated_at) "
            "VALUES ('revision-1', 'prod-1', ?, 'pending', 'review-session-1', '{}', '[]', datetime('now','+8 hours'), datetime('now','+8 hours'))",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO batch_revision_items "
            "(id, revision_run_id, chapter_number, action, status, workflow_run_id, created_at, updated_at) "
            "VALUES ('revision-item-1', 'revision-1', 1, 'rerun_chapter', 'pending', ?, datetime('now','+8 hours'), datetime('now','+8 hours'))",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO chapter_review_notes "
            "(id, project_id, chapter_number, source_run_id, revision_run_id, notes, created_at) "
            "VALUES ('note-1', ?, 1, 'prod-1', 'revision-1', 'notes', datetime('now','+8 hours'))",
            (project_id,),
        )
        chapter_id = conn.execute(
            "SELECT id FROM chapters WHERE project_id=? AND chapter_number=1",
            (project_id,),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO reviews (id, project_id, chapter_id, pass, score) "
            "VALUES (9001, ?, ?, 1, 92)",
            (project_id, chapter_id),
        )
        conn.execute(
            "INSERT INTO chapter_versions "
            "(id, project_id, chapter, version, content, review_id) "
            "VALUES (9001, ?, 1, 1, 'content', 9001)",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO production_queue "
            "(id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
            "VALUES ('queue-1', ?, 1, 1, 'pending', datetime('now','+8 hours'), datetime('now','+8 hours'))",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO production_queue_events "
            "(id, queue_id, event_type, created_at) "
            "VALUES ('queue-event-1', 'queue-1', 'created', datetime('now','+8 hours'))"
        )
        conn.execute(
            "INSERT INTO serial_plans "
            "(id, project_id, name, start_chapter, target_chapter, batch_size, current_chapter, status, total_planned_chapters, created_at, updated_at) "
            "VALUES ('serial-1', ?, 'Serial', 1, 10, 1, 1, 'active', 10, datetime('now','+8 hours'), datetime('now','+8 hours'))",
            (project_id,),
        )
        conn.execute(
            "INSERT INTO serial_plan_events "
            "(id, serial_plan_id, event_type, created_at) "
            "VALUES ('serial-event-1', 'serial-1', 'created', datetime('now','+8 hours'))"
        )
        conn.commit()
    finally:
        conn.close()


def _count_project_rows(repo: Repository, project_id: str) -> int:
    conn = repo._conn()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        total = 0
        for table in tables:
            columns = conn.execute(f"PRAGMA table_info({table['name']})").fetchall()
            if any(column["name"] == "project_id" for column in columns):
                row = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM {table['name']} WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                total += row["cnt"]
        return total
    finally:
        conn.close()


def test_delete_project_cascades_newer_project_tables(tmp_path):
    _, repo = _make_client(tmp_path)
    project_id = "delete_newer_tables"
    _seed_newer_project_rows(repo, project_id)

    assert _count_project_rows(repo, project_id) > 0

    assert repo.delete_project(project_id) is True

    assert repo.get_project(project_id) is None
    assert _count_project_rows(repo, project_id) == 0


def test_delete_project_api_cascades_newer_project_tables(tmp_path):
    client, repo = _make_client(tmp_path)
    project_id = "delete_newer_tables_api"
    _seed_newer_project_rows(repo, project_id)

    resp = client.delete(f"/api/projects/{project_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["deleted"] is True
    assert repo.get_project(project_id) is None
    assert _count_project_rows(repo, project_id) == 0
