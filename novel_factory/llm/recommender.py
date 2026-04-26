"""LLM Model Recommender for v3.9.

Recommends LLM models for each agent based on capability tags,
cost/quality preferences, and agent-specific requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .catalog import (
    LLMCatalog,
    LLMModelSpec,
    Strength,
    _COST_ORDER,
    _LATENCY_ORDER,
    _QUALITY_ORDER,
)


# ── Agent strength profiles ────────────────────────────────────
# Maps agent_id to (required_strengths, preferred_strengths, description)

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "planner": {
        "description": "总编/策划 — 生成章节写作指令",
        "required_strengths": [Strength.REASONING, Strength.PLANNING, Strength.JSON],
        "preferred_strengths": [],
        "default_quality_min": "standard",
    },
    "screenwriter": {
        "description": "编剧 — 将指令拆解为场景 beat",
        "required_strengths": [Strength.REASONING, Strength.PLANNING, Strength.JSON],
        "preferred_strengths": [Strength.PROSE],
        "default_quality_min": "standard",
    },
    "author": {
        "description": "执笔 — 根据指令和场景 beat 创作正文",
        "required_strengths": [Strength.PROSE, Strength.LONG_CONTEXT],
        "preferred_strengths": [Strength.SAFETY],
        "default_quality_min": "standard",
    },
    "polisher": {
        "description": "润色 — 清理 AI 味，优化句式",
        "required_strengths": [Strength.EDITING, Strength.PROSE, Strength.SAFETY],
        "preferred_strengths": [],
        "default_quality_min": "standard",
    },
    "editor": {
        "description": "质检 — 五层审校，通过/退回",
        "required_strengths": [Strength.EDITING, Strength.REASONING, Strength.JSON],
        "preferred_strengths": [],
        "default_quality_min": "standard",
    },
    "scout": {
        "description": "市场分析师 — 分析市场趋势和读者偏好",
        "required_strengths": [Strength.SPEED],
        "preferred_strengths": [Strength.REASONING],
        "default_quality_min": "draft",
    },
    "continuity_checker": {
        "description": "连续性检查员 — 跨章一致性检查",
        "required_strengths": [Strength.LONG_CONTEXT, Strength.REASONING, Strength.JSON],
        "preferred_strengths": [],
        "default_quality_min": "standard",
    },
    "architect": {
        "description": "系统架构师 — 提出规则和 Prompt 改进建议",
        "required_strengths": [Strength.REASONING, Strength.JSON],
        "preferred_strengths": [Strength.PLANNING],
        "default_quality_min": "standard",
    },
    "secretary": {
        "description": "秘书 — 生成报告和导出",
        "required_strengths": [],
        "preferred_strengths": [Strength.SPEED],
        "default_quality_min": "draft",
    },
}

KNOWN_AGENTS = set(AGENT_PROFILES.keys())


# ── Recommendation constraints ─────────────────────────────────

@dataclass
class RecommendationConstraints:
    """Constraints for model recommendation."""

    cost_tier_max: Optional[str] = None      # "low", "medium", "high"
    quality_tier_min: Optional[str] = None    # "draft", "standard", "premium"
    provider_whitelist: Optional[list[str]] = None
    require_strengths: Optional[list[str]] = None
    prefer_low_latency: bool = False


# ── Recommendation result ──────────────────────────────────────

@dataclass
class AgentRecommendation:
    """Recommendation result for a single agent."""

    agent_id: str
    recommended_profile_name: str
    provider: str
    model: str
    score: float
    reasons: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    profile_template: str = "openai_compatible"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for display."""
        return {
            "agent_id": self.agent_id,
            "recommended_profile_name": self.recommended_profile_name,
            "provider": self.provider,
            "model": self.model,
            "score": round(self.score, 2),
            "reasons": self.reasons,
            "tradeoffs": self.tradeoffs,
            "profile_template": self.profile_template,
        }


# ── Scoring ────────────────────────────────────────────────────

def _compute_score(
    spec: LLMModelSpec,
    agent_id: str,
    constraints: RecommendationConstraints,
) -> tuple[float, list[str], list[str]]:
    """Compute recommendation score and reasons for a model-agent pair.

    Returns:
        (score, reasons, tradeoffs)
    """
    profile = AGENT_PROFILES.get(agent_id)
    if profile is None:
        return 0.0, [], [f"Unknown agent: {agent_id}"]

    score = 0.0
    reasons = []
    tradeoffs = []

    required = set(profile["required_strengths"])
    preferred = set(profile.get("preferred_strengths", []))
    model_strengths = set(spec.strengths)

    # Check required strengths
    missing_required = required - model_strengths
    if missing_required:
        # Heavy penalty for missing required strengths
        score -= len(missing_required) * 20
        tradeoffs.append(
            f"Missing required: {', '.join(s.value for s in missing_required)}"
        )

    # Bonus for matching required strengths
    matched_required = required & model_strengths
    if matched_required:
        score += len(matched_required) * 15
        reasons.append(
            f"Has required: {', '.join(s.value for s in matched_required)}"
        )

    # Bonus for preferred strengths
    matched_preferred = preferred & model_strengths
    if matched_preferred:
        score += len(matched_preferred) * 8
        reasons.append(
            f"Has preferred: {', '.join(s.value for s in matched_preferred)}"
        )

    # Bonus for being in recommended_agents
    if agent_id in spec.recommended_agents:
        score += 10
        reasons.append("Listed as recommended for this agent")

    # Quality bonus
    quality_rank = spec.quality_rank
    score += quality_rank * 5
    if quality_rank >= 2:
        reasons.append(f"Premium quality ({spec.quality_tier.value})")
    elif quality_rank == 0:
        tradeoffs.append(f"Low quality tier ({spec.quality_tier.value})")

    # Cost factor (penalize high cost unless quality is needed)
    min_quality = constraints.quality_tier_min or profile.get("default_quality_min", "draft")
    min_quality_rank = _QUALITY_ORDER.get(min_quality, 0)
    if spec.cost_rank > 0 and min_quality_rank <= 1:
        # If we don't need premium, penalize expensive models
        score -= spec.cost_rank * 3
        if spec.cost_rank >= 2:
            tradeoffs.append(f"High cost ({spec.cost_tier.value})")

    # Latency factor
    if constraints.prefer_low_latency:
        if spec.latency_rank == 0:
            score += 5
            reasons.append("Low latency")
        elif spec.latency_rank >= 2:
            score -= 3
            tradeoffs.append(f"High latency ({spec.latency_tier.value})")

    # Context window bonus for long_context agents
    if Strength.LONG_CONTEXT in required and spec.context_window >= 100000:
        score += 8
        reasons.append(f"Large context ({spec.context_window // 1000}K)")

    return score, reasons, tradeoffs


# ── Public API ─────────────────────────────────────────────────

def recommend_for_agent(
    agent_id: str,
    catalog: LLMCatalog | None = None,
    constraints: RecommendationConstraints | None = None,
) -> dict[str, Any]:
    """Recommend the best LLM model for a specific agent.

    Args:
        agent_id: Agent identifier (e.g., "author", "editor").
        catalog: LLMCatalog instance. Loads default if None.
        constraints: Optional recommendation constraints.

    Returns:
        Dict with ok, error, data keys. Data contains AgentRecommendation.
    """
    if catalog is None:
        from .catalog import load_llm_catalog
        try:
            catalog = load_llm_catalog()
        except FileNotFoundError as e:
            return {"ok": False, "error": str(e), "data": {}}

    if constraints is None:
        constraints = RecommendationConstraints()

    if agent_id not in KNOWN_AGENTS:
        return {
            "ok": False,
            "error": f"Unknown agent: '{agent_id}'. Known agents: {sorted(KNOWN_AGENTS)}",
            "data": {},
        }

    # Apply constraint filters
    candidates = list(catalog.models)

    # Filter by cost tier
    if constraints.cost_tier_max:
        max_cost_rank = _COST_ORDER.get(constraints.cost_tier_max, 2)
        candidates = [m for m in candidates if m.cost_rank <= max_cost_rank]

    # Filter by quality tier
    if constraints.quality_tier_min:
        min_quality_rank = _QUALITY_ORDER.get(constraints.quality_tier_min, 0)
        candidates = [m for m in candidates if m.quality_rank >= min_quality_rank]

    # Filter by provider whitelist
    if constraints.provider_whitelist:
        candidates = [m for m in candidates if m.provider in constraints.provider_whitelist]

    # Filter by required strengths
    if constraints.require_strengths:
        invalid_strengths = []
        valid_strengths = []
        for s in constraints.require_strengths:
            try:
                valid_strengths.append(Strength(s))
            except ValueError:
                invalid_strengths.append(s)
        if invalid_strengths:
            valid_values = [e.value for e in Strength]
            return {
                "ok": False,
                "error": (
                    f"Invalid strength value(s): {invalid_strengths}. "
                    f"Valid strengths: {valid_values}"
                ),
                "data": {},
            }
        required = set(valid_strengths)
        candidates = [m for m in candidates if required.issubset(set(m.strengths))]

    if not candidates:
        return {
            "ok": False,
            "error": f"No models match the given constraints for agent '{agent_id}'",
            "data": {},
        }

    # Score each candidate
    scored: list[tuple[float, LLMModelSpec, list[str], list[str]]] = []
    for spec in candidates:
        score, reasons, tradeoffs = _compute_score(spec, agent_id, constraints)
        scored.append((score, spec, reasons, tradeoffs))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best_spec, best_reasons, best_tradeoffs = scored[0]

    # Generate profile name from agent_id
    profile_name = f"rec_{agent_id}"

    recommendation = AgentRecommendation(
        agent_id=agent_id,
        recommended_profile_name=profile_name,
        provider=best_spec.provider,
        model=best_spec.model,
        score=best_score,
        reasons=best_reasons,
        tradeoffs=best_tradeoffs,
        profile_template=best_spec.profile_template,
    )

    return {"ok": True, "error": None, "data": recommendation.to_dict()}


def recommend_all_agents(
    catalog: LLMCatalog | None = None,
    constraints: RecommendationConstraints | None = None,
) -> dict[str, Any]:
    """Recommend models for all known agents.

    Args:
        catalog: LLMCatalog instance. Loads default if None.
        constraints: Optional recommendation constraints.

    Returns:
        Dict with ok, error, data keys. Data contains list of recommendations.
    """
    if catalog is None:
        from .catalog import load_llm_catalog
        try:
            catalog = load_llm_catalog()
        except FileNotFoundError as e:
            return {"ok": False, "error": str(e), "data": {}}

    if constraints is None:
        constraints = RecommendationConstraints()

    recommendations = []
    failed_agents: list[dict[str, str]] = []
    for agent_id in sorted(KNOWN_AGENTS):
        result = recommend_for_agent(agent_id, catalog=catalog, constraints=constraints)
        if result["ok"]:
            recommendations.append(result["data"])
        else:
            failed_agents.append({"agent_id": agent_id, "error": result["error"]})

    if not recommendations:
        return {
            "ok": False,
            "error": "No agents could be recommended with the given constraints",
            "data": {
                "recommendations": [],
                "total": 0,
                "failed_agents": failed_agents,
            },
        }

    return {
        "ok": True,
        "error": None,
        "data": {
            "recommendations": recommendations,
            "total": len(recommendations),
            "failed_agents": failed_agents,
        },
    }


def explain_recommendation(
    agent_id: str,
    model_spec: LLMModelSpec,
) -> dict[str, Any]:
    """Explain why a model is recommended for an agent.

    Args:
        agent_id: Agent identifier.
        model_spec: LLM model specification.

    Returns:
        Dict with explanation details.
    """
    if agent_id not in KNOWN_AGENTS:
        return {"ok": False, "error": f"Unknown agent: '{agent_id}'", "data": {}}

    profile = AGENT_PROFILES[agent_id]
    required = set(profile["required_strengths"])
    preferred = set(profile.get("preferred_strengths", []))
    model_strengths = set(model_spec.strengths)

    explanation = {
        "agent_id": agent_id,
        "agent_description": profile["description"],
        "model": model_spec.display_name,
        "provider": model_spec.provider,
        "model_strengths": [s.value for s in model_spec.strengths],
        "agent_required_strengths": [s.value for s in required],
        "agent_preferred_strengths": [s.value for s in preferred],
        "required_match": sorted(s.value for s in required & model_strengths),
        "required_missing": sorted(s.value for s in required - model_strengths),
        "preferred_match": sorted(s.value for s in preferred & model_strengths),
        "cost_tier": model_spec.cost_tier.value,
        "quality_tier": model_spec.quality_tier.value,
        "latency_tier": model_spec.latency_tier.value,
        "context_window": model_spec.context_window,
    }

    return {"ok": True, "error": None, "data": explanation}


def generate_config_plan(
    catalog: LLMCatalog | None = None,
    constraints: RecommendationConstraints | None = None,
) -> dict[str, Any]:
    """Generate llm_profiles and agent_llm configuration plan.

    This produces a YAML-serializable configuration draft that can be
    merged into the user's config file. It does NOT write any files.

    Args:
        catalog: LLMCatalog instance. Loads default if None.
        constraints: Optional recommendation constraints.

    Returns:
        Dict with ok, error, data keys. Data contains:
        - llm_profiles: dict of profile_name → profile_config
        - agent_llm: dict of agent_id → profile_name
        - default_llm: recommended default profile name
    """
    if catalog is None:
        from .catalog import load_llm_catalog
        try:
            catalog = load_llm_catalog()
        except FileNotFoundError as e:
            return {"ok": False, "error": str(e), "data": {}}

    if constraints is None:
        constraints = RecommendationConstraints()

    rec_result = recommend_all_agents(catalog=catalog, constraints=constraints)
    if not rec_result["ok"]:
        # Propagate the error, including failed_agents from the inner result
        return {
            "ok": False,
            "error": rec_result.get("error", "No recommendations available"),
            "data": {
                "default_llm": "",
                "llm_profiles": {},
                "agent_llm": {},
                "failed_agents": rec_result.get("data", {}).get("failed_agents", []),
            },
        }

    recommendations = rec_result["data"]["recommendations"]

    if not recommendations:
        return {
            "ok": False,
            "error": "No recommendations available to generate config plan",
            "data": {
                "default_llm": "",
                "llm_profiles": {},
                "agent_llm": {},
                "failed_agents": rec_result["data"].get("failed_agents", []),
            },
        }

    # Build llm_profiles and agent_llm
    llm_profiles: dict[str, dict[str, Any]] = {}
    agent_llm: dict[str, str] = {}

    for rec in recommendations:
        agent_id = rec["agent_id"]
        profile_name = rec["recommended_profile_name"]
        provider = rec["provider"]
        model = rec["model"]

        # Build profile entry
        profile_entry: dict[str, Any] = {
            "provider": "openai_compatible",  # All use openai_compatible adapter
            "model": model,
        }

        # Set env var references based on provider
        env_prefix = _provider_env_prefix(provider)
        if env_prefix:
            profile_entry["base_url_env"] = f"{env_prefix}_BASE_URL"
            profile_entry["api_key_env"] = f"{env_prefix}_API_KEY"

        llm_profiles[profile_name] = profile_entry
        agent_llm[agent_id] = profile_name

    # Determine default_llm: use the most common profile, or first one
    from collections import Counter
    profile_counts = Counter(agent_llm.values())
    default_llm = profile_counts.most_common(1)[0][0] if profile_counts else "default"

    # De-duplicate profiles that have the same model+provider
    # (multiple agents might recommend the same model)
    seen_profiles: dict[str, str] = {}  # key: "provider:model" → profile_name
    deduped_profiles: dict[str, dict[str, Any]] = {}
    deduped_agent_llm: dict[str, str] = {}

    for profile_name, profile_config in llm_profiles.items():
        dedup_key = f"{profile_config.get('provider', '')}:{profile_config.get('model', '')}"
        if dedup_key in seen_profiles:
            # Reuse existing profile
            existing_name = seen_profiles[dedup_key]
            # Update agent_llm references
            for agent_id, pname in agent_llm.items():
                if pname == profile_name:
                    deduped_agent_llm[agent_id] = existing_name
        else:
            seen_profiles[dedup_key] = profile_name
            deduped_profiles[profile_name] = profile_config
            for agent_id, pname in agent_llm.items():
                if pname == profile_name:
                    deduped_agent_llm[agent_id] = profile_name

    # Re-determine default_llm after dedup
    deduped_counts = Counter(deduped_agent_llm.values())
    default_llm = deduped_counts.most_common(1)[0][0] if deduped_counts else "default"

    return {
        "ok": True,
        "error": None,
        "data": {
            "default_llm": default_llm,
            "llm_profiles": deduped_profiles,
            "agent_llm": deduped_agent_llm,
        },
    }


def _provider_env_prefix(provider: str) -> str:
    """Map provider name to environment variable prefix.

    Returns uppercase provider name with hyphens replaced by underscores.
    """
    mapping = {
        "openai": "OPENAI",
        "deepseek": "DEEPSEEK",
        "anthropic-compatible": "ANTHROPIC",
        "openrouter": "OPENROUTER",
        "local": "LOCAL",
    }
    return mapping.get(provider, provider.upper().replace("-", "_"))
