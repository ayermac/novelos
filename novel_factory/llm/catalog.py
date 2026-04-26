"""LLM Model Catalog data models and loader for v3.9.

Provides offline catalog of LLM models with capability tags,
pricing tiers, and recommendation metadata.
"""

from __future__ import annotations

import importlib.resources
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────

class CostTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LatencyTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class QualityTier(str, Enum):
    DRAFT = "draft"
    STANDARD = "standard"
    PREMIUM = "premium"


class Strength(str, Enum):
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"
    PROSE = "prose"
    EDITING = "editing"
    JSON = "json"
    PLANNING = "planning"
    SAFETY = "safety"
    SPEED = "speed"


# ── Tier ordering for comparison ───────────────────────────────

_COST_ORDER = {"low": 0, "medium": 1, "high": 2}
_LATENCY_ORDER = {"low": 0, "medium": 1, "high": 2}
_QUALITY_ORDER = {"draft": 0, "standard": 1, "premium": 2}


# ── Data Models ────────────────────────────────────────────────

class LLMModelSpec(BaseModel):
    """Specification for a single LLM model in the catalog."""

    provider: str
    model: str
    display_name: str
    profile_template: str = "openai_compatible"
    context_window: int = 4096
    cost_tier: CostTier = CostTier.LOW
    latency_tier: LatencyTier = LatencyTier.MEDIUM
    quality_tier: QualityTier = QualityTier.DRAFT
    strengths: list[Strength] = Field(default_factory=list)
    recommended_agents: list[str] = Field(default_factory=list)
    notes: str = ""

    @property
    def cost_rank(self) -> int:
        """Numeric rank for cost comparison (lower = cheaper)."""
        return _COST_ORDER.get(self.cost_tier.value, 0)

    @property
    def latency_rank(self) -> int:
        """Numeric rank for latency comparison (lower = faster)."""
        return _LATENCY_ORDER.get(self.latency_tier.value, 0)

    @property
    def quality_rank(self) -> int:
        """Numeric rank for quality comparison (higher = better)."""
        return _QUALITY_ORDER.get(self.quality_tier.value, 0)

    def to_display_dict(self) -> dict[str, Any]:
        """Convert to dictionary for display, excluding any secrets."""
        return {
            "provider": self.provider,
            "model": self.model,
            "display_name": self.display_name,
            "profile_template": self.profile_template,
            "context_window": self.context_window,
            "cost_tier": self.cost_tier.value,
            "latency_tier": self.latency_tier.value,
            "quality_tier": self.quality_tier.value,
            "strengths": [s.value for s in self.strengths],
            "recommended_agents": self.recommended_agents,
            "notes": self.notes,
        }


class LLMCatalog(BaseModel):
    """Collection of LLM model specifications."""

    models: list[LLMModelSpec] = Field(default_factory=list)

    def get_by_provider_model(self, provider: str, model: str) -> Optional[LLMModelSpec]:
        """Look up a model by provider and model name."""
        for spec in self.models:
            if spec.provider == provider and spec.model == model:
                return spec
        return None

    def get_by_agent(self, agent_id: str) -> list[LLMModelSpec]:
        """Get all models that recommend a specific agent."""
        return [m for m in self.models if agent_id in m.recommended_agents]

    def get_by_strength(self, strength: str | Strength) -> list[LLMModelSpec]:
        """Get all models with a specific strength."""
        if isinstance(strength, str):
            strength = Strength(strength)
        return [m for m in self.models if strength in m.strengths]

    def get_by_cost_tier(self, max_tier: str | CostTier) -> list[LLMModelSpec]:
        """Get models at or below a cost tier."""
        if isinstance(max_tier, str):
            max_tier = CostTier(max_tier)
        max_rank = _COST_ORDER.get(max_tier.value, 2)
        return [m for m in self.models if m.cost_rank <= max_rank]

    def get_by_quality_tier(self, min_tier: str | QualityTier) -> list[LLMModelSpec]:
        """Get models at or above a quality tier."""
        if isinstance(min_tier, str):
            min_tier = QualityTier(min_tier)
        min_rank = _QUALITY_ORDER.get(min_tier.value, 0)
        return [m for m in self.models if m.quality_rank >= min_rank]

    def get_by_provider(self, provider: str) -> list[LLMModelSpec]:
        """Get all models from a specific provider."""
        return [m for m in self.models if m.provider == provider]

    def all_providers(self) -> list[str]:
        """Get unique provider names."""
        return sorted(set(m.provider for m in self.models))

    def to_display_dict(self) -> dict[str, Any]:
        """Convert to display dictionary."""
        return {
            "models": [m.to_display_dict() for m in self.models],
            "total": len(self.models),
        }


# ── Loader ─────────────────────────────────────────────────────

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_llm_catalog(path: str | Path | None = None) -> LLMCatalog:
    """Load the LLM model catalog from YAML.

    Args:
        path: Path to catalog YAML file.
              Defaults to novel_factory/config/llm_catalog.yaml.

    Returns:
        LLMCatalog instance.

    Raises:
        FileNotFoundError: If catalog file not found.
        ValueError: If catalog data is invalid.
    """
    if path is None:
        path = _CATALOG_DIR / "llm_catalog.yaml"
    else:
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"LLM catalog not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    catalog_data = data.get("catalog", [])
    if not isinstance(catalog_data, list):
        raise ValueError("LLM catalog 'catalog' field must be a list")

    models = []
    for i, entry in enumerate(catalog_data):
        if not isinstance(entry, dict):
            raise ValueError(f"Catalog entry {i} must be a dict, got {type(entry)}")
        try:
            models.append(LLMModelSpec(**entry))
        except Exception as e:
            raise ValueError(f"Invalid catalog entry {i}: {e}") from e

    return LLMCatalog(models=models)
