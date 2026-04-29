"""Tests for v5.3.2 Genesis canonical body-style API routes."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create test client with initialized database."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    test_client = TestClient(app)
    yield test_client
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture()
def project_id(client):
    """Create a project and return its ID."""
    resp = client.post("/api/onboarding/projects", json={
        "project_id": "test-genesis",
        "name": "Test Genesis",
        "genre": "奇幻",
        "description": "A test novel",
        "total_chapters_planned": 10,
        "target_words": 30000,
    })
    assert resp.status_code == 200
    data = resp.json()
    pid = data.get("data", {}).get("project", {}).get("project_id")
    assert pid, f"Expected project ID, got: {data}"
    return pid


class TestGenesisCanonicalRoutes:
    """v5.3.2: Genesis actions use body-style (project_id in body, not URL)."""

    def test_generate_canonical_body_style(self, client, project_id):
        """POST /api/genesis/generate with project_id in body."""
        resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
            "target_chapters": 10,
            "target_words": 30000,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        genesis = body["data"]
        assert genesis["project_id"] == project_id
        assert genesis["status"] == "generated"

    def test_generate_requires_project_id_in_body(self, client):
        """POST /api/genesis/generate without project_id should fail."""
        resp = client.post("/api/genesis/generate", json={
            "title": "Test",
            "genre": "奇幻",
        })
        # Should fail because project_id is missing or invalid
        assert resp.status_code == 200
        body = resp.json()
        # Either validation error or project not found
        assert body["ok"] is False or body.get("data", {}).get("status") == "failed"

    def test_approve_canonical_body_style(self, client, project_id):
        """POST /api/genesis/approve with project_id and genesis_id in body."""
        # First generate
        gen_resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        assert gen_resp.status_code == 200
        genesis_id = gen_resp.json()["data"]["id"]

        # Then approve via canonical route
        resp = client.post("/api/genesis/approve", json={
            "project_id": project_id,
            "genesis_id": genesis_id,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_reject_canonical_body_style(self, client, project_id):
        """POST /api/genesis/reject with project_id and genesis_id in body."""
        # First generate
        gen_resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        assert gen_resp.status_code == 200
        genesis_id = gen_resp.json()["data"]["id"]

        # Then reject via canonical route
        resp = client.post("/api/genesis/reject", json={
            "project_id": project_id,
            "genesis_id": genesis_id,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_approve_wrong_project_returns_error(self, client, project_id):
        """Approve with wrong project_id returns error."""
        gen_resp = client.post("/api/genesis/generate", json={
            "project_id": project_id,
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        genesis_id = gen_resp.json()["data"]["id"]

        resp = client.post("/api/genesis/approve", json={
            "project_id": "nonexistent",
            "genesis_id": genesis_id,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False

    def test_old_path_style_still_works(self, client, project_id):
        """Legacy path-style routes remain functional for backward compat."""
        resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
