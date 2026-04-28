"""v5.1.6 LangGraph Activation Tests.

Tests for:
1. LangGraph graph compilation
2. Node execution with create_node_runners
3. Routing logic equivalence
4. run_with_graph response shape
5. Settings validate endpoint
6. API key masking
7. Chinese error messages in LLMRouter
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


class TestLangGraphCompilation:
    """Test LangGraph graph compilation."""

    def test_compile_graph_returns_compiled_graph(self):
        """compile_graph() should return a compiled graph."""
        from novel_factory.workflow.graph import compile_graph
        from novel_factory.config.settings import load_settings
        from novel_factory.db.repository import Repository

        settings = load_settings()
        repo = Repository(settings.db_path)

        graph = compile_graph(settings=settings, repo=repo, checkpoint=False)

        # Compiled graph should have invoke method
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "stream")

    def test_compile_graph_with_checkpointer(self):
        """compile_graph() with checkpoint=True should include checkpointer."""
        from novel_factory.workflow.graph import compile_graph
        from novel_factory.config.settings import load_settings
        from novel_factory.db.repository import Repository

        settings = load_settings()
        repo = Repository(settings.db_path)

        graph = compile_graph(settings=settings, repo=repo, checkpoint=True)

        # Should still have invoke method
        assert hasattr(graph, "invoke")


class TestNodeRunners:
    """Test create_node_runners for LLMRouter-based injection."""

    def test_create_node_runners_in_stub_mode(self):
        """create_node_runners should create closures in stub mode."""
        from novel_factory.workflow.nodes import create_node_runners
        from novel_factory.config.settings import load_settings
        from novel_factory.db.repository import Repository
        from novel_factory.llm.router import LLMRouter
        from novel_factory.llm.stub_provider import StubLLM
        from novel_factory.llm.profiles import LLMProfilesConfig

        settings = load_settings()
        repo = Repository(settings.db_path)

        # Create stub router
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={},
            agent_llm={},
        )
        router = LLMRouter(config, stub_provider=StubLLM(), llm_mode="stub")

        runners = create_node_runners(settings, repo, router)

        # Should have all agent runners
        assert "planner" in runners
        assert "screenwriter" in runners
        assert "author" in runners
        assert "polisher" in runners
        assert "editor" in runners

        # Each runner should be callable
        assert callable(runners["planner"])
        assert callable(runners["author"])


class TestRoutingEquivalence:
    """Test that LangGraph routing matches expected behavior."""

    def test_route_by_chapter_status_matches_expected(self):
        """route_by_chapter_status should route to correct agents."""
        from novel_factory.workflow.conditions import route_by_chapter_status

        # Test all statuses
        test_cases = [
            ("idea", "planner"),
            ("outlined", "planner"),
            # v5.3.0: planned without instruction → planner; with instruction → screenwriter
            ("planned", "planner"),  # default: no instruction
            ("planned", "screenwriter", {"has_instruction": True}),  # has instruction
            ("scripted", "author"),
            ("drafted", "polisher"),
            ("polished", "editor"),
            ("review", "editor"),
            ("reviewed", "publisher"),
            ("published", "archive"),       # v5.1.6 fix: published → archive (terminal)
            ("blocking", "human_review"),
            ("revision", "author"),          # default revision target
        ]

        for test_case in test_cases:
            if len(test_case) == 3:
                status, expected_agent, extra_state = test_case
                state = {"chapter_status": status, **extra_state}
            else:
                status, expected_agent = test_case
                state = {"chapter_status": status}
            result = route_by_chapter_status(state)
            assert result == expected_agent, f"Status {status}: expected {expected_agent}, got {result}"


class TestRunWithGraph:
    """Test run_with_graph function."""

    def test_run_with_graph_returns_dispatcher_shape(self):
        """run_with_graph should return same shape as Dispatcher.run_chapter()."""
        from novel_factory.workflow.runner import run_with_graph
        from novel_factory.config.settings import load_settings
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            settings = load_settings()
            settings.db_path = db_path
            repo = Repository(db_path)

            # Create test project and chapter
            repo.create_project(
                project_id="test_project",
                name="Test Project",
                genre="玄幻",
                total_chapters_planned=10,
            )
            repo.add_chapter(
                project_id="test_project",
                chapter_number=1,
                title="第一章",
                status="planned",
            )

            result = run_with_graph(
                project_id="test_project",
                chapter_number=1,
                settings=settings,
                repo=repo,
                llm_mode="stub",
            )

            # Check shape matches Dispatcher.run_chapter()
            assert "run_id" in result
            assert "chapter_status" in result
            assert "steps" in result
            assert "error" in result
            assert "requires_human" in result

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_run_with_graph_published_short_circuits(self):
        """Published chapters should short-circuit without running the graph."""
        from novel_factory.workflow.runner import run_with_graph
        from novel_factory.config.settings import load_settings
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            settings = load_settings()
            settings.db_path = db_path
            repo = Repository(db_path)

            repo.create_project(
                project_id="test_pub",
                name="Test Published",
                genre="玄幻",
                total_chapters_planned=10,
            )
            repo.add_chapter(
                project_id="test_pub",
                chapter_number=1,
                title="第一章",
                status="published",
            )

            result = run_with_graph(
                project_id="test_pub",
                chapter_number=1,
                settings=settings,
                repo=repo,
                llm_mode="stub",
            )

            assert result["chapter_status"] == "published"
            assert result["error"] is None
            assert result["requires_human"] is False
            assert result["steps"] == []

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestSettingsValidateEndpoint:
    """Test POST /api/settings/validate endpoint."""

    def test_validate_missing_api_key(self):
        """Validate should return valid=False for missing API key."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            from novel_factory.db.connection import init_db
            from novel_factory.api_app import create_api_app

            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            resp = client.post("/api/settings/validate", json={
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4",
                "api_key_env": "NONEXISTENT_KEY_12345",
            })

            data = resp.json()
            assert data["ok"] is True
            assert data["data"]["valid"] is False
            assert data["data"]["error_code"] == "MISSING_API_KEY"

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_validate_placeholder_key(self):
        """Validate should detect placeholder API keys."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            from novel_factory.db.connection import init_db
            from novel_factory.api_app import create_api_app

            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            # Set placeholder key
            os.environ["TEST_PLACEHOLDER_KEY"] = "sk-placeholder-12345"

            resp = client.post("/api/settings/validate", json={
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4",
                "api_key_env": "TEST_PLACEHOLDER_KEY",
            })

            data = resp.json()
            assert data["ok"] is True
            assert data["data"]["valid"] is False
            assert data["data"]["error_code"] == "PLACEHOLDER_API_KEY"

        finally:
            del os.environ["TEST_PLACEHOLDER_KEY"]
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_validate_reads_dotenv_api_key(self, tmp_path, monkeypatch):
        """Validate should read API keys from .env, same as CLI/workflow."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        db_path = tmp_path / "settings_validate_dotenv.db"
        init_db(db_path)
        app = create_api_app(db_path=str(db_path), llm_mode="stub")
        client = TestClient(app)

        monkeypatch.delenv("TEST_DOTENV_API_KEY", raising=False)
        monkeypatch.delenv("NOVEL_FACTORY_DISABLE_DOTENV", raising=False)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'dotenv-test'\n", encoding="utf-8")
        (tmp_path / ".env").write_text(
            "TEST_DOTENV_API_KEY=sk-placeholder-from-dotenv\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        resp = client.post("/api/settings/validate", json={
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4",
            "api_key_env": "TEST_DOTENV_API_KEY",
        })

        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["valid"] is False
        assert data["data"]["error_code"] == "PLACEHOLDER_API_KEY"
        assert data["data"]["details"]["has_key"] is True


class TestAPIKeyMasking:
    """Test API key masking in /api/settings response."""

    def test_settings_no_raw_api_key(self):
        """/api/settings should not return raw API keys."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            from novel_factory.db.connection import init_db
            from novel_factory.api_app import create_api_app

            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            resp = client.get("/api/settings")
            data = resp.json()

            assert data["ok"] is True

            # Check profiles don't have raw api_key
            for profile in data["data"]["llm_profiles"]:
                # Only has_key boolean, not actual key
                assert "has_key" in profile
                # No raw api_key field
                assert "api_key" not in profile or profile.get("api_key") is None

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestChineseErrorMessages:
    """Test LLMRouter returns Chinese error messages."""

    def test_missing_profile_chinese_error(self):
        """LLMRouter should return Chinese error for missing profile."""
        from novel_factory.llm.router import LLMRouter
        from novel_factory.llm.profiles import LLMProfilesConfig

        config = LLMProfilesConfig(
            default_llm="nonexistent",
            llm_profiles={},
        )

        router = LLMRouter(config, llm_mode="real")

        with pytest.raises(ValueError) as exc_info:
            router.for_agent("author")

        # Should contain Chinese characters
        error_msg = str(exc_info.value)
        has_chinese = any("一" <= char <= "鿿" for char in error_msg)
        assert has_chinese, f"Error message should be in Chinese: {error_msg}"

    def test_missing_api_key_chinese_error(self):
        """LLMRouter should return Chinese error for missing API key."""
        from novel_factory.llm.router import LLMRouter
        from novel_factory.llm.profiles import LLMProfilesConfig, LLMProfile

        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url="https://test.example.com/v1",
                    api_key_env="MISSING_KEY",
                    model="test-model",
                )
            },
        )

        def mock_getenv(name: str, default=None):
            return None

        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)

        with pytest.raises(ValueError) as exc_info:
            router.for_agent("author")

        error_msg = str(exc_info.value)
        assert "API Key 未配置" in error_msg

    def test_missing_base_url_chinese_error(self):
        """LLMRouter should return Chinese error for missing base_url."""
        from novel_factory.llm.router import LLMRouter
        from novel_factory.llm.profiles import LLMProfilesConfig, LLMProfile

        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider="openai_compatible",
                    base_url_env="MISSING_URL",
                    api_key="sk-test",
                    model="test-model",
                )
            },
        )

        def mock_getenv(name: str, default=None):
            return None

        router = LLMRouter(config, llm_mode="real", env_getter=mock_getenv)

        with pytest.raises(ValueError) as exc_info:
            router.for_agent("author")

        error_msg = str(exc_info.value)
        assert "API 地址未配置" in error_msg
