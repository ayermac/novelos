"""v4.2 Style Sample Analyzer tests.

Covers:
- analyze_style_sample_text with normal text
- Empty text returns error
- Metrics are reasonable for known text
- extract_tone_keywords
- estimate_dialogue_ratio
- estimate_action_description_psychology_ratio
- build_sample_analysis_summary
- No author imitation fields
"""

from __future__ import annotations

from novel_factory.style_bible.sample_analyzer import (
    analyze_style_sample_text,
    extract_tone_keywords,
    estimate_dialogue_ratio,
    estimate_action_description_psychology_ratio,
    build_sample_analysis_summary,
)


# Sample texts for testing
_DIALOGUE_TEXT = """
他冷笑了一声，说道：「你真的以为你能逃掉？」
她沉默了片刻，缓缓开口：「我没有想逃。」
「那就好。」他转身离去。
"""

_ACTION_TEXT = """
他猛地冲了出去，跳过栏杆，一脚踢开门。对手闪身躲开，
反手砍来一刀。他向后翻滚，抓起地上的棍子，用力挥出。
"""

_PSYCHOLOGY_TEXT = """
她心中充满了恐惧和不安，不知道该怎么做。
犹豫了很久，她终于决定面对这个残酷的现实。
内心深处的愧疚让她无法释然，每一次回忆都让她心痛不已。
"""

_LONG_TEXT = """
夜色笼罩着整座城市，紧张的气氛弥漫在空气中。他紧张地握紧了拳头，
目光一凝，盯向前方那道幽暗的身影。悬疑感笼罩着一切，
仿佛有什么诡异的事情即将发生。

「你来了。」对方冷峻的声音响起。

他没有回答，只是默默地注视着对方。心中的紧张感越来越强烈，
额头上渗出了细密的汗珠。这是一个充满危机的对峙局面，
任何一个小小的失误都可能导致严重的后果。

远处传来急促的脚步声，黑暗中似乎隐藏着无数未知的危险。
他感到一阵恐惧，但仍然克制住了自己的情绪，保持着冷静。
"""

_NARRATIVE_TEXT = """
春天的阳光温暖地洒在田野上，微风轻拂过翠绿的麦田。
小鸟在枝头活泼地歌唱，花朵在路边绽放出绚烂的色彩。
孩子们轻快地奔跑着，笑声回荡在整片田野之间。
一切都是那么温馨而美好。
"""


class TestAnalyzeStyleSampleText:
    def test_normal_text_returns_ok(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        assert result["ok"] is True
        assert "metrics" in result["data"]
        assert "analysis" in result["data"]

    def test_metrics_keys(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        metrics = result["data"]["metrics"]
        required_keys = [
            "char_count", "paragraph_count", "sentence_count",
            "avg_sentence_length", "avg_paragraph_length",
            "dialogue_ratio", "action_ratio", "description_ratio",
            "psychology_ratio", "punctuation_density",
            "short_sentence_ratio", "long_sentence_ratio",
            "ai_trace_risk", "tone_keywords", "rhythm_notes",
        ]
        for key in required_keys:
            assert key in metrics, f"Missing key: {key}"

    def test_char_count_positive(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        assert result["data"]["metrics"]["char_count"] > 0

    def test_sentence_count_positive(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        assert result["data"]["metrics"]["sentence_count"] > 0

    def test_dialogue_ratio_in_range(self):
        result = analyze_style_sample_text(_DIALOGUE_TEXT)
        ratio = result["data"]["metrics"]["dialogue_ratio"]
        assert 0.0 <= ratio <= 1.0

    def test_ratios_in_range(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        m = result["data"]["metrics"]
        for key in ["action_ratio", "description_ratio", "psychology_ratio"]:
            assert 0.0 <= m[key] <= 1.0, f"{key} out of range: {m[key]}"

    def test_ai_trace_risk_values(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        risk = result["data"]["metrics"]["ai_trace_risk"]
        assert risk in ("low", "medium", "high", "unknown")

    def test_empty_text_returns_error(self):
        result = analyze_style_sample_text("")
        assert result["ok"] is False

    def test_whitespace_only_returns_error(self):
        result = analyze_style_sample_text("   \n\n  ")
        assert result["ok"] is False

    def test_analysis_has_suggestions(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        analysis = result["data"]["analysis"]
        assert "style_suggestions" in analysis
        assert len(analysis["style_suggestions"]) > 0

    def test_analysis_has_tone_keywords(self):
        result = analyze_style_sample_text(_LONG_TEXT)
        analysis = result["data"]["analysis"]
        assert "tone_keywords" in analysis
        assert isinstance(analysis["tone_keywords"], list)


class TestExtractToneKeywords:
    def test_extracts_tense(self):
        kws = extract_tone_keywords("紧张的气氛弥漫，紧张的对峙")
        assert "紧张" in kws

    def test_extracts_multiple(self):
        kws = extract_tone_keywords("紧张的气氛，克制的表情，悬疑的谜团")
        assert len(kws) >= 2

    def test_no_author_names(self):
        """Never extract author or work names."""
        kws = extract_tone_keywords("金庸 古龙 莫言 鲁迅")
        # These should not match any tone keyword pool
        assert "金庸" not in kws
        assert "古龙" not in kws


class TestEstimateDialogueRatio:
    def test_high_dialogue(self):
        ratio = estimate_dialogue_ratio("「你好」他说。「再见」她道。")
        assert ratio > 0.3

    def test_no_dialogue(self):
        ratio = estimate_dialogue_ratio("他转过身去，走向远方。")
        assert ratio == 0.0


class TestEstimateActionDescriptionPsychology:
    def test_action_text(self):
        result = estimate_action_description_psychology_ratio(_ACTION_TEXT)
        assert result["action_ratio"] > result["psychology_ratio"]

    def test_psychology_text(self):
        result = estimate_action_description_psychology_ratio(_PSYCHOLOGY_TEXT)
        assert result["psychology_ratio"] > result["action_ratio"]

    def test_neutral_text(self):
        result = estimate_action_description_psychology_ratio("今天天气不错。")
        assert result["action_ratio"] == 0.0
        assert result["description_ratio"] == 0.0
        assert result["psychology_ratio"] == 0.0


class TestBuildSampleAnalysisSummary:
    def test_basic_summary(self):
        metrics = {
            "avg_sentence_length": 45,
            "dialogue_ratio": 0.1,
            "action_ratio": 0.1,
            "long_sentence_ratio": 0.3,
            "rhythm_notes": ["句长偏长"],
            "tone_keywords": ["紧张"],
        }
        summary = build_sample_analysis_summary(metrics)
        assert "style_suggestions" in summary
        assert any("句式偏长" in s for s in summary["style_suggestions"])

    def test_no_author_imitation(self):
        """Analysis output never contains author imitation fields."""
        result = analyze_style_sample_text(_LONG_TEXT)
        output_str = str(result)
        assert "author_name" not in output_str
        assert "imitate_author" not in output_str
        assert "模仿" not in output_str
        assert "imitate" not in output_str.lower() or "not" in output_str.lower()
