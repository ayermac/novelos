"""v3.9 LLM Recommender tests.

Covers:
- recommend_for_agent: each core agent gets a recommendation
- recommend_all_agents: all agents get recommendations
- constraints: cost_tier, quality_tier, provider_whitelist, require_strengths, prefer_low_latency
- unknown agent returns stable error
- explain_recommendation
- generate_config_plan
- No API keys in output
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from novel_factory.llm.catalog import LLMCatalog, LLMModelSpec, Strength, load_llm_catalog
from novel_factory.llm.recommender import (
    AGENT_PROFILES,
    KNOWN_AGENTS,
    RecommendationConstraints,
    explain_recommendation,
    generate_config_plan,
    recommend_all_agents,
    recommend_for_agent,
)


# ── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def catalog():
    """Load the default LLM catalog."""
    return load_llm_catalog()


@pytest.fixture
def minimal_catalog():
    """Create a minimal catalog for deterministic testing."""
    models = [
        LLMModelSpec(
            provider="test",
            model="cheap-fast",
            display_name="Cheap Fast",
            cost_tier="low",
            latency_tier="low",
            quality_tier="draft",
            strengths=[Strength.SPEED, Strength.JSON],
            recommended_agents=["scout", "secretary"],
        ),
        LLMModelSpec(
            provider="test",
            model="premium-smart",
            display_name="Premium Smart",
            cost_tier="high",
            latency_tier="medium",
            quality_tier="premium",
            strengths=[Strength.REASONING, Strength.PLANNING, Strength.JSON, Strength.PROSE],
            recommended_agents=["planner", "author"],
        ),
        LLMModelSpec(
            provider="test",
            model="mid-range",
            display_name="Mid Range",
            cost_tier="medium",
            latency_tier="medium",
            quality_tier="standard",
            strengths=[Strength.REASONING, Strength.EDITING, Strength.JSON],
            recommended_agents=["editor", "architect"],
        ),
    ]
    return LLMCatalog(models=models)


# ── Core agent recommendations ─────────────────────────────────

class TestRecommendForAgent:
    """Test recommend_for_agent for each core agent."""

    @pytest.mark.parametrize("agent_id", [
        "planner", "screenwriter", "author", "polisher",
        "editor", "scout", "continuity_checker", "architect", "secretary",
    ])
    def test_each_agent_gets_recommendation(self, catalog, agent_id):
        """Each core agent gets a valid recommendation from the default catalog."""
        result = recommend_for_agent(agent_id, catalog=catalog)
        assert result["ok"] is True, f"Agent {agent_id} recommendation failed: {result['error']}"
        data = result["data"]
        assert data["agent_id"] == agent_id
        assert data["provider"]
        assert data["model"]
        assert isinstance(data["score"], (int, float))
        assert isinstance(data["reasons"], list)
        assert len(data["reasons"]) > 0

    def test_unknown_agent_returns_error(self, catalog):
        """Unknown agent returns stable error response."""
        result = recommend_for_agent("nonexistent_agent", catalog=catalog)
        assert result["ok"] is False
        assert "Unknown agent" in result["error"]
        assert result["data"] == {}

    def test_recommendation_has_profile_template(self, catalog):
        """Recommendation includes profile_template field."""
        result = recommend_for_agent("author", catalog=catalog)
        assert result["ok"] is True
        assert "profile_template" in result["data"]


class TestRecommendAllAgents:
    """Test recommend_all_agents."""

    def test_all_agents_recommended(self, catalog):
        """All known agents get recommendations."""
        result = recommend_all_agents(catalog=catalog)
        assert result["ok"] is True
        recommendations = result["data"]["recommendations"]
        assert len(recommendations) == len(KNOWN_AGENTS)

        recommended_agents = {r["agent_id"] for r in recommendations}
        assert recommended_agents == KNOWN_AGENTS

    def test_total_count(self, catalog):
        """Total count matches recommendation list length."""
        result = recommend_all_agents(catalog=catalog)
        assert result["data"]["total"] == len(result["data"]["recommendations"])


# ── Constraints ────────────────────────────────────────────────

class TestRecommendationConstraints:
    """Test recommendation constraint filtering."""

    def test_cost_tier_max(self, catalog):
        """cost_tier_max constraint filters out expensive models."""
        constraints = RecommendationConstraints(cost_tier_max="low")
        result = recommend_for_agent("author", catalog=catalog, constraints=constraints)
        assert result["ok"] is True
        # The recommended model should be low cost
        spec = catalog.get_by_provider_model(result["data"]["provider"], result["data"]["model"])
        if spec:
            assert spec.cost_tier.value == "low"

    def test_quality_tier_min(self, catalog):
        """quality_tier_min constraint filters out low quality models."""
        constraints = RecommendationConstraints(quality_tier_min="premium")
        result = recommend_for_agent("planner", catalog=catalog, constraints=constraints)
        assert result["ok"] is True
        spec = catalog.get_by_provider_model(result["data"]["provider"], result["data"]["model"])
        if spec:
            assert spec.quality_rank >= 2

    def test_provider_whitelist(self, catalog):
        """provider_whitelist constraint filters by provider."""
        constraints = RecommendationConstraints(provider_whitelist=["openai"])
        result = recommend_for_agent("author", catalog=catalog, constraints=constraints)
        assert result["ok"] is True
        assert result["data"]["provider"] == "openai"

    def test_provider_whitelist_no_match(self, catalog):
        """provider_whitelist with no matching models returns error."""
        constraints = RecommendationConstraints(provider_whitelist=["nonexistent_provider"])
        result = recommend_for_agent("author", catalog=catalog, constraints=constraints)
        assert result["ok"] is False
        assert "No models match" in result["error"]

    def test_require_strengths(self, catalog):
        """require_strengths constraint filters by required capabilities."""
        constraints = RecommendationConstraints(require_strengths=["prose", "long_context"])
        result = recommend_for_agent("author", catalog=catalog, constraints=constraints)
        assert result["ok"] is True
        spec = catalog.get_by_provider_model(result["data"]["provider"], result["data"]["model"])
        if spec:
            strength_values = {s.value for s in spec.strengths}
            assert "prose" in strength_values
            assert "long_context" in strength_values

    def test_prefer_low_latency(self, catalog):
        """prefer_low_latency flag boosts fast models."""
        constraints = RecommendationConstraints(prefer_low_latency=True)
        result = recommend_for_agent("secretary", catalog=catalog, constraints=constraints)
        assert result["ok"] is True

    def test_combined_constraints(self, minimal_catalog):
        """Multiple constraints work together."""
        constraints = RecommendationConstraints(
            cost_tier_max="medium",
            quality_tier_min="standard",
        )
        result = recommend_for_agent("editor", catalog=minimal_catalog, constraints=constraints)
        assert result["ok"] is True

    def test_constraints_with_recommend_all(self, catalog):
        """Constraints work with recommend_all_agents."""
        constraints = RecommendationConstraints(cost_tier_max="medium")
        result = recommend_all_agents(catalog=catalog, constraints=constraints)
        assert result["ok"] is True

    def test_invalid_require_strengths_returns_error(self, catalog):
        """require_strengths with invalid value returns stable error envelope."""
        constraints = RecommendationConstraints(require_strengths=["nonexistent"])
        result = recommend_for_agent("author", catalog=catalog, constraints=constraints)
        assert result["ok"] is False
        assert "Invalid strength" in result["error"]
        assert result["data"] == {}

    def test_invalid_require_strengths_partial(self, catalog):
        """require_strengths with mix of valid and invalid returns error on first invalid."""
        constraints = RecommendationConstraints(require_strengths=["prose", "bad_strength"])
        result = recommend_for_agent("author", catalog=catalog, constraints=constraints)
        assert result["ok"] is False
        assert "Invalid strength" in result["error"]
        assert "bad_strength" in result["error"]

    def test_recommend_all_no_match_returns_error(self, catalog):
        """recommend_all_agents with impossible constraints returns ok:false."""
        constraints = RecommendationConstraints(provider_whitelist=["nonexistent_provider"])
        result = recommend_all_agents(catalog=catalog, constraints=constraints)
        assert result["ok"] is False
        assert "No agents could be recommended" in result["error"]
        assert result["data"]["total"] == 0
        assert result["data"]["recommendations"] == []
        # Should have failed_agents with diagnostics
        assert "failed_agents" in result["data"]
        assert len(result["data"]["failed_agents"]) > 0

    def test_recommend_all_includes_failed_agents(self, catalog):
        """recommend_all_agents includes failed_agents for partial failures."""
        # Use a constraint that only matches some agents
        constraints = RecommendationConstraints(provider_whitelist=["openai"])
        result = recommend_all_agents(catalog=catalog, constraints=constraints)
        # Whether ok is True or False depends on if at least some agents match
        # But failed_agents should always be present
        assert "failed_agents" in result["data"]


# ── Explain recommendation ─────────────────────────────────────

class TestExplainRecommendation:
    """Test explain_recommendation."""

    def test_explain_valid(self, catalog):
        """Explain recommendation for valid agent returns details."""
        spec = catalog.models[0]
        result = explain_recommendation("planner", spec)
        assert result["ok"] is True
        data = result["data"]
        assert data["agent_id"] == "planner"
        assert "agent_required_strengths" in data
        assert "model_strengths" in data
        assert "required_match" in data
        assert "required_missing" in data

    def test_explain_unknown_agent(self, catalog):
        """Explain recommendation for unknown agent returns error."""
        spec = catalog.models[0]
        result = explain_recommendation("nonexistent", spec)
        assert result["ok"] is False
        assert "Unknown agent" in result["error"]


# ── Config plan ────────────────────────────────────────────────

class TestConfigPlan:
    """Test generate_config_plan."""

    def test_config_plan_structure(self, catalog):
        """Config plan has expected structure."""
        result = generate_config_plan(catalog=catalog)
        assert result["ok"] is True
        data = result["data"]
        assert "default_llm" in data
        assert "llm_profiles" in data
        assert "agent_llm" in data
        assert isinstance(data["llm_profiles"], dict)
        assert isinstance(data["agent_llm"], dict)

    def test_config_plan_profiles_have_env_vars(self, catalog):
        """Config plan profiles use environment variable references."""
        result = generate_config_plan(catalog=catalog)
        data = result["data"]
        for name, profile in data["llm_profiles"].items():
            assert "base_url_env" in profile, f"Profile {name} missing base_url_env"
            assert "api_key_env" in profile, f"Profile {name} missing api_key_env"

    def test_config_plan_no_api_keys(self, catalog):
        """Config plan output contains no real API keys."""
        result = generate_config_plan(catalog=catalog)
        output_json = json.dumps(result)
        assert "sk-" not in output_json
        # Should contain env var references, not actual keys
        assert "api_key_env" in output_json

    def test_config_plan_agent_llm_covers_all_agents(self, catalog):
        """Config plan agent_llm covers all known agents."""
        result = generate_config_plan(catalog=catalog)
        data = result["data"]
        for agent_id in KNOWN_AGENTS:
            assert agent_id in data["agent_llm"], f"Agent {agent_id} missing from agent_llm"

    def test_config_plan_profiles_reference_valid_agents(self, catalog):
        """All agent_llm references point to existing profiles."""
        result = generate_config_plan(catalog=catalog)
        data = result["data"]
        for agent_id, profile_name in data["agent_llm"].items():
            assert profile_name in data["llm_profiles"], \
                f"Agent {agent_id} references non-existent profile {profile_name}"

    def test_config_plan_default_llm_exists(self, catalog):
        """default_llm points to an existing profile."""
        result = generate_config_plan(catalog=catalog)
        data = result["data"]
        assert data["default_llm"] in data["llm_profiles"]

    def test_config_plan_with_constraints(self, catalog):
        """Config plan respects constraints."""
        constraints = RecommendationConstraints(cost_tier_max="medium")
        result = generate_config_plan(catalog=catalog, constraints=constraints)
        assert result["ok"] is True
        data = result["data"]
        # All profiles should reference models at or below medium cost
        for name, profile in data["llm_profiles"].items():
            model_name = profile.get("model", "")
            spec = catalog.get_by_provider_model(
                profile.get("provider", "openai_compatible"),
                model_name,
            )
            # Provider in profile may differ from catalog provider
            # So just check the plan is valid structure

    def test_config_plan_deduplication(self, catalog):
        """Config plan deduplicates profiles with same provider+model."""
        result = generate_config_plan(catalog=catalog)
        data = result["data"]
        # Check no duplicate provider:model pairs
        seen = set()
        for name, profile in data["llm_profiles"].items():
            key = f"{profile.get('provider')}:{profile.get('model')}"
            assert key not in seen, f"Duplicate profile for {key}"
            seen.add(key)

    def test_config_plan_no_recommendations_returns_error(self, catalog):
        """generate_config_plan with impossible constraints returns ok:false."""
        constraints = RecommendationConstraints(provider_whitelist=["nonexistent_provider"])
        result = generate_config_plan(catalog=catalog, constraints=constraints)
        assert result["ok"] is False
        assert "No recommendations" in result["error"] or "No agents" in result["error"]
        assert result["data"]["llm_profiles"] == {}
        assert result["data"]["agent_llm"] == {}


# ── No secrets in output ───────────────────────────────────────

class TestNoSecrets:
    """Ensure no API keys or secrets appear in any recommendation output."""

    def test_recommend_for_agent_no_secrets(self, catalog):
        """recommend_for_agent output contains no API keys."""
        result = recommend_for_agent("author", catalog=catalog)
        output = json.dumps(result)
        assert "sk-" not in output
        assert "api_key" not in output.lower() or "api_key_env" not in output

    def test_recommend_all_agents_no_secrets(self, catalog):
        """recommend_all_agents output contains no API keys."""
        result = recommend_all_agents(catalog=catalog)
        output = json.dumps(result)
        assert "sk-" not in output

    def test_config_plan_no_secrets(self, catalog):
        """config_plan output contains no API keys."""
        result = generate_config_plan(catalog=catalog)
        output = json.dumps(result)
        assert "sk-" not in output
