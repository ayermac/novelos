"""v5.5.4 Real LLM Autonomous Planning Tests.

Tests for real-mode specific behaviors that stub mode cannot cover:
1. Real mode without API key returns LLM_CONFIG_MISSING (not silent StubLLM fallback)
2. Auto-fill only writes types that are actually missing (missing_types gate)
3. Arc-plan skips outlines with duplicate chapters_range (range-level idempotency)
4. Real LLM auto-fill success path with mock provider
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ───────────────────────────────────────────────


@pytest.fixture()
def initialized_db():
    """Create a db with a project that has approved genesis and full context."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)

    stub_app = create_api_app(db_path=db_path, llm_mode="stub")
    tc = TestClient(stub_app)

    tc.post("/api/onboarding/projects", json={
        "project_id": "v554-test",
        "name": "v5.5.4 Test",
        "genre": "奇幻",
        "description": "Test novel",
        "total_chapters_planned": 20,
        "target_words": 60000,
    })

    tc.post("/api/projects/v554-test/genesis/generate", json={
        "title": "T", "genre": "奇幻", "premise": "p",
        "target_chapters": 20, "target_words": 60000,
    })
    gid = tc.get("/api/projects/v554-test/genesis/latest").json()["data"]["id"]
    tc.post(f"/api/projects/v554-test/genesis/{gid}/approve")

    tc.post("/api/projects/v554-test/production/auto-fill", json={
        "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
    })

    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture()
def real_client_no_key(initialized_db):
    """TestClient in real mode without API key configured."""
    from novel_factory.api_app import create_api_app
    app = create_api_app(db_path=initialized_db, llm_mode="real")
    yield TestClient(app)


@pytest.fixture()
def real_client_mock(initialized_db):
    """TestClient in real mode; tests must patch get_llm_provider."""
    from novel_factory.api_app import create_api_app
    app = create_api_app(db_path=initialized_db, llm_mode="real")
    yield TestClient(app)


# ── Tests ──────────────────────────────────────────────────


class TestRealLLMConfigError:
    """Real mode without API key must surface LLM_CONFIG_MISSING."""

    def test_autofill_no_api_key(self, real_client_no_key):
        resp = real_client_no_key.post("/api/projects/v554-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "LLM_CONFIG_MISSING"

    def test_arc_plan_no_api_key(self, real_client_no_key):
        resp = real_client_no_key.post("/api/projects/v554-test/production/arc-plan", json={
            "chapter_start": 11, "chapter_end": 20, "confirm": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "LLM_CONFIG_MISSING"


class TestAutoFillMissingTypesConstraint:
    """Auto-fill must only write types that are actually missing."""

    def test_autofill_ignores_non_missing_types(self, real_client_mock, initialized_db):
        # Delete only instructions, keep world_settings/characters/outlines/plot_holes
        from novel_factory.db.repository import Repository
        repo = Repository(initialized_db)
        for inst in repo.list_instructions("v554-test"):
            repo.delete_instruction("v554-test", inst["id"])

        # Verify only instructions are missing
        assert len(repo.list_world_settings("v554-test")) > 0
        assert len(repo.list_characters("v554-test", include_inactive=True)) > 0
        assert len(repo.list_outlines("v554-test")) > 0
        assert len(repo.list_plot_holes("v554-test")) > 0
        assert len(repo.list_instructions("v554-test")) == 0

        # Mock LLM returns ALL types (including already-present ones)
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "world_settings": [{"category": "地理", "title": "新设定", "content": "新内容"}],
            "characters": [{"name": "新角色", "role": "supporting", "description": "desc", "traits": ""}],
            "outlines": [{"level": "arc", "sequence": 1, "title": "新大纲", "content": "新内容", "chapters_range": "1-3"}],
            "plot_holes": [{"code": "PH-NEW", "type": "伏笔", "title": "新伏笔", "description": "desc", "planted_chapter": 1, "planned_resolve_chapter": 5, "status": "planted"}],
            "instructions": [{"chapter_number": 1, "objective": "obj", "key_events": "ke", "plots_to_plant": [], "plots_to_resolve": [], "emotion_tone": "", "ending_hook": "", "word_target": 3000}],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/auto-fill", json={
                "scope": "missing_context", "chapter_start": 1, "chapter_end": 1, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        # Only instructions should be created
        assert data["created"]["world_settings"] == 0
        assert data["created"]["characters"] == 0
        assert data["created"]["outlines"] == 0
        assert data["created"]["plot_holes"] == 0
        assert data["created"]["instructions"] == 1

        # Warnings should note ignored types
        warnings = " ".join(data["warnings"])
        assert "已忽略" in warnings


class TestArcPlanRangeIdempotent:
    """Arc-plan must skip outlines with duplicate chapters_range."""

    def test_arc_plan_skips_duplicate_range(self, real_client_mock, initialized_db):
        mock_llm = MagicMock()

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            # First call: LLM returns a new outline for 11-20
            mock_llm.invoke_json.return_value = {
                "outlines": [{"level": "arc", "sequence": 1, "title": "第二幕", "content": "内容A", "chapters_range": "11-20"}],
                "plot_holes": [],
                "instructions": [{"chapter_number": 11, "objective": "obj", "key_events": "ke", "plots_to_plant": [], "plots_to_resolve": [], "emotion_tone": "", "ending_hook": "", "word_target": 3000}],
            }
            resp1 = real_client_mock.post("/api/projects/v554-test/production/arc-plan", json={
                "chapter_start": 11, "chapter_end": 20, "confirm": True,
            })
            assert resp1.status_code == 200
            data1 = resp1.json()["data"]
            assert data1["created"]["outlines"] == 1
            assert data1["created"]["instructions"] == 1

            # Second call: LLM returns a DIFFERENT title but SAME chapters_range
            mock_llm.invoke_json.return_value = {
                "outlines": [{"level": "arc", "sequence": 1, "title": "第二幕-新", "content": "内容B", "chapters_range": "11-20"}],
                "plot_holes": [],
                "instructions": [{"chapter_number": 11, "objective": "obj2", "key_events": "ke2", "plots_to_plant": [], "plots_to_resolve": [], "emotion_tone": "", "ending_hook": "", "word_target": 3000}],
            }
            resp2 = real_client_mock.post("/api/projects/v554-test/production/arc-plan", json={
                "chapter_start": 11, "chapter_end": 20, "confirm": True,
            })
            assert resp2.status_code == 200
            data2 = resp2.json()["data"]
            # Outline skipped because chapters_range "11-20" already exists
            assert data2["created"]["outlines"] == 0
            # Instruction skipped because chapter 11 already has one
            assert data2["created"]["instructions"] == 0

            # Warnings should mention range duplicate
            warnings2 = " ".join(data2["warnings"])
            assert "章节范围" in warnings2 or "11-20" in warnings2


class TestAutoFillEmptyOutput:
    """Auto-fill with empty or non-object LLM output must return clear errors."""

    def test_autofill_empty_output_returns_no_content_created(self, real_client_mock, initialized_db):
        # Delete instructions so they are missing
        from novel_factory.db.repository import Repository
        repo = Repository(initialized_db)
        for inst in repo.list_instructions("v554-test"):
            repo.delete_instruction("v554-test", inst["id"])

        # Mock LLM returns valid but completely empty output
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "world_settings": [],
            "characters": [],
            "outlines": [],
            "plot_holes": [],
            "instructions": [],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/auto-fill", json={
                "scope": "missing_context", "chapter_start": 1, "chapter_end": 1, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "NO_CONTENT_CREATED"

    def test_autofill_non_object_returns_llm_output_invalid(self, real_client_mock, initialized_db):
        # Delete instructions so they are missing
        from novel_factory.db.repository import Repository
        repo = Repository(initialized_db)
        for inst in repo.list_instructions("v554-test"):
            repo.delete_instruction("v554-test", inst["id"])

        # Mock LLM returns a non-dict (list), triggering LLMOutputInvalid
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = []

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/auto-fill", json={
                "scope": "missing_context", "chapter_start": 1, "chapter_end": 1, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "LLM_OUTPUT_INVALID"

    def test_autofill_only_non_missing_output_returns_no_content_created(self, real_client_mock, initialized_db):
        # Delete only instructions, keep world_settings/characters/outlines/plot_holes
        from novel_factory.db.repository import Repository
        repo = Repository(initialized_db)
        for inst in repo.list_instructions("v554-test"):
            repo.delete_instruction("v554-test", inst["id"])

        # Verify world_settings already exist
        assert len(repo.list_world_settings("v554-test")) > 0

        # Mock LLM returns ONLY non-missing type (world_settings), not the missing instructions
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "world_settings": [{"category": "地理", "title": "多余设定", "content": "不会写入"}],
            "characters": [],
            "outlines": [],
            "plot_holes": [],
            "instructions": [],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/auto-fill", json={
                "scope": "missing_context", "chapter_start": 1, "chapter_end": 1, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "NO_CONTENT_CREATED"
        # Verify no new world_settings were created (fixture creates 2 initially)
        assert len(repo.list_world_settings("v554-test")) == 2

    def test_autofill_coerces_list_fields_from_real_llm(self, real_client_mock, initialized_db):
        """Real providers often return list traits/key_events; auto-fill should salvage them."""
        from novel_factory.db.repository import Repository
        repo = Repository(initialized_db)
        for inst in repo.list_instructions("v554-test"):
            repo.delete_instruction("v554-test", inst["id"])
        for ch in repo.list_characters("v554-test", include_inactive=True):
            repo.delete_character("v554-test", ch["id"])

        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "world_settings": [],
            "characters": [
                {
                    "name": "叶辰",
                    "role": "protagonist",
                    "description": "仙帝重生到都市的主角。",
                    "traits": ["冷静果决", "仙帝记忆"],
                }
            ],
            "outlines": [],
            "plot_holes": [],
            "instructions": [
                {
                    "chapter_number": 1,
                    "objective": "叶辰回归都市，建立重生处境。",
                    "key_events": ["醒来", "发现灵气稀薄"],
                    "plots_to_plant": "仙帝陨落真相",
                    "plots_to_resolve": [],
                    "emotion_tone": "压抑后反击",
                    "ending_hook": "叶家来人逼迫。",
                    "word_target": 3000,
                }
            ],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/auto-fill", json={
                "scope": "missing_context", "chapter_start": 1, "chapter_end": 1, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["created"]["characters"] == 1
        assert body["data"]["created"]["instructions"] == 1
        character = repo.list_characters("v554-test", include_inactive=True)[0]
        assert "冷静果决" in character["traits"]
        instruction = repo.get_instruction_by_chapter("v554-test", 1)
        assert "醒来" in instruction["key_events"]


class TestArcPlanEmptyOutput:
    """Arc-plan with empty LLM output must return NO_CONTENT_CREATED."""

    def test_arc_plan_empty_output_returns_no_content_created(self, real_client_mock, initialized_db):
        # Mock LLM returns valid but completely empty output
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "outlines": [],
            "plot_holes": [],
            "instructions": [],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/arc-plan", json={
                "chapter_start": 11, "chapter_end": 20, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "NO_CONTENT_CREATED"


class TestRealLLMAutoFillSuccess:
    """Real LLM auto-fill success path with mock provider."""

    def test_autofill_real_llm_success(self, real_client_mock, initialized_db):
        # Delete instructions so they are missing
        from novel_factory.db.repository import Repository
        repo = Repository(initialized_db)
        for inst in repo.list_instructions("v554-test"):
            repo.delete_instruction("v554-test", inst["id"])

        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "world_settings": [],
            "characters": [],
            "outlines": [],
            "plot_holes": [],
            "instructions": [
                {"chapter_number": 1, "objective": "开篇", "key_events": "出场", "plots_to_plant": [], "plots_to_resolve": [], "emotion_tone": "神秘", "ending_hook": "悬念", "word_target": 3000},
                {"chapter_number": 2, "objective": "发展", "key_events": "冲突", "plots_to_plant": [], "plots_to_resolve": [], "emotion_tone": "紧张", "ending_hook": "转折", "word_target": 3000},
            ],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/auto-fill", json={
                "scope": "missing_context", "chapter_start": 1, "chapter_end": 2, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["created"]["instructions"] == 2
        assert data["created"]["world_settings"] == 0
        assert len(data["warnings"]) == 0

    def test_arc_plan_real_llm_success(self, real_client_mock, initialized_db):
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "outlines": [{"level": "arc", "sequence": 1, "title": "新篇", "content": "内容", "chapters_range": "11-20"}],
            "plot_holes": [{"code": "PH-011", "type": "伏笔", "title": "新伏笔", "description": "desc", "planted_chapter": 11, "planned_resolve_chapter": 15, "status": "planted"}],
            "instructions": [
                {"chapter_number": 11, "objective": "obj", "key_events": "ke", "plots_to_plant": [], "plots_to_resolve": [], "emotion_tone": "", "ending_hook": "", "word_target": 3000},
            ],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client_mock.post("/api/projects/v554-test/production/arc-plan", json={
                "chapter_start": 11, "chapter_end": 20, "confirm": True,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["planned"] is True
        assert data["created"]["outlines"] == 1
        assert data["created"]["instructions"] == 1
        assert data["created"]["plot_holes"] == 1
