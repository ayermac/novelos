"""v6.10.5: Story Contract models, fallback derivation, and backward compatibility tests."""

from __future__ import annotations

import json
import pytest

from novel_factory.models.creative_contracts import (
    CoreLoopStep,
    SupportingMechanism,
    DriftRule,
    StoryContract,
    ProjectLaunchProfile,
    GenreContract,
    GenreProfile,
    PayoffCadence,
    PressureLimits,
)
from novel_factory.models.chapter_contracts import (
    ChapterBrief,
    ChapterBriefTier1,
    ChapterBriefTier2,
)
from novel_factory.models.creative_ledgers import ChapterContractMetrics
from novel_factory.quality.core_loop_checker import derive_fallback_story_contract


# ── StoryContract model tests ────────────────────────────────────


class TestStoryContractModels:
    """Test StoryContract and related model schemas."""

    def test_core_loop_step_schema(self):
        step = CoreLoopStep(id="trigger", label="触发签到", payoff_type="reward")
        assert step.id == "trigger"
        assert step.label == "触发签到"
        assert step.required is True
        assert step.payoff_type == "reward"
        assert step.description == ""

    def test_supporting_mechanism_schema(self):
        mech = SupportingMechanism(id="countdown", label="倒计时")
        assert mech.allowed_role == "pressure"
        assert mech.must_serve_core_loop is True

    def test_drift_rule_schema(self):
        rule = DriftRule(id="r1", description="不能替代核心循环")
        assert rule.severity == "warning"
        assert rule.window_chapters == 1
        assert rule.threshold == 1

    def test_story_contract_schema(self):
        contract = StoryContract(
            project_id="test_proj",
            core_promise="签到获得奖励",
            core_loop=[
                CoreLoopStep(id="s1", label="签到"),
                CoreLoopStep(id="s2", label="获得奖励"),
            ],
            supporting_mechanisms=[
                SupportingMechanism(id="m1", label="倒计时"),
            ],
            payoff_types=["reward", "power_up"],
            drift_rules=[
                DriftRule(id="d1", description="压力不能替代"),
            ],
            cadence={"minor_payoff": 1, "visible_upgrade": 3},
            status="draft",
        )
        assert contract.project_id == "test_proj"
        assert len(contract.core_loop) == 2
        assert len(contract.supporting_mechanisms) == 1
        assert len(contract.drift_rules) == 1
        assert contract.status == "draft"
        assert contract.version == "1.0.0"

    def test_story_contract_defaults(self):
        contract = StoryContract()
        assert contract.project_id == ""
        assert contract.core_promise == ""
        assert contract.core_loop == []
        assert contract.supporting_mechanisms == []
        assert contract.payoff_types == []
        assert contract.drift_rules == []
        assert contract.cadence == {}
        assert contract.status == "draft"

    def test_story_contract_json_roundtrip(self):
        contract = StoryContract(
            project_id="proj1",
            core_promise="test promise",
            core_loop=[CoreLoopStep(id="s1", label="step 1")],
        )
        data = contract.model_dump()
        restored = StoryContract(**data)
        assert restored.project_id == "proj1"
        assert restored.core_promise == "test promise"
        assert len(restored.core_loop) == 1
        assert restored.core_loop[0].id == "s1"


# ── Backward compatibility tests ─────────────────────────────────


class TestBackwardCompatibility:
    """Ensure old models still work without new fields."""

    def test_chapter_brief_tier1_new_fields_default(self):
        tier1 = ChapterBriefTier1(
            chapter_goal="推进剧情",
            reader_payoff="主角获胜",
        )
        assert tier1.core_loop_target == ""
        assert tier1.primary_payoff == ""
        assert tier1.payoff_evidence_plan == ""

    def test_chapter_brief_tier2_new_fields_default(self):
        tier2 = ChapterBriefTier2(pressure_budget="中等")
        assert tier2.supporting_mechanisms_used == []
        assert tier2.new_mechanisms_allowed == []
        assert tier2.drift_risks == []
        assert tier2.contract_checklist == []

    def test_chapter_brief_backward_compat(self):
        """Old brief without new fields should deserialize fine."""
        old_data = {
            "tier1": {
                "chapter_goal": "test",
                "reader_payoff": "payoff",
                "protagonist_agency": "active",
                "forbidden_moves": ["no_deus_ex"],
            },
            "tier2": {
                "pressure_budget": "high",
                "payoff_budget": "medium",
            },
        }
        brief = ChapterBrief(**old_data)
        assert brief.tier1.chapter_goal == "test"
        assert brief.tier1.core_loop_target == ""  # new field defaulted
        assert brief.tier2.pressure_budget == "high"
        assert brief.tier2.supporting_mechanisms_used == []  # new field defaulted

    def test_chapter_brief_with_new_fields(self):
        """New brief with story contract fields."""
        data = {
            "tier1": {
                "chapter_goal": "test",
                "reader_payoff": "payoff",
                "protagonist_agency": "active",
                "core_loop_target": "cash_out",
                "primary_payoff": "主角获得奖励",
                "payoff_evidence_plan": "在第3个场景中写出奖励使用",
            },
            "tier2": {
                "pressure_budget": "medium",
                "supporting_mechanisms_used": ["countdown"],
                "new_mechanisms_allowed": [],
                "drift_risks": ["pressure_dominance"],
                "contract_checklist": ["是否完成核心兑现", "辅助机制是否服务核心"],
            },
        }
        brief = ChapterBrief(**data)
        assert brief.tier1.core_loop_target == "cash_out"
        assert brief.tier1.primary_payoff == "主角获得奖励"
        assert "countdown" in brief.tier2.supporting_mechanisms_used
        assert "是否完成核心兑现" in brief.tier2.contract_checklist


# ── Fallback derivation tests ────────────────────────────────────


class TestFallbackDerivation:
    """Test deriving StoryContract from existing launch_profile + genre_contract."""

    def test_fallback_from_launch_profile(self):
        """Fallback should use primary_payoff_loop as core_promise."""
        lp = {
            "primary_payoff_loop": "签到获得可见奖励，用奖励反制敌人",
            "core_hook": "开局签到就无敌",
        }
        contract = derive_fallback_story_contract("proj1", lp, None)
        assert contract.project_id == "proj1"
        assert "签到" in contract.core_promise
        assert contract.status == "fallback"
        assert len(contract.core_loop) >= 4  # default template

    def test_fallback_from_genre_contract(self):
        """Fallback should derive core_loop from must_have_beats."""
        gc = {
            "must_have_beats": ["开局危机", "获得金手指", "首次反制", "阶段性胜利"],
            "forbidden_drift": ["不能长期被动"],
            "payoff_cadence": {
                "minor_payoff": "每章",
                "visible_upgrade": "每3章",
                "public_reversal": "每5章",
            },
        }
        contract = derive_fallback_story_contract("proj2", None, gc)
        assert len(contract.core_loop) == 4
        assert contract.core_loop[0].label == "开局危机"
        assert contract.cadence["minor_payoff"] == 1
        assert contract.cadence["visible_upgrade"] == 3

    def test_fallback_from_both(self):
        """Fallback should combine launch_profile and genre_contract."""
        lp = {"primary_payoff_loop": "升级打怪"}
        gc = {
            "must_have_beats": ["突破", "战斗", "奖励"],
            "forbidden_drift": ["不能偏离升级"],
        }
        contract = derive_fallback_story_contract("proj3", lp, gc)
        assert contract.core_promise == "升级打怪"
        assert len(contract.core_loop) == 3
        assert len(contract.drift_rules) >= 1

    def test_fallback_no_contracts(self):
        """Fallback with no existing contracts should still produce a valid contract."""
        contract = derive_fallback_story_contract("proj4", None, None)
        assert contract.project_id == "proj4"
        assert contract.core_promise == ""
        assert len(contract.core_loop) >= 4  # default template
        assert contract.status == "fallback"


# ── ChapterContractMetrics tests ─────────────────────────────────


class TestChapterContractMetrics:
    """Test ChapterContractMetrics model."""

    def test_metrics_schema(self):
        metrics = ChapterContractMetrics(
            chapter_number=10,
            core_payoff_present=True,
            payoff_type="reward",
            core_loop_steps_completed=["cash_out", "reaction"],
            supporting_mechanisms_used=["countdown"],
            dominant_mechanism="",
            new_mechanisms_introduced=[],
            protagonist_agency=True,
            contract_drift_warnings=[],
            contract_score=85.0,
        )
        assert metrics.chapter_number == 10
        assert metrics.core_payoff_present is True
        assert metrics.contract_score == 85.0

    def test_metrics_defaults(self):
        metrics = ChapterContractMetrics()
        assert metrics.chapter_number == 0
        assert metrics.core_payoff_present is False
        assert metrics.protagonist_agency is True
        assert metrics.contract_score == 0.0
