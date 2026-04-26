"""v3.9 LLM Catalog & Recommendation CLI commands.

Provides:
- llm catalog: List all models in the catalog
- llm recommend: Recommend models for agents
- llm config-plan: Generate configuration plan
"""

from __future__ import annotations

import json
import sys
from typing import Any

from ..output import print_json_envelope, print_error_and_exit


def cmd_llm_catalog(args) -> None:
    """List all models in the LLM catalog."""
    from ...llm.catalog import load_llm_catalog

    use_json = getattr(args, "json", False)

    try:
        catalog = load_llm_catalog()
    except FileNotFoundError as e:
        print_error_and_exit(str(e), use_json)
        return
    except ValueError as e:
        print_error_and_exit(f"Invalid catalog: {e}", use_json)
        return

    data = catalog.to_display_dict()

    if use_json:
        print(json.dumps({"ok": True, "error": None, "data": data}, ensure_ascii=False, indent=2))
    else:
        print("LLM Model Catalog:")
        print(f"  Total models: {data['total']}")
        print()
        for m in data["models"]:
            print(f"  [{m['provider']}/{m['model']}]")
            print(f"    display_name: {m['display_name']}")
            print(f"    profile_template: {m['profile_template']}")
            print(f"    context_window: {m['context_window']:,}")
            print(f"    cost_tier: {m['cost_tier']}")
            print(f"    latency_tier: {m['latency_tier']}")
            print(f"    quality_tier: {m['quality_tier']}")
            print(f"    strengths: {', '.join(m['strengths'])}")
            if m['recommended_agents']:
                print(f"    recommended_agents: {', '.join(m['recommended_agents'])}")
            if m['notes']:
                print(f"    notes: {m['notes']}")
            print()


def cmd_llm_recommend(args) -> None:
    """Recommend LLM models for agents."""
    from ...llm.catalog import load_llm_catalog
    from ...llm.recommender import (
        RecommendationConstraints,
        recommend_for_agent,
        recommend_all_agents,
    )

    use_json = getattr(args, "json", False)

    # Load catalog
    try:
        catalog = load_llm_catalog()
    except FileNotFoundError as e:
        print_error_and_exit(str(e), use_json)
        return
    except ValueError as e:
        print_error_and_exit(f"Invalid catalog: {e}", use_json)
        return

    # Build constraints from args
    constraints = RecommendationConstraints(
        cost_tier_max=getattr(args, "cost_tier", None),
        quality_tier_min=getattr(args, "quality_tier", None),
        provider_whitelist=_parse_provider_whitelist(getattr(args, "provider", None)),
        require_strengths=_parse_strengths(getattr(args, "require_strengths", None)),
        prefer_low_latency=getattr(args, "prefer_low_latency", False),
    )

    # Determine mode: single agent or all
    agent_id = getattr(args, "agent", None)
    recommend_all = getattr(args, "all", False)

    if recommend_all:
        result = recommend_all_agents(catalog=catalog, constraints=constraints)
    elif agent_id:
        result = recommend_for_agent(agent_id, catalog=catalog, constraints=constraints)
    else:
        print_error_and_exit("Must specify --agent <id> or --all", use_json)
        return

    if not result["ok"]:
        print_error_and_exit(result["error"], use_json, data=result.get("data", {}))
        return

    if use_json:
        print(json.dumps({"ok": True, "error": None, "data": result["data"]}, ensure_ascii=False, indent=2))
    else:
        _print_recommendation_human(result["data"], recommend_all)


def cmd_llm_config_plan(args) -> None:
    """Generate llm_profiles and agent_llm configuration plan."""
    from ...llm.catalog import load_llm_catalog
    from ...llm.recommender import (
        RecommendationConstraints,
        generate_config_plan,
    )

    use_json = getattr(args, "json", False)

    # Load catalog
    try:
        catalog = load_llm_catalog()
    except FileNotFoundError as e:
        print_error_and_exit(str(e), use_json)
        return
    except ValueError as e:
        print_error_and_exit(f"Invalid catalog: {e}", use_json)
        return

    # Build constraints from args
    constraints = RecommendationConstraints(
        cost_tier_max=getattr(args, "cost_tier", None),
        quality_tier_min=getattr(args, "quality_tier", None),
        provider_whitelist=_parse_provider_whitelist(getattr(args, "provider", None)),
        prefer_low_latency=getattr(args, "prefer_low_latency", False),
    )

    result = generate_config_plan(catalog=catalog, constraints=constraints)

    if not result["ok"]:
        print_error_and_exit(result["error"], use_json, data=result.get("data", {}))
        return

    if use_json:
        print(json.dumps({"ok": True, "error": None, "data": result["data"]}, ensure_ascii=False, indent=2))
    else:
        data = result["data"]
        print("LLM Configuration Plan (draft):")
        print()
        print(f"default_llm: {data['default_llm']}")
        print()
        print("llm_profiles:")
        for name, profile in data["llm_profiles"].items():
            print(f"  {name}:")
            for k, v in profile.items():
                print(f"    {k}: {v}")
        print()
        print("agent_llm:")
        for agent_id, profile_name in data["agent_llm"].items():
            print(f"  {agent_id}: {profile_name}")


# ── Helpers ────────────────────────────────────────────────────

def _parse_provider_whitelist(value: str | None) -> list[str] | None:
    """Parse comma-separated provider whitelist."""
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()]


def _parse_strengths(value: str | None) -> list[str] | None:
    """Parse comma-separated required strengths."""
    if not value:
        return None
    return [s.strip() for s in value.split(",") if s.strip()]


def _print_recommendation_human(data: dict[str, Any], is_all: bool) -> None:
    """Print recommendation in human-readable format."""
    if is_all:
        recommendations = data.get("recommendations", [])
        print(f"Agent Recommendations ({data.get('total', 0)} agents):")
        print()
        for rec in recommendations:
            _print_single_recommendation(rec)
            print()
    else:
        _print_single_recommendation(data)


def _print_single_recommendation(rec: dict[str, Any]) -> None:
    """Print a single agent recommendation."""
    print(f"  Agent: {rec['agent_id']}")
    print(f"  Recommended Profile: {rec['recommended_profile_name']}")
    print(f"  Provider: {rec['provider']}")
    print(f"  Model: {rec['model']}")
    print(f"  Score: {rec['score']}")
    if rec.get("reasons"):
        print(f"  Reasons: {'; '.join(rec['reasons'])}")
    if rec.get("tradeoffs"):
        print(f"  Tradeoffs: {'; '.join(rec['tradeoffs'])}")
