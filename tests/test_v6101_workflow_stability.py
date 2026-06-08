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
