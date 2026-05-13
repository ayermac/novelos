"""Unified run guards for chapter generation entry points.

v5.5.15: All generation entries (POST /run/chapter, GET /run/chapter/stream,
auto-run generate_chapter/continue_next_chapter) must enforce the same
preconditions before starting a workflow.

This module provides a single check_chapter_run_guard() function that:
1. Rejects chapters that already have a running workflow_run
2. Rejects chapters in a terminal status (reviewed / awaiting_publish / published)

Callers should use this instead of ad-hoc inline checks.
"""

from __future__ import annotations

from typing import Any

# Chapters in these statuses have completed the production pipeline
# and must not be re-run without an explicit reset.
TERMINAL_STATUSES = frozenset({"reviewed", "awaiting_publish", "published"})


class RunGuardError(Exception):
    """Raised when a chapter generation request is blocked by a guard."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def check_chapter_run_guard(repo, project_id: str, chapter_number: int) -> RunGuardError | None:
    """Check whether a chapter can safely start a new generation run.

    Returns a RunGuardError if the chapter should NOT be generated,
    or None if the chapter is safe to generate.

    Guard 1: WORKFLOW_ALREADY_RUNNING — a running workflow_run already exists.
    Guard 2: CHAPTER_ALREADY_COMPLETED — the chapter is in a terminal status.
    """
    # Guard 1: Terminal status check. Terminal chapter state wins over stale
    # running workflow rows; reconcile first so UI/health endpoints stop
    # showing phantom work.
    chapter = repo.get_chapter(project_id, chapter_number)
    if chapter and chapter.get("status") in TERMINAL_STATUSES:
        if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
            repo.reconcile_terminal_chapter_running_workflows(
                project_id=project_id,
                chapter_number=chapter_number,
            )
        return RunGuardError(
            "CHAPTER_ALREADY_COMPLETED",
            f"第 {chapter_number} 章已处于终态（{chapter.get('status')}），不能重复启动生成。如需重新生成，请先重置章节。",
            details={
                "chapter_status": chapter.get("status"),
                "hint": "reset_chapter",
            },
        )

    # Guard 2: Running workflow check
    existing_runs = repo.get_workflow_runs_for_project(
        project_id, chapter_number=chapter_number, limit=5
    )
    running_runs = [r for r in existing_runs if r.get("status") == "running"]
    if running_runs:
        running_run = running_runs[0]
        return RunGuardError(
            "WORKFLOW_ALREADY_RUNNING",
            f"第 {chapter_number} 章已有正在运行的工作流，不能重复启动生成",
            details={
                "run_id": running_run.get("id"),
                "current_node": running_run.get("current_node"),
                "started_at": running_run.get("started_at"),
            },
        )

    return None
