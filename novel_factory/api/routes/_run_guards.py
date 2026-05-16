"""Unified run guards for chapter generation entry points.

v5.5.15: All generation entries (POST /run/chapter, GET /run/chapter/stream,
auto-run generate_chapter/continue_next_chapter) must enforce the same
preconditions before starting a workflow.

This module provides a single check_chapter_run_guard() function that:
1. Rejects chapters that already have a running workflow_run
2. Rejects chapters in a terminal status (reviewed / awaiting_publish / published)
3. Rejects planned chapters that already contain content unless the latest
   recovery action explicitly reset that chapter for regeneration.

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
    Guard 3: CHAPTER_HAS_EXISTING_CONTENT — planned chapter already has content.
    Guard 4: CONTEXT_INCOMPLETE — project context missing (genesis/world/characters/outlines/instructions).
    """
    # Guard 1: Terminal status check. Terminal chapter state wins over stale
    # running workflow rows; reconcile first so UI/health endpoints stop
    # showing phantom work.
    chapter = repo.get_chapter(project_id, chapter_number)
    if chapter and chapter.get("status") == "revision":
        from ...workflow.reconciliation import reconcile_revision_running_workflows

        reconcile_revision_running_workflows(repo, project_id, chapter_number)
    elif chapter and chapter.get("status") in {"scripted", "drafted", "polished", "review"}:
        from ...workflow.reconciliation import reconcile_interrupted_running_workflows

        reconcile_interrupted_running_workflows(repo, project_id, chapter_number)

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

    # Guard 2: A planned chapter with content is not an empty generation slot.
    # This can happen after recovery reset: reset only clears workflow state and
    # preserves the author's current text. Starting generation directly would
    # make the UI look safe while risking an overwrite.
    if chapter and chapter.get("status") == "planned":
        content = (chapter.get("content") or "").strip()
        word_count = chapter.get("word_count") or 0
        if (content or word_count > 0) and not _has_explicit_reset_recovery(
            repo, project_id, chapter_number
        ):
            return RunGuardError(
                "CHAPTER_HAS_EXISTING_CONTENT",
                f"第 {chapter_number} 章已有正文内容，不能按空白 planned 章节直接生成。请先查看正文并决定编辑、回滚或显式重置。",
                details={
                    "chapter_status": chapter.get("status"),
                    "word_count": word_count,
                    "hint": "review_existing_content",
                },
            )

    # Guard 3: Running workflow check
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

    # Guard 4: Context completeness check
    # Projects must have approved genesis + world settings + characters + outlines + instructions
    # before any chapter workflow can start. This prevents users from accidentally generating
    # chapters without proper creative context.
    latest_genesis = repo.get_latest_genesis_run(project_id)
    has_approved_genesis = latest_genesis is not None and latest_genesis.get("status") == "approved"
    has_world = len(repo.list_world_settings(project_id)) > 0
    has_chars = len(repo.list_characters(project_id, include_inactive=True)) > 0
    has_outlines = len(repo.list_outlines(project_id)) > 0
    instruction = repo.get_instruction_by_chapter(project_id, chapter_number)
    has_instruction = instruction is not None and bool(instruction.get("objective"))

    if not has_approved_genesis:
        return RunGuardError(
            "CONTEXT_INCOMPLETE",
            "项目创世设定尚未批准。请先完成并批准创世设定，再补齐项目资料后生成章节。",
            details={
                "missing": ["genesis"],
                "hint": "generate_genesis",
            },
        )

    missing_context = []
    if not has_world:
        missing_context.append("世界观")
    if not has_chars:
        missing_context.append("角色")
    if not has_outlines:
        missing_context.append("大纲")
    if not has_instruction:
        missing_context.append(f"第{chapter_number}章写作指令")

    if missing_context:
        return RunGuardError(
            "CONTEXT_INCOMPLETE",
            f"项目资料不完整，缺少：{', '.join(missing_context)}。请先补齐资料后再生成章节。",
            details={
                "missing": missing_context,
                "hint": "generate_missing_context",
            },
        )

    return None


def _has_explicit_reset_recovery(repo, project_id: str, chapter_number: int) -> bool:
    """Return True when the latest recovery explicitly reset this chapter.

    A reset recovery is the user's explicit confirmation that preserved chapter
    text may be superseded by a new workflow attempt. Without this marker,
    planned+content is treated as suspicious preserved work and stays blocked.
    """
    try:
        runs = repo.get_workflow_runs_for_project(
            project_id,
            chapter_number=chapter_number,
            limit=5,
        )
    except Exception:
        return False
    return any(
        run.get("status") == "completed" and run.get("current_node") == "reset_recovery"
        for run in runs
    )
