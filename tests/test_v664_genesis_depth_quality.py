"""Tests for v6.6.4 Genesis Initialization Depth & Specificity Closure."""

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft


@pytest.fixture()
def genesis_api():
    """Create a Genesis API client and repository backed by a temporary DB."""
    db_path = tempfile.mktemp(suffix=".db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    yield TestClient(app), Repository(db_path)
    if os.path.exists(db_path):
        os.unlink(db_path)


def _create_project_and_genesis(repo: Repository, project_id: str, draft: dict) -> dict:
    repo.create_project(project_id=project_id, name="深度测试", genre="都市", description="测试")
    run = repo.create_genesis_run(
        project_id,
        json.dumps(
            {"title": "深度测试", "genre": "都市", "premise": "测试", "target_chapters": 3},
            ensure_ascii=False,
        ),
        status="generated",
    )
    repo.update_genesis_run(run["id"], {"draft_json": json.dumps(draft, ensure_ascii=False)})
    return repo.get_genesis_run(run["id"])


# ---------------------------------------------------------------------------
# 1. High-quality drafts across genres should pass
# ---------------------------------------------------------------------------

def test_high_quality_fantasy_draft_passes():
    """1. A rich fantasy draft with depth should pass."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "叶无尘在叶家祠堂觉醒前世记忆，因此决定重返修炼之路",
                "key_events": "叶无尘在家族祭典上被当众羞辱；意外触发祠堂禁制，觉醒前世仙帝记忆；以雷霆手段击退挑衅者，导致家族震动",
                "emotion_tone": "压抑后的爆发",
                "ending_hook": "叶家老祖出关，注意到叶无尘的异变",
                "continuity_seed": "叶无尘将在下一章进入家族藏经阁寻找前世遗留的功法",
            },
            {
                "chapter_number": 2,
                "objective": "叶无尘潜入藏经阁，从而获得前世功法并引起家族暗线势力注意",
                "key_events": "叶无尘避开守卫潜入藏经阁第三层；发现前世封印的《九转玄功》残卷；暗线势力派出杀手试探，被叶无尘反杀",
                "emotion_tone": "神秘、紧张",
                "ending_hook": "杀手的尸体上发现了不属于叶家的令牌",
                "continuity_seed": "叶无尘需要通过令牌追查暗线势力背后的真正主使",
            },
        ],
        "outlines": [
            {
                "chapters_range": "1-2",
                "title": "觉醒与试探",
                "content": "叶无尘觉醒前世记忆，开始重新修炼。阶段冲突：叶无尘与家族既有权力结构的对抗；转折：暗线势力派出杀手暴露更大阴谋；阶段结果：叶无尘获得功法并发现外部势力渗透。",
            },
        ],
        "characters": [
            {"name": "叶无尘", "role": "protagonist", "description": "前世仙帝转世，叶家弃子。当前目标：恢复修为并查明前世陨落真相。内在矛盾：对家族的恨与对血脉亲情的残留感情。与主角利益关系：自身即主角。"},
            {"name": "叶天行", "role": "antagonist", "description": "叶家现任少主，嫉妒叶无尘的突然崛起。当前目标：打压叶无尘以巩固继承权。秘密：他暗中与外部势力勾结。与主角利益关系：直接竞争对手，试图抹杀叶无尘。"},
        ],
        "factions": [
            {"name": "叶家", "type": "家族", "description": "天元城四大家族之一，掌握修炼资源和城防军队。对主角态度：部分长老想利用叶无尘，部分想除掉他。当前阶段行动：老祖一派试图拉拢叶无尘，少主一派暗中策划暗杀。"},
            {"name": "黑煞盟", "type": "隐秘组织", "description": "渗透到各大家族的地下势力，擅长暗杀和情报交易。对主角态度：视叶无尘为潜在威胁。当前阶段行动：通过叶家内部代理人试探叶无尘的实力底线。"},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "叶无尘前世陨落的真正原因", "description": "叶无尘前世并非死于天劫，而是被人暗算。触发场景：叶无尘修炼《九转玄功》时。读者表象：功法中的心魔劫。真相方向：前世挚爱之人与敌人联手背叛。预计推进/兑现章节：第15-20章。"},
        ],
    }
    report = evaluate_genesis_draft(draft, title="仙帝归来", genre="玄幻", premise="仙帝转世重修", target_chapters=2)
    assert report.quality_status != "blocked"
    assert report.passed or report.quality_status == "warning"


def test_high_quality_urban_draft_passes():
    """1. A rich urban draft with depth should pass."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "陆远在地下拳场意外觉醒古武血脉，因此引起江城地下势力注意",
                "key_events": "陆远为凑医药费参加地下黑拳；在生死关头觉醒古武血脉，一拳击败冠军；地下赌场老板派人接触",
                "emotion_tone": "压抑、热血",
                "ending_hook": "赌场老板身后站着一位陆远认识的故人",
                "continuity_seed": "陆远必须在下一章决定是否接受赌场老板的庇护",
            },
        ],
        "outlines": [
            {
                "chapters_range": "1",
                "title": "觉醒",
                "content": "陆远在绝境中觉醒古武血脉。阶段冲突：陆远与地下拳场规则的对抗；转折：血脉觉醒打破实力天平；阶段结果：陆远获得生存机会但卷入更大势力博弈。",
            },
        ],
        "characters": [
            {"name": "陆远", "role": "protagonist", "description": "外卖员，古武世家遗孤。当前目标：凑钱给妹妹治病。内在矛盾：想过平凡生活但实力不允许。与主角利益关系：自身即主角。"},
        ],
        "factions": [
            {"name": "江城龙门", "type": "地下势力", "description": "掌控江城地下拳场和赌场，拥有古武者打手和情报网。对主角态度：想招揽为己用。当前阶段行动：派人与陆远接触并提出条件。"},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "陆远妹妹的病因", "description": "陆远妹妹并非普通疾病，而是古武世家血脉反噬。触发场景：陆远觉醒血脉时妹妹同时昏迷。读者表象：普通绝症。真相方向：只有陆远找到家族秘传功法才能救治。预计推进/兑现章节：第10-12章。"},
        ],
    }
    report = evaluate_genesis_draft(draft, title="都市古武", genre="都市", premise="外卖员觉醒古武", target_chapters=1)
    assert report.quality_status != "blocked"


def test_high_quality_supernatural_draft_passes():
    """1. A rich supernatural draft with depth should pass."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "苏晚在灵异事务所接手第一起案件，因此发现自己能看见亡魂的真相",
                "key_events": "苏晚接到失踪少女委托；在废弃医院发现灵体残留痕迹；遭遇厉鬼袭击，被迫使用未掌握的能力",
                "emotion_tone": "悬疑、恐惧",
                "ending_hook": "厉鬼临死前喊出了苏晚母亲的名字",
                "continuity_seed": "苏晚必须调查母亲与灵异事件的关联",
            },
        ],
        "outlines": [
            {
                "chapters_range": "1",
                "title": "入局",
                "content": "苏晚踏入灵异世界。阶段冲突：普通人与超自然力量的不对等对抗；转折：发现自己拥有通灵能力；阶段结果：苏晚决定追查母亲死亡真相。",
            },
        ],
        "characters": [
            {"name": "苏晚", "role": "protagonist", "description": "大学生，继承母亲的灵异事务所。当前目标：查清母亲死亡真相。秘密：她的通灵能力来自母亲封印在她体内的灵体。与主角利益关系：自身即主角。"},
        ],
        "factions": [
            {"name": "阴阳司", "type": "官方组织", "description": "政府直属的超自然事件处理机构，拥有法器库和封印术。对主角态度：观望，想吸纳有潜力的新人。当前阶段行动：派观察员记录苏晚第一次案件的表现。"},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "苏晚母亲封印的灵体", "description": "苏晚母亲并非死亡，而是将自身转化为灵体封印在女儿体内。触发场景：苏晚使用通灵能力时。读者表象：苏晚继承了母亲的通灵天赋。真相方向：母亲为了保护苏晚免受某个远古灵体侵害而自我牺牲。预计推进/兑现章节：第20-25章。"},
        ],
    }
    report = evaluate_genesis_draft(draft, title="灵异事务所", genre="灵异", premise="大学生继承灵异事务所", target_chapters=1)
    assert report.quality_status != "blocked"


# ---------------------------------------------------------------------------
# 2. Shallow but complete drafts should be blocked
# ---------------------------------------------------------------------------

def test_shallow_instruction_blocked():
    """2. A complete but shallow draft should trigger SHALLOW_INSTRUCTION or ABSTRACT_OBJECTIVE."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "扩大冲突，推动剧情发展",
                "key_events": "冲突升级；主角成长；势力入场",
                "emotion_tone": "紧张",
            },
            {
                "chapter_number": 2,
                "objective": "获得主动权，进入复杂局面",
                "key_events": "主角反击；局势变化；新角色登场",
                "emotion_tone": "紧张",
            },
        ],
        "outlines": [{"chapters_range": "1-2", "title": "前期", "content": "故事前期，主角面临挑战。"}],
        "characters": [
            {"name": "林默", "role": "protagonist", "description": "主角，很聪明。"},
            {"name": "陈雨晴", "role": "supporting", "description": "女主角，很勇敢。"},
        ],
        "factions": [
            {"name": "学院", "type": "学院", "description": "主角所在的学院。"},
        ],
        "plot_holes": [
            {"code": "PH-001", "title": "身世伏笔", "description": "主角的身世之谜。"},
        ],
    }
    report = evaluate_genesis_draft(draft, title="测试", genre="都市", premise="测试", target_chapters=2)
    assert not report.passed
    assert report.quality_status == "blocked"
    assert any(i.code in ("SHALLOW_INSTRUCTION", "ABSTRACT_OBJECTIVE") for i in report.issues)


# ---------------------------------------------------------------------------
# 3. Adjacent chapters with synonymous but not identical objectives detected
# ---------------------------------------------------------------------------

def test_adjacent_synonymous_objectives_detected():
    """3. Objectives that are paraphrased templates should be caught by repetition or abstraction checks."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林默在学院觉醒异能，发现父亲失踪的线索",
                "key_events": "林默在实验室触发异能；遇到神秘人物；发现线索",
            },
            {
                "chapter_number": 2,
                "objective": "林默在学院展示异能，察觉父亲失踪的新线索",
                "key_events": "林默在实战中爆发；被高层注意；获得新线索",
            },
            {
                "chapter_number": 3,
                "objective": "林默在学院使用异能，追踪父亲失踪的更多线索",
                "key_events": "林默遭遇敌人；击败对手；得到更多线索",
            },
        ],
        "world_settings": [{"title": "世界观", "category": "基础", "content": "现代都市。"}],
        "outlines": [{"chapters_range": "1-3", "title": "前期", "content": "开始。阶段冲突：对抗。转折：觉醒。阶段结果：发现线索。"}],
        "characters": [{"name": "林默", "role": "protagonist", "description": "主角。目标：查真相。矛盾：平凡与危险。利益关系：自身。"}],
        "factions": [{"name": "学院", "type": "学院", "description": "学院。资源：设施。态度：友好。行动：帮助。"}],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。触发场景：觉醒时。读者表象：普通人。真相方向：组织成员。预计推进/兑现章节：第10章。"}],
    }
    report = evaluate_genesis_draft(draft, title="测试", genre="都市", premise="测试", target_chapters=3)
    # v6.6.18 semantic alignment: Natural-language objectives with "发现" should not be falsely blocked
    # CONSECUTIVE_OBJECTIVE is still detected as a warning, but no blocker
    codes = {i.code for i in report.issues}
    assert "CONSECUTIVE_OBJECTIVE" in codes  # Still detected
    assert "SHALLOW_INSTRUCTION" not in codes  # No false positive after semantic alignment
    assert report.passed  # Passes with warnings, not blocked


# ---------------------------------------------------------------------------
# 4. Missing ending_hook / continuity_seed in multi-chapter plan
# ---------------------------------------------------------------------------

def test_missing_continuity_seed_warning():
    """4. Multi-chapter plans missing ending_hook or continuity_seed should warn."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林默在实验室觉醒异能，因此发现父亲失踪的真相",
                "key_events": "林默触发异能；遇到黑影；芯片激活",
            },
            {
                "chapter_number": 2,
                "objective": "林默在实战课展示异能，引发学院注意",
                "key_events": "林默失控；高层注意；陈雨晴相助",
            },
        ],
        "outlines": [{"chapters_range": "1-2", "title": "开篇", "content": "开始。阶段冲突：林默与学院。转折：觉醒。阶段结果：被注意。"}],
        "characters": [{"name": "林默", "role": "protagonist", "description": "主角。目标：查真相。矛盾：平凡与危险。利益关系：自身。"}],
        "factions": [{"name": "学院", "type": "学院", "description": "学院。资源：修炼设施。态度：警惕。行动：观察林默。"}],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。触发场景：觉醒时。读者表象：普通人。真相方向：组织成员。预计推进/兑现章节：第10章。"}],
    }
    report = evaluate_genesis_draft(draft, title="测试", genre="都市", premise="测试", target_chapters=2)
    assert any(i.code == "MISSING_CONTINUITY_SEED" for i in report.issues)


# ---------------------------------------------------------------------------
# 5. key_events array normalization preserves info
# ---------------------------------------------------------------------------

def test_key_events_array_normalization():
    """5. LLM returning key_events as array should be normalized without loss."""
    from novel_factory.api.routes.genesis import _coerce_instruction

    item = {
        "chapter_number": 1,
        "objective": "目标",
        "key_events": ["事件一：林默触发异能", "事件二：黑影出现", "事件三：芯片激活"],
        "emotion_tone": "紧张",
    }
    result = _coerce_instruction(item, 1)
    assert result is not None
    assert "事件一" in result["key_events"]
    assert "事件二" in result["key_events"]
    assert "事件三" in result["key_events"]
    assert "；" in result["key_events"]


# ---------------------------------------------------------------------------
# 6. Characters missing goal/conflict/interest flagged
# ---------------------------------------------------------------------------

def test_shallow_character_motivation_flagged():
    """6. Characters lacking goal, conflict, or interest relation should be flagged."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林默在实验室觉醒异能，因此发现父亲失踪的真相",
                "key_events": "林默触发异能；遇到黑影；芯片激活",
                "ending_hook": "黑影出现",
                "continuity_seed": "追查",
            },
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始。阶段冲突：对抗。转折：觉醒。阶段结果：发现。"}],
        "characters": [
            {"name": "林默", "role": "protagonist", "description": "主角，很聪明。"},
            {"name": "陈雨晴", "role": "supporting", "description": "女主角，很勇敢。"},
        ],
        "factions": [{"name": "学院", "type": "学院", "description": "学院。资源：设施。态度：友好。行动：帮助。"}],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。触发场景：觉醒时。读者表象：普通人。真相方向：组织成员。预计推进/兑现章节：第10章。"}],
    }
    report = evaluate_genesis_draft(draft, title="测试", genre="都市", premise="测试", target_chapters=1)
    assert any(i.code == "SHALLOW_CHARACTER_MOTIVATION" for i in report.issues)


# ---------------------------------------------------------------------------
# 7. Factions missing resources/action flagged
# ---------------------------------------------------------------------------

def test_shallow_faction_action_flagged():
    """7. Factions lacking resources/means or stage actions should be flagged."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林默在实验室觉醒异能，因此发现父亲失踪的真相",
                "key_events": "林默触发异能；遇到黑影；芯片激活",
                "ending_hook": "黑影出现",
                "continuity_seed": "追查",
            },
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始。阶段冲突：对抗。转折：觉醒。阶段结果：发现。"}],
        "characters": [
            {"name": "林默", "role": "protagonist", "description": "主角。目标：查真相。矛盾：平凡与危险。利益关系：自身。"},
        ],
        "factions": [
            {"name": "学院", "type": "学院", "description": "一个普通的学院。"},
        ],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。触发场景：觉醒时。读者表象：普通人。真相方向：组织成员。预计推进/兑现章节：第10章。"}],
    }
    report = evaluate_genesis_draft(draft, title="测试", genre="都市", premise="测试", target_chapters=1)
    assert any(i.code == "SHALLOW_FACTION_ACTION" for i in report.issues)


# ---------------------------------------------------------------------------
# 8. Plot holes missing trigger/appearance/truth/resolve flagged
# ---------------------------------------------------------------------------

def test_weak_plot_hole_design_flagged():
    """8. Plot holes missing trigger scene, appearance, truth direction, or resolve plan should be flagged."""
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林默在实验室觉醒异能，因此发现父亲失踪的真相",
                "key_events": "林默触发异能；遇到黑影；芯片激活",
                "ending_hook": "黑影出现",
                "continuity_seed": "追查",
            },
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始。阶段冲突：对抗。转折：觉醒。阶段结果：发现。"}],
        "characters": [
            {"name": "林默", "role": "protagonist", "description": "主角。目标：查真相。矛盾：平凡与危险。利益关系：自身。"},
        ],
        "factions": [{"name": "学院", "type": "学院", "description": "学院。资源：设施。态度：友好。行动：帮助。"}],
        "plot_holes": [
            {"code": "PH-001", "title": "身世之谜", "description": "主角的身世有问题。"},
        ],
    }
    report = evaluate_genesis_draft(draft, title="测试", genre="都市", premise="测试", target_chapters=1)
    assert any(i.code == "WEAK_PLOT_HOLE_DESIGN" for i in report.issues)


# ---------------------------------------------------------------------------
# 9. latest endpoint recomputes quality_report
# ---------------------------------------------------------------------------

def test_latest_recomputes_quality_report(genesis_api):
    """9. GET /projects/{id}/genesis/latest must return a freshly computed quality_report."""
    client, repo = genesis_api
    project_id = "v664-latest"
    draft = {
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "扩大冲突",
                "key_events": "冲突升级",
            },
        ],
        "outlines": [{"chapters_range": "1", "title": "前期", "content": "开始。"}],
        "characters": [{"name": "主角", "role": "protagonist", "description": "主角。"}],
        "factions": [{"name": "学院", "type": "学院", "description": "学院。"}],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。"}],
    }
    _create_project_and_genesis(repo, project_id, draft)

    resp = client.get(f"/api/projects/{project_id}/genesis/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    latest = body["data"]
    assert "quality_report" in latest
    assert latest["quality_report"]["passed"] is False
    assert latest["quality_report"]["quality_status"] == "blocked"


# ---------------------------------------------------------------------------
# 10. force apply audit still persists
# ---------------------------------------------------------------------------

def test_force_apply_persists_audit(genesis_api):
    """10. Force-approving a blocked draft must persist audit in draft_json._meta."""
    client, repo = genesis_api
    project_id = "v664-force"
    draft = {
        "project_updates": {"description": "测试项目简介"},
        "world_settings": [{"title": "基础", "category": "设定", "content": "现代都市。"}],
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "扩大冲突",
                "key_events": "冲突升级",
            },
        ],
        "outlines": [{"chapters_range": "1", "title": "前期", "content": "开始。"}],
        "characters": [{"name": "主角", "role": "protagonist", "description": "主角。"}],
        "factions": [{"name": "学院", "type": "学院", "description": "学院。"}],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。"}],
    }
    run = _create_project_and_genesis(repo, project_id, draft)

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

    persisted = repo.get_genesis_run(run["id"])
    assert persisted["status"] == "approved"
    persisted_draft = json.loads(persisted["draft_json"])
    assert persisted_draft["_meta"]["forced_quality_apply"] is True
    assert persisted_draft["_meta"]["quality_report_snapshot"]["passed"] is False


# ---------------------------------------------------------------------------
# 11. v6.6.3 tests still pass (covered by CI, verified separately)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 12. production-next / run guard / onboarding tests not broken (covered by CI)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Additional: latest preserves _meta forced_quality_apply audit
# ---------------------------------------------------------------------------

def test_latest_preserves_forced_apply_meta(genesis_api):
    """latest should include _meta forced_quality_apply if present in draft."""
    client, repo = genesis_api
    project_id = "v664-meta"
    draft = {
        "_meta": {"forced_quality_apply": True, "quality_report_snapshot": {"passed": False}},
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林默在实验室觉醒异能，因此发现父亲失踪的真相",
                "key_events": "林默触发异能；遇到黑影；芯片激活",
                "ending_hook": "黑影出现",
                "continuity_seed": "追查",
            },
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始。阶段冲突：对抗。转折：觉醒。阶段结果：发现。"}],
        "characters": [
            {"name": "林默", "role": "protagonist", "description": "主角。目标：查真相。矛盾：平凡与危险。利益关系：自身。"},
        ],
        "factions": [{"name": "学院", "type": "学院", "description": "学院。资源：设施。态度：友好。行动：帮助。"}],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。触发场景：觉醒时。读者表象：普通人。真相方向：组织成员。预计推进/兑现章节：第10章。"}],
    }
    _create_project_and_genesis(repo, project_id, draft)

    resp = client.get(f"/api/projects/{project_id}/genesis/latest")
    assert resp.status_code == 200
    body = resp.json()
    qr = body["data"]["quality_report"]
    assert qr.get("_meta", {}).get("forced_quality_apply") is True
