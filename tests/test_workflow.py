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
        state = {"chapter_status": status}
        assert route_by_chapter_status(state) == expected

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
    def test_pass_goes_to_publish(self):
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
