"""Config and LLM routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import (
    get_repo,
    render,
    safe_error_message,
    mask_secret,
    get_settings_for_web,
)

router = APIRouter()


@router.get("")
async def config_overview(request: Request):
    """Show configuration and LLM overview."""
    try:
        settings = get_settings_for_web(request)

        # Get LLM profiles
        profiles = []
        if hasattr(settings, "llm_profiles") and settings.llm_profiles:
            for name, profile in settings.llm_profiles.items():
                profiles.append({
                    "name": name,
                    "provider": getattr(profile, "provider", "unknown"),
                    "model": getattr(profile, "model", "unknown"),
                    "has_key": bool(getattr(profile, "api_key", None)),
                    "key_status": mask_secret(getattr(profile, "api_key", None)),
                })

        # Get agent routes
        agent_routes = []
        if hasattr(settings, "agent_llm_routes") and settings.agent_llm_routes:
            for agent, route in settings.agent_llm_routes.items():
                agent_routes.append({"agent": agent, "route": route})

        # LLM validation (simplified - just check if profiles exist)
        validation_errors = []
        validation_warnings = []

        if not profiles:
            validation_warnings.append("No LLM profiles configured")

        # Check for missing keys
        for p in profiles:
            if not p["has_key"]:
                validation_warnings.append(f"Profile '{p['name']}' has no API key configured")

        return render(
            request,
            "config.html",
            {
                "profiles": profiles,
                "agent_routes": agent_routes,
                "validation_errors": validation_errors,
                "validation_warnings": validation_warnings,
            },
        )
    except Exception as e:
        return render(request, "config.html", {"error": safe_error_message(e)})
