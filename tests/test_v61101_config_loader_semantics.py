"""v6.11.01: Pin load_settings_with_cli env/CLI override semantics.

Characterization tests for the configuration loader that v6.11.01 designates
as the single source of truth (see
docs/codex/planning/novel-factory-v6.11.01-architecture-debt-optimization-plan.md,
P1). They verify the documented priority
``CLI > OS env > .env > YAML > defaults``. The ``.env`` layer is disabled
(``load_env=False``) so the tests stay hermetic and do not read the developer's
local ``.env``.
"""

from __future__ import annotations

import pytest

from novel_factory.config.loader import load_settings_with_cli


@pytest.fixture
def clean_env(monkeypatch):
    """Remove env vars that could leak into loader tests."""
    for var in (
        "NOVEL_FACTORY_DB",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "LLM_MODE",
    ):
        monkeypatch.delenv(var, raising=False)


def test_env_db_path_overrides_default(clean_env, monkeypatch):
    """OS env NOVEL_FACTORY_DB is applied unconditionally over defaults."""
    monkeypatch.setenv("NOVEL_FACTORY_DB", "/tmp/v61101_loader_test.db")
    settings = load_settings_with_cli(load_env=False)
    assert settings.db_path == "/tmp/v61101_loader_test.db"


def test_env_llm_api_key_overrides_default(clean_env, monkeypatch):
    """OS env OPENAI_API_KEY is applied unconditionally over llm.yaml/defaults."""
    monkeypatch.setenv("OPENAI_API_KEY", "v61101-test-key")
    settings = load_settings_with_cli(load_env=False)
    assert settings.llm.api_key == "v61101-test-key"


def test_cli_db_path_overrides_env(clean_env, monkeypatch):
    """CLI db_path takes precedence over OS env NOVEL_FACTORY_DB."""
    monkeypatch.setenv("NOVEL_FACTORY_DB", "/tmp/env_value.db")
    settings = load_settings_with_cli(db_path="/tmp/cli_value.db", load_env=False)
    assert settings.db_path == "/tmp/cli_value.db"


def test_cli_llm_api_key_overrides_env(clean_env, monkeypatch):
    """CLI llm_api_key takes precedence over OS env OPENAI_API_KEY."""
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    settings = load_settings_with_cli(llm_api_key="cli-key", load_env=False)
    assert settings.llm.api_key == "cli-key"


def test_no_env_keeps_default_db_path(clean_env):
    """With no env and no CLI, the package default db_path is preserved."""
    settings = load_settings_with_cli(load_env=False)
    # Default db_path comes from Settings/DEFAULT_DB_PATH; just assert it is
    # not accidentally overridden to an env value.
    assert settings.db_path
    assert "env_value" not in settings.db_path
