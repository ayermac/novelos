"""Settings / LLM / Agent Ops Console route for Web UI."""

from __future__ import annotations

import os
from typing import Callable, Optional

from fastapi import APIRouter, Request

from ..deps import render, safe_error_message, get_settings_for_web, mask_secret

router = APIRouter()


def _build_llm_profiles_data(
    settings,
    llm_mode: str = "stub",
    env_getter: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
) -> dict:
    """Build LLM profiles data for display.
    
    Args:
        settings: Settings object from app state
        llm_mode: Current LLM mode ("stub" or "real")
        env_getter: Function to get environment variables (defaults to os.getenv)
        
    Returns:
        Dict with profiles list and default_llm
    """
    if env_getter is None:
        env_getter = os.getenv
    
    profiles = []
    
    if hasattr(settings, "llm_profiles") and settings.llm_profiles:
        for name, profile in settings.llm_profiles.items():
            # Get env var names (for display only, never show actual values)
            base_url_env = getattr(profile, "base_url_env", None)
            api_key_env = getattr(profile, "api_key_env", None)
            
            # Check if direct values are configured
            has_direct_base_url = bool(getattr(profile, "base_url", None))
            has_direct_api_key = bool(getattr(profile, "api_key", None))
            
            # Resolve actual values to check if they exist
            resolved_base_url = profile.get_resolved_base_url(env_getter)
            resolved_api_key = profile.get_resolved_api_key(env_getter)
            
            # Determine status based on resolved values
            has_base_url = bool(resolved_base_url)
            has_key = bool(resolved_api_key)
            
            # Determine status
            if has_key and has_base_url:
                status = "complete"
            elif has_key:
                status = "missing_base_url"
            elif has_base_url:
                status = "missing_key"
            else:
                status = "incomplete"
            
            # Determine env var status (for display)
            base_url_status = "N/A"
            if base_url_env:
                base_url_status = "configured" if env_getter(base_url_env) else "missing"
            elif has_direct_base_url:
                base_url_status = "direct"
            
            api_key_status = "N/A"
            if api_key_env:
                api_key_status = "configured" if env_getter(api_key_env) else "missing"
            elif has_direct_api_key:
                api_key_status = "direct"
            
            profiles.append({
                "name": name,
                "provider": getattr(profile, "provider", "unknown"),
                "model": getattr(profile, "model", "unknown"),
                "base_url_env": base_url_env or "N/A",
                "api_key_env": api_key_env or "N/A",
                "base_url_status": base_url_status,
                "api_key_status": api_key_status,
                "has_key": has_key,
                "has_base_url": has_base_url,
                "status": status,
            })
    
    default_llm = getattr(settings, "default_llm", "default")
    
    return {
        "profiles": profiles,
        "default_llm": default_llm,
    }


def _build_agent_routing_data(
    settings,
    llm_profiles: dict,
    llm_mode: str = "stub",
    env_getter: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
) -> dict:
    """Build agent routing data for display.
    
    Args:
        settings: Settings object from app state
        llm_profiles: Dict of profile name to profile data (from _build_llm_profiles_data)
        llm_mode: Current LLM mode ("stub" or "real")
        env_getter: Function to get environment variables (defaults to os.getenv)
        
    Returns:
        Dict with agent_routes list
    """
    if env_getter is None:
        env_getter = os.getenv
    
    agent_routes = []
    
    # Known agents
    known_agents = [
        "planner", "screenwriter", "author", "polisher", "editor",
        "scout", "secretary", "continuity_checker", "architect",
    ]
    
    # Get agent_llm mapping
    agent_llm = {}
    if hasattr(settings, "agent_llm") and settings.agent_llm:
        agent_llm = settings.agent_llm
    
    # Get default_llm
    default_llm = getattr(settings, "default_llm", "default")
    
    for agent in known_agents:
        route = agent_llm.get(agent, None)
        is_fallback = route is None
        profile_name = route or default_llm
        
        # Check if profile exists
        profile_exists = profile_name in llm_profiles
        profile_status = "valid"
        
        if not profile_exists:
            profile_status = "missing"
        else:
            # Check if profile is complete
            profile_data = llm_profiles[profile_name]
            if profile_data["status"] != "complete":
                profile_status = "incomplete"
        
        agent_routes.append({
            "agent": agent,
            "route": profile_name,
            "is_fallback": is_fallback,
            "profile_status": profile_status,
        })
    
    return {
        "agent_routes": agent_routes,
        "default_llm": default_llm,
    }


def _build_model_recommendations_data() -> dict:
    """Build model recommendations data for display.
    
    Returns:
        Dict with recommendations and catalog_status
    """
    try:
        from novel_factory.llm.catalog import load_default_catalog
        from novel_factory.llm.recommender import AgentRecommender
        
        # Load catalog
        catalog = load_default_catalog()
        
        if not catalog or not catalog.models:
            return {
                "recommendations": [],
                "catalog_status": "empty",
                "catalog_error": None,
            }
        
        # Create recommender
        recommender = AgentRecommender(catalog)
        
        # Get recommendations for all agents
        agents = [
            "planner", "screenwriter", "author", "polisher", "editor",
            "scout", "continuity_checker", "architect", "secretary",
        ]
        
        recommendations = []
        for agent in agents:
            recs = recommender.recommend_for_agent(agent, top_n=3)
            if recs:
                recommendations.append({
                    "agent": agent,
                    "top_recommendations": [
                        {
                            "model": rec.model,
                            "provider": rec.provider,
                            "display_name": rec.display_name,
                            "quality_tier": rec.quality_tier.value,
                            "cost_tier": rec.cost_tier.value,
                        }
                        for rec in recs
                    ],
                })
        
        return {
            "recommendations": recommendations,
            "catalog_status": "loaded",
            "catalog_error": None,
            "total_models": len(catalog.models),
        }
    
    except Exception as e:
        return {
            "recommendations": [],
            "catalog_status": "error",
            "catalog_error": safe_error_message(e),
        }


def _build_skill_status_data() -> dict:
    """Build Skill / QualityHub status data for display.
    
    Returns:
        Dict with skills, qualityhub, and agent_registry status
    """
    skills = []
    qualityhub_status = "unknown"
    agent_registry_status = "unknown"
    
    try:
        from novel_factory.skills.registry import SkillRegistry
        registry = SkillRegistry()
        skill_list = registry.list_skills()
        
        for skill_id in skill_list:
            skill = registry.get_skill(skill_id)
            if skill:
                skills.append({
                    "id": skill_id,
                    "name": getattr(skill, "name", skill_id),
                    "type": getattr(skill, "skill_type", "unknown"),
                    "enabled": True,  # If it's in the registry, it's enabled
                })
        
        qualityhub_status = "configured" if skills else "no_skills"
        agent_registry_status = "active"
    except Exception:
        qualityhub_status = "error"
        agent_registry_status = "error"
    
    return {
        "skills": skills,
        "qualityhub_status": qualityhub_status,
        "agent_registry_status": agent_registry_status,
    }


def _build_diagnostics_data(
    settings,
    llm_mode: str = "stub",
    env_getter: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
) -> dict:
    """Build diagnostics data for display.
    
    Args:
        settings: Settings object from app state
        llm_mode: Current LLM mode ("stub" or "real")
        env_getter: Function to get environment variables (defaults to os.getenv)
        
    Returns:
        Dict with errors and warnings
    """
    if env_getter is None:
        env_getter = os.getenv
    
    errors = []
    warnings = []
    
    # Check LLM profiles
    profiles_data = _build_llm_profiles_data(settings, llm_mode, env_getter)
    profile_names = {p["name"] for p in profiles_data["profiles"]}
    
    if not profiles_data["profiles"]:
        errors.append("No LLM profiles configured")
    else:
        for profile in profiles_data["profiles"]:
            # Check for missing env vars
            if profile["api_key_status"] == "missing":
                msg = (
                    f"Profile '{profile['name']}' has no API key configured "
                    f"(env var: {profile['api_key_env']})"
                )
                if llm_mode == "real":
                    errors.append(msg)
                else:
                    warnings.append(f"{msg} - stub mode allows this")
            
            if profile["base_url_status"] == "missing":
                msg = (
                    f"Profile '{profile['name']}' has no base URL configured "
                    f"(env var: {profile['base_url_env']})"
                )
                if llm_mode == "real":
                    errors.append(msg)
                else:
                    warnings.append(f"{msg} - stub mode allows this")
            
            # Check for incomplete profiles (no key or base URL at all)
            if profile["status"] == "incomplete":
                errors.append(
                    f"Profile '{profile['name']}' is incomplete (missing both key and base URL)"
                )
    
    # Check default_llm reference
    default_llm = profiles_data["default_llm"]
    if default_llm not in profile_names:
        errors.append(
            f"Default LLM profile '{default_llm}' does not exist. "
            f"Available profiles: {', '.join(sorted(profile_names)) or 'none'}"
        )
    
    # Check agent_llm references
    if hasattr(settings, "agent_llm") and settings.agent_llm:
        for agent, profile_name in settings.agent_llm.items():
            if profile_name not in profile_names:
                errors.append(
                    f"Agent '{agent}' references non-existent profile '{profile_name}'. "
                    f"Available profiles: {', '.join(sorted(profile_names)) or 'none'}"
                )
    
    # Check model recommendations
    recs_data = _build_model_recommendations_data()
    if recs_data["catalog_status"] == "error":
        warnings.append(f"Model catalog error: {recs_data['catalog_error']}")
    elif recs_data["catalog_status"] == "empty":
        warnings.append("Model catalog is empty")
    
    return {
        "errors": errors,
        "warnings": warnings,
    }


@router.get("")
async def settings_page(request: Request):
    """Display the Settings / LLM / Agent Ops Console page.
    
    Shows:
    - Runtime mode
    - LLM profiles
    - Agent routing
    - Model recommendations
    - Skill / QualityHub status
    - Diagnostics
    """
    try:
        settings = get_settings_for_web(request)
        
        # Get runtime mode
        llm_mode = getattr(request.app.state, "llm_mode", "stub")
        
        # Build data sections
        llm_data = _build_llm_profiles_data(settings, llm_mode)
        routing_data = _build_agent_routing_data(
            settings, 
            {p["name"]: p for p in llm_data["profiles"]},
            llm_mode
        )
        recommendations_data = _build_model_recommendations_data()
        skill_data = _build_skill_status_data()
        diagnostics_data = _build_diagnostics_data(settings, llm_mode)
        
        return render(
            request,
            "settings.html",
            {
                "llm_mode": llm_mode,
                "llm_profiles": llm_data["profiles"],
                "default_llm": llm_data["default_llm"],
                "agent_routes": routing_data["agent_routes"],
                "recommendations": recommendations_data["recommendations"],
                "catalog_status": recommendations_data["catalog_status"],
                "catalog_error": recommendations_data.get("catalog_error"),
                "total_models": recommendations_data.get("total_models", 0),
                "skills": skill_data["skills"],
                "qualityhub_status": skill_data["qualityhub_status"],
                "agent_registry_status": skill_data["agent_registry_status"],
                "diagnostics_errors": diagnostics_data["errors"],
                "diagnostics_warnings": diagnostics_data["warnings"],
            },
        )
    except Exception as e:
        return render(request, "settings.html", {"error": safe_error_message(e)})
