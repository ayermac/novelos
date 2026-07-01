"""v6.10.14 S4: Aging detector for long-form story facts and plot holes."""

from __future__ import annotations

import pytest

from novel_factory.context.aging import (
    NUMERIC_STATE_AGING_THRESHOLD,
    PLOT_AGING_THRESHOLD,
    detect_aging_facts,
    detect_aging_plots,
    build_aging_warnings,
)


def _make_fact(fact_type: str, subject: str, source_chapter: int) -> dict:
    return {
        "fact_key": f"key_{subject}",
        "fact_type": fact_type,
        "subject": subject,
        "attribute": "value",
        "value_json": "test",
        "source_chapter": source_chapter,
    }


def _make_plot(code: str, planted_ch: int, planned_resolve=None, status="pending", title=None) -> dict:
    return {
        "code": code,
        "title": title or f"Plot {code}",
        "status": status,
        "planted_chapter": planted_ch,
        "planned_resolve_chapter": planned_resolve,
    }


class TestDetectAgingFacts:
    def test_numeric_state_below_threshold_not_aged(self):
        facts = [_make_fact("numeric_state", "hp", source_chapter=10)]
        aged = detect_aging_facts(facts, current_chapter=20)
        assert len(aged) == 0  # age=10 < 15 threshold

    def test_numeric_state_at_threshold_is_aged(self):
        facts = [_make_fact("numeric_state", "hp", source_chapter=5)]
        aged = detect_aging_facts(facts, current_chapter=20)
        assert len(aged) == 1  # age=15 >= 15 threshold
        assert aged[0]["_age"] == 15

    def test_non_numeric_state_not_aged(self):
        facts = [_make_fact("event", "some_event", source_chapter=1)]
        aged = detect_aging_facts(facts, current_chapter=100)
        assert len(aged) == 0

    def test_sorted_by_most_stale_first(self):
        facts = [
            _make_fact("numeric_state", "new", source_chapter=15),
            _make_fact("numeric_state", "old", source_chapter=1),
            _make_fact("numeric_state", "mid", source_chapter=5),
        ]
        aged = detect_aging_facts(facts, current_chapter=30)
        assert len(aged) == 3
        assert aged[0]["subject"] == "old"  # age=29, most stale
        assert aged[1]["subject"] == "mid"  # age=25
        assert aged[2]["subject"] == "new"  # age=15

    def test_custom_threshold(self):
        facts = [_make_fact("numeric_state", "hp", source_chapter=10)]
        aged = detect_aging_facts(facts, current_chapter=12, threshold=2)
        assert len(aged) == 1  # age=2 >= 2 custom threshold


class TestDetectAgingPlots:
    def test_pending_plot_below_threshold_not_aged(self):
        plots = [_make_plot("P001", planted_ch=10)]
        aged = detect_aging_plots(plots, current_chapter=20)
        assert len(aged) == 0  # age=10 < 20 threshold

    def test_pending_plot_at_threshold_is_aged(self):
        plots = [_make_plot("P001", planted_ch=5)]
        aged = detect_aging_plots(plots, current_chapter=25)
        assert len(aged) == 1  # age=20 >= 20 threshold

    def test_overdue_plot_is_aged(self):
        plots = [_make_plot("P001", planted_ch=1, planned_resolve=10)]
        aged = detect_aging_plots(plots, current_chapter=15)
        assert len(aged) == 1
        assert aged[0]["_overdue"] is True

    def test_resolved_plot_not_aged(self):
        plots = [_make_plot("P001", planted_ch=1, status="resolved")]
        aged = detect_aging_plots(plots, current_chapter=100)
        assert len(aged) == 0

    def test_overdue_prioritized_over_aged(self):
        plots = [
            _make_plot("AGED", planted_ch=1),  # age=30, not overdue
            _make_plot("OVERDUE", planted_ch=5, planned_resolve=10),  # overdue
        ]
        aged = detect_aging_plots(plots, current_chapter=30)
        assert aged[0]["code"] == "OVERDUE"  # overdue first


class TestBuildAgingWarnings:
    def test_returns_context_items(self):
        facts = [_make_fact("numeric_state", "hp", source_chapter=1)]
        plots = [_make_plot("P001", planted_ch=1)]
        items = build_aging_warnings(facts, plots, current_chapter=30)
        assert len(items) > 0
        assert all(hasattr(item, "kind") for item in items)
        assert all(item.kind == "aging_warning" for item in items)

    def test_max_aging_warnings_limit(self):
        facts = [_make_fact("numeric_state", f"hp_{i}", source_chapter=1) for i in range(20)]
        plots = [_make_plot(f"P{i:03d}", planted_ch=1) for i in range(20)]
        items = build_aging_warnings(facts, plots, current_chapter=30)
        assert len(items) <= 5  # MAX_AGING_WARNINGS

    def test_empty_inputs_return_empty(self):
        items = build_aging_warnings([], [], current_chapter=30)
        assert len(items) == 0

    def test_overdue_plot_in_warning_text(self):
        plots = [_make_plot("P001", planted_ch=1, planned_resolve=10, title="神秘玉符")]
        items = build_aging_warnings([], plots, current_chapter=15)
        assert len(items) == 1
        assert "P001" in items[0].text
        assert "神秘玉符" in items[0].text
        assert "逾期" in items[0].text
