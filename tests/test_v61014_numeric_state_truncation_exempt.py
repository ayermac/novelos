"""v6.10.14 F8+S7: Numeric state truncation exemption and adaptive budget.

F8: numeric_state facts are exempt from the 200-char value truncation.
S7: compute_adaptive_budget raises budget for long-form projects.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from novel_factory.agent_runtime.context_builder import (
    AgentContextBuilder,
    compute_adaptive_budget,
    _MAX_CONTEXT_CHARS,
    _ADAPTIVE_BUDGET_CHAPTER_THRESHOLD,
    _ADAPTIVE_BUDGET_LONGFORM_CHARS,
)


class TestF8NumericStateTruncationExempt:
    """F8: numeric_state value_json should not be truncated at 200 chars."""

    def _make_builder(self, facts):
        repo = MagicMock()
        repo.list_story_facts.return_value = facts
        repo.get_instruction.return_value = None
        repo.get_characters.return_value = []
        return AgentContextBuilder(repo)

    def test_numeric_state_long_value_not_truncated(self):
        long_value = '{"key": "hp", "value": "999", "evidence": "' + "E" * 300 + '"}'
        facts = [
            {
                "fact_key": "f1",
                "fact_type": "numeric_state",
                "subject": "hp",
                "attribute": "value",
                "value_json": long_value,
                "source_chapter": 5,
                "confidence": 1.0,
            }
        ]
        builder = self._make_builder(facts)
        items = builder._story_facts_context("p1", 10, brief=None)
        assert len(items) == 1
        # The full long value should be present
        assert "E" * 300 in items[0].text

    def test_non_numeric_state_long_value_truncated(self):
        long_value = "X" * 300
        facts = [
            {
                "fact_key": "f2",
                "fact_type": "event",
                "subject": "event",
                "attribute": "desc",
                "value_json": long_value,
                "source_chapter": 5,
                "confidence": 1.0,
            }
        ]
        builder = self._make_builder(facts)
        items = builder._story_facts_context("p1", 10, brief=None)
        assert len(items) == 1
        assert "..." in items[0].text
        assert "X" * 300 not in items[0].text


class TestS7AdaptiveBudget:
    """S7: compute_adaptive_budget raises budget for long-form projects."""

    def test_short_form_uses_base_budget(self):
        budget = compute_adaptive_budget(total_chapters=50)
        assert budget == _MAX_CONTEXT_CHARS

    def test_at_threshold_uses_base_budget(self):
        budget = compute_adaptive_budget(total_chapters=_ADAPTIVE_BUDGET_CHAPTER_THRESHOLD)
        assert budget == _MAX_CONTEXT_CHARS

    def test_above_threshold_uses_longform_budget(self):
        budget = compute_adaptive_budget(total_chapters=_ADAPTIVE_BUDGET_CHAPTER_THRESHOLD + 1)
        assert budget == _ADAPTIVE_BUDGET_LONGFORM_CHARS

    def test_200_chapters_uses_longform_budget(self):
        budget = compute_adaptive_budget(total_chapters=200)
        assert budget == _ADAPTIVE_BUDGET_LONGFORM_CHARS

    def test_custom_base_budget(self):
        budget = compute_adaptive_budget(total_chapters=50, base_budget=8000)
        assert budget == 8000

    def test_custom_base_budget_overridden_for_longform(self):
        budget = compute_adaptive_budget(total_chapters=150, base_budget=8000)
        assert budget == _ADAPTIVE_BUDGET_LONGFORM_CHARS
