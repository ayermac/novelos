"""v6.7.8: Revision Retry Accounting & Continuity Semantics tests.

Tests that:
1. Internal compression failure does NOT consume chapter retry (retry_count unchanged)
2. Chapter-level quality gate failure DOES consume retry (retry_count increments)
3. Internal repair emits ``internal_repair_attempt`` event (not ``quality_gate_retry``)
4. Chapter retry emits ``quality_gate_retry`` event
5. Internal repair cap escalates to chapter-level retry (P1-1 fix)
6. Status-fact + consistent action is downgraded to warning (production code, P2-2 fix)
7. Status-fact + hard contradiction remains blocking even with consistent-action hit (P1-2 fix)
8. Status-fact + inconsistent action remains blocking
9. Status-fact + expanded keywords (强行维持/摇摇欲坠) is downgraded (P2-1 fix)
10. Non-status facts are not affected by the filter
11. Version alignment: version.py matches frontend/package.json
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState


# ── Helpers ──────────────────────────────────────────────────────


class StubLLMProvider(LLMProvider):
    """Minimal stub that returns canned responses for invoke_json."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self._call_count = 0

    def invoke_json(self, messages, schema=None, **kwargs):
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        return {}

    def invoke_text(self, messages, **kwargs):
        return json.dumps(self.invoke_json(messages))


def _make_state(
    project_id: str = "test_proj",
    chapter_number: int = 1,
    max_retries: int = 3,
    workflow_run_id: str = "run-001",
    **kwargs,
) -> FactoryState:
    return FactoryState(
        project_id=project_id,
        chapter_number=chapter_number,
        max_retries=max_retries,
        workflow_run_id=workflow_run_id,
        **kwargs,
    )


def _seed_project(repo, project_id="test_proj", chapter_number=1, status="polished"):
    """Seed a project with instruction and chapter."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, chapter_number, "第一章 测试", status,
         "赵宏明强撑着威胁对方，色厉内荏地大喊。赵宏明从容指挥安保大步离开。"),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (project_id, chapter_number, "测试目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.commit()
    conn.close()


def _seed_story_fact(repo, project_id, subject, attribute, value, status="active"):
    """Seed a story fact."""
    conn = repo._conn()
    fact_id = f"fact-{subject}-{attribute}"
    conn.execute(
        "INSERT INTO story_facts "
        "(id, project_id, fact_key, fact_type, subject, attribute, value_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (fact_id, project_id, f"{subject}.{attribute}", "character",
         subject, attribute, value, status),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def seeded_repo():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    repo = Repository(db_path)
    _seed_project(repo)
    try:
        yield repo
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture
def seeded_repo_with_facts():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    repo = Repository(db_path)
    _seed_project(repo)
    _seed_story_fact(
        repo, "test_proj", "赵宏明", "状态",
        json.dumps("被安保围住，极度恐惧", ensure_ascii=False),
    )
    try:
        yield repo
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ── A. Internal repair does NOT consume chapter retry ────────────


class TestInternalRepairRetryAccounting:
    """v6.7.8: Internal repairs (auto-compression) do not consume chapter retries."""

    def test_internal_compression_failure_does_not_increment_retry(self, seeded_repo):
        """1. Internal compression failure: retry_count stays unchanged."""
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = seeded_repo
        state = _make_state()

        assert repo.get_chapter_retry_count("test_proj", 1) == 0

        result = {
            "error": "字数质量门未通过: 超出上限",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "word_count_fail": True,
                "message": "超出上限",
                "actual_word_count": 6000,
                "word_target": 4800,
                "agent": "polisher",
                "workflow_run_id": "run-001",
                "internal_repair": True,
                "consume_revision_retry": False,
                "repair_scope": "internal_word_count_compression",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        assert updated.get("retry_count") == 0
        assert updated.get("retryable_quality_gate") is True
        assert updated.get("requires_human") is False
        assert repo.get_chapter_retry_count("test_proj", 1) == 0

    def test_chapter_retry_does_increment(self, seeded_repo):
        """2. Chapter-level quality gate failure: retry_count increments."""
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = seeded_repo
        state = _make_state()

        assert repo.get_chapter_retry_count("test_proj", 1) == 0

        result = {
            "error": "死亡红线违规",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "death_penalty_fail": True,
                "message": "死亡红线违规",
                "agent": "polisher",
                "workflow_run_id": "run-001",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        assert updated.get("retry_count") == 1
        assert updated.get("retryable_quality_gate") is True
        assert updated.get("requires_human") is False

    def test_internal_repair_emits_internal_repair_attempt_event(self, seeded_repo):
        """3. Internal repair emits internal_repair_attempt event type."""
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = seeded_repo
        state = _make_state()

        result = {
            "error": "字数质量门未通过",
            "quality_gate": {
                "pass": False,
                "revision_target": "author",
                "word_count_fail": True,
                "message": "字数质量门未通过",
                "agent": "author",
                "workflow_run_id": "run-001",
                "internal_repair": True,
                "consume_revision_retry": False,
                "repair_scope": "internal_word_count_compression",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        events = updated.get("_exec_events", [])
        assert len(events) == 1
        assert events[0]["event_type"] == "internal_repair_attempt"
        assert events[0]["payload"]["internal_repair"] is True
        assert events[0]["payload"]["repair_scope"] == "internal_word_count_compression"
        assert all(e["event_type"] != "quality_gate_retry" for e in events)

    def test_chapter_retry_emits_quality_gate_retry_event(self, seeded_repo):
        """4. Chapter-level retry emits quality_gate_retry event type."""
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = seeded_repo
        state = _make_state()

        result = {
            "error": "场景覆盖不足",
            "quality_gate": {
                "pass": False,
                "revision_target": "author",
                "scene_beat_coverage_fail": True,
                "message": "场景覆盖不足",
                "agent": "author",
                "workflow_run_id": "run-001",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        events = updated.get("_exec_events", [])
        assert len(events) == 1
        assert events[0]["event_type"] == "quality_gate_retry"
        assert "internal_repair" not in events[0].get("payload", {})

    def test_internal_repair_cap_escalates_to_chapter_retry(self, seeded_repo):
        """5. (P1-1) After MAX_INTERNAL_REPAIR_ATTEMPTS in same run, escalation."""
        from novel_factory.workflow.nodes import (
            _handle_retryable_quality_gate,
            MAX_INTERNAL_REPAIR_ATTEMPTS,
        )

        repo = seeded_repo
        run_id = "run-cap-test"
        state = _make_state(workflow_run_id=run_id)

        # Exhaust the internal repair budget within the same run.
        for i in range(MAX_INTERNAL_REPAIR_ATTEMPTS):
            tid = repo.start_task(
                "test_proj", 1, "internal_repair", "polisher",
                workflow_run_id=run_id,
            )
            repo.complete_task(tid, success=True)

        assert repo.get_chapter_internal_repair_count(
            "test_proj", 1, workflow_run_id=run_id, agent_id="polisher",
        ) == MAX_INTERNAL_REPAIR_ATTEMPTS
        assert repo.get_chapter_retry_count("test_proj", 1) == 0

        result = {
            "error": "字数质量门未通过",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "word_count_fail": True,
                "message": "字数质量门未通过",
                "agent": "polisher",
                "workflow_run_id": run_id,
                "internal_repair": True,
                "consume_revision_retry": False,
                "repair_scope": "internal_word_count_compression",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        # Should have escalated to chapter-level retry.
        assert updated.get("retry_count") == 1
        assert repo.get_chapter_retry_count("test_proj", 1) == 1
        events = updated.get("_exec_events", [])
        assert events[0]["event_type"] == "quality_gate_retry"
        assert events[1]["event_type"] == "internal_repair_escalated"
        assert events[1]["payload"]["current_retry_count"] == 0
        assert events[1]["payload"]["new_retry_count"] == 1

    def test_author_internal_repairs_do_not_exhaust_polisher_budget(self, seeded_repo):
        """6. (P2 regression) Author internal repairs scoped to run don't affect polisher."""
        from novel_factory.workflow.nodes import (
            _handle_retryable_quality_gate,
            MAX_INTERNAL_REPAIR_ATTEMPTS,
        )

        repo = seeded_repo
        run_id = "run-cross-agent"

        # Author exhausts its own internal repair budget in the same run.
        for i in range(MAX_INTERNAL_REPAIR_ATTEMPTS):
            tid = repo.start_task(
                "test_proj", 1, "internal_repair", "author",
                workflow_run_id=run_id,
            )
            repo.complete_task(tid, success=True)

        # Now polisher tries an internal repair in the same run.
        # Budget is scoped by run and agent, so author repairs must not exhaust
        # polisher's internal repair budget.
        state = _make_state(workflow_run_id=run_id)
        result = {
            "error": "字数质量门未通过",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "word_count_fail": True,
                "message": "字数质量门未通过",
                "agent": "polisher",
                "workflow_run_id": run_id,
                "internal_repair": True,
                "consume_revision_retry": False,
                "repair_scope": "internal_word_count_compression",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        # Polisher has its own budget -> should NOT escalate.
        assert updated.get("retry_count") == 0
        assert repo.get_chapter_retry_count("test_proj", 1) == 0
        events = updated.get("_exec_events", [])
        assert events[0]["event_type"] == "internal_repair_attempt"

    def test_old_run_repairs_do_not_pollute_new_run(self, seeded_repo):
        """7. (P2 regression) Old run's internal repairs don't affect new run."""
        from novel_factory.workflow.nodes import (
            _handle_retryable_quality_gate,
            MAX_INTERNAL_REPAIR_ATTEMPTS,
        )

        repo = seeded_repo
        old_run = "run-old"

        # Old run exhausts its internal repair budget.
        for i in range(MAX_INTERNAL_REPAIR_ATTEMPTS):
            tid = repo.start_task(
                "test_proj", 1, "internal_repair", "polisher",
                workflow_run_id=old_run,
            )
            repo.complete_task(tid, success=True)

        # New run should have a fresh budget.
        new_run = "run-new"
        state = _make_state(workflow_run_id=new_run)
        result = {
            "error": "字数质量门未通过",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "word_count_fail": True,
                "message": "字数质量门未通过",
                "agent": "polisher",
                "workflow_run_id": new_run,
                "internal_repair": True,
                "consume_revision_retry": False,
                "repair_scope": "internal_word_count_compression",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        # New run has its own budget -> should NOT escalate.
        assert updated.get("retry_count") == 0
        assert repo.get_chapter_retry_count("test_proj", 1) == 0
        events = updated.get("_exec_events", [])
        assert events[0]["event_type"] == "internal_repair_attempt"

    def test_max_retries_still_caps_internal_repairs(self, seeded_repo):
        """8. At max retries, internal repairs still get requires_human."""
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = seeded_repo
        state = _make_state(max_retries=3)

        for i in range(3):
            tid = repo.start_task("test_proj", 1, "revise", "polisher", workflow_run_id=f"run-{i}")
            repo.complete_task(tid, success=True)

        assert repo.get_chapter_retry_count("test_proj", 1) == 3

        result = {
            "error": "字数质量门未通过",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "word_count_fail": True,
                "message": "字数质量门未通过",
                "agent": "polisher",
                "workflow_run_id": "run-001",
                "internal_repair": True,
                "consume_revision_retry": False,
                "repair_scope": "internal_word_count_compression",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)
        assert updated.get("requires_human") is True


# ── B. Story facts compliance — production code tests ────────────


class TestStatusFactFilterProduction:
    """v6.7.8 P2-2: Status-fact tests call production _run_story_facts_compliance."""

    def _make_editor(self, repo, llm_responses):
        """Create an EditorAgent with a StubLLMProvider."""
        from novel_factory.agents.editor import EditorAgent
        llm = StubLLMProvider(llm_responses)
        return EditorAgent(repo=repo, llm=llm)

    def _make_inputs(self, repo, content, project_id="test_proj", chapter_number=1):
        """Create EditorInputs for _run_story_facts_compliance."""
        from novel_factory.agents.editor import EditorInputs
        return EditorInputs(
            project_id=project_id,
            chapter_number=chapter_number,
            chapter={"content": content, "title": "测试"},
            content=content,
            llm_mode="real",
        )

    def test_status_fact_consistent_action_downgraded_via_production_code(
        self, seeded_repo_with_facts,
    ):
        """6. Production code: status-fact + consistent action -> warning."""
        violations_response = {
            "violations": [
                {
                    "fact_key": "赵宏明.状态",
                    "fact_statement": "赵宏明.状态: 被安保围住，极度恐惧",
                    "violation_text": "赵宏明强撑着威胁对方，色厉内荏地大喊",
                    "severity": "blocking",
                },
            ],
        }
        editor = self._make_editor(seeded_repo_with_facts, [violations_response])
        inputs = self._make_inputs(
            seeded_repo_with_facts,
            "赵宏明强撑着威胁对方，色厉内荏地大喊",
        )

        result = editor._run_story_facts_compliance(inputs)

        assert result.checked is True
        assert result.violation_count == 1
        assert result.blocking_violation_count == 0
        assert result.violations[0]["severity"] == "warning"
        assert result.violations[0]["_downgrade_reason"] == "status_fact_with_consistent_action"

    def test_hard_contradiction_not_downgraded(self, seeded_repo_with_facts):
        """7. (P1-2) Hard contradiction blocks downgrade even with consistent-action hit."""
        violations_response = {
            "violations": [
                {
                    "fact_key": "赵宏明.状态",
                    "fact_statement": "赵宏明.状态: 被安保围住，极度恐惧",
                    "violation_text": "赵宏明强撑着从容指挥安保，大步离开",
                    "severity": "blocking",
                },
            ],
        }
        editor = self._make_editor(seeded_repo_with_facts, [violations_response])
        inputs = self._make_inputs(
            seeded_repo_with_facts,
            "赵宏明强撑着从容指挥安保，大步离开",
        )

        result = editor._run_story_facts_compliance(inputs)

        assert result.checked is True
        assert result.blocking_violation_count == 1
        assert result.violations[0]["severity"] == "blocking"
        assert "_downgrade_reason" not in result.violations[0]

    def test_status_fact_inconsistent_action_remains_blocking(self, seeded_repo_with_facts):
        """8. Status-fact + inconsistent action -> stays blocking."""
        violations_response = {
            "violations": [
                {
                    "fact_key": "赵宏明.状态",
                    "fact_statement": "赵宏明.状态: 被安保围住，极度恐惧",
                    "violation_text": "赵宏明从容指挥安保，大步走出大厅",
                    "severity": "blocking",
                },
            ],
        }
        editor = self._make_editor(seeded_repo_with_facts, [violations_response])
        inputs = self._make_inputs(
            seeded_repo_with_facts,
            "赵宏明从容指挥安保，大步走出大厅",
        )

        result = editor._run_story_facts_compliance(inputs)

        assert result.blocking_violation_count == 1
        assert result.violations[0]["severity"] == "blocking"

    def test_expanded_keywords_downgrade(self, seeded_repo_with_facts):
        """9. (P2-1) Expanded keywords (强行维持/摇摇欲坠) trigger downgrade."""
        violations_response = {
            "violations": [
                {
                    "fact_key": "赵宏明.状态",
                    "fact_statement": "赵宏明.状态: 被安保围住，极度恐惧",
                    "violation_text": "赵宏明强行维持摇摇欲坠的体面，声音粗重地开口",
                    "severity": "blocking",
                },
            ],
        }
        editor = self._make_editor(seeded_repo_with_facts, [violations_response])
        inputs = self._make_inputs(
            seeded_repo_with_facts,
            "赵宏明强行维持摇摇欲坠的体面，声音粗重地开口",
        )

        result = editor._run_story_facts_compliance(inputs)

        assert result.blocking_violation_count == 0
        assert result.violations[0]["severity"] == "warning"
        assert result.violations[0]["_downgrade_reason"] == "status_fact_with_consistent_action"

    def test_non_status_fact_not_affected(self, seeded_repo_with_facts):
        """10. Non-status facts are not affected by the filter."""
        violations_response = {
            "violations": [
                {
                    "fact_key": "林泽.身份",
                    "fact_statement": "林泽.身份: 系统持有者",
                    "violation_text": "林泽完全不知道系统的存在",
                    "severity": "blocking",
                },
            ],
        }
        editor = self._make_editor(seeded_repo_with_facts, [violations_response])
        inputs = self._make_inputs(
            seeded_repo_with_facts,
            "林泽完全不知道系统的存在",
        )

        result = editor._run_story_facts_compliance(inputs)

        assert result.blocking_violation_count == 1
        assert result.violations[0]["severity"] == "blocking"


# ── C. Version alignment ────────────────────────────────────────


class TestVersionAlignment:
    """v6.8.5+: All version sources must agree."""

    def test_version_py_matches_runtime_version(self):
        from novel_factory.version import get_version
        from novel_factory.version import __version__
        assert __version__ == get_version()

    def test_frontend_package_json_matches(self):
        from novel_factory.version import get_version
        with open("frontend/package.json") as f:
            data = json.load(f)
        assert data["version"] == get_version()

    def test_desktop_package_json_matches(self):
        from novel_factory.version import get_version
        with open("desktop/package.json") as f:
            data = json.load(f)
        assert data["version"] == get_version()
