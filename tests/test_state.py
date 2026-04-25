"""Tests for models/state.py — ChapterStatus enum and FactoryState."""

import pytest

from novel_factory.models.state import (
    ChapterStatus,
    FactoryState,
    TRANSITIONS,
    is_valid_transition,
)


class TestChapterStatus:
    """Test ChapterStatus enum and state transitions."""

    def test_all_v1_statuses_exist(self):
        """v1 must have exactly these statuses per architecture doc 17.3."""
        expected = {
            "idea", "outlined", "planned", "scripted", "drafted",
            "polished", "review", "reviewed", "revision", "published", "blocking",
        }
        assert set(ChapterStatus.values()) == expected

    def test_happy_path_transition(self):
        """Test the complete happy path: planned -> ... -> published."""
        path = [
            ("planned", "scripted"),
            ("scripted", "drafted"),
            ("drafted", "polished"),
            ("polished", "review"),
            ("review", "reviewed"),
            ("reviewed", "published"),
        ]
        for src, dst in path:
            assert is_valid_transition(src, dst), f"{src} -> {dst} should be valid"

    def test_revision_can_go_to_author(self):
        assert is_valid_transition("revision", "drafted")

    def test_revision_can_go_to_polisher(self):
        assert is_valid_transition("revision", "polished")

    def test_revision_can_go_to_planner(self):
        assert is_valid_transition("revision", "planned")

    def test_blocking_has_no_transitions(self):
        assert not is_valid_transition("blocking", "planned")
        assert not is_valid_transition("blocking", "drafted")

    def test_invalid_transition(self):
        assert not is_valid_transition("planned", "published")  # skip steps
        assert not is_valid_transition("drafted", "reviewed")   # skip polish


class TestFactoryState:
    """Test FactoryState TypedDict creation."""

    def test_create_minimal_state(self):
        state: FactoryState = {
            "workflow_run_id": "test-001",
            "project_id": "proj-1",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }
        assert state["project_id"] == "proj-1"
        assert state["chapter_number"] == 1
        assert state["retry_count"] == 0

    def test_state_with_quality_gate(self):
        state: FactoryState = {
            "project_id": "proj-1",
            "chapter_number": 5,
            "chapter_status": "revision",
            "quality_gate": {
                "pass": False,
                "score": 75,
                "revision_target": "author",
            },
            "retry_count": 2,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }
        assert state["quality_gate"]["score"] == 75
        assert state["quality_gate"]["revision_target"] == "author"
