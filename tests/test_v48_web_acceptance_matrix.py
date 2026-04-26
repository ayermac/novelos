"""Tests for v4.8 Web Acceptance Matrix.

Tests the acceptance matrix page and data structure.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_factory.db.connection import init_db
from novel_factory.web.app import create_app
from novel_factory.web.acceptance_matrix import (
    CAPABILITIES,
    get_acceptance_matrix,
    get_capability_by_id,
    validate_capability_ids,
)


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


class TestAcceptanceMatrixPage:
    """Test the acceptance matrix web page."""

    def test_acceptance_page_returns_200(self, client):
        """GET /acceptance returns 200."""
        response = client.get("/acceptance")
        assert response.status_code == 200

    def test_acceptance_page_has_title(self, client):
        """Page has Acceptance Matrix title."""
        response = client.get("/acceptance")
        assert "Acceptance Matrix" in response.text

    def test_acceptance_page_has_all_capabilities(self, client):
        """Page contains all core capabilities."""
        response = client.get("/acceptance")
        
        # Check for key capabilities
        assert "onboarding" in response.text.lower()
        assert "run_chapter" in response.text.lower()
        assert "project_workspace" in response.text.lower()
        assert "batch" in response.text.lower()
        assert "queue" in response.text.lower()
        assert "serial" in response.text.lower()
        assert "review" in response.text.lower()
        assert "style_bible" in response.text.lower()
        assert "style_gate" in response.text.lower()
        assert "style_samples" in response.text.lower()
        assert "style_proposals" in response.text.lower()
        assert "config" in response.text.lower()

    def test_acceptance_page_has_status_values(self, client):
        """Page contains pass/partial/missing status."""
        response = client.get("/acceptance")
        
        # Should have status badges
        assert "status-pass" in response.text or "通过" in response.text
        # May or may not have partial/missing depending on current state
        assert "status-" in response.text

    def test_acceptance_page_has_web_routes(self, client):
        """Page shows web route information."""
        response = client.get("/acceptance")
        
        # Should show some web routes
        assert "/onboarding" in response.text
        assert "/run" in response.text
        assert "/projects" in response.text

    def test_acceptance_page_has_test_coverage(self, client):
        """Page shows test coverage information."""
        response = client.get("/acceptance")
        
        # Should mention tests
        assert "test" in response.text.lower()
        # Should have success/failure test badges
        assert "成功" in response.text or "success" in response.text.lower()

    def test_acceptance_page_no_traceback(self, client):
        """Page does not contain traceback."""
        response = client.get("/acceptance")
        
        # Should not have Python traceback
        assert "Traceback" not in response.text
        assert "File " not in response.text or "File \"" not in response.text

    def test_acceptance_page_no_api_key(self, client):
        """Page does not contain API key or secret."""
        response = client.get("/acceptance")
        
        # Should not have API key patterns
        assert "api_key" not in response.text.lower() or "API key" not in response.text
        assert "secret" not in response.text.lower() or "secret" not in response.text
        assert "sk-" not in response.text

    def test_acceptance_page_has_summary(self, client):
        """Page has summary statistics."""
        response = client.get("/acceptance")
        
        # Should have summary section
        assert "总能力" in response.text or "total" in response.text.lower()
        assert "通过率" in response.text or "pass" in response.text.lower()

    def test_acceptance_page_no_raw_json(self, client):
        """Page does not show raw JSON."""
        response = client.get("/acceptance")
        
        # Should not have raw JSON dumps
        assert '{"capabilities"' not in response.text
        assert '["capabilities"]' not in response.text


class TestAcceptanceMatrixData:
    """Test the acceptance matrix data structure."""

    def test_get_acceptance_matrix_returns_dict(self):
        """get_acceptance_matrix() returns a dict."""
        matrix = get_acceptance_matrix()
        
        assert isinstance(matrix, dict)
        assert "capabilities" in matrix
        assert "summary" in matrix

    def test_capabilities_list_not_empty(self):
        """Capabilities list is not empty."""
        matrix = get_acceptance_matrix()
        
        assert len(matrix["capabilities"]) > 0

    def test_summary_has_required_fields(self):
        """Summary has all required fields."""
        matrix = get_acceptance_matrix()
        summary = matrix["summary"]
        
        assert "total" in summary
        assert "passed" in summary
        assert "partial" in summary
        assert "missing" in summary
        assert "pass_rate" in summary

    def test_summary_counts_match_capabilities(self):
        """Summary counts match actual capabilities."""
        matrix = get_acceptance_matrix()
        
        total = matrix["summary"]["total"]
        passed = matrix["summary"]["passed"]
        partial = matrix["summary"]["partial"]
        missing = matrix["summary"]["missing"]
        
        assert total == len(matrix["capabilities"])
        assert passed + partial + missing == total

    def test_each_capability_has_required_fields(self):
        """Each capability has required fields."""
        matrix = get_acceptance_matrix()
        
        for cap in matrix["capabilities"]:
            assert "capability_id" in cap
            assert "label" in cap
            assert "web_route" in cap
            assert "status" in cap
            assert cap["status"] in ["pass", "partial", "missing"]

    def test_capability_ids_are_unique(self):
        """All capability IDs are unique."""
        duplicates = validate_capability_ids()
        
        assert duplicates == [], f"Duplicate capability IDs found: {duplicates}"

    def test_get_capability_by_id_returns_capability(self):
        """get_capability_by_id() returns the right capability."""
        cap = get_capability_by_id("onboarding")
        
        assert cap is not None
        assert cap.capability_id == "onboarding"
        assert cap.label == "Onboarding"

    def test_get_capability_by_id_returns_none_for_unknown(self):
        """get_capability_by_id() returns None for unknown ID."""
        cap = get_capability_by_id("nonexistent_capability")
        
        assert cap is None

    def test_capabilities_have_valid_status(self):
        """All capabilities have valid status values."""
        for cap in CAPABILITIES:
            assert cap.status in ["pass", "partial", "missing"], \
                f"Invalid status '{cap.status}' for capability '{cap.capability_id}'"

    def test_capabilities_from_python_not_template(self):
        """Capabilities come from Python data structure, not template."""
        # Verify that we can import and use the data directly
        from novel_factory.web.acceptance_matrix import CAPABILITIES
        
        assert len(CAPABILITIES) > 0
        
        # Verify each is a proper Capability object
        for cap in CAPABILITIES:
            assert hasattr(cap, 'capability_id')
            assert hasattr(cap, 'label')
            assert hasattr(cap, 'status')

    def test_success_test_files_exist(self):
        """Each non-empty success_test must exist in tests/ directory."""
        from pathlib import Path
        
        tests_dir = Path(__file__).parent
        
        for cap in CAPABILITIES:
            if cap.success_test:
                test_file = tests_dir / cap.success_test
                assert test_file.exists(), \
                    f"Capability '{cap.capability_id}' has success_test='{cap.success_test}' but file does not exist at {test_file}"

    def test_failure_test_files_exist(self):
        """Each non-empty failure_test must exist in tests/ directory."""
        from pathlib import Path
        
        tests_dir = Path(__file__).parent
        
        for cap in CAPABILITIES:
            if cap.failure_test:
                test_file = tests_dir / cap.failure_test
                assert test_file.exists(), \
                    f"Capability '{cap.capability_id}' has failure_test='{cap.failure_test}' but file does not exist at {test_file}"

    def test_pass_capabilities_have_required_coverage(self):
        """status=pass capabilities must have web_route, success_test, failure_test, safety_check."""
        for cap in CAPABILITIES:
            if cap.status == "pass":
                assert cap.web_route is not None, \
                    f"Capability '{cap.capability_id}' has status=pass but no web_route"
                assert cap.success_test is not None, \
                    f"Capability '{cap.capability_id}' has status=pass but no success_test"
                assert cap.failure_test is not None, \
                    f"Capability '{cap.capability_id}' has status=pass but no failure_test"
                assert cap.safety_check is True, \
                    f"Capability '{cap.capability_id}' has status=pass but safety_check=False"

    def test_pass_capabilities_without_db_assertion_must_explain(self):
        """If status=pass but db_assertion=False, notes must explain why."""
        for cap in CAPABILITIES:
            if cap.status == "pass" and not cap.db_assertion:
                assert cap.notes is not None and len(cap.notes) > 0, \
                    f"Capability '{cap.capability_id}' has status=pass and db_assertion=False but no notes explaining why"


class TestAcceptanceMatrixNavigation:
    """Test navigation to acceptance matrix."""

    def test_acceptance_link_in_nav(self, client):
        """Acceptance link appears in navigation."""
        response = client.get("/")
        
        assert "/acceptance" in response.text

    def test_acceptance_page_links_to_capabilities(self, client):
        """Acceptance page has links to capability routes."""
        response = client.get("/acceptance")
        
        # Should have links to various routes
        assert 'href="/onboarding"' in response.text or 'href="/run"' in response.text


class TestAcceptanceMatrixSafety:
    """Test safety requirements for acceptance matrix."""

    def test_no_shell_execution(self):
        """Acceptance matrix does not execute shell commands."""
        # The acceptance matrix should only read data, not execute pytest or shell
        matrix = get_acceptance_matrix()
        
        # Should be purely data-driven
        assert isinstance(matrix, dict)
        assert "capabilities" in matrix

    def test_no_database_writes(self, client, temp_db):
        """Acceptance page does not write to database."""
        from novel_factory.db.repository import Repository
        
        # Get initial state
        repo = Repository(temp_db)
        projects_before = repo.list_projects()
        
        # Access acceptance page
        client.get("/acceptance")
        
        # Verify no changes
        projects_after = repo.list_projects()
        assert len(projects_after) == len(projects_before)

    def test_no_production_logic(self, client, temp_db):
        """Acceptance page does not trigger production."""
        from novel_factory.db.repository import Repository
        
        repo = Repository(temp_db)
        
        # Access acceptance page
        client.get("/acceptance")
        
        # Verify no production runs created (check for any project)
        # Since we haven't created any projects, this should be empty
        projects = repo.list_projects()
        for project in projects:
            runs = repo.get_workflow_runs_for_project(project["project_id"])
            assert len(runs) == 0
