"""Regression tests for stale Genesis run recovery."""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _stale_genesis_api(tmp_path):
    db_path = str(tmp_path / "stale_genesis.db")
    init_db(db_path)
    repo = Repository(db_path)
    repo.create_project(
        project_id="stale-genesis",
        name="Stale Genesis",
        genre="科幻",
        description="海潮与档案馆的悬疑故事。",
        total_chapters_planned=10,
        target_words=30000,
    )
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), repo


def _create_stale_running_genesis(repo: Repository) -> dict:
    run = repo.create_genesis_run(
        "stale-genesis",
        input_json='{"title":"Stale Genesis","genre":"科幻"}',
        status="running",
    )
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE genesis_runs "
            "SET created_at=datetime('now','-2 hours','+8 hours'), "
            "updated_at=datetime('now','-2 hours','+8 hours') "
            "WHERE id=?",
            (run["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    return repo.get_genesis_run(run["id"])


def test_latest_marks_stale_running_genesis_failed(tmp_path):
    client, repo = _stale_genesis_api(tmp_path)
    run = _create_stale_running_genesis(repo)

    resp = client.get("/api/projects/stale-genesis/genesis/latest")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["id"] == run["id"]
    assert data["status"] == "failed"
    assert "超过 30 分钟未更新" in data["error_message"]
    persisted = repo.get_genesis_run(run["id"])
    assert persisted["status"] == "failed"


def test_generate_ignores_stale_running_genesis_and_retries(tmp_path):
    client, repo = _stale_genesis_api(tmp_path)
    stale = _create_stale_running_genesis(repo)

    resp = client.post(
        "/api/projects/stale-genesis/genesis/generate",
        json={
            "title": "Stale Genesis",
            "genre": "科幻",
            "premise": "海潮与档案馆的悬疑故事。",
            "target_chapters": 3,
            "target_words": 12000,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["data"]["status"] == "generated"

    assert repo.get_genesis_run(stale["id"])["status"] == "failed"
    assert payload["data"]["id"] != stale["id"]


def test_production_next_recovers_stale_genesis_instead_of_waiting(tmp_path):
    client, repo = _stale_genesis_api(tmp_path)
    run = _create_stale_running_genesis(repo)

    resp = client.get("/api/projects/stale-genesis/production-next")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["next_action"]["key"] == "generate_genesis"
    assert repo.get_genesis_run(run["id"])["status"] == "failed"
