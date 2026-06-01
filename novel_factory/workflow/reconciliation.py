"""Workflow state reconciliation helpers.

These helpers repair coarse workflow_run rows when durable chapter state and
fine-grained execution evidence already prove the workflow advanced further
than the run row says.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


ACTIVE_RUN_RECONCILE_GRACE_SECONDS = 120

_TERMINAL_PLOT_STATUSES = ("resolved", "abandoned")


def reconcile_revision_running_workflows(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
    min_quiet_seconds: int = ACTIVE_RUN_RECONCILE_GRACE_SECONDS,
) -> dict[str, Any]:
    """Close orphaned running/editor runs whose editor already returned revision.

    Real-mode SSE runs can be interrupted after an agent finishes but before the
    next deterministic routing node is executed. When the chapter is already in
    ``revision`` and editor evidence exists, keeping the run at
    ``running/editor`` is misleading and blocks the next repair run. Mark it as
    completed at ``revision_router`` so the next invocation resumes from DB
    truth: chapter status ``revision`` and the persisted review target.
    """
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter or chapter.get("status") != "revision":
        return {"reconciled": 0, "runs": []}

    runs = _candidate_runs(repo, project_id, chapter_number, run_id)
    reconciled: list[dict[str, Any]] = []
    for run in runs:
        rid = run.get("id") or run.get("run_id")
        if not rid:
            continue
        if run.get("status") != "running" or run.get("current_node") != "editor":
            continue
        if not _has_editor_completion_evidence(repo, rid):
            continue
        if not _run_has_quiet_period(repo, run, min_quiet_seconds):
            continue

        repo.update_workflow_run(
            rid,
            status="completed",
            current_node="revision_router",
            clear_error=True,
        )
        _ensure_revision_router_events(repo, rid, project_id, chapter_number)
        reconciled.append({
            "run_id": rid,
            "from_node": "editor",
            "to_node": "revision_router",
            "chapter_status": "revision",
        })

    return {"reconciled": len(reconciled), "runs": reconciled}


def reconcile_interrupted_running_workflows(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
    min_quiet_seconds: int = ACTIVE_RUN_RECONCILE_GRACE_SECONDS,
) -> dict[str, Any]:
    """Close interrupted partial runs after a completed stage boundary.

    The chapter status is the durable source of truth. If an SSE execution is
    interrupted after an agent has successfully committed its output but before
    LangGraph starts the next node, the run row remains ``running`` and blocks
    the author from continuing. Close only when the completed node exactly
    matches the current durable chapter status.
    """
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter:
        return {"reconciled": 0, "runs": []}

    status_to_completed_node = {
        "scripted": "screenwriter",
        "drafted": "author",
        "polished": "polisher",
        "review": "polisher",
    }
    expected_node = status_to_completed_node.get(chapter.get("status"))
    if not expected_node:
        return {"reconciled": 0, "runs": []}

    runs = _candidate_runs(repo, project_id, chapter_number, run_id)
    reconciled: list[dict[str, Any]] = []
    for run in runs:
        rid = run.get("id") or run.get("run_id")
        if not rid:
            continue
        if run.get("status") != "running" or run.get("current_node") != expected_node:
            continue
        if not _has_node_completion_evidence(repo, rid, expected_node):
            continue
        if not _run_has_quiet_period(repo, run, min_quiet_seconds):
            continue
        if _has_later_node_started(repo, rid, expected_node):
            continue

        repo.update_workflow_run(
            rid,
            status="completed",
            current_node=expected_node,
            clear_error=True,
        )
        reconciled.append({
            "run_id": rid,
            "closed_at_node": expected_node,
            "chapter_status": chapter.get("status"),
            "reason": "interrupted_after_completed_stage",
        })

    return {"reconciled": len(reconciled), "runs": reconciled}


def _parse_workflow_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _run_has_quiet_period(repo: Any, run: dict[str, Any], min_quiet_seconds: int) -> bool:
    """Return True only after a running row has been inactive long enough.

    Timeline/run-guard reconciliation is allowed to close genuinely orphaned
    runs, but must not race an active background workflow between a completed
    node and the next LangGraph node start.
    """
    run_id = run.get("id") or run.get("run_id")
    latest_at = _parse_workflow_timestamp(run.get("started_at"))
    if run_id:
        for event in _run_activity_events(repo, str(run_id)):
            event_at = _parse_workflow_timestamp(event.get("created_at"))
            if event_at and (latest_at is None or event_at > latest_at):
                latest_at = event_at
    if latest_at is None:
        return False

    now_local = datetime.utcnow() + timedelta(hours=8)
    return (now_local - latest_at).total_seconds() >= min_quiet_seconds


def _run_activity_events(repo: Any, run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        events.extend(repo.get_workflow_node_events(run_id))
    except Exception:
        pass
    try:
        events.extend(repo.get_workflow_execution_events(run_id))
    except Exception:
        pass
    return events


def _candidate_runs(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str | None,
) -> list[dict[str, Any]]:
    if not run_id:
        return repo.get_workflow_runs_for_project(
            project_id,
            chapter_number=chapter_number,
            limit=5,
        )

    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT * FROM workflow_runs WHERE id=? AND project_id=? AND chapter_number=?",
            (run_id, project_id, chapter_number),
        ).fetchone()
        if not row:
            return []
        from ..db.connection import row_to_dict

        data = row_to_dict(row)
        data["run_id"] = data.get("id")
        return [data]
    finally:
        conn.close()


def _has_editor_completion_evidence(repo: Any, run_id: str) -> bool:
    return _has_node_completion_evidence(repo, run_id, "editor")


def _has_node_completion_evidence(repo: Any, run_id: str, node_name: str) -> bool:
    for event_type in ("evidence_verified", "llm_completed", "artifact_saved"):
        try:
            event = repo.get_latest_workflow_execution_event(
                run_id,
                node_name=node_name,
                event_type=event_type,
            )
        except Exception:
            event = None
        if event:
            return True
    return False


def _has_later_node_started(repo: Any, run_id: str, node_name: str) -> bool:
    order = ["planner", "screenwriter", "author", "polisher", "editor", "memory_curator", "awaiting_publish", "publisher", "archive"]
    try:
        node_index = order.index(node_name)
    except ValueError:
        return False
    later_nodes = set(order[node_index + 1 :])
    try:
        events = repo.get_workflow_node_events(run_id)
    except Exception:
        events = []
    return any(
        event.get("node_name") in later_nodes and event.get("event_type") == "started"
        for event in events
    )


def _ensure_revision_router_events(
    repo: Any,
    run_id: str,
    project_id: str,
    chapter_number: int,
) -> None:
    try:
        events = repo.get_workflow_node_events(run_id)
    except Exception:
        events = []
    if any(event.get("node_name") == "revision_router" for event in events):
        return
    try:
        repo.create_workflow_node_event(
            run_id,
            project_id,
            chapter_number,
            "revision_router",
            "started",
            status="running",
            message="进入返修路由",
        )
        repo.create_workflow_node_event(
            run_id,
            project_id,
            chapter_number,
            "revision_router",
            "completed",
            status="completed",
            message="返修路由已确认，等待下一轮返修执行",
        )
    except Exception:
        # Reconciliation must never break user-facing reads or run guards.
        return


def _parse_plot_codes(raw: Any) -> list[str]:
    """Parse a plots_to_resolve field (JSON list or comma text) into codes."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: comma/space separated
    return [tok.strip() for tok in text.replace("，", ",").split(",") if tok.strip()]


def reconcile_plot_resolution(
    repo: Any,
    project_id: str,
    chapter_number: int,
) -> dict[str, Any]:
    """v6.8.3: Deterministically resolve plot holes a chapter planned to resolve.

    A plot is auto-resolved when BOTH conditions hold:
      1. Its code appears in the chapter instruction's ``plots_to_resolve``.
      2. That same code literally appears in the published chapter content
         (hard evidence the foreshadow was actually paid off in the prose).

    This is a safety net independent of the LLM MemoryCurator: even if the
    curator never emits a ``resolve`` patch, a planned-and-paid-off plot still
    gets marked resolved. It is a no-op when the plot is already terminal.

    Returns a dict ``{"resolved": [codes...]}``. Never raises — reconciliation
    must not break the workflow.
    """
    try:
        instruction = repo.get_instruction_by_chapter(project_id, chapter_number)
        if not instruction:
            return {"resolved": []}

        planned = _parse_plot_codes(instruction.get("plots_to_resolve"))
        if not planned:
            return {"resolved": []}

        chapter = repo.get_chapter(project_id, chapter_number)
        content = (chapter or {}).get("content") or ""

        plots = {
            str(p.get("code") or "").strip(): p
            for p in repo.list_plot_holes(project_id)
            if str(p.get("code") or "").strip()
        }

        resolved: list[str] = []
        for code in planned:
            plot = plots.get(code)
            if not plot:
                continue
            if plot.get("status") in _TERMINAL_PLOT_STATUSES:
                continue
            # Hard evidence: the plot code must appear in the chapter prose.
            if code not in content:
                continue
            repo.update_plot_hole(
                project_id,
                plot["id"],
                {"status": "resolved", "resolved_chapter": chapter_number},
            )
            resolved.append(code)

        if resolved:
            logger.info(
                "reconcile_plot_resolution: auto-resolved %s for %s ch%d",
                resolved, project_id, chapter_number,
            )
        return {"resolved": resolved}
    except Exception:
        logger.debug(
            "reconcile_plot_resolution failed for %s ch%s",
            project_id, chapter_number,
            exc_info=True,
        )
        return {"resolved": []}
