"""Workflow state reconciliation helpers.

These helpers repair coarse workflow_run rows when durable chapter state and
fine-grained execution evidence already prove the workflow advanced further
than the run row says.
"""

from __future__ import annotations

from typing import Any


def reconcile_revision_running_workflows(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
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
