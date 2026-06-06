"""Tests for v6.9.1 Phase 3: Skill Aggregation.

Tests cover:
- Weighted score calculation
- Blocking skill enforcement
- Low skill score handling
- Backward compatibility
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass

from novel_factory.quality.editor_strategy import (
    EditorPolicyInput,
    EditorDecision,
    aggregate_skill_scores,
    classify_editor_result,
    build_policy_input,
    post_process_llm_decision,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def base_policy_input():
    """Create a base policy input for testing."""
    return EditorPolicyInput(
        score=80,
        pass_=True,
        skill_weighted_score=0,
        blocking_skill_count=0,
        warning_skill_count=0,
        skill_scores={},
        editor_weights={},
    )


# ── A. Aggregate Skill Scores ───────────────────────────────────────────


class TestAggregateSkillScores:
    """Test aggregate_skill_scores function."""

    def test_aggregate_skill_scores_basic(self):
        """Test basic weighted score calculation."""
        skill_scores = {
            "skill_a": 80,
            "skill_b": 90,
            "skill_c": 70,
        }
        # No weights → equal weighting
        result = aggregate_skill_scores(skill_scores)
        expected = (80 + 90 + 70) / 3
        assert abs(result - expected) < 0.01

    def test_aggregate_skill_scores_with_weights(self):
        """Test weighted score calculation with genre weights."""
        skill_scores = {
            "excitement-density-checker": 80,
            "opening-hook-checker": 90,
            "death-penalty": 100,
        }
        editor_weights = {
            "excitement-density-checker": 2.0,
            "opening-hook-checker": 1.5,
            "death-penalty": 1.0,
        }

        result = aggregate_skill_scores(skill_scores, editor_weights)

        # Expected: (80*2 + 90*1.5 + 100*1) / (2 + 1.5 + 1)
        expected = (80 * 2 + 90 * 1.5 + 100 * 1) / (2 + 1.5 + 1)
        assert abs(result - expected) < 0.01

    def test_aggregate_skill_scores_empty(self):
        """Test empty scores return 0."""
        assert aggregate_skill_scores({}) == 0.0

    def test_aggregate_skill_scores_zero_weight(self):
        """Test behavior when some weights are zero."""
        skill_scores = {
            "skill_a": 80,
            "skill_b": 90,
        }
        editor_weights = {
            "skill_a": 0,  # Zero weight
            "skill_b": 1.0,
        }

        result = aggregate_skill_scores(skill_scores, editor_weights)
        # Only skill_b should contribute
        assert result == 90.0

    def test_aggregate_skill_scores_all_zero_weights(self):
        """Test behavior when all weights are zero."""
        skill_scores = {
            "skill_a": 80,
            "skill_b": 90,
        }
        editor_weights = {
            "skill_a": 0,
            "skill_b": 0,
        }

        # Should return 0 to avoid division by zero
        result = aggregate_skill_scores(skill_scores, editor_weights)
        assert result == 0.0

    def test_aggregate_skill_scores_partial_weights(self):
        """Test behavior when only some skills have weights."""
        skill_scores = {
            "skill_a": 80,
            "skill_b": 90,
            "skill_c": 70,
        }
        editor_weights = {
            "skill_a": 2.0,
            # skill_b and skill_c have no weight → default 1.0
        }

        result = aggregate_skill_scores(skill_scores, editor_weights)
        # Expected: (80*2 + 90*1 + 70*1) / (2 + 1 + 1)
        expected = (80 * 2 + 90 * 1 + 70 * 1) / (2 + 1 + 1)
        assert abs(result - expected) < 0.01


# ── B. Editor Policy Input ──────────────────────────────────────────────


class TestEditorPolicyInput:
    """Test EditorPolicyInput construction and usage."""

    def test_editor_policy_input_with_skills(self):
        """Test EditorPolicyInput with skill data."""
        policy_input = EditorPolicyInput(
            score=85,
            pass_=True,
            skill_weighted_score=80,
            blocking_skill_count=1,
            warning_skill_count=2,
            skill_scores={
                "death-penalty": 0,
                "excitement-density-checker": 85,
                "opening-hook-checker": 90,
            },
            editor_weights={
                "excitement-density-checker": 2.0,
                "opening-hook-checker": 1.5,
            },
        )

        assert policy_input.score == 85
        assert policy_input.pass_ is True
        assert policy_input.skill_weighted_score == 80
        assert policy_input.blocking_skill_count == 1
        assert policy_input.warning_skill_count == 2
        assert len(policy_input.skill_scores) == 3
        assert len(policy_input.editor_weights) == 2

    def test_editor_policy_input_defaults(self):
        """Test EditorPolicyInput default values."""
        policy_input = EditorPolicyInput(score=80, pass_=True)

        assert policy_input.score == 80
        assert policy_input.pass_ is True
        assert policy_input.skill_weighted_score == 0
        assert policy_input.blocking_skill_count == 0
        assert policy_input.warning_skill_count == 0
        assert policy_input.skill_scores == {}
        assert policy_input.editor_weights == {}


# ── C. Classify Editor Result ───────────────────────────────────────────


class TestClassifyEditorResult:
    """Test classify_editor_result function."""

    def test_classify_with_blocking_skill(self, base_policy_input):
        """Test that blocking skill forces blocking decision."""
        base_policy_input.blocking_skill_count = 1
        base_policy_input.skill_weighted_score = 80

        decision = classify_editor_result(base_policy_input)
        assert decision.decision_type == "blocking"
        assert decision.revision_needed is True

    def test_classify_with_low_skill_score(self, base_policy_input):
        """Test that low skill score forces revision."""
        base_policy_input.skill_weighted_score = 65  # Below 70 threshold

        decision = classify_editor_result(base_policy_input)
        assert decision.decision_type == "revision"

    def test_classify_with_high_skill_score(self, base_policy_input):
        """Test that high skill score with no blocking passes."""
        base_policy_input.skill_weighted_score = 85
        base_policy_input.blocking_skill_count = 0
        base_policy_input.score = 85

        decision = classify_editor_result(base_policy_input)
        assert decision.decision_type in ("pass", "advisory_pass")

    def test_classify_with_warning_skills(self, base_policy_input):
        """Test that warning skills don't force revision."""
        base_policy_input.skill_weighted_score = 80
        base_policy_input.warning_skill_count = 3
        base_policy_input.blocking_skill_count = 0

        decision = classify_editor_result(base_policy_input)
        # Warnings should not force revision
        assert decision.decision_type in ("pass", "advisory_pass")

    def test_classify_with_mixed_signals(self, base_policy_input):
        """Test classification with conflicting signals."""
        # High LLM score but low skill score
        base_policy_input.score = 90
        base_policy_input.skill_weighted_score = 65

        decision = classify_editor_result(base_policy_input)
        # Low skill score should override high LLM score
        assert decision.decision_type == "revision"

    def test_classify_edge_case_boundary_score(self, base_policy_input):
        """Test classification at boundary score (70)."""
        base_policy_input.skill_weighted_score = 70
        base_policy_input.blocking_skill_count = 0
        base_policy_input.score = 70  # Both at boundary

        decision = classify_editor_result(base_policy_input)
        # effective_score = skill_weighted_score (70) since > 0
        # 70 >= 70 -> not < 70 (Rule 1.6 passes)
        # 70 < 80 -> Rule 6: revision
        assert decision.decision_type == "revision"

    def test_classify_edge_case_below_boundary(self, base_policy_input):
        """Test classification just below boundary (69)."""
        base_policy_input.skill_weighted_score = 69
        base_policy_input.blocking_skill_count = 0

        decision = classify_editor_result(base_policy_input)
        # Score below 70 should force revision
        assert decision.decision_type == "revision"


# ── D. Effective Score Fallback ──────────────────────────────────────────


class TestEffectiveScoreFallback:
    """Test effective score calculation with fallback."""

    def test_effective_score_fallback_no_skills(self, base_policy_input):
        """Test that effective score falls back to LLM score when no skills."""
        base_policy_input.score = 85
        base_policy_input.skill_weighted_score = 0  # No skill data

        decision = classify_editor_result(base_policy_input)
        # Should use LLM score (85) as effective score -> >= 85 -> advisory_pass
        assert decision.decision_type in ("pass", "advisory_pass")

    def test_effective_score_uses_skill_score(self, base_policy_input):
        """Test that effective score uses skill score when available."""
        base_policy_input.score = 85
        base_policy_input.skill_weighted_score = 80  # Skill data available

        decision = classify_editor_result(base_policy_input)
        # Should use skill score (80) as effective score -> 80-84 range, no priority -> advisory_pass
        assert decision.decision_type in ("pass", "advisory_pass")

    def test_effective_score_min_strategy(self, base_policy_input):
        """Test effective score behavior: skill score takes precedence."""
        # Current implementation: effective_score = skill_weighted_score if > 0 else score

        base_policy_input.score = 90  # High LLM score
        base_policy_input.skill_weighted_score = 75  # Lower skill score

        decision = classify_editor_result(base_policy_input)

        # Current behavior: uses skill score (75) -> 75-79, < 80 -> revision
        # (near-miss guard requires retry_count >= 1, default is 0)
        assert decision.decision_type == "revision"


# ── E. Build Policy Input ───────────────────────────────────────────────


class TestBuildPolicyInput:
    """Test build_policy_input function."""

    def test_build_policy_input_with_skills(self):
        """Test building policy input with skill data."""
        policy_input = build_policy_input(
            score=85,
            pass_=True,
            issues=[],
            skill_weighted_score=80,
            blocking_skill_count=1,
            warning_skill_count=2,
            skill_scores={"test-skill": 80},
            editor_weights={"test-skill": 1.5},
        )

        assert isinstance(policy_input, EditorPolicyInput)
        assert policy_input.score == 85
        assert policy_input.skill_weighted_score == 80
        assert policy_input.blocking_skill_count == 1
        assert policy_input.warning_skill_count == 2

    def test_build_policy_input_without_skills(self):
        """Test building policy input without skill data."""
        policy_input = build_policy_input(
            score=85,
            pass_=True,
            issues=[],
        )

        assert isinstance(policy_input, EditorPolicyInput)
        assert policy_input.score == 85
        assert policy_input.skill_weighted_score == 0
        assert policy_input.blocking_skill_count == 0


# ── F. Post Process LLM Decision ────────────────────────────────────────


class TestPostProcessLLMDecision:
    """Test post_process_llm_decision function."""

    def test_post_process_with_blocking_skill(self):
        """Test post-processing overrides LLM decision when blocking skill."""
        # Simulate LLM decision to pass
        llm_pass = True
        score = 85
        issues = []

        # But there's a blocking skill
        result = post_process_llm_decision(
            llm_pass=llm_pass,
            score=score,
            issues=issues,
            skill_weighted_score=80,
            blocking_skill_count=1,
            warning_skill_count=0,
            skill_scores={"death-penalty": 0},
            editor_weights={},
        )

        # Should override to blocking
        assert result.decision_type == "blocking"
        assert result.pass_ is False

    def test_post_process_preserves_llm_decision(self):
        """Test post-processing preserves LLM decision when no blocking."""
        # Simulate LLM decision to pass
        llm_pass = True
        score = 85
        issues = []

        # No blocking skills
        result = post_process_llm_decision(
            llm_pass=llm_pass,
            score=score,
            issues=issues,
            skill_weighted_score=80,
            blocking_skill_count=0,
            warning_skill_count=0,
            skill_scores={},
            editor_weights={},
        )

        # Should preserve pass decision
        assert result.decision_type in ("pass", "advisory_pass")


# ── G. Integration Tests ────────────────────────────────────────────────


class TestSkillAggregationIntegration:
    """Integration tests for the full skill aggregation flow."""

    def test_full_flow_with_genre_weights(self):
        """Test full flow with genre-specific weights."""
        # Simulate a webnovel project
        skill_scores = {
            "excitement-density-checker": 85,
            "opening-hook-checker": 90,
            "death-penalty": 100,
            "word-count-gate": 95,
        }
        editor_weights = {
            "excitement-density-checker": 2.0,  # High weight for webnovel
            "opening-hook-checker": 1.5,
            "death-penalty": 1.0,
            "word-count-gate": 0.5,
        }

        # Calculate weighted score
        weighted_score = aggregate_skill_scores(skill_scores, editor_weights)

        # Build policy input
        policy_input = build_policy_input(
            score=85,
            pass_=True,
            issues=[],
            skill_weighted_score=weighted_score,
            blocking_skill_count=0,
            warning_skill_count=0,
            skill_scores=skill_scores,
            editor_weights=editor_weights,
        )

        # Classify
        decision = classify_editor_result(policy_input)

        # Should pass with good scores (weighted_score ~90.56, >=85)
        assert decision.decision_type in ("pass", "advisory_pass")
        assert decision.pass_ is True

    def test_full_flow_with_blocking_skill(self):
        """Test full flow with blocking skill."""
        skill_scores = {
            "death-penalty": 0,  # Blocking
            "excitement-density-checker": 85,
        }
        editor_weights = {
            "death-penalty": 1.0,
            "excitement-density-checker": 2.0,
        }

        weighted_score = aggregate_skill_scores(skill_scores, editor_weights)

        policy_input = build_policy_input(
            score=85,
            pass_=True,
            issues=[],
            skill_weighted_score=weighted_score,
            blocking_skill_count=1,
            warning_skill_count=0,
            skill_scores=skill_scores,
            editor_weights=editor_weights,
        )

        decision = classify_editor_result(policy_input)

        # Should force blocking due to blocking skill
        assert decision.decision_type == "blocking"
        assert decision.pass_ is False

    def test_backward_compat_no_skill_data(self):
        """Test backward compatibility when no skill data is available."""
        policy_input = build_policy_input(score=85, pass_=True, issues=[])

        decision = classify_editor_result(policy_input)

        # Should pass based on LLM score alone
        assert decision.decision_type in ("pass", "advisory_pass")
        assert decision.pass_ is True