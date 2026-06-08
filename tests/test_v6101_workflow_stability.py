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
