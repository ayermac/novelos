"""v6.10.14 S5: Pull recall channel for proactive entity-based fact retrieval."""

from __future__ import annotations

import pytest

from novel_factory.context.recall_channel import (
    MAX_PULL_ITEMS,
    extract_pull_entities,
    pull_facts_for_entities,
    build_pull_context,
)


def _make_fact(fact_key: str, subject: str, value: str = "test", source_chapter: int = 5) -> dict:
    return {
        "fact_key": fact_key,
        "fact_type": "event",
        "subject": subject,
        "attribute": "value",
        "value_json": value,
        "source_chapter": source_chapter,
        "confidence": 1.0,
    }


class TestExtractPullEntities:
    def test_extracts_from_key_events(self):
        brief = {"key_events": "张三和李四在玄天宗修炼"}
        entities = extract_pull_entities(brief)
        assert "张三" in entities
        assert "李四" in entities
        assert "玄天宗" in entities

    def test_extracts_from_objective(self):
        brief = {"objective": "王五突破境界"}
        entities = extract_pull_entities(brief)
        assert "王五" in entities

    def test_extracts_from_required_events_list(self):
        brief = {"required_events": ["张三出场", "李四受伤"]}
        entities = extract_pull_entities(brief)
        assert "张三" in entities
        assert "李四" in entities

    def test_none_brief_returns_empty(self):
        assert extract_pull_entities(None) == set()

    def test_empty_brief_returns_empty(self):
        assert extract_pull_entities({}) == set()


class TestPullFactsForEntities:
    def test_pulls_by_subject_match(self):
        facts = [
            _make_fact("f1", "张三", "修炼突破"),
            _make_fact("f2", "路人甲", "出场"),
        ]
        result = pull_facts_for_entities(facts, {"张三"}, current_chapter=10)
        assert len(result) == 1
        assert result[0]["subject"] == "张三"

    def test_pulls_by_value_match(self):
        facts = [
            _make_fact("f1", "道具", "玉符剩余3次"),
            _make_fact("f2", "路人甲", "出场"),
        ]
        result = pull_facts_for_entities(facts, {"玉符"}, current_chapter=10)
        assert len(result) == 1
        assert "玉符" in result[0]["value_json"]

    def test_respects_max_limit(self):
        facts = [_make_fact(f"f{i}", "张三", f"event_{i}") for i in range(20)]
        result = pull_facts_for_entities(facts, {"张三"}, current_chapter=10)
        assert len(result) <= MAX_PULL_ITEMS

    def test_excludes_future_chapters(self):
        facts = [
            _make_fact("f1", "张三", "event", source_chapter=15),
        ]
        result = pull_facts_for_entities(facts, {"张三"}, current_chapter=10)
        assert len(result) == 0  # source_chapter > current_chapter

    def test_empty_entities_returns_empty(self):
        facts = [_make_fact("f1", "张三")]
        result = pull_facts_for_entities(facts, set(), current_chapter=10)
        assert len(result) == 0

    def test_deduplicates_by_fact_key(self):
        facts = [
            _make_fact("f1", "张三", "event1"),
            _make_fact("f1", "张三", "event2"),  # same key
        ]
        result = pull_facts_for_entities(facts, {"张三"}, current_chapter=10)
        assert len(result) == 1


class TestBuildPullContext:
    def test_returns_context_items(self):
        facts = [_make_fact("f1", "张三", "修炼突破")]
        brief = {"key_events": "张三修炼"}
        items = build_pull_context(facts, brief, current_chapter=10)
        assert len(items) == 1
        assert items[0].kind == "pull_recall"
        assert "主动召回" in items[0].text

    def test_none_brief_returns_empty(self):
        facts = [_make_fact("f1", "张三")]
        items = build_pull_context(facts, None, current_chapter=10)
        assert len(items) == 0

    def test_no_matching_entities_returns_empty(self):
        facts = [_make_fact("f1", "路人甲")]
        brief = {"key_events": "张三修炼"}
        items = build_pull_context(facts, brief, current_chapter=10)
        assert len(items) == 0

    def test_numeric_state_exempt_from_truncation(self):
        long_value = "x" * 300
        facts = [
            {
                "fact_key": "f1",
                "fact_type": "numeric_state",
                "subject": "张三",
                "attribute": "余额",
                "value_json": long_value,
                "source_chapter": 5,
                "confidence": 1.0,
            }
        ]
        brief = {"key_events": "张三修炼"}
        items = build_pull_context(facts, brief, current_chapter=10)
        assert len(items) == 1
        # Should not be truncated
        assert "..." not in items[0].text
