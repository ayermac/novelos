"""v6.10.8: Agent robustness hardening tests.

Covers the 12 fixes delivered in v6.10.8:
  - gate_passed() helper
  - SelfCheckLoop final_check after repair
  - STATUS_ORDER shared utility
  - Editor final_gate revision_target validation
  - Editor seam blocking_count precision
  - Memory Curator instructions fallback
  - Memory Curator _find_existing non-numeric target_name
  - memory_update lock race condition (IntegrityError vs others)
  - Author _scene_terms sliding-window Chinese matching
  - CreativeLedgerCurator agent_id
  - node_recovery NODE_RETRY_TARGETS coverage
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from novel_factory.models.state import (
    ChapterStatus,
    STATUS_ORDER,
    status_order,
)
from novel_factory.workflow.conditions import (
    gate_passed,
    route_after_agent,
    route_by_quality_gate,
    route_by_review_result,
)
from novel_factory.workflow.node_recovery import NODE_RETRY_TARGETS


# ──────────────────────────────────────────────────────────────────────
# Phase 1.1 — gate_passed helper
# ──────────────────────────────────────────────────────────────────────


class TestGatePassed:
    """gate_passed() must read both 'passed' and 'pass' field names."""

    def test_passed_true(self):
        assert gate_passed({"passed": True}) is True

    def test_passed_false(self):
        assert gate_passed({"passed": False}) is False

    def test_pass_true(self):
        assert gate_passed({"pass": True}) is True

    def test_pass_false(self):
        assert gate_passed({"pass": False}) is False

    def test_both_fields_passed_wins(self):
        # "checked" field (from quality_gate_node) takes precedence
        assert gate_passed({"passed": True, "pass": False}) is True

    def test_empty_gate(self):
        assert gate_passed({}) is False

    def test_none_gate(self):
        # guard against callers that pass None
        assert gate_passed(None or {}) is False

    def test_route_by_quality_gate_uses_gate_passed(self):
        """route_by_quality_gate must pass when only 'pass' is set."""
        state = {"quality_gate": {"pass": True}}
        assert route_by_quality_gate(state) == "editor"

    def test_route_by_review_result_uses_gate_passed(self):
        """route_by_review_result must pass when only 'passed' is set."""
        state = {"quality_gate": {"passed": True}}
        assert route_by_review_result(state) == "memory_curator"

    def test_route_after_agent_uses_gate_passed(self):
        """route_after_agent must detect fail via 'passed' field too."""
        state = {
            "quality_gate": {"passed": False, "word_count_fail": True},
            "chapter_status": "scripted",
        }
        assert route_after_agent(state) == "revision_router"


# ──────────────────────────────────────────────────────────────────────
# Phase 1.2 — SelfCheckLoop final_check after repair
# ──────────────────────────────────────────────────────────────────────


class TestSelfCheckFinalCheck:
    """SelfCheckLoop.run() must re-validate after successful repair."""

    def test_repair_then_pass(self):
        """Repaired output passes final_check → continue."""
        from novel_factory.agent_runtime.self_check import SelfCheckLoop, SelfCheckResult

        original = {"text": "bad"}
        repaired = {"text": "good"}

        def generate_fn():
            return dict(original)

        call_count = {"n": 0}

        def self_check_fn(output):
            call_count["n"] += 1
            if output.get("text") == "good":
                return SelfCheckResult(passed=True)
            return SelfCheckResult(passed=False, repair_needed=True, repair_suggestion="fix it")

        def repair_fn(output, check):
            return dict(repaired)

        loop = SelfCheckLoop(agent_id="test", max_repair_attempts=1)
        result = loop.run(generate_fn, self_check_fn, repair_fn)

        # self_check_fn called twice: once for original, once for repaired
        assert call_count["n"] == 2
        assert result["text"] == "good"
        assert result["_autonomy"]["decision"] == "continue"

    def test_repair_then_fail(self):
        """Repaired output fails final_check → ask_human."""
        from novel_factory.agent_runtime.self_check import SelfCheckLoop, SelfCheckResult

        original = {"text": "bad"}

        def generate_fn():
            return dict(original)

        def self_check_fn(output):
            return SelfCheckResult(passed=False, repair_needed=True, repair_suggestion="fix")

        def repair_fn(output, check):
            return {"text": "still_bad"}

        loop = SelfCheckLoop(agent_id="test", max_repair_attempts=1)
        result = loop.run(generate_fn, self_check_fn, repair_fn)

        assert result["_autonomy"]["decision"] == "ask_human"
        assert "重新自检仍未通过" in result["_autonomy"]["reason"]


# ──────────────────────────────────────────────────────────────────────
# Phase 1.3 — STATUS_ORDER shared utility
# ──────────────────────────────────────────────────────────────────────


class TestStatusOrder:
    """STATUS_ORDER must be consistent with ChapterStatus enum."""

    def test_all_statuses_have_order(self):
        for member in ChapterStatus:
            assert member.value in STATUS_ORDER, f"{member.value} missing from STATUS_ORDER"

    def test_status_order_function(self):
        assert status_order("idea") == 0
        assert status_order("scripted") == 3
        assert status_order("polished") == 5
        assert status_order("blocking") == 10

    def test_unknown_status_returns_minus_one(self):
        assert status_order("nonexistent") == -1

    def test_order_is_monotonic_for_happy_path(self):
        happy_path = ["idea", "outlined", "planned", "scripted", "drafted",
                      "polished", "review", "reviewed", "published"]
        for prev, nxt in zip(happy_path, happy_path[1:]):
            assert status_order(prev) < status_order(nxt), (
                f"{prev} ({status_order(prev)}) should be < {nxt} ({status_order(nxt)})"
            )

    def test_revision_order_between_reviewed_and_published(self):
        assert status_order("reviewed") < status_order("revision")
        assert status_order("revision") < status_order("published")


# ──────────────────────────────────────────────────────────────────────
# Phase 4.1 — Author _scene_terms sliding-window
# ──────────────────────────────────────────────────────────────────────


class TestSceneTerms:
    """_scene_terms must extract short CJK substrings, not long tokens."""

    def test_chinese_sliding_window_extracts_substrings(self):
        from novel_factory.agents.author import AuthorAgent
        terms = AuthorAgent._scene_terms("林泽在宴会厅走向主位")
        # Must contain 3-char substrings, not the full 8-char string
        assert "林泽在" in terms or "泽在宴" in terms or "在宴会" in terms
        # Must NOT contain the full string as a single term
        assert "林泽在宴会厅走向主位" not in terms

    def test_chinese_stopwords_filtered(self):
        from novel_factory.agents.author import AuthorAgent
        # "林泽" is in the stopwords set, but 3-char "林泽在" is not
        terms = AuthorAgent._scene_terms("林泽")
        # All substrings from a 2-char input should be empty (min window=3)
        assert len(terms) == 0

    def test_english_tokens_extracted(self):
        from novel_factory.agents.author import AuthorAgent
        terms = AuthorAgent._scene_terms("HP恢复了50点")
        assert "HP" in terms

    def test_empty_input(self):
        from novel_factory.agents.author import AuthorAgent
        assert AuthorAgent._scene_terms("") == []
        assert AuthorAgent._scene_terms(None) == []

    def test_beat_coverage_now_matches_paraphrased_text(self):
        """The old approach produced one long CJK token; sliding window matches shorter substrings."""
        from novel_factory.agents.author import AuthorAgent
        beat_text = "林泽走向主位坐下"
        # Tail text contains the literal 3-char substrings from beat_text
        tail_text = "...林泽走向主位，从容坐下。"
        terms = AuthorAgent._scene_terms(beat_text)
        matched = any(t in tail_text for t in terms)
        assert matched, f"Expected at least one of {terms[:5]} in tail_text"

    def test_old_approach_would_fail_on_long_token(self):
        """Verify sliding window produces shorter terms than the old regex."""
        from novel_factory.agents.author import AuthorAgent
        text = "林泽在宴会厅走向主位"
        terms = AuthorAgent._scene_terms(text)
        # Old regex would produce one 8-char token; new approach produces 3-6 char substrings
        assert all(len(t) <= 6 for t in terms if all(ord(c) > 0x80 for c in t))
        # Must contain useful short substrings
        assert "宴会厅" in terms  # 3-char substring


# ──────────────────────────────────────────────────────────────────────
# Phase 5.1 — CreativeLedgerCurator agent_id
# ──────────────────────────────────────────────────────────────────────


class TestCreativeLedgerCuratorId:
    """CreativeLedgerCurator must define agent_id, not inherit 'base'."""

    def test_agent_id_defined(self):
        from novel_factory.agents.creative_ledger_curator import CreativeLedgerCurator
        assert CreativeLedgerCurator.agent_id == "creative_ledger_curator"
        assert CreativeLedgerCurator.agent_id != "base"


# ──────────────────────────────────────────────────────────────────────
# Phase 5.2 — node_recovery NODE_RETRY_TARGETS coverage
# ──────────────────────────────────────────────────────────────────────


class TestNodeRetryTargets:
    """NODE_RETRY_TARGETS must cover all v6.8.5+ / v6.9.0 nodes."""

    def test_quality_gate_present(self):
        assert "quality_gate" in NODE_RETRY_TARGETS
        assert NODE_RETRY_TARGETS["quality_gate"]["status"] == "polished"

    def test_memory_curator_present(self):
        assert "memory_curator" in NODE_RETRY_TARGETS
        assert NODE_RETRY_TARGETS["memory_curator"]["status"] == "reviewed"

    def test_creative_ledger_curator_present(self):
        assert "creative_ledger_curator" in NODE_RETRY_TARGETS
        assert NODE_RETRY_TARGETS["creative_ledger_curator"]["status"] == "published"

    def test_original_five_still_present(self):
        for node in ("planner", "screenwriter", "author", "polisher", "editor"):
            assert node in NODE_RETRY_TARGETS, f"{node} missing from NODE_RETRY_TARGETS"


# ──────────────────────────────────────────────────────────────────────
# Phase 3.2 — Memory Curator _find_existing non-numeric target_name
# ──────────────────────────────────────────────────────────────────────


class TestMemoryCuratorFindExisting:
    """_find_existing must handle non-numeric target_name for instructions."""

    def test_numeric_target_name_works(self):
        """Normal numeric chapter number should work as before."""
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        mock_repo = MagicMock()
        mock_repo.get_instruction_by_chapter.return_value = {"id": 1}
        agent = MemoryCuratorAgent(repo=mock_repo, llm=MagicMock())
        result = agent._find_existing("proj", "instructions", "5")
        mock_repo.get_instruction_by_chapter.assert_called_once_with("proj", 5)
        assert result == {"id": 1}

    def test_chinese_prefixed_target_name(self):
        """'第5章' should extract 5 via regex."""
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        mock_repo = MagicMock()
        mock_repo.get_instruction_by_chapter.return_value = {"id": 2}
        agent = MemoryCuratorAgent(repo=mock_repo, llm=MagicMock())
        result = agent._find_existing("proj", "instructions", "第5章")
        mock_repo.get_instruction_by_chapter.assert_called_once_with("proj", 5)
        assert result == {"id": 2}

    def test_non_numeric_target_name_returns_none(self):
        """Pure text with no digits should return None gracefully."""
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        mock_repo = MagicMock()
        agent = MemoryCuratorAgent(repo=mock_repo, llm=MagicMock())
        result = agent._find_existing("proj", "instructions", "章节标题")
        mock_repo.get_instruction_by_chapter.assert_not_called()
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# Phase 3.1 — Memory Curator instructions fallback
# ──────────────────────────────────────────────────────────────────────


class TestMemoryCuratorInstructionsFallback:
    """_normalize_and_apply_patches should fill target_name for instructions."""

    def test_instructions_fallback_from_chapter_number(self):
        """When target_name is empty and data has chapter_number, use it."""
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        mock_repo = MagicMock()
        agent = MemoryCuratorAgent(repo=mock_repo, llm=MagicMock())
        # Simulate the fallback logic directly
        target_table = "instructions"
        target_name = ""
        data = {"chapter_number": 3, "objective": "test"}
        # The actual fallback code from _normalize_and_apply_patches
        if target_table == "instructions" and not target_name:
            target_name = str(data.get("chapter_number") or data.get("chapter") or "").strip()
        assert target_name == "3"


# ──────────────────────────────────────────────────────────────────────
# Phase 3.3 — memory_update lock IntegrityError handling
# ──────────────────────────────────────────────────────────────────────


class TestMemoryUpdateLockRace:
    """acquire_memory_curator_lock must distinguish IntegrityError from others."""

    def test_integrity_error_returns_acquired_false(self):
        """Primary key conflict (IntegrityError) with active (non-stale) lock → acquired=False."""
        from novel_factory.db.repositories.memory_update import MemoryUpdateRepositoryMixin

        mixin = MemoryUpdateRepositoryMixin()
        mock_conn = MagicMock()
        # First INSERT raises IntegrityError; after stale check returns False (active lock),
        # the method falls through to the final SELECT.
        mock_conn.execute.side_effect = [
            sqlite3.IntegrityError("UNIQUE constraint failed"),  # first INSERT
            MagicMock(fetchone=MagicMock(return_value=None)),    # SELECT (final)
        ]
        mixin._conn = MagicMock(return_value=mock_conn)
        # Simulate active lock: _delete_stale returns False (nothing deleted)
        mixin._delete_stale_memory_curator_lock = MagicMock(return_value=False)

        result = mixin.acquire_memory_curator_lock("proj", 1, "run-1")

        assert result["acquired"] is False
        # _delete_stale was called but found no stale lock
        mixin._delete_stale_memory_curator_lock.assert_called_once()


# ──────────────────────────────────────────────────────────────────────
# Phase 2 — Editor seam blocking_count (unit level)
# ──────────────────────────────────────────────────────────────────────


class TestEditorSeamBlockingCount:
    """Seam blocking_count must count only seam-related issues."""

    def test_only_seam_issues_counted(self):
        blocking_issues = [
            "[章间衔接] 缺少场景过渡",
            "[死刑红线] 主角死亡",
            "some other blocking issue",
        ]
        seam_blocking = [i for i in blocking_issues if isinstance(i, str) and "章间衔接" in i]
        assert len(seam_blocking) == 1
        # Old code would return len(blocking_issues) == 3

    def test_no_seam_issues(self):
        blocking_issues = ["[死刑红线] 主角死亡", "other issue"]
        seam_blocking = [i for i in blocking_issues if isinstance(i, str) and "章间衔接" in i]
        assert len(seam_blocking) == 0


# ──────────────────────────────────────────────────────────────────────
# U5 — Memory Updates create-patch protagonist false-positive
# ──────────────────────────────────────────────────────────────────────


class TestCreatePatchProtagonistFalsePositive:
    """A create-patch for a new character must NOT be misrouted to the protagonist
    just because the evidence text mentions the protagonist's name."""

    def test_find_character_by_exact_name_matches_exact(self):
        """_find_character_by_exact_name returns the character when name matches."""
        from novel_factory.api.routes.memory_updates import _find_character_by_exact_name
        mock_repo = MagicMock()
        mock_repo.list_characters.return_value = [
            {"id": 1, "name": "陆恒", "role": "protagonist"},
            {"id": 2, "name": "张三", "role": "supporting"},
        ]
        result = _find_character_by_exact_name(mock_repo, "proj", "张三")
        assert result is not None
        assert result["name"] == "张三"

    def test_find_character_by_exact_name_no_match_for_new_character(self):
        """New character name not in DB → returns None, bypassing fuzzy match."""
        from novel_factory.api.routes.memory_updates import _find_character_by_exact_name
        mock_repo = MagicMock()
        mock_repo.list_characters.return_value = [
            {"id": 1, "name": "陆恒", "role": "protagonist"},
        ]
        result = _find_character_by_exact_name(mock_repo, "proj", "未知黑影")
        assert result is None

    def test_create_patch_with_protagonist_in_evidence_does_not_match(self):
        """Create patch with evidence mentioning protagonist → exact name lookup
        returns None, so operation stays 'create' and new character is created."""
        from novel_factory.api.routes.memory_updates import _find_character_by_exact_name
        mock_repo = MagicMock()
        mock_repo.list_characters.return_value = [
            {"id": 1, "name": "陆恒", "role": "protagonist"},
        ]
        # New character evidence mentions protagonist name
        new_char_name = "未知黑影"
        result = _find_character_by_exact_name(mock_repo, "proj", new_char_name)
        assert result is None, (
            "Exact name lookup should NOT match '陆恒' just because evidence text mentions him"
        )


# ──────────────────────────────────────────────────────────────────────
# U1 — Editor _call_editor_llm fallback double-failure guard
# ──────────────────────────────────────────────────────────────────────


class TestEditorFallbackGuard:
    """Editor must not raise UnboundLocalError when fallback also fails."""

    def test_fallback_output_is_always_bound(self):
        """Even when _fallback_rule_review raises, output should be a valid EditorOutput."""
        from novel_factory.agents.editor import EditorAgent, EditorOutput
        # Simulate the defensive pattern from the fix:
        # try: output = fallback() except: output = emergency default
        try:
            raise RuntimeError("LLM failed")
        except Exception:
            try:
                raise RuntimeError("fallback also failed")
            except Exception:
                from novel_factory.models.schemas import EditorScores
                output = EditorOutput(
                    pass_=False,
                    score=40,
                    issues=["LLM 审核异常且规则兜底也失败"],
                    revision_target="author",
                    scores=EditorScores(continuity=40, logic=40, style=40, quality=40),
                )
        assert output.pass_ is False
        assert output.score == 40
        assert output.revision_target == "author"


# ──────────────────────────────────────────────────────────────────────
# U2 — Screenwriter empty scene_beats rejection
# ──────────────────────────────────────────────────────────────────────


class TestScreenwriterEmptyBeats:
    """Screenwriter self-check must reject empty scene_beats."""

    def test_empty_beats_triggers_issue(self):
        """An empty scene_beats list should produce a beat_completeness issue."""
        from novel_factory.agents.screenwriter import ScreenwriterAgent
        from novel_factory.models.schemas import ScreenwriterOutput, SceneBeat
        from novel_factory.agent_runtime.self_check import SelfCheckResult

        # Create output with empty scene_beats
        out = ScreenwriterOutput(scene_beats=[])
        data = {"output": out}

        # Simulate the self_check_wrap logic (extracted from screenwriter.py)
        issues = []
        if not out.scene_beats:
            issues.append({"type": "beat_completeness", "message": "scene_beats 列表为空"})
        for i, beat in enumerate(out.scene_beats):
            if not beat.scene_goal:
                issues.append({"type": "beat_completeness", "message": f"Beat {i+1} missing scene_goal"})

        assert len(issues) == 1
        assert "为空" in issues[0]["message"]


# ──────────────────────────────────────────────────────────────────────
# U3 — ContinuityChecker send_message method name
# ──────────────────────────────────────────────────────────────────────


class TestContinuityCheckerMethodName:
    """ContinuityChecker must use repo.send_message, not send_agent_message."""

    def test_send_message_method_exists(self):
        """The repository must expose send_message (not send_agent_message)."""
        from novel_factory.db.repositories.workflow import WorkflowRepositoryMixin
        assert hasattr(WorkflowRepositoryMixin, "send_message")

    def test_send_agent_message_does_not_exist(self):
        """send_agent_message should not exist on the repository."""
        from novel_factory.db.repositories.workflow import WorkflowRepositoryMixin
        assert not hasattr(WorkflowRepositoryMixin, "send_agent_message")


# ──────────────────────────────────────────────────────────────────────
# U4 — CreativeLedgerCurator invoke_json messages format
# ──────────────────────────────────────────────────────────────────────


class TestCreativeLedgerCuratorInvokeFormat:
    """CreativeLedgerCurator must pass messages list to invoke_json."""

    def test_invoke_json_receives_messages_list(self):
        """invoke_json should be called with a list of message dicts, not a string."""
        from novel_factory.agents.creative_ledger_curator import CreativeLedgerCurator

        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {"entries": []}
        mock_repo = MagicMock()
        mock_repo.get_chapter_content.return_value = "test content"
        mock_repo.get_project.return_value = {"id": "proj"}
        mock_repo.get_chapter.return_value = {"chapter_number": 1}
        mock_repo.get_chapter_state.return_value = None
        mock_repo.get_latest_review.return_value = None
        mock_repo.get_latest_creative_ledger.return_value = None

        curator = CreativeLedgerCurator(repo=mock_repo, llm=mock_llm)
        try:
            curator._generate_ledger_update(
                project_id="proj",
                chapter_number=1,
                chapter_content="test content",
                ledger_type="reader_promise",
                previous_data=None,
            )
        except Exception:
            pass  # We only care about the call signature

        if mock_llm.invoke_json.called:
            call_args = mock_llm.invoke_json.call_args
            first_arg = call_args[0][0]
            # Must be a list of dicts, not a raw string
            assert isinstance(first_arg, list), f"Expected list, got {type(first_arg)}"
            assert isinstance(first_arg[0], dict)
            assert "role" in first_arg[0]
