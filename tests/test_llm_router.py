"""Tests for LLM router (v3.1)."""

from __future__ import annotations

import pytest
from typing import Optional

from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
from novel_factory.llm.router import LLMRouter
from novel_factory.llm.provider import LLMProvider


class StubProvider(LLMProvider):
    """Stub LLM provider for testing."""

    def invoke_json(self, messages, schema=None, temperature=None):
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None):
        return ""


class TestLLMRouter:
    """Tests for LLMRouter."""

    def test_router_stub_mode_returns_stub_provider(self):
        """In stub mode, router returns stub provider for all agents."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        stub = StubProvider()
        router = LLMRouter(config, stub_provider=stub, llm_mode="stub")
        
        # All agents should get stub provider
        assert router.for_agent("author") is stub
        assert router.for_agent("editor") is stub
        assert router.for_agent("planner") is stub

    def test_router_stub_mode_requires_stub_provider(self):
        """Stub mode without stub provider raises error."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        router = LLMRouter(config, stub_provider=None, llm_mode="stub")
        
        with pytest.raises(ValueError, match="Stub provider not configured"):
            router.for_agent("author")

    def test_router_real_mode_routes_to_profile(self):
        """In real mode, router routes agent to its profile."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="gpt-4o-mini",
                ),
                "author": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="claude-3.7-sonnet",
                ),
            },
            agent_llm={"author": "author"},
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            if name == "TEST_API_KEY":
                return "sk-test-key"
            return default
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        # Author should get author profile
        author_llm = router.for_agent("author")
        assert author_llm is not None
        
        # Editor should get default profile
        editor_llm = router.for_agent("editor")
        assert editor_llm is not None
        
        # They should be different providers (different profiles)
        assert author_llm is not editor_llm

    def test_router_caches_providers(self):
        """Router caches providers for the same profile."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            if name == "TEST_API_KEY":
                return "sk-test-key"
            return default
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        # Multiple calls should return same cached provider
        llm1 = router.for_agent("author")
        llm2 = router.for_agent("editor")
        llm3 = router.for_agent("planner")
        
        assert llm1 is llm2
        assert llm2 is llm3

    def test_router_real_mode_missing_profile(self):
        """Real mode with missing profile raises error."""
        config = LLMProfilesConfig(
            default_llm="nonexistent",
            llm_profiles={},
        )
        
        router = LLMRouter(config, llm_mode="real")
        
        with pytest.raises(ValueError, match="profile.*not found"):
            router.for_agent("author")

    def test_router_real_mode_missing_api_key(self):
        """Real mode with missing API key raises error."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="MISSING_API_KEY",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            # MISSING_API_KEY returns None
            return None
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        with pytest.raises(ValueError, match="API key not configured"):
            router.for_agent("author")

    def test_router_real_mode_missing_base_url(self):
        """Real mode with missing base_url raises error."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="MISSING_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_API_KEY":
                return "sk-test-key"
            # MISSING_BASE_URL returns None
            return None
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        with pytest.raises(ValueError, match="base_url not configured"):
            router.for_agent("author")

    def test_router_unsupported_provider(self):
        """Router rejects unsupported providers."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="unsupported_provider",
                    base_url="https://test.example.com/v1",
                    api_key="sk-test-key",
                    model="test-model",
                ),
            },
        )
        
        router = LLMRouter(config, llm_mode="real")
        
        with pytest.raises(ValueError, match="Unsupported provider"):
            router.for_agent("author")

    def test_get_route_info(self):
        """get_route_info returns correct routing information."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="gpt-4o-mini",
                    temperature=0.7,
                    max_tokens=4096,
                ),
            },
            agent_llm={"author": "default"},
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            if name == "TEST_API_KEY":
                return "sk-test-key-12345"
            return default
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        info = router.get_route_info("author")
        
        assert info["agent"] == "author"
        assert info["profile"] == "default"
        assert info["provider"] == "openai_compatible"
        assert info["base_url"] == "https://test.example.com/v1"
        # API key should always be masked as "***"
        assert info["api_key"] == "***"
        assert "sk-test-key-12345" not in info["api_key"]
        assert info["model"] == "gpt-4o-mini"
        assert info["temperature"] == 0.7
        assert info["max_tokens"] == 4096

    def test_list_profiles(self):
        """list_profiles returns all profiles with masked keys."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="gpt-4o-mini",
                ),
                "author": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="claude-3.7-sonnet",
                ),
            },
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            if name == "TEST_API_KEY":
                return "sk-test-key-12345"
            return default
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        profiles = router.list_profiles()
        
        assert len(profiles) == 2
        assert "default" in profiles
        assert "author" in profiles
        # API keys should be masked (not the full keys)
        assert "sk-test-key-12345" not in profiles["default"]["api_key"]
        assert "sk-test-key-12345" not in profiles["author"]["api_key"]
        assert "..." in profiles["default"]["api_key"] or profiles["default"]["api_key"] == "***"
        assert "..." in profiles["author"]["api_key"] or profiles["author"]["api_key"] == "***"

    def test_validate_no_issues(self):
        """validate returns no issues for valid config."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            if name == "TEST_API_KEY":
                return "sk-test-key"
            return default
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        result = router.validate()
        
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_validate_missing_env_vars(self):
        """validate detects missing environment variables."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="MISSING_BASE_URL",
                    api_key_env="MISSING_API_KEY",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            # All env vars return None
            return None
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        result = router.validate()
        
        assert len(result["errors"]) == 2
        assert any("MISSING_BASE_URL" in e for e in result["errors"])
        assert any("MISSING_API_KEY" in e for e in result["errors"])

    def test_validate_unused_profiles(self):
        """validate warns about unused profiles."""
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="gpt-4o-mini",
                ),
                "unused": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="TEST_BASE_URL",
                    api_key_env="TEST_API_KEY",
                    model="unused-model",
                ),
            },
            agent_llm={},
        )
        
        def mock_getenv(name: str, default: Optional[str] = None) -> Optional[str]:
            if name == "TEST_BASE_URL":
                return "https://test.example.com/v1"
            if name == "TEST_API_KEY":
                return "sk-test-key"
            return default
        
        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)
        
        result = router.validate()
        
        assert result["errors"] == []
        assert len(result["warnings"]) == 1
        assert "unused" in result["warnings"][0]
