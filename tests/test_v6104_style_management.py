"""v6.10.4 Style Management Hardening tests.

Covers:
- Canonical StyleBible initialization via POST /style/init
- Old-format normalization
- GET /style/bible/{project_id} returns full structure
- PUT /style/bible/{project_id} structured update
- Author plain-text context includes Style Bible
- Style Gate default non-blocking strategy
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import StyleBible, ForbiddenExpression, PreferredExpression
from novel_factory.models.style_gate import StyleGateConfig


# ── Helpers ────────────────────────────────────────────────────


def _ensure_project(db_path: str, project_id: str, name: str = "Test Project", genre: str = "") -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name, genre) VALUES (?, ?, ?)",
            (project_id, name, genre),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path):
    db = str(tmp_path / "test_v6104.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


@pytest.fixture
def client(db_path):
    from novel_factory.api_app import create_api_app

    app = create_api_app(db_path=db_path, config_path=None, llm_mode="stub")
    return TestClient(app)


# ── 1. Canonical initialization ────────────────────────────────


class TestStyleInitCanonical:
    """POST /style/init creates canonical StyleBible."""

    def test_init_creates_canonical_fields(self, client, db_path, repo):
        _ensure_project(db_path, "proj_canon", name="Canon Test", genre="都市异能")
        res = client.post("/api/style/init", json={"project_id": "proj_canon"})
        assert res.status_code == 200
        payload = res.json()
        assert payload["ok"] is True
        assert payload["data"]["created"] is True
        assert payload["data"]["template_used"] == "urban_fantasy_fast"

        record = repo.get_style_bible("proj_canon")
        assert record is not None
        bible = record["bible"]
        # Canonical fields must exist
        assert "tone_keywords" in bible
        assert "pacing" in bible
        assert "pov" in bible
        assert "dialogue_style" in bible
        assert "prose_style" in bible
        assert "forbidden_expressions" in bible
        assert "ai_trace_avoidance" in bible
        # project_id must be in bible JSON
        assert bible.get("project_id") == "proj_canon"

    def test_init_uses_default_template_when_genre_unknown(self, client, db_path, repo):
        _ensure_project(db_path, "proj_default", name="Default Test", genre="未知类型")
        res = client.post("/api/style/init", json={"project_id": "proj_default"})
        assert res.status_code == 200
        assert res.json()["data"]["template_used"] == "default_web_serial"

    def test_init_with_reference_text_sets_needs_review(self, client, db_path, repo):
        _ensure_project(db_path, "proj_ref", name="Ref Test")
        res = client.post("/api/style/init", json={
            "project_id": "proj_ref",
            "reference_text": "这是一段参考文本。",
        })
        assert res.status_code == 200
        record = repo.get_style_bible("proj_ref")
        assert record["bible"].get("status") == "needs_review"
        assert record["bible"].get("generated_from_reference") is True

    def test_init_attaches_default_gate_config(self, client, db_path, repo):
        _ensure_project(db_path, "proj_gate", name="Gate Test")
        res = client.post("/api/style/init", json={"project_id": "proj_gate"})
        assert res.status_code == 200
        record = repo.get_style_bible("proj_gate")
        gate = record["bible"].get("gate_config")
        assert gate is not None
        assert gate["enabled"] is False
        assert gate["mode"] == "warn"

    def test_init_already_exists_returns_error(self, client, db_path, repo):
        _ensure_project(db_path, "proj_dup", name="Dup Test")
        r1 = client.post("/api/style/init", json={"project_id": "proj_dup"})
        assert r1.status_code == 200
        r2 = client.post("/api/style/init", json={"project_id": "proj_dup"})
        assert r2.status_code == 200
        assert r2.json()["ok"] is False
        assert "ALREADY_EXISTS" in r2.json()["error"]["code"]


# ── 2. Old format normalization ────────────────────────────────


class TestStyleBibleNormalization:
    """Legacy voice/narrative/prose formats normalize to canonical."""

    def test_normalize_legacy_voice_narrative_prose(self, db_path, repo):
        _ensure_project(db_path, "proj_legacy", name="Legacy Test")
        old_format = {
            "project_name": "Legacy Test",
            "voice": {"tone": "轻松,幽默", "formality": "适中"},
            "narrative": {"pov": "第三人称", "tense": "过去时"},
            "prose": {"sentence_length": "中短句", "dialogue_style": "口语化"},
        }
        repo.save_style_bible("proj_legacy", old_format)

        from novel_factory.style_bible.normalizer import ensure_canonical_style_bible
        record = repo.get_style_bible("proj_legacy")
        bible = ensure_canonical_style_bible(record["bible"])

        assert isinstance(bible, StyleBible)
        assert bible.tone_keywords == ["轻松", "幽默"]
        assert bible.pov.value == "third_person_limited"
        assert bible.dialogue_style == "口语化"
        assert any("中短句" in r.description for r in bible.sentence_rules)

    def test_normalize_unknown_status_to_draft(self, db_path, repo):
        from novel_factory.style_bible.normalizer import normalize_style_bible_status
        assert normalize_style_bible_status({"status": "unknown"}) == "draft"
        assert normalize_style_bible_status({"status": ""}) == "draft"
        assert normalize_style_bible_status(None) == "draft"
        assert normalize_style_bible_status({"status": "active"}) == "active"
        assert normalize_style_bible_status({"status": "needs_review"}) == "needs_review"

    def test_status_is_read_from_bible_json(self, db_path, repo):
        from novel_factory.style_bible.normalizer import normalize_style_bible_status

        _ensure_project(db_path, "proj_status_bible", name="Status Bible")
        repo.save_style_bible("proj_status_bible", {
            "name": "Status Bible",
            "tone_keywords": ["热血"],
            "status": "active",
        })

        record = repo.get_style_bible("proj_status_bible")
        assert normalize_style_bible_status(record) == "active"


# ── 3. rules_for_agent non-empty after init ────────────────────


class TestRulesForAgentAfterInit:
    """Initialization result yields non-empty rules for author."""

    def test_rules_for_author_not_empty_after_init(self, client, db_path, repo):
        _ensure_project(db_path, "proj_rules", name="Rules Test", genre="玄幻")
        res = client.post("/api/style/init", json={"project_id": "proj_rules"})
        assert res.status_code == 200

        record = repo.get_style_bible("proj_rules")
        from novel_factory.style_bible.normalizer import ensure_canonical_style_bible
        bible = ensure_canonical_style_bible(record["bible"])
        rules = bible.rules_for_agent("author")
        assert rules != ""
        assert "写作指引" in rules


# ── 4. GET /style/bible/{project_id} ───────────────────────────


class TestGetStyleBibleDetail:
    """GET /api/style/bible/{project_id} returns full structure."""

    def test_get_detail_returns_full_structure(self, client, db_path, repo):
        _ensure_project(db_path, "proj_get", name="Get Test")
        client.post("/api/style/init", json={"project_id": "proj_get"})

        res = client.get("/api/style/bible/proj_get")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["project_id"] == "proj_get"
        assert data["project_name"] == "Get Test"
        assert data["status"] in ("draft", "active", "needs_review")
        assert "version" in data
        assert "bible" in data
        assert "gate_config" in data
        assert data["bible"].get("project_id") == "proj_get"

    def test_get_detail_not_found(self, client, db_path):
        _ensure_project(db_path, "proj_no_bible", name="No Bible")
        res = client.get("/api/style/bible/proj_no_bible")
        assert res.status_code == 200
        assert res.json()["ok"] is False
        assert "NOT_FOUND" in res.json()["error"]["code"]

    def test_get_detail_project_not_found(self, client):
        res = client.get("/api/style/bible/nonexistent_project")
        assert res.status_code == 200
        assert res.json()["ok"] is False
        assert "PROJECT_NOT_FOUND" in res.json()["error"]["code"]


# ── 5. PUT /style/bible/{project_id} ───────────────────────────


class TestPutStyleBibleStructured:
    """PUT /api/style/bible/{project_id} accepts structured JSON."""

    def test_structured_update_modifies_bible(self, client, db_path, repo):
        _ensure_project(db_path, "proj_put", name="Put Test")
        client.post("/api/style/init", json={"project_id": "proj_put"})

        update = {
            "bible": {
                "name": "Updated Bible",
                "tone_keywords": ["热血", "爽感", "逆袭"],
                "pacing": "fast",
                "pov": "first_person",
                "dialogue_style": "犀利",
                "prose_style": "极简",
                "tension_style": "constant",
                "humor_style": "dry",
                "emotional_intensity": "high",
                "forbidden_expressions": [],
                "preferred_expressions": [],
                "sentence_rules": [],
                "paragraph_rules": [],
                "chapter_opening_rules": [],
                "chapter_ending_rules": [],
                "ai_trace_avoidance": {"avoid_patterns": [], "prefer_patterns": [], "notes": ""},
            }
        }
        res = client.put("/api/style/bible/proj_put", json=update)
        assert res.status_code == 200
        assert res.json()["data"]["updated"] is True

        record = repo.get_style_bible("proj_put")
        bible = record["bible"]
        assert bible["name"] == "Updated Bible"
        assert bible["tone_keywords"] == ["热血", "爽感", "逆袭"]
        assert bible["pov"] == "first_person"

    def test_structured_update_with_gate_config(self, client, db_path, repo):
        _ensure_project(db_path, "proj_gate_put", name="Gate Put Test")
        client.post("/api/style/init", json={"project_id": "proj_gate_put"})

        update = {
            "bible": {"name": "Gate Test Bible"},
            "gate_config": {
                "enabled": True,
                "mode": "warn",
                "blocking_threshold": 60,
                "revision_target": "author",
                "apply_stages": ["draft", "polished"],
            }
        }
        res = client.put("/api/style/bible/proj_gate_put", json=update)
        assert res.status_code == 200
        record = repo.get_style_bible("proj_gate_put")
        gate = record["bible"]["gate_config"]
        assert gate["enabled"] is True
        assert gate["mode"] == "warn"
        assert gate["blocking_threshold"] == 60

    def test_gate_only_update_preserves_existing_bible(self, client, db_path, repo):
        _ensure_project(db_path, "proj_gate_only", name="Gate Only Test")
        client.post("/api/style/init", json={"project_id": "proj_gate_only"})
        before = repo.get_style_bible("proj_gate_only")["bible"]

        res = client.put("/api/style/bible/proj_gate_only", json={
            "gate_config": {
                "enabled": True,
                "mode": "warn",
                "blocking_threshold": 65,
                "revision_target": "polisher",
                "apply_stages": ["polished", "final_gate"],
            }
        })
        assert res.status_code == 200

        after = repo.get_style_bible("proj_gate_only")["bible"]
        assert after["name"] == before["name"]
        assert after["tone_keywords"] == before["tone_keywords"]
        assert after["prose_style"] == before["prose_style"]
        assert after["gate_config"]["enabled"] is True
        assert after["gate_config"]["blocking_threshold"] == 65

    def test_structured_update_creates_if_missing(self, client, db_path, repo):
        _ensure_project(db_path, "proj_put_create", name="Put Create Test")
        update = {
            "bible": {
                "name": "Created Bible",
                "tone_keywords": ["悬疑"],
                "pacing": "balanced",
                "pov": "third_person_limited",
            }
        }
        res = client.put("/api/style/bible/proj_put_create", json=update)
        assert res.status_code == 200
        assert res.json()["data"]["created"] is True
        record = repo.get_style_bible("proj_put_create")
        assert record["bible"]["name"] == "Created Bible"

    def test_legacy_put_still_works(self, client, db_path, repo):
        _ensure_project(db_path, "proj_legacy_put", name="Legacy Put Test")
        client.post("/api/style/init", json={"project_id": "proj_legacy_put"})

        legacy_bible = {
            "name": "Legacy Updated",
            "tone_keywords": ["古风"],
            "pacing": "slow",
            "pov": "omniscient",
        }
        res = client.put("/api/style/bible", json={
            "project_id": "proj_legacy_put",
            "content": json.dumps(legacy_bible),
        })
        assert res.status_code == 200
        assert res.json()["data"]["updated"] is True
        record = repo.get_style_bible("proj_legacy_put")
        assert record["bible"]["name"] == "Legacy Updated"


# ── 6. Author plain-text context includes Style Bible ──────────


class TestAuthorPlainTextContext:
    """Author _build_plain_text_context includes Style Bible via AgentContextBuilder."""

    def test_plain_text_context_contains_style_bible(self, db_path, repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt

        _ensure_project(db_path, "proj_author_ctx", name="Author Ctx Test")
        bible = StyleBible(
            project_id="proj_author_ctx",
            name="Author Test Bible",
            prose_style="紧凑",
            dialogue_style="犀利",
            tone_keywords=["热血"],
            pacing="fast",
            pov="third_person_limited",
        )
        repo.save_style_bible("proj_author_ctx", bible.to_storage_dict())

        agent = AuthorAgent(repo, MagicMock())
        state = {
            "project_id": "proj_author_ctx",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }
        ctx = agent.build_context(state)
        assert "风格规范" in ctx
        assert "写作指引" in ctx
        assert "紧凑" in ctx

    def test_agent_context_builder_includes_style(self, db_path, repo):
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt

        _ensure_project(db_path, "proj_builder", name="Builder Test")
        bible = StyleBible(
            project_id="proj_builder",
            name="Builder Bible",
            prose_style="干练",
            dialogue_style="简洁",
            tone_keywords=["爽快"],
            pacing="fast",
            pov="third_person_limited",
        )
        repo.save_style_bible("proj_builder", bible.to_storage_dict())

        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_author("proj_builder", 1)
        assert len(bundle.style_context) > 0
        prompt = format_context_bundle_for_prompt(bundle, agent_name="author")
        assert "【风格规范 / Style Bible】" in prompt
        assert "干练" in prompt

    def test_planner_context_builder_includes_style(self, db_path, repo):
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt

        _ensure_project(db_path, "proj_planner", name="Planner Test")
        bible = StyleBible(
            project_id="proj_planner",
            name="Planner Bible",
            tone_keywords=["悬疑"],
            pacing="balanced",
            pov="third_person_limited",
            chapter_opening_rules=[{"description": "开篇必须有动作", "severity": "warning"}],
        )
        repo.save_style_bible("proj_planner", bible.to_storage_dict())

        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_planner("proj_planner", 1)
        assert len(bundle.style_context) > 0
        prompt = format_context_bundle_for_prompt(bundle, agent_name="planner")
        assert "【风格规范 / Style Bible】" in prompt
        assert "策划摘要" in prompt

    def test_editor_context_builder_includes_style(self, db_path, repo):
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt

        _ensure_project(db_path, "proj_editor", name="Editor Test")
        bible = StyleBible(
            project_id="proj_editor",
            name="Editor Bible",
            forbidden_expressions=[ForbiddenExpression(pattern="冷笑", reason="AI味", severity="blocking")],
        )
        repo.save_style_bible("proj_editor", bible.to_storage_dict())

        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_editor("proj_editor", 1)
        assert len(bundle.style_context) > 0
        prompt = format_context_bundle_for_prompt(bundle, agent_name="editor")
        assert "【风格规范 / Style Bible】" in prompt
        assert "审校规则" in prompt


# ── 7. Style Gate default strategy ─────────────────────────────


class TestStyleGateDefaultStrategy:
    """Style Gate defaults to non-blocking."""

    def test_default_gate_enabled_false(self, client, db_path, repo):
        _ensure_project(db_path, "proj_gate_default", name="Gate Default Test")
        client.post("/api/style/init", json={"project_id": "proj_gate_default"})
        record = repo.get_style_bible("proj_gate_default")
        gate = record["bible"].get("gate_config", {})
        assert gate.get("enabled") is False

    def test_gate_config_model_defaults(self):
        gate = StyleGateConfig()
        assert gate.enabled is False
        assert gate.mode.value == "warn"
        assert gate.blocking_threshold == 70
        assert gate.revision_target == "polisher"

    def test_console_status_semantics(self, client, db_path, repo):
        _ensure_project(db_path, "proj_console", name="Console Test")
        # Save an old-format bible with status='unknown'
        repo.save_style_bible("proj_console", {
            "project_name": "Console Test",
            "voice": {"tone": "轻松"},
            "status": "unknown",
        })
        res = client.get("/api/style/console")
        assert res.status_code == 200
        bibles = res.json()["data"]["style_bibles"]
        found = next((b for b in bibles if b["project_id"] == "proj_console"), None)
        assert found is not None
        assert found["status"] == "draft"
