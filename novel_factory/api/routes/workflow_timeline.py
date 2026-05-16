"""Workflow timeline API for chapter-level observability (v5.8).

GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-stream (v6.1 SSE)
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from starlette.responses import StreamingResponse

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ...workflow.graph import get_canonical_workflow_nodes

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


def _get_workflow_run_by_id(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str,
) -> dict | None:
    """Fetch one workflow run by id without depending on recent-run limits."""
    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT * FROM workflow_runs WHERE id=? AND project_id=? AND chapter_number=?",
            (run_id, project_id, chapter_number),
        ).fetchone()
        if not row:
            return None
        from ...db.connection import row_to_dict

        data = row_to_dict(row)
        data["run_id"] = data.get("id")
        return data
    finally:
        conn.close()


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
    retry_target = _node_retry_target(run_data.get("current_node") if run_data else None)

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
        recommended_action = "retry_node" if retry_target else "reset_chapter"
        reason = (
            f"章节处于阻塞/返修状态，可保留已有产物并重试{retry_target['label']}。"
            if retry_target
            else "章节处于阻塞/返修状态，可清除阻塞并重置。"
        )
        safe_actions.extend([
            {"key": "view_artifacts", "label": "查看产物", "safe": True},
        ])
        if retry_target:
            safe_actions.append({
                "key": "retry_node",
                "label": f"重试{retry_target['label']}",
                "safe": True,
                "note": f"恢复到 {retry_target['status']}，跳过已完成上游节点",
            })
        safe_actions.append({
            "key": "reset_chapter",
            "label": "清除阻塞并重置",
            "safe": True,
            "note": "回到 planned，完整重跑",
        })

    return {
        "recommended_action": recommended_action,
        "reason": reason,
        "safe_actions": safe_actions,
    }


def _node_retry_target(current_node: str | None) -> dict[str, str] | None:
    node = (current_node or "").strip()
    return {
        "author": {"label": "执笔", "status": "scripted"},
        "polisher": {"label": "润色", "status": "drafted"},
        "editor": {"label": "审核", "status": "polished"},
    }.get(node)


def _build_node_timeline(
    events: list[dict],
    artifacts: list[dict],
    run_status: str | None = None,
    current_node: str | None = None,
) -> list[dict]:
    """Build canonical node timeline overlaid with workflow_node_events.

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
    seen_nodes: set[str] = set()
    canonical_nodes = get_canonical_workflow_nodes()

    current_node_for_timeline = "publisher" if current_node == "publish" else current_node

    canonical_order = [node["node_name"] for node in canonical_nodes]

    def _is_before_current(node_name: str) -> bool:
        if not current_node_for_timeline:
            return False
        try:
            return canonical_order.index(node_name) < canonical_order.index(current_node_for_timeline)
        except ValueError:
            return False

    def build_node(base: dict[str, Any]) -> dict[str, Any]:
        node_name = base["node_name"]
        evs = node_events.get(node_name, [])
        # Sort by created_at
        evs = sorted(evs, key=lambda e: e.get("created_at") or "")
        started_events = [e for e in evs if e.get("event_type") == "started"]
        completed_events = [e for e in evs if e.get("event_type") == "completed"]
        failed_events = [e for e in evs if e.get("event_type") == "failed"]
        started_ev = started_events[-1] if started_events else None
        completed_ev = completed_events[-1] if completed_events else None
        failed_ev = failed_events[-1] if failed_events else None
        last_ev = evs[-1] if evs else None

        if last_ev and last_ev.get("event_type") == "failed":
            status = "failed"
        elif last_ev and last_ev.get("event_type") == "completed":
            status = "completed"
        elif last_ev and last_ev.get("event_type") == "started":
            status = "running"
        elif _is_before_current(node_name):
            status = "skipped"
        elif node_name == current_node_for_timeline and run_status in {"running", "blocked", "failed", "completed"}:
            status = {
                "running": "running",
                "blocked": "blocked",
                "failed": "failed",
                "completed": "completed",
            }[run_status]
        else:
            status = "pending"

        started_at = started_ev.get("created_at") if started_ev else None
        completed_at = None
        if status == "completed" and completed_ev:
            completed_at = completed_ev.get("created_at")
        elif status == "failed" and failed_ev:
            completed_at = failed_ev.get("created_at")

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
        if status == "skipped":
            if node_name == "planner" and current_node_for_timeline == "screenwriter":
                messages.append("已有人工章节指令，本轮跳过规划节点。")
            else:
                messages.append(f"本轮从{_node_label(current_node_for_timeline)}继续，跳过该节点。")

        # Build artifact refs
        arts = node_artifacts.get(node_name, [])
        artifact_refs = []
        for art in arts:
            artifact_refs.append({
                "type": art.get("artifact_type", ""),
                "label": _artifact_label(art.get("artifact_type")),
                "artifact_id": art.get("id", ""),
            })

        return {
            "node_name": node_name,
            "label": base.get("label") or _node_label(node_name),
            "node_group": base.get("node_group", "unknown"),
            "node_type": base.get("node_type", base.get("node_group", "unknown")),
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "messages": messages,
            "artifacts": artifact_refs,
        }

    for base in canonical_nodes:
        nodes.append(build_node(base))
        seen_nodes.add(base["node_name"])

    # Preserve visibility for any legacy/custom node events not in the canonical graph.
    for node_name in node_events:
        if node_name in seen_nodes:
            continue
        nodes.append(build_node({
            "node_name": node_name,
            "label": _node_label(node_name),
            "node_group": "unknown",
            "node_type": "unknown",
        }))

    return nodes


def _checkpoint_metadata(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any]:
    try:
        from ...workflow.checkpoint import inspect_checkpoint_thread
        return inspect_checkpoint_thread(repo.db_path, project_id, chapter_number)
    except Exception:
        return {
            "checkpoint_exists": False,
            "checkpoint_node": None,
            "current_node": None,
            "checkpoint_summary": None,
            "state_keys": [],
            "recovery_available": False,
        }


# ── v6.1: Execution events helpers ──────────────────────────────

def _group_execution_events_by_node(
    exec_events: list[dict],
) -> dict[str, list[dict]]:
    """Group execution events by node_name for timeline embedding."""
    grouped: dict[str, list[dict]] = {}
    for ev in exec_events:
        node = ev.get("node_name", "")
        if node:
            grouped.setdefault(node, []).append(ev)
    return grouped


def _build_node_evidence(node_exec_events: list[dict]) -> dict[str, Any]:
    """Build evidence summary for a node from its execution events."""
    if not node_exec_events:
        return {"has_evidence": False}

    has_warnings = False
    has_evidence_failure = False
    latest_summary = ""

    for ev in node_exec_events:
        etype = ev.get("event_type", "")
        status = ev.get("status", "info")
        if etype == "evidence_verified" and status == "fail":
            has_evidence_failure = True
        if status in ("warning", "error"):
            has_warnings = True

    # Latest meaningful summary
    for ev in reversed(node_exec_events):
        msg = ev.get("message", "")
        if msg and ev.get("event_type") in ("evidence_verified", "node_completed", "llm_completed"):
            latest_summary = msg
            break
    if not latest_summary and node_exec_events:
        latest_summary = node_exec_events[-1].get("message", "")

    return {
        "has_evidence": True,
        "has_warnings": has_warnings,
        "has_evidence_failure": has_evidence_failure,
        "latest_event_summary": latest_summary,
        "event_count": len(node_exec_events),
    }


def _embed_execution_events_in_nodes(
    nodes: list[dict],
    exec_events: list[dict],
) -> list[dict]:
    """Embed execution events and evidence into timeline nodes."""
    grouped = _group_execution_events_by_node(exec_events)
    for node in nodes:
        node_name = node.get("node_name", "")
        node_exec = grouped.get(node_name, [])
        if node_exec:
            node["events"] = [
                {
                    "id": ev.get("id"),
                    "event_type": ev.get("event_type"),
                    "status": ev.get("status"),
                    "message": ev.get("message"),
                    "payload": ev.get("payload", {}),
                    "token_count": ev.get("token_count"),
                    "latency_ms": ev.get("latency_ms"),
                    "created_at": ev.get("created_at"),
                }
                for ev in node_exec
            ]
            node["evidence"] = _build_node_evidence(node_exec)
        else:
            node["events"] = []
            node["evidence"] = {"has_evidence": False}
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

        if hasattr(repo, "reconcile_latest_blocked_runs_with_chapters"):
            repo.reconcile_latest_blocked_runs_with_chapters(
                project_id=project_id,
                chapter_number=chapter_number,
                run_id=run_id,
            )
            chapter = repo.get_chapter(project_id, chapter_number) or chapter

        if chapter.get("status") == "revision":
            from ...workflow.reconciliation import reconcile_revision_running_workflows

            reconcile_revision_running_workflows(
                repo,
                project_id,
                chapter_number,
                run_id=run_id,
            )
        elif chapter.get("status") in {"scripted", "drafted", "polished", "review"}:
            from ...workflow.reconciliation import reconcile_interrupted_running_workflows

            reconcile_interrupted_running_workflows(
                repo,
                project_id,
                chapter_number,
                run_id=run_id,
            )

        # Find target run
        target_run: dict | None = None
        if run_id:
            target_run = _get_workflow_run_by_id(repo, project_id, chapter_number, run_id)
        else:
            # Latest run for this chapter
            runs = repo.get_workflow_runs_for_project(
                project_id, chapter_number=chapter_number, limit=1
            )
            if runs:
                target_run = runs[0]

        if (
            not run_id
            and target_run
            and target_run.get("status") == "completed"
            and target_run.get("current_node") == "reset_recovery"
            and chapter.get("status") == "planned"
        ):
            target_run = None

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
                refreshed_id = target_run.get("id") or target_run.get("run_id")
                if refreshed_id:
                    target_run = _get_workflow_run_by_id(
                        repo, project_id, chapter_number, refreshed_id
                    ) or target_run

        # No run -> empty timeline
        if not target_run:
            checkpoint = _checkpoint_metadata(repo, project_id, chapter_number)
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
                "checkpoint": checkpoint,
                "nodes": _build_node_timeline([], []),
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
            if not artifacts and not events:
                # Fallback: legacy artifacts without run_id
                artifacts = repo.get_artifacts_for_chapter(project_id, chapter_number)
        except Exception:
            artifacts = []

        nodes = _build_node_timeline(
            events,
            artifacts,
            run_status=run_status,
            current_node=current_node,
        )

        # v6.1: Embed execution events into timeline nodes
        try:
            exec_events = repo.get_workflow_execution_events(run_id_str)
            nodes = _embed_execution_events_in_nodes(nodes, exec_events)
        except Exception:
            pass  # Backward compatible — execution events are additive

        checkpoint = _checkpoint_metadata(repo, project_id, chapter_number)

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
            "checkpoint": checkpoint,
            "nodes": nodes,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取工作流时间线失败: {str(e)}")


# ── v6.1: SSE Streaming Endpoint ───────────────────────────────

@router.get("/projects/{project_id}/chapters/{chapter_number}/workflow-stream")
async def workflow_stream_sse(
    request: Request,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
    since_id: int | None = None,
    replay: bool = True,
) -> StreamingResponse:
    """SSE endpoint for real-time workflow execution event streaming.

    Streams existing events first for replay, then polls DB for new events
    every 1-2 seconds while the target run is active.
    """
    from ..deps import get_repo

    repo = get_repo(request)

    # Find target run
    target_run: dict | None = None
    if run_id:
        target_run = _get_workflow_run_by_id(repo, project_id, chapter_number, run_id)
    else:
        runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=1)
        if runs:
            target_run = runs[0]

    run_id_str = target_run.get("id") or target_run.get("run_id", "") if target_run else ""
    run_status = target_run.get("status", "") if target_run else ""

    async def event_generator():
        last_event_id = since_id or 0

        # Replay existing events
        if replay and run_id_str:
            try:
                existing = repo.get_workflow_execution_events(run_id_str)
                for ev in existing:
                    if ev.get("id", 0) <= last_event_id:
                        continue
                    last_event_id = ev.get("id", 0)
                    payload = {
                        "id": ev.get("id"),
                        "run_id": run_id_str,
                        "node_name": ev.get("node_name"),
                        "agent_id": ev.get("agent_id"),
                        "event_type": ev.get("event_type"),
                        "status": ev.get("status"),
                        "message": ev.get("message"),
                        "payload": ev.get("payload", {}),
                        "token_count": ev.get("token_count"),
                        "latency_ms": ev.get("latency_ms"),
                        "created_at": ev.get("created_at"),
                    }
                    yield f"event: workflow_event\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception:
                pass

        # If run is already terminal, emit done and close
        if not run_id_str or run_status in ("completed", "failed", "blocked"):
            done_payload = {"run_id": run_id_str, "status": run_status or "no_run"}
            yield f"event: workflow_done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
            return

        # Poll for new events while run is active
        max_poll_seconds = 1800  # 30 minutes max
        poll_interval = 1.5
        start = time.time()
        while time.time() - start < max_poll_seconds:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                new_events = repo.get_workflow_execution_events_since(
                    run_id_str, since_id=last_event_id,
                )
                for ev in new_events:
                    last_event_id = ev.get("id", 0)
                    payload = {
                        "id": ev.get("id"),
                        "run_id": run_id_str,
                        "node_name": ev.get("node_name"),
                        "agent_id": ev.get("agent_id"),
                        "event_type": ev.get("event_type"),
                        "status": ev.get("status"),
                        "message": ev.get("message"),
                        "payload": ev.get("payload", {}),
                        "token_count": ev.get("token_count"),
                        "latency_ms": ev.get("latency_ms"),
                        "created_at": ev.get("created_at"),
                    }
                    yield f"event: workflow_event\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception:
                pass

            # Check if run has completed
            try:
                current_run = _get_workflow_run_by_id(
                    repo, project_id, chapter_number, run_id_str,
                )
                if current_run and current_run.get("status") in ("completed", "failed", "blocked"):
                    done_payload = {"run_id": run_id_str, "status": current_run["status"]}
                    yield f"event: workflow_done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                    return
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

        # Timeout - emit done
        done_payload = {"run_id": run_id_str, "status": "timeout"}
        yield f"event: workflow_done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
