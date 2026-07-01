"""v6.10.14 S6: Continuity checker full-scope validation set.

Tests that continuity_checker._build_context now includes ALL active
story_facts as a full validation ledger, not just [from, to] range.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from novel_factory.agents.continuity_checker import ContinuityCheckerAgent


def _make_checker(
    chapters=None,
    states=None,
    plots=None,
    instructions=None,
    facts=None,
) -> ContinuityCheckerAgent:
    repo = MagicMock()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = chapters or []
    conn.execute.return_value.fetchone.return_value = None
    repo._conn.return_value = conn
    repo.get_chapter_state.return_value = None
    repo.get_pending_plots.return_value = plots or []
    repo.get_instruction.return_value = None
    repo.list_story_facts.return_value = facts or []
    checker = ContinuityCheckerAgent.__new__(ContinuityCheckerAgent)
    checker.repo = repo
    checker.agent_id = "continuity_checker"
    return checker


def test_build_context_includes_full_facts_ledger():
    """_build_context should include ALL active story_facts, not just [from,to] range."""
    facts = [
        {
            "fact_key": "f1",
            "fact_type": "event",
            "subject": "主角",
            "attribute": "左臂",
            "value_json": "已断",
            "source_chapter": 5,
            "confidence": 1.0,
        },
        {
            "fact_key": "f2",
            "fact_type": "numeric_state",
            "subject": "玉符",
            "attribute": "剩余次数",
            "value_json": "3",
            "source_chapter": 10,
            "confidence": 1.0,
        },
    ]
    checker = _make_checker(facts=facts)
    # chapters in range
    checker.repo._conn.return_value.execute.return_value.fetchall.return_value = [
        {"chapter_number": 15, "title": "ch15", "status": "published", "word_count": 3000},
    ]

    result = checker._build_context("p1", from_chapter=15, to_chapter=15)

    assert "全量事实账本" in result
    assert "主角" in result
    assert "玉符" in result


def test_build_context_includes_validation_directive():
    """_build_context should include the expanded validation directive."""
    facts = [
        {
            "fact_key": "f1",
            "fact_type": "event",
            "subject": "test",
            "attribute": "val",
            "value_json": "test",
            "source_chapter": 1,
            "confidence": 1.0,
        }
    ]
    checker = _make_checker(facts=facts)
    checker.repo._conn.return_value.execute.return_value.fetchall.return_value = [
        {"chapter_number": 10, "title": "ch10", "status": "published", "word_count": 3000},
    ]

    result = checker._build_context("p1", from_chapter=10, to_chapter=10)

    assert "校验职责扩展" in result
    assert "fact_contradiction" in result


def test_build_context_no_facts_skips_ledger():
    """When there are no active facts, the ledger section should be omitted."""
    checker = _make_checker(facts=[])
    checker.repo._conn.return_value.execute.return_value.fetchall.return_value = [
        {"chapter_number": 10, "title": "ch10", "status": "published", "word_count": 3000},
    ]

    result = checker._build_context("p1", from_chapter=10, to_chapter=10)

    assert "全量事实账本" not in result


def test_build_context_deduplicates_facts():
    """Facts should be deduplicated by subject.attribute, keeping latest."""
    facts = [
        {
            "fact_key": "f1",
            "fact_type": "numeric_state",
            "subject": "玉符",
            "attribute": "剩余次数",
            "value_json": "5",
            "source_chapter": 3,
            "confidence": 1.0,
        },
        {
            "fact_key": "f2",
            "fact_type": "numeric_state",
            "subject": "玉符",
            "attribute": "剩余次数",
            "value_json": "3",
            "source_chapter": 10,
            "confidence": 1.0,
        },
    ]
    checker = _make_checker(facts=facts)
    checker.repo._conn.return_value.execute.return_value.fetchall.return_value = [
        {"chapter_number": 15, "title": "ch15", "status": "published", "word_count": 3000},
    ]

    result = checker._build_context("p1", from_chapter=15, to_chapter=15)

    # Should only have the latest value (3), not the old one (5)
    assert "3" in result
    assert result.count("玉符.剩余次数") == 1
