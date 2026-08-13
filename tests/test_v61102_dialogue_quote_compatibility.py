"""Regression tests for Chinese curly-quote dialogue detection."""

from novel_factory.skills.character_voice_checker import CharacterVoiceChecker
from novel_factory.skills.pacing_profile_checker import PacingProfileChecker


def test_character_voice_extracts_curly_quote_dialogue():
    checker = CharacterVoiceChecker()
    dialogues = checker._extract_dialogues(
        "林默说：“零点前全部撤离。”苏晴问：“旧计时器怎么办？”"
    )

    assert [item["text"] for item in dialogues] == [
        "零点前全部撤离。",
        "旧计时器怎么办？",
    ]


def test_pacing_profile_counts_curly_quote_dialogue_ratio():
    checker = PacingProfileChecker()
    content = "旁白" * 10 + "“" + "这段对白持续推进冲突" * 5 + "”" + "旁白" * 10

    score, findings = checker._check_dialogue_ratio(content)

    assert score == 100
    assert all(item.get("code") != "LOW_DIALOGUE_RATIO" for item in findings)
