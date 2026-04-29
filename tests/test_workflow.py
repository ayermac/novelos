"""Tests for workflow/conditions.py — routing logic."""

import pytest

from novel_factory.models.state import ChapterStatus
from novel_factory.workflow.conditions import (
    route_by_chapter_status,
    route_by_review_result,
    route_after_memory_curator,
    route_by_revision_type,
)


class TestRouteByChapterStatus:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("planned", "screenwriter"),
            ("scripted", "author"),
            ("drafted", "polisher"),
            ("polished", "editor"),
            ("review", "editor"),
            ("reviewed", "publisher"),
            ("blocking", "human_review"),
            ("idea", "planner"),
            ("outlined", "planner"),
        ],
    )
    def test_happy_path_routing(self, status, expected):
        # v5.3.0: planned status requires has_instruction=True to route to screenwriter
        if status == "planned":
            state = {"chapter_status": status, "has_instruction": True}
        else:
            state = {"chapter_status": status}
        assert route_by_chapter_status(state) == expected

    def test_planned_without_instruction_routes_to_planner(self):
        """v5.3.0: planned status without instruction should route to planner."""
        state = {"chapter_status": "planned", "has_instruction": False}
        assert route_by_chapter_status(state) == "planner"

    def test_revision_routes_to_author_by_default(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "author"},
        }
        assert route_by_chapter_status(state) == "author"

    def test_revision_routes_to_polisher(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "polisher"},
        }
        assert route_by_chapter_status(state) == "polisher"

    def test_revision_routes_to_planner(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "planner"},
        }
        assert route_by_chapter_status(state) == "planner"


class TestRouteByReviewResult:
    def test_pass_goes_to_memory_curator_in_stub_mode(self):
        """v5.3.2: Stub mode routes to memory_curator after pass."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3, "llm_mode": "stub"}
        assert route_by_review_result(state) == "memory_curator"

    def test_pass_goes_to_memory_curator_in_real_mode(self):
        """v5.3.2: Real mode routes to memory_curator after pass."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3, "llm_mode": "real"}
        assert route_by_review_result(state) == "memory_curator"

    def test_pass_without_llm_mode_defaults_to_memory_curator(self):
        """v5.3.2: No llm_mode defaults to memory_curator after pass."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3}
        assert route_by_review_result(state) == "memory_curator"

    def test_fail_goes_to_revise(self):
        state = {"quality_gate": {"pass": False}, "retry_count": 1, "max_retries": 3}
        assert route_by_review_result(state) == "revise"

    def test_max_retries_goes_to_human(self):
        state = {"quality_gate": {"pass": False}, "retry_count": 3, "max_retries": 3}
        assert route_by_review_result(state) == "human_review"


class TestRouteByRevisionType:
    @pytest.mark.parametrize(
        "target,expected",
        [
            ("author", "author"),
            ("polisher", "polisher"),
            ("planner", "planner"),
        ],
    )
    def test_revision_target_routing(self, target, expected):
        state = {"quality_gate": {"revision_target": target}}
        assert route_by_revision_type(state) == expected

    def test_default_routes_to_author(self):
        state = {"quality_gate": {}}
        assert route_by_revision_type(state) == "author"


class TestRouteAfterMemoryCurator:
    """v5.3.2 closure: memory_curator failure routing."""

    def test_stub_mode_no_error_goes_to_publish(self):
        state = {"llm_mode": "stub"}
        assert route_after_memory_curator(state) == "publish"

    def test_real_mode_no_error_goes_to_awaiting_publish(self):
        state = {"llm_mode": "real"}
        assert route_after_memory_curator(state) == "awaiting_publish"

    def test_no_llm_mode_defaults_to_publish(self):
        state = {}
        assert route_after_memory_curator(state) == "publish"

    def test_requires_human_routes_to_human_review(self):
        """Real mode memory_curator failure blocks publish."""
        state = {"llm_mode": "real", "requires_human": True}
        assert route_after_memory_curator(state) == "human_review"

    def test_error_routes_to_human_review(self):
        """Error in state blocks publish regardless of mode."""
        state = {"llm_mode": "real", "error": "extraction failed"}
        assert route_after_memory_curator(state) == "human_review"

    def test_requires_human_in_stub_also_blocks(self):
        """Even in stub mode, requires_human=True routes to human_review."""
        state = {"llm_mode": "stub", "requires_human": True}
        assert route_after_memory_curator(state) == "human_review"
