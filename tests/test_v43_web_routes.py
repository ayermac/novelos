"""v4.3 Web Routes tests - HTTP endpoint testing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_factory.web.app import create_app
from novel_factory.db.connection import init_db


@pytest.fixture
def client():
    """Create a test client with a temporary database."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test_web.db")
        init_db(db_path)

        app = create_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)
        yield client


class TestDashboard:
    def test_dashboard_returns_200(self, client):
        """GET / returns 200."""
        response = client.get("/")
        assert response.status_code == 200
        assert "AttributeError" not in response.text
        assert "list_projects" not in response.text

    def test_dashboard_shows_db_path(self, client):
        """Dashboard shows database path."""
        response = client.get("/")
        assert response.status_code == 200
        # Should show DB path somewhere in the response
        assert "DB:" in response.text or "db_path" in response.text.lower()


class TestProjects:
    def test_projects_returns_200(self, client):
        """GET /projects returns 200."""
        response = client.get("/projects")
        assert response.status_code == 200

    def test_project_detail_not_found(self, client):
        """GET /projects/nonexistent returns 404 or shows error."""
        response = client.get("/projects/nonexistent")
        # Should not crash
        assert response.status_code in [200, 404]


class TestRun:
    def test_run_returns_200(self, client):
        """GET /run returns 200."""
        response = client.get("/run")
        assert response.status_code == 200

    def test_run_chapter_post_stub(self, client):
        """POST /run/chapter with stub mode executes without traceback."""
        # First seed a project
        from novel_factory.db.connection import get_connection

        db_path = client.app.state.db_path
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name) VALUES (?, ?)",
                ("test_proj", "Test Project"),
            )
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
                ("test_proj", 1, "Test Chapter", "planned"),
            )
            conn.commit()
        finally:
            conn.close()

        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_proj",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 5,
            },
        )
        # Should not crash or return 500
        assert response.status_code in [200, 302]
        # Should not contain traceback
        assert "Traceback" not in response.text
        # Should not contain Dispatcher construction errors
        assert "unexpected keyword argument" not in response.text.lower()
        assert "Error:" not in response.text or "error" not in response.text.lower()
        
        # Verify chapter status changed (real business result)
        conn = get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT status FROM chapters WHERE project_id = ? AND chapter_number = ?",
                ("test_proj", 1),
            )
            row = cursor.fetchone()
            assert row is not None, "Chapter should exist"
            # In stub mode, chapter should have progressed from 'planned'
            assert row[0] != "planned", f"Chapter status should have changed from 'planned', got: {row[0]}"
        finally:
            conn.close()


class TestBatch:
    def test_batch_returns_200(self, client):
        """GET /batch returns 200."""
        response = client.get("/batch")
        assert response.status_code == 200


class TestQueue:
    def test_queue_returns_200(self, client):
        """GET /queue returns 200."""
        response = client.get("/queue")
        assert response.status_code == 200


class TestSerial:
    def test_serial_returns_200(self, client):
        """GET /serial returns 200."""
        response = client.get("/serial")
        assert response.status_code == 200


class TestReview:
    def test_review_returns_200(self, client):
        """GET /review returns 200."""
        response = client.get("/review")
        assert response.status_code == 200


class TestStyle:
    def test_style_returns_200(self, client):
        """GET /style returns 200."""
        response = client.get("/style")
        assert response.status_code == 200

    def test_style_init_creates_bible_in_web_db(self, client):
        """POST /style/init creates Style Bible in current Web DB."""
        from novel_factory.db.connection import get_connection

        db_path = client.app.state.db_path
        conn = get_connection(db_path)
        try:
            # Create a project first
            conn.execute(
                "INSERT INTO projects (project_id, name) VALUES (?, ?)",
                ("style_test_proj", "Style Test Project"),
            )
            conn.commit()
        finally:
            conn.close()

        # Initialize Style Bible
        response = client.post(
            "/style/init",
            data={
                "project_id": "style_test_proj",
                "template": "default_web_serial",
            },
        )
        
        assert response.status_code == 200
        assert "Traceback" not in response.text
        assert "unexpected keyword argument" not in response.text.lower()
        
        # Verify Style Bible was created in Web DB
        from novel_factory.db.repository import Repository
        repo = Repository(db_path)
        bible = repo.get_style_bible("style_test_proj")
        
        assert bible is not None, "Style Bible should be created in Web DB"
        assert bible.get("project_id") == "style_test_proj"

    def test_style_gate_set_uses_correct_field_name(self, client):
        """POST /style/gate-set saves blocking_threshold (not threshold)."""
        from novel_factory.db.connection import get_connection

        db_path = client.app.state.db_path
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name) VALUES (?, ?)",
                ("gate_test_proj", "Gate Test Project"),
            )
            conn.commit()
        finally:
            conn.close()

        # First initialize Style Bible (gate config requires Style Bible to exist)
        init_response = client.post(
            "/style/init",
            data={
                "project_id": "gate_test_proj",
                "template": "default_web_serial",
            },
        )
        assert init_response.status_code == 200

        # Set gate config
        response = client.post(
            "/style/gate-set",
            data={
                "project_id": "gate_test_proj",
                "mode": "block",
                "threshold": 85,
                "enabled": "true",
            },
        )
        
        assert response.status_code == 200
        assert "Traceback" not in response.text
        
        # Verify blocking_threshold was saved (not threshold)
        from novel_factory.db.repository import Repository
        repo = Repository(db_path)
        gate_config = repo.get_style_gate_config("gate_test_proj")
        
        assert gate_config is not None, "Gate config should exist"
        assert "blocking_threshold" in gate_config, "Should have blocking_threshold field"
        assert gate_config["blocking_threshold"] == 85, "blocking_threshold should be 85"
        assert gate_config["mode"] == "block", "mode should be block"

    def test_style_proposal_decide_maps_status(self, client):
        """POST /style/proposal-decide maps approve/reject to approved/rejected."""
        from novel_factory.db.connection import get_connection
        import json
        from datetime import datetime

        db_path = client.app.state.db_path
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name) VALUES (?, ?)",
                ("proposal_test_proj", "Proposal Test Project"),
            )
            # Create a pending proposal (note: primary key is 'id', not 'proposal_id')
            conn.execute(
                """INSERT INTO style_evolution_proposals 
                   (id, project_id, proposal_type, proposal_json, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "test_proposal_1",
                    "proposal_test_proj",
                    "adjust_pacing",
                    json.dumps({"test": "data"}),
                    "pending",
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        # Decide to approve
        response = client.post(
            "/style/proposal-decide",
            data={
                "proposal_id": "test_proposal_1",
                "decision": "approve",
                "notes": "Test approval",
            },
        )
        
        assert response.status_code == 200
        assert "Traceback" not in response.text
        
        # Verify proposal status changed to 'approved' (not 'approve')
        conn = get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT status FROM style_evolution_proposals WHERE id = ?",
                ("test_proposal_1",),
            )
            row = cursor.fetchone()
            assert row is not None, "Proposal should exist"
            assert row[0] == "approved", f"Status should be 'approved', got: {row[0]}"
        finally:
            conn.close()

    def test_style_page_lists_pending_proposals(self, client):
        """GET /style shows pending proposal IDs so users can decide them."""
        from novel_factory.db.connection import get_connection
        import json
        from datetime import datetime

        db_path = client.app.state.db_path
        conn = get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name) VALUES (?, ?)",
                ("proposal_list_proj", "Proposal List Project"),
            )
            conn.execute(
                """INSERT INTO style_evolution_proposals
                   (id, project_id, proposal_type, proposal_json, rationale, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    "pending_proposal_visible",
                    "proposal_list_proj",
                    "tone_adjustment",
                    json.dumps({"suggestion": "tighten voice"}),
                    "Use shorter sentences in high tension scenes",
                    "pending",
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        response = client.get("/style")

        assert response.status_code == 200
        assert "pending_proposal_visible" in response.text
        assert "tone_adjustment" in response.text
        assert "Use shorter sentences" in response.text


class TestConfig:
    def test_config_returns_200(self, client):
        """GET /config returns 200."""
        response = client.get("/config")
        assert response.status_code == 200

    def test_config_does_not_leak_api_keys(self, client):
        """Config page does not show actual API keys."""
        response = client.get("/config")
        assert response.status_code == 200
        # Should not contain common API key patterns
        text = response.text
        # Should show masked keys, not actual keys
        # (This is a basic check - real keys would be longer)
        assert "sk-" not in text  # OpenAI key prefix
        assert "api_key" not in text.lower() or "***" in text


class TestErrorHandling:
    def test_error_page_no_traceback(self, client):
        """Error pages do not show traceback."""
        # Trigger an error by accessing a route that will fail
        response = client.get("/projects/nonexistent_project_that_does_not_exist")
        # Should not crash with 500
        assert response.status_code in [200, 404]
        # Should not contain traceback
        assert "Traceback" not in response.text
        # Should show error message
        assert "not found" in response.text.lower() or "error" in response.text.lower()
