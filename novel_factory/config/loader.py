"""Configuration loader with explicit priority.

Priority (highest to lowest):
1. CLI arguments (passed via Settings constructor)
2. Environment variables
3. Project root .env file
4. --config YAML file
5. Package default YAML (novel_factory/config/*.yaml)
6. Pydantic default values

Usage:
    from novel_factory.config.loader import load_settings_with_cli
    settings = load_settings_with_cli(
        config_path=args.config if args.config else None,
        db_path=args.db_path if args.db_path else None,
        llm_mode=args.llm_mode if hasattr(args, 'llm_mode') else None,
    )
"""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
from typing import Any

import yaml
from .settings import Settings, LLMConfig, QualityGateConfig, WorkflowConfig
from .env_loader import load_dotenv


def _load_package_yaml(name: str) -> dict[str, Any]:
    """Load YAML from package data."""
    try:
        # Try importlib.resources first
        if importlib.resources.is_resource("novel_factory.config", name):
            text = importlib.resources.files("novel_factory.config").joinpath(name).read_text(encoding="utf-8")
            return yaml.safe_load(text) or {}
    except (ImportError, FileNotFoundError, AttributeError):
        pass
    # Fallback to file path
    fallback = Path(__file__).resolve().parent / name
    if fallback.exists():
        with open(fallback, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_default_config() -> dict[str, Any]:
    """Load default configuration from package YAML files."""
    config = {}
    # Load llm.yaml
    llm_data = _load_package_yaml("llm.yaml")
    if llm_data:
        config["llm"] = llm_data
    # Load agents.yaml
    agents_data = _load_package_yaml("agents.yaml")
    if agents_data:
        config["agents"] = agents_data
    return config


def load_settings_with_cli(
    config_path: str | Path | None = None,
    db_path: str | None = None,
    llm_mode: str | None = None,
    llm_api_key: str | None = None,
    llm_base_url: str | None = None,
    llm_model: str | None = None,
    load_env: bool = True,
) -> Settings:
    """Load settings with explicit priority.

    Args:
        config_path: Path to custom YAML config file.
        db_path: Database path override.
        llm_mode: LLM mode override ('stub' or 'real').
        llm_api_key: LLM API key override.
        llm_base_url: LLM base URL override.
        llm_model: LLM model override.
        load_env: Whether to load .env file (default True).

    Returns:
        Settings object with all overrides applied.
    """
    # Load .env file (non-polluting, returns dict)
    dotenv_vars = {}
    if load_env:
        dotenv_vars = load_dotenv()
    
    # Create env getter with priority: OS env > .env > default
    from .env_loader import create_env_getter
    env_getter = create_env_getter(dotenv_vars)
    
    # Start with package defaults
    data = load_default_config()

    # Override with --config YAML
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
            # Deep merge (simplified)
            for key, value in config_data.items():
                if isinstance(value, dict) and key in data:
                    data[key].update(value)
                else:
                    data[key] = value

    # Environment variable overrides (OS env > .env > default)
    if env_db := env_getter("NOVEL_FACTORY_DB"):
        data["db_path"] = env_db
    if env_key := env_getter("OPENAI_API_KEY"):
        data.setdefault("llm", {})
        data["llm"]["api_key"] = env_key
    if env_base := env_getter("OPENAI_BASE_URL"):
        data.setdefault("llm", {})
        data["llm"]["base_url"] = env_base

    # CLI argument overrides (highest priority)
    if db_path:
        data["db_path"] = db_path
    if llm_api_key:
        data.setdefault("llm", {})
        data["llm"]["api_key"] = llm_api_key
    if llm_base_url:
        data.setdefault("llm", {})
        data["llm"]["base_url"] = llm_base_url
    if llm_model:
        data.setdefault("llm", {})
        data["llm"]["model"] = llm_model

    return Settings(**data)


def validate_settings(settings: Settings, llm_mode: str = "real") -> list[str]:
    """Validate settings and return list of issues."""
    issues = []
    # DB path must be writable parent directory
    db_path = Path(settings.db_path)
    if not db_path.parent.exists():
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            issues.append(f"Cannot create DB directory {db_path.parent}: {e}")
    # LLM validation
    if llm_mode == "real":
        if not settings.llm.api_key:
            issues.append("LLM API key is required for real mode")
        if not settings.llm.base_url:
            issues.append("LLM base URL is required for real mode")
        if not settings.llm.model:
            issues.append("LLM model is required for real mode")
    # Quality gate
    if settings.quality_gate.pass_score < 0 or settings.quality_gate.pass_score > 100:
        issues.append(f"pass_score must be between 0 and 100, got {settings.quality_gate.pass_score}")
    if settings.quality_gate.max_retries < 0:
        issues.append(f"max_retries must be >= 0, got {settings.quality_gate.max_retries}")
    return issues