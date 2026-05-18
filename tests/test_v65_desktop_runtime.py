"""v6.5 Desktop runtime and config governance tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db


def test_desktop_config_write_rejected_outside_desktop_runtime(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "local.yaml"
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
    monkeypatch.delenv("NOVELOS_DESKTOP", raising=False)

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode="stub"))
    response = client.put("/api/desktop/config", json={"model": "gpt-4o"})

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "DESKTOP_ONLY"
    assert "gpt-4o" not in config_path.read_text(encoding="utf-8")


def test_desktop_config_write_must_stay_inside_desktop_config_dir(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "desktop-config"
    config_dir.mkdir()
    outside_config = tmp_path / "outside.yaml"
    outside_config.write_text("llm_mode: stub\n", encoding="utf-8")
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(outside_config), llm_mode="stub"))
    response = client.put("/api/desktop/config", json={"model": "gpt-4o"})

    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CONFIG_PATH_OUTSIDE_DESKTOP_DIR"
    assert "gpt-4o" not in outside_config.read_text(encoding="utf-8")


def test_desktop_config_redacts_secret_like_fields(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text(
        "llm_mode: real\n"
        "default_llm: default\n"
        "llm_profiles:\n"
        "  default:\n"
        "    provider: openai_compatible\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key: sk-secret\n"
        "    api_key_env: OPENAI_API_KEY\n"
        "    authorization: Bearer abc\n"
        "    nested:\n"
        "      refresh_token: token-secret\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    monkeypatch.setenv("NOVELOS_DESKTOP", "1")
    monkeypatch.setenv("NOVELOS_CONFIG_DIR", str(config_dir))

    client = TestClient(create_api_app(db_path=str(db_path), config_path=str(config_path), llm_mode="real"))
    response = client.get("/api/desktop/config")

    body = response.json()
    assert body["ok"] is True
    preview = body["data"]["raw_preview"]
    assert "sk-secret" not in preview
    assert "Bearer abc" not in preview
    assert "token-secret" not in preview
    assert "OPENAI_API_KEY" in preview
