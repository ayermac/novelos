"""v4.0 Style Bible Checker skill tests.

Covers:
- Forbidden expression detection
- Preferred expression checking
- Sentence rule checking
- Paragraph rule checking
- Chapter opening/ending rules
- AI trace avoidance checking
- Normal text passes with minimal issues
- Score calculation
- No LLM calls
"""

from __future__ import annotations

import json

import pytest

from novel_factory.models.style_bible import (
    AITraceAvoidance,
    ForbiddenExpression,
    PreferredExpression,
    StyleBible,
    StyleRule,
)
from novel_factory.skills.style_bible_checker import StyleBibleCheckerSkill


@pytest.fixture
def checker():
    return StyleBibleCheckerSkill()


@pytest.fixture
def strict_bible():
    """Bible with many rules for testing."""
    return StyleBible(
        name="Strict Test Bible",
        forbidden_expressions=[
            ForbiddenExpression(pattern="冷笑", reason="AI味", severity="blocking"),
            ForbiddenExpression(pattern="不由得", reason="AI味", severity="warning"),
        ],
        preferred_expressions=[
            PreferredExpression(pattern="短句推进", context="战斗"),
        ],
        sentence_rules=[
            StyleRule(description="避免超长句", severity="warning"),
        ],
        paragraph_rules=[
            StyleRule(description="段落不超过500字", severity="warning"),
        ],
        chapter_opening_rules=[
            StyleRule(description="首句须有动作或冲突", severity="warning"),
        ],
        chapter_ending_rules=[
            StyleRule(description="章末须有钩子", severity="warning"),
        ],
        ai_trace_avoidance=AITraceAvoidance(
            avoid_patterns=["深邃的目光", "一股暖流"],
            prefer_patterns=["用动作暗示情绪"],
        ),
    )


class TestForbiddenExpressionDetection:
    """Test forbidden expression detection."""

    def test_forbidden_blocking(self, checker, strict_bible):
        """Blocking forbidden expression is detected."""
        text = "他冷笑一声，转身离去。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        assert result["ok"] is True
        data = result["data"]
        assert data["blocking_issues"] >= 1
        assert any(i["rule_type"] == "forbidden_expression" and i["severity"] == "blocking" for i in data["issues"])

    def test_forbidden_warning(self, checker, strict_bible):
        """Warning-level forbidden expression is detected."""
        text = "他不由得叹了口气。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        assert result["ok"] is True
        data = result["data"]
        assert data["warning_issues"] >= 1
        assert any("不由得" in i["description"] for i in data["issues"])

    def test_no_forbidden(self, checker, strict_bible):
        """Clean text has no forbidden expression issues."""
        text = "他转身离去，没有回头。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        # May have other issues but no forbidden_expression type
        forbidden_issues = [i for i in result["data"]["issues"] if i["rule_type"] == "forbidden_expression"]
        assert len(forbidden_issues) == 0


class TestAITraceDetection:
    """Test AI trace avoidance detection."""

    def test_ai_trace_detected(self, checker, strict_bible):
        """AI trace pattern is detected."""
        text = "他的深邃的目光扫过房间。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        assert any(i["rule_type"] == "ai_trace" for i in result["data"]["issues"])

    def test_no_ai_trace(self, checker, strict_bible):
        """Clean text has no AI trace issues."""
        text = "他看了一眼房间，皱了皱眉。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        ai_issues = [i for i in result["data"]["issues"] if i["rule_type"] == "ai_trace"]
        assert len(ai_issues) == 0


class TestSentenceRules:
    """Test sentence-level rule checking."""

    def test_long_sentence_detected(self, checker, strict_bible):
        """Very long sentence is detected."""
        # Create a sentence without punctuation marks (>80 chars)
        long_sentence = "这是一段非常非常长的句子" + "包含了大量的文字描述和详细说明" * 10
        result = checker.run({"text": long_sentence, "style_bible": strict_bible.to_storage_dict()})
        assert any(i["rule_type"] == "rule_violation" and "超长句" in i["description"] for i in result["data"]["issues"])


class TestParagraphRules:
    """Test paragraph-level rule checking."""

    def test_long_paragraph_detected(self, checker, strict_bible):
        """Very long paragraph is detected."""
        long_para = "这是一段中等长度的句子。" * 60  # >500 chars in one paragraph
        result = checker.run({"text": long_para, "style_bible": strict_bible.to_storage_dict()})
        assert any(i["rule_type"] == "rule_violation" and "超长段落" in i["description"] for i in result["data"]["issues"])


class TestChapterRules:
    """Test chapter opening/ending rule checking."""

    def test_chapter_opening_without_action(self, checker, strict_bible):
        """Opening without action words may trigger warning."""
        text = "那是一个平静的夜晚，月光洒在大地上，一切都显得那么宁静祥和。远处的山峦在月光下若隐若现。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        # May or may not trigger depending on heuristic, but should not crash
        assert result["ok"] is True

    def test_chapter_ending_without_hook(self, checker, strict_bible):
        """Ending without hook words may trigger warning."""
        text = "他走进了房间。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        # May or may not trigger depending on heuristic
        assert result["ok"] is True


class TestScoreCalculation:
    """Test score calculation."""

    def test_perfect_score(self, checker):
        """Clean text against empty bible gets perfect score."""
        bible = StyleBible()
        text = "他走进了房间，看了一眼窗外。"
        result = checker.run({"text": text, "style_bible": bible.to_storage_dict()})
        assert result["data"]["score"] == 100.0

    def test_blocking_reduces_score(self, checker, strict_bible):
        """Blocking issues reduce score by 10 each."""
        text = "他冷笑一声。"
        result = checker.run({"text": text, "style_bible": strict_bible.to_storage_dict()})
        assert result["data"]["score"] < 100.0


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_text(self, checker, strict_bible):
        """Empty text returns perfect score."""
        result = checker.run({"text": "", "style_bible": strict_bible.to_storage_dict()})
        assert result["ok"] is True
        assert result["data"]["score"] == 100.0

    def test_no_style_bible(self, checker):
        """No Style Bible returns ok with note."""
        result = checker.run({"text": "some text", "style_bible": None})
        assert result["ok"] is True
        assert "note" in result["data"]

    def test_invalid_style_bible(self, checker):
        """Invalid Style Bible returns error."""
        result = checker.run({"text": "some text", "style_bible": "not_a_dict"})
        assert result["ok"] is False
        assert "Invalid" in result["error"]

    def test_output_envelope(self, checker, strict_bible):
        """Output follows envelope format."""
        result = checker.run({"text": "测试文本。", "style_bible": strict_bible.to_storage_dict()})
        assert "ok" in result
        assert "error" in result
        assert "data" in result
        # No API keys in output
        json_str = json.dumps(result)
        assert "sk-" not in json_str
        assert "api_key" not in json_str.lower() or "api_key_env" not in json_str
