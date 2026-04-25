"""Shared helpers for CLI commands.

Provides settings loading, LLM mode resolution, and dispatcher construction.
"""

from __future__ import annotations

from ..config.loader import load_settings_with_cli, validate_settings
from ..config.settings import Settings
from ..db.connection import init_db
from ..db.repository import Repository
from ..dispatcher import Dispatcher
from ..llm.stub_provider import StubLLM as _StubLLM
from ..llm.provider import LLMProvider

import json
import sys
from typing import Any


def _get_effective_llm_mode(args) -> str:
    """Get effective LLM mode with proper global/subcommand priority.

    Priority:
    1. Subcommand --llm-mode (if explicitly provided by user)
    2. Global --llm-mode (if explicitly provided by user)
    3. Default "real"

    Since argparse writes both global and subcommand --llm-mode to
    args.llm_mode (subcommand default overwrites global), we use
    separate dest names to distinguish them.
    """
    return (
        getattr(args, "llm_mode", None)
        or getattr(args, "global_llm_mode", None)
        or "real"
    )


def _get_settings(args) -> Settings:
    """Load settings with explicit priority."""
    llm_mode = _get_effective_llm_mode(args)
    return load_settings_with_cli(
        config_path=getattr(args, "config", None),
        db_path=getattr(args, "db_path", None),
        llm_mode=llm_mode,
        llm_api_key=getattr(args, "llm_api_key", None),
        llm_base_url=getattr(args, "llm_base_url", None),
        llm_model=getattr(args, "llm_model", None),
    )


def _get_llm(settings: Settings, llm_mode: str = "real") -> LLMProvider:
    """Create LLM provider from settings and llm_mode.

    DEPRECATED: This function is kept for backward compatibility.
    Prefer _build_dispatcher() for v3.1+ agent-level routing.
    """
    if llm_mode == "stub":
        return _StubLLM()
    # real mode
    if not settings.llm.api_key:
        raise ValueError("API key not configured for real mode. Set OPENAI_API_KEY environment variable or configure in .env file.")
    from ..llm.openai_compatible import OpenAICompatibleProvider
    return OpenAICompatibleProvider(settings.llm)


def _build_dispatcher(repo, settings: Settings, llm_mode: str = "real"):
    """Build Dispatcher with LLMRouter support (v3.1).

    This function implements the priority:
    1. Stub mode: uses _StubLLM (backward compatible)
    2. Real mode with llm_profiles: builds LLMRouter and passes to Dispatcher
    3. Real mode without llm_profiles: falls back to old _get_llm() for backward compatibility

    Args:
        repo: Repository instance
        settings: Settings instance
        llm_mode: "stub" or "real"

    Returns:
        Dispatcher instance with appropriate LLM configuration
    """
    # Stub mode: always use stub LLM, regardless of llm_profiles
    if llm_mode == "stub":
        stub_llm = _StubLLM()
        # If llm_profiles is configured, use LLMRouter with stub
        if settings.llm_profiles and len(settings.llm_profiles) > 0:
            from ..llm.profiles import LLMProfilesConfig
            from ..llm.router import LLMRouter

            config = LLMProfilesConfig(
                default_llm=settings.default_llm,
                llm_profiles=settings.llm_profiles,
                agent_llm=settings.agent_llm,
            )

            router = LLMRouter(config, stub_provider=stub_llm, llm_mode="stub")
            return Dispatcher(repo, llm_router=router, max_retries=settings.quality_gate.max_retries)
        else:
            # No llm_profiles, use single stub LLM
            return Dispatcher(repo, llm=stub_llm, max_retries=settings.quality_gate.max_retries)

    # Real mode: load .env for API keys (non-polluting)
    from ..config.env_loader import load_dotenv, create_env_getter

    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)

    # Real mode: check if llm_profiles is configured
    if settings.llm_profiles and len(settings.llm_profiles) > 0:
        # Profile mode: build LLMRouter and let it validate per-profile keys
        from ..llm.profiles import LLMProfilesConfig
        from ..llm.router import LLMRouter

        config = LLMProfilesConfig(
            default_llm=settings.default_llm,
            llm_profiles=settings.llm_profiles,
            agent_llm=settings.agent_llm,
        )

        # Create LLMRouter with custom env_getter — validation happens per-profile
        router = LLMRouter(config, llm_mode=llm_mode, env_getter=env_getter)

        return Dispatcher(repo, llm_router=router, max_retries=settings.quality_gate.max_retries)
    else:
        # Legacy single-LLM fallback: check OPENAI_API_KEY before constructing
        api_key_available = bool(env_getter("OPENAI_API_KEY"))
        if not api_key_available and not settings.llm.api_key:
            raise ValueError("API key not configured for real mode. Set OPENAI_API_KEY environment variable or configure in .env file.")

        llm = _get_llm(settings, llm_mode)
        return Dispatcher(repo, llm=llm, max_retries=settings.quality_gate.max_retries)
