"""Regression tests for MemoryCurator per-chapter extraction locking."""

from __future__ import annotations

from typing import Any

import pytest

from novel_factory.llm.provider import LLMProvider


class CountingMemoryProvider(LLMProvider):
    """Small provider that succeeds if the lock lets MemoryCurator run."""

    def __init__(self):
        self.call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None):
        self.call_count += 1
        return {
            "patches": [
                {
                    "target_table": "story_facts",
                    "operation": "create",
                    "target_name": "lock_test_fact",
                    "data": {
                        "fact_key": "lock_test_fact",
                        "fact_type": "narrative_event",
                        "value": {"text": "lock test"},
                    },
                    "confidence": 0.85,
                    "evidence_text": "lock test evidence",
                    "rationale": "normal extraction",
                }
            ]
        }

    def invoke_text(self, messages, temperature=None, max_tokens=None, max_retries=None, request_timeout_seconds=None):
        self.call_count += 1
        return "ok"


def _seed_repo(tmp_path):
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    db_path = tmp_path / "memory-lock.db"
    init_db(db_path)
    repo = Repository(str(db_path))
    repo.create_project(project_id="memory-lock-proj", name="Memory Lock", genre="test")
    repo.add_chapter("memory-lock-proj", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content(
        "memory-lock-proj",
        1,
        "第1章\n\n这是一段用于记忆提取的正文。陆澈发现了一条新的事实线索。",
    )
    return repo


@pytest.fixture
def db_path(tmp_path):
    from novel_factory.db.connection import init_db

    db_file = tmp_path / "memory-lock-api.db"
    init_db(str(db_file))
    yield str(db_file)


@pytest.fixture
def client(db_path):
    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app

    app = create_api_app(db_path=db_path, llm_mode="stub")
    with TestClient(app) as test_client:
        yield test_client


def test_memory_curator_lock_is_exclusive_per_chapter(tmp_path):
    """A second lock for the same project/chapter should be refused."""
    repo = _seed_repo(tmp_path)

    first = repo.acquire_memory_curator_lock(
        "memory-lock-proj",
        1,
        run_id="run-1",
    )
    second = repo.acquire_memory_curator_lock(
        "memory-lock-proj",
        1,
        run_id="run-2",
    )

    assert first["acquired"] is True
    assert second["acquired"] is False
    assert second["lock"]["run_id"] == "run-1"


def test_memory_curator_lock_recovers_stale_running_lock(tmp_path):
    """A stale running lock should not block a chapter forever after a crash."""
    repo = _seed_repo(tmp_path)
    first = repo.acquire_memory_curator_lock(
        "memory-lock-proj",
        1,
        run_id="stale-run",
    )
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE memory_curator_locks "
            "SET locked_at=datetime('now', '+8 hours', '-3 hours') "
            "WHERE project_id=? AND chapter_number=?",
            ("memory-lock-proj", 1),
        )
        conn.commit()
    finally:
        conn.close()

    second = repo.acquire_memory_curator_lock(
        "memory-lock-proj",
        1,
        run_id="fresh-run",
    )

    assert first["acquired"] is True
    assert second["acquired"] is True
    assert second["lock"]["run_id"] == "fresh-run"


def test_memory_curator_agent_does_not_extract_when_lock_is_held(tmp_path):
    """The agent should report a lock conflict without treating it as extraction failure."""
    from novel_factory.agents.memory_curator import MemoryCuratorAgent

    repo = _seed_repo(tmp_path)
    repo.acquire_memory_curator_lock("memory-lock-proj", 1, run_id="run-1")
    provider = CountingMemoryProvider()

    agent = MemoryCuratorAgent(repo, provider)
    result: dict[str, Any] = agent.run(
        {
            "project_id": "memory-lock-proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-2",
            "llm_mode": "real",
        }
    )

    assert result["memory_curator_processed"] is False
    assert result["memory_curator_locked"] is True
    assert "error" not in result
    assert "正在提取" in result["memory_curator_warning"]
    assert provider.call_count == 0
    assert repo.list_memory_batches("memory-lock-proj") == []


def test_memory_curator_lock_is_not_real_mode_extraction_failure():
    """A lock conflict is a concurrency signal, not a failed extraction."""
    from novel_factory.workflow.nodes import _memory_curator_real_mode_error
    from novel_factory.workflow.conditions import route_after_memory_curator

    error = _memory_curator_real_mode_error(
        {"llm_mode": "real"},
        {
            "memory_curator_locked": True,
            "memory_curator_warning": "第1章记忆正在提取，不能重复启动。",
            "extraction_success": False,
        },
    )

    assert error is None
    assert route_after_memory_curator({"llm_mode": "real", "memory_curator_locked": True}) == "awaiting_publish"


def test_memory_curator_releases_lock_after_success(tmp_path):
    """A completed extraction should release the lock so a later run can proceed."""
    from novel_factory.agents.memory_curator import MemoryCuratorAgent

    repo = _seed_repo(tmp_path)
    provider = CountingMemoryProvider()
    agent = MemoryCuratorAgent(repo, provider)

    first = agent.run(
        {
            "project_id": "memory-lock-proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-1",
            "llm_mode": "real",
        }
    )
    second_lock = repo.acquire_memory_curator_lock("memory-lock-proj", 1, run_id="run-2")

    assert first["memory_curator_processed"] is True
    assert first["memory_batch_id"]
    assert second_lock["acquired"] is True


def test_memory_backfill_reports_running_lock_without_new_batch(client, db_path):
    """Manual memory backfill should not launch extraction while the chapter lock is held."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="memory-lock-api-proj", name="Memory Lock API", genre="test")
    repo.add_chapter("memory-lock-api-proj", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("memory-lock-api-proj", 1, "第1章\n\n陆澈发现离线证据。")
    source_run_id = repo.create_workflow_run("memory-lock-api-proj", 1)
    repo.update_workflow_run(source_run_id, status="completed", current_node="awaiting_publish")
    repo.acquire_memory_curator_lock("memory-lock-api-proj", 1, run_id="active-run")

    response = client.post(
        f"/api/runs/{source_run_id}/memory/backfill",
        json={"confirm": True, "force": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "MEMORY_CURATOR_RUNNING"
    details = body["error"]["details"]
    assert details["active_run_id"] == "active-run"
    assert details["domain_result"]["domain_status"] == "blocked"
    assert repo.list_memory_batches("memory-lock-api-proj") == []


def test_memory_backfill_lock_does_not_ignore_existing_fallback(client, db_path):
    """force=true must not mutate existing fallback batches when the lock is held."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="memory-lock-fallback-proj", name="Memory Lock Fallback", genre="test")
    repo.add_chapter("memory-lock-fallback-proj", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("memory-lock-fallback-proj", 1, "第1章\n\n状态卡兜底候选仍在。")
    source_run_id = repo.create_workflow_run("memory-lock-fallback-proj", 1)
    repo.update_workflow_run(source_run_id, status="completed", current_node="awaiting_publish")
    batch = repo.create_memory_batch(
        "memory-lock-fallback-proj",
        chapter_number=1,
        summary="第1章记忆提取 - 状态卡兜底 (1项)",
    )
    repo.create_memory_item(
        batch_id=batch["id"],
        project_id="memory-lock-fallback-proj",
        target_table="story_facts",
        operation="create",
        after_json='{"fact_key":"fallback_fact"}',
        confidence=0.45,
        evidence_text="状态卡兜底候选仍在。",
        rationale="状态卡兜底候选：未经过 MemoryCurator LLM 复核",
    )
    repo.acquire_memory_curator_lock("memory-lock-fallback-proj", 1, run_id="active-run")

    response = client.post(
        f"/api/runs/{source_run_id}/memory/backfill",
        json={"confirm": True, "force": True},
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == "MEMORY_CURATOR_RUNNING"
    assert repo.get_memory_batch(batch["id"])["status"] == "pending"


def test_publish_reports_running_memory_lock_without_publishing(client, db_path):
    """Manual publish should wait when memory extraction is already running."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="memory-lock-publish-proj", name="Memory Lock Publish", genre="test")
    repo.add_chapter("memory-lock-publish-proj", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("memory-lock-publish-proj", 1, "第1章\n\n陆澈准备发布前等待记忆提取。")
    repo.acquire_memory_curator_lock("memory-lock-publish-proj", 1, run_id="active-memory-run")

    response = client.post(
        "/api/publish/chapter",
        json={"project_id": "memory-lock-publish-proj", "chapter": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "MEMORY_CURATOR_RUNNING"
    assert body["error"]["message"] == "第 1 章记忆提取正在进行中，请等待完成后再发布。"
    assert body["error"]["details"]["active_run_id"] == "active-memory-run"
    assert (
        body["error"]["details"]["domain_result"]["user_message"]
        == "记忆提取正在进行中，请等待完成后再发布。"
    )
    assert repo.get_chapter("memory-lock-publish-proj", 1)["status"] == "reviewed"
    assert repo.list_memory_batches("memory-lock-publish-proj") == []


def test_timeline_keeps_running_memory_curator_visible_for_reviewed_chapter(client, db_path):
    """Timeline must not hide an active MemoryCurator behind awaiting_publish."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="memory-lock-timeline-proj", name="Memory Lock Timeline", genre="test")
    repo.add_chapter("memory-lock-timeline-proj", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("memory-lock-timeline-proj", 1, "第1章\n\n陆澈正在等待记忆提取。")
    run_id = repo.create_workflow_run("memory-lock-timeline-proj", 1)
    repo.update_workflow_run(run_id, status="running", current_node="memory_curator")
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id="memory-lock-timeline-proj",
        chapter_number=1,
        node_name="memory_curator",
        event_type="started",
        status="running",
        message="开始记忆整理",
    )
    repo.acquire_memory_curator_lock("memory-lock-timeline-proj", 1, run_id=run_id)

    response = client.get("/api/projects/memory-lock-timeline-proj/chapters/1/workflow-timeline")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["run_id"] == run_id
    assert data["run_status"] == "running"
    assert data["current_node"] == "memory_curator"
    memory_node = next(node for node in data["nodes"] if node["node_name"] == "memory_curator")
    assert memory_node["status"] == "running"
    persisted = repo.get_workflow_runs_for_project("memory-lock-timeline-proj", chapter_number=1, limit=1)[0]
    assert persisted["status"] == "running"
    assert persisted["current_node"] == "memory_curator"


def test_publish_ignores_stale_memory_lock_when_batch_exists(client, db_path):
    """A stale lock should not make publish rerun or block after memory already exists."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="memory-lock-stale-publish-proj", name="Memory Lock Stale Publish", genre="test")
    repo.add_chapter("memory-lock-stale-publish-proj", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("memory-lock-stale-publish-proj", 1, "第1章\n\n陆澈已经有记忆批次。")
    batch = repo.create_memory_batch(
        "memory-lock-stale-publish-proj",
        chapter_number=1,
        run_id="old-memory-run",
        summary="第1章记忆提取 - 状态卡兜底 (1项)",
    )
    repo.create_memory_item(
        batch_id=batch["id"],
        project_id="memory-lock-stale-publish-proj",
        target_table="story_facts",
        operation="create",
        after_json='{"fact_key":"stale_lock_fact"}',
        confidence=0.45,
        evidence_text="陆澈已经有记忆批次。",
        rationale="状态卡兜底候选：未经过 MemoryCurator LLM 复核",
    )
    repo.acquire_memory_curator_lock("memory-lock-stale-publish-proj", 1, run_id="stale-memory-run")
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE memory_curator_locks "
            "SET locked_at=datetime('now', '+8 hours', '-3 hours') "
            "WHERE project_id=? AND chapter_number=?",
            ("memory-lock-stale-publish-proj", 1),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.post(
        "/api/publish/chapter",
        json={"project_id": "memory-lock-stale-publish-proj", "chapter": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["chapter_status"] == "published"
    assert body["data"]["memory_curator_skipped"] is True
    assert repo.get_memory_curator_lock("memory-lock-stale-publish-proj", 1) is None
