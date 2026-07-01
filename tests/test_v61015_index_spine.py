"""v6.10.15 S10: Index spine — compact fact directory for megafiction."""

from __future__ import annotations

import pytest

from novel_factory.context.index_spine import (
    build_index_spine,
    MAX_INDEX_ROWS,
    MAX_INDEX_CHARS,
)


def _make_fact(fact_key, fact_type, subject, attribute="attr", source_chapter=1):
    return {
        "fact_key": fact_key,
        "fact_type": fact_type,
        "subject": subject,
        "attribute": attribute,
        "value_json": "test",
        "source_chapter": source_chapter,
    }


class TestBuildIndexSpine:
    def test_returns_context_item(self):
        facts = [_make_fact("f1", "event", "张三", source_chapter=10)]
        items = build_index_spine(facts, current_chapter=15)
        assert len(items) == 1
        assert items[0].kind == "index_spine"
        assert "事实索引脊柱" in items[0].text

    def test_empty_facts_returns_empty(self):
        items = build_index_spine([], current_chapter=10)
        assert len(items) == 0

    def test_numeric_state_excluded(self):
        """numeric_state facts should be excluded from index (shown in mandatory bucket)."""
        facts = [
            _make_fact("f1", "numeric_state", "hp", source_chapter=10),
            _make_fact("f2", "event", "张三", source_chapter=10),
        ]
        items = build_index_spine(facts, current_chapter=15)
        assert len(items) == 1
        assert "张三" in items[0].text
        assert "hp" not in items[0].text

    def test_deduplication(self):
        """Facts with same subject.attribute should be deduplicated, keeping latest."""
        facts = [
            _make_fact("f1", "event", "张三", attribute="修为", source_chapter=5),
            _make_fact("f2", "event", "张三", attribute="修为", source_chapter=15),
        ]
        items = build_index_spine(facts, current_chapter=20)
        assert len(items) == 1
        # Should show the more recent one (age = 20 - 15 = 5 chapters ago)
        assert "5章前" in items[0].text
        assert "15章前" not in items[0].text

    def test_age_tag(self):
        """Age tag should show how many chapters ago the fact was set."""
        facts = [_make_fact("f1", "event", "张三", source_chapter=10)]
        items = build_index_spine(facts, current_chapter=15)
        assert "5章前" in items[0].text

    def test_current_chapter_age_tag(self):
        """Facts from current chapter should show (本章)."""
        facts = [_make_fact("f1", "event", "张三", source_chapter=15)]
        items = build_index_spine(facts, current_chapter=15)
        assert "本章" in items[0].text

    def test_grouped_by_fact_type(self):
        """Index should group facts by type with labels."""
        facts = [
            _make_fact("f1", "event", "事件A", source_chapter=10),
            _make_fact("f2", "item", "道具B", source_chapter=10),
            _make_fact("f3", "relationship", "关系C", source_chapter=10),
        ]
        items = build_index_spine(facts, current_chapter=15)
        assert len(items) == 1
        text = items[0].text
        assert "[事件]" in text
        assert "[道具]" in text
        assert "[关系]" in text

    def test_max_index_rows_limit(self):
        """Index should not exceed MAX_INDEX_ROWS."""
        facts = [_make_fact(f"f{i}", "event", f"subj_{i}", source_chapter=1) for i in range(500)]
        items = build_index_spine(facts, current_chapter=100)
        assert len(items) == 1
        text = items[0].text
        assert "还有" in text or "未列出" in text

    def test_max_index_chars_limit(self):
        """Index should not exceed MAX_INDEX_CHARS."""
        # Create facts with very long subject names
        facts = [
            _make_fact(f"f{i}", "event", "张" * 50, source_chapter=1)
            for i in range(200)
        ]
        items = build_index_spine(facts, current_chapter=100)
        assert len(items) == 1
        assert len(items[0].text) <= MAX_INDEX_CHARS + 200  # allow header overhead

    def test_megafiction_scenario(self):
        """Simulate 1000-chapter project with 500 deduplicated facts."""
        facts = [
            _make_fact(f"f{i}", "event", f"伏笔_{i}", source_chapter=i)
            for i in range(1, 501)
        ]
        items = build_index_spine(facts, current_chapter=1000)
        assert len(items) == 1
        # Should be capped at MAX_INDEX_ROWS
        text = items[0].text
        lines = [l for l in text.split("\n") if l.strip().startswith("- ")]
        assert len(lines) <= MAX_INDEX_ROWS
        # Should indicate truncation
        assert "未列出" in text
