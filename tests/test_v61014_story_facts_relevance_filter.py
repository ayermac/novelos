"""v6.10.14 S2+F8: Story facts relevance filtering and numeric_state truncation exemption.

Tests that:
- With a brief, only relevant facts (entity match + numeric_state + aged) are kept
- Without a brief, all facts are returned (no regression)
- numeric_state facts are exempt from 200-char value truncation
- Entity extraction works from brief fields
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from novel_factory.agent_runtime.context_builder import AgentContextBuilder, ContextItem


def _make_repo(
    facts: list[dict] | None = None,
    instruction: dict | None = None,
    characters: list[dict] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.list_story_facts.return_value = facts or []
    repo.get_instruction.return_value = instruction
    repo.get_characters.return_value = characters or []
    return repo


def _make_fact(
    fact_key: str,
    fact_type: str,
    subject: str,
    attribute: str = "",
    value: str = "test",
    source_chapter: int = 1,
) -> dict:
    return {
        "fact_key": fact_key,
        "fact_type": fact_type,
        "subject": subject,
        "attribute": attribute,
        "value_json": value,
        "source_chapter": source_chapter,
        "confidence": 1.0,
    }


def test_relevance_filter_keeps_numeric_state():
    """numeric_state facts should always be kept regardless of brief."""
    facts = [
        _make_fact("f1", "numeric_state", "玉符", "剩余次数", "3", source_chapter=5),
        _make_fact("f2", "event", "路人甲", "出场", "chapter 3", source_chapter=3),
    ]
    brief = {"key_events": "张三修炼", "project_id": "p1"}
    repo = _make_repo(facts=facts, instruction=brief, characters=[{"name": "张三"}])
    builder = AgentContextBuilder(repo)

    items = builder._story_facts_context("p1", 10, brief)
    subjects = [it.text.split(".")[0] for it in items]
    assert "玉符" in subjects, "numeric_state must be kept"


def test_relevance_filter_keeps_entity_match():
    """Facts whose subject matches a brief entity should be kept."""
    facts = [
        _make_fact("f1", "event", "张三", "修炼", "突破", source_chapter=8),
        _make_fact("f2", "event", "路人甲", "出场", "chapter 3", source_chapter=3),
    ]
    brief = {"key_events": "张三修炼突破", "project_id": "p1"}
    repo = _make_repo(facts=facts, instruction=brief, characters=[{"name": "张三"}])
    builder = AgentContextBuilder(repo)

    items = builder._story_facts_context("p1", 10, brief)
    texts = [it.text for it in items]
    assert any("张三" in t for t in texts), "Entity-matched fact must be kept"
    assert not any("路人甲" in t for t in texts), "Irrelevant fact should be filtered out"


def test_relevance_filter_keeps_aged_facts():
    """Facts older than the aging threshold should be kept as fallback."""
    facts = [
        _make_fact("f1", "event", "旧伏笔", "埋设", "mysterious_item", source_chapter=1),
    ]
    brief = {"key_events": "张三修炼", "project_id": "p1"}
    repo = _make_repo(facts=facts, instruction=brief, characters=[{"name": "张三"}])
    builder = AgentContextBuilder(repo)

    # Chapter 25 → age = 24 > 20 threshold
    items = builder._story_facts_context("p1", 25, brief)
    texts = [it.text for it in items]
    assert any("旧伏笔" in t for t in texts), "Aged fact must be kept"


def test_relevance_filter_no_brief_returns_all():
    """Without a brief, all facts should be returned (no regression)."""
    facts = [
        _make_fact("f1", "event", "张三", "修炼", "突破", source_chapter=8),
        _make_fact("f2", "event", "路人甲", "出场", "chapter 3", source_chapter=3),
        _make_fact("f3", "numeric_state", "玉符", "剩余次数", "3", source_chapter=5),
    ]
    repo = _make_repo(facts=facts, instruction=None, characters=[])
    builder = AgentContextBuilder(repo)

    items = builder._story_facts_context("p1", 10, brief=None)
    assert len(items) == 3, "All facts should be returned when brief is None"


def test_numeric_state_exempt_from_truncation():
    """numeric_state facts should not be truncated at 200 chars."""
    long_value = '{"key": "test", "value": "' + "x" * 300 + '", "evidence": "long evidence"}'
    facts = [
        _make_fact("f1", "numeric_state", "玉符", "剩余次数", long_value, source_chapter=5),
    ]
    repo = _make_repo(facts=facts, instruction=None, characters=[])
    builder = AgentContextBuilder(repo)

    items = builder._story_facts_context("p1", 10, brief=None)
    assert len(items) == 1
    # The full value should be present (no "..." truncation)
    assert "..." not in items[0].text or "x" * 250 in items[0].text, (
        "numeric_state value should not be truncated"
    )


def test_non_numeric_state_truncated():
    """Non-numeric_state facts should still be truncated at 200 chars."""
    long_value = "x" * 300
    facts = [
        _make_fact("f1", "event", "张三", "描述", long_value, source_chapter=5),
    ]
    repo = _make_repo(facts=facts, instruction=None, characters=[])
    builder = AgentContextBuilder(repo)

    items = builder._story_facts_context("p1", 10, brief=None)
    assert len(items) == 1
    assert "..." in items[0].text, "Non-numeric fact should be truncated"


def test_extract_entities_from_brief():
    """_extract_entities should pull CJK names from brief fields."""
    brief = {
        "key_events": "张三和李四在玄天宗修炼",
        "objective": "王五突破境界",
        "project_id": "p1",
    }
    repo = _make_repo(
        instruction=brief,
        characters=[{"name": "张三"}, {"name": "李四"}],
    )
    builder = AgentContextBuilder(repo)

    entities = builder._extract_entities(brief)
    assert "张三" in entities
    assert "李四" in entities
    assert "王五" in entities
    assert "玄天宗" in entities  # CJK name-like token


def test_brief_cache_avoids_repeated_lookups():
    """_load_brief should cache the result to avoid repeated DB calls."""
    repo = _make_repo(instruction={"key_events": "test", "project_id": "p1"})
    builder = AgentContextBuilder(repo)

    brief1 = builder._load_brief("p1", 5)
    brief2 = builder._load_brief("p1", 5)

    assert brief1 is brief2
    # repo.get_instruction should only be called once due to caching
    assert repo.get_instruction.call_count == 1
