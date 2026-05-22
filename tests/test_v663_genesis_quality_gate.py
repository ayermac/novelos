"""Tests for v6.6.3 Genesis Initialization Quality Gate."""

import json
import pytest
from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.quality.genesis_quality_gate import (
    evaluate_genesis_draft,
    GenesisQualityIssue,
    GenesisQualityReport,
)


@pytest.fixture()
def genesis_api(tmp_path):
    """Create a Genesis API client and repository backed by a temporary DB."""
    db_path = str(tmp_path / "genesis_quality.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def _low_quality_complete_draft() -> dict:
    """A complete but intentionally generic draft that should be quality-blocked."""
    return {
        "project_updates": {"description": "一个主角获得机会并面对敌人的故事。"},
        "world_settings": [
            {"title": "基础世界观", "category": "设定", "content": "现代都市背景，主角逐步成长。"},
        ],
        "characters": [
            {"name": "主角", "role": "protagonist", "description": "主角", "traits": "成长"},
            {"name": "核心盟友", "role": "supporting", "description": "盟友", "traits": "可靠"},
            {"name": "反派首领", "role": "antagonist", "description": "反派", "traits": "强大"},
        ],
        "factions": [
            {"name": "主角阵营", "type": "阵营", "description": "主角所属"},
            {"name": "敌对势力", "type": "势力", "description": "敌对"},
        ],
        "outlines": [
            {"chapters_range": "1-3", "title": "开篇", "content": "开局", "level": "arc", "sequence": 1},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "主角关键能力来源", "description": "主角能力来源", "status": "planted"},
            {"code": "PH-002", "title": "隐秘组织为何关注主角", "description": "组织关注主角", "status": "planted"},
        ],
        "instructions": [
            {"chapter_number": 1, "objective": "建立主角处境", "key_events": "主角登场", "emotion_tone": "紧张"},
            {"chapter_number": 2, "objective": "建立主角处境", "key_events": "主角登场", "emotion_tone": "紧张"},
            {"chapter_number": 3, "objective": "建立主角处境", "key_events": "主角登场", "emotion_tone": "紧张"},
        ],
    }


def _create_generated_genesis(repo: Repository, project_id: str, draft: dict) -> dict:
    repo.create_project(project_id=project_id, name="质量门测试", genre="都市", description="测试")
    run = repo.create_genesis_run(
        project_id,
        json.dumps(
            {
                "title": "质量门测试",
                "genre": "都市",
                "premise": "测试",
                "target_chapters": 3,
            },
            ensure_ascii=False,
        ),
        status="generated",
    )
    repo.update_genesis_run(run["id"], {"draft_json": json.dumps(draft, ensure_ascii=False)})
    return repo.get_genesis_run(run["id"])


def test_repetitive_objective_detected():
    """Test that repeated objectives across chapters are detected."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "建立主角处境和核心冲突", "key_events": "主角登场"},
            {"chapter_number": 2, "objective": "建立主角处境和核心冲突", "key_events": "盟友登场"},
            {"chapter_number": 3, "objective": "建立主角处境和核心冲突", "key_events": "反派登场"},
            {"chapter_number": 4, "objective": "建立主角处境和核心冲突", "key_events": "冲突升级"},
        ],
        "outlines": [{"chapters_range": "1-4", "title": "开篇", "content": "故事开始"}],
        "characters": [{"name": "林默", "role": "protagonist", "description": "主角"}],
        "factions": [{"name": "星海学院", "type": "学院", "description": "主角所在学院"}],
        "plot_holes": [{"code": "PH-001", "title": "身世之谜", "description": "主角身世"}],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试小说",
        genre="都市",
        premise="主角觉醒超能力",
        target_chapters=4,
    )

    assert not report.passed
    assert report.quality_status == "blocked"
    assert any(i.code == "REPETITIVE_OBJECTIVE" for i in report.issues)


def test_repetitive_key_events_detected():
    """Test that repeated key_events across chapters are detected."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章目标", "key_events": "主角主动出击，对手设局"},
            {"chapter_number": 2, "objective": "第二章目标", "key_events": "主角主动出击，对手设局"},
            {"chapter_number": 3, "objective": "第三章目标", "key_events": "主角主动出击，对手设局"},
        ],
        "outlines": [{"chapters_range": "1-3", "title": "开篇", "content": "故事开始"}],
        "characters": [{"name": "林默", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=3,
    )

    assert any(i.code == "REPETITIVE_KEY_EVENTS" for i in report.issues)


def test_scaffold_fallback_detected():
    """Test that scaffold fallback drafts are properly marked."""
    draft = {
        "_meta": {
            "source": "scaffold_fallback",
            "quality_status": "scaffold_fallback",
        },
        "instructions": [
            {"chapter_number": 1, "objective": "建立主角处境", "key_events": "主角登场"},
        ],
        "outlines": [],
        "characters": [{"name": "主角", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=1,
    )

    assert report.quality_status == "scaffold_fallback"
    assert not report.passed
    assert report.score == 0.0
    assert any(i.code == "SCAFFOLD_FALLBACK" for i in report.issues)


def test_generic_character_names_detected():
    """Test that generic character names are detected."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件1"},
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始"}],
        "characters": [
            {"name": "主角", "role": "protagonist", "description": "主角"},
            {"name": "核心盟友", "role": "supporting", "description": "盟友"},
            {"name": "反派首领", "role": "antagonist", "description": "反派"},
        ],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=1,
    )

    assert any(i.code == "MOST_GENERIC_CHARACTERS" for i in report.issues)


def test_generic_plot_holes_detected():
    """Test that generic plot holes are detected."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件1"},
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始"}],
        "characters": [{"name": "林默", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [
            {"code": "PH-001", "title": "主角关键能力来源", "description": "主角能力来源"},
            {"code": "PH-002", "title": "隐秘组织为何关注主角", "description": "组织关注主角"},
        ],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=1,
    )

    assert any(i.code == "ALL_GENERIC_PLOT_HOLES" for i in report.issues)


def test_stage_label_only_outlines_detected():
    """Test that stage-label-only outlines are detected."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件1"},
        ],
        "outlines": [
            {"chapters_range": "1-3", "title": "开篇", "content": "开局"},
            {"chapters_range": "4-6", "title": "高潮", "content": "高潮"},
        ],
        "characters": [{"name": "林默", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=6,
    )

    assert any(i.code == "STAGE_LABEL_ONLY_OUTLINES" for i in report.issues)


def test_high_quality_fantasy_draft_passes():
    """Test that a high-quality fantasy draft passes or gets only warnings."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林默在星海学院实验室觉醒异能，因此发现自己与父亲失踪案存在直接关联",
                "key_events": "林默在实验室意外触发异能，导致设备爆炸；神秘黑影出现并留下警告；父亲遗留的芯片被激活并显示加密坐标",
                "ending_hook": "黑影提到「组织」正在寻找林默",
                "continuity_seed": "林默必须在下一章决定是隐藏异能还是向学院坦白",
            },
            {
                "chapter_number": 2,
                "objective": "林默在实战课被迫展示异能，从而引发学院高层注意并遭到秘密监视",
                "key_events": "林默在实战课失控击碎训练场；学院高层召开紧急会议决定试探林默；陈雨晴出手相助并暗示她知道内幕",
                "ending_hook": "学院决定秘密观察林默",
                "continuity_seed": "陈雨晴将在下一章向林默透露她掌握的关于「组织」的线索",
            },
        ],
        "outlines": [
            {
                "chapters_range": "1-2",
                "title": "觉醒与冲突",
                "content": "林默觉醒异能，发现父亲失踪与「组织」有关，学院内部势力开始博弈。阶段冲突：林默的异能与学院既有秩序产生摩擦；转折：神秘黑影出现揭示更大阴谋；阶段结果：林默决定主动追查父亲失踪真相，同时学院开始监视他。",
            },
        ],
        "characters": [
            {"name": "林默", "role": "protagonist", "description": "星海学院学生，父亲失踪后觉醒异能。当前目标：追查父亲失踪真相。内在矛盾：渴望平凡生活与不得不面对危险真相之间的挣扎。与主角利益关系：自身即为主角。"},
            {"name": "陈雨晴", "role": "supporting", "description": "学院情报系学生，暗中帮助林默。当前目标：利用林默接触「组织」核心情报。秘密：她的家族与「组织」存在隐秘联系。与主角利益关系：表面盟友，实则各取所需。"},
        ],
        "factions": [
            {"name": "星海学院", "type": "学院", "description": "培养异能者的学院，掌握大量修炼资源和情报网络。对主角态度：警惕但想利用。当前阶段行动：派遣观察员监视林默，同时试探他的异能上限。"},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "林默父亲的真实身份", "description": "林默父亲曾是「组织」核心成员。触发场景：林默在实验室触发芯片时。读者表象：父亲只是一个普通研究员。真相方向：父亲是「组织」叛逃者，芯片中藏有组织核心机密。预计推进/兑现章节：第8-10章。"},
        ],
    }

    report = evaluate_genesis_draft(
        draft,
        title="异能觉醒",
        genre="都市异能",
        premise="大学生林默觉醒异能，追查父亲失踪真相",
        target_chapters=2,
    )

    # Should pass or only have warnings, not blockers
    assert report.passed or report.quality_status == "warning"
    assert report.quality_status != "blocked"


def test_approve_blocks_low_quality_draft():
    """Test that quality gate blocks low-quality drafts from approval."""
    # Test the quality gate function directly
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件"},
            {"chapter_number": 2, "objective": "第一章", "key_events": "事件"},
            {"chapter_number": 3, "objective": "第一章", "key_events": "事件"},
        ],
        "outlines": [{"chapters_range": "1-3", "title": "开篇", "content": "开始"}],
        "characters": [{"name": "主角", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="Test",
        genre="都市",
        premise="测试",
        target_chapters=3,
    )

    # Should be blocked
    assert not report.passed
    assert report.quality_status == "blocked"
    assert any(i.code == "REPETITIVE_OBJECTIVE" for i in report.issues)


def test_force_apply_with_confirmation():
    """Test that force apply would require explicit confirmation in API."""
    # This test verifies the quality gate behavior
    # The API-level force_apply logic is tested in integration tests
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件"},
            {"chapter_number": 2, "objective": "第一章", "key_events": "事件"},
            {"chapter_number": 3, "objective": "第一章", "key_events": "事件"},
        ],
        "outlines": [{"chapters_range": "1-3", "title": "开篇", "content": "开始"}],
        "characters": [{"name": "主角", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="Test",
        genre="都市",
        premise="测试",
        target_chapters=3,
    )

    # Quality gate should fail
    assert not report.passed

    # In the API, this would require force_apply=True AND confirm_quality_risk=True
    # to proceed with approval


def test_quality_report_in_generate_response():
    """Test that quality_report structure is correct."""
    # Test the quality report structure directly
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "建立主角处境", "key_events": "主角登场"},
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "故事开始"}],
        "characters": [{"name": "林默", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试小说",
        genre="都市",
        premise="主角觉醒异能",
        target_chapters=1,
    )

    # Verify report structure
    assert hasattr(report, "passed")
    assert hasattr(report, "score")
    assert hasattr(report, "quality_status")
    assert hasattr(report, "issues")
    assert hasattr(report, "metrics")

    # Verify metrics
    assert "instruction_count" in report.metrics
    assert "outline_count" in report.metrics
    assert "character_count" in report.metrics


def test_fill_missing_sections_marks_scaffold():
    """Test that _fill_missing_genesis_sections marks scaffold sections."""
    from novel_factory.api.routes.genesis import (
        _fill_missing_genesis_sections,
        GenesisGenerateRequest,
    )
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    import tempfile
    import os

    db_path = tempfile.mktemp(suffix=".db")
    init_db(db_path)
    repo = Repository(db_path)

    body = GenesisGenerateRequest(
        project_id="test",
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=3,
    )

    # Empty draft
    draft = {}
    filled = _fill_missing_genesis_sections(body, draft)

    # Should have _meta marking scaffold sections
    assert "_meta" in filled
    assert filled["_meta"].get("quality_status") == "scaffold_fallback"
    assert "scaffold_sections" in filled["_meta"]

    os.unlink(db_path)


def test_consecutive_objective_warning():
    """Test that consecutive chapters with same objective trigger warning."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "建立主角处境", "key_events": "事件1"},
            {"chapter_number": 2, "objective": "建立主角处境", "key_events": "事件2"},
            {"chapter_number": 3, "objective": "推进剧情", "key_events": "事件3"},
        ],
        "outlines": [{"chapters_range": "1-3", "title": "开篇", "content": "开始"}],
        "characters": [{"name": "林默", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=3,
    )

    # Should have warning for consecutive duplicate
    assert any(i.code == "CONSECUTIVE_OBJECTIVE" for i in report.issues)


def test_generic_faction_names_detected():
    """Test that generic faction names are detected."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件"},
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始"}],
        "characters": [{"name": "林默", "role": "protagonist"}],
        "factions": [
            {"name": "主角阵营", "type": "阵营", "description": "主角所属"},
            {"name": "敌对势力", "type": "势力", "description": "敌对"},
        ],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=1,
    )

    assert any(i.code == "MOST_GENERIC_FACTIONS" for i in report.issues)


def test_repetitive_ending_hook_detected():
    """Test that repeated ending_hooks are detected."""
    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件1", "ending_hook": "更大危机浮出水面"},
            {"chapter_number": 2, "objective": "第二章", "key_events": "事件2", "ending_hook": "更大危机浮出水面"},
            {"chapter_number": 3, "objective": "第三章", "key_events": "事件3", "ending_hook": "更大危机浮出水面"},
        ],
        "outlines": [{"chapters_range": "1-3", "title": "开篇", "content": "开始"}],
        "characters": [{"name": "林默", "role": "protagonist"}],
        "factions": [],
        "plot_holes": [],
    }

    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=3,
    )

    assert any(i.code == "REPETITIVE_HOOK" for i in report.issues)


def test_canonical_approve_blocks_low_quality_draft(genesis_api):
    """Canonical approve must refuse blocked drafts without explicit force confirmation."""
    client, repo = genesis_api
    project_id = "quality-block-canonical"
    run = _create_generated_genesis(repo, project_id, _low_quality_complete_draft())

    resp = client.post(
        "/api/genesis/approve",
        json={"project_id": project_id, "genesis_id": run["id"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "GENESIS_QUALITY_BLOCKED"
    assert body["error"]["details"]["quality_report"]["passed"] is False

    persisted = repo.get_genesis_run(run["id"])
    assert persisted["status"] == "generated"


def test_latest_genesis_recomputes_quality_report_for_persisted_draft(genesis_api):
    """Reloading the Genesis module must still receive quality gate data."""
    client, repo = genesis_api
    project_id = "quality-latest"
    _create_generated_genesis(repo, project_id, _low_quality_complete_draft())

    resp = client.get(f"/api/projects/{project_id}/genesis/latest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    latest = body["data"]
    assert latest["status"] == "generated"
    assert latest["quality_report"]["passed"] is False
    assert latest["quality_report"]["quality_status"] == "blocked"


def test_canonical_force_approve_persists_quality_audit(genesis_api):
    """Force-apply must persist its audit trail, not only return it in the response."""
    client, repo = genesis_api
    project_id = "quality-force-canonical"
    run = _create_generated_genesis(repo, project_id, _low_quality_complete_draft())

    resp = client.post(
        "/api/genesis/approve",
        json={
            "project_id": project_id,
            "genesis_id": run["id"],
            "force_apply": True,
            "confirm_quality_risk": True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["forced_apply"] is True
    assert body["data"]["quality_report"]["passed"] is False

    persisted = repo.get_genesis_run(run["id"])
    assert persisted["status"] == "approved"
    draft = json.loads(persisted["draft_json"])
    meta = draft["_meta"]
    assert meta["forced_quality_apply"] is True
    assert meta["quality_report_snapshot"]["passed"] is False
    assert meta["quality_report_snapshot"]["quality_status"] == "blocked"


def test_path_force_approve_persists_quality_audit(genesis_api):
    """Path-style approve must use the same durable audit semantics as canonical approve."""
    client, repo = genesis_api
    project_id = "quality-force-path"
    run = _create_generated_genesis(repo, project_id, _low_quality_complete_draft())

    resp = client.post(
        f"/api/projects/{project_id}/genesis/{run['id']}/approve",
        json={"force_apply": True, "confirm_quality_risk": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["forced_apply"] is True

    persisted = repo.get_genesis_run(run["id"])
    assert persisted["status"] == "approved"
    draft = json.loads(persisted["draft_json"])
    assert draft["_meta"]["forced_quality_apply"] is True
    assert draft["_meta"]["quality_report_snapshot"]["passed"] is False
