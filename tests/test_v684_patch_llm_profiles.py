"""v6.8.4: PATCH /settings/llm-profiles/{name} endpoint tests."""

from __future__ import annotations

import pytest
import yaml


@pytest.fixture()
def config_dir(tmp_path):
    config = {
        "db_path": str(tmp_path / "test.db"),
        "llm_profiles": {
            "default": {
                "provider": "openai_compatible",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "max_tokens": 4096,
                "temperature": 0.7,
            },
            "author": {
                "provider": "openai_compatible",
                "model": "gpt-4o",
                "max_tokens": 8192,
                "temperature": 0.8,
            },
        },
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return str(config_file)


@pytest.fixture()
def client(config_dir):
    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app
    app = create_api_app(config_path=config_dir, llm_mode="stub")
    return TestClient(app)


class TestPatchLlmProfile:
    def test_update_max_tokens(self, client, config_dir):
        resp = client.patch("/api/settings/llm-profiles/default", json={"max_tokens": 8192})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["updated_fields"]["max_tokens"]["new"] == 8192
        with open(config_dir) as f:
            cfg = yaml.safe_load(f)
        assert cfg["llm_profiles"]["default"]["max_tokens"] == 8192
        assert cfg["llm_profiles"]["default"]["model"] == "gpt-4"

    def test_update_temperature(self, client, config_dir):
        resp = client.patch("/api/settings/llm-profiles/author", json={"temperature": 0.9})
        assert resp.status_code == 200
        with open(config_dir) as f:
            cfg = yaml.safe_load(f)
        assert cfg["llm_profiles"]["author"]["temperature"] == 0.9

    def test_reject_sensitive_field(self, client):
        resp = client.patch("/api/settings/llm-profiles/default", json={"api_key": "sk-xxx"})
        assert resp.json()["ok"] is False
        assert "SECURITY_REJECTED" in resp.json().get("error", {}).get("code", "")

    def test_reject_base_url(self, client):
        resp = client.patch("/api/settings/llm-profiles/default", json={"base_url": "https://evil.com"})
        assert resp.json()["ok"] is False

    def test_reject_provider(self, client):
        resp = client.patch("/api/settings/llm-profiles/default", json={"provider": "anthropic"})
        assert resp.json()["ok"] is False

    def test_reject_unknown_field(self, client):
        resp = client.patch("/api/settings/llm-profiles/default", json={"unknown_field": 123})
        assert resp.json()["ok"] is False
        assert "VALIDATION_ERROR" in resp.json().get("error", {}).get("code", "")

    def test_profile_not_found(self, client):
        resp = client.patch("/api/settings/llm-profiles/nonexistent", json={"max_tokens": 4096})
        assert resp.json()["ok"] is False
        assert "PROFILE_NOT_FOUND" in resp.json().get("error", {}).get("code", "")

    def test_reject_negative_value(self, client):
        resp = client.patch("/api/settings/llm-profiles/default", json={"max_tokens": -1})
        assert resp.json()["ok"] is False

    def test_no_config_path(self, tmp_path):
        from fastapi.testclient import TestClient
        from novel_factory.api_app import create_api_app
        app = create_api_app(db_path=str(tmp_path / "test.db"), llm_mode="stub")
        c = TestClient(app)
        resp = c.patch("/api/settings/llm-profiles/default", json={"max_tokens": 4096})
        assert resp.json()["ok"] is False
