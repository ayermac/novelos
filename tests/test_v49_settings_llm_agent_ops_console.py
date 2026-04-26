"""Tests for v4.9 Settings / LLM / Agent Ops Console.

Tests the settings page and configuration display.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_factory.db.connection import init_db
from novel_factory.web.app import create_app


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Initialize database
    init_db(db_path)
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client(temp_db):
    """Create a test client."""
    app = create_app(db_path=temp_db, config_path=None, llm_mode="stub")
    return TestClient(app)


class TestSettingsPage:
    """Test the settings web page."""

    def test_settings_page_returns_200(self, client):
        """GET /settings returns 200."""
        response = client.get("/settings")
        assert response.status_code == 200

    def test_settings_page_has_title(self, client):
        """Page has Settings title."""
        response = client.get("/settings")
        assert "Settings" in response.text
        assert "LLM" in response.text or "Agent Ops" in response.text

    def test_settings_page_has_runtime_mode(self, client):
        """Page shows runtime mode."""
        response = client.get("/settings")
        
        # Should show LLM mode
        assert "LLM Mode" in response.text or "llm_mode" in response.text.lower()
        assert "stub" in response.text.lower() or "real" in response.text.lower()

    def test_settings_page_has_llm_profiles_section(self, client):
        """Page has LLM profiles section."""
        response = client.get("/settings")
        
        # Should have LLM profiles heading
        assert "LLM Profiles" in response.text

    def test_settings_page_has_agent_routing_section(self, client):
        """Page has agent routing section."""
        response = client.get("/settings")
        
        # Should have agent routing heading
        assert "Agent Routing" in response.text or "agent" in response.text.lower()

    def test_settings_page_has_recommendations_section(self, client):
        """Page has model recommendations section."""
        response = client.get("/settings")
        
        # Should have recommendations heading
        assert "Recommendation" in response.text or "catalog" in response.text.lower()

    def test_settings_page_has_diagnostics_section(self, client):
        """Page has diagnostics section."""
        response = client.get("/settings")
        
        # Should have diagnostics heading
        assert "Diagnostic" in response.text

    def test_settings_page_no_traceback(self, client):
        """Page does not contain traceback."""
        response = client.get("/settings")
        
        # Should not have Python traceback
        assert "Traceback" not in response.text
        assert "File " not in response.text or "File \"" not in response.text

    def test_settings_page_no_api_key(self, client):
        """Page does not contain API key or secret."""
        response = client.get("/settings")
        
        # Should not have API key patterns
        assert "sk-" not in response.text
        # Should not show actual keys
        assert "api_key" not in response.text.lower() or "API Key Env" in response.text

    def test_settings_page_no_raw_json(self, client):
        """Page does not show raw JSON."""
        response = client.get("/settings")
        
        # Should not have raw JSON dumps
        assert '{"llm_profiles"' not in response.text
        assert '["profiles"]' not in response.text

    def test_settings_page_has_status_badges(self, client):
        """Page has status badges for profiles."""
        response = client.get("/settings")
        
        # Should have status badges
        assert "status-badge" in response.text or "status-" in response.text


class TestSettingsData:
    """Test the settings data structure."""

    def test_llm_profiles_display(self, client):
        """LLM profiles are displayed correctly."""
        response = client.get("/settings")
        
        # Should show profile table or empty state
        assert "LLM Profiles" in response.text

    def test_agent_routing_display(self, client):
        """Agent routing is displayed correctly."""
        response = client.get("/settings")
        
        # Should show agent routing table
        assert "Agent Routing" in response.text

    def test_recommendations_display(self, client):
        """Model recommendations are displayed correctly."""
        response = client.get("/settings")
        
        # Should show catalog status
        assert "Catalog Status" in response.text or "catalog" in response.text.lower()

    def test_diagnostics_display(self, client):
        """Diagnostics are displayed correctly."""
        response = client.get("/settings")
        
        # Should show diagnostics section
        assert "Diagnostic" in response.text


class TestSettingsNavigation:
    """Test navigation to settings page."""

    def test_settings_link_in_nav(self, client):
        """Settings link appears in navigation."""
        response = client.get("/")
        
        assert "/settings" in response.text


class TestSettingsSafety:
    """Test safety requirements for settings page."""

    def test_no_database_writes(self, client, temp_db):
        """Settings page does not write to database."""
        from novel_factory.db.repository import Repository
        
        # Get initial state
        repo = Repository(temp_db)
        projects_before = repo.list_projects()
        
        # Access settings page
        client.get("/settings")
        
        # Verify no changes
        projects_after = repo.list_projects()
        assert len(projects_after) == len(projects_before)

    def test_no_production_logic(self, client, temp_db):
        """Settings page does not trigger production."""
        from novel_factory.db.repository import Repository
        
        repo = Repository(temp_db)
        
        # Access settings page
        client.get("/settings")
        
        # Verify no production runs created
        projects = repo.list_projects()
        for project in projects:
            runs = repo.get_workflow_runs_for_project(project["project_id"])
            assert len(runs) == 0

    def test_no_env_modification(self, client):
        """Settings page does not modify environment."""
        import os
        
        # Get initial env state
        initial_keys = set(os.environ.keys())
        
        # Access settings page
        client.get("/settings")
        
        # Verify no new env vars
        final_keys = set(os.environ.keys())
        assert final_keys == initial_keys


class TestSettingsEmptyStates:
    """Test empty states for settings page."""

    def test_empty_profiles_shows_message(self, client):
        """Empty profiles shows appropriate message."""
        response = client.get("/settings")
        
        # Should show empty state or table
        assert "LLM Profiles" in response.text

    def test_empty_recommendations_shows_message(self, client):
        """Empty recommendations shows appropriate message."""
        response = client.get("/settings")
        
        # Should show catalog status
        assert "Catalog Status" in response.text or "catalog" in response.text.lower()

    def test_empty_skills_shows_message(self, client):
        """Empty skills shows appropriate message."""
        response = client.get("/settings")
        
        # Should show skill status
        assert "Skill" in response.text or "QualityHub" in response.text


class TestSettingsBadConfig:
    """Test bad configuration diagnostics."""

    def test_missing_default_llm_shows_error(self, temp_db):
        """Missing default_llm profile shows error in diagnostics."""
        from novel_factory.config.settings import Settings
        from novel_factory.llm.profiles import LLMProfile
        
        # Create settings with missing default_llm
        settings = Settings(
            llm_profiles={
                "author": LLMProfile(
                    provider="openai_compatible",
                    model="gpt-4",
                    api_key_env="OPENAI_API_KEY",
                    base_url_env="OPENAI_BASE_URL",
                )
            },
            default_llm="nonexistent",  # This profile doesn't exist
            agent_llm={}
        )
        
        # Build diagnostics
        from novel_factory.web.routes.settings import _build_diagnostics_data
        diagnostics = _build_diagnostics_data(settings, llm_mode="real")
        
        # Should have error about missing default_llm
        assert any("Default LLM profile 'nonexistent' does not exist" in e for e in diagnostics["errors"])

    def test_missing_agent_llm_profile_shows_error(self, temp_db):
        """Agent referencing non-existent profile shows error in diagnostics."""
        from novel_factory.config.settings import Settings
        from novel_factory.llm.profiles import LLMProfile
        
        # Create settings with missing agent_llm profile
        settings = Settings(
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    model="gpt-4",
                    api_key_env="OPENAI_API_KEY",
                    base_url_env="OPENAI_BASE_URL",
                )
            },
            default_llm="default",
            agent_llm={"author": "missing_profile"}  # This profile doesn't exist
        )
        
        # Build diagnostics
        from novel_factory.web.routes.settings import _build_diagnostics_data
        diagnostics = _build_diagnostics_data(settings, llm_mode="real")
        
        # Should have error about missing profile
        assert any("Agent 'author' references non-existent profile 'missing_profile'" in e for e in diagnostics["errors"])

    def test_missing_env_var_shows_error_in_real_mode(self, temp_db):
        """Missing env var shows error in real mode."""
        from novel_factory.config.settings import Settings
        from novel_factory.llm.profiles import LLMProfile
        
        # Create settings with env var that doesn't exist
        settings = Settings(
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    model="gpt-4",
                    api_key_env="NONEXISTENT_API_KEY",  # This env var doesn't exist
                    base_url_env="NONEXISTENT_BASE_URL",  # This env var doesn't exist
                )
            },
            default_llm="default",
            agent_llm={}
        )
        
        # Build diagnostics with mock env_getter that returns None
        def mock_env_getter(key, default=None):
            return None
        
        from novel_factory.web.routes.settings import _build_diagnostics_data
        diagnostics = _build_diagnostics_data(settings, llm_mode="real", env_getter=mock_env_getter)
        
        # Should have error about missing API key and base URL
        assert any("no API key configured" in e for e in diagnostics["errors"])
        assert any("no base URL configured" in e for e in diagnostics["errors"])

    def test_missing_env_var_shows_warning_in_stub_mode(self, temp_db):
        """Missing env var shows warning in stub mode."""
        from novel_factory.config.settings import Settings
        from novel_factory.llm.profiles import LLMProfile
        
        # Create settings with env var that doesn't exist
        settings = Settings(
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    model="gpt-4",
                    api_key_env="NONEXISTENT_API_KEY",  # This env var doesn't exist
                    base_url_env="NONEXISTENT_BASE_URL",  # This env var doesn't exist
                )
            },
            default_llm="default",
            agent_llm={}
        )
        
        # Build diagnostics with mock env_getter that returns None
        def mock_env_getter(key, default=None):
            return None
        
        from novel_factory.web.routes.settings import _build_diagnostics_data
        diagnostics = _build_diagnostics_data(settings, llm_mode="stub", env_getter=mock_env_getter)
        
        # Should have warnings (not errors) about missing env vars
        assert any("no API key configured" in w for w in diagnostics["warnings"])
        assert any("no base URL configured" in w for w in diagnostics["warnings"])

    def test_configured_env_var_not_leaked(self, temp_db):
        """Configured env var value is not leaked in page."""
        from novel_factory.config.settings import Settings
        from novel_factory.llm.profiles import LLMProfile
        
        # Create settings with real env var
        settings = Settings(
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    model="gpt-4",
                    api_key_env="TEST_API_KEY",
                    base_url_env="TEST_BASE_URL",
                )
            },
            default_llm="default",
            agent_llm={}
        )
        
        # Build profiles with mock env_getter that returns fake values
        def mock_env_getter(key, default=None):
            if key == "TEST_API_KEY":
                return "sk-test-secret-key-12345"
            if key == "TEST_BASE_URL":
                return "https://api.example.com"
            return None
        
        from novel_factory.web.routes.settings import _build_llm_profiles_data
        profiles_data = _build_llm_profiles_data(settings, llm_mode="real", env_getter=mock_env_getter)
        
        # Should show env var names but not values
        profile = profiles_data["profiles"][0]
        assert profile["api_key_env"] == "TEST_API_KEY"
        assert profile["base_url_env"] == "TEST_BASE_URL"
        assert profile["api_key_status"] == "configured"
        assert profile["base_url_status"] == "configured"
        
        # Should NOT contain actual values
        assert "sk-test-secret-key-12345" not in str(profile)
        assert "https://api.example.com" not in str(profile)

    def test_direct_api_key_not_leaked(self, temp_db):
        """Direct API key value is not leaked in page."""
        from novel_factory.config.settings import Settings
        from novel_factory.llm.profiles import LLMProfile
        
        # Create settings with direct API key (not recommended but supported)
        settings = Settings(
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    model="gpt-4",
                    api_key="sk-direct-secret-key-67890",  # Direct key
                    base_url="https://direct.api.example.com",  # Direct URL
                )
            },
            default_llm="default",
            agent_llm={}
        )
        
        from novel_factory.web.routes.settings import _build_llm_profiles_data
        profiles_data = _build_llm_profiles_data(settings, llm_mode="real")
        
        # Should show status as direct but not the actual values
        profile = profiles_data["profiles"][0]
        assert profile["api_key_status"] == "direct"
        assert profile["base_url_status"] == "direct"
        assert profile["status"] == "complete"
        
        # Should NOT contain actual values
        assert "sk-direct-secret-key-67890" not in str(profile)
        assert "https://direct.api.example.com" not in str(profile)

    def test_agent_routing_shows_invalid_profile(self, temp_db):
        """Agent routing shows invalid profile status."""
        from novel_factory.config.settings import Settings
        from novel_factory.llm.profiles import LLMProfile
        
        # Create settings with missing agent_llm profile
        settings = Settings(
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    model="gpt-4",
                    api_key_env="OPENAI_API_KEY",
                    base_url_env="OPENAI_BASE_URL",
                )
            },
            default_llm="default",
            agent_llm={"author": "missing_profile"}  # This profile doesn't exist
        )
        
        from novel_factory.web.routes.settings import _build_llm_profiles_data, _build_agent_routing_data
        
        # Build profiles
        llm_data = _build_llm_profiles_data(settings, llm_mode="real")
        profiles_dict = {p["name"]: p for p in llm_data["profiles"]}
        
        # Build routing
        routing_data = _build_agent_routing_data(settings, profiles_dict, llm_mode="real")
        
        # Should show author route as missing
        author_route = next(r for r in routing_data["agent_routes"] if r["agent"] == "author")
        assert author_route["route"] == "missing_profile"
        assert author_route["profile_status"] == "missing"
