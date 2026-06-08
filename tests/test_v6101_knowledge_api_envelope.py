"""Regression tests for Knowledge Skill API envelope compatibility."""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app


def test_knowledge_skills_list_returns_frontend_envelope(tmp_path):
    """GET /knowledge-skills must match the frontend api.get() envelope contract."""
    db_path = tmp_path / "test.db"
    client = TestClient(create_api_app(db_path=str(db_path), llm_mode="stub"))

    response = client.get("/api/knowledge-skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert isinstance(payload["data"], list)
    assert payload["data"]
    assert all(item["qualified_id"].startswith("knowledge:") for item in payload["data"])


def test_knowledge_selection_preview_returns_frontend_envelope(tmp_path):
    """POST /knowledge-skills/select must also be enveloped for UI preview clients."""
    db_path = tmp_path / "test.db"
    client = TestClient(create_api_app(db_path=str(db_path), llm_mode="stub"))

    response = client.post(
        "/api/knowledge-skills/select",
        json={
            "agent_id": "author",
            "genre": "urban",
            "token_budget": 1200,
            "quality_signals": ["LOW_COLLOQUIAL_MARKERS"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert "skills" in payload["data"]
    assert "selection_reason" in payload["data"]
