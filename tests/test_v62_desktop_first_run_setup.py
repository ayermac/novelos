"""v6.2.2 Desktop first-run real LLM setup tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db


def _make_client(tmp_path: Path, monkeypatch, config_yaml: str, llm_mode: str = "stub") -> TestClient:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text(config_yaml, encoding="utf-8")
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))

    return TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode=llm_mode))


def test_desktop_config_accepts_api_key_env(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: stub\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "stub",
    )
    response = client.put("/api/desktop/config", json={"api_key_env": "DEEPSEEK_API_KEY"})
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["restart_required"] is True
    content = (tmp_path / "config" / "local.yaml").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY" in content


def test_desktop_config_rejects_raw_api_key(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: stub\n",
        "stub",
    )
    response = client.put("/api/desktop/config", json={"api_key": "sk-secret"})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SECURITY_REJECTED"


def test_desktop_config_rejects_secret_token(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: stub\n",
        "stub",
    )
    response = client.put("/api/desktop/config", json={"my_secret_token": "xyz"})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SECURITY_REJECTED"


def test_desktop_config_restart_required_on_change(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: stub\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "stub",
    )
    response = client.put("/api/desktop/config", json={"model": "gpt-4o"})
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["restart_required"] is True


def test_desktop_config_no_restart_when_unchanged(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "real",
    )
    response = client.put("/api/desktop/config", json={"model": "gpt-4"})
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["restart_required"] is False


def test_desktop_config_returns_configured_and_runtime_modes(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "stub",
    )
    response = client.get("/api/desktop/config")
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["llm_mode"] == "real"
    assert body["data"]["configured_llm_mode"] == "real"
    assert body["data"]["runtime_llm_mode"] == "stub"


def test_desktop_config_accepts_agent_llm_routes(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: stub\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "stub",
    )
    response = client.put("/api/desktop/config", json={
        "llm_mode": "real",
        "agent_llm": {
            "planner": "default",
            "author": "default",
            "editor": "default",
        },
    })
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["restart_required"] is True
    content = (tmp_path / "config" / "local.yaml").read_text(encoding="utf-8")
    assert "agent_llm:" in content
    assert "planner: default" in content
    assert "author: default" in content
    assert "editor: default" in content


def test_desktop_config_creates_agent_specific_model_profiles(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: stub\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4o-mini\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "stub",
    )
    response = client.put("/api/desktop/config", json={
        "llm_mode": "real",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "api_key_env": "OPENAI_API_KEY",
        "agent_models": {
            "author": "MiniMax-M2.7",
            "editor": "Kimi-K2.6",
        },
    })
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["restart_required"] is True

    content = (tmp_path / "config" / "local.yaml").read_text(encoding="utf-8")
    assert "author:" in content
    assert "model: MiniMax-M2.7" in content
    assert "editor:" in content
    assert "model: Kimi-K2.6" in content
    assert "agent_llm:" in content
    assert "author: author" in content
    assert "editor: editor" in content


def test_desktop_test_llm_rejected_outside_desktop(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text("llm_mode: real\n", encoding="utf-8")
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    monkeypatch.delenv("NOVELOS_DESKTOP", raising=False)

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode="real"))
    response = client.post("/api/desktop/test-llm", json={
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    })
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "DESKTOP_ONLY"


def test_desktop_test_llm_returns_stub_mode(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: stub\n",
        "stub",
    )
    response = client.post("/api/desktop/test-llm", json={
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    })
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["ok"] is False
    assert data["error_code"] == "STUB_MODE"


def test_desktop_test_llm_returns_api_key_missing(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4o-mini\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "real",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/api/desktop/test-llm", json={
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    })
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["ok"] is False
    assert data["error_code"] == "API_KEY_MISSING"
    assert "API Key 未配置" in data["message"]


def test_desktop_test_llm_returns_placeholder_key_error(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n",
        "real",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-placeholder")
    response = client.post("/api/desktop/test-llm", json={
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    })
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["ok"] is False
    assert data["error_code"] == "API_KEY_MISSING"


def test_desktop_config_redacts_secrets_in_response(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key: sk-secret-value\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "real",
    )
    response = client.get("/api/desktop/config")
    body = response.json()
    assert body["ok"] is True
    raw_preview = body["data"].get("raw_preview", "")
    assert "sk-secret-value" not in raw_preview
    assert "***REDACTED***" in raw_preview
