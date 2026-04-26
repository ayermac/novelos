"""v3.9 LLM Catalog tests.

Covers:
- Default catalog file loading
- Model spec schema validation
- Catalog query methods (by agent, strength, cost, quality, provider)
- Display dict format (no API keys)
- Error handling (missing file, invalid data)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from novel_factory.llm.catalog import (
    CostTier,
    LatencyTier,
    LLMCatalog,
    LLMModelSpec,
    QualityTier,
    Strength,
    load_llm_catalog,
)


# ── Default catalog loading ────────────────────────────────────

class TestDefaultCatalogLoading:
    """Test loading the default llm_catalog.yaml."""

    def test_default_catalog_loads(self):
        """Default catalog file can be loaded without error."""
        catalog = load_llm_catalog()
        assert isinstance(catalog, LLMCatalog)
        assert len(catalog.models) > 0

    def test_default_catalog_has_multiple_providers(self):
        """Default catalog contains models from multiple providers."""
        catalog = load_llm_catalog()
        providers = catalog.all_providers()
        assert len(providers) >= 3
        assert "openai" in providers
        assert "deepseek" in providers

    def test_default_catalog_has_stub_model(self):
        """Default catalog contains a stub model for testing."""
        catalog = load_llm_catalog()
        stub = catalog.get_by_provider_model("local", "stub")
        assert stub is not None
        assert stub.profile_template == "stub"

    def test_default_catalog_no_api_keys(self):
        """Default catalog display dict contains no API keys."""
        catalog = load_llm_catalog()
        display = catalog.to_display_dict()
        display_json = json.dumps(display)
        assert "api_key" not in display_json.lower() or "api_key_env" not in display_json
        # Ensure no secret-like values
        assert "sk-" not in display_json
        assert "key=" not in display_json


# ── Model spec schema validation ───────────────────────────────

class TestModelSpecValidation:
    """Test LLMModelSpec schema validation."""

    def test_minimal_valid_spec(self):
        """Minimal valid spec with required fields only."""
        spec = LLMModelSpec(
            provider="test",
            model="test-model",
            display_name="Test Model",
        )
        assert spec.provider == "test"
        assert spec.model == "test-model"
        assert spec.display_name == "Test Model"
        assert spec.profile_template == "openai_compatible"
        assert spec.cost_tier == CostTier.LOW
        assert spec.latency_tier == LatencyTier.MEDIUM
        assert spec.quality_tier == QualityTier.DRAFT

    def test_full_spec(self):
        """Full spec with all fields."""
        spec = LLMModelSpec(
            provider="openai",
            model="gpt-4o",
            display_name="GPT-4o",
            profile_template="openai_compatible",
            context_window=128000,
            cost_tier=CostTier.HIGH,
            latency_tier=LatencyTier.MEDIUM,
            quality_tier=QualityTier.PREMIUM,
            strengths=[Strength.REASONING, Strength.PROSE, Strength.JSON],
            recommended_agents=["planner", "author"],
            notes="Flagship model",
        )
        assert spec.context_window == 128000
        assert len(spec.strengths) == 3
        assert "planner" in spec.recommended_agents

    def test_invalid_cost_tier(self):
        """Invalid cost tier raises validation error."""
        with pytest.raises(Exception):
            LLMModelSpec(
                provider="test",
                model="test",
                display_name="Test",
                cost_tier="invalid",
            )

    def test_invalid_strength(self):
        """Invalid strength raises validation error."""
        with pytest.raises(Exception):
            LLMModelSpec(
                provider="test",
                model="test",
                display_name="Test",
                strengths=["invalid_strength"],
            )

    def test_tier_ranks(self):
        """Tier rank properties return correct numeric values."""
        spec_low = LLMModelSpec(
            provider="test", model="test", display_name="Test",
            cost_tier="low", latency_tier="low", quality_tier="draft",
        )
        assert spec_low.cost_rank == 0
        assert spec_low.latency_rank == 0
        assert spec_low.quality_rank == 0

        spec_high = LLMModelSpec(
            provider="test", model="test", display_name="Test",
            cost_tier="high", latency_tier="high", quality_tier="premium",
        )
        assert spec_high.cost_rank == 2
        assert spec_high.latency_rank == 2
        assert spec_high.quality_rank == 2

    def test_display_dict_no_secrets(self):
        """Display dict does not contain any secret fields."""
        spec = LLMModelSpec(
            provider="test", model="test", display_name="Test",
            strengths=[Strength.REASONING],
        )
        d = spec.to_display_dict()
        assert "api_key" not in d
        assert "api_key_env" not in d
        assert "base_url" not in d
        assert "base_url_env" not in d
        assert "provider" in d
        assert "model" in d
        assert "strengths" in d
        assert isinstance(d["strengths"], list)
        assert d["strengths"] == ["reasoning"]


# ── Catalog query methods ──────────────────────────────────────

class TestCatalogQueries:
    """Test LLMCatalog query methods."""

    @pytest.fixture
    def catalog(self):
        """Load the default catalog for testing."""
        return load_llm_catalog()

    def test_get_by_provider_model(self, catalog):
        """Lookup by provider+model returns correct spec."""
        spec = catalog.get_by_provider_model("openai", "gpt-4o")
        assert spec is not None
        assert spec.display_name == "GPT-4o"

    def test_get_by_provider_model_not_found(self, catalog):
        """Lookup for non-existent model returns None."""
        spec = catalog.get_by_provider_model("nonexistent", "no-model")
        assert spec is None

    def test_get_by_agent(self, catalog):
        """Lookup by agent returns models recommended for that agent."""
        author_models = catalog.get_by_agent("author")
        assert len(author_models) > 0
        for m in author_models:
            assert "author" in m.recommended_agents

    def test_get_by_strength(self, catalog):
        """Lookup by strength returns models with that strength."""
        reasoning_models = catalog.get_by_strength("reasoning")
        assert len(reasoning_models) > 0
        for m in reasoning_models:
            assert Strength.REASONING in m.strengths

    def test_get_by_cost_tier(self, catalog):
        """Filter by cost tier returns models at or below that tier."""
        low_cost = catalog.get_by_cost_tier("low")
        assert len(low_cost) > 0
        for m in low_cost:
            assert m.cost_rank <= 0  # only low cost

        medium_cost = catalog.get_by_cost_tier("medium")
        assert len(medium_cost) >= len(low_cost)
        for m in medium_cost:
            assert m.cost_rank <= 1  # low or medium

    def test_get_by_quality_tier(self, catalog):
        """Filter by quality tier returns models at or above that tier."""
        premium = catalog.get_by_quality_tier("premium")
        assert len(premium) > 0
        for m in premium:
            assert m.quality_rank >= 2

        standard = catalog.get_by_quality_tier("standard")
        assert len(standard) >= len(premium)

    def test_get_by_provider(self, catalog):
        """Filter by provider returns models from that provider."""
        openai_models = catalog.get_by_provider("openai")
        assert len(openai_models) > 0
        for m in openai_models:
            assert m.provider == "openai"

    def test_all_providers(self, catalog):
        """all_providers returns sorted unique list."""
        providers = catalog.all_providers()
        assert providers == sorted(providers)
        assert len(set(providers)) == len(providers)  # unique

    def test_to_display_dict(self, catalog):
        """Catalog display dict has expected structure."""
        d = catalog.to_display_dict()
        assert "models" in d
        assert "total" in d
        assert d["total"] == len(d["models"])
        assert d["total"] > 0


# ── Error handling ─────────────────────────────────────────────

class TestCatalogErrors:
    """Test catalog loading error handling."""

    def test_missing_file(self):
        """Loading from non-existent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_llm_catalog("/nonexistent/path/catalog.yaml")

    def test_invalid_catalog_not_list(self):
        """Catalog with non-list 'catalog' field raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"catalog": "not a list"}, f)
            f.flush()
            with pytest.raises(ValueError, match="must be a list"):
                load_llm_catalog(f.name)

    def test_invalid_entry_missing_required(self):
        """Catalog entry missing required field raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"catalog": [{"provider": "test"}]}, f)  # missing model, display_name
            f.flush()
            with pytest.raises(ValueError, match="Invalid catalog entry"):
                load_llm_catalog(f.name)

    def test_custom_path_loading(self):
        """Custom path catalog loading works."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "catalog": [{
                    "provider": "custom",
                    "model": "custom-model",
                    "display_name": "Custom Model",
                }]
            }, f)
            f.flush()
            catalog = load_llm_catalog(f.name)
            assert len(catalog.models) == 1
            assert catalog.models[0].provider == "custom"
