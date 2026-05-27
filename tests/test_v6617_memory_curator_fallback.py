"""Tests for v6.6.17 Memory Curator LLM Fallback Model.

Ensures:
- Primary timeout -> fallback model success
- Primary timeout + fallback timeout -> state_card fallback
- Primary timeout + fallback timeout + empty state_card -> degraded_noop (non-blocking)
- Backward compatibility when agent_llm_fallback is not configured
- Clear error when fallback profile does not exist
- Provider layer does NOT retry LLMTimeoutError
- Desktop config supports agent_llm_fallback
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from novel_factory.llm.openai_compatible import LLMConnectionError, LLMTimeoutError, OutputValidationError
from novel_factory.llm.provider import LLMProvider


class TimeoutThenFallbackProvider(LLMProvider):
    """Provider that raises LLMTimeoutError on every call."""

    def __init__(self, model_name: str = "timeout-model"):
        self.model_name = model_name
        self.call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None):
        self.call_count += 1
        raise LLMTimeoutError(f"LLM 响应超时（>{self.model_name}）")

    def invoke_text(self, messages, temperature=None, max_tokens=None, max_retries=None, request_timeout_seconds=None):
        self.call_count += 1
        raise LLMTimeoutError(f"LLM 响应超时（>{self.model_name}）")


class ConnectionFailureProvider(LLMProvider):
    """Provider that raises LLMConnectionError on every call."""

    def __init__(self):
        self.call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None):
        self.call_count += 1
        raise LLMConnectionError("LLM 网络连接失败，请稍后重试: Connection error.")

    def invoke_text(self, messages, temperature=None, max_tokens=None, max_retries=None, request_timeout_seconds=None):
        self.call_count += 1
        raise LLMConnectionError("LLM 网络连接失败，请稍后重试: Connection error.")


class SuccessProvider(LLMProvider):
    """Provider that returns successful patches."""

    def __init__(self, patches: list[dict[str, Any]] | None = None):
        self.patches = patches or [
            {
                "target_table": "story_facts",
                "operation": "create",
                "target_name": "test_fact",
                "data": {"fact_key": "test_fact", "fact_type": "narrative_event"},
                "confidence": 0.85,
                "evidence_text": "test evidence",
                "rationale": "test",
            }
        ]
        self.call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None):
        self.call_count += 1
        return {"patches": self.patches}

    def invoke_text(self, messages, temperature=None, max_tokens=None, max_retries=None, request_timeout_seconds=None):
        self.call_count += 1
        return "ok"


class EmptyProvider(LLMProvider):
    """Provider that returns empty patches."""

    def __init__(self):
        self.call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None):
        self.call_count += 1
        return {"patches": []}

    def invoke_text(self, messages, temperature=None, max_tokens=None, max_retries=None, request_timeout_seconds=None):
        self.call_count += 1
        return "ok"


# ── Unit Tests for MemoryCuratorAgent fallback logic ──────────────────


def test_memory_curator_primary_timeout_fallback_success():
    """Primary LLMTimeoutError -> fallback provider succeeds."""
    from novel_factory.agents.memory_curator import MemoryCuratorAgent
    from novel_factory.db.repository import Repository

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from novel_factory.db.connection import init_db
    init_db(db_path)

    repo = Repository(db_path)
    repo.create_project(project_id="test-fb", name="Test", genre="test")
    repo.add_chapter("test-fb", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("test-fb", 1, "some content here for testing")

    primary = TimeoutThenFallbackProvider("primary")
    fallback = SuccessProvider()

    agent = MemoryCuratorAgent(repo, primary, fallback_llm=fallback)
    result = agent.run({
        "project_id": "test-fb",
        "chapter_number": 1,
        "chapter_status": "reviewed",
        "workflow_run_id": "run-1",
        "llm_mode": "real",
    })

    assert primary.call_count >= 1
    assert fallback.call_count == 1
    assert result.get("memory_curator_processed") is True
    assert result.get("fallback_model_used") is True
    assert result.get("fallback_model_profile") == "unknown"
    assert result.get("extraction_success") is True
    assert result.get("fallback_created") is False
    assert result.get("memory_curator_fallback") is None
    assert result.get("memory_batch_id") is not None
    assert result.get("memory_items_count", 0) > 0
    from novel_factory.api.routes._memory_curator_gate import has_trusted_memory_batch
    assert has_trusted_memory_batch(repo, "test-fb", 1) is True

    os.unlink(db_path)


def test_memory_curator_primary_and_fallback_timeout_state_card_fallback():
    """Primary timeout + fallback timeout -> state_card fallback."""
    from novel_factory.agents.memory_curator import MemoryCuratorAgent
    from novel_factory.db.repository import Repository

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from novel_factory.db.connection import init_db
    init_db(db_path)

    repo = Repository(db_path)
    repo.create_project(project_id="test-fb2", name="Test", genre="test")
    repo.add_chapter("test-fb2", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("test-fb2", 1, "some content here for testing")

    # Create a state card with new_facts so state_card fallback produces patches
    repo.save_chapter_state("test-fb2", 1, state_data={
        "new_facts": ["fact one", "fact two"],
    })

    primary = TimeoutThenFallbackProvider("primary")
    fallback = TimeoutThenFallbackProvider("fallback")

    agent = MemoryCuratorAgent(repo, primary, fallback_llm=fallback)
    result = agent.run({
        "project_id": "test-fb2",
        "chapter_number": 1,
        "chapter_status": "reviewed",
        "workflow_run_id": "run-1",
        "llm_mode": "real",
    })

    assert primary.call_count >= 1
    assert fallback.call_count == 1
    assert result.get("memory_curator_processed") is True
    assert result.get("fallback_source") is not None
    assert "chapter_state" in result.get("fallback_source")
    assert result.get("memory_batch_id") is not None
    assert result.get("memory_items_count", 0) > 0

    os.unlink(db_path)


def test_memory_curator_connection_error_uses_state_card_fallback():
    """Primary LLMConnectionError should use state_card fallback instead of failing the node."""
    from novel_factory.agents.memory_curator import MemoryCuratorAgent
    from novel_factory.db.repository import Repository

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from novel_factory.db.connection import init_db
    init_db(db_path)

    repo = Repository(db_path)
    repo.create_project(project_id="test-conn-fb", name="Test", genre="test")
    repo.add_chapter("test-conn-fb", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("test-conn-fb", 1, "some content here for testing")
    repo.save_chapter_state("test-conn-fb", 1, state_data={
        "new_facts": ["connection fallback fact"],
    })

    primary = ConnectionFailureProvider()

    agent = MemoryCuratorAgent(repo, primary, fallback_llm=None)
    result = agent.run({
        "project_id": "test-conn-fb",
        "chapter_number": 1,
        "chapter_status": "reviewed",
        "workflow_run_id": "run-1",
        "llm_mode": "real",
    })

    assert primary.call_count >= 1
    assert result.get("memory_curator_processed") is True
    assert result.get("fallback_source") is not None
    assert "chapter_state" in result.get("fallback_source")
    assert result.get("memory_batch_id") is not None
    assert result.get("memory_items_count", 0) > 0
    assert "error" not in result

    os.unlink(db_path)


def test_memory_curator_degraded_noop_no_block():
    """Primary timeout + fallback timeout + empty state_card -> degraded_noop, non-blocking."""
    from novel_factory.agents.memory_curator import MemoryCuratorAgent
    from novel_factory.db.repository import Repository

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from novel_factory.db.connection import init_db
    init_db(db_path)

    repo = Repository(db_path)
    repo.create_project(project_id="test-fb3", name="Test", genre="test")
    repo.add_chapter("test-fb3", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("test-fb3", 1, "short")

    primary = TimeoutThenFallbackProvider("primary")
    fallback = TimeoutThenFallbackProvider("fallback")

    agent = MemoryCuratorAgent(repo, primary, fallback_llm=fallback)
    result = agent.run({
        "project_id": "test-fb3",
        "chapter_number": 1,
        "chapter_status": "reviewed",
        "workflow_run_id": "run-1",
        "llm_mode": "real",
    })

    assert result.get("memory_curator_processed") is True
    assert result.get("fallback_source") == "none"
    assert result.get("memory_curator_degraded") is True
    assert result.get("partial_success") is False
    assert result.get("memory_items_count", -1) == 0
    assert "error" not in result  # must NOT block

    os.unlink(db_path)


def test_memory_curator_no_fallback_config_backward_compatible():
    """Without fallback_llm, behavior is identical to pre-v6.6.17."""
    from novel_factory.agents.memory_curator import MemoryCuratorAgent
    from novel_factory.db.repository import Repository

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from novel_factory.db.connection import init_db
    init_db(db_path)

    repo = Repository(db_path)
    repo.create_project(project_id="test-compat", name="Test", genre="test")
    repo.add_chapter("test-compat", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("test-compat", 1, "some content")

    primary = TimeoutThenFallbackProvider("primary")

    agent = MemoryCuratorAgent(repo, primary, fallback_llm=None)
    result = agent.run({
        "project_id": "test-compat",
        "chapter_number": 1,
        "chapter_status": "reviewed",
        "workflow_run_id": "run-1",
        "llm_mode": "real",
    })

    # Without fallback, it should eventually degrade to state_card or noop
    assert result.get("memory_curator_processed") is True
    assert "error" not in result

    os.unlink(db_path)


# ── LLMRouter Tests ───────────────────────────────────────────────────


def test_router_fallback_profile_not_found():
    """Configured fallback profile that does not exist raises clear error."""
    from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
    from novel_factory.llm.router import LLMRouter

    config = LLMProfilesConfig(
        default_llm="default",
        llm_profiles={
            "default": LLMProfile(
                provider="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            ),
        },
        agent_llm_fallback={"memory_curator": "nonexistent"},
    )

    router = LLMRouter(config, llm_mode="real")

    with pytest.raises(ValueError, match="Agent 'memory_curator' 的 fallback LLM 档案不存在: nonexistent"):
        router.for_agent_fallback("memory_curator")


def test_router_fallback_returns_none_when_not_configured():
    """No fallback config -> for_agent_fallback returns None."""
    from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
    from novel_factory.llm.router import LLMRouter

    config = LLMProfilesConfig(
        default_llm="default",
        llm_profiles={
            "default": LLMProfile(
                provider="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            ),
        },
    )

    router = LLMRouter(config, llm_mode="real")
    assert router.for_agent_fallback("memory_curator") is None


def test_router_fallback_caching():
    """Fallback provider is cached separately from primary."""
    from novel_factory.llm.profiles import LLMProfile, LLMProfilesConfig
    from novel_factory.llm.router import LLMRouter

    config = LLMProfilesConfig(
        default_llm="default",
        llm_profiles={
            "default": LLMProfile(
                provider="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            ),
            "fast": LLMProfile(
                provider="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            ),
        },
        agent_llm_fallback={"memory_curator": "fast"},
    )

    router = LLMRouter(config, llm_mode="real")
    primary = router.for_agent("memory_curator")
    fallback = router.for_agent_fallback("memory_curator")

    assert primary is not fallback
    # Second call returns cached instance
    assert router.for_agent("memory_curator") is primary
    assert router.for_agent_fallback("memory_curator") is fallback


def test_workflow_router_wires_agent_llm_fallback():
    """Production workflow router receives Settings.agent_llm_fallback."""
    from novel_factory.config.settings import Settings
    from novel_factory.llm.profiles import LLMProfile
    from novel_factory.workflow.runner import _build_llm_router

    settings = Settings(
        default_llm="default",
        llm_profiles={
            "default": LLMProfile(
                provider="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o",
            ),
            "fast": LLMProfile(
                provider="openai_compatible",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
                request_timeout_seconds=90,
            ),
        },
        agent_llm={"memory_curator": "default"},
        agent_llm_fallback={"memory_curator": "fast"},
    )

    router = _build_llm_router(settings, "real")
    fallback = router.for_agent_fallback("memory_curator")

    assert fallback is not None
    assert getattr(fallback.config, "model", "") == "gpt-4o-mini"
    assert getattr(fallback.config, "request_timeout_seconds", None) == 90

    route_info = router.get_fallback_route_info("memory_curator")
    assert route_info is not None
    assert route_info["request_timeout_seconds"] == 90


# ── Provider Layer Tests ──────────────────────────────────────────────


def test_provider_retry_does_not_include_llm_timeout():
    """OpenAICompatibleProvider does not retry LLMTimeoutError."""
    from novel_factory.llm.openai_compatible import (
        OpenAICompatibleProvider,
        LLMTimeoutError,
    )
    from novel_factory.config.settings import LLMConfig

    class TimeoutClient:
        def __init__(self):
            self.calls = 0

        def invoke(self, messages, **kwargs):
            self.calls += 1
            raise LLMTimeoutError("timeout once")

    provider = OpenAICompatibleProvider(LLMConfig(retry_attempts=3, min_interval_seconds=0))
    client = TimeoutClient()
    provider._client = client

    with pytest.raises(LLMTimeoutError):
        provider.invoke_text([{"role": "user", "content": "hi"}])

    assert client.calls == 1


# ── Desktop Config API Tests ──────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    from novel_factory.db.connection import init_db
    db_file = tmp_path / "test.db"
    init_db(str(db_file))
    yield str(db_file)


@pytest.fixture
def desktop_client(db_path, tmp_path, monkeypatch):
    """Create a test client with desktop runtime enabled."""
    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("NOVELOS_CONFIG_PATH", str(tmp_path / "config.yaml"))

    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app

    app = create_api_app(db_path=db_path, llm_mode="stub")
    with TestClient(app) as test_client:
        yield test_client


def test_desktop_config_get_includes_agent_llm_fallback(desktop_client, tmp_path, monkeypatch):
    """GET /desktop/config returns agent_llm_fallback."""
    config_dir = tmp_path / "desktop_get"
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("NOVELOS_CONFIG_PATH", str(config_dir / "config.yaml"))

    import yaml
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump({
            "llm_mode": "real",
            "llm_profiles": {
                "default": {"provider": "openai_compatible", "model": "gpt-4o", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
                "fast": {"provider": "openai_compatible", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            },
            "agent_llm": {"memory_curator": "default"},
            "agent_llm_fallback": {"memory_curator": "fast"},
        }, f)

    response = desktop_client.get("/api/desktop/config")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data.get("agent_llm_fallback") == {"memory_curator": "fast"}


def test_desktop_config_put_validates_fallback_profile(desktop_client, tmp_path, monkeypatch):
    """PUT /desktop/config rejects fallback profile that does not exist."""
    config_dir = tmp_path / "desktop_put"
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("NOVELOS_CONFIG_PATH", str(config_dir / "config.yaml"))

    import yaml
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump({
            "llm_mode": "real",
            "llm_profiles": {
                "default": {"provider": "openai_compatible", "model": "gpt-4o", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            },
        }, f)

    response = desktop_client.put("/api/desktop/config", json={
        "llm_mode": "real",
        "llm_profiles": {
            "default": {"provider": "openai_compatible", "model": "gpt-4o", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "agent_llm_fallback": {"memory_curator": "nonexistent"},
    })
    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is False
    assert "nonexistent" in body.get("error", {}).get("message", "")


def test_desktop_config_put_saves_agent_llm_fallback(desktop_client, tmp_path, monkeypatch):
    """PUT /desktop/config successfully saves agent_llm_fallback."""
    config_dir = tmp_path / "desktop_put_save"
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("NOVELOS_CONFIG_PATH", str(config_dir / "config.yaml"))

    import yaml
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump({
            "llm_mode": "real",
            "llm_profiles": {
                "default": {"provider": "openai_compatible", "model": "gpt-4o", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
                "fast": {"provider": "openai_compatible", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            },
        }, f)

    response = desktop_client.put("/api/desktop/config", json={
        "llm_mode": "real",
        "llm_profiles": {
            "default": {"provider": "openai_compatible", "model": "gpt-4o", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "fast": {"provider": "openai_compatible", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "agent_llm": {"memory_curator": "default"},
        "agent_llm_fallback": {"memory_curator": "fast"},
    })
    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is True
    assert body["data"].get("saved") is True

    # Verify file contents
    with open(config_file, "r", encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert saved.get("agent_llm_fallback") == {"memory_curator": "fast"}
