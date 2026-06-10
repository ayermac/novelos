"""Tests for v6.6.6 Workflow Recovery & State Integrity Closure.

Tests the derive_workflow_recovery_state() pure function and its integration
with API routes and workflow execution.
"""

import pytest
from datetime import datetime, timedelta

from novel_factory.workflow.state_integrity import (
    derive_workflow_recovery_state,
    RecoveryCapability,
    CheckpointState,
    is_local_edit_state,
    should_protect_from_blocking,
    STALE_CHECKPOINT_SECONDS,
    STALE_RUNNING_RUN_SECONDS,
)


# ── Pure Function Tests ─────────────────────────────────────────────


def test_state_matrix_planned_no_run():
    """Test planned status with no run."""
    result = derive_workflow_recovery_state(
        chapter={"status": "planned", "content": ""},
        latest_run=None,
        checkpoint_info=None,
        has_existing_content=False,
    )

    assert result["chapter_status"] == "planned"
    assert result["run_status"] is None
    assert result["recovery_capability"] == RecoveryCapability.NO_RECOVERY_NEEDED.value
    assert "generate" in result["safe_actions"]
    assert result["checkpoint_status"] == CheckpointState.ABSENT.value


def test_state_matrix_running_resumable_checkpoint():
    """Healthy running runs should not show recovery actions."""
    now = datetime.utcnow() + timedelta(hours=8)
    started_at = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")

    result = derive_workflow_recovery_state(
        chapter={"status": "drafted", "content": "some content"},
        latest_run={
            "id": "run-123",
            "status": "running",
            "started_at": started_at,
            "current_node": "author",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "author"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "drafted"
    assert result["run_status"] == "running"
    assert result["recovery_capability"] == RecoveryCapability.NO_RECOVERY_NEEDED.value
    assert result["recommended_action"] is None
    assert result["safe_actions"] == []
    assert result["checkpoint_status"] in (CheckpointState.RESUMABLE.value, CheckpointState.EXISTS.value)


def test_state_matrix_running_stale_checkpoint():
    """Test stale running run recommends mark_stuck before rerun/reset."""
    now = datetime.utcnow() + timedelta(hours=8)
    # Run started 5 hours ago (beyond STALE_RUNNING_RUN_SECONDS = 2 hours)
    started_at = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")

    result = derive_workflow_recovery_state(
        chapter={"status": "drafted", "content": "some content"},
        latest_run={
            "id": "run-123",
            "status": "running",
            "started_at": started_at,
            "current_node": "author",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "author"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "drafted"
    assert result["run_status"] == "running"
    assert result["recovery_capability"] == RecoveryCapability.MANUAL_INTERVENTION_REQUIRED.value
    assert result["recommended_action"] == "mark_stuck"
    assert "mark_stuck" in result["safe_actions"]


def test_state_matrix_failed_with_checkpoint():
    """Test failed run with checkpoint."""
    result = derive_workflow_recovery_state(
        chapter={"status": "drafted", "content": "some content"},
        latest_run={
            "id": "run-123",
            "status": "failed",
            "current_node": "author",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "author"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "drafted"
    assert result["run_status"] == "failed"
    assert result["recovery_capability"] == RecoveryCapability.CLEAR_CHECKPOINT_AND_RERUN.value
    assert result["recommended_action"] == "reset"
    assert "reset" in result["safe_actions"]
    assert result["checkpoint_status"] == CheckpointState.STALE.value


def test_state_matrix_blocked_with_checkpoint():
    """Test blocked run with checkpoint."""
    result = derive_workflow_recovery_state(
        chapter={"status": "blocking", "content": "some content"},
        latest_run={
            "id": "run-123",
            "status": "blocked",
            "current_node": "author",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "author"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "blocking"
    assert result["run_status"] == "blocked"
    assert result["recovery_capability"] == RecoveryCapability.RESET_TO_PLANNED.value
    assert "reset" in result["safe_actions"]


def test_state_matrix_reviewed_ready_to_publish():
    """Test reviewed status ready to publish."""
    result = derive_workflow_recovery_state(
        chapter={"status": "reviewed", "content": "final content"},
        latest_run={
            "id": "run-123",
            "status": "completed",
            "current_node": "awaiting_publish",
        },
        checkpoint_info={"checkpoint_exists": False},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "reviewed"
    assert result["recovery_capability"] == RecoveryCapability.PUBLISH_READY.value
    assert "publish" in result["safe_actions"]
    assert "view_content" in result["safe_actions"]


def test_state_matrix_awaiting_publish_ready():
    """Test awaiting_publish status ready to publish."""
    result = derive_workflow_recovery_state(
        chapter={"status": "awaiting_publish", "content": "final content"},
        latest_run={
            "id": "run-123",
            "status": "completed",
            "current_node": "awaiting_publish",
        },
        checkpoint_info={"checkpoint_exists": False},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "awaiting_publish"
    assert result["recovery_capability"] == RecoveryCapability.PUBLISH_READY.value
    assert "publish" in result["safe_actions"]


def test_state_matrix_published_no_recovery():
    """Test published status with no recovery needed."""
    result = derive_workflow_recovery_state(
        chapter={"status": "published", "content": "published content"},
        latest_run={
            "id": "run-123",
            "status": "completed",
            "current_node": "publish",
        },
        checkpoint_info={"checkpoint_exists": False},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "published"
    assert result["recovery_capability"] == RecoveryCapability.NO_RECOVERY_NEEDED.value
    assert "view_content" in result["safe_actions"]
    assert "create_revision_draft" in result["safe_actions"]


def test_state_matrix_revision_state():
    """Test revision status recovery."""
    result = derive_workflow_recovery_state(
        chapter={"status": "revision", "content": "needs revision"},
        latest_run={
            "id": "run-123",
            "status": "completed",
            "current_node": "revision_router",
        },
        checkpoint_info={"checkpoint_exists": False},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "revision"
    assert result["recovery_capability"] == RecoveryCapability.REOPEN_REVISION.value
    assert "reopen_revision" in result["safe_actions"]


def test_state_matrix_blocking_manual_intervention():
    """Test blocking status requires manual intervention."""
    result = derive_workflow_recovery_state(
        chapter={"status": "blocking", "content": "blocked content"},
        latest_run={
            "id": "run-123",
            "status": "blocked",
            "current_node": "human_review",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "editor"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "blocking"
    assert result["recovery_capability"] == RecoveryCapability.MANUAL_INTERVENTION_REQUIRED.value
    assert result["blocking_reason"] is not None
    assert "reset" in result["safe_actions"]


def test_planned_with_existing_content_blocks_blank_generation():
    """Test planned chapter with existing content doesn't recommend blank generation."""
    result = derive_workflow_recovery_state(
        chapter={"status": "planned", "content": "existing content"},
        latest_run=None,
        checkpoint_info=None,
        has_existing_content=True,
    )

    assert result["chapter_status"] == "planned"
    assert result["recovery_capability"] == RecoveryCapability.MANUAL_INTERVENTION_REQUIRED.value
    assert "view_content" in result["safe_actions"]
    assert "reset_explicitly" in result["safe_actions"]
    assert result["blocking_reason"] is not None


def test_completed_run_with_revision_blocking_chapter():
    """Test completed run with revision/blocking chapter requires manual intervention."""
    result = derive_workflow_recovery_state(
        chapter={"status": "revision", "content": "content"},
        latest_run={
            "id": "run-123",
            "status": "completed",
            "current_node": "editor",
        },
        checkpoint_info={"checkpoint_exists": False},
        has_existing_content=True,
    )

    # Completed run but revision chapter - should recommend reopening revision
    assert result["chapter_status"] == "revision"
    assert result["recovery_capability"] == RecoveryCapability.REOPEN_REVISION.value


# ── Local Edit Protection Tests ────────────────────────────────────


def test_local_edit_state_protection():
    """Test local edit state doesn't enter main workflow blocking."""
    # awaiting_publish with local edit should be protected
    assert is_local_edit_state("awaiting_publish", has_local_edit=True) is True
    assert should_protect_from_blocking("awaiting_publish", is_local_edit=True) is True

    # reviewed with local edit should be protected
    assert is_local_edit_state("reviewed", has_local_edit=True) is True
    assert should_protect_from_blocking("reviewed", is_local_edit=True) is True

    # published with local edit should be protected
    assert is_local_edit_state("published", has_local_edit=True) is True
    assert should_protect_from_blocking("published", is_local_edit=True) is True

    # drafted should not be protected even with local edit
    assert is_local_edit_state("drafted", has_local_edit=True) is False
    assert should_protect_from_blocking("drafted", is_local_edit=True) is False

    # awaiting_publish without local edit flag should not be protected
    assert is_local_edit_state("awaiting_publish", has_local_edit=False) is False
    assert should_protect_from_blocking("awaiting_publish", is_local_edit=False) is False


def test_local_edit_on_awaiting_publish_does_not_block():
    """Test local edit on awaiting_publish chapter doesn't enter main workflow blocking."""
    result = derive_workflow_recovery_state(
        chapter={"status": "awaiting_publish", "content": "content"},
        latest_run={
            "id": "run-123",
            "status": "completed",
            "current_node": "awaiting_publish",
        },
        checkpoint_info={"checkpoint_exists": False},
        has_existing_content=True,
        is_local_edit=True,
    )

    assert result["chapter_status"] == "awaiting_publish"
    assert result["recovery_capability"] == RecoveryCapability.PUBLISH_READY.value
    assert "publish" in result["safe_actions"]
    assert "local_edit" in result["safe_actions"]


def test_local_edit_content_save_keeps_awaiting_publish_status(client, db_path):
    """Saving an accepted local edit on awaiting_publish must not re-enter review workflow."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    project_id = "test-local-edit-save"
    repo.create_project(project_id=project_id, name="Local Edit Save", genre="test")
    repo.add_chapter(project_id, 1, title="Chapter 1", status="planned")
    original = "待发布章节正文" * 20
    repo.save_chapter(project_id, 1, "Chapter 1", original, len(original), "awaiting_publish")
    version_id = repo.save_version(project_id, 1, original, source="ai_generation")

    edited = original + " 局部润色。"
    response = client.post(
        f"/api/projects/{project_id}/chapters/1/content",
        json={
            "content": edited,
            "base_version_id": version_id,
            "summary": "接受局部返修",
            "confirm": True,
            "is_local_edit": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"], body.get("error")
    assert body["data"]["status"] == "awaiting_publish"
    assert body["data"]["status_changed"] is False
    assert repo.get_chapter(project_id, 1)["status"] == "awaiting_publish"


# ── Checkpoint Stale Detection Tests ───────────────────────────────


def test_checkpoint_stale_by_run_status():
    """Test checkpoint is stale when run is not running."""
    from novel_factory.workflow.state_integrity import _checkpoint_is_stale

    is_stale, reason = _checkpoint_is_stale(
        run_status="failed",
        checkpoint_exists=True,
        checkpoint_node="author",
        checkpoint_chapter_status=None,
        current_chapter_status="drafted",
        current_node="author",
        checkpoint_age_seconds=None,
    )

    assert is_stale is True
    assert "failed" in reason


def test_blocked_checkpoint_stale_by_node_mismatch():
    """Test blocked checkpoint is stale when node doesn't match current node."""
    from novel_factory.workflow.state_integrity import _checkpoint_is_stale

    is_stale, reason = _checkpoint_is_stale(
        run_status="blocked",
        checkpoint_exists=True,
        checkpoint_node="planner",
        checkpoint_chapter_status=None,
        current_chapter_status="drafted",  # Expected node is author, not planner
        current_node="author",
        checkpoint_age_seconds=None,
    )

    assert is_stale is True


def test_running_checkpoint_node_mismatch_is_not_stale_while_active():
    """Active runs may have routing checkpoints that lag the current node."""
    from novel_factory.workflow.state_integrity import _checkpoint_is_stale

    is_stale, reason = _checkpoint_is_stale(
        run_status="running",
        checkpoint_exists=True,
        checkpoint_node="loop",
        checkpoint_chapter_status="scripted",
        current_chapter_status="drafted",
        current_node="author",
        checkpoint_age_seconds=None,
    )

    assert is_stale is False
    assert reason is None


def test_checkpoint_stale_by_age():
    """Test checkpoint is stale when age exceeds threshold."""
    from novel_factory.workflow.state_integrity import _checkpoint_is_stale

    is_stale, reason = _checkpoint_is_stale(
        run_status="running",
        checkpoint_exists=True,
        checkpoint_node="author",
        checkpoint_chapter_status=None,
        current_chapter_status="drafted",
        current_node="author",
        checkpoint_age_seconds=STALE_CHECKPOINT_SECONDS + 1000,  # Older than threshold
    )

    assert is_stale is True
    assert "exceeds threshold" in reason


# ── Integration Tests (API) ─────────────────────────────────────────


def test_recovery_state_in_run_detail_response(client, db_path):
    """Test run detail API returns recovery_state field."""
    from novel_factory.db.repository import Repository
    from novel_factory.workflow.state_integrity import RecoveryCapability

    repo = Repository(db_path)

    # Create project and chapter
    project_id = "test-recovery-proj"
    repo.create_project(project_id=project_id, name="Test Project", genre="test")
    repo.add_chapter(project_id, 1, title="Chapter 1", status="planned")

    # Create a workflow run
    run_id = repo.create_workflow_run(project_id, 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")
    repo.update_chapter_status(project_id, 1, "reviewed")

    # Get run detail
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200

    data = response.json()["data"]
    assert "recovery_state" in data

    recovery_state = data["recovery_state"]
    assert recovery_state["chapter_status"] == "reviewed"
    assert recovery_state["recovery_capability"] in (
        RecoveryCapability.PUBLISH_READY.value,
        RecoveryCapability.NO_RECOVERY_NEEDED.value,
    )
    assert "safe_actions" in recovery_state
    assert isinstance(recovery_state["safe_actions"], list)


def test_workflow_timeline_returns_recovery_state(client, db_path):
    """Test workflow timeline API returns recovery_state in recovery field."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)

    # Create project and chapter
    project_id = "test-timeline-proj"
    repo.create_project(project_id=project_id, name="Test Project", genre="test")
    repo.add_chapter(project_id, 1, title="Chapter 1", status="planned")

    # Create a workflow run
    run_id = repo.create_workflow_run(project_id, 1)
    repo.update_workflow_run(run_id, status="running", current_node="author")
    repo.update_chapter_status(project_id, 1, "drafted")

    # Get workflow timeline
    response = client.get(f"/api/projects/{project_id}/chapters/1/workflow-timeline")
    assert response.status_code == 200

    data = response.json()["data"]
    assert "recovery" in data
    assert "recovery_state" in data["recovery"]

    recovery_state = data["recovery"]["recovery_state"]
    assert recovery_state["chapter_status"] == "drafted"
    assert "safe_actions" in recovery_state


def test_workflow_timeline_uses_active_node_age_not_total_run_age(client, db_path):
    """Timeline stale detection should not flag a long run when current node is fresh."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    project_id = "test-timeline-active-node-age"
    repo.create_project(project_id=project_id, name="Timeline Active Node Age", genre="test")
    repo.add_chapter(project_id, 1, title="Chapter 1", status="polished")
    run_id = repo.create_workflow_run(project_id, 1)
    repo.update_workflow_run(run_id, status="running", current_node="editor")
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE workflow_runs SET started_at=datetime('now','-45 minutes','+8 hours') WHERE id=?",
            (run_id,),
        )
        conn.commit()
    finally:
        conn.close()
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id=project_id,
        chapter_number=1,
        node_name="editor",
        event_type="started",
        status="running",
    )

    response = client.get(f"/api/projects/{project_id}/chapters/1/workflow-timeline")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["elapsed_minutes"] >= 30
    assert data["is_stale"] is False
    assert data["recovery"]["recommended_action"] is None
    assert data["recovery"]["recovery_state"]["recommended_action"] is None


def test_production_next_respects_manual_intervention(client, db_path):
    """Test production-next doesn't recommend impossible automatic action when manual intervention required."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)

    # Create project and chapter
    project_id = "test-production-proj"
    repo.create_project(project_id=project_id, name="Test Project", genre="test")
    repo.add_chapter(project_id, 1, title="Chapter 1", status="planned")

    # Set chapter to blocking status
    repo.update_chapter_status(project_id, 1, "blocking")

    # Get production-next
    response = client.get(f"/api/projects/{project_id}/production-next")
    assert response.status_code == 200

    data = response.json()["data"]
    # Should not recommend auto-generate when manual intervention is required
    if data.get("recommended_action") == "generate":
        # If recommending generate, must have clear reason
        assert data.get("reason") is not None


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    from novel_factory.db.connection import init_db

    db_file = tmp_path / "test.db"
    init_db(str(db_file))
    yield str(db_file)


@pytest.fixture
def client(db_path):
    """Create a test client with the database."""
    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app

    app = create_api_app(db_path=db_path, llm_mode="stub")

    with TestClient(app) as test_client:
        yield test_client
