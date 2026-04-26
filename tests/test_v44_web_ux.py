"""Tests for v4.4 Web Review UX Hardening.

Focus on testing real business state changes, not HTML content.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_factory.db.connection import get_connection, init_db
from novel_factory.db.repository import Repository
from novel_factory.web.app import create_app


def _ensure_project(db_path: str, project_id: str, name: str = "Test Project") -> None:
    """Insert a project row."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name, genre, total_chapters_planned) "
            "VALUES (?, ?, ?, ?)",
            (project_id, name, "fantasy", 100),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Initialize database
    init_db(db_path)
    
    # Create test project
    _ensure_project(db_path, "test_project", "Test Project")
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client(temp_db):
    """Create a test client."""
    app = create_app(db_path=temp_db, config_path=None, llm_mode="stub")
    return TestClient(app)


class TestBatchPageEnhancements:
    """Test Batch page enhancements."""
    
    def test_batch_page_lists_production_runs(self, client, temp_db):
        """Batch page shows recent production runs with details."""
        repo = Repository(temp_db)
        
        # Create multiple runs
        run_id_1 = repo.create_production_run("test_project", 1, 3)
        run_id_2 = repo.create_production_run("test_project", 4, 6)
        
        response = client.get("/batch")
        assert response.status_code == 200
        
        # Check that runs are displayed
        assert run_id_1[:8].encode() in response.content
        assert run_id_2[:8].encode() in response.content
    
    def test_batch_review_post_changes_run_status(self, client, temp_db):
        """POST /batch/review changes production_run status."""
        repo = Repository(temp_db)
        run_id = repo.create_production_run("test_project", 1, 3)
        repo.update_production_run(run_id, status="awaiting_review")
        
        # Submit review with request_changes (doesn't require continuity gate)
        response = client.post(
            "/batch/review",
            data={
                "run_id": run_id,
                "decision": "request_changes",
                "notes": "Needs revision",
            },
        )
        assert response.status_code == 200
        assert b"list_production_run_items" not in response.content
        assert b"Error:" not in response.content
        
        # Verify status changed in DB
        run = repo.get_production_run(run_id)
        assert run["status"] == "request_changes"


class TestQueuePageEnhancements:
    """Test Queue page enhancements."""
    
    def test_queue_page_lists_items(self, client, temp_db):
        """Queue page shows queue items."""
        repo = Repository(temp_db)
        
        # Create queue items
        queue_id = repo.create_queue_item("test_project", 1, 3, priority=100)
        
        response = client.get("/queue")
        assert response.status_code == 200
        
        # Check that queue item is displayed
        assert queue_id[:8].encode() in response.content
    
    def test_queue_retry_post_changes_item_status(self, client, temp_db):
        """POST /queue/retry changes failed item to pending."""
        repo = Repository(temp_db)
        queue_id = repo.create_queue_item("test_project", 1, 3)
        repo.update_queue_item(queue_id, status="failed")
        
        # Retry
        response = client.post(
            "/queue/retry",
            data={"queue_id": queue_id},
        )
        assert response.status_code == 200
        
        # Verify status changed
        item = repo.get_queue_item(queue_id)
        assert item["status"] == "pending"
    
    def test_queue_pause_resume_post_changes_status(self, client, temp_db):
        """POST /queue/pause and /queue/resume change item status."""
        repo = Repository(temp_db)
        queue_id = repo.create_queue_item("test_project", 1, 3)
        
        # Pause
        response = client.post(
            "/queue/pause",
            data={"queue_id": queue_id},
        )
        assert response.status_code == 200
        item = repo.get_queue_item(queue_id)
        assert item["status"] == "paused"
        
        # Resume
        response = client.post(
            "/queue/resume",
            data={"queue_id": queue_id},
        )
        assert response.status_code == 200
        item = repo.get_queue_item(queue_id)
        assert item["status"] == "pending"


class TestSerialPageEnhancements:
    """Test Serial page enhancements."""
    
    def test_serial_page_lists_plans(self, client, temp_db):
        """Serial page shows list of serial plans."""
        repo = Repository(temp_db)
        
        # Create serial plan
        plan_id = repo.create_serial_plan(
            project_id="test_project",
            name="Test Plan",
            start_chapter=1,
            target_chapter=10,
            batch_size=3,
        )
        
        response = client.get("/serial")
        assert response.status_code == 200
        
        # Check that plan is displayed
        assert plan_id[:12].encode() in response.content
    
    def test_serial_enqueue_next_post_creates_queue_item(self, client, temp_db):
        """POST /serial/enqueue-next creates queue item."""
        repo = Repository(temp_db)
        
        plan_id = repo.create_serial_plan(
            project_id="test_project",
            name="Test Plan",
            start_chapter=1,
            target_chapter=10,
            batch_size=3,
        )
        
        # Enqueue next
        response = client.post(
            "/serial/enqueue-next",
            data={"serial_plan_id": plan_id},
        )
        assert response.status_code == 200
        
        # Verify queue item was created
        plan = repo.get_serial_plan(plan_id)
        assert plan["current_queue_id"] is not None


class TestStylePageEnhancements:
    """Test Style page enhancements."""
    
    def test_style_inline_proposal_approve_changes_status(self, client, temp_db):
        """Inline approve button changes proposal status to approved."""
        repo = Repository(temp_db)
        
        # Create proposal
        proposal_id = repo.create_style_evolution_proposal(
            project_id="test_project",
            proposal_type="tone_adjustment",
            proposal_json={"tone": "more formal"},
            rationale="User feedback",
        )
        
        # Approve via inline form
        response = client.post(
            "/style/proposal-decide",
            data={
                "proposal_id": proposal_id,
                "decision": "approve",
                "notes": "Approved",
            },
        )
        assert response.status_code == 200
        
        # Verify status changed
        proposal = repo.get_style_evolution_proposal(proposal_id)
        assert proposal["status"] == "approved"
    
    def test_style_inline_proposal_reject_changes_status(self, client, temp_db):
        """Inline reject button changes proposal status to rejected."""
        repo = Repository(temp_db)
        
        proposal_id = repo.create_style_evolution_proposal(
            project_id="test_project",
            proposal_type="tone_adjustment",
            proposal_json={"tone": "more casual"},
            rationale="User feedback",
        )
        
        # Reject via inline form
        response = client.post(
            "/style/proposal-decide",
            data={
                "proposal_id": proposal_id,
                "decision": "reject",
                "notes": "Not needed",
            },
        )
        assert response.status_code == 200
        
        # Verify status changed
        proposal = repo.get_style_evolution_proposal(proposal_id)
        assert proposal["status"] == "rejected"


class TestErrorHandling:
    """Test error handling improvements."""
    
    def test_error_pages_do_not_include_traceback(self, client, temp_db):
        """Error pages do not include Python traceback."""
        # Trigger an error by providing invalid data
        response = client.post(
            "/batch/run",
            data={
                "project_id": "nonexistent_project",
                "from_chapter": 1,
                "to_chapter": 3,
            },
        )
        assert response.status_code == 200
        
        # Check that no traceback is shown
        assert b"Traceback" not in response.content
        assert b"File " not in response.content


class TestResultPanels:
    """Test result panel improvements."""
    
    def test_success_result_panel_shows_checkmark(self, client, temp_db):
        """Success result panel shows checkmark icon."""
        repo = Repository(temp_db)
        # Single-chapter runs do not require a continuity gate for approve.
        run_id = repo.create_production_run("test_project", 1, 1)
        repo.update_production_run(run_id, status="awaiting_review")
        
        response = client.post(
            "/batch/review",
            data={
                "run_id": run_id,
                "decision": "approve",
            },
        )
        assert response.status_code == 200
        
        # Check for success indicator
        assert b"success-panel" in response.content
        assert b"\xe2\x9c\x85" in response.content
        assert repo.get_production_run(run_id)["status"] == "approved"
    
    def test_error_result_panel_shows_x(self, client, temp_db):
        """Error result panel shows X icon."""
        response = client.post(
            "/batch/review",
            data={
                "run_id": "nonexistent_run",
                "decision": "approve",
            },
        )
        assert response.status_code == 200
        
        # Check for error indicator
        assert b"error-panel" in response.content or b"\xe2\x9d\x8c" in response.content
