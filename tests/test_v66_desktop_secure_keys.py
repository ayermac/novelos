"""v6.6 Desktop secure API key storage tests."""

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


def test_desktop_config_never_returns_api_key_value(tmp_path: Path, monkeypatch):
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
        "    api_key: sk-secret-should-not-appear\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "real",
    )
    response = client.get("/api/desktop/config")
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    # Ensure no secret value leaks in any string field
    response_text = response.text
    assert "sk-secret-should-not-appear" not in response_text
    assert data["profiles"]["default"]["api_key_env"] == "OPENAI_API_KEY"


def test_desktop_config_shows_secure_storage_source(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NOVELOS_DESKTOP_SECRET_KEYS", "OPENAI_API_KEY")
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "real",
    )
    response = client.get("/api/desktop/config")
    body = response.json()
    assert body["ok"] is True
    profile = body["data"]["profiles"]["default"]
    assert profile["api_key_configured"] is True
    assert profile["api_key_source"] == "desktop_secure_storage"


def test_desktop_config_shows_environment_source(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # NOVELOS_DESKTOP_SECRET_KEYS not set, or does not include OPENAI_API_KEY
    monkeypatch.setenv("NOVELOS_DESKTOP_SECRET_KEYS", "OTHER_API_KEY")
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "real",
    )
    response = client.get("/api/desktop/config")
    body = response.json()
    assert body["ok"] is True
    profile = body["data"]["profiles"]["default"]
    assert profile["api_key_configured"] is True
    assert profile["api_key_source"] == "environment"


def test_desktop_config_shows_missing_source(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NOVELOS_DESKTOP_SECRET_KEYS", raising=False)
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    api_key_env: OPENAI_API_KEY\n",
        "real",
    )
    response = client.get("/api/desktop/config")
    body = response.json()
    assert body["ok"] is True
    profile = body["data"]["profiles"]["default"]
    assert profile["api_key_configured"] is False
    assert profile["api_key_source"] == "missing"


def test_desktop_config_put_rejects_secret_fields(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text(
        "llm_mode: stub\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    model: gpt-4\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode="stub"))

    response = client.put("/api/desktop/config", json={"api_key": "sk-secret"})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SECURITY_REJECTED"
    assert "sk-secret" not in config_path.read_text(encoding="utf-8")


def test_desktop_config_put_rejects_api_key_env_field(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text("llm_mode: stub\n", encoding="utf-8")
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode="stub"))

    response = client.put("/api/desktop/config", json={"apiKey": "secret"})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SECURITY_REJECTED"


def test_desktop_config_put_rejects_token_field(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text("llm_mode: stub\n", encoding="utf-8")
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode="stub"))

    response = client.put("/api/desktop/config", json={"token": "secret"})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SECURITY_REJECTED"


def test_desktop_config_put_rejects_nested_secret_field(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text("llm_mode: stub\n", encoding="utf-8")
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode="stub"))

    response = client.put("/api/desktop/config", json={"profiles": [{"secret": "sk-nested"}]})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SECURITY_REJECTED"
    assert "sk-nested" not in config_path.read_text(encoding="utf-8")


def test_desktop_config_raw_preview_redacts_secrets(tmp_path: Path, monkeypatch):
    client = _make_client(
        tmp_path,
        monkeypatch,
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    api_key: sk-secret\n"
        "    refresh_token: rt-secret\n"
        "    password: pw-secret\n"
        "    authorization: Bearer abc\n",
        "real",
    )
    response = client.get("/api/desktop/config")
    body = response.json()
    assert body["ok"] is True
    preview = body["data"]["raw_preview"]
    assert "sk-secret" not in preview
    assert "rt-secret" not in preview
    assert "pw-secret" not in preview
    assert "Bearer abc" not in preview
    assert "***REDACTED***" in preview
