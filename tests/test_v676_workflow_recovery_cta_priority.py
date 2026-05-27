"""Tests for v6.7.6 Workflow Recovery CTA Priority Fix.

Tests that blocked/failed run_status takes priority over terminal chapter statuses,
ensuring recovery actions are shown instead of publish when workflow is broken.
"""

import pytest
from datetime import datetime, timedelta

from novel_factory.workflow.state_integrity import (
    derive_workflow_recovery_state,
    RecoveryCapability,
    CheckpointState,
)


# ── v6.7.6: Blocked run + terminal chapter status ──────────────────


def test_blocked_run_with_awaiting_publish_shows_reset():
    """Blocked run should show reset even when chapter is awaiting_publish.

    This is the primary fix: previously awaiting_publish was treated as
    publish-ready, hiding the recovery actions.
    """
    result = derive_workflow_recovery_state(
        chapter={"status": "awaiting_publish", "content": "final content"},
        latest_run={
            "id": "run-123",
            "status": "blocked",
            "current_node": "memory_curator",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "memory_curator"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "awaiting_publish"
    assert result["run_status"] == "blocked"
    assert result["recovery_capability"] == RecoveryCapability.RESET_TO_PLANNED.value
    assert result["recommended_action"] == "reset"
    assert "reset" in result["safe_actions"]
    assert "view_content" in result["safe_actions"]
    assert "view_detail" in result["safe_actions"]
    # Should NOT have publish as recommended action
    assert result["recommended_action"] != "publish"


def test_blocked_run_with_reviewed_shows_reset():
    """Blocked run should show reset even when chapter is reviewed.

    Note: checkpoint_node="publisher" matches the expected node for reviewed status.
    checkpoint_node="editor" would be classified as STALE (node mismatch),
    which triggers MANUAL_INTERVENTION_REQUIRED instead of RESET_TO_PLANNED.
    """
    result = derive_workflow_recovery_state(
        chapter={"status": "reviewed", "content": "final content"},
        latest_run={
            "id": "run-123",
            "status": "blocked",
            "current_node": "publisher",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "publisher"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "reviewed"
    assert result["run_status"] == "blocked"
    assert result["recovery_capability"] == RecoveryCapability.RESET_TO_PLANNED.value
    assert result["recommended_action"] == "reset"
    assert "reset" in result["safe_actions"]
    assert result["recommended_action"] != "publish"


def test_blocked_run_with_published_shows_reset():
    """Blocked run should show reset even when chapter is published."""
    result = derive_workflow_recovery_state(
        chapter={"status": "published", "content": "published content"},
        latest_run={
            "id": "run-123",
            "status": "blocked",
            "current_node": "archive",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "archive"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "published"
    assert result["run_status"] == "blocked"
    assert result["recovery_capability"] == RecoveryCapability.RESET_TO_PLANNED.value
    assert result["recommended_action"] == "reset"


def test_failed_run_with_awaiting_publish_shows_reset():
    """Failed run should show reset even when chapter is awaiting_publish."""
    result = derive_workflow_recovery_state(
        chapter={"status": "awaiting_publish", "content": "final content"},
        latest_run={
            "id": "run-123",
            "status": "failed",
            "current_node": "memory_curator",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "memory_curator"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "awaiting_publish"
    assert result["run_status"] == "failed"
    assert result["recovery_capability"] == RecoveryCapability.CLEAR_CHECKPOINT_AND_RERUN.value
    assert result["recommended_action"] == "reset"
    assert "reset" in result["safe_actions"]
    assert result["recommended_action"] != "publish"


# ── Healthy terminal chapters still show publish ────────────────────


def test_completed_run_with_awaiting_publish_shows_publish():
    """Healthy completed run with awaiting_publish should still show publish."""
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
    assert result["run_status"] == "completed"
    assert result["recovery_capability"] == RecoveryCapability.PUBLISH_READY.value
    assert result["recommended_action"] == "publish"
    assert "publish" in result["safe_actions"]


def test_completed_run_with_reviewed_shows_publish():
    """Healthy completed run with reviewed should still show publish."""
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
    assert result["run_status"] == "completed"
    assert result["recovery_capability"] == RecoveryCapability.PUBLISH_READY.value
    assert result["recommended_action"] == "publish"


def test_no_run_with_awaiting_publish_shows_publish():
    """No run with awaiting_publish should still show publish."""
    result = derive_workflow_recovery_state(
        chapter={"status": "awaiting_publish", "content": "final content"},
        latest_run=None,
        checkpoint_info=None,
        has_existing_content=True,
    )

    assert result["chapter_status"] == "awaiting_publish"
    assert result["run_status"] is None
    assert result["recovery_capability"] == RecoveryCapability.PUBLISH_READY.value
    assert result["recommended_action"] == "publish"


# ── Running + stale + terminal chapter ──────────────────────────────


def test_running_stale_with_awaiting_publish_shows_mark_stuck():
    """Running stale run with awaiting_publish should show mark_stuck.

    Even though the chapter is in a terminal status, a stale running run
    indicates the workflow is stuck. Recovery actions take priority to
    prevent "publish" from masking a broken workflow.
    """
    now = datetime.utcnow() + timedelta(hours=8)
    # Run started 5 hours ago (beyond STALE_RUNNING_RUN_SECONDS = 2 hours)
    started_at = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")

    result = derive_workflow_recovery_state(
        chapter={"status": "awaiting_publish", "content": "final content"},
        latest_run={
            "id": "run-123",
            "status": "running",
            "started_at": started_at,
            "current_node": "memory_curator",
        },
        checkpoint_info={"checkpoint_exists": True, "checkpoint_node": "memory_curator"},
        has_existing_content=True,
    )

    assert result["chapter_status"] == "awaiting_publish"
    assert result["run_status"] == "running"
    assert result["recovery_capability"] == RecoveryCapability.MANUAL_INTERVENTION_REQUIRED.value
    assert result["recommended_action"] == "mark_stuck"
    assert "mark_stuck" in result["safe_actions"]
    assert result["recommended_action"] != "publish"


# ── Blocked run with stale checkpoint ───────────────────────────────


def test_blocked_run_stale_checkpoint_shows_reset():
    """Blocked run with stale checkpoint should show reset with manual intervention.

    Uses non-terminal chapter status "drafted" so the expected_node check
    (expected "author" vs actual "memory_curator") classifies checkpoint as STALE.
    Terminal statuses like awaiting_publish have no expected_node mapping,
    so they can't trigger the stale checkpoint classification via Rule 3.
    """
    result = derive_workflow_recovery_state(
        chapter={"status": "drafted", "content": "draft content"},
        latest_run={
            "id": "run-123",
            "status": "blocked",
            "current_node": "memory_curator",
        },
        checkpoint_info={
            "checkpoint_exists": True,
            "checkpoint_node": "memory_curator",
        },
        has_existing_content=True,
    )

    assert result["chapter_status"] == "drafted"
    assert result["run_status"] == "blocked"
    assert result["recovery_capability"] == RecoveryCapability.MANUAL_INTERVENTION_REQUIRED.value
    assert result["recommended_action"] == "reset"
    assert "reset" in result["safe_actions"]
