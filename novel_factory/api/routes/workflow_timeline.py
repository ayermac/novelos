"""Workflow timeline API for chapter-level observability (v5.8).

GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()

# Node label mapping (matches frontend state-labels.ts)
NODE_LABELS: dict[str, str] = {
    "health_check": "预检",
    "task_discovery": "任务识别",
    "planner": "规划",
    "screenwriter": "编剧",
    "author": "执笔",
    "polisher": "润色",
    "editor": "审核",
    "memory_curator": "记忆整理",
    "publisher": "发布",
    "publish": "发布",
    "awaiting_publish": "等待发布",
    "archive": "归档",
    "revision_router": "返修路由",
    "human_review": "人工审核",
}

# Artifact type label mapping
ARTIFACT_TYPE_LABELS: dict[str, str] = {
    "chapter_brief": "章节规划",
    "scene_plan": "章节场景规划",
    "draft": "章节初稿",
    "polished_draft": "润色稿",
    "polished_content": "润色稿",
    "review": "审核报告",
    "published_chapter": "发布记录",
    "memory_update": "记忆更新",
    "style_report": "风格报告",
    "fact_snapshot": "事实快照",
}

STUCK_THRESHOLD_MINUTES = 30


def _node_label(node_name: str | None) -> str:
    if not node_name:
        return "—"
    return NODE_LABELS.get(node_name, node_name)


def _artifact_label(artifact_type: str | None) -> str:
    if not artifact_type:
        return "产物"
    return ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type)


def _parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("T", " ").replace("Z", "")
        return datetime.fromisoformat(normalized).replace(tzinfo=timezone(timedelta(hours=8)))
    except Exception:
        return None


def _elapsed_minutes_since(value: str | None) -> float | None:
    started = _parse_db_datetime(value)
    if not started:
        return None
    now = datetime.now(tz=timezone(timedelta(hours=8)))
    return max(0.0, (now - started).total_seconds() / 60)


def _detect_stale(
    run_data: dict | None,
    timeout_minutes: int = STUCK_THRESHOLD_MINUTES,
) -> dict[str, Any]:
    if not run_data or run_data.get("status") != "running":
        return {"is_stale": False, "reason": None, "elapsed_minutes": None}
    elapsed = _elapsed_minutes_since(run_data.get("started_at"))
    is_stale = elapsed is not None and elapsed >= timeout_minutes
    reason = None
    if is_stale:
        reason = (
            f"运行已超过 {timeout_minutes} 分钟仍处于 running，"
            "可先标记为阻塞再执行恢复。"
        )
    return {
        "is_stale": is_stale,
        "reason": reason,
        "elapsed_minutes": elapsed,
    }


def _build_recovery(
    run_data: dict | None,
    chapter_status: str | None,
    timeout_minutes: int = STUCK_THRESHOLD_MINUTES,
) -> dict[str, Any]:
    stale_info = _detect_stale(run_data, timeout_minutes)
    is_stale = stale_info["is_stale"]
    chapter_status = chapter_status or "unknown"
    terminal_statuses = {"reviewed", "awaiting_publish", "published"}

    recommended_action = None
    reason = None
    safe_actions: list[dict] = []

    if chapter_status in terminal_statuses:
        safe_actions.append({"key": "view_artifacts", "label": "查看产物", "safe": True})
        if is_stale:
            recommended_action = "mark_stuck"
            reason = "终态章节仍有运行中工作流，建议标记为阻塞。"
            safe_actions.append({"key": "mark_stuck", "label": "标记为阻塞", "safe": True})
    elif is_stale:
        recommended_action = "mark_stuck"
        reason = stale_info["reason"]
        safe_actions.extend([
            {"key": "view_artifacts", "label": "查看产物", "safe": True},
            {"key": "mark_stuck", "label": "标记为阻塞", "safe": True},
            {"key": "reset_chapter", "label": "清除阻塞并重置", "safe": True, "note": "保留当前正文和版本"},
        ])
    elif chapter_status in ("blocking", "revision"):
        recommended_action = "reset_chapter"
        reason = "章节处于阻塞/返修状态，可清除阻塞并重置。"
        safe_actions.extend([
            {"key": "view_artifacts", "label": "查看产物", "safe": True},
            {"key": "reset_chapter", "label": "清除阻塞并重置", "safe": True, "note": "保留当前正文和版本"},
        ])

    return {
        "recommended_action": recommended_action,
        "reason": reason,
        "safe_actions": safe_actions,
    }


def _build_node_timeline(
    events: list[dict],
    artifacts: list[dict],
) -> list[dict]:
    """Build node timeline from workflow_node_events.

    Groups events by node_name and derives status, duration, messages, artifacts.
    """
    # Group events by node_name
    node_events: dict[str, list[dict]] = {}
    for ev in events:
        name = ev.get("node_name", "")
        if not name:
            continue
        node_events.setdefault(name, []).append(ev)

    # Group artifacts by agent_id
    node_artifacts: dict[str, list[dict]] = {}
    for art in artifacts:
        aid = art.get("agent_id", "")
        if aid:
            node_artifacts.setdefault(aid, []).append(art)

    nodes = []
    for node_name, evs in node_events.items():
        # Sort by created_at
        evs = sorted(evs, key=lambda e: e.get("created_at") or "")
        started_ev = next((e for e in evs if e.get("event_type") == "started"), None)
        completed_ev = next((e for e in evs if e.get("event_type") == "completed"), None)
        failed_ev = next((e for e in evs if e.get("event_type") == "failed"), None)

        if failed_ev:
            status = "failed"
        elif completed_ev:
            status = "completed"
        elif started_ev:
            status = "running"
        else:
            status = "pending"

        started_at = started_ev.get("created_at") if started_ev else None
        completed_at = (completed_ev or failed_ev).get("created_at") if (completed_ev or failed_ev) else None

        duration_ms = None
        if started_at and completed_at:
            s = _parse_db_datetime(started_at)
            c = _parse_db_datetime(completed_at)
            if s and c:
                duration_ms = int((c - s).total_seconds() * 1000)

        messages = []
        for e in evs:
            msg = e.get("message")
            if msg and msg not in messages:
                messages.append(msg)

        # Build artifact refs
        arts = node_artifacts.get(node_name, [])
        artifact_refs = []
        for art in arts:
            artifact_refs.append({
                "type": art.get("artifact_type", ""),
                "label": _artifact_label(art.get("artifact_type")),
                "artifact_id": art.get("id", ""),
            })

        nodes.append({
            "node_name": node_name,
            "label": _node_label(node_name),
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "messages": messages,
            "artifacts": artifact_refs,
        })

    return nodes


@router.get("/projects/{project_id}/chapters/{chapter_number}/workflow-timeline")
async def get_workflow_timeline(
    request: Request,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
) -> EnvelopeResponse:
    """Get workflow timeline for a chapter.

    Returns node-level event timeline, run status, stale detection,
    and recovery recommendations.
    """
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        timeout_minutes = settings.workflow.task_timeout_minutes

        # Verify chapter exists
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        # Find target run
        target_run: dict | None = None
        if run_id:
            runs = repo.get_workflow_runs_for_project(
                project_id, chapter_number=chapter_number, limit=1
            )
            # Filter by run_id
            for r in runs:
                if r.get("id") == run_id or r.get("run_id") == run_id:
                    target_run = r
                    break
            if not target_run:
                # Direct lookup fallback
                conn = repo._conn()
                try:
                    row = conn.execute(
                        "SELECT * FROM workflow_runs WHERE id=? AND project_id=? AND chapter_number=?",
                        (run_id, project_id, chapter_number),
                    ).fetchone()
                    target_run = dict(row) if row else None
                finally:
                    conn.close()
        else:
            # Latest run for this chapter
            runs = repo.get_workflow_runs_for_project(
                project_id, chapter_number=chapter_number, limit=1
            )
            if runs:
                target_run = runs[0]

        # Reconcile terminal chapter with running run (same logic as runs.py)
        if (
            target_run
            and target_run.get("status") == "running"
            and chapter.get("status") in ("reviewed", "awaiting_publish", "published")
            and hasattr(repo, "reconcile_terminal_chapter_running_workflows")
        ):
            reconciliation = repo.reconcile_terminal_chapter_running_workflows(
                project_id=project_id,
                chapter_number=chapter_number,
                run_id=target_run.get("id") or target_run.get("run_id"),
            )
            if reconciliation.get("runs"):
                # Refresh run data
                runs = repo.get_workflow_runs_for_project(
                    project_id, chapter_number=chapter_number, limit=1
                )
                if runs:
                    target_run = runs[0]

        # No run -> empty timeline
        if not target_run:
            return envelope_response({
                "project_id": project_id,
                "chapter_number": chapter_number,
                "run_id": None,
                "run_status": None,
                "current_node": None,
                "started_at": None,
                "elapsed_minutes": None,
                "is_stale": False,
                "recovery": {
                    "recommended_action": None,
                    "reason": None,
                    "safe_actions": [],
                },
                "nodes": [],
            })

        run_id_str = target_run.get("id") or target_run.get("run_id", "")
        run_status = target_run.get("status", "unknown")
        current_node = target_run.get("current_node")
        started_at = target_run.get("started_at")

        stale_info = _detect_stale(target_run, timeout_minutes)
        recovery = _build_recovery(target_run, chapter.get("status"), timeout_minutes)

        # Fetch node events
        events = repo.get_workflow_node_events(run_id_str)

        # Fetch artifacts for this run
        artifacts: list[dict] = []
        try:
            artifacts = repo.get_artifacts_for_chapter(
                project_id, chapter_number, workflow_run_id=run_id_str
            )
            if not artifacts:
                # Fallback: legacy artifacts without run_id
                artifacts = repo.get_artifacts_for_chapter(project_id, chapter_number)
        except Exception:
            artifacts = []

        nodes = _build_node_timeline(events, artifacts)

        return envelope_response({
            "project_id": project_id,
            "chapter_number": chapter_number,
            "run_id": run_id_str,
            "run_status": run_status,
            "current_node": current_node,
            "started_at": started_at,
            "elapsed_minutes": stale_info.get("elapsed_minutes"),
            "is_stale": stale_info.get("is_stale", False),
            "recovery": recovery,
            "nodes": nodes,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取工作流时间线失败: {str(e)}")
