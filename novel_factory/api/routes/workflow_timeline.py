"""Workflow timeline API for chapter-level observability (v6.6.11).

GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-stream (v6.1 SSE)

v6.6.11: Each timeline node now includes node_status, domain_status, severity,
retryable, blocking, next_action, action_label, user_message, flags — derived
from NodeOperationResult. memory_curator node correctly shows warning/fallback
instead of success green when memory is not trusted.
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
from ...workflow.node_recovery import (
    node_retry_target,
    resolve_failed_node_from_events,
)

router = APIRouter()

# Node label mapping (matches frontend state-labels.ts)
NODE_LABELS: dict[str, str] = {
    "health_check": "预检",
    "task_discovery": "任务识别",
    "planner": "规划",
    "brief_validation": "规划校验",  # v6.9.0
    "rhythm_budget_preflight": "节奏预检",  # v6.9.0
    "screenwriter": "编剧",
    "author": "执笔",
    "polisher": "润色",
    "editor": "审核",
    "memory_curator": "记忆整理",
    "publisher": "发布",
    "publish": "发布",
    "creative_ledger_curator": "创作台账",  # v6.9.0
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


def _derive_node_semantics(
    node_name: str,
    status: str,
    events: list[dict] | None = None,
    *,
    memory_status: dict | None = None,
) -> dict[str, Any]:
    """Derive node-level semantic fields for timeline response (v6.6.11).

    Uses NodeOperationResult contract for memory_curator and
    generic derivation for other nodes.

    Returns dict with: node_status, domain_status, severity, retryable,
    blocking, next_action, action_label, user_message, flags.
    """
    from ..contracts import (
        NodeOperationResult,
        node_success,
        node_warning,
        node_failed,
        node_blocked,
        node_skipped,
        memory_curator_node_result,
    )

    # Special handling for memory_curator
    if node_name == "memory_curator" and memory_status is not None:
        mem_st = memory_status.get("memory_status", "missing")
        event_st = None
        has_error = False
        error_message = None

        if events:
            failed_events = [e for e in events if e.get("event_type") == "failed"]
            if failed_events:
                has_error = True
                error_message = failed_events[-1].get("message")
            elif status == "running":
                event_st = "running"
            elif status == "skipped":
                event_st = "skipped"
            elif status in {"completed", "warning"}:
                event_st = "completed"

        result = memory_curator_node_result(
            memory_status=mem_st,
            event_status=event_st,
            batch_count=memory_status.get("batch_count", 0),
            trusted_batch_count=memory_status.get("trusted_batch_count", 0),
            fallback_batch_count=memory_status.get("fallback_batch_count", 0),
            has_error=has_error,
            error_message=error_message,
        )
        d = result.to_dict()
        # Remove node_name from output (redundant in timeline node)
        d.pop("node_name", None)
        d.pop("message", None)  # internal message, not for timeline
        return d

    # Generic node derivation
    if status in {"completed", "warning"}:
        # Check if node events indicate warnings/degradation
        has_warnings = False
        warning_msg = ""
        if events:
            for ev in events:
                ev_status = ev.get("status", "")
                if ev_status in ("warning", "error"):
                    has_warnings = True
                    warning_msg = ev.get("message", "")
                    break

        if has_warnings:
            result = node_warning(
                node_name,
                warning_msg or "节点执行产生警告",
                domain_status="degraded",
                user_message=warning_msg or "节点执行有警告，建议检查",
            )
        else:
            result = node_success(node_name)
    elif status == "running":
        result = NodeOperationResult(
            node_name=node_name,
            node_status="running",
            domain_status="pending",
            severity="info",
            message="节点运行中",
        )
    elif status == "failed":
        error_msg = ""
        if events:
            failed_events = [e for e in events if e.get("event_type") == "failed"]
            if failed_events:
                error_msg = failed_events[-1].get("message", "")
        result = node_failed(
            node_name,
            error_msg or "节点执行失败",
            user_message=error_msg or "节点执行失败，可重试",
            retryable=True,
        )
    elif status == "blocked":
        result = node_blocked(
            node_name,
            "节点被阻塞",
            next_action="retry_node",
            action_label="重试节点",
        )
    elif status == "skipped":
        result = node_skipped(node_name)
    else:
        # pending
        result = NodeOperationResult(
            node_name=node_name,
            node_status="pending",
            domain_status="pending",
            severity="info",
            message="等待执行",
        )

    d = result.to_dict()
    d.pop("node_name", None)
    d.pop("message", None)  # internal message, not for timeline
    return d


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


def _get_active_memory_curator_lock(
    repo: Any,
    project_id: str,
    chapter_number: int,
) -> dict | None:
    """Return the active MemoryCurator lock, letting the repository clear stale locks."""
    if not hasattr(repo, "get_memory_curator_lock"):
        return None
    try:
        lock = repo.get_memory_curator_lock(project_id, chapter_number)
    except Exception:
        return None
    if lock and str(lock.get("status") or "") == "running":
        return lock
    return None


def _has_memory_curator_timeout_event(repo: Any, run_id: str) -> bool:
    """Return True when MemoryCurator recorded timeout/failure for the run."""
    if not run_id:
        return False
    try:
        events = repo.get_workflow_node_events(run_id, node_name="memory_curator")
    except Exception:
        return False
    for event in events:
        status = str(event.get("status") or "").lower()
        event_type = str(event.get("event_type") or "").lower()
        message = f"{event.get('message') or ''} {event.get('error_message') or ''}".lower()
        if status in {"failed", "error"} or event_type in {"failed", "error"}:
            return True
        if "执行超时" in message or "timeout" in message:
            return True
    return False


def _block_memory_curator_timeout_run_if_needed(repo: Any, run_data: dict | None) -> bool:
    """Release stale MemoryCurator lock and keep the run blocked at that node."""
    if (
        not run_data
        or run_data.get("status") not in {"running", "blocked", "failed"}
    ):
        return False
    run_id = str(run_data.get("id") or run_data.get("run_id") or "")
    project_id = str(run_data.get("project_id") or "")
    chapter_number = int(run_data.get("chapter_number") or 0)
    if not run_id or not project_id or not chapter_number:
        return False
    if not _has_memory_curator_timeout_event(repo, run_id):
        return False
    try:
        events = repo.get_workflow_node_events(run_id)
    except Exception:
        events = []
    if resolve_failed_node_from_events(events, run_data.get("current_node")) != "memory_curator":
        return False
    if hasattr(repo, "release_memory_curator_lock"):
        try:
            repo.release_memory_curator_lock(project_id, chapter_number, run_id=run_id)
        except Exception:
            pass
    try:
        repo.update_workflow_run(
            run_id,
            status="blocked",
            current_node="memory_curator",
            error_message="节点 memory_curator 执行超时（>600秒），需要补跑记忆提取",
        )
    except Exception:
        pass
    return True


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
    chapter: dict | None = None,
    checkpoint_info: dict | None = None,
    failed_node: str | None = None,
) -> dict[str, Any]:
    """Build recovery recommendations for a workflow run.

    v6.6.6: Uses derive_workflow_recovery_state() for canonical state,
    then enriches with legacy safe_actions format for backward compatibility.
    """
    from ...workflow.state_integrity import derive_workflow_recovery_state

    stale_info = _detect_stale(run_data, timeout_minutes)
    is_stale = stale_info["is_stale"]
    chapter_status = chapter_status or "unknown"
    terminal_statuses = {"reviewed", "awaiting_publish", "published"}

    # v6.6.6: Derive canonical recovery state
    has_existing_content = bool(chapter and chapter.get("content")) if chapter else False
    recovery_state = derive_workflow_recovery_state(
        chapter=chapter,
        latest_run=run_data,
        checkpoint_info=checkpoint_info,
        has_existing_content=has_existing_content,
    )

    def _payload() -> dict[str, Any]:
        return {
            "recommended_action": recommended_action,
            "reason": reason,
            "safe_actions": safe_actions,
            # v6.6.6: Include canonical recovery_state
            "recovery_state": recovery_state,
        }

    # Build legacy safe_actions format for backward compatibility
    recommended_action = None
    reason = None
    safe_actions: list[dict] = []
    current_node = run_data.get("current_node") if run_data else None
    effective_node = failed_node or current_node
    retry_target = _node_retry_target(effective_node)

    # A healthy active run is not a recovery scenario. Checkpoint availability is
    # shown in the checkpoint panel; turning it into a recovery CTA makes a
    # normal in-progress workflow look broken.
    if run_data and run_data.get("status") == "running" and not is_stale and chapter_status != "blocking":
        return _payload()

    # v6.7.6: Blocked/Failed run takes priority over terminal chapter status
    # When run is blocked, show recovery actions even if chapter is awaiting_publish
    run_status = run_data.get("status") if run_data else None
    if (
        effective_node == "memory_curator"
        and chapter_status in terminal_statuses
        and run_status in ("blocked", "failed")
    ):
        recommended_action = "backfill_memory"
        reason = "记忆整理节点失败或超时，正文已到发布就绪状态，可补跑记忆提取后继续发布。"
        safe_actions.extend([
            {"key": "view_artifacts", "label": "查看产物", "safe": True},
            {"key": "view_content", "label": "查看正文", "safe": True},
            {
                "key": "backfill_memory",
                "label": "补跑记忆提取",
                "safe": True,
                "note": "只重跑 Memory Curator，不覆盖正文和审核结果",
            },
        ])
        return _payload()

    if (
        effective_node == "memory_curator"
        and chapter_status in terminal_statuses
        and run_status == "running"
        and is_stale
    ):
        recommended_action = "mark_stuck"
        reason = "记忆整理节点运行超时，先标记卡住运行，再补跑记忆提取。"
        safe_actions.extend([
            {"key": "view_artifacts", "label": "查看产物", "safe": True},
            {"key": "view_content", "label": "查看正文", "safe": True},
            {"key": "mark_stuck", "label": "标记为阻塞", "safe": True, "note": "释放旧运行后可补跑记忆"},
        ])
        return _payload()

    if run_status in ("blocked", "failed"):
        recommended_action = "retry_node" if retry_target else "reset_chapter"
        reason = (
            f"工作流在{retry_target['label']}节点阻塞，可保留已有产物并定点重试。"
            if retry_target
            else (
                "工作流被阻塞，可清除阻塞并重置。"
                if run_status == "blocked"
                else "工作流运行失败，可清除阻塞并重置。"
            )
        )
        safe_actions.extend([
            {"key": "view_artifacts", "label": "查看产物", "safe": True},
            {"key": "view_content", "label": "查看正文", "safe": True},
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
            "note": "保留当前正文和版本，回到 planned，完整重跑",
        })
        return _payload()

    if chapter_status in terminal_statuses:
        safe_actions.append({"key": "view_artifacts", "label": "查看产物", "safe": True})
        if is_stale:
            recommended_action = "mark_stuck"
            reason = "终态章节仍有运行中工作流，建议标记为阻塞。"
            safe_actions.append({"key": "mark_stuck", "label": "标记为阻塞", "safe": True})
        else:
            # v6.6.6: publish_ready for terminal chapters
            safe_actions.append({"key": "publish", "label": "确认发布", "safe": True})
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
    elif run_data and run_data.get("status") == "completed" and chapter_status in ("scripted", "drafted", "polished", "review"):
        recommended_action = "generate"
        reason = f"本次运行没有到达发布终态，章节仍停在 {chapter_status}，可从当前状态继续生成。"
        safe_actions.extend([
            {"key": "view_content", "label": "查看正文", "safe": True},
            {
                "key": "generate",
                "label": "继续生成",
                "safe": True,
                "note": "从当前章节状态继续，不覆盖已保存正文",
            },
        ])
    else:
        # v6.6.6: Use canonical recovery_state for other statuses
        for action_key in recovery_state.get("safe_actions", []):
            action_labels = {
                "view_content": "查看正文",
                "view_detail": "查看详情",
                "generate": "生成本章",
                "publish": "确认发布",
                "resume": "继续/恢复运行",
                "rerun": "重新运行",
                "reset": "清除阻塞并重置",
                "mark_stuck": "标记为阻塞",
                "local_edit": "局部编辑",
                "create_revision_draft": "创建修订版",
                "reset_explicitly": "显式重置",
                "reopen_revision": "重新返修",
            }
            label = action_labels.get(action_key, action_key)
            safe_actions.append({"key": action_key, "label": label, "safe": True})
        recommended_action = recovery_state.get("recommended_action")
        reason = recovery_state.get("blocking_reason") or recovery_state.get("recovery_hint")

    return _payload()


def _node_retry_target(current_node: str | None) -> dict[str, str] | None:
    target = node_retry_target(current_node)
    if not target:
        return None
    return {"label": target["label"], "status": target["status"]}


def _build_node_timeline(
    events: list[dict],
    artifacts: list[dict],
    run_status: str | None = None,
    current_node: str | None = None,
    memory_status: dict | None = None,
) -> list[dict]:
    """Build canonical node timeline overlaid with workflow_node_events.

    Groups events by node_name and derives status, duration, messages, artifacts.
    v6.6.11: Enriches each node with node_status, domain_status, severity,
    retryable, blocking, next_action, action_label, user_message, flags.
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
        # v6.6.21: Stable sort — null/empty timestamps last, then ascending.
        # Events without timestamps (skip/resume messages) should not float to the top.
        evs = sorted(
            evs,
            key=lambda e: (e.get("created_at") or "9999-12-31T23:59:59", e.get("id") or 0),
        )
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
            ev_status = last_ev.get("status", "")
            # v6.6.21-review: completed + failed/error status must show as failed,
            # not success. This also handles legacy events where event_type was
            # "completed" but the node actually failed.
            if ev_status in ("failed", "error"):
                status = "failed"
            elif ev_status == "warning":
                status = "warning"
            else:
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

        started_at = _normalize_timestamp(started_ev.get("created_at")) if started_ev else None
        completed_at = None
        if status in {"completed", "warning"} and completed_ev:
            completed_at = _normalize_timestamp(completed_ev.get("created_at"))
        elif status == "failed" and failed_ev:
            completed_at = _normalize_timestamp(failed_ev.get("created_at"))

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

        # v6.6.11: Derive node-level semantic fields
        node_semantics = _derive_node_semantics(
            node_name, status, evs,
            memory_status=memory_status if node_name == "memory_curator" else None,
        )

        return {
            "node_name": node_name,
            "label": base.get("label") or _node_label(node_name),
            "node_group": base.get("node_group", "unknown"),
            "node_type": base.get("node_type", base.get("node_group", "unknown")),
            "status": status,
            # v6.6.11: Node-level semantic fields
            "node_status": node_semantics.get("node_status", status),
            "domain_status": node_semantics.get("domain_status", "pending"),
            "severity": node_semantics.get("severity", "info"),
            "retryable": node_semantics.get("retryable", False),
            "blocking": node_semantics.get("blocking", False),
            "next_action": node_semantics.get("next_action"),
            "action_label": node_semantics.get("action_label"),
            "user_message": node_semantics.get("user_message", ""),
            "flags": node_semantics.get("flags", {}),
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
    """Embed execution events and evidence into timeline nodes.

    v6.10.0: Filter redundant node_message events and normalize timestamps.
    """
    # Filter noise: node_message that duplicates node_started/node_completed
    node_started_set: set[str] = set()
    node_completed_set: set[str] = set()
    for ev in exec_events:
        et = ev.get("event_type", "")
        node = ev.get("node_name", "")
        if et == "node_started":
            node_started_set.add(node)
        elif et == "node_completed":
            node_completed_set.add(node)

    filtered_events = []
    for ev in exec_events:
        et = ev.get("event_type", "")
        node = ev.get("node_name", "")
        msg = ev.get("message", "")

        # Skip node_message for started/completed (redundant with node_started/node_completed)
        if et == "node_message":
            if node in node_started_set and ("开始" in msg or "started" in msg.lower()):
                continue
            if node in node_completed_set and ("完成" in msg or "completed" in msg.lower()):
                continue
            # Skip "跳过该节点" messages
            if "跳过该节点" in msg:
                continue

        # Skip task_log (run_detail noise)
        if et == "task_log":
            continue

        filtered_events.append(ev)

    grouped = _group_execution_events_by_node(filtered_events)
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
                    "created_at": _normalize_timestamp(ev.get("created_at")),
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
        try:
            settings = get_settings(request)
            timeout_minutes = settings.workflow.task_timeout_minutes
        except Exception:
            timeout_minutes = STUCK_THRESHOLD_MINUTES

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
        if hasattr(repo, "restore_memory_curator_reset_recovery_runs"):
            repo.restore_memory_curator_reset_recovery_runs(
                project_id=project_id,
                chapter_number=chapter_number,
                run_id=run_id,
            )

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

        active_memory_lock = _get_active_memory_curator_lock(repo, project_id, chapter_number)
        if not run_id and active_memory_lock and active_memory_lock.get("run_id"):
            locked_run = _get_workflow_run_by_id(
                repo,
                project_id,
                chapter_number,
                str(active_memory_lock.get("run_id")),
            )
            if locked_run:
                target_run = locked_run

        if (
            not run_id
            and target_run
            and target_run.get("status") == "completed"
            and target_run.get("current_node") == "reset_recovery"
            and chapter.get("status") == "planned"
        ):
            target_run = None

        if _block_memory_curator_timeout_run_if_needed(repo, target_run):
            refreshed_id = target_run.get("id") or target_run.get("run_id")
            if refreshed_id:
                target_run = _get_workflow_run_by_id(
                    repo, project_id, chapter_number, refreshed_id
                ) or target_run
            active_memory_lock = _get_active_memory_curator_lock(repo, project_id, chapter_number)

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
                active_memory_lock = _get_active_memory_curator_lock(repo, project_id, chapter_number)

        # No run -> empty timeline
        if not target_run:
            checkpoint = _checkpoint_metadata(repo, project_id, chapter_number)
            # v6.6.6: Build recovery state even without run
            recovery = _build_recovery(
                None,
                chapter.get("status"),
                timeout_minutes,
                chapter=chapter,
                checkpoint_info=checkpoint,
            )
            return envelope_response({
                "project_id": project_id,
                "chapter_number": chapter_number,
                "run_id": None,
                "run_status": None,
                "current_node": None,
                "started_at": None,
                "elapsed_minutes": None,
                "is_stale": False,
                "memory_curator_running": False,
                "memory_curator_lock": None,
                "recovery": recovery,
                "checkpoint": checkpoint,
                "nodes": _build_node_timeline([], []),
            })

        run_id_str = target_run.get("id") or target_run.get("run_id", "")
        run_status = target_run.get("status", "unknown")
        current_node = target_run.get("current_node")
        started_at = target_run.get("started_at")
        active_memory_run_id = active_memory_lock.get("run_id") if active_memory_lock else None
        memory_curator_running = bool(
            active_memory_lock
            and (
                (active_memory_run_id and str(active_memory_run_id) == str(run_id_str))
                or (not active_memory_run_id and current_node == "memory_curator")
            )
        )
        stale_run_data = target_run
        if memory_curator_running:
            run_status = "running"
            current_node = "memory_curator"
            stale_run_data = {
                **target_run,
                "status": "running",
                "current_node": "memory_curator",
            }

        stale_info = _detect_stale(stale_run_data, timeout_minutes)

        # Fetch node events before recovery so a human_review wrapper can be
        # attributed to the real failed node.
        events = repo.get_workflow_node_events(run_id_str)
        failed_node = resolve_failed_node_from_events(events, current_node)

        # v6.6.6: Get checkpoint info for recovery state
        checkpoint = _checkpoint_metadata(repo, project_id, chapter_number)
        recovery = _build_recovery(
            stale_run_data,
            chapter.get("status"),
            timeout_minutes,
            chapter=chapter,
            checkpoint_info=checkpoint,
            failed_node=failed_node,
        )

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

        # v6.6.11: Fetch memory status for node-level semantics
        memory_status = None
        try:
            from ..routes._memory_curator_gate import get_memory_status_for_chapter
            memory_status = get_memory_status_for_chapter(
                repo,
                project_id,
                chapter_number,
                run_id=run_id_str,
            )
        except Exception:
            pass

        nodes = _build_node_timeline(
            events,
            artifacts,
            run_status=run_status,
            current_node=current_node,
            memory_status=memory_status,
        )

        # v6.1: Embed execution events into timeline nodes
        try:
            exec_events = repo.get_workflow_execution_events(run_id_str)
            nodes = _embed_execution_events_in_nodes(nodes, exec_events)
        except Exception:
            pass  # Backward compatible — execution events are additive

        checkpoint = _checkpoint_metadata(repo, project_id, chapter_number)
        display_current_node = (
            failed_node
            if current_node == "human_review" and failed_node
            else current_node
        )

        return envelope_response({
            "project_id": project_id,
            "chapter_number": chapter_number,
            "run_id": run_id_str,
            "run_status": run_status,
            "chapter_status": chapter.get("status"),
            "current_node": display_current_node,
            "raw_current_node": current_node,
            "resolved_failed_node": failed_node,
            "started_at": _normalize_timestamp(started_at),
            "elapsed_minutes": stale_info.get("elapsed_minutes"),
            "is_stale": stale_info.get("is_stale", False),
            "memory_curator_running": memory_curator_running,
            "memory_curator_lock": active_memory_lock if memory_curator_running else None,
            "recovery": recovery,
            "checkpoint": checkpoint,
            "nodes": nodes,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取工作流时间线失败: {str(e)}")


# ── v6.1: SSE Streaming Endpoint ───────────────────────────────


def _normalize_timestamp(ts: str | None) -> str | None:
    """Normalize timestamp to ISO 8601 format with UTC+8 timezone."""
    if not ts:
        return None
    if "T" in ts and ("+" in ts or "Z" in ts or ts.endswith("00:00")):
        return ts
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone(timedelta(hours=8))).isoformat()
    except (ValueError, TypeError):
        return ts


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

    # v6.8.4 Phase 3: Wait for run creation when no run_id provided
    if not target_run and not run_id:
        for _ in range(10):
            await asyncio.sleep(0.5)
            runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=1)
            if runs:
                target_run = runs[0]
                break

    run_id_str = target_run.get("id") or target_run.get("run_id", "") if target_run else ""
    run_status = target_run.get("status", "") if target_run else ""

    async def event_generator():
        last_event_id = since_id or 0

        # v6.10.0: Check if real-time event queue is available.
        # If so, skip DB replay — the queue's subscribe() will replay
        # existing events, avoiding duplicates.
        from ...workflow.event_queue import get_event_queue_manager
        live_queue = get_event_queue_manager().get(run_id_str) if run_id_str else None

        # Replay existing events from DB only when no live queue is available
        # (e.g. reconnecting to a completed run or legacy path).
        if replay and run_id_str and not (live_queue and not live_queue.is_done):
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
                        "created_at": _normalize_timestamp(ev.get("created_at")),
                    }
                    yield f"event: workflow_event\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.warning("SSE event_generator error: %s", e, exc_info=True)

        # If run is already terminal, emit done and close
        if not run_id_str or run_status in ("completed", "failed", "blocked", "cancelled"):
            done_payload = {"run_id": run_id_str, "status": run_status or "no_run"}
            yield f"event: workflow_done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
            return

        # Poll for new events while run is active
        max_poll_seconds = 1800  # 30 minutes max
        poll_interval = 1.5
        heartbeat_interval = 10  # send heartbeat every ~15s (10 * 1.5s)
        heartbeat_counter = 0
        start = time.time()

        # Reuse the live_queue variable computed above; fall back to DB polling
        event_queue = live_queue

        if event_queue and not event_queue.is_done:
            # Real-time mode: subscribe to event queue
            q = event_queue.subscribe()
            try:
                while time.time() - start < max_poll_seconds:
                    if await request.is_disconnected():
                        break

                    try:
                        event = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        # Send heartbeat
                        yield ":heartbeat\n\n"
                        continue

                    if isinstance(event, dict) and event.get("type") == "done":
                        done_payload = {"run_id": run_id_str, "status": event.get("status", "done")}
                        yield f"event: workflow_done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                        return

                    # Push event to client
                    payload = {
                        "id": event.get("id"),
                        "run_id": run_id_str,
                        "node_name": event.get("node_name"),
                        "agent_id": event.get("agent_id"),
                        "event_type": event.get("event_type"),
                        "status": event.get("status"),
                        "message": event.get("message"),
                        "payload": event.get("payload", {}),
                        "token_count": event.get("token_count"),
                        "latency_ms": event.get("latency_ms"),
                        "created_at": _normalize_timestamp(event.get("created_at")),
                    }
                    yield f"event: workflow_event\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            finally:
                event_queue.unsubscribe(q)
        else:
            # Fallback: DB polling mode (legacy)
            while time.time() - start < max_poll_seconds:
                if await request.is_disconnected():
                    break

                heartbeat_counter += 1
                if heartbeat_counter >= heartbeat_interval:
                    heartbeat_counter = 0
                    yield ":heartbeat\n\n"

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
                except Exception as e:
                    logger.warning("SSE event_generator error: %s", e, exc_info=True)

                try:
                    current_run = _get_workflow_run_by_id(
                        repo, project_id, chapter_number, run_id_str,
                    )
                    if current_run and current_run.get("status") in ("completed", "failed", "blocked", "cancelled"):
                        done_payload = {"run_id": run_id_str, "status": current_run["status"]}
                        yield f"event: workflow_done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                        return
                except Exception as e:
                    logger.warning("SSE run status check error: %s", e, exc_info=True)

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
