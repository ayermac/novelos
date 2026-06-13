"""v6.10.1 workflow stability regressions."""

from __future__ import annotations

from unittest.mock import MagicMock

from novel_factory.quality.chapter_seam import evaluate_chapter_seam


def _seam_repo(previous_content: str, ending_hook: str = ""):
    repo = MagicMock()
    repo.get_chapter.side_effect = lambda project_id, chapter_number: (
        {"content": previous_content} if chapter_number == 2 else None
    )
    repo.get_chapter_state.return_value = {
        "state_data": {
            "suspense_hooks": [],
        }
    }
    repo.get_instruction.return_value = {
        "ending_hook": ending_hook,
    }
    return repo


def test_chapter_seam_accepts_semantic_time_anchor_continuation():
    """A chapter opening can bridge a time hook without repeating the exact word."""
    repo = _seam_repo(
        "上一章结尾，他说：今晚，我会住在江城最高的地方。\n"
        "掌心的修罗徽章苏醒，系统询问是否在帝豪总统套房开启第二次签到。",
        "今晚在帝豪总统套房开启第二次签到",
    )
    current = (
        "掌心修罗徽章的灼热感尚未完全消退，系统提示仍悬在视野边缘。\n"
        "黑色专车滑入帝豪酒店门廊，秦伯替他拉开车门。"
    )

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is True
    assert result["blocking_issues"] == []


def test_chapter_seam_still_blocks_unacknowledged_time_anchor():
    """A new unrelated opening still fails when it ignores a hard previous time hook."""
    repo = _seam_repo(
        "上一章结尾，他说：今晚，我会住在江城最高的地方。\n"
        "掌心的修罗徽章苏醒，系统询问是否在帝豪总统套房开启第二次签到。",
        "今晚在帝豪总统套房开启第二次签到",
    )
    current = "第二天清晨，林辰坐在陌生办公室里翻看合同，像昨夜什么都没发生。"

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is False
    assert any("明确时间节点" in issue for issue in result["blocking_issues"])


def test_chapter_seam_ignores_question_fragment_as_location():
    """Question fragments ending in 所 should not become hard location obligations."""
    repo = _seam_repo(
        "上一章结尾，系统提示：是否终止与苏家所有合作，并立刻开启第二次签到？",
        "是否终止与苏家所有合作",
    )
    current = "掌心修罗徽章的灼热感尚未完全消退，系统提示仍悬在视野边缘。"

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is True
    assert all("终止与苏家所" not in issue for issue in result["blocking_issues"])


def test_chapter_seam_ignores_action_fragment_as_location():
    """v6.10.5: Action descriptions like '明天去苏家所' must not become hard location obligations.

    The location "苏家所" is filtered because it appears in an action context
    ("去苏家所"). However, the time marker "明天" remains a legitimate hard
    constraint and still produces a blocking issue when unacknowledged.
    """
    repo = _seam_repo(
        "上一章结尾，他说：明天去苏家所，把东西取回来。",
        "明天去苏家所",
    )
    current = "掌心修罗徽章的灼热感尚未完全消退，系统提示仍悬在视野边缘。"

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    # Location must NOT appear in blocking issues (the core fix).
    assert not any("苏家所" in issue for issue in result["blocking_issues"])
    # Time marker "明天" is still a hard constraint when unacknowledged.
    assert result["pass"] is False
    assert any("明确时间节点" in issue for issue in result["blocking_issues"])


def test_chapter_seam_ignores_suoyou_suffix():
    """v6.10.5: '苏家所' extracted from '苏家所有钱' must not be treated as a location."""
    repo = _seam_repo(
        "上一章结尾，苏家所有钱都被冻结了。",
        "苏家所有钱",
    )
    current = "掌心修罗徽章的灼热感尚未完全消退，系统提示仍悬在视野边缘。"

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is True
    assert result["blocking_issues"] == []


def test_chapter_seam_ignores_body_part_fragment_as_location():
    """Body-part phrases ending in 部 must not become location obligations."""
    repo = _seam_repo(
        "上一章结尾，今晚的寒意顺着脊背爬上来，饥饿搅得胃部一阵抽痛。",
        "今晚饥饿搅得胃部抽痛",
    )
    current = "今晚的风还冷，他扶着墙站稳，先把涌上喉咙的酸意压下去。"

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is True
    assert not any("搅得胃部" in issue for issue in result["blocking_issues"])


def test_chapter_seam_blocks_precise_countdown_regression():
    """A countdown sequence must continue from the latest previous value, not rewind."""
    previous = (
        "左眼猩红数字断崖式暴跌。\n"
        "23:45:21。\n"
        "23:31:04。\n"
        "23:19:27。\n"
        "23:03:41。\n"
        "锁链一根接一根崩断，第四声搏动砸进胸腔。"
    )
    current = (
        "23:45:16。\n"
        "左眼猛地一烫，暗红的肉质地面在膝盖下蠕动。"
    )
    repo = _seam_repo(previous)

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is False
    assert any("倒计时已推进至" in issue for issue in result["blocking_issues"])
    assert any("23:03:41" in issue and "23:45:16" in issue for issue in result["blocking_issues"])


def test_chapter_seam_accepts_precise_countdown_continuation():
    """Continuing at or below the latest countdown value is not a seam break."""
    previous = (
        "左眼猩红数字断崖式暴跌。\n"
        "23:45:21。\n"
        "23:31:04。\n"
        "23:19:27。\n"
        "23:03:41。\n"
        "锁链一根接一根崩断，第四声搏动砸进胸腔。"
    )
    current = (
        "23:03:40。\n"
        "第五声搏动紧跟着砸下，林辰的膝盖仍压在暗红肉质地面上。"
    )
    repo = _seam_repo(previous)

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is True
    assert result["blocking_issues"] == []


def test_chapter_seam_blocks_numeric_state_reset():
    """Generic numeric states such as balances and levels must not reset silently."""
    previous = (
        "系统面板终于稳定下来。\n"
        "账户余额只剩800万。\n"
        "权限等级升至3级。\n"
        "林辰把这两个数字牢牢记住。"
    )
    current = (
        "账户余额仍是1200万。\n"
        "权限等级还是2级。\n"
        "林辰推门走进会议室。"
    )
    repo = _seam_repo(previous)

    result = evaluate_chapter_seam(repo, "novel", 3, current)

    assert result["pass"] is False
    assert any("章间数值继承断裂" in issue for issue in result["blocking_issues"])
    assert any("800万" in issue and "1200万" in issue for issue in result["blocking_issues"])


def test_numeric_state_extracts_open_ended_state_metrics():
    """Explicit state metrics outside the built-in keyword list should still persist."""
    from novel_factory.quality.numeric_state import extract_numeric_states

    states = extract_numeric_states(
        "系统面板刷新：锚点稳定率降至43%。\n"
        "裂隙指数：17.8点。\n"
        "外级授权残页剩余2枚。\n"
        "林辰坐上17层电梯。"
    )

    values = {state.label: state.value for state in states}
    assert values["锚点稳定率"] == "43%"
    assert values["裂隙指数"] == "17.8点"
    assert values["外级授权残页"] == "2枚"
    assert "电梯" not in values


def test_numeric_state_extracts_arrow_final_value_and_ratio_snapshot():
    """Dashboard-style state transitions should persist final values, not old values."""
    from novel_factory.quality.numeric_state import extract_numeric_states

    states = extract_numeric_states("【魂源：4.5 → 49.5】【统帅值：10/10】")

    values = {state.label: state.value for state in states}
    assert values["魂源"] == "49.5"
    assert values["统帅值"] == "10/10"
