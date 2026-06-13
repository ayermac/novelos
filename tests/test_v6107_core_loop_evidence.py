"""v6.10.7: Core-loop evidence governance tests."""

from __future__ import annotations

import os
import tempfile

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.models.chapter_contracts import ChapterBrief
from novel_factory.models.creative_contracts import CoreLoopStep, StoryContract
from novel_factory.models.creative_ledgers import ChapterContractMetrics
from novel_factory.quality.core_loop_checker import check_core_loop_compliance


@pytest.fixture()
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture()
def repo(db_path):
    return Repository(db_path)


def _summoner_contract(project_id: str = "test_proj", status: str = "active") -> StoryContract:
    return StoryContract(
        project_id=project_id,
        core_promise="F级召唤师获得魂源和兵主指令后，用兵俑军团兑现战果并反噬敌人。",
        core_loop=[
            CoreLoopStep(id="trigger", label="触发资源机会"),
            CoreLoopStep(id="summon", label="召唤或指挥兵俑"),
            CoreLoopStep(id="reward", label="获得魂源或新指令"),
            CoreLoopStep(id="payoff", label="用兵俑兑现战果"),
            CoreLoopStep(id="reaction", label="敌人受到反噬"),
        ],
        payoff_types=["魂源", "兵俑", "召唤", "指令"],
        status=status,
    )


def test_brief_payoff_declaration_does_not_count_as_textual_evidence():
    contract = _summoner_contract(status="confirmed")
    brief = ChapterBrief.model_validate({
        "tier1": {
            "chapter_goal": "完成兵主指令兑现",
            "reader_payoff": "主角获得魂源并打脸敌人",
            "primary_payoff": "兵俑军团反杀",
            "core_loop_target": "payoff",
            "payoff_evidence_plan": "正文写出兵俑出手",
        },
    })

    result = check_core_loop_compliance(
        project_id="test_proj",
        chapter_number=3,
        content="黑市危机不断升级，顾家暗卫封锁退路，主角只能继续周旋。",
        story_contract=contract,
        chapter_brief=brief,
    )

    assert result.core_payoff_present is False
    assert "本章未检测到核心兑现证据" in result.warnings


def test_unlock_without_summon_payoff_and_state_delta_is_blocking_for_active_contract():
    contract = _summoner_contract(status="active")
    recent = [
        ChapterContractMetrics(
            chapter_number=2,
            tracked_states={"魂源": "14.5", "统帅值": "10/10"},
            core_payoff_present=False,
        )
    ]

    content = """
    【指令解锁：噬源】
    七号仓顶部，三颗中品魂源石同时炸开——不是碎裂，是被无形力量瞬间抽干。
    顾长歌面前的追踪罗盘从正中央裂开，他低声道：我的鱼钩被崩断了。
    """

    result = check_core_loop_compliance(
        project_id="test_proj",
        chapter_number=3,
        content=content,
        story_contract=contract,
        recent_contract_metrics=recent,
    )

    assert result.passed is False
    assert result.core_payoff_present is False
    assert "contract_required_payoff" in result.missing_evidence
    assert "state_delta:魂源" in result.missing_evidence
    assert result.blocking_issues


def test_summon_payoff_with_state_delta_passes():
    contract = _summoner_contract(status="active")
    recent = [
        ChapterContractMetrics(
            chapter_number=2,
            tracked_states={"魂源": "14.5", "统帅值": "10/10"},
        )
    ]
    content = """
    【击杀E级暗卫×2，获得魂源+5.5】
    陆恒抬手下令，十名刀盾兵俑列阵冲出，刀锋压住顾家暗卫，将两人逼得跪倒在地。
    意识深处，魂源从14.5变为20。
    """

    result = check_core_loop_compliance(
        project_id="test_proj",
        chapter_number=4,
        content=content,
        story_contract=contract,
        recent_contract_metrics=recent,
    )

    assert result.passed is True
    assert result.core_payoff_present is True
    assert result.missing_evidence == []
    assert result.tracked_states["魂源"] == "20"
    assert result.state_deltas == [{"state": "魂源", "from": "14.5", "to": "20", "source": "text_delta"}]


def test_arrow_state_delta_uses_final_value_as_current_state():
    contract = _summoner_contract(status="active")
    recent = [
        ChapterContractMetrics(
            chapter_number=3,
            tracked_states={"魂源": "4.5", "统帅值": "10/10"},
            core_payoff_present=False,
        )
    ]
    content = """
    【获得奖励：中品魂源石】
    陆恒动用噬源指令吸收魂源石，十名兵俑列阵冲出，刀盾压得顾家暗卫连退三步。
    顾长歌面前的追踪罗盘炸开，他的脸色终于僵住。
    【魂源：4.5 → 49.5】【统帅值：10/10】
    """

    result = check_core_loop_compliance(
        project_id="test_proj",
        chapter_number=4,
        content=content,
        story_contract=contract,
        recent_contract_metrics=recent,
    )

    assert result.passed is True
    assert result.core_payoff_present is True
    assert result.tracked_states["魂源"] == "49.5"
    assert result.tracked_states["统帅值"] == "10/10"
    assert {"state": "魂源", "from": "4.5", "to": "49.5", "source": "text_delta"} in result.state_deltas
    assert "state_delta:魂源" not in result.missing_evidence


def test_workflow_helper_routes_core_loop_blocking_to_author(repo):
    from novel_factory.workflow.nodes import _check_core_loop_compliance, _determine_revision_target
    from novel_factory.quality.issue_codes import IssueCode
    from novel_factory.api.routes._core_loop_diagnostics import get_core_loop_diagnostics_for_chapter

    conn = repo._conn()
    try:
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("test_proj", "Test Novel", "urban"),
        )
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test_proj", 3, "第三章 测试", "polished", "", 0),
        )
        conn.commit()
    finally:
        conn.close()

    contract = _summoner_contract()
    repo.upsert_creative_contract("test_proj", "story_contract", contract.model_dump())
    repo.upsert_creative_ledger(
        "test_proj",
        2,
        "contract_metrics",
        ChapterContractMetrics(
            chapter_number=2,
            tracked_states={"魂源": "14.5", "统帅值": "10/10"},
        ).model_dump(),
    )

    result = _check_core_loop_compliance(
        repo,
        "test_proj",
        3,
        "【指令解锁：噬源】三颗中品魂源石被抽干，顾长歌的追踪罗盘崩断。",
    )

    assert result["passed"] is False
    assert result["blocking_issues"]
    assert "state_delta:魂源" in result["diagnostics"]["missing_evidence"]
    assert _determine_revision_target([IssueCode.CORE_LOOP_DRIFT_WARNING]) == "author"

    diagnostics = get_core_loop_diagnostics_for_chapter(repo, "test_proj", 3)
    assert diagnostics is not None
    assert diagnostics["core_payoff_present"] is False
    assert "state_delta:魂源" in diagnostics["missing_evidence"]
