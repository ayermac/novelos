"""Tests for v3.3 Batch Continuity Gate.

Tests that batch continuity gate works correctly and blocks approve
when gate failed/error, while allowing request_changes through.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider


class StubLLM(LLMProvider):
    """Stub LLM for testing."""

    def __init__(self, continuity_issues=None, fail_continuity=False):
        self._continuity_issues = continuity_issues or []
        self._fail_continuity = fail_continuity

    def invoke_text(self, prompt: str, **kwargs) -> str:
        return "Stub response"

    def invoke_json(self, prompt, **kwargs) -> dict:
        # Check schema name for appropriate response
        schema = kwargs.get("schema")
        schema_name = getattr(schema, "__name__", "") if schema else ""

        if "ContinuityCheckerOutput" in schema_name:
            if self._fail_continuity:
                raise RuntimeError("ContinuityChecker failed")

            return {
                "report": {
                    "project_id": "demo",
                    "from_chapter": 1,
                    "to_chapter": 3,
                    "issues": self._continuity_issues,
                    "warnings": [],
                    "state_card_consistency": not any(
                        i.get("issue_type") == "state_card" and i.get("severity") == "error"
                        for i in self._continuity_issues
                    ),
                    "character_consistency": not any(
                        i.get("issue_type") == "character" and i.get("severity") == "error"
                        for i in self._continuity_issues
                    ),
                    "plot_consistency": not any(
                        i.get("issue_type") == "plot" and i.get("severity") == "error"
                        for i in self._continuity_issues
                    ),
                    "summary": "连续性检查摘要",
                },
                "agent_messages": [],
            }

        if "Editor" in schema_name:
            return {"pass": True, "score": 95, "scores": {}, "issues": [], "suggestions": [], "state_card": {}}
        if "Polisher" in schema_name:
            content = "润色后的内容。" * 100
            return {"content": content, "fact_change_risk": "none", "changed_scope": []}
        if "Author" in schema_name:
            content = "这是测试内容。" * 50
            return {"title": "测试章节", "content": content, "word_count": len(content)}
        if "Screenwriter" in schema_name:
            return {"scene_beats": [{"sequence": 1, "scene_goal": "目标", "conflict": "冲突", "hook": "钩子"}]}
        if "Planner" in schema_name:
            return {"chapter_brief": {"objective": "目标", "required_events": ["事件1"], "plots_to_plant": [], "plots_to_resolve": [], "ending_hook": "钩子", "constraints": []}}
        return {"result": "stub"}


def _seed_project(repo: Repository, project_id: str = "demo", num_chapters: int = 3):
    """Seed a project with chapters for testing."""
    conn = repo._conn()
    try:
        existing = conn.execute(
            "SELECT project_id FROM projects WHERE project_id=?", (project_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
                (project_id, f"{project_id.title()} Novel", "fantasy"),
            )
        for ch in range(1, num_chapters + 1):
            existing_ch = conn.execute(
                "SELECT chapter_number FROM chapters WHERE project_id=? AND chapter_number=?",
                (project_id, ch),
            ).fetchone()
            if not existing_ch:
                conn.execute(
                    "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
                    (project_id, ch, f"第{ch}章", "planned"),
                )
        conn.commit()
    finally:
        conn.close()


def _setup_batch_awaiting_review(repo, project_id="demo", from_ch=1, to_ch=3):
    """Create a production run and mark it as awaiting_review."""
    _seed_project(repo, project_id, to_ch)
    run_id = repo.create_production_run(project_id, from_ch, to_ch)
    repo.update_production_run(run_id, status="awaiting_review")
    return run_id


def run_cli(args: list[str]) -> tuple[int, str, str]:
    """Run CLI command and return exit code, stdout, stderr."""
    cmd = [sys.executable, "-m", "novel_factory.cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


# ── Test 1: Migration 009 idempotency ──────────────────────────────


class TestMigration009Idempotency:

    def test_init_db_with_009_migration(self, tmp_path):
        """init_db() should handle 009 migration idempotently."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        init_db(str(db_path))

        conn = get_connection(str(db_path))
        try:
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            assert "batch_continuity_gates" in tables
        finally:
            conn.close()


# ── Test 2: run_batch_continuity_gate saves gate ──────────────────


class TestRunBatchContinuityGateSavesGate:

    def test_gate_saved_to_db(self, tmp_path):
        """run_batch_continuity_gate should save gate to database."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)
        result = dispatcher.run_batch_continuity_gate(run_id)

        assert result["ok"]
        assert "gate_id" in result["data"]

        # Verify in DB
        gate = repo.get_latest_batch_continuity_gate(run_id)
        assert gate is not None
        assert gate["status"] in ("passed", "warning", "failed", "error")


# ── Test 3: No error issue -> gate passed ──────────────────────────


class TestNoErrorIssueGatePassed:

    def test_no_error_issues_passes_gate(self, tmp_path):
        """No error issues should result in gate passed."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM(continuity_issues=[])
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)
        result = dispatcher.run_batch_continuity_gate(run_id)

        assert result["ok"]
        assert result["data"]["status"] == "passed"
        assert result["data"]["issue_count"] == 0


# ── Test 4: Warning issue -> gate warning, allow approve ───────────


class TestWarningIssueGateWarning:

    def test_warning_issues_gate_warning(self, tmp_path):
        """Warning issues should result in gate warning and allow approve."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        warning_issues = [{
            "issue_type": "character",
            "severity": "warning",
            "chapter_range": "1-3",
            "description": "角色性格微漂移",
            "recommendation": "检查角色设定",
        }]
        stub_llm = StubLLM(continuity_issues=warning_issues)
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)
        result = dispatcher.run_batch_continuity_gate(run_id)

        assert result["ok"]
        assert result["data"]["status"] == "warning"

        # Can approve with warning
        can_approve = dispatcher.can_approve_batch(run_id)
        assert can_approve["ok"] is True


# ── Test 5: Error issue -> gate failed, block approve ──────────────


class TestErrorIssueGateFailed:

    def test_error_issues_gate_failed(self, tmp_path):
        """Error issues should result in gate failed and block approve."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        error_issues = [{
            "issue_type": "state_card",
            "severity": "error",
            "chapter_range": "2-3",
            "description": "角色等级回退",
            "recommendation": "修复状态卡",
        }]
        stub_llm = StubLLM(continuity_issues=error_issues)
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)
        result = dispatcher.run_batch_continuity_gate(run_id)

        assert result["ok"]
        assert result["data"]["status"] == "failed"

        # Cannot approve
        can_approve = dispatcher.can_approve_batch(run_id)
        assert can_approve["ok"] is False


# ── Test 6: Continuity checker execution failure -> gate error ──────


class TestContinuityCheckerFailureGateError:

    def test_checker_failure_gate_error(self, tmp_path):
        """ContinuityChecker exception should result in gate error."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM(fail_continuity=True)
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)
        result = dispatcher.run_batch_continuity_gate(run_id)

        assert result["ok"]  # Gate ran (didn't crash)
        assert result["data"]["status"] == "error"

        # Cannot approve
        can_approve = dispatcher.can_approve_batch(run_id)
        assert can_approve["ok"] is False


# ── Test 7: Multi-chapter batch without gate blocks approve ─────────


class TestMultiChapterNoGateBlocksApprove:

    def test_multi_chapter_no_gate_blocks_approve(self, tmp_path):
        """Multi-chapter batch without gate should block approve."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo, from_ch=1, to_ch=3)

        can_approve = dispatcher.can_approve_batch(run_id)
        assert can_approve["ok"] is False
        assert "not been run" in can_approve["error"]


# ── Test 8: Single-chapter batch without gate allows approve ────────


class TestSingleChapterNoGateAllowsApprove:

    def test_single_chapter_no_gate_allows_approve(self, tmp_path):
        """Single-chapter batch without gate should allow approve with gate_required=false."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo, from_ch=1, to_ch=1)

        can_approve = dispatcher.can_approve_batch(run_id)
        assert can_approve["ok"] is True
        assert can_approve["data"]["gate_required"] is False


# ── Test 9: Gate failed blocks review approve, no state changes ─────


class TestGateFailedBlocksReviewApprove:

    def test_gate_failed_blocks_approve_no_state_changes(self, tmp_path):
        """Gate failed should block approve without updating production_run or saving review_session."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        error_issues = [{
            "issue_type": "state_card",
            "severity": "error",
            "chapter_range": "2-3",
            "description": "状态卡不一致",
            "recommendation": "修复",
        }]
        stub_llm = StubLLM(continuity_issues=error_issues)
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)

        # Run gate -> failed
        gate_result = dispatcher.run_batch_continuity_gate(run_id)
        assert gate_result["data"]["status"] == "failed"

        # Try approve -> should be blocked
        review_result = dispatcher.review_batch(run_id, "approve")
        assert review_result["ok"] is False
        assert "approve is blocked" in review_result["error"]

        # Verify production_run status is NOT updated to approved
        run = repo.get_production_run(run_id)
        assert run["status"] == "awaiting_review"

        # Verify no human_review_session saved
        session = repo.get_latest_human_review_session(run_id)
        assert session is None


# ── Test 10: Gate failed does not block request_changes ─────────────


class TestGateFailedDoesNotBlockRequestChanges:

    def test_request_changes_allowed_after_gate_failed(self, tmp_path):
        """request_changes should be allowed even when gate failed."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        error_issues = [{
            "issue_type": "state_card",
            "severity": "error",
            "chapter_range": "2-3",
            "description": "状态卡不一致",
            "recommendation": "修复",
        }]
        stub_llm = StubLLM(continuity_issues=error_issues)
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)

        # Run gate -> failed
        gate_result = dispatcher.run_batch_continuity_gate(run_id)
        assert gate_result["data"]["status"] == "failed"

        # request_changes should be allowed
        review_result = dispatcher.review_batch(run_id, "request_changes", "修复连续性问题")
        assert review_result["ok"] is True


# ── Test 11: Re-running gate after revision gets latest status ──────


class TestRerunGateAfterRevision:

    def test_rerun_gate_updates_status(self, tmp_path):
        """Re-running gate after revision should reflect latest status."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))

        run_id = _setup_batch_awaiting_review(repo)

        # First run: with error issues
        error_issues = [{
            "issue_type": "state_card",
            "severity": "error",
            "chapter_range": "2-3",
            "description": "状态卡不一致",
            "recommendation": "修复",
        }]
        stub_llm_fail = StubLLM(continuity_issues=error_issues)
        dispatcher = Dispatcher(repo, stub_llm_fail, max_retries=3, create_skill_registry=False)
        result1 = dispatcher.run_batch_continuity_gate(run_id)
        assert result1["data"]["status"] == "failed"

        # Second run: with no issues (after revision fixed them)
        stub_llm_pass = StubLLM(continuity_issues=[])
        dispatcher2 = Dispatcher(repo, stub_llm_pass, max_retries=3, create_skill_registry=False)
        result2 = dispatcher2.run_batch_continuity_gate(run_id)
        assert result2["data"]["status"] == "passed"

        # Verify latest gate is passed
        can_approve = dispatcher2.can_approve_batch(run_id)
        assert can_approve["ok"] is True


# ── Test 12: batch continuity CLI JSON envelope ────────────────────


class TestBatchContinuityCLIJsonEnvelope:

    def test_batch_continuity_json_envelope(self, tmp_path):
        """batch continuity --json should output stable envelope."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        _seed_project(repo, "demo", 3)

        run_id = repo.create_production_run("demo", 1, 3)
        repo.update_production_run(run_id, status="awaiting_review")

        code, stdout, stderr = run_cli([
            "--db-path", str(db_path), "batch", "continuity",
            "--run-id", run_id, "--llm-mode", "stub", "--json",
        ])

        result = json.loads(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result

        if result["ok"]:
            assert "gate_id" in result["data"]
            assert "status" in result["data"]


# ── Test 13: batch continuity-status CLI JSON envelope ──────────────


class TestBatchContinuityStatusCLIJsonEnvelope:

    def test_batch_continuity_status_json_envelope(self, tmp_path):
        """batch continuity-status --json should output stable envelope."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        _seed_project(repo, "demo", 3)
        run_id = repo.create_production_run("demo", 1, 3)
        repo.update_production_run(run_id, status="awaiting_review")

        # Run gate first
        dispatcher.run_batch_continuity_gate(run_id)

        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "batch", "continuity-status",
            "--run-id", run_id, "--json",
        ])

        result = json.loads(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result


# ── Test 14: Synthetic blocking issue for consistency flags ─────────


class TestSyntheticBlockingIssues:

    def test_false_consistency_flags_create_synthetic_issues(self, tmp_path):
        """When state_card/character/plot_consistency is False, synthetic blocking issues should be added."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))

        # Issues that set consistency flags to False but have no explicit error issue
        consistency_issues = [{
            "issue_type": "state_card",
            "severity": "warning",
            "chapter_range": "1-3",
            "description": "轻微状态卡漂移",
            "recommendation": "检查",
        }]
        # Override consistency flags manually via LLM response
        class ConsistencyFlagLLM(StubLLM):
            def invoke_json(self, prompt, **kwargs):
                schema = kwargs.get("schema")
                schema_name = getattr(schema, "__name__", "") if schema else ""
                if "ContinuityCheckerOutput" in schema_name:
                    return {
                        "report": {
                            "project_id": "demo",
                            "from_chapter": 1,
                            "to_chapter": 3,
                            "issues": consistency_issues,
                            "warnings": [],
                            "state_card_consistency": False,
                            "character_consistency": False,
                            "plot_consistency": True,
                            "summary": "存在一致性问题",
                        },
                        "agent_messages": [],
                    }
                return super().invoke_json(prompt, **kwargs)

        stub_llm = ConsistencyFlagLLM(continuity_issues=consistency_issues)
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        run_id = _setup_batch_awaiting_review(repo)
        result = dispatcher.run_batch_continuity_gate(run_id)

        assert result["ok"]
        assert result["data"]["status"] == "failed"
        # Should have synthetic blocking issues
        blocking = result["data"]["blocking_issues"]
        issue_types = [i["issue_type"] for i in blocking]
        assert "state_card" in issue_types
        assert "character" in issue_types
