"""v6.10.5: Workflow contract injection tests.

Tests:
- Context builder loads and formats StoryContract for each agent role
- Agent plain-text paths receive contract context
- _check_core_loop_compliance helper integrates with quality_gate_node
- Core loop compliance stores contract metrics in ledger
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.models.creative_contracts import (
    StoryContract,
    CoreLoopStep,
    SupportingMechanism,
    DriftRule,
)
from novel_factory.llm.provider import LLMProvider


class StubLLMProvider(LLMProvider):
    """Stub LLM for testing."""

    def __init__(self):
        pass

    def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None, max_retries=None, **kwargs):
        return {"content": "stub response"}

    def invoke_text(self, messages, temperature=None, max_tokens=None, max_retries=None, **kwargs):
        return "stub response"

    def invoke_text_stream(self, messages, temperature=None, max_tokens=None, agent_id="unknown", **kwargs):
        yield "stub response"


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture()
def repo(db_path):
    return Repository(db_path)


def _seed_project(repo, project_id="test_proj"):
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, 1, "第一章 测试", "polished", "主角完成签到，获得奖励，实力大幅提升。", 30),
    )
    conn.commit()
    conn.close()


def _seed_story_contract(repo, project_id="test_proj"):
    contract = StoryContract(
        project_id=project_id,
        core_promise="签到获得奖励",
        core_loop=[
            CoreLoopStep(id="trigger", label="触发签到"),
            CoreLoopStep(id="action", label="完成签到"),
            CoreLoopStep(id="reward", label="获得奖励"),
            CoreLoopStep(id="cash_out", label="兑现奖励"),
        ],
        supporting_mechanisms=[
            SupportingMechanism(id="countdown", label="倒计时"),
        ],
        payoff_types=["reward", "power_up"],
        drift_rules=[
            DriftRule(id="pressure_not_primary", description="辅助机制不能替代核心循环"),
        ],
        status="active",
    )
    repo.upsert_creative_contract(
        project_id=project_id,
        contract_type="story_contract",
        contract_data=contract.model_dump(),
    )
    return contract


def _seed_blocking_story_contract(repo, project_id="test_proj", status="active"):
    contract = StoryContract(
        project_id=project_id,
        core_promise="签到获得奖励",
        core_loop=[
            CoreLoopStep(id="trigger", label="触发签到"),
            CoreLoopStep(id="reward", label="获得奖励"),
        ],
        supporting_mechanisms=[
            SupportingMechanism(id="countdown", label="倒计时"),
        ],
        drift_rules=[
            DriftRule(
                id="pressure_not_primary",
                description="辅助机制不能替代核心循环",
                severity="blocking",
            ),
        ],
        status=status,
    )
    repo.upsert_creative_contract(
        project_id=project_id,
        contract_type="story_contract",
        contract_data=contract.model_dump(),
    )
    return contract


def _seed_chapter_brief(repo, project_id="test_proj", chapter_number=1):
    brief_data = {
        "tier1": {
            "chapter_goal": "完成签到并兑现",
            "reader_payoff": "主角获得签到奖励",
            "protagonist_agency": "主动选择签到",
            "core_loop_target": "cash_out",
            "primary_payoff": "获得签到奖励",
            "payoff_evidence_plan": "在场景3中写出奖励使用",
        },
        "tier2": {
            "supporting_mechanisms_used": ["countdown"],
            "new_mechanisms_allowed": [],
            "drift_risks": [],
            "contract_checklist": ["是否完成核心兑现"],
        },
    }
    repo.upsert_chapter_brief(project_id, chapter_number, brief_data)
    return brief_data


# ── Context builder tests ────────────────────────────────────────


class TestContextBuilderStoryContract:
    """Test AgentContextBuilder loads and formats story contract context."""

    def test_builder_author_with_story_contract(self, db_path, repo):
        """Author context bundle includes story_contract_context."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder

        _seed_project(repo)
        _seed_story_contract(repo)
        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_author("test_proj", 1)

        assert len(bundle.story_contract_context) > 0
        text = "\n".join(item.text for item in bundle.story_contract_context)
        assert "核心承诺" in text or "核心循环" in text

    def test_builder_planner_with_story_contract(self, db_path, repo):
        """Planner context bundle includes story_contract_context."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder

        _seed_project(repo)
        _seed_story_contract(repo)
        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_planner("test_proj", 1)

        assert len(bundle.story_contract_context) > 0

    def test_builder_editor_with_story_contract(self, db_path, repo):
        """Editor context bundle includes story_contract_context."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder

        _seed_project(repo)
        _seed_story_contract(repo)
        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_editor("test_proj", 1)

        assert len(bundle.story_contract_context) > 0

    def test_builder_polisher_with_story_contract(self, db_path, repo):
        """Polisher context bundle includes story_contract_context."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder

        _seed_project(repo)
        _seed_story_contract(repo)
        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_polisher("test_proj", 1)

        assert len(bundle.story_contract_context) > 0

    def test_builder_without_story_contract(self, db_path, repo):
        """Context builder works without story contract (fallback derived)."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder

        _seed_project(repo)
        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_author("test_proj", 1)

        # Should still work — either fallback or empty
        assert isinstance(bundle.story_contract_context, list)

    def test_format_context_bundle_includes_contract_section(self, db_path, repo):
        """format_context_bundle_for_prompt renders story contract section."""
        from novel_factory.agent_runtime.context_builder import (
            AgentContextBuilder,
            format_context_bundle_for_prompt,
        )

        _seed_project(repo)
        _seed_story_contract(repo)
        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_author("test_proj", 1)

        formatted = format_context_bundle_for_prompt(bundle, "author")
        assert "故事合同" in formatted or "Story Contract" in formatted


# ── Agent plain-text path tests ─────────────────────────────────


class TestAgentPlainTextContractInjection:
    """Test that agent build_context plain-text paths include story contract."""

    def test_author_plain_text_includes_contract(self, db_path, repo):
        """AuthorAgent.build_context includes story contract context."""
        from novel_factory.agents.author import AuthorAgent

        _seed_project(repo)
        _seed_story_contract(repo)
        _seed_chapter_brief(repo)

        agent = AuthorAgent(repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })

        assert "核心循环" in context or "核心承诺" in context or "故事合同" in context

    def test_editor_plain_text_includes_contract(self, db_path, repo):
        """EditorAgent.build_context includes story contract context."""
        from novel_factory.agents.editor import EditorAgent

        _seed_project(repo)
        _seed_story_contract(repo)
        _seed_chapter_brief(repo)

        agent = EditorAgent(repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "content": "主角完成签到，获得奖励。",
        })

        assert "核心循环" in context or "核心承诺" in context or "故事合同" in context

    def test_planner_plain_text_includes_contract(self, db_path, repo):
        """PlannerAgent.build_context includes story contract context."""
        from novel_factory.agents.planner import PlannerAgent

        _seed_project(repo)
        _seed_story_contract(repo)

        agent = PlannerAgent(repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
        })

        assert "核心循环" in context or "核心承诺" in context or "故事合同" in context

    def test_polisher_plain_text_includes_contract(self, db_path, repo):
        """PolisherAgent.build_context includes story contract context."""
        from novel_factory.agents.polisher import PolisherAgent

        _seed_project(repo)
        _seed_story_contract(repo)

        agent = PolisherAgent(repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "content": "主角完成签到，获得奖励。",
        })

        assert "核心循环" in context or "核心承诺" in context or "故事合同" in context


# ── Quality gate integration tests ──────────────────────────────


class TestQualityGateCoreLoopIntegration:
    """Test _check_core_loop_compliance integration in quality_gate_node."""

    def test_check_core_loop_compliance_passes(self, db_path, repo):
        """Clean chapter with payoff passes core loop compliance."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)
        _seed_story_contract(repo)
        _seed_chapter_brief(repo)

        result = _check_core_loop_compliance(
            repo, "test_proj", 1,
            "主角完成签到，获得奖励，实力大幅提升。"
        )

        assert result["check_name"] == "core_loop_compliance"
        assert result["passed"] is True
        assert result["blocking_issues"] == []

    def test_check_core_loop_compliance_warns_on_missing_payoff(self, db_path, repo):
        """Chapter without payoff evidence produces advisory warnings."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)
        _seed_story_contract(repo)
        # No chapter brief seeded — payoff detection falls to content keywords

        result = _check_core_loop_compliance(
            repo, "test_proj", 1,
            "危机四伏，压力升级，主角陷入困境。"
        )

        assert result["check_name"] == "core_loop_compliance"
        assert len(result["advisory_issues"]) > 0
        # Default is advisory, not blocking
        assert result["blocking_issues"] == []

    def test_check_core_loop_compliance_stores_metrics(self, db_path, repo):
        """Core loop compliance stores contract metrics in ledger."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)
        _seed_story_contract(repo)
        _seed_chapter_brief(repo)

        _check_core_loop_compliance(
            repo, "test_proj", 1,
            "主角完成签到，获得奖励。"
        )

        # Verify metrics stored
        metrics = repo.get_chapter_contract_metrics("test_proj", limit=1)
        assert len(metrics) > 0
        assert metrics[0]["chapter_number"] == 1

    def test_check_core_loop_compliance_uses_fallback_contract(self, db_path, repo):
        """Core loop compliance works with fallback contract (no explicit story_contract)."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)
        # No story_contract seeded — should derive fallback

        result = _check_core_loop_compliance(
            repo, "test_proj", 1,
            "主角完成签到，获得奖励。"
        )

        assert result["check_name"] == "core_loop_compliance"
        assert result["diagnostics"]["contract_status"] == "fallback"

    def test_check_core_loop_compliance_detects_pressure_dominance(self, db_path, repo):
        """Pressure-heavy content without payoff flags supporting mechanism dominance."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)
        _seed_story_contract(repo)

        result = _check_core_loop_compliance(
            repo, "test_proj", 1,
            "危机四伏，追杀不断，倒计时逼近，困境重重，主角被迫面对绝境。"
        )

        assert result["diagnostics"]["supporting_mechanism_dominance"] is True
        assert len(result["priority_issues"]) > 0 or len(result["advisory_issues"]) > 0

    def test_check_core_loop_compliance_blocks_confirmed_contract(self, db_path, repo):
        """Confirmed/active contracts honor blocking drift rules."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)
        _seed_blocking_story_contract(repo)

        result = _check_core_loop_compliance(
            repo, "test_proj", 1,
            "危机四伏，追杀不断，倒计时逼近，困境重重，主角被迫面对绝境。"
        )

        assert result["passed"] is False
        assert result["blocking_issues"]
        assert result["diagnostics"]["contract_status"] == "active"

    def test_check_core_loop_compliance_draft_contract_does_not_block(self, db_path, repo):
        """Draft contracts report blocking drift as non-blocking until confirmed."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)
        _seed_blocking_story_contract(repo, status="draft")

        result = _check_core_loop_compliance(
            repo, "test_proj", 1,
            "危机四伏，追杀不断，倒计时逼近，困境重重，主角被迫面对绝境。"
        )

        assert result["passed"] is True
        assert result["blocking_issues"] == []
        assert result["diagnostics"]["contract_status"] == "draft"


# ── Backward compatibility tests ─────────────────────────────────


class TestBackwardCompatibilityWorkflow:
    """Test that old projects without story contract still work."""

    def test_context_builder_works_without_contract(self, db_path, repo):
        """Context builder works for projects with no story contract at all."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder

        _seed_project(repo)
        builder = AgentContextBuilder(repo)
        bundle = builder.build_for_author("test_proj", 1)

        # Should not raise — just empty or fallback
        assert isinstance(bundle.story_contract_context, list)

    def test_quality_gate_works_without_contract(self, db_path, repo):
        """Quality gate works for projects with no story contract."""
        from novel_factory.workflow.nodes import _check_core_loop_compliance

        _seed_project(repo)

        result = _check_core_loop_compliance(
            repo, "test_proj", 1,
            "普通章节内容。"
        )

        assert result["check_name"] == "core_loop_compliance"
        assert result["passed"] is True

    def test_agent_context_works_without_contract(self, db_path, repo):
        """Agent build_context works without story contract."""
        from novel_factory.agents.author import AuthorAgent

        _seed_project(repo)

        agent = AuthorAgent(repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })

        # Should not raise — just no contract section
        assert isinstance(context, str)
