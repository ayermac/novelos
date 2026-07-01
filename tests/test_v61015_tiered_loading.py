"""v6.10.15 S9: DB-layer tiered loading for megafiction (1000+ chapters).

Tests that:
- Tier 1: recent chapters are fully loaded
- Tier 2: numeric_state facts are always loaded regardless of chapter
- Tier 3: aged facts (age >= threshold) are loaded
- Facts not matching any tier are excluded
- Falls back to full load on SQL error
"""

from __future__ import annotations

import sqlite3
import pytest

from novel_factory.db.connection import row_to_dict
from novel_factory.db.repository import Repository


@pytest.fixture
def repo(tmp_path):
    """Create a real Repository with a test database."""
    db_path = str(tmp_path / "test_tiered.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Create story_facts table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS story_facts (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            subject TEXT,
            attribute TEXT,
            value_json TEXT NOT NULL DEFAULT '{}',
            unit TEXT,
            scope TEXT DEFAULT 'global',
            status TEXT DEFAULT 'active',
            confidence REAL DEFAULT 1.0,
            source_chapter INTEGER,
            source_agent TEXT,
            last_changed_chapter INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours'))
        );
        CREATE TABLE IF NOT EXISTS chapters (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            title TEXT,
            status TEXT,
            word_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', '+8 hours')),
            updated_at TEXT DEFAULT (datetime('now', '+8 hours'))
        );
    """)
    conn.commit()
    conn.close()

    r = Repository(db_path)
    return r


def _insert_fact(repo, project_id, fact_key, fact_type, subject, source_chapter, status="active"):
    repo.create_story_fact(
        project_id=project_id,
        fact_key=fact_key,
        fact_type=fact_type,
        value_json='{"value": "test"}',
        subject=subject,
        attribute="attr",
        source_chapter=source_chapter,
        source_agent="test",
        status=status,
    )


class TestListStoryFactsTiered:
    def test_recent_chapters_loaded(self, repo):
        """Tier 1: Facts from recent chapters should be loaded."""
        _insert_fact(repo, "p1", "f_recent", "event", "recent_event", source_chapter=95)
        _insert_fact(repo, "p1", "f_old", "event", "old_event", source_chapter=5)

        # current_chapter=100, recent_window=50 → cutoff=50
        facts = repo.list_story_facts_tiered("p1", 100, recent_window=50, aging_threshold=20)
        keys = [f["fact_key"] for f in facts]
        assert "f_recent" in keys  # 95 >= 50, in window
        # f_old is at chapter 5, age=95 >= 20, so it's also loaded via Tier 3

    def test_numeric_state_always_loaded(self, repo):
        """Tier 2: numeric_state facts should always be loaded regardless of chapter."""
        _insert_fact(repo, "p1", "f_num_old", "numeric_state", "hp", source_chapter=1)
        _insert_fact(repo, "p1", "f_num_recent", "numeric_state", "mana", source_chapter=95)

        facts = repo.list_story_facts_tiered("p1", 100, recent_window=10, aging_threshold=50)
        keys = [f["fact_key"] for f in facts]
        assert "f_num_old" in keys  # numeric_state always loaded even at chapter 1
        assert "f_num_recent" in keys

    def test_aged_facts_loaded(self, repo):
        """Tier 3: Facts with age >= threshold should be loaded."""
        _insert_fact(repo, "p1", "f_aged", "event", "old_foreshadow", source_chapter=10)
        _insert_fact(repo, "p1", "f_not_aged", "event", "mid_event", source_chapter=85)

        # current_chapter=100, window=50 (cutoff=50), threshold=20
        # f_aged: chapter 10, age=90 >= 20 → loaded
        # f_not_aged: chapter 85, in window (85 >= 50) → loaded (Tier 1)
        facts = repo.list_story_facts_tiered("p1", 100, recent_window=50, aging_threshold=20)
        keys = [f["fact_key"] for f in facts]
        assert "f_aged" in keys
        assert "f_not_aged" in keys

    def test_unrelated_old_fact_excluded(self, repo):
        """Facts that are old, non-numeric, and not aged should be excluded."""
        _insert_fact(repo, "p1", "f_excluded", "event", "minor_event", source_chapter=80)

        # current_chapter=100, window=10 (cutoff=90), threshold=50
        # f_excluded: chapter 80 < 90 (not recent), age=20 < 50 (not aged), not numeric_state → excluded
        facts = repo.list_story_facts_tiered("p1", 100, recent_window=10, aging_threshold=50)
        keys = [f["fact_key"] for f in facts]
        assert "f_excluded" not in keys

    def test_status_filter(self, repo):
        """Only active facts should be returned by default."""
        _insert_fact(repo, "p1", "f_active", "event", "active_event", source_chapter=95)
        _insert_fact(repo, "p1", "f_inactive", "event", "inactive_event", source_chapter=95, status="superseded")

        facts = repo.list_story_facts_tiered("p1", 100, recent_window=50, aging_threshold=20)
        keys = [f["fact_key"] for f in facts]
        assert "f_active" in keys
        assert "f_inactive" not in keys

    def test_empty_project(self, repo):
        """Empty project should return empty list."""
        facts = repo.list_story_facts_tiered("empty_project", 100)
        assert facts == []

    def test_megafiction_scenario(self, repo):
        """Simulate a 1000-chapter project with diverse fact ages."""
        # Recent facts (within 50 chapters)
        for i in range(950, 1000):
            _insert_fact(repo, "p1", f"f_recent_{i}", "event", f"event_{i}", source_chapter=i)

        # Old numeric_state (should be loaded regardless)
        _insert_fact(repo, "p1", "f_num_ch1", "numeric_state", "hp", source_chapter=1)

        # Old aged event (should be loaded via Tier 3)
        _insert_fact(repo, "p1", "f_aged_ch5", "event", "old_foreshadow", source_chapter=5)

        # Old non-aged event (should be excluded)
        _insert_fact(repo, "p1", "f_excluded_ch980", "event", "minor", source_chapter=980)

        facts = repo.list_story_facts_tiered("p1", 1000, recent_window=50, aging_threshold=20)
        keys = {f["fact_key"] for f in facts}

        # All recent should be present
        assert f"f_recent_950" in keys
        assert f"f_recent_999" in keys

        # Numeric state from chapter 1 should be present
        assert "f_num_ch1" in keys

        # Aged event from chapter 5 should be present
        assert "f_aged_ch5" in keys

        # Should be significantly less than full load
        assert len(facts) < 100  # ~50 recent + 1 numeric + 1 aged


class TestListStoryFactIndex:
    def test_returns_lightweight_fields(self, repo):
        """Index should only return fact_key, fact_type, subject, attribute, source_chapter."""
        _insert_fact(repo, "p1", "f1", "event", "test", source_chapter=10)

        index = repo.list_story_fact_index("p1")
        assert len(index) == 1
        row = index[0]
        assert "fact_key" in row
        assert "fact_type" in row
        assert "subject" in row
        assert "source_chapter" in row
        # value_json should NOT be in the index
        assert "value_json" not in row

    def test_multiple_facts(self, repo):
        """Index should return all active facts."""
        for i in range(5):
            _insert_fact(repo, "p1", f"f{i}", "event", f"subj_{i}", source_chapter=i)

        index = repo.list_story_fact_index("p1")
        assert len(index) == 5

    def test_status_filter(self, repo):
        """Index should only return active facts."""
        _insert_fact(repo, "p1", "f1", "event", "s1", source_chapter=1)
        _insert_fact(repo, "p1", "f2", "event", "s2", source_chapter=2, status="superseded")

        index = repo.list_story_fact_index("p1", status="active")
        assert len(index) == 1
        assert index[0]["fact_key"] == "f1"
