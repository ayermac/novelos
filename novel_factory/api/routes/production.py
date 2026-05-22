"""Autonomous Production Loop API endpoints.

v5.5.3: Provides next-action guidance and AI auto-fill for project production.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ..contracts import success, partial_success, failed, blocked as blocked_result, needs_human

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class AutoFillRequest(BaseModel):
    """Request for AI auto-fill of missing project context."""

    scope: str = "missing_context"  # missing_context | arc_plan | chapter_instructions
    chapter_start: int = 1
    chapter_end: int = 10
    confirm: bool = False


class ArcPlanRequest(BaseModel):
    """Request for arc planning over a chapter range."""

    chapter_start: int = 1
    chapter_end: int = 10
    confirm: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_approved_genesis(repo, project_id: str) -> bool:
    """Check if project has an approved genesis run."""
    return any(run.get("status") == "approved" for run in repo.list_genesis_runs(project_id))


def _latest_non_stale_genesis(repo, project_id: str, timeout_minutes: int = 30) -> dict | None:
    """Return latest genesis after recovering abandoned running rows."""
    from .genesis import _recover_stale_running_genesis

    latest = repo.get_latest_genesis_run(project_id)
    return _recover_stale_running_genesis(repo, latest, timeout_minutes)


def _has_pending_genesis(repo, project_id: str, timeout_minutes: int = 30) -> bool:
    """Check if project has a pending/generated genesis draft awaiting review."""
    latest = _latest_non_stale_genesis(repo, project_id, timeout_minutes)
    return latest is not None and latest.get("status") == "generated"


def _has_running_genesis(repo, project_id: str, timeout_minutes: int = 30) -> bool:
    """Check if project has a running genesis."""
    latest = _latest_non_stale_genesis(repo, project_id, timeout_minutes)
    return latest is not None and latest.get("status") == "running"


def _has_manual_context_ready(health: dict) -> bool:
    """Return true when project context is complete enough for chapter generation.

    v6.3.1: Unified with run guard — requires approved genesis + world + characters
    + outlines + instructions (same as ready_for_chapter_1). This prevents the
    mismatch where production-next recommends generate_chapter but the run guard
    blocks with CONTEXT_INCOMPLETE.
    """
    return health.get("ready_for_chapter_1", False)


def _get_blocking_chapter(repo, project_id: str) -> dict | None:
    """Find a chapter in blocking or revision status."""
    chapters = repo.list_chapters(project_id)
    for ch in chapters:
        if ch.get("status") in ("blocking", "revision"):
            return ch
    return None


def _get_stuck_run(repo, project_id: str, current_chapter: int) -> dict | None:
    """Find a stuck workflow run for the current chapter.

    Only considers the *latest* run for the current chapter. If the latest run
    succeeded, old failures are ignored to prevent them from permanently
    hijacking production-next.
    """
    runs = repo.get_workflow_runs_for_project(project_id, chapter_number=current_chapter, limit=20)
    if not runs:
        return None
    # runs are ordered by started_at DESC (most recent first)
    latest = runs[0]
    chapter = repo.get_chapter(project_id, current_chapter)
    chapter_status = chapter.get("status") if chapter else None
    if latest.get("status") in ("failed", "blocked") and chapter_status in ("blocking", "revision"):
        return latest
    return None


def _has_pending_memory_updates(repo, project_id: str) -> bool:
    """Check for pending or partial memory update batches."""
    pending_items, actionable_batches = _list_actionable_memory_updates(repo, project_id)
    return bool(pending_items or actionable_batches)


def _list_actionable_memory_updates(repo, project_id: str) -> tuple[list[dict], list[dict]]:
    """Return pending memory items whose parent batches are still actionable."""
    actionable_batches = [
        batch for batch in repo.list_memory_batches(project_id)
        if batch.get("status") in ("pending", "partial")
    ]
    actionable_batch_ids = {batch.get("id") for batch in actionable_batches}
    pending_items = [
        item for item in repo.list_memory_items_by_project(project_id, status="pending")
        if item.get("batch_id") in actionable_batch_ids
    ]
    return pending_items, actionable_batches


def _is_chapter_production_run(run: dict) -> bool:
    return (run.get("graph_name") or "chapter_production") == "chapter_production"


def _has_running_chapter_workflow(repo, project_id: str, chapter_number: int) -> bool:
    """Check if a chapter has a currently running workflow run."""
    if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
        repo.reconcile_terminal_chapter_running_workflows(
            project_id=project_id,
            chapter_number=chapter_number,
        )
    runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=5)
    return any(r.get("status") == "running" and _is_chapter_production_run(r) for r in runs)


def _get_running_chapter_workflow(repo, project_id: str, chapter_number: int) -> dict | None:
    """Return the latest running workflow run for a chapter, if any."""
    if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
        repo.reconcile_terminal_chapter_running_workflows(
            project_id=project_id,
            chapter_number=chapter_number,
        )
    runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=5)
    for run in runs:
        if run.get("status") == "running" and _is_chapter_production_run(run):
            return run
    return None


def _get_running_project_chapter_workflow(repo, project_id: str) -> dict | None:
    """Return the latest running chapter workflow anywhere in the project."""
    if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
        repo.reconcile_terminal_chapter_running_workflows(project_id=project_id)
    runs = repo.get_workflow_runs_for_project(project_id, limit=100)
    for run in runs:
        if run.get("status") == "running" and _is_chapter_production_run(run):
            return run
    return None


def _elapsed_minutes_since(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return (datetime.now() - datetime.strptime(timestamp[:26], fmt)).total_seconds() / 60
        except ValueError:
            continue
    return None


def _target_workflow_health(repo, project_id: str, target_chapter: int, timeout_minutes: int) -> dict:
    """Build workflow health for the chapter targeted by the recommended action."""
    running = _get_running_chapter_workflow(repo, project_id, target_chapter)
    elapsed = _elapsed_minutes_since(running.get("started_at")) if running else None
    stale = elapsed is not None and elapsed >= timeout_minutes
    return {
        "target_chapter": target_chapter,
        "has_running_target_workflow": running is not None,
        "target_workflow_run_id": running.get("id") if running else None,
        "target_workflow_current_node": running.get("current_node") if running else None,
        "target_workflow_elapsed_minutes": elapsed,
        "target_workflow_stale": stale,
    }


def _view_running_workflow_action(project_id: str, chapter_number: int, run: dict | None) -> dict:
    """Return a non-generating action for a chapter that is already running."""
    current_node = run.get("current_node") if run else None
    node_desc = f"当前节点：{current_node}。" if current_node else ""
    return {
        "key": "view_running_workflow",
        "label": f"查看第 {chapter_number} 章运行进度",
        "description": f"第 {chapter_number} 章已有工作流正在运行，{node_desc}请先查看进度，不要重复启动生成。",
        "primary": True,
        "action_url": f"/projects/{project_id}?module=chapters&chapter={chapter_number}&view=workflow",
        "method": "GET",
        "requires_confirmation": False,
        "target_chapter": chapter_number,
        "run_id": run.get("id") if run else None,
    }


def _is_obsolete_disconnected_session(repo, project_id: str, session: dict, steps: list[dict], next_action: dict) -> bool:
    """Return True when a paused disconnected session no longer matches project truth."""
    if session.get("status") != "paused" or session.get("stop_reason") != "client_disconnected":
        return False

    unfinished_steps = [s for s in steps if not s.get("result")]
    if not unfinished_steps:
        return False

    last_step = unfinished_steps[-1]
    step_action = last_step.get("action")
    step_target = last_step.get("target_chapter") or session.get("chapter_start")
    next_target = next_action.get("target_chapter") or step_target

    target_chapter = repo.get_chapter(project_id, int(step_target)) if step_target else None
    target_status = target_chapter.get("status") if target_chapter else None
    target_already_moved_on = target_status in ("reviewed", "awaiting_publish", "published", "blocking")
    action_changed = next_action.get("key") != step_action or next_target != step_target

    if target_already_moved_on:
        return True

    if step_target and _has_running_chapter_workflow(repo, project_id, int(step_target)):
        return False

    return target_already_moved_on or action_changed


def _list_stale_running_workflows(repo, project_id: str, timeout_minutes: int) -> list[dict]:
    """List running workflow runs that exceeded the project timeout."""
    if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
        repo.reconcile_terminal_chapter_running_workflows(project_id=project_id)
    rows = repo.get_workflow_runs_for_project(project_id, limit=100)
    stale: list[dict] = []
    for row in rows:
        if row.get("status") != "running":
            continue
        elapsed = _elapsed_minutes_since(row.get("started_at"))
        if elapsed is None or elapsed < timeout_minutes:
            continue
        stale.append({
            "run_id": row.get("id") or row.get("run_id"),
            "chapter_number": row.get("chapter_number"),
            "current_node": row.get("current_node"),
            "elapsed_minutes": elapsed,
            "started_at": row.get("started_at"),
        })
    return stale


def _get_project_stale_running_workflow(repo, project_id: str, timeout_minutes: int) -> dict | None:
    """Return the oldest stale running workflow for this project, if any."""
    stale = _list_stale_running_workflows(repo, project_id, timeout_minutes)
    if not stale:
        return None
    return stale[0]


def _get_planned_chapter_with_content(repo, project_id: str) -> dict | None:
    """Find a planned chapter that still has preserved content."""
    for chapter in repo.list_chapters(project_id):
        if chapter.get("status") != "planned":
            continue
        content = (chapter.get("content") or "").strip()
        word_count = chapter.get("word_count") or 0
        if (content or word_count > 0) and not _has_explicit_reset_recovery(
            repo, project_id, chapter.get("chapter_number")
        ):
            return chapter
    return None


def _has_explicit_reset_recovery(repo, project_id: str, chapter_number: int | None) -> bool:
    if chapter_number is None:
        return False
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


def _detect_chapter_workflow_contradictions(repo, project_id: str) -> list[dict]:
    """v5.5.15: Detect contradictions between chapter_status and workflow_run status.

    Priority rule: workflow_run > chapter_status > auto_run_session

    Contradictions detected:
    1. Chapter is reviewed/published/awaiting_publish but has a running workflow run
    2. Chapter is in a terminal state but has a stale running workflow that should have completed
    3. Chapter status contradicts the most recent workflow status
    """
    if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
        repo.reconcile_terminal_chapter_running_workflows(project_id=project_id)

    items: list[dict] = []
    chapters = repo.list_chapters(project_id)
    terminal_statuses = {"reviewed", "published", "awaiting_publish"}

    for ch in chapters:
        ch_num = ch.get("chapter_number")
        ch_status = ch.get("status", "planned")

        # Get workflow runs for this chapter
        runs = repo.get_workflow_runs_for_project(project_id, chapter_number=ch_num, limit=5)
        if not runs:
            continue

        running_runs = [
            r for r in runs
            if r.get("status") == "running" and _is_chapter_production_run(r)
        ]
        latest_run = runs[0]  # Most recent first

        # Contradiction 1: Chapter in terminal state but workflow is still "running"
        if ch_status in terminal_statuses and running_runs:
            run = running_runs[0]
            items.append({
                "key": f"chapter_workflow_contradiction:{ch_num}:running_terminal",
                "severity": "blocking",
                "label": f"第 {ch_num} 章状态矛盾",
                "description": f"章节已 {ch_status}，但工作流仍显示运行中（节点：{run.get('current_node') or '未知'}），可能需要标记卡住或等待完成。",
                "action_label": "处理卡住运行",
                "action_url": f"/projects/{project_id}?module=chapters&chapter={ch_num}&view=workflow",
                "chapter_number": ch_num,
                "run_id": run.get("id") or run.get("run_id"),
            })

        # Contradiction 2: Chapter status doesn't match latest completed workflow
        elif ch_status not in terminal_statuses and ch_status not in ("blocking", "revision", "planned") and latest_run.get("status") == "completed":
            # If the latest run completed successfully, the chapter should have advanced
            # If it hasn't, something is inconsistent
            items.append({
                "key": f"chapter_workflow_contradiction:{ch_num}:stale_state",
                "severity": "attention",
                "label": f"第 {ch_num} 章状态可能滞后",
                "description": f"章节当前状态为 {ch_status}，但最近的工作流已完成。请检查章节是否需要刷新。",
                "action_label": "查看章节",
                "action_url": f"/projects/{project_id}?module=chapters&chapter={ch_num}",
                "chapter_number": ch_num,
            })

    return items


def _build_project_health_summary(repo, project_id: str, timeout_minutes: int) -> dict:
    """Build a concise author-facing project health summary."""
    if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
        repo.reconcile_terminal_chapter_running_workflows(project_id=project_id)

    project = repo.get_project(project_id)
    current_chapter = project.get("current_chapter", 1) if project else 1
    health = _build_health(repo, project_id, current_chapter)
    next_action = _determine_next_action(repo, project_id, health, current_chapter, timeout_minutes)

    stale_runs = _list_stale_running_workflows(repo, project_id, timeout_minutes)
    pending_memory_items, pending_memory_batches = _list_actionable_memory_updates(repo, project_id)

    active_session = repo.get_active_auto_run_session(project_id)
    obsolete_session = None
    if active_session:
        steps = repo.list_auto_run_steps(active_session["id"])
        if _is_obsolete_disconnected_session(repo, project_id, active_session, steps, next_action):
            obsolete_session = active_session

    blocking_chapter = _get_blocking_chapter(repo, project_id)

    # v5.5.15: Detect chapter/workflow status contradictions
    contradiction_items = _detect_chapter_workflow_contradictions(repo, project_id)

    items: list[dict] = []

    for run in stale_runs[:5]:
        ch = run.get("chapter_number")
        items.append({
            "key": f"stale_run:{run.get('run_id')}",
            "severity": "blocking",
            "label": f"第 {ch} 章运行疑似卡住",
            "description": f"当前节点 {run.get('current_node') or '未知'} 已超过 {timeout_minutes} 分钟未完成。",
            "action_label": "处理卡住运行",
            "action_url": f"/projects/{project_id}?module=chapters&chapter={ch}&view=workflow",
            "run_id": run.get("run_id"),
            "chapter_number": ch,
        })

    # v5.5.15: Chapter/workflow contradiction items
    items.extend(contradiction_items)

    if obsolete_session:
        items.append({
            "key": f"obsolete_session:{obsolete_session.get('id')}",
            "severity": "warning",
            "label": "存在过期的断线会话",
            "description": "旧自动生产会话的目标章节已经进入新状态，可以清理，避免继续误导。",
            "action_label": "清理旧会话",
            "action_url": f"/api/projects/{project_id}/production/run-auto/sessions/{obsolete_session.get('id')}",
            "session_id": obsolete_session.get("id"),
        })

    if blocking_chapter:
        ch = blocking_chapter.get("chapter_number")
        items.append({
            "key": f"blocking_chapter:{ch}",
            "severity": "blocking",
            "label": f"第 {ch} 章需要恢复",
            "description": "章节处于阻塞/返修状态，需要处理后才能继续生产。",
            "action_label": "查看章节",
            "action_url": f"/projects/{project_id}?module=chapters&chapter={ch}&view=workflow",
            "chapter_number": ch,
        })

    if pending_memory_items or pending_memory_batches:
        items.append({
            "key": "pending_memory_updates",
            "severity": "attention",
            "label": "有待处理的记忆更新",
            "description": f"{len(pending_memory_items)} 条记忆项等待应用或审核。",
            "action_label": "打开记忆收件箱",
            "action_url": f"/projects/{project_id}?module=memory",
            "pending_items": len(pending_memory_items),
            "pending_batches": len(pending_memory_batches),
        })

    status = "ok"
    if any(item["severity"] == "blocking" for item in items):
        status = "blocking"
    elif items:
        status = "attention"

    return {
        "project_id": project_id,
        "status": status,
        "summary": {
            "blocking": sum(1 for item in items if item["severity"] == "blocking"),
            "attention": sum(1 for item in items if item["severity"] == "attention"),
            "warning": sum(1 for item in items if item["severity"] == "warning"),
            "stale_runs": len(stale_runs),
            "pending_memory_items": len(pending_memory_items),
            "obsolete_sessions": 1 if obsolete_session else 0,
            "contradictions": len(contradiction_items),
        },
        "items": items,
        "next_action": next_action,
    }


def _build_health(repo, project_id: str, current_chapter: int) -> dict:
    """Build health snapshot for a project."""
    from ...agent_runtime.title_contract import evaluate_title_alignment

    project = repo.get_project(project_id)
    world_settings = repo.list_world_settings(project_id)
    characters = repo.list_characters(project_id, include_inactive=True)
    outlines = repo.list_outlines(project_id)
    instruction = repo.get_instruction_by_chapter(project_id, current_chapter)
    latest_genesis = _latest_non_stale_genesis(repo, project_id)
    context_items: list[str] = []
    context_items.extend(f"{w.get('title', '')} {w.get('content', '')}" for w in world_settings)
    context_items.extend(f"{c.get('name', '')} {c.get('description', '')} {c.get('traits', '')}" for c in characters)
    context_items.extend(f"{o.get('title', '')} {o.get('content', '')}" for o in outlines)
    if instruction:
        context_items.append(
            f"{instruction.get('objective', '')} {instruction.get('key_events', '')} "
            f"{instruction.get('emotion_tone', '')} {instruction.get('ending_hook', '')}"
        )
    title_alignment = evaluate_title_alignment(project, context_items)

    has_approved_genesis = _has_approved_genesis(repo, project_id)
    has_world = len(world_settings) > 0
    has_chars = len(characters) > 0
    has_outlines_ok = len(outlines) > 0
    has_instruction = instruction is not None and bool(instruction.get("objective"))

    # v6.3: ready_for_chapter_1 is the single source of truth for whether
    # chapter generation can proceed without hitting run guards.
    ready_for_chapter_1 = (
        has_approved_genesis
        and has_world
        and has_chars
        and has_outlines_ok
        and has_instruction
    )

    return {
        "has_project": project is not None,
        "has_genesis": latest_genesis is not None,
        "has_approved_genesis": has_approved_genesis,
        "has_world_settings": has_world,
        "has_characters": has_chars,
        "has_outlines": has_outlines_ok,
        "has_instructions_for_current_chapter": has_instruction,
        "ready_for_chapter_1": ready_for_chapter_1,
        "has_pending_memory_updates": _has_pending_memory_updates(repo, project_id),
        "has_blocking_chapter": _get_blocking_chapter(repo, project_id) is not None,
        "has_stuck_run": _get_stuck_run(repo, project_id, current_chapter) is not None,
        "has_running_chapter_workflow": _has_running_chapter_workflow(repo, project_id, current_chapter),
        "title_contract": title_alignment,
        "title_contract_aligned": title_alignment["aligned"],
        "manual_context_ready": ready_for_chapter_1,
    }


def _build_missing(health: dict, project_id: str, current_chapter: int) -> list[dict]:
    """Build list of missing items with AI action suggestions."""
    missing = []

    manual_context_ready = _has_manual_context_ready(health)
    health["manual_context_ready"] = manual_context_ready

    if not health["has_approved_genesis"] and not manual_context_ready:
        missing.append({
            "key": "genesis",
            "label": "项目创世设定",
            "severity": "blocking",
            "manual_url": f"/projects/{project_id}?module=genesis",
            "ai_action": {
                "key": "generate_genesis",
                "label": "让 AI 生成项目设定",
            },
        })

    if health["has_approved_genesis"] or manual_context_ready:
        if not health.get("title_contract_aligned", True):
            missing.append({
                "key": "title_contract",
                "label": "书名与内容一致性",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=genesis",
                "ai_action": {
                    "key": "repair_title_contract",
                    "label": "重新生成符合书名的项目设定",
                },
            })

        if not health["has_world_settings"]:
            missing.append({
                "key": "world_settings",
                "label": "世界观",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=worldview",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": "让 AI 补齐世界观",
                },
            })

        if not health["has_characters"]:
            missing.append({
                "key": "characters",
                "label": "角色",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=characters",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": "让 AI 补齐角色",
                },
            })

        if not health["has_outlines"]:
            missing.append({
                "key": "outlines",
                "label": "大纲",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=outline",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": "让 AI 补齐大纲",
                },
            })

        if not health["has_instructions_for_current_chapter"]:
            missing.append({
                "key": "instructions",
                "label": f"第{current_chapter}章写作指令",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=instructions",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": f"让 AI 补齐第{current_chapter}章指令",
                },
            })

    return missing


def _determine_next_action(
    repo,
    project_id: str,
    health: dict,
    current_chapter: int,
    timeout_minutes: int = 30,
) -> dict:
    """Determine the next production action based on project state."""

    # 1. Recover blocked runs / blocking chapters first
    blocking_ch = _get_blocking_chapter(repo, project_id)
    stale_running = _get_project_stale_running_workflow(repo, project_id, timeout_minutes)
    planned_with_content = _get_planned_chapter_with_content(repo, project_id)
    stuck_run = _get_stuck_run(repo, project_id, current_chapter)

    if blocking_ch:
        ch_num = blocking_ch.get("chapter_number", current_chapter)
        return {
            "key": "recover_blocked_run",
            "label": f"恢复阻塞运行（第 {ch_num} 章）",
            "description": f"检测到第 {ch_num} 章处于阻塞状态，建议重置后重试。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/chapters/{ch_num}/reset",
            "method": "POST",
            "requires_confirmation": True,
            "target_chapter": ch_num,
        }

    if stale_running:
        ch_num = stale_running.get("chapter_number", current_chapter)
        return {
            "key": "recover_blocked_run",
            "label": f"处理卡住运行（第 {ch_num} 章）",
            "description": f"检测到第 {ch_num} 章的运行已超过恢复阈值，建议先处理卡住运行。",
            "primary": True,
            "action_url": f"/projects/{project_id}?module=chapters&chapter={ch_num}&view=workflow",
            "method": "GET",
            "requires_confirmation": False,
            "target_chapter": ch_num,
            "run_id": stale_running.get("run_id"),
        }

    running_current = _get_running_chapter_workflow(repo, project_id, current_chapter)
    if running_current:
        return _view_running_workflow_action(project_id, current_chapter, running_current)

    running_any = _get_running_project_chapter_workflow(repo, project_id)
    if running_any:
        ch_num = running_any.get("chapter_number", current_chapter)
        return _view_running_workflow_action(project_id, ch_num, running_any)

    if planned_with_content:
        ch_num = planned_with_content.get("chapter_number", current_chapter)
        return {
            "key": "review_existing_chapter_content",
            "label": f"检查第 {ch_num} 章已有正文",
            "description": f"第 {ch_num} 章处于 planned 状态但已有正文，建议先查看正文并决定编辑、回滚或重新生成。",
            "primary": True,
            "action_url": f"/projects/{project_id}?module=chapters&chapter={ch_num}&view=content",
            "method": "GET",
            "requires_confirmation": False,
            "target_chapter": ch_num,
        }

    if stuck_run:
        ch_num = stuck_run.get("chapter_number", current_chapter)
        return {
            "key": "recover_blocked_run",
            "label": f"恢复阻塞运行（第 {ch_num} 章）",
            "description": f"检测到第 {ch_num} 章的运行未完成或失败，建议先处理后再继续。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/chapters/{ch_num}/reset",
            "method": "POST",
            "requires_confirmation": True,
            "target_chapter": ch_num,
        }

    # 2. Genesis flow
    manual_context_ready = _has_manual_context_ready(health)
    health["manual_context_ready"] = manual_context_ready

    if not health["has_approved_genesis"] and not manual_context_ready:
        if _has_running_genesis(repo, project_id, timeout_minutes):
            return {
                "key": "wait_genesis",
                "label": "等待创世完成",
                "description": "AI 正在生成项目设定，请稍候。",
                "primary": True,
                "action_url": f"/api/projects/{project_id}/genesis/latest",
                "method": "GET",
                "requires_confirmation": False,
            }
        if _has_pending_genesis(repo, project_id, timeout_minutes):
            return {
                "key": "review_genesis",
                "label": "审核创世草案",
                "description": "项目设定已生成，请审核后批准应用。",
                "primary": True,
                "action_url": f"/api/projects/{project_id}/genesis/latest",
                "method": "GET",
                "requires_confirmation": False,
            }
        return {
            "key": "generate_genesis",
            "label": "生成项目设定",
            "description": "项目缺少基础设定，让 AI 一键生成世界观、角色、大纲等。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/genesis/generate",
            "method": "POST",
            "requires_confirmation": True,
        }

    # 3. Missing context after approved genesis
    missing_items = _build_missing(health, project_id, current_chapter)
    if missing_items:
        if any(item.get("key") == "title_contract" for item in missing_items):
            return {
                "key": "repair_title_contract",
                "label": "修复书名与内容不一致",
                "description": "当前世界观、角色或大纲没有兑现书名承诺，建议先重新生成并审核项目设定。",
                "primary": True,
                "action_url": f"/api/projects/{project_id}/genesis/generate",
                "method": "POST",
                "requires_confirmation": True,
            }
        return {
            "key": "generate_missing_context",
            "label": "补齐缺失资料",
            "description": "项目还缺少部分资料，让 AI 自动补齐。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/production/auto-fill",
            "method": "POST",
            "requires_confirmation": True,
        }

    # 4. Memory updates
    if health["has_pending_memory_updates"]:
        return {
            "key": "apply_memory_updates",
            "label": "应用记忆更新",
            "description": "有待处理的记忆更新，建议审核并应用。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/memory-updates",
            "method": "GET",
            "requires_confirmation": False,
        }

    # 5. Chapter generation flow
    chapter = repo.get_chapter(project_id, current_chapter)
    chapter_status = chapter.get("status") if chapter else "planned"

    running_current = _get_running_chapter_workflow(repo, project_id, current_chapter)
    if running_current:
        return _view_running_workflow_action(project_id, current_chapter, running_current)

    if chapter_status in ("planned", "scripted", "drafted", "polished", "revision"):
        return {
            "key": "generate_chapter",
            "label": f"生成第 {current_chapter} 章",
            "description": "资料已就绪，开始生成章节内容。",
            "primary": True,
            "action_url": f"/api/run/chapter",
            "method": "POST",
            "requires_confirmation": True,
        }

    if chapter_status in ("reviewed", "awaiting_publish"):
        return {
            "key": "review_chapter",
            "label": f"审核/发布第 {current_chapter} 章",
            "description": "章节已生成并通过审核，请最终确认发布。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/chapters/{current_chapter}",
            "method": "GET",
            "requires_confirmation": False,
        }

    if chapter_status == "published":
        # Check if there's a next chapter
        next_ch = current_chapter + 1
        next_chapter = repo.get_chapter(project_id, next_ch)
        if next_chapter is None:
            next_instruction = repo.get_instruction(project_id, next_ch)
            if next_instruction is not None:
                return {
                    "key": "continue_next_chapter",
                    "label": f"继续生成第 {next_ch} 章",
                    "description": "下一章写作指令已就绪，继续生成章节内容。",
                    "primary": True,
                    "action_url": f"/api/run/chapter",
                    "method": "POST",
                    "requires_confirmation": True,
                    "target_chapter": next_ch,
                }
            return {
                "key": "generate_arc_plan",
                "label": f"规划第 {next_ch} 章及后续",
                "description": "当前章节已发布，需要为下一批次生成章节规划。",
                "primary": True,
                "action_url": f"/api/projects/{project_id}/production/arc-plan",
                "method": "POST",
                "requires_confirmation": True,
            }
        running_next = _get_running_chapter_workflow(repo, project_id, next_ch)
        if running_next:
            return _view_running_workflow_action(project_id, next_ch, running_next)
        return {
            "key": "continue_next_chapter",
            "label": f"继续生成第 {next_ch} 章",
            "description": "当前章节已发布，继续下一章。",
            "primary": True,
            "action_url": f"/api/run/chapter",
            "method": "POST",
            "requires_confirmation": True,
            "target_chapter": next_ch,
        }

    return {
        "key": "none",
        "label": "暂无操作",
        "description": "项目当前没有明确的下一步生产动作。",
        "primary": False,
        "action_url": "",
        "method": "GET",
        "requires_confirmation": False,
    }


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/production-next")
async def get_production_next(request: Request, project_id: str) -> EnvelopeResponse:
    """Get the next production action for a project.

    Returns current project health, missing items, and a recommended next action.
    """
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if hasattr(repo, "reconcile_latest_blocked_runs_with_chapters"):
            repo.reconcile_latest_blocked_runs_with_chapters(project_id=project_id)

        current_chapter = project.get("current_chapter", 1)

        health = _build_health(repo, project_id, current_chapter)
        missing = _build_missing(health, project_id, current_chapter)
        timeout_minutes = getattr(settings.workflow, "task_timeout_minutes", 30)
        next_action = _determine_next_action(repo, project_id, health, current_chapter, timeout_minutes)
        target_chapter = next_action.get("target_chapter") or current_chapter
        health.update(_target_workflow_health(repo, project_id, target_chapter, timeout_minutes))

        # Build secondary actions
        actions = []
        if next_action["key"] != "generate_genesis" and not health["has_approved_genesis"]:
            actions.append({
                "key": "generate_genesis",
                "label": "生成项目设定",
                "description": "重新生成项目基础设定",
                "action_url": f"/api/projects/{project_id}/genesis/generate",
                "method": "POST",
            })
        if next_action["key"] != "generate_arc_plan" and health["has_approved_genesis"]:
            actions.append({
                "key": "generate_arc_plan",
                "label": "生成章节计划",
                "description": "为指定章节范围生成大纲和指令",
                "action_url": f"/api/projects/{project_id}/production/arc-plan",
                "method": "POST",
            })

        # v6.6.12: Build domain_result for production-next
        domain_result = _build_production_next_domain_result(health, next_action, missing)

        return envelope_response({
            "project_id": project_id,
            "current_chapter": current_chapter,
            "next_action": next_action,
            "health": health,
            "missing": missing,
            "actions": actions,
            "domain_result": domain_result,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取生产下一步失败: {str(e)}")


@router.get("/projects/{project_id}/production/health-summary")
async def get_production_health_summary(request: Request, project_id: str) -> EnvelopeResponse:
    """Return an author-facing health summary for the current project."""
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        timeout_minutes = getattr(settings.workflow, "task_timeout_minutes", 30)
        return envelope_response(_build_project_health_summary(repo, project_id, timeout_minutes))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目健康摘要失败: {str(e)}")


@router.post("/projects/{project_id}/production/auto-fill")
async def auto_fill(request: Request, project_id: str, body: AutoFillRequest) -> EnvelopeResponse:
    """AI auto-fill missing project context based on current gaps.

    Uses stub/deterministic generation when LLM mode is stub.
    Never overwrites existing user content.
    """
    from ..deps import get_repo, get_llm_mode, get_settings

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请设置 confirm=true 确认执行自动补齐")

        created = {
            "world_settings": 0,
            "characters": 0,
            "outlines": 0,
            "instructions": 0,
            "plot_holes": 0,
        }
        warnings: list[str] = []

        # Ensure genesis is approved; if not, suggest genesis first
        if not _has_approved_genesis(repo, project_id):
            warnings.append("项目创世尚未批准，建议先生成并批准创世设定")
            # Still allow stub fill for demo/testing

        if llm_mode == "stub":
            created, _ = _stub_autofill(repo, project, project_id, body.chapter_start, body.chapter_end)
        else:
            # Real LLM mode: use autonomous planner
            from ..deps import get_llm_provider, LLMConfigMissingError
            from ...agents.autonomous_planner import execute_autofill

            try:
                llm = get_llm_provider(request)
            except LLMConfigMissingError as e:
                return error_response("LLM_CONFIG_MISSING", str(e))

            created, warnings, missing_types = execute_autofill(repo, llm, project_id, body.chapter_start, body.chapter_end)

            # If LLM invocation or validation failed, return error
            _llm_error_keywords = ("调用失败", "校验失败", "非对象")
            if any(k in w for w in warnings for k in _llm_error_keywords):
                return error_response(
                    "LLM_OUTPUT_INVALID",
                    "LLM 生成内容解析失败，未写入任何资料",
                    details={"warnings": warnings},
                )

            # If any target missing type was not created, return error
            # (This distinguishes "LLM returned wrong types" from "items already existed")
            if missing_types and not any(created.get(t, 0) > 0 for t in missing_types):
                return error_response(
                    "NO_CONTENT_CREATED",
                    f"LLM 未生成缺失的资料类型: {', '.join(missing_types)}",
                    details={"warnings": warnings, "missing_types": missing_types},
                )

            # If nothing was actually created and it's not due to idempotent skips, return error
            total_created = sum(created.values())
            _idempotent_keywords = ("已存在", "已忽略", "跳过", "已有")
            has_idempotent_skip = any(k in w for w in warnings for k in _idempotent_keywords)
            if total_created == 0 and not has_idempotent_skip:
                return error_response(
                    "NO_CONTENT_CREATED",
                    "LLM 未生成任何有效资料",
                    details={"warnings": warnings},
                )

        return envelope_response({
            "filled": True,
            "scope": body.scope,
            "created": created,
            "warnings": warnings,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"自动补齐失败: {str(e)}")


@router.post("/projects/{project_id}/production/arc-plan")
async def arc_plan(request: Request, project_id: str, body: ArcPlanRequest) -> EnvelopeResponse:
    """Generate arc plan (outlines + instructions) for a chapter range.

    Does not regenerate genesis. Does not overwrite confirmed base settings.
    """
    from ..deps import get_repo, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请设置 confirm=true 确认执行 arc plan")

        if body.chapter_start > body.chapter_end:
            return error_response("VALIDATION_ERROR", "chapter_start 不能大于 chapter_end")

        if not _has_approved_genesis(repo, project_id):
            return error_response("GENESIS_REQUIRED", "请先完成并批准项目创世设定")

        created = {
            "outlines": 0,
            "instructions": 0,
            "plot_holes": 0,
        }
        warnings: list[str] = []

        # Determine arc segmentation
        arc_size = 10
        num_arcs = max(1, (body.chapter_end - body.chapter_start + 1 + arc_size - 1) // arc_size)

        if llm_mode == "stub":
            created = _stub_arc_plan(repo, project, project_id, body.chapter_start, body.chapter_end)
        else:
            # Real LLM mode: use autonomous planner
            from ..deps import get_llm_provider, LLMConfigMissingError
            from ...agents.autonomous_planner import execute_arc_plan

            try:
                llm = get_llm_provider(request)
            except LLMConfigMissingError as e:
                return error_response("LLM_CONFIG_MISSING", str(e))

            created, warnings = execute_arc_plan(repo, llm, project_id, body.chapter_start, body.chapter_end)

            # If LLM invocation or validation failed, return error
            _llm_error_keywords = ("调用失败", "校验失败", "非对象")
            if any(k in w for w in warnings for k in _llm_error_keywords):
                return error_response(
                    "LLM_OUTPUT_INVALID",
                    "LLM 生成内容解析失败，未写入任何资料",
                    details={"warnings": warnings},
                )

            # If nothing was actually created and it's not due to idempotent skips, return error
            total_created = sum(created.values())
            _idempotent_keywords = ("已存在", "已忽略", "跳过", "已有")
            has_idempotent_skip = any(k in w for w in warnings for k in _idempotent_keywords)
            if total_created == 0 and not has_idempotent_skip:
                return error_response(
                    "NO_CONTENT_CREATED",
                    "LLM 未生成任何有效资料",
                    details={"warnings": warnings},
                )

        return envelope_response({
            "planned": True,
            "chapter_start": body.chapter_start,
            "chapter_end": body.chapter_end,
            "created": created,
            "warnings": warnings,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"Arc plan 生成失败: {str(e)}")


# ---------------------------------------------------------------------------
# Stub Mode Helpers (extracted for run-auto reuse)
# ---------------------------------------------------------------------------


def _stub_autofill(repo, project: dict, project_id: str, chapter_start: int, chapter_end: int) -> tuple[dict[str, int], list[str]]:
    """Stub mode auto-fill logic.

    Returns:
        (created_counts, warnings) where created_counts maps type -> count.
    """
    created = {
        "world_settings": 0,
        "characters": 0,
        "outlines": 0,
        "instructions": 0,
        "plot_holes": 0,
    }
    warnings: list[str] = []

    # ── World Settings ──
    existing_ws = repo.list_world_settings(project_id)
    if len(existing_ws) == 0:
        repo.create_world_setting(
            project_id,
            category="地理",
            title="世界观基础",
            content=f"故事发生在{project.get('genre', '奇幻')}世界中，存在多个势力和未知领域。",
        )
        repo.create_world_setting(
            project_id,
            category="规则",
            title="力量体系",
            content="修炼体系分为九个大境界，每个境界有初期、中期、后期三个小阶段。",
        )
        created["world_settings"] = 2

    # ── Characters ──
    existing_chars = repo.list_characters(project_id, include_inactive=True)
    if len(existing_chars) == 0:
        repo.create_character(
            project_id,
            name="主角",
            role="protagonist",
            description=f"《{project.get('name', '未命名')}》的核心人物，性格坚毅，有着不为人知的过去。",
            traits="聪明、执着、重情义",
        )
        repo.create_character(
            project_id,
            name="挚友",
            role="supporting",
            description="主角的青梅竹马，性格开朗，擅长情报收集。",
            traits="机智、幽默、忠诚",
        )
        repo.create_character(
            project_id,
            name="反派首领",
            role="antagonist",
            description="幕后黑手，行事隐秘，目的不明。",
            traits="狡猾、冷酷、有魅力",
        )
        created["characters"] = 3

    # ── Outlines ──
    existing_outlines = repo.list_outlines(project_id)
    if len(existing_outlines) == 0:
        repo.create_outline(
            project_id,
            level="arc",
            sequence=1,
            title="开篇",
            content="主角出场，建立日常世界，引出核心冲突。",
            chapters_range=f"{chapter_start}-{min(chapter_start + 2, chapter_end)}",
        )
        repo.create_outline(
            project_id,
            level="arc",
            sequence=2,
            title="启程",
            content="主角踏上旅程，遇到第一个挑战和盟友。",
            chapters_range=f"{chapter_start + 3}-{min(chapter_start + 5, chapter_end)}",
        )
        repo.create_outline(
            project_id,
            level="arc",
            sequence=3,
            title="第一幕高潮",
            content="主角面对第一个重大考验，揭示更大的阴谋。",
            chapters_range=f"{chapter_start + 6}-{chapter_end}",
        )
        created["outlines"] = 3

    # ── Plot Holes ──
    existing_plots = repo.list_plot_holes(project_id)
    if len(existing_plots) == 0:
        repo.create_plot_hole(
            project_id,
            code="PH-001",
            type="悬念",
            title="主角身世之谜",
            description="主角的真实身份和家族秘密。",
            planted_chapter=chapter_start,
            planned_resolve_chapter=chapter_end + 10,
            status="planted",
        )
        repo.create_plot_hole(
            project_id,
            code="PH-002",
            type="伏笔",
            title="神秘信物",
            description="主角随身携带的古旧物品的来历。",
            planted_chapter=chapter_start,
            planned_resolve_chapter=chapter_start + 9,
            status="planted",
        )
        created["plot_holes"] = 2

    # ── Instructions ──
    for ch_num in range(chapter_start, chapter_end + 1):
        existing_inst = repo.get_instruction_by_chapter(project_id, ch_num)
        if existing_inst is None:
            word_target = 3000
            if project.get("target_words") and project.get("total_chapters_planned"):
                word_target = project["target_words"] // project["total_chapters_planned"]
            repo.create_instruction(
                project_id,
                chapter_number=ch_num,
                objective=f"第 {ch_num} 章写作指令",
                key_events=f"关键事件 {ch_num}",
                plots_to_plant="[]",
                plots_to_resolve="[]",
                emotion_tone="神秘" if ch_num == 1 else "紧张",
                ending_hook="",
                word_target=word_target,
                status="active",
            )
            created["instructions"] += 1

    return created, warnings


def _stub_arc_plan(repo, project: dict, project_id: str, chapter_start: int, chapter_end: int) -> dict[str, int]:
    """Stub mode arc-plan logic.

    Returns:
        created_counts mapping type -> count.
    """
    created = {
        "outlines": 0,
        "instructions": 0,
        "plot_holes": 0,
    }

    arc_size = 10
    num_arcs = max(1, (chapter_end - chapter_start + 1 + arc_size - 1) // arc_size)

    # Generate arc-level outlines
    for arc_idx in range(num_arcs):
        arc_start = chapter_start + arc_idx * arc_size
        arc_end = min(arc_start + arc_size - 1, chapter_end)

        # Check if an outline already covers this range
        existing_outlines = repo.list_outlines(project_id)
        range_str = f"{arc_start}-{arc_end}"
        has_covering = any(
            o.get("chapters_range") == range_str for o in existing_outlines
        )
        if not has_covering:
            arc_titles = ["新篇章", "暗流涌动", "危机四伏", "真相浮现", "最终决战"]
            arc_contents = [
                "故事进入新阶段，角色面临新的挑战。",
                "隐藏在暗处的势力开始行动，局势变得复杂。",
                "多重危机同时爆发，主角陷入绝境。",
                "关键线索串联起来，真相逐渐浮出水面。",
                "所有矛盾集中爆发，迎来阶段性高潮。",
            ]
            title = arc_titles[arc_idx % len(arc_titles)]
            content = arc_contents[arc_idx % len(arc_contents)]

            # Find next sequence
            max_seq = max((o.get("sequence", 0) for o in existing_outlines), default=0)

            repo.create_outline(
                project_id,
                level="arc",
                sequence=max_seq + 1,
                title=title,
                content=content,
                chapters_range=range_str,
            )
            created["outlines"] += 1

    # Generate chapter instructions
    word_target = 3000
    if project.get("target_words") and project.get("total_chapters_planned"):
        word_target = project["target_words"] // project["total_chapters_planned"]

    for ch_num in range(chapter_start, chapter_end + 1):
        existing_inst = repo.get_instruction_by_chapter(project_id, ch_num)
        if existing_inst is None:
            repo.create_instruction(
                project_id,
                chapter_number=ch_num,
                objective=f"第 {ch_num} 章写作指令",
                key_events=f"关键事件 {ch_num}",
                plots_to_plant="[]",
                plots_to_resolve="[]",
                emotion_tone="紧张",
                ending_hook="",
                word_target=word_target,
                status="active",
            )
            created["instructions"] += 1

    # Maybe add a new plot hole for the arc
    existing_plots = repo.list_plot_holes(project_id)
    max_ph = len(existing_plots)
    if max_ph < 5:
        repo.create_plot_hole(
            project_id,
            code=f"PH-{max_ph + 1:03d}",
            type="伏笔",
            title=f"新伏笔 {max_ph + 1}",
            description=f"在第 {chapter_start}-{chapter_end} 章期间埋下新的线索。",
            planted_chapter=chapter_start,
            planned_resolve_chapter=chapter_end + 5,
            status="planted",
        )
        created["plot_holes"] += 1

    return created


# ---------------------------------------------------------------------------
# v5.5.5: Autonomous Production Runner
# ---------------------------------------------------------------------------


class RunAutoRequest(BaseModel):
    """Request for autonomous production runner."""

    chapter_start: int | None = None
    chapter_end: int | None = None
    max_steps: int = 10
    dry_run: bool = False
    stop_on_review: bool = True
    confirm: bool = False
    max_consecutive_no_progress: int = 3
    max_retries_per_step: int = 2
    max_session_tokens: int | None = None


# Stop reasons
STOP_REASON_MAX_STEPS = "max_steps_reached"
STOP_REASON_REVIEW = "review_required"
STOP_REASON_BLOCKED = "blocked"
STOP_REASON_COMPLETED = "completed"
STOP_REASON_UNSUPPORTED = "unsupported_action"
STOP_REASON_FAILED = "step_failed"
STOP_REASON_NO_PROGRESS = "consecutive_no_progress"
STOP_REASON_REPEATED_FAILURE = "repeated_failure"
STOP_REASON_TOKEN_BUDGET = "token_budget_exceeded"


# v5.5.10: Guardrail helpers
_NO_PROGRESS_RESULTS = {"skipped", "failed", "blocked", "dry_run"}


def _check_consecutive_no_progress(steps: list[dict], max_count: int) -> bool:
    """Check if the last max_count steps all had no progress."""
    if len(steps) < max_count:
        return False
    recent = steps[-max_count:]
    return all(s.get("result") in _NO_PROGRESS_RESULTS for s in recent)


def _check_repeated_failure(steps: list[dict], action: str, target_chapter: int | None, max_count: int) -> bool:
    """Check if the same (action, target_chapter) has failed consecutively max_count times."""
    consecutive = 0
    for s in reversed(steps):
        if s.get("action") == action and s.get("target_chapter") == target_chapter and s.get("result") == "failed":
            consecutive += 1
        else:
            break
    return consecutive >= max_count


# ---------------------------------------------------------------------------
# v5.5.7: Shared auto-run core (used by both POST and SSE)
# ---------------------------------------------------------------------------


async def _auto_run_generator(
    request: Request,
    project_id: str,
    body: RunAutoRequest,
    session_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Async generator that yields auto-run events for both POST and SSE.

    Yields dicts with keys: event (str), data (dict).

    Args:
        session_id: Optional auto-run session id. When provided, the generator
            checks session status at each step (cooperative pause/cancel) and
            persists step records to the database.
    """
    from ..deps import get_repo, get_llm_mode, get_settings

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)
        settings = get_settings(request)
        timeout_minutes = getattr(settings.workflow, "task_timeout_minutes", 30)

        project = repo.get_project(project_id)
        if not project:
            yield {
                "event": "auto_run_error",
                "data": {
                    "project_id": project_id,
                    "error": "PROJECT_NOT_FOUND",
                    "message": f"项目 '{project_id}' 不存在",
                },
            }
            return

        # Validate session belongs to project when provided
        if session_id:
            session = repo.get_auto_run_session(session_id)
            if not session or session.get("project_id") != project_id:
                yield {
                    "event": "auto_run_error",
                    "data": {
                        "project_id": project_id,
                        "error": "SESSION_NOT_FOUND",
                        "message": f"会话 '{session_id}' 不存在或不属于该项目",
                    },
                }
                return

        if not body.confirm:
            yield {
                "event": "auto_run_error",
                "data": {
                    "project_id": project_id,
                    "error": "CONFIRM_REQUIRED",
                    "message": "请设置 confirm=true 确认执行自动生产",
                },
            }
            return

        # Validate LLM config for real mode
        if llm_mode == "real":
            try:
                from ..deps import get_llm_provider
                get_llm_provider(request)
            except Exception as e:
                yield {
                    "event": "auto_run_error",
                    "data": {
                        "project_id": project_id,
                        "error": "LLM_CONFIG_MISSING",
                        "message": str(e),
                    },
                }
                return

        # Initialize tracking
        steps: list[dict] = []
        chapters_touched: set[int] = set()
        current_chapter = project.get("current_chapter", 1)

        # Determine chapter range
        ch_start = body.chapter_start if body.chapter_start is not None else current_chapter
        ch_end = body.chapter_end if body.chapter_end is not None else ch_start + 9

        # P2-1: When a range is explicitly requested, start from chapter_start
        # so that generate_chapter/continue_next_chapter actions target the
        # requested range instead of falling back to project.current_chapter.
        if body.chapter_start is not None:
            active_chapter = ch_start
        else:
            active_chapter = current_chapter

        # Execute steps
        step_count = 0
        stop_reason = ""
        final_next_action: dict | None = None
        session_tokens_used = 0
        session_token_limit = (
            body.max_session_tokens
            if body.max_session_tokens is not None
            else settings.runtime_budget.auto_run_token_limit
        )

        # v5.5.9: Resume state from persisted session steps
        if session_id:
            existing_steps = repo.list_auto_run_steps(session_id)
            if existing_steps:
                steps = [
                    {
                        "step": s["step_number"],
                        "action": s["action"],
                        "label": s["label"],
                        "target_chapter": s.get("target_chapter"),
                        "result": s.get("result", "unknown"),
                        "warnings": s.get("warnings", []),
                        "error": s.get("error"),
                    }
                    for s in existing_steps
                ]
                step_count = len(steps)
                for s in steps:
                    if s.get("target_chapter") is not None:
                        chapters_touched.add(s["target_chapter"])
            # Recompute active_chapter from project state in case it advanced
            # while the session was paused/disconnected.
            active_chapter = project.get("current_chapter", active_chapter)

        yield {
            "event": "auto_run_started",
            "data": {
                "project_id": project_id,
                "chapter_start": ch_start,
                "chapter_end": ch_end,
                "max_steps": body.max_steps,
                "dry_run": body.dry_run,
                "stop_on_review": body.stop_on_review,
                "max_session_tokens": session_token_limit,
            },
        }
        if session_id:
            repo.update_auto_run_session_status(
                session_id, None, current_step=step_count, last_event="auto_run_started"
            )

        while step_count < body.max_steps:
            # v5.5.8: Cooperative pause/cancel check
            if session_id:
                session = repo.get_auto_run_session(session_id)
                if session and session.get("status") == "cancelled":
                    yield {
                        "event": "auto_run_stopped",
                        "data": {
                            "project_id": project_id,
                            "stop_reason": "cancelled",
                            "steps_executed": step_count,
                            "steps": steps,
                            "chapters_touched": sorted(list(chapters_touched)),
                            "final_next_action": final_next_action,
                            "session_tokens_used": session_tokens_used,
                            "max_session_tokens": session_token_limit,
                        },
                    }
                    return
                if session and session.get("status") == "paused":
                    yield {
                        "event": "auto_run_stopped",
                        "data": {
                            "project_id": project_id,
                            "stop_reason": "paused",
                            "steps_executed": step_count,
                            "steps": steps,
                            "chapters_touched": sorted(list(chapters_touched)),
                            "final_next_action": final_next_action,
                            "session_tokens_used": session_tokens_used,
                            "max_session_tokens": session_token_limit,
                        },
                    }
                    return
                repo.update_auto_run_session_status(
                    session_id, None, current_step=step_count
                )

            # Get current state using active_chapter for range-aware decisions
            health = _build_health(repo, project_id, active_chapter)
            next_action = _determine_next_action(repo, project_id, health, active_chapter, timeout_minutes)

            # Check if we should stop
            if next_action["key"] == "none":
                stop_reason = STOP_REASON_COMPLETED
                final_next_action = next_action
                break

            # Check for human-review-required actions
            if next_action["key"] in ("review_genesis", "review_chapter", "apply_memory_updates"):
                stop_reason = STOP_REASON_REVIEW
                final_next_action = next_action
                break

            if next_action["key"] in ("wait_genesis",):
                stop_reason = STOP_REASON_BLOCKED
                final_next_action = next_action
                break

            # P2-1: Range-aware target selection — derive effective target for all action types
            effective_target = next_action.get("target_chapter")
            if effective_target is None and next_action["key"] in ("generate_chapter", "continue_next_chapter"):
                # These actions fall back to active_chapter when target_chapter is absent
                effective_target = active_chapter
            elif effective_target is None and next_action["key"] == "generate_arc_plan":
                # Arc plan targets the next chapter after active_chapter
                effective_target = active_chapter + 1

            if effective_target is not None and (effective_target < ch_start or effective_target > ch_end):
                stop_reason = STOP_REASON_COMPLETED
                final_next_action = next_action
                step_count += 1
                skipped_step = {
                    "step": step_count,
                    "action": next_action["key"],
                    "label": next_action["label"],
                    "target_chapter": effective_target,
                    "result": "skipped",
                    "warnings": [f"目标章节 {effective_target} 超出请求范围 {ch_start}-{ch_end}"],
                }
                steps.append(skipped_step)
                yield {
                    "event": "step_completed",
                    "data": {
                        "project_id": project_id,
                        "step": skipped_step["step"],
                        "action": skipped_step["action"],
                        "label": skipped_step["label"],
                        "target_chapter": skipped_step["target_chapter"],
                        "result": "skipped",
                        "warnings": skipped_step["warnings"],
                        "error": None,
                        "steps_executed": step_count,
                        "chapters_touched": sorted(list(chapters_touched)),
                    },
                }
                if session_id:
                    repo.update_auto_run_session_status(
                        session_id, None, current_step=step_count, last_event="step_completed"
                    )
                break

            # P2-2: Stop if active_chapter itself is outside the requested range.
            # This prevents no-target actions (e.g. generate_missing_context) from
            # running after the requested range has been exhausted.
            if active_chapter > ch_end:
                stop_reason = STOP_REASON_COMPLETED
                final_next_action = next_action
                break

            # Dry run: just record the action, don't execute
            if body.dry_run:
                step_count += 1
                steps.append({
                    "step": step_count,
                    "action": next_action["key"],
                    "label": next_action["label"],
                    "target_chapter": effective_target,
                    "result": "dry_run",
                    "warnings": [],
                })
                # v5.5.8: Persist dry-run step
                if session_id:
                    repo.create_auto_run_step(
                        session_id, step_count, next_action["key"], next_action["label"], effective_target
                    )
                    repo.complete_auto_run_step(session_id, step_count, "dry_run", warnings=[])
                yield {
                    "event": "step_completed",
                    "data": {
                        "project_id": project_id,
                        "step": step_count,
                        "action": next_action["key"],
                        "label": next_action["label"],
                        "target_chapter": effective_target,
                        "result": "dry_run",
                        "warnings": [],
                        "error": None,
                        "steps_executed": step_count,
                        "chapters_touched": sorted(list(chapters_touched)),
                    },
                }
                if session_id:
                    repo.update_auto_run_session_status(
                        session_id, None, current_step=step_count, last_event="step_completed"
                    )
                stop_reason = "dry_run_preview"
                break

            # v5.5.10: Repeated failure guardrail — stop before executing if the
            # same (action, target_chapter) has already failed max_retries_per_step times.
            if _check_repeated_failure(steps, next_action["key"], effective_target, body.max_retries_per_step):
                stop_reason = STOP_REASON_REPEATED_FAILURE
                final_next_action = next_action
                if session_id:
                    repo.update_auto_run_session_status(
                        session_id, "stopped", stop_reason=stop_reason, current_step=step_count
                    )
                yield {
                    "event": "auto_run_stopped",
                    "data": {
                        "project_id": project_id,
                        "stop_reason": stop_reason,
                        "steps_executed": step_count,
                        "steps": steps,
                        "chapters_touched": sorted(list(chapters_touched)),
                        "final_next_action": final_next_action,
                        "session_tokens_used": session_tokens_used,
                        "max_session_tokens": session_token_limit,
                    },
                }
                return

            # v5.5.8: Persist step start
            if session_id:
                repo.create_auto_run_step(
                    session_id,
                    step_number=step_count + 1,
                    action=next_action["key"],
                    label=next_action["label"],
                    target_chapter=effective_target,
                )

            # Yield step_started
            yield {
                "event": "step_started",
                "data": {
                    "project_id": project_id,
                    "step": step_count + 1,
                    "action": next_action["key"],
                    "label": next_action["label"],
                    "target_chapter": effective_target,
                },
            }
            if session_id:
                repo.update_auto_run_session_status(
                    session_id, None, current_step=step_count, last_event="step_started"
                )

            # Execute the action
            step_result = await _execute_auto_step(
                request, repo, settings, llm_mode, project_id, next_action, ch_start, ch_end, active_chapter
            )

            step_count += 1  # Count attempted steps consistently
            step_tokens = int(step_result.get("total_tokens", 0) or 0)
            session_tokens_used += step_tokens

            # Use the most accurate target chapter available (step_result overrides effective fallback)
            _resolved_target = step_result.get("target_chapter") if step_result.get("target_chapter") is not None else effective_target

            steps.append({
                "step": step_count,
                "action": next_action["key"],
                "label": next_action["label"],
                "target_chapter": _resolved_target,
                "result": step_result.get("result", "unknown"),
                "warnings": step_result.get("warnings", []),
                "error": step_result.get("error"),
                "total_tokens": step_tokens,
            })

            if _resolved_target is not None:
                chapters_touched.add(_resolved_target)

            # Check for step failure — P2-3: return AUTO_RUN_STEP_FAILED error
            if step_result.get("result") == "failed":
                # v5.5.8: Persist step failure
                if session_id:
                    repo.complete_auto_run_step(
                        session_id, step_count, "failed",
                        warnings=step_result.get("warnings", []),
                        error=step_result.get("error"),
                    )
                    repo.update_auto_run_session_status(
                        session_id, "failed", stop_reason=STOP_REASON_FAILED, current_step=step_count
                    )
                yield {
                    "event": "step_failed",
                    "data": {
                        "project_id": project_id,
                        "step": step_count,
                        "action": next_action["key"],
                        "label": next_action["label"],
                        "target_chapter": _resolved_target,
                        "result": "failed",
                        "warnings": step_result.get("warnings", []),
                        "error": step_result.get("error"),
                        "steps_executed": step_count,
                        "chapters_touched": sorted(list(chapters_touched)),
                        "total_tokens": step_tokens,
                        "session_tokens_used": session_tokens_used,
                        "max_session_tokens": session_token_limit,
                    },
                }
                # v5.5.9: last_event updated via status update below
                yield {
                    "event": "auto_run_stopped",
                    "data": {
                        "project_id": project_id,
                        "stop_reason": STOP_REASON_FAILED,
                        "steps_executed": step_count,
                        "steps": steps,
                        "chapters_touched": sorted(list(chapters_touched)),
                        "final_next_action": next_action,
                        "session_tokens_used": session_tokens_used,
                        "max_session_tokens": session_token_limit,
                    },
                }
                return

            yield {
                "event": "step_completed",
                "data": {
                    "project_id": project_id,
                    "step": step_count,
                    "action": next_action["key"],
                    "label": next_action["label"],
                    "target_chapter": _resolved_target,
                    "result": step_result.get("result", "unknown"),
                    "warnings": step_result.get("warnings", []),
                    "error": step_result.get("error"),
                    "total_tokens": step_tokens,
                    "steps_executed": step_count,
                    "chapters_touched": sorted(list(chapters_touched)),
                    "session_tokens_used": session_tokens_used,
                    "max_session_tokens": session_token_limit,
                },
            }

            # v5.5.8: Persist step completion
            if session_id:
                repo.complete_auto_run_step(
                    session_id, step_count,
                    result=step_result.get("result", "unknown"),
                    warnings=step_result.get("warnings", []),
                    error=step_result.get("error"),
                )
                repo.update_auto_run_session_status(
                    session_id, None, current_step=step_count, last_event="step_completed"
                )

            if session_token_limit and session_tokens_used > session_token_limit:
                stop_reason = STOP_REASON_TOKEN_BUDGET
                final_next_action = next_action
                if session_id:
                    repo.update_auto_run_session_status(
                        session_id, "stopped", stop_reason=stop_reason, current_step=step_count
                    )
                break

            # v5.5.10: No-progress guardrail — stop if the last N steps all had no progress
            if _check_consecutive_no_progress(steps, body.max_consecutive_no_progress):
                stop_reason = STOP_REASON_NO_PROGRESS
                final_next_action = next_action
                if session_id:
                    repo.update_auto_run_session_status(
                        session_id, "stopped", stop_reason=stop_reason, current_step=step_count
                    )
                break

            # Check for unsupported action
            if step_result.get("result") == "unsupported":
                stop_reason = STOP_REASON_UNSUPPORTED
                final_next_action = next_action
                break

            # Check for review-required after generate_chapter
            if next_action["key"] in ("generate_chapter", "continue_next_chapter"):
                if step_result.get("requires_human") or step_result.get("awaiting_publish"):
                    if body.stop_on_review:
                        stop_reason = STOP_REASON_REVIEW
                        final_next_action = next_action
                        break

            # Update active_chapter and project current_chapter if chapter was published
            if step_result.get("chapter_status") == "published":
                published_ch = _resolved_target if _resolved_target is not None else active_chapter
                active_chapter = published_ch + 1
                current_chapter = active_chapter
                repo.update_project(project_id, current_chapter=current_chapter)

        # Determine final status
        if body.dry_run:
            status = "dry_run"
        elif stop_reason in (STOP_REASON_REVIEW, STOP_REASON_BLOCKED, STOP_REASON_UNSUPPORTED):
            status = "stopped"
        elif stop_reason == STOP_REASON_TOKEN_BUDGET:
            status = "stopped"
        else:
            status = "completed"

        # If we hit max_steps, mark it
        if step_count >= body.max_steps and not stop_reason:
            stop_reason = STOP_REASON_MAX_STEPS
            status = "stopped"
            # Get final next action
            health = _build_health(repo, project_id, current_chapter)
            final_next_action = _determine_next_action(repo, project_id, health, current_chapter, timeout_minutes)

        final_event_name = "auto_run_stopped" if status == "stopped" else "auto_run_completed"

        # v5.5.8: Update session final state
        if session_id:
            repo.update_auto_run_session_status(
                session_id, status, stop_reason=stop_reason, current_step=step_count
            )

        yield {
            "event": final_event_name,
            "data": {
                "project_id": project_id,
                "status": status,
                "steps": steps,
                "final_next_action": final_next_action,
                "chapters_touched": sorted(list(chapters_touched)),
                "stop_reason": stop_reason,
                "steps_executed": step_count,
                "session_tokens_used": session_tokens_used,
                "max_session_tokens": session_token_limit,
            },
        }

    except Exception as e:
        # v5.5.8: Mark session as failed on unexpected error
        if session_id:
            repo.update_auto_run_session_status(
                session_id, "failed", stop_reason="INTERNAL_ERROR", current_step=step_count
            )
        yield {
            "event": "auto_run_error",
            "data": {
                "project_id": project_id,
                "error": "INTERNAL_ERROR",
                "message": f"自动生产运行失败: {str(e)}",
            },
        }


@router.post("/projects/{project_id}/production/run-auto")
async def run_auto_production(request: Request, project_id: str, body: RunAutoRequest) -> EnvelopeResponse:
    """v5.5.5: Autonomous production runner.

    Executes production steps automatically based on production-next recommendations.
    Stops on: max_steps, review/publish requirements, blocking states, or errors.

    IMPORTANT: Never auto-publishes chapters. Real mode stops at awaiting_publish/review.
    """
    try:
        events: list[dict] = []
        async for event in _auto_run_generator(request, project_id, body):
            events.append(event)

        # Handle any auto_run_error event (not just the first one)
        error_events = [e for e in events if e["event"] == "auto_run_error"]
        if error_events:
            err_data = error_events[0]["data"]
            domain_result = failed(
                err_data["message"],
                user_message=err_data["message"],
                retryable=True,
                next_action="retry_auto_run",
                action_label="重试自动生产",
                details={
                    "project_id": project_id,
                    "error_code": err_data["error"],
                },
                flags={"auto_run_failed": True},
            ).to_dict()
            return error_response(
                err_data["error"],
                err_data["message"],
                details={"domain_result": domain_result},
            )

        # Check for step failure
        failed_events = [e for e in events if e["event"] == "step_failed"]
        if failed_events:
            failed_data = failed_events[0]["data"]
            all_steps = [
                {
                    "step": e["data"]["step"],
                    "action": e["data"]["action"],
                    "label": e["data"]["label"],
                    "target_chapter": e["data"].get("target_chapter"),
                    "result": e["data"]["result"],
                    "warnings": e["data"].get("warnings", []),
                    "error": e["data"].get("error"),
                }
                for e in events
                if e["event"] in ("step_completed", "step_failed")
            ]
            domain_result = failed(
                f"第 {failed_data['step']} 步执行失败",
                user_message=(
                    f"第 {failed_data['step']} 步执行失败："
                    f"{failed_data.get('error', '未知错误')}"
                ),
                retryable=True,
                next_action="retry_auto_run_step",
                action_label="重试失败步骤",
                details={
                    "step": failed_data["step"],
                    "action": failed_data["action"],
                    "stop_reason": STOP_REASON_FAILED,
                    "steps_executed": failed_data["steps_executed"],
                },
                flags={"auto_run_step_failed": True},
            ).to_dict()
            return error_response(
                "AUTO_RUN_STEP_FAILED",
                f"第 {failed_data['step']} 步执行失败: {failed_data.get('error', '未知错误')}",
                details={
                    "step": failed_data["step"],
                    "action": failed_data["action"],
                    "steps": all_steps,
                    "chapters_touched": failed_data.get("chapters_touched", []),
                    "stop_reason": STOP_REASON_FAILED,
                    "steps_executed": failed_data["steps_executed"],
                    "domain_result": domain_result,
                },
            )

        # Find final event
        final_event = events[-1]
        data = final_event["data"]

        # v6.6.12: Build domain_result for run-auto
        domain_result = _build_run_auto_domain_result(data)

        return envelope_response({
            "status": data["status"],
            "steps": data["steps"],
            "final_next_action": data.get("final_next_action"),
            "chapters_touched": data.get("chapters_touched", []),
            "stop_reason": data["stop_reason"],
            "steps_executed": data["steps_executed"],
            "session_tokens_used": data.get("session_tokens_used", 0),
            "max_session_tokens": data.get("max_session_tokens"),
            "domain_result": domain_result,
        })

    except Exception as e:
        message = f"自动生产运行失败: {str(e)}"
        domain_result = failed(
            message,
            user_message="自动生产运行失败，请检查日志后重试",
            retryable=True,
            next_action="retry_auto_run",
            action_label="重试自动生产",
            flags={"auto_run_failed": True},
        ).to_dict()
        return error_response(
            "INTERNAL_ERROR",
            message,
            details={"domain_result": domain_result},
        )


@router.get("/projects/{project_id}/production/run-auto/stream")
async def run_auto_stream(
    request: Request,
    project_id: str,
    chapter_start: int | None = None,
    chapter_end: int | None = None,
    max_steps: int = 10,
    dry_run: bool = False,
    stop_on_review: bool = True,
    confirm: bool = False,
    max_session_tokens: int | None = None,
    session_id: str | None = None,
) -> StreamingResponse:
    """v5.5.7: Real-time production monitor via SSE.

    Streams auto-run events as they happen.
    v5.5.8: Supports session_id for control-loop integration.
    """
    import json
    from ..deps import get_repo

    repo = get_repo(request)

    # Validate session when provided
    if session_id:
        session = repo.get_auto_run_session(session_id)
        if not session or session.get("project_id") != project_id:
            async def error_stream():
                err = {
                    "event": "auto_run_error",
                    "data": {
                        "project_id": project_id,
                        "error": "SESSION_NOT_FOUND",
                        "message": f"会话 '{session_id}' 不存在或不属于该项目",
                    },
                }
                yield f"event: {err['event']}\ndata: {json.dumps(err['data'], ensure_ascii=False)}\n\n"
            return StreamingResponse(error_stream(), media_type="text/event-stream")

        # Do NOT auto-resume paused sessions here; resume endpoint handles that.
        if session.get("status") == "paused":
            async def paused_stream():
                evt = {
                    "event": "auto_run_stopped",
                    "data": {
                        "project_id": project_id,
                        "stop_reason": "paused",
                        "steps_executed": session.get("current_step", 0),
                        "steps": [],
                        "chapters_touched": [],
                    },
                }
                yield f"event: {evt['event']}\ndata: {json.dumps(evt['data'], ensure_ascii=False)}\n\n"
            return StreamingResponse(paused_stream(), media_type="text/event-stream")

    body = RunAutoRequest(
        chapter_start=chapter_start,
        chapter_end=chapter_end,
        max_steps=max_steps,
        dry_run=dry_run,
        stop_on_review=stop_on_review,
        confirm=confirm,
        max_session_tokens=max_session_tokens,
    )

    async def event_stream():
        import asyncio
        try:
            async for event in _auto_run_generator(request, project_id, body, session_id=session_id):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            # v5.5.9: Client disconnected — mark session as paused so user can resume
            if session_id:
                repo.update_auto_run_session_status(
                    session_id, "paused", stop_reason="client_disconnected"
                )
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _normalize_llm_warnings(
    created: dict, warnings: list[str], missing_types: list[str] | None = None
) -> tuple[str, str | None]:
    """Normalize LLM warnings into (status, error_message) for run-auto steps.

    Reuses the same error detection logic as the standalone auto-fill/arc-plan routes.
    When missing_types is provided, requires at least one missing target type to be created.
    Returns ("success", None) if no error, ("failed", error_message) otherwise.
    """
    _llm_error_keywords = ("调用失败", "校验失败", "非对象")
    if any(k in w for w in warnings for k in _llm_error_keywords):
        return "failed", "LLM 生成内容解析失败，未写入任何资料"

    total_created = sum(created.values())
    _idempotent_keywords = ("已存在", "已忽略", "跳过", "已有")
    has_idempotent_skip = any(k in w for w in warnings for k in _idempotent_keywords)

    # P2-2: If missing_types is provided, require at least one missing target type
    # to be created — matching the standalone route logic.
    if missing_types is not None:
        if not any(created.get(t, 0) > 0 for t in missing_types):
            return "failed", f"LLM 未生成缺失的资料类型: {', '.join(missing_types)}"

    if total_created == 0 and not has_idempotent_skip:
        return "failed", "LLM 未生成任何有效资料"

    return "success", None


async def _execute_auto_step(
    request: Request,
    repo,
    settings,
    llm_mode: str,
    project_id: str,
    next_action: dict,
    ch_start: int,
    ch_end: int,
    active_chapter: int,
) -> dict:
    """Execute a single auto-production step.

    Returns:
        Dict with result, warnings, error, target_chapter, chapter_status, requires_human, awaiting_publish.
    """
    action_key = next_action["key"]
    target_chapter = next_action.get("target_chapter")
    result = {"result": "unknown", "warnings": [], "target_chapter": target_chapter}

    try:
        # ── generate_missing_context ──
        if action_key == "generate_missing_context":
            project = repo.get_project(project_id)
            if llm_mode == "stub":
                created, warnings = _stub_autofill(repo, project, project_id, ch_start, ch_end)
                missing_types = None
            else:
                from ..deps import get_llm_provider
                from ...agents.autonomous_planner import execute_autofill
                llm = get_llm_provider(request)
                created, warnings, missing_types = execute_autofill(repo, llm, project_id, ch_start, ch_end)

            # P2-2: Normalize LLM failures same as standalone route, with missing_types
            status, error_msg = _normalize_llm_warnings(created, warnings, missing_types)
            result["result"] = status
            if error_msg:
                result["error"] = error_msg
            result["warnings"] = warnings
            result["created"] = created
            return result

        # ── generate_arc_plan ──
        if action_key == "generate_arc_plan":
            project = repo.get_project(project_id)
            # P2-1: Use target_chapter if provided (set by range guard), otherwise
            # fall back to active_chapter + 1 to stay within the requested range.
            next_ch = target_chapter or (active_chapter + 1)
            if llm_mode == "stub":
                created = _stub_arc_plan(repo, project, project_id, next_ch, next_ch + 9)
                warnings: list[str] = []
            else:
                from ..deps import get_llm_provider
                from ...agents.autonomous_planner import execute_arc_plan
                llm = get_llm_provider(request)
                created, warnings = execute_arc_plan(repo, llm, project_id, next_ch, next_ch + 9)

            # P2-2: Normalize LLM failures same as standalone route
            status, error_msg = _normalize_llm_warnings(created, warnings)
            result["result"] = status
            if error_msg:
                result["error"] = error_msg
            result["warnings"] = warnings
            result["created"] = created
            return result

        # ── generate_chapter / continue_next_chapter ──
        if action_key in ("generate_chapter", "continue_next_chapter"):
            chapter_num = target_chapter or active_chapter
            result["target_chapter"] = chapter_num

            # v5.5.15: Unified run guard — same checks as POST /run/chapter
            from ._run_guards import check_chapter_run_guard

            guard_error = check_chapter_run_guard(repo, project_id, chapter_num)
            if guard_error:
                result["result"] = "skipped"
                result["error"] = guard_error.message
                return result

            # Use run_with_graph
            from ...workflow.runner import run_with_graph
            import asyncio

            run_result = await asyncio.to_thread(
                run_with_graph,
                project_id=project_id,
                chapter_number=chapter_num,
                settings=settings,
                repo=repo,
                llm_mode=llm_mode,
            )

            result["chapter_status"] = run_result.get("chapter_status")
            result["requires_human"] = run_result.get("requires_human", False)
            result["awaiting_publish"] = run_result.get("awaiting_publish", False)
            result["prompt_tokens"] = run_result.get("prompt_tokens", 0)
            result["completion_tokens"] = run_result.get("completion_tokens", 0)
            result["total_tokens"] = run_result.get("total_tokens", 0)
            result["duration_ms"] = run_result.get("duration_ms", 0)

            if run_result.get("error"):
                result["result"] = "failed"
                result["error"] = run_result["error"]
            elif run_result.get("context_incomplete"):
                result["result"] = "failed"
                result["error"] = "项目资料不完整"
                result["warnings"] = run_result.get("missing", [])
            else:
                result["result"] = "success"

            return result

        # ── recover_blocked_run ──
        if action_key == "recover_blocked_run":
            chapter_num = target_chapter or active_chapter
            result["target_chapter"] = chapter_num

            # Reset the chapter
            chapter = repo.get_chapter(project_id, chapter_num)
            if not chapter:
                result["result"] = "failed"
                result["error"] = f"章节 {chapter_num} 不存在"
                return result

            current_status = chapter.get("status", "")
            if current_status not in ("blocking", "revision"):
                result["result"] = "failed"
                result["error"] = f"章节状态为 '{current_status}'，无法重置"
                return result

            reset_ok = repo.reset_chapter(project_id, chapter_num)
            if not reset_ok:
                result["result"] = "failed"
                result["error"] = "重置章节失败"
                return result

            if hasattr(repo, "recover_active_workflow_runs_for_chapter"):
                repo.recover_active_workflow_runs_for_chapter(project_id, chapter_num)
            else:
                repo.invalidate_running_workflow_runs_for_chapter(
                    project_id,
                    chapter_num,
                    "章节已重置，旧运行已作废，请重新开始新的工作流。",
                )

            # Clear checkpoint
            from ...workflow.checkpoint import delete_checkpoint_thread
            delete_checkpoint_thread(repo.db_path, project_id, chapter_num)

            result["result"] = "success"
            return result

        # ── apply_memory_updates ──
        if action_key == "apply_memory_updates":
            # This requires human review, return as blocked
            result["result"] = "blocked"
            result["error"] = "记忆更新需要人工审核后应用"
            return result

        # ── Unsupported actions ──
        # generate_genesis, review_genesis, review_chapter, wait_genesis, none
        result["result"] = "unsupported"
        result["error"] = f"动作 '{action_key}' 需要人工处理"
        return result

    except Exception as e:
        result["result"] = "failed"
        result["error"] = str(e)[:200]
        return result


# ---------------------------------------------------------------------------
# v5.5.8: Auto-Run Control Loop — Session Management
# ---------------------------------------------------------------------------


class RetryStepRequest(BaseModel):
    """Request to retry a failed step."""

    step_number: int


@router.post("/projects/{project_id}/production/run-auto/start")
async def run_auto_start(request: Request, project_id: str, body: RunAutoRequest) -> EnvelopeResponse:
    """Create an auto-run session and return session info + stream URL.

    The actual execution happens via the SSE stream endpoint using the
    returned session_id.
    """
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请设置 confirm=true 确认执行自动生产")

        session = repo.create_auto_run_session(
            project_id=project_id,
            chapter_start=body.chapter_start,
            chapter_end=body.chapter_end,
            max_steps=body.max_steps,
            dry_run=body.dry_run,
            stop_on_review=body.stop_on_review,
        )

        stream_url = (
            f"/api/projects/{project_id}/production/run-auto/stream"
            f"?session_id={session['id']}"
            f"&confirm=true"
            f"&max_steps={body.max_steps}"
            f"&dry_run={str(body.dry_run).lower()}"
            f"&stop_on_review={str(body.stop_on_review).lower()}"
        )
        if body.chapter_start is not None:
            stream_url += f"&chapter_start={body.chapter_start}"
        if body.chapter_end is not None:
            stream_url += f"&chapter_end={body.chapter_end}"
        if body.max_session_tokens is not None:
            stream_url += f"&max_session_tokens={body.max_session_tokens}"

        return envelope_response({
            "session_id": session["id"],
            "project_id": project_id,
            "status": session["status"],
            "stream_url": stream_url,
            "config": {
                "chapter_start": body.chapter_start,
                "chapter_end": body.chapter_end,
                "max_steps": body.max_steps,
                "max_session_tokens": body.max_session_tokens,
                "dry_run": body.dry_run,
                "stop_on_review": body.stop_on_review,
            },
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建自动生产会话失败: {str(e)}")


@router.get("/projects/{project_id}/production/run-auto/sessions")
async def list_auto_run_sessions(request: Request, project_id: str) -> EnvelopeResponse:
    """List recent auto-run sessions for a project."""
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        sessions = repo.list_auto_run_sessions(project_id, limit=20)
        # Light serialization: exclude heavy fields
        return envelope_response({
            "sessions": sessions,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取会话列表失败: {str(e)}")


@router.get("/projects/{project_id}/production/run-auto/sessions/{session_id}")
async def get_auto_run_session_detail(
    request: Request, project_id: str, session_id: str
) -> EnvelopeResponse:
    """Get a single auto-run session with its steps."""
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)

        session = repo.get_auto_run_session(session_id)
        if not session or session.get("project_id") != project_id:
            return error_response("SESSION_NOT_FOUND", "会话不存在")

        steps = repo.list_auto_run_steps(session_id)

        return envelope_response({
            "session": session,
            "steps": steps,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取会话详情失败: {str(e)}")


@router.post("/projects/{project_id}/production/run-auto/sessions/{session_id}/cancel")
async def cancel_auto_run_session(
    request: Request, project_id: str, session_id: str
) -> EnvelopeResponse:
    """Cancel a running auto-run session.

    Cooperative cancel: the generator checks status at the next step boundary
    and stops. This does not interrupt an in-flight LLM call.
    """
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)

        session = repo.get_auto_run_session(session_id)
        if not session or session.get("project_id") != project_id:
            return error_response("SESSION_NOT_FOUND", "会话不存在")

        if session.get("status") not in ("running", "paused"):
            return error_response("INVALID_STATE", f"当前状态 '{session.get('status')}' 不可取消")

        repo.update_auto_run_session_status(session_id, "cancelled", stop_reason="cancelled")
        return envelope_response({"cancelled": True, "session_id": session_id})
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"取消会话失败: {str(e)}")


@router.post("/projects/{project_id}/production/run-auto/sessions/{session_id}/pause")
async def pause_auto_run_session(
    request: Request, project_id: str, session_id: str
) -> EnvelopeResponse:
    """Pause a running auto-run session.

    Cooperative pause: the generator checks status at the next step boundary
    and yields a stopped event with stop_reason='paused'.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        session = repo.get_auto_run_session(session_id)
        if not session or session.get("project_id") != project_id:
            return error_response("SESSION_NOT_FOUND", "会话不存在")

        if session.get("status") != "running":
            return error_response("INVALID_STATE", f"当前状态 '{session.get('status')}' 不可暂停")

        repo.update_auto_run_session_status(session_id, "paused")
        return envelope_response({"paused": True, "session_id": session_id})
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"暂停会话失败: {str(e)}")


class ResumeRequest(BaseModel):
    """Request to resume a paused session."""

    extra_steps: int = 5


@router.post("/projects/{project_id}/production/run-auto/sessions/{session_id}/resume")
async def resume_auto_run_session(
    request: Request, project_id: str, session_id: str, body: ResumeRequest | None = None
) -> EnvelopeResponse:
    """Resume a paused auto-run session.

    Returns a stream_url for the client to reconnect and continue execution.
    v5.5.9: Supports extra_steps to extend max_steps on resume.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        session = repo.get_auto_run_session(session_id)
        if not session or session.get("project_id") != project_id:
            return error_response("SESSION_NOT_FOUND", "会话不存在")

        if session.get("status") not in ("paused", "stopped", "failed", "dry_run"):
            return error_response("INVALID_STATE", f"当前状态 '{session.get('status')}' 不可继续")

        extra = body.extra_steps if body else 5
        new_max_steps = session.get("max_steps", 10) + extra
        repo.update_auto_run_session_max_steps(session_id, new_max_steps)

        # Reset to running so the stream endpoint can pick it up
        repo.update_auto_run_session_status(session_id, "running")

        stream_url = (
            f"/api/projects/{project_id}/production/run-auto/stream"
            f"?session_id={session_id}"
            f"&confirm=true"
            f"&max_steps={new_max_steps}"
            f"&dry_run={bool(session.get('dry_run'))}"
            f"&stop_on_review={bool(session.get('stop_on_review', 1))}"
        )
        if session.get("chapter_start") is not None:
            stream_url += f"&chapter_start={session['chapter_start']}"
        if session.get("chapter_end") is not None:
            stream_url += f"&chapter_end={session['chapter_end']}"

        return envelope_response({
            "resumed": True,
            "session_id": session_id,
            "stream_url": stream_url,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"恢复会话失败: {str(e)}")


@router.get("/projects/{project_id}/production/run-auto/active-session")
async def get_active_auto_run_session(request: Request, project_id: str) -> EnvelopeResponse:
    """Get the active (running or paused) auto-run session for a project.

    v5.5.9: Used by frontend to recover session state after refresh.
    """
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        session = repo.get_active_auto_run_session(project_id)
        if not session:
            return envelope_response({"active": False})

        steps = repo.list_auto_run_steps(session["id"])
        current_chapter = project.get("current_chapter", 1)
        health = _build_health(repo, project_id, current_chapter)
        timeout_minutes = getattr(settings.workflow, "task_timeout_minutes", 30)
        next_action = _determine_next_action(repo, project_id, health, current_chapter, timeout_minutes)
        if _is_obsolete_disconnected_session(repo, project_id, session, steps, next_action):
            repo.update_auto_run_session_status(
                session["id"],
                "stopped",
                stop_reason="obsolete",
                last_event="obsolete",
            )
            return envelope_response({
                "active": False,
                "obsolete_session_id": session["id"],
                "stop_reason": "obsolete",
            })

        return envelope_response({
            "active": True,
            "session": session,
            "steps": steps,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取活跃会话失败: {str(e)}")


@router.post("/projects/{project_id}/production/run-auto/sessions/{session_id}/retry-step")
async def retry_auto_run_step(
    request: Request, project_id: str, session_id: str, body: RetryStepRequest
) -> EnvelopeResponse:
    """Retry a specific failed step from a session.

    Re-executes the action associated with the given step_number using the
    current project state. Does not bypass safety gates or auto-publish.
    """
    from ..deps import get_repo, get_llm_mode, get_settings

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)
        settings = get_settings(request)

        session = repo.get_auto_run_session(session_id)
        if not session or session.get("project_id") != project_id:
            return error_response("SESSION_NOT_FOUND", "会话不存在")

        steps = repo.list_auto_run_steps(session_id)
        target_step = None
        for s in steps:
            if s.get("step_number") == body.step_number:
                target_step = s
                break

        if not target_step:
            return error_response("STEP_NOT_FOUND", f"步骤 {body.step_number} 不存在")

        if target_step.get("result") != "failed":
            return error_response("INVALID_STEP", "仅可重试失败的步骤")

        # Build the action dict from the persisted step
        action = {
            "key": target_step.get("action", ""),
            "label": target_step.get("label", ""),
            "target_chapter": target_step.get("target_chapter"),
        }

        # Re-execute using the same _execute_auto_step helper
        ch_start = session.get("chapter_start") or 1
        ch_end = session.get("chapter_end") or (ch_start + 9)
        project = repo.get_project(project_id)
        current_chapter = project.get("current_chapter", 1) if project else 1

        step_result = await _execute_auto_step(
            request, repo, settings, llm_mode, project_id, action, ch_start, ch_end, current_chapter
        )

        return envelope_response({
            "retried": True,
            "session_id": session_id,
            "step_number": body.step_number,
            "action": action["key"],
            "result": step_result.get("result"),
            "error": step_result.get("error"),
            "warnings": step_result.get("warnings", []),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"重试步骤失败: {str(e)}")


# ---------------------------------------------------------------------------
# v5.5.10: Session cleanup
# ---------------------------------------------------------------------------

class CleanupRequest(BaseModel):
    """Request to clean up old auto-run sessions."""

    keep_running: bool = True
    days_old: int = 0


@router.delete("/projects/{project_id}/production/run-auto/sessions/{session_id}")
async def delete_auto_run_session(
    request: Request, project_id: str, session_id: str
) -> EnvelopeResponse:
    """Delete a single auto-run session and its steps."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        session = repo.get_auto_run_session(session_id)
        if not session or session.get("project_id") != project_id:
            return error_response("SESSION_NOT_FOUND", "会话不存在")
        if session.get("status") in ("running", "paused"):
            return error_response("INVALID_STATE", f"当前状态 '{session.get('status')}' 不可删除")

        repo.delete_auto_run_session(session_id)
        return envelope_response({"deleted": True, "session_id": session_id})
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除会话失败: {str(e)}")


@router.post("/projects/{project_id}/production/run-auto/cleanup")
async def cleanup_auto_run_sessions(
    request: Request, project_id: str, body: CleanupRequest | None = None
) -> EnvelopeResponse:
    """Clean up old auto-run sessions for a project.

    Removes sessions with status in (completed, failed, cancelled, dry_run)
    optionally older than N days.  Never removes running or paused sessions
    unless keep_running is False.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        keep_running = body.keep_running if body else True
        days_old = body.days_old if body else 0

        removed = repo.cleanup_auto_run_sessions(
            project_id,
            keep_running=keep_running,
            days_old=days_old,
        )

        return envelope_response({
            "cleaned": True,
            "removed_count": removed,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"清理会话失败: {str(e)}")


# ---------------------------------------------------------------------------
# v6.6.12: Domain result helpers for production endpoints
# ---------------------------------------------------------------------------


def _build_production_next_domain_result(
    health: dict,
    next_action: dict,
    missing: list[dict],
) -> dict:
    """Build domain_result for production-next endpoint.

    Maps project health state to domain-level semantics:
    - Blocking issues → blocked/needs_human
    - Missing context → blocked
    - Running workflow → pending
    - Ready to generate → success
    """
    # Check for blocking issues
    if health.get("has_blocking_chapter") or health.get("has_stuck_run"):
        return needs_human(
            "项目存在阻塞章节或卡住运行",
            user_message="需要先处理阻塞/卡住的章节才能继续生产",
            next_action=next_action.get("key", "recover_blocked_run"),
            action_label=next_action.get("label", "处理阻塞"),
            details={
                "next_action_key": next_action.get("key"),
                "has_blocking_chapter": health.get("has_blocking_chapter", False),
                "has_stuck_run": health.get("has_stuck_run", False),
            },
            flags={"production_blocked": True},
        ).to_dict()

    # Check for missing context
    blocking_missing = [m for m in missing if m.get("severity") == "blocking"]
    if blocking_missing:
        return blocked_result(
            "项目资料不完整，无法生成章节",
            user_message="需要补齐项目基础资料后才能开始章节生成",
            next_action=next_action.get("key", "generate_genesis"),
            action_label=next_action.get("label", "生成项目设定"),
            details={
                "next_action_key": next_action.get("key"),
                "missing_count": len(blocking_missing),
                "missing_keys": [m.get("key") for m in blocking_missing],
            },
            flags={"context_incomplete": True},
        ).to_dict()

    # Check for running workflow
    if health.get("has_running_chapter_workflow"):
        from ..contracts import OperationResult
        return OperationResult(
            ok=True,
            domain_status="pending",
            message="章节工作流运行中",
            user_message="当前章节正在生成中，请等待完成",
            severity="info",
            details={
                "next_action_key": next_action.get("key"),
            },
            flags={"workflow_running": True},
        ).to_dict()

    # Ready to generate
    return success(
        "项目已就绪，可开始章节生成",
        user_message=next_action.get("description", "项目已就绪"),
        details={
            "next_action_key": next_action.get("key"),
            "next_action_label": next_action.get("label"),
            "current_chapter": health.get("current_chapter"),
        },
        flags={"production_ready": True},
    ).to_dict()


def _build_run_auto_domain_result(data: dict) -> dict:
    """Build domain_result for run-auto endpoint.

    Maps auto-run outcome to domain-level semantics:
    - stop_reason=failed → failed
    - stop_reason=review_needed → needs_human
    - stop_reason=blocked → blocked
    - stop_reason=completed with chapters → success
    - stop_reason=completed without chapters → partial_success
    """
    stop_reason = data.get("stop_reason", "")
    steps_executed = data.get("steps_executed", 0)
    chapters_touched = data.get("chapters_touched", [])
    status = data.get("status", "unknown")

    if stop_reason == "failed" or status == "failed":
        return failed(
            "自动生产执行失败",
            user_message="自动生产过程中发生错误，请检查后重试",
            retryable=True,
            next_action="retry_auto_run",
            action_label="重试自动生产",
            details={
                "stop_reason": stop_reason,
                "steps_executed": steps_executed,
                "chapters_touched": chapters_touched,
            },
            flags={"auto_run_failed": True},
        ).to_dict()

    if stop_reason == "review_needed":
        return needs_human(
            "自动生产暂停：需要人工审核",
            user_message="章节已到待发布状态，需要人工确认发布后继续",
            next_action="publish_chapter",
            action_label="确认发布",
            details={
                "stop_reason": stop_reason,
                "steps_executed": steps_executed,
                "chapters_touched": chapters_touched,
            },
            flags={"auto_run_review_needed": True},
        ).to_dict()

    if stop_reason == "blocked":
        return blocked_result(
            "自动生产被阻塞",
            user_message="生产过程中遇到阻塞，需要处理后继续",
            next_action="recover_blocked_run",
            action_label="处理阻塞",
            details={
                "stop_reason": stop_reason,
                "steps_executed": steps_executed,
                "chapters_touched": chapters_touched,
            },
            flags={"auto_run_blocked": True},
        ).to_dict()

    if chapters_touched:
        return success(
            f"自动生产完成：已处理 {len(chapters_touched)} 章",
            user_message=f"自动生产已完成，共处理 {len(chapters_touched)} 章",
            details={
                "stop_reason": stop_reason,
                "steps_executed": steps_executed,
                "chapters_touched": chapters_touched,
            },
            flags={"auto_run_completed": True},
        ).to_dict()

    return partial_success(
        "自动生产完成，但未生成章节",
        user_message="自动生产已完成，但未实际生成章节内容",
        next_action="check_production_next",
        action_label="查看下一步",
        details={
            "stop_reason": stop_reason,
            "steps_executed": steps_executed,
        },
        flags={"auto_run_no_chapters": True},
    ).to_dict()
