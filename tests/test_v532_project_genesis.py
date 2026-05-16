"""Tests for v5.3.2 Genesis canonical body-style API routes."""

import os
import tempfile
import asyncio
import time
import json
from types import SimpleNamespace

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
        "project_id": "test-genesis",
        "name": "Test Genesis",
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


class TestGenesisCanonicalRoutes:
    """v5.3.2: Genesis actions use body-style (project_id in body, not URL)."""

    def test_generate_canonical_body_style(self, client, project_id):
        """POST /api/genesis/generate with project_id in body."""
        resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
            "target_chapters": 10,
            "target_words": 30000,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        genesis = body["data"]
        assert genesis["project_id"] == project_id
        assert genesis["status"] == "generated"

    def test_generate_rejects_empty_creative_brief(self, client, project_id):
        """Genesis should not generate from a blank form/default template."""
        blank_project_id = "blank-genesis-input"
        # v6.3.2: Create a project with no name/genre so inheritance cannot fill blanks.
        create_resp = client.post("/api/onboarding/projects", json={
            "project_id": blank_project_id,
            "name": "",
            "genre": "",
            "description": "",
            "total_chapters_planned": 10,
            "target_words": 30000,
        })
        assert create_resp.status_code == 200

        resp = client.post("/api/genesis/generate", json={
            "project_id": blank_project_id,
            "title": "",
            "genre": "",
            "premise": "",
            "target_chapters": 10,
            "target_words": 30000,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "GENESIS_INPUT_REQUIRED"

        latest = client.get(f"/api/projects/{blank_project_id}/genesis/latest").json()
        assert latest["ok"] is True
        assert latest["data"] is None

    def test_generate_inherits_project_title_genre_and_description(self, client, project_id):
        """Genesis should reuse onboarding project fields instead of asking again."""
        resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "",
            "genre": "",
            "premise": "",
            "target_chapters": 3,
            "target_words": 9000,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

        genesis = body["data"]
        input_data = json.loads(genesis["input_json"])
        assert input_data["title"] == "Test Genesis"
        assert input_data["genre"] == "奇幻"
        assert input_data["premise"] == "A test novel"

    def test_generate_requires_project_id_in_body(self, client):
        """POST /api/genesis/generate without project_id should fail."""
        resp = client.post("/api/genesis/generate", json={
            "title": "Test",
            "genre": "奇幻",
        })
        # Should fail because project_id is missing or invalid
        assert resp.status_code == 200
        body = resp.json()
        # Either validation error or project not found
        assert body["ok"] is False or body.get("data", {}).get("status") == "failed"

    def test_approve_canonical_body_style(self, client, project_id):
        """POST /api/genesis/approve with project_id and genesis_id in body."""
        # First generate
        gen_resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        assert gen_resp.status_code == 200
        genesis_id = gen_resp.json()["data"]["id"]

        # Then approve via canonical route
        resp = client.post("/api/genesis/approve", json={
            "project_id": project_id,
            "genesis_id": genesis_id,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_reject_canonical_body_style(self, client, project_id):
        """POST /api/genesis/reject with project_id and genesis_id in body."""
        # First generate
        gen_resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        assert gen_resp.status_code == 200
        genesis_id = gen_resp.json()["data"]["id"]

        # Then reject via canonical route
        resp = client.post("/api/genesis/reject", json={
            "project_id": project_id,
            "genesis_id": genesis_id,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_approve_wrong_project_returns_error(self, client, project_id):
        """Approve with wrong project_id returns error."""
        gen_resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        genesis_id = gen_resp.json()["data"]["id"]

        resp = client.post("/api/genesis/approve", json={
            "project_id": "nonexistent",
            "genesis_id": genesis_id,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False

    def test_old_path_style_still_works(self, client, project_id):
        """Legacy path-style routes remain functional for backward compat."""
        resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True


@pytest.mark.asyncio
async def test_real_genesis_generation_does_not_block_event_loop(monkeypatch):
    """Real genesis LLM calls must be offloaded so status APIs can stay responsive."""
    from novel_factory.api.routes import genesis as genesis_routes

    class BlockingProvider:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            assert max_tokens == 7000
            time.sleep(0.2)
            return {
                "project_updates": {"description": "ok"},
                "world_settings": [],
                "characters": [],
                "factions": [],
                "outlines": [],
                "plot_holes": [],
                "instructions": [],
            }

    class Router:
        def for_agent(self, agent_name):
            return BlockingProvider()

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    body = genesis_routes.GenesisGenerateRequest(
        title="事件循环测试",
        genre="悬疑",
        premise="验证 real genesis 不阻塞 API 事件循环",
    )
    task = asyncio.create_task(
        genesis_routes._generate_real_draft(body, SimpleNamespace())
    )

    started = time.perf_counter()
    await asyncio.sleep(0.05)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.15
    assert await task == {
        "project_updates": {"description": "ok"},
        "world_settings": [],
        "characters": [],
        "factions": [],
        "outlines": [],
        "plot_holes": [],
        "instructions": [],
    }


@pytest.mark.asyncio
async def test_real_genesis_prompt_treats_chapter_count_as_initial_batch(monkeypatch):
    """Genesis prompt should not imply target_chapters is the whole book length."""
    from novel_factory.api.routes import genesis as genesis_routes

    captured: dict[str, list[dict[str, str]]] = {}

    class CapturingProvider:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            captured["messages"] = messages
            return {
                "project_updates": {"description": "ok"},
                "world_settings": [],
                "characters": [],
                "factions": [],
                "outlines": [],
                "plot_holes": [],
                "instructions": [],
            }

    class Router:
        def for_agent(self, agent_name):
            return CapturingProvider()

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    body = genesis_routes.GenesisGenerateRequest(
        title="首批规划测试",
        genre="都市幻想",
        premise="验证创世章数不会被理解成全书长度",
        target_chapters=10,
        target_words=30000,
    )

    await genesis_routes._generate_real_draft(body, SimpleNamespace())

    prompt = captured["messages"][1]["content"]
    assert "首批章节规划范围: 前 10 章，首批合计约 30000 字" in prompt
    assert "不是整本书总篇幅" in prompt
    assert "篇幅: 10章" not in prompt


@pytest.mark.asyncio
async def test_real_genesis_uses_dedicated_llm_profile_and_runtime_budget(monkeypatch):
    """Genesis should not share planner's short chapter-planning runtime budget."""
    from novel_factory.api.routes import genesis as genesis_routes

    captured: dict[str, object] = {}

    class CapturingProvider:
        def __init__(self):
            self.config = SimpleNamespace(
                request_timeout_seconds=45,
                retry_attempts=1,
            )

        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            captured["timeout"] = self.config.request_timeout_seconds
            captured["retry_attempts"] = self.config.retry_attempts
            captured["max_tokens"] = max_tokens
            return {
                "project_updates": {"description": "ok"},
                "world_settings": [],
                "characters": [],
                "factions": [],
                "outlines": [],
                "plot_holes": [],
                "instructions": [],
            }

    class Router:
        def __init__(self):
            self.provider = CapturingProvider()

        def for_agent(self, agent_name):
            captured["agent_name"] = agent_name
            return self.provider

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    body = genesis_routes.GenesisGenerateRequest(
        title="创世路由测试",
        genre="都市幻想",
        premise="验证创世使用独立 profile",
        target_chapters=10,
        target_words=30000,
    )

    await genesis_routes._generate_real_draft(body, SimpleNamespace())

    assert captured["agent_name"] == "genesis"
    assert captured["timeout"] == 180
    assert captured["retry_attempts"] == 2
    assert captured["max_tokens"] == 7000
