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

    def test_approve_replacement_genesis_clears_old_context_and_memory(self):
        """Approving a new genesis should replace project bible context, not merge old story worlds."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            init_db(db_path)
            repo = Repository(db_path)
            test_client = TestClient(create_api_app(db_path=db_path, llm_mode="stub"))
            project_id = "genesis-replacement-test"
            test_client.post("/api/onboarding/projects", json={
                "project_id": project_id,
                "name": "替换创世测试",
                "genre": "科幻",
                "description": "验证重新创世不会污染后续章节",
                "total_chapters_planned": 3,
                "target_words": 9000,
            })

            repo.create_world_setting(project_id, "旧世界", "旧城市", "旧内容")
            repo.create_character(project_id, "旧主角", role="protagonist", description="旧主角描述")
            repo.create_faction(project_id, "旧组织", type="官方", description="旧组织描述")
            repo.create_outline(project_id, "arc", 1, "旧大纲", "旧大纲内容", "1-3")
            repo.create_plot_hole(project_id, "OLD-001", title="旧伏笔", description="旧伏笔内容")
            repo.create_instruction(project_id, 1, "旧目标", "旧事件")
            repo.create_story_fact(project_id, "old.fact", "event", '"旧事实"', subject="旧主角", attribute="过去")
            batch = repo.create_memory_batch(project_id, chapter_number=1, summary="旧记忆")
            repo.create_memory_item(
                batch_id=batch["id"],
                project_id=project_id,
                target_table="characters",
                operation="create",
                after_json='{"name":"旧主角"}',
                confidence=0.95,
                evidence_text="旧证据",
                rationale="旧记忆",
            )
            repo.create_agent_memory(
                project_id,
                "author",
                "user_feedback",
                "old-style",
                {"note": "旧记忆"},
            )
            repo.save_chapter(project_id, 1, "旧第一章", "旧正文林深仍在调查档案馆。" * 20, 240, "published")
            repo.save_chapter_state(project_id, 1, {"新增事实": ["旧状态卡"]}, "旧状态卡")

            draft = {
                "project_updates": {"description": "新创世描述"},
                "world_settings": [{"title": "新城市", "category": "新世界", "content": "新内容"}],
                "characters": [{"name": "新主角", "role": "protagonist", "description": "新主角描述"}],
                "factions": [{"name": "新组织", "type": "民间", "description": "新组织描述"}],
                "outlines": [{"level": "arc", "sequence": 1, "title": "新大纲", "content": "新大纲内容", "chapters_range": "1-3"}],
                "plot_holes": [{"code": "NEW-001", "title": "新伏笔", "description": "新伏笔内容"}],
                "instructions": [{"chapter_number": 1, "objective": "新目标", "key_events": "新事件"}],
            }
            genesis = repo.create_genesis_run(
                project_id,
                input_json=json.dumps({
                    "title": "替换创世测试",
                    "genre": "科幻",
                    "premise": "验证重新创世不会污染后续章节",
                    "target_chapters": 3,
                }, ensure_ascii=False),
                status="generated",
            )
            repo.update_genesis_run(
                genesis["id"],
                {"draft_json": json.dumps(draft, ensure_ascii=False)},
            )

            approve_resp = test_client.post("/api/genesis/approve", json={
                "project_id": project_id,
                "genesis_id": genesis["id"],
                "force_apply": True,
                "confirm_quality_risk": True,
            })
            body = approve_resp.json()

            assert body["ok"] is True
            assert body["data"]["applied"]["context_replaced"] is True
            assert [c["name"] for c in repo.list_characters(project_id, include_inactive=True)] == ["新主角"]
            assert [w["title"] for w in repo.list_world_settings(project_id)] == ["新城市"]
            assert [o["title"] for o in repo.list_outlines(project_id)] == ["新大纲"]
            assert [p["code"] for p in repo.list_plot_holes(project_id)] == ["NEW-001"]
            assert repo.get_instruction_by_chapter(project_id, 1)["objective"] == "新目标"
            assert repo.list_story_facts(project_id) == []
            assert repo.list_memory_batches(project_id) == []
            assert repo.list_agent_memories(project_id, enabled_only=False) == []
            assert repo.get_chapter_state(project_id, 1) is None

            from novel_factory.agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt

            bundle = AgentContextBuilder(repo).build_for_author(project_id, 2, {"chapter_status": "planned"})
            prompt_context = format_context_bundle_for_prompt(bundle, "author")
            assert "旧正文林深仍在调查档案馆" not in prompt_context
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
async def test_real_genesis_invalid_json_recovers_to_usable_local_draft(monkeypatch):
    """Invalid real-LLM JSON should recover to usable data, not a blocked template."""
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
    assert draft["_meta"]["source"] == "local_recovery"
    assert draft["_meta"]["quality_status"] == "recovered_from_invalid_json"
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
    assert quality_report.passed is True
    assert quality_report.quality_status in {"pass", "warning"}
    assert not any(issue.severity == "blocker" for issue in quality_report.issues)
    objectives = [item["objective"] for item in draft["instructions"]]
    key_events = [item["key_events"] for item in draft["instructions"]]
    assert len(objectives) == len(set(objectives))
    assert len(key_events) == len(set(key_events))
    assert [item["name"] for item in draft["characters"]] == [
        "林泽",
        "许知夏",
        "魏承霜",
        "周砚白",
    ]


def test_real_genesis_api_invalid_json_returns_usable_recovery_draft(monkeypatch, tmp_path):
    """API should return reviewable concrete data instead of blocked template fallback."""
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
    assert draft["_meta"]["source"] == "local_recovery"
    assert draft["_meta"]["quality_status"] == "recovered_from_invalid_json"
    assert draft["_meta"]["generation_fallback"] is True
    assert body["data"]["quality_report"]["passed"] is True
    assert body["data"]["quality_report"]["quality_status"] in {"pass", "warning"}
    assert not any(
        issue["severity"] == "blocker"
        for issue in body["data"]["quality_report"]["issues"]
    )


def test_real_genesis_api_connection_error_reports_failure_without_template_recovery(monkeypatch, tmp_path):
    """Provider connectivity failures should not masquerade as generated Genesis."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db
    from novel_factory.llm.openai_compatible import LLMConnectionError

    class FailingProvider:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            raise LLMConnectionError("LLM 网络连接失败，请稍后重试: Connection error.")

    class Router:
        def for_agent(self, agent_name):
            return FailingProvider()

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    db_path = str(tmp_path / "genesis-connection-error.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="real")
    with TestClient(app) as client:
        create_resp = client.post("/api/onboarding/projects", json={
            "project_id": "connection-error-genesis",
            "name": "潮汐档案",
            "genre": "悬疑科幻",
            "description": "记者调查父亲旧案时发现潮汐系统隐藏着城市级实验。",
            "total_chapters_planned": 10,
            "target_words": 30000,
        })
        assert create_resp.status_code == 200

        resp = client.post("/api/genesis/generate", json={
            "project_id": "connection-error-genesis",
            "title": "潮汐档案",
            "genre": "悬疑科幻",
            "premise": "记者调查父亲旧案时发现潮汐系统隐藏着城市级实验。",
            "target_chapters": 3,
            "target_words": 9000,
        })
        latest = client.get("/api/projects/connection-error-genesis/genesis/latest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "GENESIS_FAILED"
    assert "Connection error" in body["error"]["message"]
    latest_body = latest.json()
    assert latest_body["ok"] is True
    assert latest_body["data"]["status"] == "failed"
    assert "Connection error" in latest_body["data"]["error_message"]


def test_genesis_completion_merge_deduplicates_full_draft_patch():
    """Completion patches that repeat full sections must replace/merge, not append."""
    from novel_factory.api.routes import genesis as genesis_routes

    base = {
        "project_updates": {"description": "old"},
        "world_settings": [
            {"title": "异常分类", "category": "规则", "content": "旧内容"},
        ],
        "characters": [
            {"name": "林泽", "role": "protagonist", "description": "旧描述"},
        ],
        "factions": [
            {"name": "异常处理局深城分部", "type": "官方", "description": "旧描述"},
        ],
        "outlines": [
            {"level": "arc", "sequence": 1, "chapters_range": "1-3", "title": "旧大纲", "content": "旧内容"},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "旧伏笔", "description": "旧描述"},
        ],
        "instructions": [
            {"chapter_number": 1, "objective": "旧目标", "key_events": "旧事件"},
        ],
    }
    patch = {
        "world_settings": [
            {"title": "异常分类", "category": "规则", "content": "新内容"},
            {"title": "同化机制", "category": "规则", "content": "新增内容"},
        ],
        "characters": [
            {"name": "林泽", "role": "protagonist", "description": "新描述"},
        ],
        "factions": [
            {"name": "异常处理局深城分部", "type": "官方", "description": "新描述"},
        ],
        "outlines": [
            {"level": "arc", "sequence": 1, "chapters_range": "1-3", "title": "新大纲", "content": "新内容"},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "新伏笔", "description": "新描述"},
        ],
        "instructions": [
            {"chapter_number": 1, "objective": "新目标", "key_events": "新事件"},
        ],
    }

    merged = genesis_routes._merge_genesis_drafts(base, patch)

    assert len(merged["world_settings"]) == 2
    assert merged["world_settings"][0]["content"] == "新内容"
    assert len(merged["characters"]) == 1
    assert merged["characters"][0]["description"] == "新描述"
    assert len(merged["factions"]) == 1
    assert len(merged["outlines"]) == 1
    assert merged["outlines"][0]["title"] == "新大纲"
    assert len(merged["plot_holes"]) == 1
    assert merged["plot_holes"][0]["title"] == "新伏笔"
    assert len(merged["instructions"]) == 1
    assert merged["instructions"][0]["objective"] == "新目标"


def test_genesis_world_settings_deduplicate_semantic_slots():
    """World settings should collapse near-duplicate LLM/local recovery concepts."""
    from novel_factory.api.routes import genesis as genesis_routes

    draft = {
        "world_settings": [
            {
                "title": "异常的起源与定义",
                "category": "core_concept",
                "content": "2056年3月15日，地球突然出现异常。异常分为五级。",
            },
            {
                "title": "异常的定义与分类",
                "category": "core_concept",
                "content": "异常是2056年3月15日突然出现的无法用科学解释的现象，分为五级。",
            },
            {
                "title": "修正员等级与能力",
                "category": "game_mechanic",
                "content": "修正员通过完成任务提升等级并解锁权限。",
            },
            {
                "title": "同化机制",
                "category": "mystery",
                "content": "同化程度越高能力越强，但人性流失也越严重。",
            },
        ]
    }

    deduped = genesis_routes._dedupe_genesis_draft(draft)

    assert [item["title"] for item in deduped["world_settings"]] == [
        "异常的定义与分类",
        "修正员等级与能力",
        "同化机制",
    ]


@pytest.mark.asyncio
async def test_real_genesis_generation_does_not_block_event_loop(monkeypatch):
    """Real genesis LLM calls must be offloaded so status APIs can stay responsive."""
    from novel_factory.api.routes import genesis as genesis_routes

    class BlockingProvider:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            assert max_tokens <= 4500
            time.sleep(0.2)
            prompt = messages[-1]["content"]
            if "【生成段落】foundation" in prompt:
                return {
                    "project_updates": {"description": "ok"},
                    "world_settings": [{"title": "规则", "category": "世界观", "content": "ok"}],
                }
            if "【生成段落】cast" in prompt:
                return {
                    "characters": [{"name": "林澈", "role": "protagonist", "description": "ok"}],
                    "factions": [{"name": "档案局", "type": "官方", "description": "ok"}],
                }
            if "【生成段落】plot" in prompt:
                return {
                    "outlines": [{"chapters_range": "1-1", "title": "开局", "content": "ok", "level": "arc", "sequence": 1}],
                    "plot_holes": [{"code": "PH-001", "title": "谜团", "description": "ok", "status": "planted"}],
                }
            if "【生成段落】instructions" in prompt:
                return {
                    "instructions": [{"chapter_number": 1, "objective": "ok", "key_events": "ok", "emotion_tone": "ok"}],
                }
            raise AssertionError(f"Unexpected prompt: {prompt[:120]}")

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
    draft = await task
    assert genesis_routes._missing_required_genesis_sections(draft) == []


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

    first_draft = {
        "world_settings": [
            {"title": "现代都市修仙", "category": "世界观", "content": "都市暗藏修仙势力。"},
        ],
    }
    completed = await genesis_routes._complete_real_genesis_draft(
        body, SimpleNamespace(), first_draft
    )

    assert provider.calls == 1
    assert genesis_routes._missing_required_genesis_sections(completed) == []
    assert len(completed["world_settings"]) == 1
    assert completed["characters"][0]["name"] == "叶无尘"
    assert len(completed["instructions"]) == 3


@pytest.mark.asyncio
async def test_real_genesis_completion_falls_back_to_complete_local_scaffold(monkeypatch):
    """If provider repair returns empty JSON, Genesis recovers to reviewable local data."""
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
    assert completed["_meta"]["source"] == "local_recovery"
    assert completed["_meta"]["quality_status"] == "recovered_from_incomplete_json"
    assert completed["_meta"]["fallback_reason"] == "incomplete_json"
    assert completed["project_updates"]["description"].startswith("《仙帝归来》")
    assert len(completed["world_settings"]) >= 1
    assert len(completed["characters"]) >= 3
    assert len(completed["factions"]) >= 3
    assert len(completed["outlines"]) >= 1
    assert len(completed["plot_holes"]) >= 1
    assert len(completed["instructions"]) == 5

    quality_report = genesis_routes.evaluate_genesis_draft(
        completed,
        title=body.title,
        genre=body.genre,
        premise=body.premise,
        target_chapters=body.target_chapters,
    )
    assert quality_report.passed is True
    assert quality_report.quality_status in {"pass", "warning"}
    assert not any(issue.severity == "blocker" for issue in quality_report.issues)


@pytest.mark.asyncio
async def test_real_genesis_generates_with_bounded_segmented_llm_calls(monkeypatch):
    """Genesis should avoid one oversized all-sections LLM request."""
    from novel_factory.api.routes import genesis as genesis_routes

    class SegmentedProvider:
        def __init__(self):
            self.config = SimpleNamespace(
                request_timeout_seconds=45,
                retry_attempts=1,
            )
            self.calls: list[dict[str, object]] = []

        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            user_prompt = messages[-1]["content"]
            self.calls.append({
                "prompt": user_prompt,
                "max_tokens": max_tokens,
                "max_retries": max_retries,
            })
            if "【生成段落】foundation" in user_prompt:
                return {
                    "project_updates": {"description": "潮汐系统会通过城市水位操控记忆，记者追查父亲旧案。"},
                    "world_settings": [
                        {"title": "潮汐系统", "category": "核心规则", "content": "城市水位与记忆备份系统绑定。"},
                    ],
                }
            if "【生成段落】cast" in user_prompt:
                return {
                    "characters": [
                        {"name": "林潮", "role": "protagonist", "description": "记者，目标是查清父亲旧案，秘密是自己曾被潮汐系统备份。", "traits": "敏锐"},
                        {"name": "沈澜", "role": "antagonist", "description": "系统维护者，目标是阻止真相外泄，秘密是参与过旧案。", "traits": "冷静"},
                        {"name": "许闻", "role": "supporting", "description": "档案员，帮助主角读取被删记录。", "traits": "谨慎"},
                    ],
                    "factions": [
                        {"name": "潮汐管理局", "type": "官方机构", "description": "掌握水位调度和记忆备份权限。资源/手段: 城市泵站、档案系统。当前阶段行动: 封锁旧案。", "relationship_with_protagonist": "压制调查"},
                        {"name": "旧港互助会", "type": "民间组织", "description": "保存未清洗证词。资源/手段: 目击者网络。当前阶段行动: 暗中协助。", "relationship_with_protagonist": "潜在盟友"},
                    ],
                }
            if "【生成段落】plot" in user_prompt:
                return {
                    "outlines": [
                        {"chapters_range": "1-3", "title": "旧案重启", "content": "阶段冲突: 林潮调查父亲旧案并被管理局阻止。转折: 潮位记录证明父亲死亡当天系统被人工改写。阶段结果: 林潮取得第一份证据。", "level": "arc", "sequence": 1},
                    ],
                    "plot_holes": [
                        {"code": "PH-001", "type": "主线谜团", "title": "父亲为何留下潮位表", "description": "触发场景: 林潮发现潮位表。读者表象: 普通遗物。真相方向: 潮位表是记忆备份索引。预计兑现: 第3章。", "planted_chapter": 1, "planned_resolve_chapter": 3, "status": "planted"},
                    ],
                }
            if "【生成段落】instructions" in user_prompt:
                return {
                    "instructions": [
                        {"chapter_number": 1, "objective": "林潮进入旧港泵站寻找父亲留下的潮位表。", "key_events": "林潮收到匿名潮位短信；他潜入泵站发现监控被删；沈澜派人封锁出口。", "emotion_tone": "悬疑紧张", "ending_hook": "潮位表上出现林潮自己的死亡时间。", "continuity_seed": "下一章追查死亡时间来源", "word_target": 3000},
                        {"chapter_number": 2, "objective": "林潮追查死亡时间与记忆备份系统的关系。", "key_events": "林潮找到旧港互助会；许闻解释备份索引；管理局发布通缉。", "emotion_tone": "压迫", "ending_hook": "许闻说林潮曾经来过这里。", "continuity_seed": "下一章验证林潮被备份的过去", "word_target": 3000},
                        {"chapter_number": 3, "objective": "林潮验证自己是否被潮汐系统备份。", "key_events": "林潮读取备份片段；发现父亲旧案当天自己在现场；沈澜承认系统需要活样本。", "emotion_tone": "震惊", "ending_hook": "备份片段里的父亲仍在求救。", "continuity_seed": "下一阶段进入父亲记忆备份", "word_target": 3000},
                    ],
                }
            raise AssertionError(f"Unexpected prompt: {user_prompt[:120]}")

    provider = SegmentedProvider()

    class Router:
        def for_agent(self, agent_name):
            return provider

    monkeypatch.setattr(
        "novel_factory.workflow.runner._build_llm_router",
        lambda settings, llm_mode: Router(),
    )

    body = genesis_routes.GenesisGenerateRequest(
        title="潮汐档案",
        genre="悬疑科幻",
        premise="记者调查父亲旧案时发现潮汐系统隐藏着城市级实验。",
        target_chapters=3,
        target_words=9000,
    )

    draft = await genesis_routes._generate_real_draft(body, SimpleNamespace())

    assert len(provider.calls) == 4
    assert all(call["max_tokens"] <= 4500 for call in provider.calls)
    assert all(call["max_retries"] == 2 for call in provider.calls)
    assert genesis_routes._missing_required_genesis_sections(draft) == []
    assert "local_recovery" not in json.dumps(draft, ensure_ascii=False)
    assert len(draft["instructions"]) == 3


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
            captured.setdefault("max_tokens", []).append(max_tokens)
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
    assert captured["max_tokens"] == [2400, 3000, 3200, 3900, 3900]
