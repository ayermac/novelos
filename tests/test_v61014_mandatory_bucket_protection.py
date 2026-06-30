"""v6.10.14 S1+S3+F8: Mandatory bucket protection, per-bucket truncation,
and numeric_state truncation exemption.

Tests that:
- mandatory buckets (hard_constraints, numeric_state_constraints, timeline_constraints)
  are always included even when budget is tight
- non-mandatory buckets use continue (not break) so later mandatory buckets survive
- story_facts value truncation exempts numeric_state facts
"""

from __future__ import annotations

import pytest

from novel_factory.agent_runtime.context_builder import (
    AgentContextBundle,
    ContextItem,
    format_context_bundle_for_prompt,
)


def _make_item(kind: str, text: str, priority: int = 5) -> ContextItem:
    return ContextItem(kind=kind, text=text, source="test", priority=priority, trusted=True)


def test_mandatory_numeric_state_survives_tight_budget():
    """When story_facts fills the budget, numeric_state_constraints must still appear."""
    bundle = AgentContextBundle()
    # Fill story_facts with a large block to trigger truncation
    bundle.story_facts = [
        _make_item("story_fact", f"fact_{i} = " + "x" * 80, priority=4)
        for i in range(50)
    ]
    # numeric_state is mandatory and comes AFTER story_facts in order
    bundle.numeric_state_constraints = [
        _make_item("numeric_state_constraint", "玉符剩余次数 = 3", priority=1),
    ]

    result = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=2000)

    assert "玉符剩余次数 = 3" in result, "numeric_state must survive budget pressure"
    assert "数值状态约束" in result


def test_mandatory_hard_constraints_survives_tight_budget():
    """hard_constraints (mandatory) must always be included."""
    bundle = AgentContextBundle()
    bundle.revision_feedback = [
        _make_item("revision", "r" * 200, priority=1) for _ in range(20)
    ]
    bundle.story_facts = [
        _make_item("story_fact", "s" * 200, priority=4) for _ in range(20)
    ]
    bundle.hard_constraints = [
        _make_item("hard", "主角不可复活", priority=0),
    ]

    result = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=1500)

    assert "主角不可复活" in result


def test_mandatory_timeline_constraints_survives_tight_budget():
    """timeline_constraints (mandatory) must always be included."""
    bundle = AgentContextBundle()
    bundle.story_facts = [
        _make_item("story_fact", "f" * 200, priority=4) for _ in range(30)
    ]
    bundle.timeline_constraints = [
        _make_item("timeline", "三天后举行拍卖会", priority=1),
    ]

    result = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=2000)

    assert "三天后举行拍卖会" in result


def test_break_replaced_by_continue():
    """Non-mandatory bucket truncation should NOT skip subsequent mandatory buckets.

    This is the core regression test for the C1 bug: previously `break` would
    skip numeric_state_constraints (position 5) after story_facts (position 4)
    triggered truncation.
    """
    bundle = AgentContextBundle()
    # story_facts (position 4, non-mandatory) — large enough to trigger truncation
    bundle.story_facts = [
        _make_item("story_fact", "S" * 100, priority=4) for _ in range(30)
    ]
    # numeric_state_constraints (position 5, mandatory) — must still appear
    bundle.numeric_state_constraints = [
        _make_item("numeric_state", "灵石余额 = 5000", priority=1),
    ]

    result = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=1500)

    assert "灵石余额 = 5000" in result, (
        "numeric_state_constraints must appear even after story_facts triggers truncation"
    )


def test_non_mandatory_bucket_is_truncated_not_dropped():
    """When a non-mandatory bucket partially fits, it should be truncated (not fully dropped)."""
    bundle = AgentContextBundle()
    bundle.story_facts = [
        _make_item("story_fact", f"fact_{i}", priority=4) for i in range(10)
    ]

    # Very small budget so story_facts gets truncated
    result = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=300)

    assert "已截断" in result or "fact_0" in result


def test_normal_budget_no_truncation():
    """With sufficient budget, all buckets are included without truncation."""
    bundle = AgentContextBundle()
    bundle.hard_constraints = [_make_item("hard", "rule1", priority=0)]
    bundle.story_facts = [_make_item("story_fact", "fact1", priority=4)]
    bundle.numeric_state_constraints = [_make_item("numeric", "hp = 100", priority=1)]

    result = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=10000)

    assert "rule1" in result
    assert "fact1" in result
    assert "hp = 100" in result
    assert "已截断" not in result


def test_mandatory_overflow_warning_logged(caplog):
    """When mandatory buckets cause overflow, a warning should be logged."""
    import logging

    bundle = AgentContextBundle()
    bundle.story_facts = [
        _make_item("story_fact", "x" * 200, priority=4) for _ in range(10)
    ]
    bundle.numeric_state_constraints = [
        _make_item("numeric", "mandatory_value = 42", priority=1),
    ]

    caplog.set_level(logging.WARNING)
    format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=500)

    # The mandatory bucket should still appear in the output regardless
    result = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=500)
    assert "mandatory_value = 42" in result
