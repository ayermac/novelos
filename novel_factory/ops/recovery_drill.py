"""Workflow recovery diagnostics for production readiness gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


TERMINAL_CHAPTER_STATUSES = {"reviewed", "awaiting_publish", "published"}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = str(value).replace("T", " ").replace("Z", "")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
        return parsed
    except Exception:
        return None


def _minutes_since(value: str | None, now: datetime | None = None) -> float | None:
    started = _parse_time(value)
    if not started:
        return None
    now = now or datetime.now(tz=timezone(timedelta(hours=8)))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone(timedelta(hours=8)))
    return max(0.0, round((now - started).total_seconds() / 60, 2))


def inspect_chapter_recovery(
    repo: Any,
    project_id: str,
    chapter_number: int,
    *,
    stale_minutes: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return safe recovery diagnosis for one chapter."""
    chapter = repo.get_chapter(project_id, chapter_number) or {}
    run = _latest_run(repo, project_id, chapter_number)
    running_tasks = _running_tasks(repo, project_id, chapter_number)

    chapter_status = str(chapter.get("status") or "unknown")
    run_status = str((run or {}).get("status") or "none")
    elapsed = _minutes_since((run or {}).get("started_at"), now=now)
    is_stale = run_status == "running" and elapsed is not None and elapsed >= stale_minutes
    terminal = chapter_status in TERMINAL_CHAPTER_STATUSES

    state = "ready"
    recommended_action = "none"
    safe_actions: list[str] = ["view_detail"]
    reason = "chapter has no active recovery issue"

    if run_status == "failed":
        state = "failed"
        recommended_action = "retry_failed_node"
        safe_actions += ["retry_node", "reset_to_planned"]
        reason = (run or {}).get("error_message") or "latest workflow run failed"
    elif run_status == "blocked" or chapter_status == "blocking":
        state = "blocked"
        recommended_action = "inspect_human_review"
        safe_actions += ["retry_node", "reset_to_planned"]
        reason = (run or {}).get("error_message") or "workflow is blocked"
    elif is_stale:
        state = "stale_running"
        recommended_action = "mark_stuck_blocked"
        safe_actions += ["mark_stuck_blocked", "reset_to_planned"]
        reason = f"workflow has been running for {elapsed} minutes"
    elif run_status == "running" and terminal:
        state = "terminal_with_running_run"
        recommended_action = "reconcile_terminal_run"
        safe_actions += ["reconcile_terminal_run"]
        reason = "chapter is terminal but latest run is still running"
    elif run_status == "running":
        state = "healthy_running"
        recommended_action = "wait"
        safe_actions += ["watch_timeline"]
        reason = "workflow is running and not stale"
    elif terminal:
        state = "terminal"
        recommended_action = "publish_or_archive"
        safe_actions += ["view_artifacts", "publish"]
        reason = f"chapter is {chapter_status}"

    return {
        "ok": state in {"ready", "terminal", "healthy_running"},
        "project_id": project_id,
        "chapter_number": chapter_number,
        "state": state,
        "recommended_action": recommended_action,
        "safe_actions": sorted(set(safe_actions)),
        "reason": reason,
        "chapter_status": chapter_status,
        "workflow_status": run_status,
        "run_id": (run or {}).get("id") or (run or {}).get("run_id"),
        "current_node": (run or {}).get("current_node"),
        "elapsed_minutes": elapsed,
        "running_task_count": len(running_tasks),
        "running_tasks": running_tasks[:10],
    }


def _latest_run(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any] | None:
    if hasattr(repo, "get_latest_workflow_run"):
        try:
            return repo.get_latest_workflow_run(project_id, chapter_number)
        except TypeError:
            pass
        except Exception:
            return None
    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT * FROM workflow_runs WHERE project_id=? AND chapter_number=? "
            "ORDER BY started_at DESC, id DESC LIMIT 1",
            (project_id, chapter_number),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _running_tasks(repo: Any, project_id: str, chapter_number: int) -> list[dict[str, Any]]:
    conn = repo._conn()
    try:
        rows = conn.execute(
            "SELECT id, task_type, agent_id, status, started_at, workflow_run_id "
            "FROM task_status WHERE project_id=? AND chapter_number=? AND status='running' "
            "ORDER BY started_at DESC LIMIT 20",
            (project_id, chapter_number),
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()
