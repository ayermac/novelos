"""Tests for workflow/conditions.py — routing logic."""

import pytest

from novel_factory.models.state import ChapterStatus
from novel_factory.workflow.conditions import (
    route_by_chapter_status,
    route_by_review_result,
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
    def test_pass_goes_to_publish_in_stub_mode(self):
        """v5.3.0: Stub mode (default) routes to publish after pass."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3, "llm_mode": "stub"}
        assert route_by_review_result(state) == "publish"

    def test_pass_goes_to_awaiting_publish_in_real_mode(self):
        """v5.3.0: Real mode routes to awaiting_publish, not publish."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3, "llm_mode": "real"}
        assert route_by_review_result(state) == "awaiting_publish"

    def test_pass_without_llm_mode_defaults_to_publish(self):
        """Backward compatibility: no llm_mode defaults to stub behavior."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3}
        assert route_by_review_result(state) == "publish"

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
