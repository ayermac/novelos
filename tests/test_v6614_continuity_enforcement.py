"""v6.6.14: Continuity & Memory Enforcement Closure tests.

Tests that:
P1 - AgentContextBundle gets memory_context_degraded / trusted_memory_batch_id flags
P1 - format_context_bundle_for_prompt includes degraded notice when flag is True
P2 - EditorAgent._run_story_facts_compliance: stub mode → empty, no active facts → unchecked,
     any blocking fact violation → triggers revision
P2 - Editor result always contains story_facts_compliance field
P3 - build_for_planner sets memory_context_audit fields from bundle metadata
P3 - memory_context_degraded is annotation-only, never affects status flow
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from typing import Any

import pytest

from novel_factory.agent_runtime.context_builder import (
    AgentContextBuilder,
    AgentContextBundle,
    format_context_bundle_for_prompt,
)
from novel_factory.agents.editor import (
    FACTS_COMPLIANCE_BLOCK_THRESHOLD,
    EditorInputs,
    StoryFactsComplianceResult,
)
from novel_factory.agents.planner import build_memory_context_audit
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState


# ── Helpers ──────────────────────────────────────────────────────


class StubLLMProvider(LLMProvider):
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


def _make_db() -> tuple[str, Repository]:
    td = tempfile.mkdtemp()
    db_path = os.path.join(td, "test_v6614.db")
    init_db(db_path)
    return db_path, Repository(db_path)


def _seed_project(repo: Repository, project_id: str, chapter_number: int = 2, status: str = "planned") -> None:
    conn = repo._conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            (project_id, "Test Novel", "urban"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
            (project_id, chapter_number, f"第{chapter_number}章", status),
        )
        conn.execute(
            "INSERT OR IGNORE INTO instructions (project_id, chapter_number, objective, key_events, "
            "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            (project_id, chapter_number, "测试目标", '["事件1"]', '[]', '[]', "悬念", 2500),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_trusted_memory_batch(repo: Repository, project_id: str, chapter_number: int = 1) -> str:
    """Seed a trusted memory batch for the given chapter."""
    batch_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    conn = repo._conn()
    try:
        conn.execute(
            "INSERT INTO memory_update_batches (id, project_id, chapter_number, status, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            (batch_id, project_id, chapter_number, "applied", "valid extraction"),
        )
        conn.execute(
            "INSERT INTO memory_update_items "
            "(id, batch_id, project_id, target_table, operation, after_json, "
            "confidence, evidence_text, rationale, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item_id, batch_id, project_id, "characters", "update",
                '{"name": "林泽"}', 0.9, "章节中提到角色全名", "有效更新", "applied",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return batch_id


def _seed_story_facts(repo: Repository, project_id: str, facts: list[dict]) -> None:
    """Seed story_facts rows with status='active'."""
    conn = repo._conn()
    try:
        for fact in facts:
            conn.execute(
                "INSERT INTO story_facts (id, project_id, fact_key, fact_type, subject, attribute, "
                "value_json, status, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    project_id,
                    fact.get("fact_key", "key"),
                    fact.get("fact_type", "character"),
                    fact.get("subject", "林泽"),
                    fact.get("attribute", "name"),
                    json.dumps(fact.get("value", "林泽")),
                    "active",
                    fact.get("confidence", 1.0),
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ── P1: memory_context_degraded flag ─────────────────────────────


def test_memory_context_degraded_flag_set_when_no_trusted_batch():
    """bundle.memory_context_degraded is True when no trusted batch exists for prev chapter."""
    _, repo = _make_db()
    project_id = "proj_degraded"
    _seed_project(repo, project_id, chapter_number=2)

    builder = AgentContextBuilder(repo)
    bundle = builder.build_for_planner(project_id, chapter_number=2)

    assert bundle.memory_context_degraded is True
    assert bundle.trusted_memory_batch_id is None


def test_memory_context_degraded_is_hard_constraint():
    """No-trusted-memory warning is promoted to hard_constraints for prompt priority."""
    _, repo = _make_db()
    project_id = "proj_degraded_hard"
    _seed_project(repo, project_id, chapter_number=2)

    builder = AgentContextBuilder(repo)
    bundle = builder.build_for_author(project_id, chapter_number=2)

    assert bundle.memory_context_degraded is True
    assert bundle.hard_constraints
    assert bundle.hard_constraints[0].kind == "memory_degraded_warning"
    assert "story_facts" in bundle.hard_constraints[0].text
    assert "禁止脑补" in bundle.hard_constraints[0].text


def test_memory_context_degraded_flag_not_set_when_trusted_batch_exists():
    """bundle.memory_context_degraded is False when a trusted batch exists for prev chapter."""
    _, repo = _make_db()
    project_id = "proj_trusted"
    _seed_project(repo, project_id, chapter_number=2)
    batch_id = _seed_trusted_memory_batch(repo, project_id, chapter_number=1)

    builder = AgentContextBuilder(repo)
    bundle = builder.build_for_planner(project_id, chapter_number=2)

    assert bundle.memory_context_degraded is False
    assert bundle.trusted_memory_batch_id == batch_id


def test_memory_context_chapter_one_not_degraded():
    """Chapter 1 has no prev chapter — empty memory is expected, flag stays False."""
    _, repo = _make_db()
    project_id = "proj_ch1"
    _seed_project(repo, project_id, chapter_number=1)

    builder = AgentContextBuilder(repo)
    bundle = builder.build_for_planner(project_id, chapter_number=1)

    assert bundle.memory_context_degraded is False
    assert bundle.trusted_memory_batch_id is None


def test_format_context_bundle_includes_degraded_notice():
    """Degraded notice appears in formatted prompt when memory_context_degraded is True."""
    bundle = AgentContextBundle()
    bundle.memory_context_degraded = True

    result = format_context_bundle_for_prompt(bundle, agent_name="planner")

    assert "记忆上下文降级" in result
    assert "可信记忆批次" in result
    assert "story_facts" in result


def test_format_context_bundle_no_degraded_notice_when_trusted():
    """No degraded notice appears when memory_context_degraded is False."""
    bundle = AgentContextBundle()
    bundle.memory_context_degraded = False

    result = format_context_bundle_for_prompt(bundle, agent_name="planner")

    assert "记忆上下文降级" not in result


# ── P2: story_facts compliance check ─────────────────────────────


def test_story_facts_compliance_skipped_when_no_active_facts():
    """compliance returns checked=False when no active story_facts exist."""
    _, repo = _make_db()
    project_id = "proj_no_facts"
    _seed_project(repo, project_id)

    from novel_factory.agents.editor import EditorAgent

    agent = EditorAgent(repo, StubLLMProvider())
    inputs = EditorInputs(
        project_id=project_id,
        chapter_number=2,
        chapter={},
        content="Some chapter text",
        llm_mode="real",
    )

    result = agent._run_story_facts_compliance(inputs)

    assert result.checked is False
    assert result.violation_count == 0
    assert result.violations == []


def test_story_facts_compliance_returns_empty_in_stub_mode():
    """Stub mode returns empty compliance result without any LLM call."""
    _, repo = _make_db()
    project_id = "proj_stub"
    _seed_project(repo, project_id)
    _seed_story_facts(repo, project_id, [{"fact_key": "char_name", "subject": "林泽"}])

    from novel_factory.agents.editor import EditorAgent

    stub_llm = StubLLMProvider()
    agent = EditorAgent(repo, stub_llm)
    inputs = EditorInputs(
        project_id=project_id,
        chapter_number=2,
        chapter={},
        content="章节内容提到林泽",
        llm_mode="stub",
    )

    result = agent._run_story_facts_compliance(inputs)

    assert result.checked is False
    assert result.violations == []
    assert stub_llm._call_count == 0


def test_story_facts_compliance_zero_blocking_is_advisory():
    """Warning-only fact findings are advisory; blocking fact findings are hard."""
    result = StoryFactsComplianceResult(
        checked=True,
        violation_count=1,
        blocking_violation_count=0,
        violations=[
            {"fact_key": "k", "fact_statement": "s", "violation_text": "t", "severity": "warning"}
        ],
    )

    assert result.blocking_violation_count < FACTS_COMPLIANCE_BLOCK_THRESHOLD


def test_story_facts_compliance_at_threshold_triggers_revision():
    """At threshold: one blocking fact violation is enough to trigger revision."""
    _, repo = _make_db()
    project_id = "proj_threshold"
    _seed_project(repo, project_id, chapter_number=2)
    _seed_story_facts(repo, project_id, [
        {"fact_key": f"fact_{i}", "subject": "林泽", "attribute": f"attr_{i}"}
        for i in range(5)
    ])

    from novel_factory.agents.editor import EditorAgent

    violations = [
        {
            "fact_key": f"fact_{i}",
            "fact_statement": f"林泽的attr_{i}为X",
            "violation_text": f"正文把林泽写成了Y",
            "severity": "blocking",
        }
        for i in range(FACTS_COMPLIANCE_BLOCK_THRESHOLD)
    ]
    stub_llm = StubLLMProvider([{"violations": violations}])
    agent = EditorAgent(repo, stub_llm)
    inputs = EditorInputs(
        project_id=project_id,
        chapter_number=2,
        chapter={},
        content="章节内容，林泽登场",
        llm_mode="real",
    )

    result = agent._run_story_facts_compliance(inputs)

    assert result.checked is True
    assert result.blocking_violation_count >= FACTS_COMPLIANCE_BLOCK_THRESHOLD


def test_editor_result_always_includes_story_facts_compliance_field():
    """Editor result dict always contains story_facts_compliance with correct schema."""
    _, repo = _make_db()
    project_id = "proj_editor_field"
    chapter_number = 1

    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Test", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, chapter_number, "第一章", "polished", "章节内容" * 100, 400),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (project_id, chapter_number, "目标", '[]', '[]', '[]', "hook", 2500),
    )
    conn.commit()
    conn.close()

    from novel_factory.agents.editor import EditorAgent

    editor_response = {
        "pass": True,
        "score": 85,
        "scores": {"setting": 22, "logic": 23, "poison": 18, "text": 13, "pacing": 13},
        "issues": [],
        "suggestions": [],
        "revision_target": None,
        "state_card": {
            "summary": "test",
            "new_facts": [],
            "character_status": {},
            "suspense_hooks": [],
        },
    }
    stub_llm = StubLLMProvider([editor_response])
    agent = EditorAgent(repo, stub_llm)

    state: FactoryState = {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "chapter_status": ChapterStatus.POLISHED.value,
        "workflow_run_id": "test-run-v6614",
        "llm_mode": "stub",
        "retry_count": 0,
    }

    result = agent.run(state)

    assert "story_facts_compliance" in result
    compliance = result["story_facts_compliance"]
    assert "checked" in compliance
    assert "violation_count" in compliance
    assert "blocking_violation_count" in compliance
    assert "violations" in compliance

    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT content_json FROM agent_artifacts "
            "WHERE workflow_run_id=? AND agent_id='editor' "
            "AND artifact_type='review' ORDER BY created_at DESC LIMIT 1",
            ("test-run-v6614",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    artifact = json.loads(row["content_json"])
    assert "story_facts_compliance" in artifact
    assert artifact["story_facts_compliance"] == compliance


# ── P3: memory context audit trail ───────────────────────────────


def test_build_for_planner_audit_fields_missing_batch():
    """Audit dict derived from bundle is 'missing' when no trusted batch exists."""
    _, repo = _make_db()
    project_id = "proj_audit_missing"
    _seed_project(repo, project_id, chapter_number=2)

    builder = AgentContextBuilder(repo)
    bundle = builder.build_for_planner(project_id, chapter_number=2)

    audit = build_memory_context_audit(2, bundle)

    assert audit["batch_status"] == "missing"
    assert audit["memory_context_degraded"] is True
    assert audit["batch_id"] is None
    assert audit["memory_items_count"] == 0


def test_build_for_planner_audit_fields_trusted_batch():
    """Audit dict is 'trusted' when a trusted batch exists for the previous chapter."""
    _, repo = _make_db()
    project_id = "proj_audit_trusted"
    _seed_project(repo, project_id, chapter_number=2)
    batch_id = _seed_trusted_memory_batch(repo, project_id, chapter_number=1)

    builder = AgentContextBuilder(repo)
    bundle = builder.build_for_planner(project_id, chapter_number=2)

    audit = build_memory_context_audit(2, bundle)

    assert audit["batch_status"] == "trusted"
    assert audit["memory_context_degraded"] is False
    assert audit["batch_id"] == batch_id


def test_build_for_planner_audit_fields_chapter_one_not_applicable():
    """Chapter 1 has no previous memory to consume, so audit must not claim trusted."""
    _, repo = _make_db()
    project_id = "proj_audit_ch1"
    _seed_project(repo, project_id, chapter_number=1)

    builder = AgentContextBuilder(repo)
    bundle = builder.build_for_planner(project_id, chapter_number=1)
    audit = build_memory_context_audit(1, bundle)

    assert audit["batch_status"] == "not_applicable"
    assert audit["memory_context_degraded"] is False
    assert audit["batch_id"] is None
    assert audit["memory_items_count"] == 0


def test_memory_context_degraded_does_not_affect_status_flow():
    """memory_context_degraded is annotation-only — no chapter_status/revision fields on bundle."""
    bundle = AgentContextBundle()
    bundle.memory_context_degraded = True

    formatted = format_context_bundle_for_prompt(bundle, agent_name="author")
    assert "记忆上下文降级" in formatted

    # Bundle must not have any workflow-state fields
    assert not hasattr(bundle, "chapter_status")
    assert not hasattr(bundle, "requires_human")
    assert not hasattr(bundle, "revision_target")


def test_story_facts_compliance_result_schema():
    """StoryFactsComplianceResult.to_dict() always returns all four required keys."""
    r = StoryFactsComplianceResult()
    d = r.to_dict()

    assert set(d.keys()) == {"checked", "violation_count", "blocking_violation_count", "violations"}
    assert d["checked"] is False
    assert d["violations"] == []


def test_facts_compliance_block_threshold_value():
    """A single explicit blocking fact violation should block publishing."""
    assert FACTS_COMPLIANCE_BLOCK_THRESHOLD == 1
