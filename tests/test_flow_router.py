"""Tests for FlowRouter — pure function routing.

v6.10.13: Tests for deterministic routing decisions.
"""

import pytest

from novel_factory.dispatch.flow_router import (
    FlowAction,
    Instruction,
    RouterState,
    describe_resume,
    route,
)


class TestRoute:
    """Test route() pure function."""

    def test_complete_phase(self):
        """Phase=Complete returns complete instruction."""
        state = RouterState(phase="complete", flow="writing")
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.COMPLETE

    def test_planning_phase_with_missing_foundation(self):
        """Phase!=Writing with missing foundation returns plan instruction."""
        state = RouterState(
            phase="genesis",
            flow="writing",
            foundation_missing=["characters", "world_settings"],
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.PLAN
        assert "characters" in result.task

    def test_planning_phase_no_missing(self):
        """Phase!=Writing without missing foundation returns None."""
        state = RouterState(phase="genesis", flow="writing", foundation_missing=[])
        result = route(state)
        assert result is None

    def test_pending_rewrites(self):
        """PendingRewrites returns rewrite instruction."""
        state = RouterState(
            phase="writing",
            flow="rewriting",
            pending_rewrites=[5, 7, 9],
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.REWRITE
        assert result.chapter == 5
        assert result.agent == "author"

    def test_pending_rewrites_polishing(self):
        """PendingRewrites with polishing flow returns polish instruction."""
        state = RouterState(
            phase="writing",
            flow="polishing",
            pending_rewrites=[5],
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.POLISH
        assert result.agent == "polisher"

    def test_pending_reviews(self):
        """PendingReviews returns process_review instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            pending_reviews=[{"chapter_number": 3}],
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.PROCESS_REVIEW
        assert result.chapter == 3

    def test_pending_memory_updates(self):
        """PendingMemoryUpdates returns apply_memory instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            pending_memory_updates=[{"id": "batch-123"}],
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.APPLY_MEMORY

    def test_reviewing_flow(self):
        """Flow=Reviewing returns None (let LLM handle)."""
        state = RouterState(phase="writing", flow="reviewing")
        result = route(state)
        assert result is None

    def test_steering_flow(self):
        """Flow=Steering returns None (let LLM handle)."""
        state = RouterState(phase="writing", flow="steering")
        result = route(state)
        assert result is None

    def test_arc_end_review_missing(self):
        """Arc end without review returns arc_review instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            layered=True,
            is_arc_end=True,
            has_arc_review=False,
            current_volume=1,
            current_arc=2,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.ARC_REVIEW
        assert result.agent == "editor"

    def test_arc_end_summary_missing(self):
        """Arc end with review but no summary returns arc_summary instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            layered=True,
            is_arc_end=True,
            has_arc_review=True,
            has_arc_summary=False,
            current_volume=1,
            current_arc=2,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.ARC_SUMMARY
        assert result.agent == "editor"

    def test_volume_end_summary_missing(self):
        """Volume end without summary returns volume_summary instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            layered=True,
            is_arc_end=True,
            is_volume_end=True,
            has_arc_review=True,
            has_arc_summary=True,
            has_volume_summary=False,
            current_volume=1,
            current_arc=2,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.VOLUME_SUMMARY
        assert result.agent == "editor"

    def test_arc_needs_expansion(self):
        """Arc needs expansion returns expand_arc instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            layered=True,
            is_arc_end=True,
            has_arc_review=True,
            has_arc_summary=True,
            needs_expansion=True,
            next_volume=2,
            next_arc=1,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.EXPAND_ARC
        assert result.agent == "architect"

    def test_volume_end_needs_decision(self):
        """Volume end needing decision returns next_volume instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            layered=True,
            is_arc_end=True,
            is_volume_end=True,
            has_arc_review=True,
            has_arc_summary=True,
            has_volume_summary=True,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.NEXT_VOLUME
        assert result.agent == "architect"

    def test_in_progress_chapter(self):
        """In-progress chapter returns continue instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            in_progress_chapter=5,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.CONTINUE_CHAPTER
        assert result.chapter == 5

    def test_normal_write_next(self):
        """Normal state returns write_next_chapter instruction."""
        state = RouterState(
            phase="writing",
            flow="writing",
            completed_chapters=[1, 2, 3],
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.WRITE_NEXT_CHAPTER
        assert result.chapter == 4
        assert result.agent == "author"

    def test_normal_write_first_chapter(self):
        """No completed chapters returns write chapter 1."""
        state = RouterState(
            phase="writing",
            flow="writing",
            completed_chapters=[],
            current_chapter=0,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.WRITE_NEXT_CHAPTER
        assert result.chapter == 1

    def test_priority_order(self):
        """Higher priority rules take precedence."""
        # Pending rewrites should take precedence over arc end
        state = RouterState(
            phase="writing",
            flow="rewriting",
            pending_rewrites=[5],
            layered=True,
            is_arc_end=True,
            has_arc_review=False,
        )
        result = route(state)
        assert result is not None
        assert result.action == FlowAction.REWRITE
        assert result.chapter == 5


class TestDescribeResume:
    """Test describe_resume() pure function."""

    def test_complete(self):
        state = RouterState(phase="complete", flow="writing")
        assert describe_resume(state) == "创作已完成"

    def test_planning_phase(self):
        state = RouterState(phase="genesis", flow="writing")
        assert "规划阶段" in describe_resume(state)

    def test_pending_steer(self):
        state = RouterState(
            phase="writing",
            flow="writing",
            pending_steer="修改主角",
        )
        assert "用户干预" in describe_resume(state)

    def test_pending_rewrites(self):
        state = RouterState(
            phase="writing",
            flow="rewriting",
            pending_rewrites=[5, 7],
        )
        assert "重写" in describe_resume(state)
        assert "2 章" in describe_resume(state)

    def test_reviewing(self):
        state = RouterState(phase="writing", flow="reviewing")
        assert "审阅中断" in describe_resume(state)

    def test_in_progress(self):
        state = RouterState(
            phase="writing",
            flow="writing",
            in_progress_chapter=5,
        )
        assert "第 5 章进行中" in describe_resume(state)

    def test_arc_end_review_missing(self):
        state = RouterState(
            phase="writing",
            flow="writing",
            layered=True,
            is_arc_end=True,
            has_arc_review=False,
            current_volume=1,
            current_arc=2,
        )
        assert "弧末评审" in describe_resume(state)

    def test_normal_resume(self):
        state = RouterState(
            phase="writing",
            flow="writing",
            completed_chapters=[1, 2, 3],
        )
        assert "第 4 章继续" in describe_resume(state)


class TestInstruction:
    """Test Instruction dataclass."""

    def test_format_message_with_agent(self):
        inst = Instruction(
            action=FlowAction.WRITE_NEXT_CHAPTER,
            chapter=5,
            agent="author",
            task="写第 5 章",
            reason="续写下一章",
        )
        msg = inst.format_message()
        assert "author" in msg
        assert "写第 5 章" in msg
        assert "续写下一章" in msg

    def test_format_message_without_agent(self):
        inst = Instruction(
            action=FlowAction.COMPLETE,
            task="创作已完成",
            reason="Phase=Complete",
        )
        msg = inst.format_message()
        assert "创作已完成" in msg
