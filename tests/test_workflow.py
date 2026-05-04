"""Tests for workflow/conditions.py — routing logic."""

import pytest

from novel_factory.models.state import ChapterStatus
from novel_factory.workflow.conditions import (
    route_by_chapter_status,
    route_by_review_result,
    route_after_memory_curator,
    route_by_revision_type,
    route_after_agent,
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

    # P1: Safety gate tests — error/requires_human always routes to human_review
    @pytest.mark.parametrize("status", ["planned", "scripted", "drafted", "polished", "reviewed", "revision"])
    def test_requires_human_routes_to_human_review(self, status):
        state = {"chapter_status": status, "requires_human": True}
        assert route_by_chapter_status(state) == "human_review"

    @pytest.mark.parametrize("status", ["planned", "scripted", "drafted", "polished", "reviewed", "revision"])
    def test_error_routes_to_human_review(self, status):
        state = {"chapter_status": status, "error": "some failure"}
        assert route_by_chapter_status(state) == "human_review"

    # P1: Stale checkpoint recovery — DB status overrides stale state
    def test_drafted_with_stale_revision_gate_routes_to_polisher(self):
        """If checkpoint says revision but DB says drafted, must go to polisher."""
        state = {
            "chapter_status": "drafted",
            "quality_gate": {"revision_target": "author"},  # stale gate from old run
        }
        assert route_by_chapter_status(state) == "polisher"

    def test_polished_with_stale_revision_gate_routes_to_editor(self):
        """If checkpoint says revision but DB says polished, must go to editor."""
        state = {
            "chapter_status": "polished",
            "quality_gate": {"revision_target": "planner"},  # stale gate from old run
        }
        assert route_by_chapter_status(state) == "editor"


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

    def test_death_penalty_gate_after_agent_goes_to_revision(self):
        state = {
            "quality_gate": {
                "pass": False,
                "revision_target": "author",
                "death_penalty_fail": True,
            }
        }
        assert route_after_agent(state) == "revision_router"

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

    # P1: Full stale-revision-gate matrix — when DB status != REVISION, ignore gate
    @pytest.mark.parametrize(
        "db_status,expected",
        [
            (ChapterStatus.IDEA.value, "planner"),
            (ChapterStatus.OUTLINED.value, "planner"),
            (ChapterStatus.PLANNED.value, "planner"),
            (ChapterStatus.SCRIPTED.value, "author"),
            (ChapterStatus.DRAFTED.value, "polisher"),
            (ChapterStatus.POLISHED.value, "editor"),
            (ChapterStatus.REVIEW.value, "editor"),
            (ChapterStatus.REVIEWED.value, "publisher"),
            (ChapterStatus.PUBLISHED.value, "archive"),
            (ChapterStatus.BLOCKING.value, "human_review"),
        ],
    )
    def test_stale_revision_gate_routes_by_db_status(self, db_status, expected):
        """Stale revision gate must never override actual DB status."""
        state = {
            "chapter_status": db_status,
            "quality_gate": {"revision_target": "author"},  # stale gate
        }
        assert route_by_revision_type(state) == expected

    def test_stale_revision_gate_respects_drafted_status(self):
        state = {
            "chapter_status": ChapterStatus.DRAFTED.value,
            "quality_gate": {"revision_target": "author"},
        }
        assert route_by_revision_type(state) == "polisher"

    def test_stale_revision_gate_respects_polished_status(self):
        state = {
            "chapter_status": ChapterStatus.POLISHED.value,
            "quality_gate": {"revision_target": "planner"},
        }
        assert route_by_revision_type(state) == "editor"


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
