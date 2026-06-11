"""v6.10.5: Core Loop Checker tests.

Tests the deterministic contract compliance checking:
- core payoff present/missing
- supporting mechanism dominance
- new mechanism budget
- protagonist agency
- trend checking (payoff gap, pressure streak)
- drift rule evaluation
"""

from __future__ import annotations

import pytest

from novel_factory.models.creative_contracts import (
    StoryContract,
    CoreLoopStep,
    SupportingMechanism,
    DriftRule,
)
from novel_factory.models.chapter_contracts import (
    ChapterBrief,
    ChapterBriefTier1,
    ChapterBriefTier2,
)
from novel_factory.models.creative_ledgers import ChapterContractMetrics
from novel_factory.quality.core_loop_checker import (
    check_core_loop_compliance,
    derive_fallback_story_contract,
)


# ── Fixtures ─────────────────────────────────────────────────────


def _make_contract(
    core_loop: list[CoreLoopStep] | None = None,
    supporting_mechanisms: list[SupportingMechanism] | None = None,
    drift_rules: list[DriftRule] | None = None,
    payoff_types: list[str] | None = None,
) -> StoryContract:
    if core_loop is None:
        core_loop = [
            CoreLoopStep(id="trigger", label="触发签到"),
            CoreLoopStep(id="action", label="完成签到"),
            CoreLoopStep(id="reward", label="获得奖励"),
            CoreLoopStep(id="cash_out", label="兑现奖励"),
        ]
    if supporting_mechanisms is None:
        supporting_mechanisms = [
            SupportingMechanism(id="countdown", label="倒计时"),
        ]
    if drift_rules is None:
        drift_rules = [
            DriftRule(id="pressure_not_primary", description="压力不能替代核心循环", window_chapters=2),
            DriftRule(id="payoff_within_window", description="连续2章必须有核心兑现", window_chapters=2),
        ]
    if payoff_types is None:
        payoff_types = ["reward", "power_up"]
    return StoryContract(
        project_id="test_proj",
        core_promise="签到获得奖励",
        core_loop=core_loop,
        supporting_mechanisms=supporting_mechanisms,
        payoff_types=payoff_types,
        drift_rules=drift_rules,
    )


def _make_brief(
    core_loop_target: str = "cash_out",
    reader_payoff: str = "获得签到奖励",
    primary_payoff: str = "",
    supporting_mechanisms_used: list[str] | None = None,
    new_mechanisms_allowed: list[str] | None = None,
) -> ChapterBrief:
    return ChapterBrief(
        tier1=ChapterBriefTier1(
            chapter_goal="完成签到并兑现",
            reader_payoff=reader_payoff,
            protagonist_agency="主动选择签到",
            core_loop_target=core_loop_target,
            primary_payoff=primary_payoff or reader_payoff,
            payoff_evidence_plan="在场景3中写出奖励使用",
        ),
        tier2=ChapterBriefTier2(
            supporting_mechanisms_used=supporting_mechanisms_used or [],
            new_mechanisms_allowed=new_mechanisms_allowed or [],
            drift_risks=[],
            contract_checklist=["是否完成核心兑现"],
        ),
    )


# ── Core payoff tests ────────────────────────────────────────────


class TestCorePayoffPresent:
    """Test core payoff detection."""

    def test_payoff_from_brief_reader_payoff(self):
        """Brief with reader_payoff should signal payoff present."""
        contract = _make_contract()
        brief = _make_brief(reader_payoff="主角获得签到奖励，实力提升")
        content = "普通章节内容，没有特殊关键词。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.core_payoff_present is True

    def test_payoff_from_brief_primary_payoff(self):
        """Brief with primary_payoff should signal payoff present."""
        contract = _make_contract()
        brief = ChapterBrief(
            tier1=ChapterBriefTier1(
                chapter_goal="test",
                reader_payoff="",
                primary_payoff="获得珍贵丹药",
            ),
        )
        content = "普通章节内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.core_payoff_present is True

    def test_payoff_from_content_keywords(self):
        """Content with multiple payoff keywords should signal present."""
        contract = _make_contract()
        content = "主角获得了珍贵的奖励，实力大幅提升。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract,
        )
        assert result.core_payoff_present is True

    def test_payoff_missing(self):
        """No payoff evidence should signal missing."""
        contract = _make_contract()
        brief = ChapterBrief(
            tier1=ChapterBriefTier1(
                chapter_goal="铺垫危机",
                reader_payoff="",  # empty
            ),
        )
        content = "危机四伏，主角陷入困境，被迫面对强敌。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.core_payoff_present is False
        assert any("核心兑现" in w for w in result.warnings)


# ── Supporting mechanism dominance tests ─────────────────────────


class TestSupportingMechanismDominance:
    """Test supporting mechanism dominance detection."""

    def test_dominance_pressure_heavy_no_payoff(self):
        """Heavy pressure keywords with no payoff should flag dominance."""
        contract = _make_contract()
        content = "危机四伏，追杀不断，倒计时逼近，困境重重，主角被迫面对绝境。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract,
        )
        assert result.supporting_mechanism_dominance is True

    def test_no_dominance_balanced_content(self):
        """Balanced content with both pressure and payoff should not flag."""
        contract = _make_contract()
        content = "面对危机，主角主动反击，获得胜利，收获奖励。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract,
        )
        assert result.supporting_mechanism_dominance is False

    def test_dominance_from_brief(self):
        """Brief with many supporting mechanisms but no core_loop_target."""
        contract = _make_contract()
        brief = ChapterBrief(
            tier1=ChapterBriefTier1(chapter_goal="test", reader_payoff="test"),
            tier2=ChapterBriefTier2(
                supporting_mechanisms_used=["countdown", "debt", "mystery"],
            ),
        )
        # Clear core_loop_target to trigger dominance
        brief.tier1.core_loop_target = ""
        content = "普通内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.supporting_mechanism_dominance is True


# ── New mechanism budget tests ───────────────────────────────────


class TestNewMechanismBudget:
    """Test new mechanism introduction budget."""

    def test_within_budget(self):
        """Brief with 0 new mechanisms should be within budget."""
        contract = _make_contract()
        brief = _make_brief(new_mechanisms_allowed=[])
        content = "普通章节内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.new_mechanism_count == 0

    def test_over_budget_from_brief(self):
        """Brief with 3 new mechanisms should be over budget."""
        contract = _make_contract()
        brief = _make_brief(new_mechanisms_allowed=["m1", "m2", "m3"])
        content = "普通章节内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.new_mechanism_count == 3


# ── Protagonist agency tests ────────────────────────────────────


class TestProtagonistAgency:
    """Test protagonist agency detection."""

    def test_agency_present_from_brief(self):
        """Brief with protagonist_agency should signal present."""
        contract = _make_contract()
        brief = _make_brief()
        content = "普通内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.protagonist_agency_present is True

    def test_agency_present_from_content(self):
        """Content with active keywords should signal agency present."""
        contract = _make_contract()
        content = "主角主动决定出手反击，主导了整个局面。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract,
        )
        assert result.protagonist_agency_present is True

    def test_agency_gap_from_content(self):
        """Content with passive keywords and no active should flag gap."""
        contract = _make_contract()
        brief = ChapterBrief(tier1=ChapterBriefTier1(chapter_goal="test", reader_payoff="test"))
        content = "主角被迫无奈，无力反抗，只能任由摆布，被控制被支配。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        # Should detect agency gap
        assert any(s.drift_type == "protagonist_agency_gap" for s in result.drift_signals)


# ── Trend checking tests ─────────────────────────────────────────


class TestTrendChecking:
    """Test trend-based drift detection."""

    def test_payoff_gap_trend(self):
        """Recent chapters without payoff should trigger payoff_gap."""
        contract = _make_contract()
        recent = [
            ChapterContractMetrics(chapter_number=3, core_payoff_present=False),
            ChapterContractMetrics(chapter_number=4, core_payoff_present=False),
        ]
        content = "危机加深，压力升级。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, recent_contract_metrics=recent,
        )
        payoff_gap_signals = [s for s in result.drift_signals if s.drift_type == "payoff_gap"]
        assert len(payoff_gap_signals) > 0

    def test_no_payoff_gap_with_recent_payoff(self):
        """Recent chapter with payoff should not trigger gap."""
        contract = _make_contract()
        recent = [
            ChapterContractMetrics(chapter_number=3, core_payoff_present=True),
            ChapterContractMetrics(chapter_number=4, core_payoff_present=True),
        ]
        content = "普通章节内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, recent_contract_metrics=recent,
        )
        payoff_gap_signals = [s for s in result.drift_signals if s.drift_type == "payoff_gap"]
        assert len(payoff_gap_signals) == 0


# ── Drift rule evaluation tests ─────────────────────────────────


class TestDriftRuleEvaluation:
    """Test contract drift rule evaluation."""

    def test_pressure_not_primary_rule(self):
        """Pressure dominance should trigger pressure_not_primary rule."""
        contract = _make_contract(
            drift_rules=[
                DriftRule(id="pressure_not_primary", description="压力不能替代核心循环", severity="warning"),
            ]
        )
        content = "危机四伏，追杀不断，倒计时逼近，困境重重。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract,
        )
        dominance_signals = [s for s in result.drift_signals if s.drift_type == "pressure_mechanism_dominance"]
        assert len(dominance_signals) > 0

    def test_new_mechanism_budget_rule(self):
        """Exceeding mechanism budget should trigger rule."""
        contract = _make_contract(
            drift_rules=[
                DriftRule(id="new_mechanism_budget", description="单章新增不超过1个", severity="warning", threshold=1),
            ]
        )
        brief = _make_brief(new_mechanisms_allowed=["m1", "m2"])
        content = "普通内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        overload_signals = [s for s in result.drift_signals if s.drift_type == "new_mechanism_overload"]
        assert len(overload_signals) > 0


# ── Score and pass/fail tests ────────────────────────────────────


class TestScoreAndPassFail:
    """Test scoring and pass/fail determination."""

    def test_clean_chapter_passes(self):
        """Chapter with payoff and no drift should pass with high score."""
        contract = _make_contract()
        brief = _make_brief()
        content = "主角完成签到，获得奖励，实力提升，敌人受到反噬。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.passed is True
        assert result.score >= 80

    def test_multiple_warnings_lower_score(self):
        """Multiple warnings should lower score but still pass."""
        contract = _make_contract()
        content = "危机四伏，追杀不断，倒计时逼近，困境重重。"  # pressure heavy

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract,
        )
        # Should have warnings but still pass (no blocking by default)
        assert len(result.warnings) > 0
        assert result.score < 100

    def test_contract_metrics_generated(self):
        """Result should include contract metrics for ledger persistence."""
        contract = _make_contract()
        brief = _make_brief()
        content = "主角获得奖励。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert result.contract_metrics is not None
        assert result.contract_metrics.chapter_number == 5
        assert result.contract_metrics.core_payoff_present is True


# ── Core loop steps tests ────────────────────────────────────────


class TestCoreLoopSteps:
    """Test core loop step identification."""

    def test_steps_from_brief(self):
        """Brief core_loop_target should map to contract steps."""
        contract = _make_contract()
        brief = _make_brief(core_loop_target="cash_out")
        content = "普通内容。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract, chapter_brief=brief,
        )
        assert "cash_out" in result.core_loop_steps_completed

    def test_steps_from_content(self):
        """Content matching step labels should detect steps."""
        contract = _make_contract()
        content = "主角完成了签到，获得奖励后兑现了权力。"

        result = check_core_loop_compliance(
            project_id="test", chapter_number=5, content=content,
            story_contract=contract,
        )
        # Should detect some steps from content
        assert len(result.core_loop_steps_completed) > 0
