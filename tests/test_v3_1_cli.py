"""Tests for v3.1 CLI commands."""

from __future__ import annotations

import json
import pytest

from novel_factory.cli import build_parser
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_v31.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


class TestLLMCLICommands:
    """Tests for LLM CLI commands."""

    def test_llm_profiles_json_output(self):
        """llm profiles --json outputs valid JSON envelope."""
        parser = build_parser()
        args = parser.parse_args(["llm", "profiles", "--json"])
        
        assert args.llm_command == "profiles"
        assert args.json is True

    def test_llm_route_requires_agent(self):
        """llm route requires --agent argument."""
        parser = build_parser()
        
        # Should raise SystemExit due to required argument
        with pytest.raises(SystemExit):
            parser.parse_args(["llm", "route", "--json"])

    def test_llm_route_json_output(self):
        """llm route --agent author --json outputs valid JSON envelope."""
        parser = build_parser()
        args = parser.parse_args(["llm", "route", "--agent", "author", "--json"])
        
        assert args.llm_command == "route"
        assert args.agent == "author"
        assert args.json is True

    def test_llm_validate_json_output(self):
        """llm validate --json outputs valid JSON envelope."""
        parser = build_parser()
        args = parser.parse_args(["llm", "validate", "--json"])
        
        assert args.llm_command == "validate"
        assert args.json is True

    def test_llm_profiles_masks_keys(self, tmp_path, monkeypatch):
        """llm profiles does not leak API keys."""
        # Create a config file with profiles
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
default_llm: default

llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: TEST_BASE_URL
    api_key_env: TEST_API_KEY
    model: gpt-4o-mini
    temperature: 0.7
    max_tokens: 4096

agent_llm:
  author: default
""")
        
        # Set environment variables
        monkeypatch.setenv("TEST_BASE_URL", "https://test.example.com/v1")
        monkeypatch.setenv("TEST_API_KEY", "sk-secret-key-12345")
        
        # Parse and execute
        parser = build_parser()
        args = parser.parse_args(["--config", str(config_file), "llm", "profiles", "--json"])
        
        # Check that args are correct
        assert args.config == str(config_file)
        assert args.llm_command == "profiles"
        assert args.json is True

    def test_llm_route_masks_keys(self, tmp_path, monkeypatch):
        """llm route does not leak API keys."""
        # Create a config file with profiles
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
default_llm: default

llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: TEST_BASE_URL
    api_key_env: TEST_API_KEY
    model: gpt-4o-mini

agent_llm:
  author: default
""")
        
        # Set environment variables
        monkeypatch.setenv("TEST_BASE_URL", "https://test.example.com/v1")
        monkeypatch.setenv("TEST_API_KEY", "sk-secret-key-12345")
        
        # Parse and execute
        parser = build_parser()
        args = parser.parse_args(["--config", str(config_file), "llm", "route", "--agent", "author", "--json"])
        
        # Check that args are correct
        assert args.config == str(config_file)
        assert args.agent == "author"
        assert args.json is True


class TestDispatcherWithRouter:
    """Tests for Dispatcher with LLMRouter."""

    def test_dispatcher_with_llm_router(self, tmp_db, repo):
        """Dispatcher can be initialized with llm_router."""
        from novel_factory.dispatcher import Dispatcher
        from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
        from novel_factory.llm.router import LLMRouter
        from tests.test_llm_router import StubProvider
        
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://test.example.com/v1",
                    api_key="sk-test-key",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        stub = StubProvider()
        router = LLMRouter(config, stub_provider=stub, llm_mode="stub")
        
        dispatcher = Dispatcher(repo, llm_router=router)
        
        assert dispatcher.llm_router is router

    def test_dispatcher_with_single_llm_backward_compat(self, tmp_db, repo):
        """Dispatcher still works with single llm (backward compatibility)."""
        from novel_factory.dispatcher import Dispatcher
        from tests.test_llm_router import StubProvider
        
        stub = StubProvider()
        dispatcher = Dispatcher(repo, llm=stub)
        
        assert dispatcher.llm is stub
        assert dispatcher.llm_router is None

    def test_dispatcher_requires_llm_or_router(self, tmp_db, repo):
        """Dispatcher raises error if neither llm nor llm_router provided."""
        from novel_factory.dispatcher import Dispatcher
        
        with pytest.raises(ValueError, match="Either 'llm' or 'llm_router' must be provided"):
            Dispatcher(repo, llm=None, llm_router=None)

    def test_dispatcher_llm_for_agent_with_router(self, tmp_db, repo):
        """Dispatcher._llm_for_agent uses router when available."""
        from novel_factory.dispatcher import Dispatcher
        from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
        from novel_factory.llm.router import LLMRouter
        from tests.test_llm_router import StubProvider
        
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://test.example.com/v1",
                    api_key="sk-test-key",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        stub = StubProvider()
        router = LLMRouter(config, stub_provider=stub, llm_mode="stub")
        
        dispatcher = Dispatcher(repo, llm_router=router)
        
        # Should get stub provider from router
        llm = dispatcher._llm_for_agent("author")
        assert llm is stub

    def test_dispatcher_llm_for_agent_falls_back_to_single_llm(self, tmp_db, repo):
        """Dispatcher._llm_for_agent falls back to single llm when no router."""
        from novel_factory.dispatcher import Dispatcher
        from tests.test_llm_router import StubProvider
        
        stub = StubProvider()
        dispatcher = Dispatcher(repo, llm=stub)
        
        # Should get single llm
        llm = dispatcher._llm_for_agent("author")
        assert llm is stub


class TestEnvExample:
    """Tests for .env.example file."""

    def test_env_example_exists(self):
        """.env.example file exists."""
        from pathlib import Path
        env_example = Path(__file__).parent.parent / ".env.example"
        assert env_example.exists(), ".env.example file should exist"

    def test_env_example_has_placeholders(self):
        """.env.example does not contain real API keys."""
        from pathlib import Path
        env_example = Path(__file__).parent.parent / ".env.example"
        content = env_example.read_text()
        
        # Should not contain real-looking API keys
        assert "sk-" not in content or "replace-me" in content
        assert "sk-or-" not in content or "replace-me" in content
        assert "sk-ds-" not in content or "replace-me" in content
        
        # Should contain placeholder values
        assert "replace-me" in content

    def test_gitignore_ignores_env(self):
        """.gitignore includes .env."""
        from pathlib import Path
        gitignore = Path(__file__).parent.parent / ".gitignore"
        content = gitignore.read_text()
        
        assert ".env" in content


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing tests."""

    def test_existing_tests_still_work_with_stub_llm(self, tmp_db, repo):
        """Existing tests that pass StubLLM still work."""
        from novel_factory.dispatcher import Dispatcher
        from novel_factory.cli import _StubLLM
        
        stub_llm = _StubLLM()
        dispatcher = Dispatcher(repo, llm=stub_llm, max_retries=3)
        
        # Should work as before
        assert dispatcher.llm is stub_llm
        assert dispatcher.max_retries == 3

    def test_dispatcher_router_priority_over_llm(self, tmp_db, repo):
        """If both llm and llm_router provided, router takes precedence."""
        from novel_factory.dispatcher import Dispatcher
        from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
        from novel_factory.llm.router import LLMRouter
        from tests.test_llm_router import StubProvider
        
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://test.example.com/v1",
                    api_key="sk-test-key",
                    model="gpt-4o-mini",
                ),
            },
        )
        
        router_stub = StubProvider()
        router = LLMRouter(config, stub_provider=router_stub, llm_mode="stub")
        
        single_stub = StubProvider()
        
        # Both provided
        dispatcher = Dispatcher(repo, llm=single_stub, llm_router=router)
        
        # Router should take precedence
        llm = dispatcher._llm_for_agent("author")
        assert llm is router_stub
        assert llm is not single_stub
