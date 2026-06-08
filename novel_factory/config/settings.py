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
    request_timeout_seconds: int = 60
    retry_attempts: int = 3
    retry_min_seconds: float = 1.0
    retry_max_seconds: float = 30.0
    min_interval_seconds: float = 0.0


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
    node_timeout_seconds: int = 300  # v6.10.0: Per-node execution timeout (5 minutes)
    node_timeout_overrides: dict[str, int] = Field(
        default_factory=lambda: {
            "memory_curator": 600,
        },
    )


class RuntimeBudgetConfig(BaseModel):
    """Token budget guardrails for real LLM production runs.

    A value of 0 disables the corresponding limit.
    """

    chapter_token_limit: int = 0
    project_token_limit: int = 0
    auto_run_token_limit: int = 0


# ── v6.10.0: Agentic mode configuration ──────────────────────


class AgenticAgentConfig(BaseModel):
    """单个 Agent 的 Agentic 配置."""

    agentic_mode: bool = False
    max_tool_rounds: int = 3


class AgenticConfig(BaseModel):
    """全局 Agentic 配置（v6.10.0 知识 Skill + Function Calling）."""

    enabled: bool = False
    agents: dict[str, AgenticAgentConfig] = Field(
        default_factory=lambda: {
            "planner": AgenticAgentConfig(),
            "screenwriter": AgenticAgentConfig(),
            "author": AgenticAgentConfig(),
            "polisher": AgenticAgentConfig(),
            "editor": AgenticAgentConfig(),
            "memory_curator": AgenticAgentConfig(),
        }
    )


class KnowledgeAgentConfig(BaseModel):
    """Per-agent Knowledge Skill strategy."""

    token_budget: int = 2400
    agentic_mode: bool = False
    max_tool_rounds: int = 3


class KnowledgeConfig(BaseModel):
    """Knowledge Skill governance configuration."""

    enabled: bool = True
    default_injection_mode: str = "auto"
    default_token_budget: int = 2400
    agents: dict[str, KnowledgeAgentConfig] = Field(
        default_factory=lambda: {
            "planner": KnowledgeAgentConfig(token_budget=1800),
            "screenwriter": KnowledgeAgentConfig(token_budget=2200),
            "author": KnowledgeAgentConfig(token_budget=3000),
            "polisher": KnowledgeAgentConfig(token_budget=2200),
            "editor": KnowledgeAgentConfig(token_budget=2200),
            "memory_curator": KnowledgeAgentConfig(token_budget=1200),
        }
    )


class Settings(BaseModel):
    """Root settings object."""

    db_path: str = str(DEFAULT_DB_PATH)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    quality_gate: QualityGateConfig = Field(default_factory=QualityGateConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    runtime_budget: RuntimeBudgetConfig = Field(default_factory=RuntimeBudgetConfig)
    
    # v3.1: LLM profiles and agent routing
    default_llm: str = "default"
    llm_profiles: dict[str, LLMProfile] = Field(default_factory=dict)
    agent_llm: dict[str, str] = Field(default_factory=dict)
    agent_llm_fallback: dict[str, str] = Field(default_factory=dict)

    # v6.10.0: Agentic mode
    agentic: AgenticConfig = Field(default_factory=AgenticConfig)

    # v6.10.1: Knowledge Skill governance
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)


# ── Loaders ────────────────────────────────────────────────────

def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from YAML + env overrides."""
    data: dict[str, Any] = {}

    config_exists = False
    if config_path:
        try:
            config_exists = Path(config_path).exists()
        except OSError:
            config_exists = False

    if config_path and config_exists:
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
