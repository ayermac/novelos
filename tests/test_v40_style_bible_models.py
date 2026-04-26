"""v4.0 Style Bible model tests.

Covers:
- StyleBible default values
- StyleBible field validation
- StyleCheckReport
- StyleRule/ForbiddenExpression/PreferredExpression
- No author name references
- Context generation per agent
"""

from __future__ import annotations

import json

import pytest

from novel_factory.models.style_bible import (
    AITraceAvoidance,
    EmotionalIntensity,
    ForbiddenExpression,
    Pacing,
    POV,
    PreferredExpression,
    StyleBible,
    StyleCheckIssue,
    StyleCheckReport,
    StyleRule,
)


class TestStyleBibleDefaults:
    """Test StyleBible model defaults."""

    def test_default_values(self):
        """StyleBible has sensible defaults."""
        bible = StyleBible()
        assert bible.name == "Default Style Bible"
        assert bible.pacing == Pacing.BALANCED
        assert bible.pov == POV.THIRD_PERSON_LIMITED
        assert bible.emotional_intensity == EmotionalIntensity.MEDIUM
        assert bible.version == "1.0.0"
        assert bible.forbidden_expressions == []
        assert bible.preferred_expressions == []

    def test_custom_values(self):
        """StyleBible accepts custom values."""
        bible = StyleBible(
            name="Test Bible",
            genre="玄幻",
            pacing="fast",
            pov="first_person",
            tone_keywords=["热血", "爽感"],
            emotional_intensity="high",
        )
        assert bible.name == "Test Bible"
        assert bible.genre == "玄幻"
        assert bible.pacing == Pacing.FAST
        assert bible.pov == POV.FIRST_PERSON
        assert bible.tone_keywords == ["热血", "爽感"]
        assert bible.emotional_intensity == EmotionalIntensity.HIGH

    def test_with_forbidden_expressions(self):
        """StyleBible with forbidden expressions."""
        bible = StyleBible(
            forbidden_expressions=[
                ForbiddenExpression(pattern="嘴角勾起", reason="AI味", severity="blocking"),
                ForbiddenExpression(pattern="不由得", reason="AI味"),
            ],
        )
        assert len(bible.forbidden_expressions) == 2
        assert bible.forbidden_expressions[0].severity == "blocking"
        assert bible.forbidden_expressions[1].severity == "warning"

    def test_with_preferred_expressions(self):
        """StyleBible with preferred expressions."""
        bible = StyleBible(
            preferred_expressions=[
                PreferredExpression(pattern="短句+动作推进", context="战斗场景"),
            ],
        )
        assert len(bible.preferred_expressions) == 1
        assert bible.preferred_expressions[0].context == "战斗场景"


class TestStyleBibleSerialization:
    """Test StyleBible serialization."""

    def test_to_storage_dict(self):
        """StyleBible can be serialized to dict."""
        bible = StyleBible(name="Test", genre="科幻")
        d = bible.to_storage_dict()
        assert d["name"] == "Test"
        assert d["genre"] == "科幻"
        # Must be JSON-serializable
        json_str = json.dumps(d, ensure_ascii=False)
        assert "Test" in json_str

    def test_from_storage_dict(self):
        """StyleBible can be deserialized from dict."""
        bible = StyleBible(name="Test", genre="科幻", pacing="fast")
        d = bible.to_storage_dict()
        restored = StyleBible.from_storage_dict(d)
        assert restored.name == "Test"
        assert restored.genre == "科幻"
        assert restored.pacing == Pacing.FAST

    def test_roundtrip(self):
        """StyleBible survives serialization roundtrip."""
        bible = StyleBible(
            name="Roundtrip Test",
            genre="仙侠",
            tone_keywords=["超脱", "悟道"],
            forbidden_expressions=[ForbiddenExpression(pattern="一道流光")],
        )
        d = bible.to_storage_dict()
        restored = StyleBible.from_storage_dict(d)
        assert restored.name == bible.name
        assert restored.tone_keywords == bible.tone_keywords
        assert len(restored.forbidden_expressions) == 1
        assert restored.forbidden_expressions[0].pattern == "一道流光"


class TestStyleBibleContext:
    """Test StyleBible context generation."""

    def test_summary_for_context(self):
        """summary_for_context returns a string."""
        bible = StyleBible(
            name="Test",
            genre="玄幻",
            tone_keywords=["热血"],
            pacing="fast",
        )
        summary = bible.summary_for_context()
        assert "Test" in summary
        assert "热血" in summary
        assert "fast" in summary

    def test_summary_respects_token_budget(self):
        """summary_for_context respects token budget."""
        bible = StyleBible(
            name="Test",
            tone_keywords=["a"] * 100,  # Lots of keywords
        )
        summary = bible.summary_for_context(token_budget=50)
        # Should be truncated
        max_chars = int(50 / 0.5)
        assert len(summary) <= max_chars + 50  # Allow some margin for truncation marker

    def test_rules_for_author(self):
        """rules_for_author returns author-specific rules."""
        bible = StyleBible(
            prose_style="紧凑",
            dialogue_style="口语化",
            preferred_expressions=[PreferredExpression(pattern="短句推进")],
        )
        rules = bible.rules_for_agent("author")
        assert "紧凑" in rules
        assert "口语化" in rules

    def test_rules_for_editor(self):
        """rules_for_editor returns editor-specific rules."""
        bible = StyleBible(
            forbidden_expressions=[ForbiddenExpression(pattern="冷笑", severity="blocking")],
            ai_trace_avoidance=AITraceAvoidance(avoid_patterns=["深邃的目光"]),
        )
        rules = bible.rules_for_agent("editor")
        assert "冷笑" in rules
        assert "深邃的目光" in rules

    def test_rules_for_planner(self):
        """rules_for_planner returns planner-specific rules."""
        bible = StyleBible(
            tone_keywords=["紧张"],
            pacing="fast",
            chapter_opening_rules=[StyleRule(description="首句须有冲突")],
        )
        rules = bible.rules_for_agent("planner")
        assert "紧张" in rules
        assert "首句须有冲突" in rules

    def test_rules_for_unknown_agent(self):
        """rules_for unknown agent returns generic summary."""
        bible = StyleBible(name="Test")
        rules = bible.rules_for_agent("unknown_agent")
        assert "Test" in rules

    def test_empty_bible_context(self):
        """Empty StyleBible still generates valid context."""
        bible = StyleBible()
        summary = bible.summary_for_context()
        assert isinstance(summary, str)


class TestStyleCheckReport:
    """Test StyleCheckReport model."""

    def test_default_report(self):
        """Default report has no issues."""
        report = StyleCheckReport()
        assert report.total_issues == 0
        assert report.blocking_issues == 0
        assert report.score == 100.0

    def test_report_with_issues(self):
        """Report with issues."""
        report = StyleCheckReport(
            total_issues=2,
            blocking_issues=1,
            warning_issues=1,
            issues=[
                StyleCheckIssue(rule_type="forbidden_expression", severity="blocking", description="Test"),
                StyleCheckIssue(rule_type="rule_violation", severity="warning", description="Test2"),
            ],
            score=70.0,
        )
        assert report.blocking_issues == 1
        assert report.score == 70.0


class TestNoAuthorReferences:
    """Ensure no author references in StyleBible fields."""

    def test_no_author_in_defaults(self):
        """Default StyleBible has no author references."""
        bible = StyleBible()
        json_str = json.dumps(bible.to_storage_dict(), ensure_ascii=False)
        # Check for common author reference patterns
        assert "模仿" not in json_str
        assert "仿写" not in json_str

    def test_template_no_author(self):
        """Templates have no author references."""
        from novel_factory.style_bible.templates import list_templates
        templates = list_templates()
        for tid, tdata in templates.items():
            json_str = json.dumps(tdata, ensure_ascii=False)
            assert "模仿" not in json_str, f"Template {tid} contains author reference"
            assert "仿写" not in json_str, f"Template {tid} contains author reference"
