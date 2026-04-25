"""Configuration management for Novel Factory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

# Import LLM profiles for v3.1
from ..llm.profiles import LLMProfile


# ── Project paths ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "novel_factory.db"
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent


# ── Pydantic config models ─────────────────────────────────────


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = Field(default="", repr=False)
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096


class QualityGateConfig(BaseModel):
    """Quality gate thresholds."""

    pass_score: int = 90
    max_retries: int = 3
    death_penalty_words: list[str] = Field(
        default_factory=lambda: [
            "冷笑", "嘴角微扬", "嘴角勾起", "倒吸一口凉气",
            "眼中闪过", "眼中闪现", "眼中精光", "眼中寒芒",
            "心中暗想", "心道", "夜色笼罩", "夜幕降临",
        ]
    )


class WorkflowConfig(BaseModel):
    """Workflow runtime configuration."""

    task_timeout_minutes: int = 30
    checkpoint_enabled: bool = True


class Settings(BaseModel):
    """Root settings object."""

    db_path: str = str(DEFAULT_DB_PATH)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    quality_gate: QualityGateConfig = Field(default_factory=QualityGateConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    
    # v3.1: LLM profiles and agent routing
    default_llm: str = "default"
    llm_profiles: dict[str, LLMProfile] = Field(default_factory=dict)
    agent_llm: dict[str, str] = Field(default_factory=dict)


# ── Loaders ────────────────────────────────────────────────────

def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from YAML + env overrides."""
    data: dict[str, Any] = {}

    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # env overrides
    if env_db := os.getenv("NOVEL_FACTORY_DB"):
        data.setdefault("db_path", env_db)
    if env_key := os.getenv("OPENAI_API_KEY"):
        data.setdefault("llm", {})
        data["llm"]["api_key"] = env_key
    if env_base := os.getenv("OPENAI_BASE_URL"):
        data.setdefault("llm", {})
        data["llm"]["base_url"] = env_base

    return Settings(**data)
