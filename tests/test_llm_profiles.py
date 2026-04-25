"""Tests for LLM profiles (v3.1)."""

from __future__ import annotations

import os
import pytest
from pathlib import Path
from typing import Optional

from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
from novel_factory.config.env_loader import load_dotenv, mask_api_key


class TestLLMProfile:
    """Tests for LLMProfile model."""

    def test_profile_with_direct_values(self):
        """Profile can be created with direct base_url and api_key."""
        profile = LLMProfile(
            provider="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key="sk-test-key",
            model="gpt-4o-mini",
        )
        
        assert profile.provider == "openai_compatible"
        assert profile.base_url == "https://api.openai.com/v1"
        assert profile.api_key == "sk-test-key"
        assert profile.model == "gpt-4o-mini"

    def test_profile_with_env_vars(self):
        """Profile can resolve values from environment variables."""
        profile = LLMProfile(
            provider="openai_compatible",
            base_url_env="TEST_BASE_URL",
            api_key_env="TEST_API_KEY",
            model="gpt-4o-mini",
        )
        
        # Mock env getter
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            if name == "TEST_API_KEY":
                return "sk-test-from-env"
            return default
        
        assert profile.get_resolved_base_url(mock_getenv) == "https://test.example.com/v1"
        assert profile.get_resolved_api_key(mock_getenv) == "sk-test-from-env"

    def test_profile_direct_overrides_env(self):
        """Direct values take precedence over environment variables."""
        profile = LLMProfile(
            provider="openai_compatible",
            base_url="https://direct.example.com/v1",
            base_url_env="TEST_BASE_URL",
            api_key="sk-direct-key",
            api_key_env="TEST_API_KEY",
            model="gpt-4o-mini",
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            return "should-not-be-used"
        
        assert profile.get_resolved_base_url(mock_getenv) == "https://direct.example.com/v1"
        assert profile.get_resolved_api_key(mock_getenv) == "sk-direct-key"

    def test_to_display_dict_masks_key(self):
        """to_display_dict masks API key by default."""
        profile = LLMProfile(
            provider="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key="sk-secret-key-12345",
            model="gpt-4o-mini",
        )
        
        display = profile.to_display_dict(mask_key=True)
        assert display["api_key"] == "***"
        assert "sk-secret" not in str(display)

    def test_to_display_dict_shows_env_var_names(self):
        """to_display_dict includes env var names if present."""
        profile = LLMProfile(
            provider="openai_compatible",
            base_url_env="OPENAI_BASE_URL",
            api_key_env="OPENAI_API_KEY",
            model="gpt-4o-mini",
        )
        
        display = profile.to_display_dict(mask_key=True)
        assert display["base_url_env"] == "OPENAI_BASE_URL"
        assert display["api_key_env"] == "OPENAI_API_KEY"


class TestLLMProfilesConfig:
    """Tests for LLMProfilesConfig."""

    def test_get_profile_for_agent_with_specific_profile(self):
        """Agent with specific profile gets that profile."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                ),
                "author": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://openrouter.ai/api/v1",
                    model="anthropic/claude-3.7-sonnet",
                ),
            },
            agent_llm={"author": "author"},
        )
        
        profile_name, profile = config.get_profile_for_agent("author")
        assert profile_name == "author"
        assert profile.model == "anthropic/claude-3.7-sonnet"

    def test_get_profile_for_agent_falls_back_to_default(self):
        """Agent without specific profile falls back to default."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                ),
            },
            agent_llm={},
        )
        
        profile_name, profile = config.get_profile_for_agent("editor")
        assert profile_name == "default"
        assert profile.model == "gpt-4o-mini"

    def test_get_profile_for_agent_missing_profile(self):
        """Missing profile returns None."""
        config = LLMProfilesConfig(
            default_llm="nonexistent",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                ),
            },
            agent_llm={},
        )
        
        profile_name, profile = config.get_profile_for_agent("editor")
        assert profile_name == "nonexistent"
        assert profile is None

    def test_validate_profiles_missing_default(self):
        """Validation fails if default_llm not in profiles."""
        config = LLMProfilesConfig(
            default_llm="missing",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                ),
            },
            agent_llm={},
        )
        
        issues = config.validate_profiles()
        assert len(issues) == 1
        assert "default_llm 'missing' not found" in issues[0]

    def test_validate_profiles_missing_agent_profile(self):
        """Validation fails if agent_llm references non-existent profile."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                ),
            },
            agent_llm={"author": "nonexistent"},
        )
        
        issues = config.validate_profiles()
        assert len(issues) == 1
        assert "agent_llm[author] references non-existent profile" in issues[0]


class TestEnvLoader:
    """Tests for .env loader."""

    def test_mask_api_key_short(self):
        """Short keys are fully masked."""
        assert mask_api_key("abc") == "***"
        assert mask_api_key("") == "***"
        assert mask_api_key(None) == "***"

    def test_mask_api_key_long(self):
        """All keys are fully masked as '***' (v3.1 security fix)."""
        masked = mask_api_key("sk-1234567890-abcdef")
        assert masked == "***"
        # Ensure no key information is leaked
        assert "sk-" not in masked
        assert "1234567890" not in masked
        assert "abcdef" not in masked

    def test_load_dotenv_missing_file(self, tmp_path):
        """load_dotenv returns empty dict for missing file."""
        result = load_dotenv(dotenv_path=tmp_path / ".env.missing")
        assert result == {}

    def test_load_dotenv_loads_vars(self, tmp_path, monkeypatch):
        """load_dotenv loads variables from file into dict."""
        # Temporarily re-enable .env loading for this test
        monkeypatch.delenv("NOVEL_FACTORY_DISABLE_DOTENV", raising=False)
        
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\n")
        
        result = load_dotenv(dotenv_path=env_file)
        assert result == {"TEST_VAR": "test_value"}
        # Verify it does NOT pollute os.environ
        assert "TEST_VAR" not in os.environ

    def test_load_dotenv_respects_os_env_priority(self, tmp_path, monkeypatch):
        """OS environment variables have priority over .env via create_env_getter."""
        from novel_factory.config.env_loader import create_env_getter
        
        # Temporarily re-enable .env loading for this test
        monkeypatch.delenv("NOVEL_FACTORY_DISABLE_DOTENV", raising=False)
        
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_PRIORITY=from_file\n")
        
        # Set OS env first
        os.environ["TEST_PRIORITY"] = "from_os"
        
        # Load .env (non-polluting)
        dotenv_vars = load_dotenv(dotenv_path=env_file)
        assert dotenv_vars == {"TEST_PRIORITY": "from_file"}
        
        # Create env getter with priority
        env_getter = create_env_getter(dotenv_vars)
        
        # OS env should have priority
        assert env_getter("TEST_PRIORITY") == "from_os"
        
        # Cleanup
        del os.environ["TEST_PRIORITY"]
