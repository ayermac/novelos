"""v6.10.9: Core loop前置约束与事实锁感知 tests.

Covers the v6.10.9 feature set:
  - CoreLoopDesign model (Planner output constraint)
  - DialogueSlot model (Screenwriter output)
  - SceneBeat enhancement (is_reward_beat, dialogue_slots, character_states)
  - ChapterBrief enhancement (core_loop, dialogue_target_ratio, fact_locks)
  - BEAT_DESIGN issue category and revision classifier routing
  - determine_revision_target screenwriter routing
  - Editor context builder v6.10.9 beat field injection
  - Workflow routing for screenwriter revision target
"""

from __future__ import annotations

import pytest

from novel_factory.models.schemas import (
    CoreLoopDesign,
    DialogueSlot,
    SceneBeat,
    ChapterBrief,
    ScreenwriterOutput,
    PlannerOutput,
)
from novel_factory.models.quality import IssueCategory


# ──────────────────────────────────────────────────────────────────────
# T1: CoreLoopDesign model
# ──────────────────────────────────────────────────────────────────────


class TestCoreLoopDesign:
    """CoreLoopDesign model validation."""

    def test_default_values(self):
        """All fields have backward-compatible defaults."""
        cl = CoreLoopDesign()
        assert cl.reward_event_index == 1
        assert cl.reward_type == "ability"
        assert cl.reward_evidence == ""
        assert cl.protagonist_decision == ""

    def test_valid_reward_types(self):
        """All five reward types are accepted."""
        for rtype in ("ability", "intellect", "emotion", "identity", "resource"):
            cl = CoreLoopDesign(reward_type=rtype)
            assert cl.reward_type == rtype

    def test_invalid_reward_type_rejected(self):
        """Reward type must match the pattern."""
        with pytest.raises(Exception):
            CoreLoopDesign(reward_type="invalid_type")

    def test_reward_event_index_bounds(self):
        """reward_event_index must be 1-5."""
        CoreLoopDesign(reward_event_index=1)
        CoreLoopDesign(reward_event_index=5)
        with pytest.raises(Exception):
            CoreLoopDesign(reward_event_index=0)
        with pytest.raises(Exception):
            CoreLoopDesign(reward_event_index=6)

    def test_full_valid_object(self):
        """Full valid CoreLoopDesign with all fields."""
        cl = CoreLoopDesign(
            reward_event_index=2,
            reward_type="ability",
            reward_evidence="苏晚棠的魂源泄露停止，生命体征稳定",
            protagonist_decision="陆恒在魂源冲击剧痛下坚持引导，选择先救苏晚棠",
        )
        assert cl.reward_event_index == 2
        assert cl.reward_type == "ability"
        assert "苏晚棠" in cl.reward_evidence
        assert "陆恒" in cl.protagonist_decision


# ──────────────────────────────────────────────────────────────────────
# T2: DialogueSlot model
# ──────────────────────────────────────────────────────────────────────


class TestDialogueSlot:
    """DialogueSlot model validation."""

    def test_default_values(self):
        """All fields have backward-compatible defaults."""
        slot = DialogueSlot()
        assert slot.speakers == []
        assert slot.conflict_type == ""
        assert slot.key_line == ""
        assert slot.must_convey == ""

    def test_full_valid_object(self):
        """Full valid DialogueSlot."""
        slot = DialogueSlot(
            speakers=["陆恒", "苏晚棠"],
            conflict_type="信息差",
            must_convey="苏晚棠在昏迷中无意识地喊了一声'陆恒'",
        )
        assert len(slot.speakers) == 2
        assert slot.conflict_type == "信息差"


# ──────────────────────────────────────────────────────────────────────
# T3: SceneBeat enhancement
# ──────────────────────────────────────────────────────────────────────


class TestSceneBeatEnhanced:
    """SceneBeat v6.10.9 fields."""

    def test_backward_compatible_defaults(self):
        """Old-style SceneBeat without v6.10.9 fields still works."""
        beat = SceneBeat(sequence=1, scene_goal="test goal")
        assert beat.is_reward_beat is False
        assert beat.dialogue_slots == []
        assert beat.character_states == {}

    def test_reward_beat(self):
        """SceneBeat with is_reward_beat=True."""
        beat = SceneBeat(
            sequence=2,
            scene_goal="陆恒首次泵血，引导魂源拯救苏晚棠",
            is_reward_beat=True,
            character_states={
                "陆恒": "清醒，剧痛但坚持",
                "苏晚棠": "濒死，魂源泄露中",
            },
            dialogue_slots=[
                DialogueSlot(
                    speakers=["陆恒", "苏晚棠"],
                    conflict_type="信息差",
                    must_convey="苏晚棠在昏迷中无意识地喊了一声'陆恒'",
                )
            ],
        )
        assert beat.is_reward_beat is True
        assert "陆恒" in beat.character_states
        assert len(beat.dialogue_slots) == 1

    def test_screenwriter_output_with_enhanced_beats(self):
        """ScreenwriterOutput can contain enhanced beats."""
        output = ScreenwriterOutput(
            scene_beats=[
                SceneBeat(sequence=1, scene_goal="goal1"),
                SceneBeat(
                    sequence=2,
                    scene_goal="goal2",
                    is_reward_beat=True,
                    dialogue_slots=[
                        DialogueSlot(speakers=["A", "B"], conflict_type="立场对立")
                    ],
                ),
            ]
        )
        assert len(output.scene_beats) == 2
        assert output.scene_beats[1].is_reward_beat is True
        assert len(output.scene_beats[1].dialogue_slots) == 1


# ──────────────────────────────────────────────────────────────────────
# T4: ChapterBrief enhancement
# ──────────────────────────────────────────────────────────────────────


class TestChapterBriefEnhanced:
    """ChapterBrief v6.10.9 fields."""

    def test_backward_compatible_defaults(self):
        """Old-style ChapterBrief without v6.10.9 fields still works."""
        brief = ChapterBrief(objective="test")
        assert brief.core_loop.reward_event_index == 1
        assert brief.dialogue_target_ratio == 0.15
        assert brief.fact_locks == []

    def test_full_v6109_brief(self):
        """ChapterBrief with all v6.10.9 fields populated."""
        brief = ChapterBrief(
            objective="魂源统帅清零的陆恒被迫成为血池新核心",
            chapter_goal="陆恒完成首次泵血",
            required_events=[
                "陆恒接受新核身份，感知血池系统结构",
                "陆恒首次尝试泵血，成功引导魂源至苏晚棠",
                "陆恒发现陆璃有微弱反应",
            ],
            ending_hook="加密遗言揭示第二轮选核威胁",
            core_loop=CoreLoopDesign(
                reward_event_index=2,
                reward_type="ability",
                reward_evidence="苏晚棠的魂源泄露停止，生命体征稳定；陆恒感受到系统控制权从被动变为主动",
                protagonist_decision="陆恒在魂源冲击剧痛下坚持引导，选择先救苏晚棠而非自保",
            ),
            dialogue_target_ratio=0.15,
            fact_locks=[
                "陆璃：无呼吸，胸口无起伏，被LH-0427-F金属环锁于血池舱金属床",
                "苏晚棠：魂源持续泄露，处于濒死状态",
                "陆恒：魂源=0，统帅=0，神军沉寂",
            ],
        )
        assert brief.core_loop.reward_event_index == 2
        assert brief.core_loop.reward_type == "ability"
        assert len(brief.fact_locks) == 3
        assert "陆璃" in brief.fact_locks[0]

    def test_planner_output_with_v6109_fields(self):
        """PlannerOutput flat dict parsing includes v6.10.9 fields."""
        data = {
            "objective": "test objective",
            "chapter_goal": "test goal",
            "required_events": ["event1", "event2"],
            "core_loop": {
                "reward_event_index": 1,
                "reward_type": "emotion",
                "reward_evidence": "test evidence with enough characters",
                "protagonist_decision": "test decision made",
            },
            "dialogue_target_ratio": 0.20,
            "fact_locks": ["角色A: 状态描述"],
        }
        output = PlannerOutput(**data)
        assert output.chapter_brief.core_loop.reward_type == "emotion"
        assert output.chapter_brief.dialogue_target_ratio == 0.20
        assert len(output.chapter_brief.fact_locks) == 1


# ──────────────────────────────────────────────────────────────────────
# T5: BEAT_DESIGN issue category
# ──────────────────────────────────────────────────────────────────────


class TestBeatDesignCategory:
    """BEAT_DESIGN issue category in quality model."""

    def test_beat_design_in_enum(self):
        assert "BEAT_DESIGN" in IssueCategory.__members__
        assert IssueCategory.BEAT_DESIGN.value == "beat_design"


# ──────────────────────────────────────────────────────────────────────
# T6: Revision classifier — beat design routing
# ──────────────────────────────────────────────────────────────────────


class TestRevisionClassifierBeatDesign:
    """Revision classifier routes beat-design issues to screenwriter."""

    def test_core_loop_design_defect_routes_to_screenwriter(self):
        from novel_factory.validators.revision_classifier import classify_issue

        result = classify_issue("核心循环设计缺陷导致爽点标记缺失")
        assert result.category == IssueCategory.BEAT_DESIGN
        assert result.revision_target == "screenwriter"

    def test_beat_design_issue_routes_to_screenwriter(self):
        from novel_factory.validators.revision_classifier import classify_issue

        result = classify_issue("场景 beat 设计不完整")
        assert result.category == IssueCategory.BEAT_DESIGN
        assert result.revision_target == "screenwriter"

    def test_dialogue_slot_missing_routes_to_screenwriter(self):
        from novel_factory.validators.revision_classifier import classify_issue

        result = classify_issue("对白槽位缺失，无法支撑对白占比目标")
        assert result.revision_target == "screenwriter"

    def test_character_state_design_routes_to_screenwriter(self):
        from novel_factory.validators.revision_classifier import classify_issue

        result = classify_issue("角色状态设计与事实锁不一致")
        assert result.revision_target == "screenwriter"

    def test_classify_issues_batch_with_beat_design(self):
        from novel_factory.validators.revision_classifier import classify_issues

        result = classify_issues([
            "核心循环设计缺陷",
            "beat 设计不完整",
        ])
        assert result.dominant_target == "screenwriter"

    def test_beat_design_takes_priority_over_author_structural(self):
        """Beat design keywords should route to screenwriter, not author."""
        from novel_factory.validators.revision_classifier import classify_issue

        result = classify_issue("核心循环未标记，beat 层设计缺陷")
        assert result.revision_target == "screenwriter"


# ──────────────────────────────────────────────────────────────────────
# T7: determine_revision_target — screenwriter routing
# ──────────────────────────────────────────────────────────────────────


class TestDetermineRevisionTargetScreenwriter:
    """determine_revision_target routes beat-design issues to screenwriter."""

    def test_screenwriter_keyword_beat_design(self):
        from novel_factory.quality.editor_strategy import determine_revision_target

        target = determine_revision_target(
            issues=["beat 设计不完整，核心循环未标记"],
            llm_revision_target="author",
        )
        assert target == "screenwriter"

    def test_screenwriter_keyword_reward_missing(self):
        from novel_factory.quality.editor_strategy import determine_revision_target

        target = determine_revision_target(
            issues=["爽点标记缺失，is_reward_beat 未设置"],
            llm_revision_target="author",
        )
        assert target == "screenwriter"

    def test_screenwriter_keyword_dialogue_slots(self):
        from novel_factory.quality.editor_strategy import determine_revision_target

        target = determine_revision_target(
            issues=["对白槽位缺失"],
            llm_revision_target="polisher",
        )
        assert target == "screenwriter"

    def test_screenwriter_keyword_character_states(self):
        from novel_factory.quality.editor_strategy import determine_revision_target

        target = determine_revision_target(
            issues=["character_states 未标注角色物理状态"],
            llm_revision_target="author",
        )
        assert target == "screenwriter"

    def test_llm_target_screenwriter_passthrough(self):
        """LLM-provided screenwriter target passes through when no keyword match."""
        from novel_factory.quality.editor_strategy import determine_revision_target

        target = determine_revision_target(
            issues=["一些通用问题"],
            llm_revision_target="screenwriter",
        )
        assert target == "screenwriter"

    def test_planner_keywords_still_take_priority(self):
        """Planner keywords still route to planner, not screenwriter."""
        from novel_factory.quality.editor_strategy import determine_revision_target

        target = determine_revision_target(
            issues=["设定体系冲突"],
            llm_revision_target="screenwriter",
        )
        assert target == "planner"


# ──────────────────────────────────────────────────────────────────────
# T8: Workflow routing — screenwriter revision target
# ──────────────────────────────────────────────────────────────────────


class TestWorkflowRoutingScreenwriter:
    """Workflow routing supports screenwriter as revision target."""

    def test_valid_revision_targets_includes_screenwriter(self):
        from novel_factory.workflow.conditions import VALID_REVISION_TARGETS

        assert "screenwriter" in VALID_REVISION_TARGETS

    def test_route_by_revision_type_screenwriter(self):
        from novel_factory.workflow.conditions import route_by_revision_type

        state = {
            "quality_gate": {"revision_target": "screenwriter"},
            "chapter_status": "revision",
        }
        assert route_by_revision_type(state) == "screenwriter"

    def test_route_by_chapter_status_revision_screenwriter(self):
        from novel_factory.workflow.conditions import route_by_chapter_status

        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "screenwriter"},
        }
        assert route_by_chapter_status(state) == "screenwriter"


# ──────────────────────────────────────────────────────────────────────
# T9: Context builder — v6.10.9 beat field injection
# ──────────────────────────────────────────────────────────────────────


class TestContextBuilderBeatInjection:
    """Context builder injects v6.10.9 beat fields into Editor context."""

    def test_reward_beat_marker_in_context(self):
        """is_reward_beat=True should produce 【核心爽点 beat】 marker."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder
        from unittest.mock import MagicMock

        repo = MagicMock()
        repo.get_scene_beats.return_value = [
            {
                "sequence": 2,
                "scene_goal": "陆恒首次泵血",
                "conflict": "魂源冲击",
                "turn": "被动转主动",
                "hook": "苏晚棠稳定",
                "is_reward_beat": True,
                "character_states": {"陆恒": "清醒，剧痛"},
                "dialogue_slots": [
                    {
                        "speakers": ["陆恒", "苏晚棠"],
                        "conflict_type": "信息差",
                        "must_convey": "苏晚棠喊了一声'陆恒'",
                    }
                ],
            }
        ]
        builder = AgentContextBuilder(repo)
        items = builder._scene_beats_context("proj", 1)
        assert len(items) == 1
        text = items[0].text
        assert "【核心爽点 beat】" in text
        assert "角色状态:" in text
        assert "对白槽位1:" in text
        assert "信息差" in text

    def test_backward_compatible_beats_without_v6109_fields(self):
        """Old-style beats without v6.10.9 fields still render correctly."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder
        from unittest.mock import MagicMock

        repo = MagicMock()
        repo.get_scene_beats.return_value = [
            {
                "sequence": 1,
                "scene_goal": "test goal",
                "conflict": "test conflict",
                "turn": "test turn",
                "hook": "test hook",
            }
        ]
        builder = AgentContextBuilder(repo)
        items = builder._scene_beats_context("proj", 1)
        assert len(items) == 1
        text = items[0].text
        assert "test goal" in text
        assert "核心爽点" not in text
        assert "对白槽位" not in text

    def test_multiple_dialogue_slots(self):
        """Multiple dialogue slots are all rendered."""
        from novel_factory.agent_runtime.context_builder import AgentContextBuilder
        from unittest.mock import MagicMock

        repo = MagicMock()
        repo.get_scene_beats.return_value = [
            {
                "sequence": 1,
                "scene_goal": "test",
                "dialogue_slots": [
                    {"speakers": ["A", "B"], "conflict_type": "立场对立", "must_convey": "info1"},
                    {"speakers": ["C", "D"], "conflict_type": "潜台词", "must_convey": "info2"},
                    {"speakers": ["E", "F"], "conflict_type": "", "must_convey": ""},
                ],
            }
        ]
        builder = AgentContextBuilder(repo)
        items = builder._scene_beats_context("proj", 1)
        text = items[0].text
        assert "对白槽位1:" in text
        assert "对白槽位2:" in text
        assert "对白槽位3:" in text


# ──────────────────────────────────────────────────────────────────────
# T10: Version check
# ──────────────────────────────────────────────────────────────────────


class TestVersion:
    """Version should be 6.10.9."""

    def test_version_is_6109(self):
        from novel_factory.version import __version__

        assert __version__ == "6.10.18"


# ──────────────────────────────────────────────────────────────────────
# T11: Quality gate deterministic routing — beat-aware CORE_LOOP
# ──────────────────────────────────────────────────────────────────────


class TestQualityGateBeatAwareRouting:
    """quality_gate_node's _determine_revision_target routes CORE_LOOP
    issues to screenwriter when beat design is deficient."""

    def test_core_loop_no_reward_beat_routes_to_author(self):
        """CORE_LOOP_PAYOFF_MISSING + beats exist but no is_reward_beat → author.

        v6.10.9-fix: When beats are designed (exist) but none marked as reward,
        the issue is in content layer, not beat design. Route to author.
        """
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.CORE_LOOP_PAYOFF_MISSING],
            scene_beats=[
                {"sequence": 1, "scene_goal": "goal1"},
                {"sequence": 2, "scene_goal": "goal2"},
            ],
        )
        assert target == "author"

    def test_core_loop_no_beats_at_all_routes_to_screenwriter(self):
        """CORE_LOOP_PAYOFF_MISSING + no scene_beats at all → screenwriter."""
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.CORE_LOOP_PAYOFF_MISSING],
            scene_beats=None,
        )
        assert target == "screenwriter"

    def test_core_loop_with_reward_beat_routes_to_author(self):
        """CORE_LOOP_PAYOFF_MISSING + has is_reward_beat → author."""
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.CORE_LOOP_PAYOFF_MISSING],
            scene_beats=[
                {"sequence": 1, "scene_goal": "goal1"},
                {"sequence": 2, "scene_goal": "goal2", "is_reward_beat": True},
            ],
        )
        assert target == "author"

    def test_core_loop_drift_no_beats_routes_to_screenwriter(self):
        """CORE_LOOP_DRIFT_WARNING + no scene_beats → screenwriter."""
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.CORE_LOOP_DRIFT_WARNING],
            scene_beats=[],
        )
        assert target == "screenwriter"

    def test_core_loop_drift_no_beats_none_routes_to_screenwriter(self):
        """CORE_LOOP_DRIFT_WARNING + scene_beats=None → screenwriter."""
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.CORE_LOOP_DRIFT_WARNING],
            scene_beats=None,
        )
        assert target == "screenwriter"

    def test_death_penalty_still_routes_to_author(self):
        """Non-core-loop issues still route to author regardless of beats."""
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.DEATH_PENALTY],
            scene_beats=[{"sequence": 1, "scene_goal": "g"}],
        )
        assert target == "author"

    def test_story_facts_still_routes_to_author(self):
        """Story facts issues still route to author regardless of beats."""
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.STORY_FACTS_CONTRADICTION],
            scene_beats=[],
        )
        assert target == "author"

    def test_mixed_core_loop_and_death_penalty_routes_to_author(self):
        """When both CORE_LOOP and DEATH_PENALTY exist, DEATH_PENALTY wins."""
        from novel_factory.workflow.nodes import _determine_revision_target
        from novel_factory.quality.issue_codes import IssueCode

        target = _determine_revision_target(
            [IssueCode.CORE_LOOP_PAYOFF_MISSING, IssueCode.DEATH_PENALTY],
            scene_beats=[],
        )
        assert target == "author"

    def test_no_issue_codes_returns_none(self):
        """No issues → no revision target."""
        from novel_factory.workflow.nodes import _determine_revision_target

        target = _determine_revision_target([], scene_beats=[])
        assert target is None


# ──────────────────────────────────────────────────────────────────────
# T12: Polisher skip for non-polisher revisions
# ──────────────────────────────────────────────────────────────────────


class TestPolisherSkip:
    """route_after_agent skips Polisher when revision target is not polisher."""

    def test_author_revision_skips_polisher(self):
        """Revision target 'author' → skip_to_quality_gate."""
        from novel_factory.workflow.conditions import route_after_agent

        state = {
            "chapter_status": "drafted",
            "_revision_review": {"revision_target": "author", "score": 67},
        }
        assert route_after_agent(state) == "skip_to_quality_gate"

    def test_screenwriter_revision_skips_polisher(self):
        """Revision target 'screenwriter' → skip_to_quality_gate."""
        from novel_factory.workflow.conditions import route_after_agent

        state = {
            "chapter_status": "drafted",
            "_revision_review": {"revision_target": "screenwriter", "score": 67},
        }
        assert route_after_agent(state) == "skip_to_quality_gate"

    def test_polisher_revision_goes_to_polisher(self):
        """Revision target 'polisher' → next (polisher)."""
        from novel_factory.workflow.conditions import route_after_agent

        state = {
            "chapter_status": "drafted",
            "_revision_review": {"revision_target": "polisher", "score": 67},
        }
        assert route_after_agent(state) == "next"

    def test_no_revision_review_goes_to_polisher(self):
        """No revision review (fresh run) → next (polisher)."""
        from novel_factory.workflow.conditions import route_after_agent

        state = {"chapter_status": "drafted"}
        assert route_after_agent(state) == "next"

    def test_empty_revision_review_goes_to_polisher(self):
        """Empty revision review → next (polisher)."""
        from novel_factory.workflow.conditions import route_after_agent

        state = {"chapter_status": "drafted", "_revision_review": {}}
        assert route_after_agent(state) == "next"

    def test_requires_human_still_takes_priority(self):
        """requires_human overrides polisher skip."""
        from novel_factory.workflow.conditions import route_after_agent

        state = {
            "requires_human": True,
            "chapter_status": "drafted",
            "_revision_review": {"revision_target": "author"},
        }
        assert route_after_agent(state) == "human_review"

    def test_quality_gate_fail_still_takes_priority(self):
        """Quality gate retryable failures override polisher skip."""
        from novel_factory.workflow.conditions import route_after_agent

        state = {
            "chapter_status": "revision",
            "quality_gate": {"pass": False, "word_count_fail": True},
            "_revision_review": {"revision_target": "author"},
        }
        assert route_after_agent(state) == "revision_router"


# ──────────────────────────────────────────────────────────────────────
# T13: Score degradation detection
# ──────────────────────────────────────────────────────────────────────


class TestScoreDegradation:
    """route_by_review_result detects score degradation."""

    def test_score_degradation_escalates_to_human(self):
        """Score drops from 67 to 64 → human_review."""
        from novel_factory.workflow.conditions import route_by_review_result

        state = {
            "quality_gate": {"pass": False, "score": 64},
            "retry_count": 1,
            "max_retries": 3,
            "_revision_review": {"score": 67},
        }
        assert route_by_review_result(state) == "human_review"

    def test_score_improvement_allows_revision(self):
        """Score improves from 64 to 70 → revise."""
        from novel_factory.workflow.conditions import route_by_review_result

        state = {
            "quality_gate": {"pass": False, "score": 70},
            "retry_count": 1,
            "max_retries": 3,
            "_revision_review": {"score": 64},
        }
        assert route_by_review_result(state) == "revise"

    def test_same_score_allows_revision(self):
        """Score stays the same → revise."""
        from novel_factory.workflow.conditions import route_by_review_result

        state = {
            "quality_gate": {"pass": False, "score": 67},
            "retry_count": 1,
            "max_retries": 3,
            "_revision_review": {"score": 67},
        }
        assert route_by_review_result(state) == "revise"

    def test_first_retry_no_degradation_check(self):
        """retry_count=0 → no degradation check, revise."""
        from novel_factory.workflow.conditions import route_by_review_result

        state = {
            "quality_gate": {"pass": False, "score": 50},
            "retry_count": 0,
            "max_retries": 3,
            "_revision_review": {"score": 67},
        }
        assert route_by_review_result(state) == "revise"

    def test_no_previous_score_skips_check(self):
        """No previous score → no degradation check."""
        from novel_factory.workflow.conditions import route_by_review_result

        state = {
            "quality_gate": {"pass": False, "score": 50},
            "retry_count": 1,
            "max_retries": 3,
        }
        assert route_by_review_result(state) == "revise"

    def test_passing_review_ignores_degradation(self):
        """Passing review → memory_curator regardless of score."""
        from novel_factory.workflow.conditions import route_by_review_result

        state = {
            "quality_gate": {"pass": True, "score": 80},
            "retry_count": 1,
            "max_retries": 3,
            "_revision_review": {"score": 90},
        }
        assert route_by_review_result(state) == "memory_curator"

    def test_max_retries_still_escalates(self):
        """Max retries → human_review regardless of score."""
        from novel_factory.workflow.conditions import route_by_review_result

        state = {
            "quality_gate": {"pass": False, "score": 70},
            "retry_count": 3,
            "max_retries": 3,
            "_revision_review": {"score": 67},
        }
        assert route_by_review_result(state) == "human_review"
