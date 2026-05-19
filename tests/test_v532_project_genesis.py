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

        # Then approve via canonical route (force apply to bypass quality gate for stub draft)
        resp = client.post("/api/genesis/approve", json={
            "project_id": project_id,
            "genesis_id": genesis_id,
            "force_apply": True,
            "confirm_quality_risk": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_approve_applies_draft_to_formal_context_tables(self):
        """Approving genesis must persist draft data into production context tables."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(db_path)
            repo = Repository(db_path)
            test_client = TestClient(create_api_app(db_path=db_path, llm_mode="stub"))
            project_id = "genesis-apply-test"
            create_resp = test_client.post("/api/onboarding/projects", json={
                "project_id": project_id,
                "name": "创世应用测试",
                "genre": "都市修仙",
                "description": "验证创世草案批准后写入正式上下文",
                "total_chapters_planned": 10,
                "target_words": 30000,
            })
            assert create_resp.status_code == 200

            gen_resp = test_client.post("/api/genesis/generate", json={
                "project_id": project_id,
                "title": "",
                "genre": "",
                "premise": "",
                "target_chapters": 3,
                "target_words": 9000,
            })
            genesis_id = gen_resp.json()["data"]["id"]

            approve_resp = test_client.post("/api/genesis/approve", json={
                "project_id": project_id,
                "genesis_id": genesis_id,
                "force_apply": True,
                "confirm_quality_risk": True,
            })
            body = approve_resp.json()
            assert body["ok"] is True
            assert body["data"]["status"] == "approved"

            assert len(repo.list_world_settings(project_id)) > 0
            assert len(repo.list_characters(project_id, include_inactive=True)) > 0
            assert len(repo.list_outlines(project_id)) > 0
            assert repo.get_instruction_by_chapter(project_id, 1) is not None
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_approve_rejects_non_object_draft_without_partial_apply(self):
        """Bad generated draft_json should fail cleanly, not raise str.get or write partial context."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(db_path)
            repo = Repository(db_path)
            test_client = TestClient(create_api_app(db_path=db_path, llm_mode="stub"))
            project_id = "bad-genesis-draft"
            test_client.post("/api/onboarding/projects", json={
                "project_id": project_id,
                "name": "坏草案测试",
                "genre": "科幻",
                "description": "验证坏草案不会半应用",
                "total_chapters_planned": 10,
                "target_words": 30000,
            })
            genesis = repo.create_genesis_run(project_id, "{}", status="generated")
            repo.update_genesis_run(genesis["id"], {"draft_json": json.dumps("not a json object")})

            resp = test_client.post("/api/genesis/approve", json={
                "project_id": project_id,
                "genesis_id": genesis["id"],
            })
            body = resp.json()
            assert body["ok"] is False
            assert body["error"]["code"] == "INVALID_DRAFT"
            assert repo.get_genesis_run(genesis["id"])["status"] == "generated"
            assert repo.list_world_settings(project_id) == []
            assert repo.list_characters(project_id, include_inactive=True) == []
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_approve_rejects_incomplete_top_level_world_settings_list(self):
        """A world-only draft is not a complete project initialization and must not apply."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(db_path)
            repo = Repository(db_path)
            test_client = TestClient(create_api_app(db_path=db_path, llm_mode="stub"))
            project_id = "list-genesis-draft"
            test_client.post("/api/onboarding/projects", json={
                "project_id": project_id,
                "name": "列表草案测试",
                "genre": "都市修仙",
                "description": "验证顶层数组残缺草案不可应用",
                "total_chapters_planned": 10,
                "target_words": 30000,
            })
            genesis = repo.create_genesis_run(project_id, "{}", status="generated")
            repo.update_genesis_run(genesis["id"], {"draft_json": json.dumps([
                {"title": "修仙文明体系", "category": "力量架构", "content": "九大境界。"},
                {"title": "现代都市格局", "category": "社会结构", "content": "四大家族。"},
            ], ensure_ascii=False)})

            resp = test_client.post("/api/genesis/approve", json={
                "project_id": project_id,
                "genesis_id": genesis["id"],
            })
            body = resp.json()
            assert body["ok"] is False
            assert body["error"]["code"] == "INCOMPLETE_DRAFT"
            assert "角色" in body["error"]["message"]
            assert "章节指令" in body["error"]["message"]
            assert repo.get_genesis_run(genesis["id"])["status"] == "generated"
            assert len(repo.list_world_settings(project_id)) == 0
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

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
async def test_real_genesis_invalid_json_falls_back_to_blocked_scaffold(monkeypatch):
    """Invalid real-LLM JSON should not leave Genesis stuck in failed state."""
    from novel_factory.api.routes import genesis as genesis_routes
    from novel_factory.llm.openai_compatible import OutputValidationError

    class InvalidJsonProvider:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            raise OutputValidationError(
                "LLM 输出不是有效的 JSON 格式: Expecting value: line 1 column 1 (char 0)"
            )

    class Router:
        def for_agent(self, agent_name):
            return InvalidJsonProvider()

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    body = genesis_routes.GenesisGenerateRequest(
        title="异常修正员",
        genre="现代超自然",
        premise="修正员处理异常却发现系统并不可信",
        target_chapters=3,
        target_words=9000,
    )

    draft = await genesis_routes._generate_real_draft_with_scaffold_fallback(
        body,
        SimpleNamespace(),
    )

    assert genesis_routes._missing_required_genesis_sections(draft) == []
    assert draft["_meta"]["source"] == "scaffold_fallback"
    assert draft["_meta"]["generation_fallback"] is True
    assert draft["_meta"]["fallback_reason"] == "invalid_json"
    assert "Expecting value" in draft["_meta"]["original_error"]

    quality_report = genesis_routes.evaluate_genesis_draft(
        draft,
        title=body.title,
        genre=body.genre,
        premise=body.premise,
        target_chapters=body.target_chapters,
    )
    assert quality_report.passed is False
    assert quality_report.quality_status == "scaffold_fallback"


def test_real_genesis_api_invalid_json_returns_reviewable_scaffold(monkeypatch, tmp_path):
    """API should return a quality-blocked draft instead of a raw JSON parse failure."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db
    from novel_factory.llm.openai_compatible import OutputValidationError

    class InvalidJsonProvider:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            raise OutputValidationError(
                "LLM 输出不是有效的 JSON 格式: Expecting value: line 1 column 1 (char 0)"
            )

    class Router:
        def for_agent(self, agent_name):
            return InvalidJsonProvider()

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    db_path = str(tmp_path / "genesis-invalid-json.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="real")
    with TestClient(app) as client:
        create_resp = client.post("/api/onboarding/projects", json={
            "project_id": "invalid-json-genesis",
            "name": "异常修正员",
            "genre": "现代超自然",
            "description": "修正员处理异常却发现系统并不可信",
            "total_chapters_planned": 10,
            "target_words": 30000,
        })
        assert create_resp.status_code == 200

        resp = client.post("/api/genesis/generate", json={
            "project_id": "invalid-json-genesis",
            "title": "异常修正员",
            "genre": "现代超自然",
            "premise": "修正员处理异常却发现系统并不可信",
            "target_chapters": 3,
            "target_words": 9000,
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "generated"
    assert body["data"]["error_message"] in (None, "")
    draft = json.loads(body["data"]["draft_json"])
    assert draft["_meta"]["source"] == "scaffold_fallback"
    assert draft["_meta"]["generation_fallback"] is True
    assert body["data"]["quality_report"]["passed"] is False
    assert body["data"]["quality_report"]["quality_status"] == "scaffold_fallback"


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
async def test_real_genesis_completion_repairs_world_only_output(monkeypatch):
    """A partial real Genesis response should be completed before review."""
    from novel_factory.api.routes import genesis as genesis_routes

    class PartialThenCompletionProvider:
        def __init__(self):
            self.calls = 0

        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            self.calls += 1
            if self.calls == 1:
                return [
                    {"title": "现代都市修仙", "category": "世界观", "content": "都市暗藏修仙势力。"},
                ]
            return {
                "project_updates": {"description": "《仙帝归来》是一部都市修仙题材小说。"},
                "characters": [
                    {
                        "name": "叶无尘",
                        "role": "protagonist",
                        "description": "重生归来的仙帝。",
                        "traits": "冷静、强大",
                    }
                ],
                "factions": [
                    {
                        "name": "叶家",
                        "type": "豪门家族",
                        "description": "主角出身的都市修仙家族。",
                        "relationship_with_protagonist": "出身但存在冲突",
                    }
                ],
                "outlines": [
                    {
                        "chapters_range": "1-10",
                        "title": "归来立足",
                        "content": "主角重返都市，建立初期优势。",
                        "level": "arc",
                        "sequence": 1,
                    }
                ],
                "instructions": [
                    {
                        "chapter_number": i,
                        "objective": f"第 {i} 章推进主角归来后的局面",
                        "key_events": "建立冲突、展示能力、留下钩子",
                        "emotion_tone": "爽感",
                        "word_target": 3000,
                    }
                    for i in range(1, 4)
                ],
                "plot_holes": [
                    {
                        "code": "PH-001",
                        "type": "身世伏笔",
                        "title": "前世背叛真相",
                        "description": "主角前世陨落的幕后原因尚未揭开。",
                        "planted_chapter": 1,
                        "planned_resolve_chapter": 10,
                        "status": "planted",
                    }
                ],
            }

    provider = PartialThenCompletionProvider()

    class Router:
        def for_agent(self, agent_name):
            return provider

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    body = genesis_routes.GenesisGenerateRequest(
        title="仙帝归来",
        genre="都市修仙",
        premise="前世仙帝重生都市",
        target_chapters=3,
        target_words=9000,
    )

    first_draft = await genesis_routes._generate_real_draft(body, SimpleNamespace())
    completed = await genesis_routes._complete_real_genesis_draft(
        body, SimpleNamespace(), first_draft
    )

    assert provider.calls == 2
    assert genesis_routes._missing_required_genesis_sections(completed) == []
    assert len(completed["world_settings"]) == 1
    assert completed["characters"][0]["name"] == "叶无尘"
    assert len(completed["instructions"]) == 3


@pytest.mark.asyncio
async def test_real_genesis_completion_falls_back_to_complete_local_scaffold(monkeypatch):
    """If provider repair keeps returning empty JSON, Genesis still produces an editable complete draft."""
    from novel_factory.api.routes import genesis as genesis_routes

    class EmptyProvider:
        def __init__(self):
            self.calls = 0

        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            self.calls += 1
            return {}

    provider = EmptyProvider()

    class Router:
        def for_agent(self, agent_name):
            return provider

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    body = genesis_routes.GenesisGenerateRequest(
        title="仙帝归来",
        genre="都市修仙",
        premise="前世仙帝重生都市，重新面对家族与隐秘势力。",
        target_chapters=5,
        target_words=15000,
    )

    completed = await genesis_routes._complete_real_genesis_draft(
        body, SimpleNamespace(), {}
    )

    assert provider.calls == 2
    assert genesis_routes._missing_required_genesis_sections(completed) == []
    assert completed["project_updates"]["description"].startswith("《仙帝归来》")
    assert len(completed["world_settings"]) >= 1
    assert len(completed["characters"]) >= 3
    assert len(completed["factions"]) >= 3
    assert len(completed["outlines"]) >= 1
    assert len(completed["plot_holes"]) >= 1
    assert len(completed["instructions"]) == 5


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
