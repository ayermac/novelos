"""Title contract tests for keeping generated content aligned with the book name."""

from __future__ import annotations

import os
import json
import tempfile
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_db():
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    return db_path


def test_title_contract_detects_mismatched_xian_di_context():
    from novel_factory.agents.title_contract import evaluate_title_alignment

    project = {"name": "绝世仙帝在都市", "genre": "urban"}
    alignment = evaluate_title_alignment(project, [
        "故事发生在一个封闭的沿海小镇，常年被浓雾笼罩。",
        "艾伦是一名年轻机械师，负责维护废弃灯塔下的发电机。",
    ])

    assert alignment["aligned"] is False
    assert "immortal_emperor" in alignment["missing"]
    assert "urban_stage" in alignment["missing"]
    assert "浓雾" in alignment["mismatch_signals"]


def test_real_autofill_prompt_includes_title_contract():
    from novel_factory.api_app import create_api_app
    from novel_factory.db.repository import Repository

    db_path = _make_db()
    try:
        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)
        client.post("/api/onboarding/projects", json={
            "project_id": "title-contract-test",
            "name": "绝世仙帝在都市",
            "genre": "urban",
            "description": "仙帝归来，在现代都市重建巅峰。",
            "total_chapters_planned": 20,
            "target_words": 60000,
        })
        repo = Repository(db_path)
        repo.create_genesis_run("title-contract-test", json.dumps({"title": "绝世仙帝在都市"}), status="approved")
        repo.delete_instructions_by_project("title-contract-test")

        real_app = create_api_app(db_path=db_path, llm_mode="real")
        real_client = TestClient(real_app)
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "world_settings": [],
            "characters": [],
            "outlines": [],
            "plot_holes": [],
            "instructions": [{
                "chapter_number": 1,
                "objective": "仙帝归来，踏入现代都市。",
                "key_events": "主角在城市中展露仙帝底蕴。",
                "plots_to_plant": [],
                "plots_to_resolve": [],
                "emotion_tone": "强势",
                "ending_hook": "昔日仇敌现身都市。",
                "word_target": 3000,
            }],
        }

        from novel_factory.api import deps
        with patch.object(deps, "get_llm_provider", return_value=mock_llm):
            resp = real_client.post("/api/projects/title-contract-test/production/auto-fill", json={
                "scope": "missing_context",
                "chapter_start": 1,
                "chapter_end": 1,
                "confirm": True,
            })

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        messages = mock_llm.invoke_json.call_args.args[0]
        prompt = messages[1]["content"]
        assert "【书名契约】" in prompt
        assert "绝世仙帝在都市" in prompt
        assert "仙帝身份/修仙力量" in prompt
        assert "现代都市舞台" in prompt
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_production_next_blocks_mismatched_title_contract_after_genesis():
    from novel_factory.api_app import create_api_app
    from novel_factory.db.repository import Repository

    db_path = _make_db()
    try:
        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)
        client.post("/api/onboarding/projects", json={
            "project_id": "mismatch-test",
            "name": "绝世仙帝在都市",
            "genre": "urban",
            "description": "仙帝归来，在现代都市横扫强敌。",
            "total_chapters_planned": 20,
            "target_words": 60000,
        })
        repo = Repository(db_path)
        repo.create_genesis_run("mismatch-test", json.dumps({"title": "绝世仙帝在都市"}), status="approved")
        repo.delete_world_settings_by_project("mismatch-test")
        repo.delete_characters_by_project("mismatch-test")
        repo.delete_outlines_by_project("mismatch-test")
        repo.create_world_setting(
            "mismatch-test",
            "地理",
            "地理环境",
            "故事发生在一个封闭的沿海小镇，常年被浓雾笼罩，有一座废弃灯塔。",
        )
        repo.create_character(
            "mismatch-test",
            "艾伦",
            "protagonist",
            description="年轻机械师，负责维护小镇发电机。",
            traits="内向、坚韧",
        )
        repo.create_outline(
            "mismatch-test",
            "arc",
            1,
            "迷雾中的微光",
            "艾伦发现灯塔信号，试图打破小镇封锁。",
            "1-3",
        )

        resp = client.get("/api/projects/mismatch-test/production-next")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["health"]["title_contract_aligned"] is False
        assert data["next_action"]["key"] == "repair_title_contract"
        assert any(item["key"] == "title_contract" for item in data["missing"])
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
