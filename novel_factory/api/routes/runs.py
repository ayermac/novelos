"""Run detail API endpoints."""

from __future__ import annotations

import json
import time
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ..contracts import (
    success,
    partial_success,
    failed,
    blocked,
    needs_human,
    ignored,
)
from ._memory_curator_gate import (
    complete_memory_curator_recovery_if_trusted,
    complete_memory_curator_run_if_batch_exists,
    has_trusted_memory_batch,
    is_trusted_memory_batch,
    memory_incomplete_details,
    memory_incomplete_message,
    memory_result_is_incomplete,
)
from ._core_loop_diagnostics import get_core_loop_diagnostics_for_chapter
from ...workflow.node_recovery import (
    active_node_started_at_from_events,
    node_retry_target,
    resolve_failed_node_from_events,
)

router = APIRouter()

PUBLISH_READY_CHAPTER_STATUSES = frozenset({"reviewed", "awaiting_publish", "published"})
RESETTABLE_CHAPTER_STATUSES = frozenset({"blocking", "revision", "planned", "review"})


def _get_run_recovery_settings(request: Request):
    """Load settings for recovery endpoints without blocking reset on cwd loss."""
    from ..deps import get_settings
    from ...config.settings import Settings

    try:
        return get_settings(request)
    except FileNotFoundError:
        return Settings()


def _run_recovery_preserves_chapter_status(run_data: dict, chapter_status: str) -> bool:
    """Return whether recovery should clean up the run without rewinding chapter status."""
    return (
        chapter_status in PUBLISH_READY_CHAPTER_STATUSES
        and run_data.get("status") in ("blocked", "failed")
    )


def _memory_curator_running_domain_result(project_id: str, chapter_number: int, lock: dict | None) -> dict:
    """Build a blocked domain result for an active MemoryCurator lock."""
    active_run_id = (lock or {}).get("run_id")
    message = f"第 {chapter_number} 章记忆提取正在进行中，请等待完成后再重试。"
    technical_message = f"第 {chapter_number} 章记忆正在提取，不能重复启动。"
    if active_run_id:
        technical_message = f"{technical_message} 当前运行: {active_run_id}"
    return blocked(
        message,
        user_message="记忆提取正在进行中，请等待完成后再重试。",
        next_action="view_workflow",
        action_label="查看工作流",
        details={
            "project_id": project_id,
            "chapter_number": chapter_number,
            "active_run_id": active_run_id,
            "memory_lock": lock,
            "error_code": "MEMORY_CURATOR_RUNNING",
            "technical_message": technical_message,
        },
        flags={"memory_curator_running": True},
    ).to_dict()


def _resolve_recoverable_node(repo, run_data: dict | None) -> str | None:
    """Resolve the real node that should drive recovery actions."""
    if not run_data:
        return None
    run_id = str(run_data.get("id") or run_data.get("run_id") or "")
    events: list[dict] = []
    if run_id:
        try:
            events = repo.get_workflow_node_events(run_id)
        except Exception:
            events = []
    return resolve_failed_node_from_events(events, run_data.get("current_node"))


class RunRecoveryResetRequest(BaseModel):
    """Run recovery reset request."""

    confirm: bool = False


class RunRecoveryMarkStuckRequest(BaseModel):
    """Mark a confirmed stuck run as blocked."""

    confirm: bool = False


class RunRecoveryRetryNodeRequest(BaseModel):
    """Retry the failed workflow node from its last safe chapter status."""

    confirm: bool = False


class RunMemoryBackfillRequest(BaseModel):
    """Run MemoryCurator backfill from a run detail page."""

    confirm: bool = False
    force: bool = False


class RunHealthMarkStuckRequest(BaseModel):
    """Batch mark stuck workflow runs as blocked."""

    run_ids: list[str]
    confirm: bool = False


# Agent step configuration
AGENT_STEPS = [
    {"key": "planner", "label": "规划", "description": "生成章节目标、关键事件和伏笔要求"},
    {"key": "screenwriter", "label": "编剧", "description": "规划章节场景和情节"},
    {"key": "author", "label": "执笔", "description": "撰写章节正文"},
    {"key": "polisher", "label": "润色", "description": "优化文字表达"},
    {"key": "editor", "label": "审核", "description": "检查内容质量"},
    {"key": "publish", "label": "发布", "description": "发布章节内容"},
]

# Status to agent mapping (reverse of STATUS_ROUTE)
STATUS_TO_AGENT = {
    "planned": None,  # Initial state
    "scripted": "screenwriter",
    "drafted": "author",
    "polished": "polisher",
    "reviewed": "editor",
    "published": "publish",
}

AGENT_DISPLAY_NAMES = {
    "planner": "规划",
    "screenwriter": "编剧",
    "author": "执笔",
    "polisher": "润色",
    "editor": "审稿",
    "publish": "发布",
    "publisher": "发布",
    "human_review": "人工审核",
    "memory_curator": "记忆整理",
    "continuity_checker": "连续性检查",
    "system": "系统",
    "human": "人工处理",
}

ARTIFACT_TYPE_DISPLAY_NAMES = {
    "chapter_brief": "章节规划",
    "scene_plan": "分场规划",
    "draft": "正文初稿",
    "polished_draft": "润色稿",
    "review": "审稿报告",
    "published_chapter": "发布记录",
    "memory_update": "记忆更新",
    "style_report": "风格报告",
    "fact_snapshot": "事实快照",
}

TASK_TYPE_DISPLAY_NAMES = {
    "create": "生成任务",
    "write": "写作任务",
    "revise": "返修任务",
    "reset": "重置恢复",
    "recover": "卡住恢复",
    "generate": "生成任务",
    "publish": "发布任务",
    "review": "审核任务",
}


def _humanize_key(value: str) -> str:
    """Fallback display for unknown internal keys."""
    return value.replace("_", " ").strip() or "产物"


def _agent_display_name(agent_id: str) -> str:
    """Return user-facing agent name."""
    return AGENT_DISPLAY_NAMES.get(agent_id, _humanize_key(agent_id))


def _artifact_type_display_name(artifact_type: str) -> str:
    """Return user-facing artifact type label."""
    return ARTIFACT_TYPE_DISPLAY_NAMES.get(artifact_type, _humanize_key(artifact_type))


def _task_type_display_name(task_type: str) -> str:
    """Return user-facing task type label."""
    return TASK_TYPE_DISPLAY_NAMES.get(task_type, _humanize_key(task_type))


def _build_artifact_display_summary(artifacts_list: list[dict]) -> dict:
    """Build human-readable artifact labels instead of leaking raw DB keys."""
    labels: list[str] = []
    raw_types: list[str] = []
    for artifact in artifacts_list:
        artifact_type = artifact.get("artifact_type", "") or "artifact"
        agent_id = artifact.get("agent_id", "") or ""
        raw_types.append(artifact_type)
        type_label = _artifact_type_display_name(artifact_type)
        agent_label = _agent_display_name(agent_id)
        label = f"{type_label} · {agent_label}" if agent_label else type_label
        if label not in labels:
            labels.append(label)

    if not labels:
        labels = ["Agent 产物"]

    return {
        "summary": "、".join(labels),
        "artifact_count": len(artifacts_list),
        "artifact_types": raw_types,
        "artifact_labels": labels,
    }


@router.get("/runs/health")
async def get_runs_health(
    request: Request,
    project_id: str | None = None,
    limit: int = 50,
) -> EnvelopeResponse:
    """Return production run health with stuck-run detection."""
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        timeout_minutes = settings.workflow.task_timeout_minutes
        safe_limit = max(1, min(limit, 200))
        rows = _list_run_health_rows(repo, project_id=project_id, limit=safe_limit)
        items = [
            _build_run_health_item(repo, row, timeout_minutes=timeout_minutes)
            for row in rows
        ]

        stuck_count = sum(1 for item in items if item["stuck"])
        total_running = sum(1 for item in items if item["workflow_status"] == "running")
        blocked_count = sum(1 for item in items if item["workflow_status"] == "blocked")
        failed_count = sum(1 for item in items if item["workflow_status"] == "failed")

        return envelope_response({
            "timeout_minutes": timeout_minutes,
            "project_id": project_id,
            "limit": safe_limit,
            "summary": {
                "total": len(items),
                "total_running": total_running,
                "healthy_running": max(0, total_running - stuck_count),
                "stuck": stuck_count,
                "blocked": blocked_count,
                "failed": failed_count,
                "actionable": sum(1 for item in items if item["actions"]["mark_stuck_blocked"]["enabled"]),
            },
            "runs": items,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行健康状态失败: {str(e)}")


@router.post("/runs/health/mark-stuck")
async def mark_stuck_runs_from_health(
    request: Request,
    body: RunHealthMarkStuckRequest,
) -> EnvelopeResponse:
    """Batch mark confirmed stuck runs as blocked from the health dashboard."""
    from ..deps import get_repo, get_settings

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认批量标记卡住运行")
        if not body.run_ids:
            return error_response("NO_RUNS_SELECTED", "请选择需要标记的运行")
        if len(body.run_ids) > 50:
            return error_response("TOO_MANY_RUNS", "一次最多处理 50 条运行")

        repo = get_repo(request)
        settings = get_settings(request)
        results = []
        marked = 0
        for run_id in body.run_ids:
            result = _mark_stuck_run_for_recovery(repo, settings, run_id)
            if result["ok"]:
                marked += 1
            results.append(result)

        return envelope_response({
            "requested": len(body.run_ids),
            "marked": marked,
            "failed": len(body.run_ids) - marked,
            "results": results,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"批量标记卡住运行失败: {str(e)}")


def _generate_stub_artifacts(step_key: str, chapter_number: int) -> dict | None:
    """Generate mock artifacts for stub mode.

    Different chapters produce different content using chapter_number as seed.
    """
    # Scene templates for different chapters
    scene_templates = [
        ["修炼突破", "危机降临", "转机出现"],
        ["故人重逢", "恩怨化解", "新的征程"],
        ["探寻秘境", "意外收获", "暗流涌动"],
        ["强敌来袭", "背水一战", "绝地反击"],
        ["真相揭露", "命运抉择", "风云再起"],
    ]

    # Character names for variety
    characters = ["萧炎", "林动", "牧尘", "唐三", "叶凡"]
    char = characters[chapter_number % len(characters)]
    scenes = scene_templates[chapter_number % len(scene_templates)]

    base_word_count = 2800 + (chapter_number % 5) * 200  # 2800-3600 range

    if step_key == "planner":
        return {
            "summary": f"生成第 {chapter_number} 章写作目标、关键事件和伏笔要求",
            "output_preview": f"章节目标：推进主线冲突，保留第 {chapter_number + 1} 章钩子"
        }
    elif step_key == "screenwriter":
        return {
            "summary": f"本章规划了 {len(scenes)} 个场景：{char}{scenes[0]}、{scenes[1]}、{scenes[2]}",
            "scenes": len(scenes),
            "word_count_hint": f"{base_word_count}-{base_word_count + 400}",
            "output_preview": f"场景一：{char}{scenes[0]}…\n场景二：{scenes[1]}…\n场景三：{scenes[2]}…"
        }
    elif step_key == "author":
        draft_words = base_word_count + (chapter_number % 3) * 100
        return {
            "summary": f"基于编剧大纲完成正文，初稿 {draft_words} 字",
            "draft_word_count": draft_words,
            "output_preview": f"第{chapter_number}章开篇，{char}正面临前所未有的挑战…"
        }
    elif step_key == "polisher":
        polished_words = base_word_count + 150 + (chapter_number % 3) * 50
        changes = 8 + (chapter_number % 8)
        return {
            "summary": f"润色后 {polished_words} 字，优化了 {changes} 处表达",
            "polished_word_count": polished_words,
            "changes": changes,
            "output_preview": f"主要修改：1) 开篇节奏调整；2) 对话细节润色；3) 结尾情感升华"
        }
    elif step_key == "editor":
        score = 80 + (chapter_number % 15)
        return {
            "summary": f"审核通过，质量评分 {score}/100",
            "quality_score": score,
            "issues_found": 0,
            "output_preview": "角色一致性：✓\n情节连贯性：✓\n风格匹配度：✓"
        }
    elif step_key == "publish":
        final_words = base_word_count + 150 + (chapter_number % 3) * 50
        return {
            "summary": f"章节已发布，最终字数 {final_words}",
            "final_word_count": final_words,
            "output_preview": f"第 {chapter_number} 章已发布到项目"
        }

    return None


@router.get("/runs/{run_id}")
async def get_run_detail(request: Request, run_id: str) -> EnvelopeResponse:
    """Get detailed information about a workflow run.

    Returns run metadata and step timeline.
    """
    from ..deps import get_repo, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        # Get workflow run
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?",
                (run_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        run_data = dict(row)

        # Get project info
        project = repo.get_project(run_data["project_id"])
        project_name = project.get("name", "") if project else ""

        # Get chapter info
        chapter = repo.get_chapter(run_data["project_id"], run_data["chapter_number"])
        if _block_memory_curator_timeout_run_if_needed(repo, run_data):
            refreshed = _get_run_by_id(repo, run_id, reconcile=False)
            if refreshed:
                run_data = refreshed
        reconciliation = {"runs": 0, "tasks": 0, "run_ids": []}
        if (
            chapter
            and run_data.get("status") == "running"
            and chapter.get("status") in ("reviewed", "awaiting_publish", "published")
            and hasattr(repo, "reconcile_terminal_chapter_running_workflows")
        ):
            reconciliation = repo.reconcile_terminal_chapter_running_workflows(
                project_id=run_data["project_id"],
                chapter_number=run_data["chapter_number"],
                run_id=run_id,
            )
            if reconciliation.get("runs"):
                refreshed = _get_run_by_id(repo, run_id)
                if refreshed:
                    run_data = refreshed

        error_message = _resolve_run_error_message(repo, run_data, chapter)
        if error_message and not run_data.get("error_message"):
            run_data = dict(run_data)
            run_data["error_message"] = error_message

        # Build steps timeline (with observability data from task_status and agent_artifacts)
        steps = _build_steps_timeline(run_data, chapter, llm_mode, repo=repo)

        # v6.6.6: Build recovery state
        from ..deps import get_settings
        try:
            settings = get_settings(request)
            max_retries = settings.quality_gate.max_retries
            timeout_minutes = settings.workflow.task_timeout_minutes
        except Exception:
            max_retries = 3
            timeout_minutes = 30
        recovery_state = _build_recovery_state(
            repo,
            run_data,
            max_retries=max_retries,
            timeout_minutes=timeout_minutes,
        )

        # v6.6.7: Memory status for reviewed/awaiting_publish/published chapters
        memory_status: dict[str, Any] = {}
        if chapter and chapter.get("status") in ("reviewed", "awaiting_publish", "published"):
            try:
                from ...api.routes._memory_curator_gate import get_memory_status_for_chapter

                memory_status = get_memory_status_for_chapter(
                    repo, run_data["project_id"], run_data["chapter_number"]
                )
            except Exception:
                pass

        # v6.6.10: Derive domain-level result for the entire workflow run
        from ..contracts import workflow_run_to_domain_status
        domain_result = workflow_run_to_domain_status(
            run_data.get("status", "unknown"),
            chapter.get("status", "unknown") if chapter else "unknown",
            memory_status=memory_status if memory_status else None,
        )

        # v6.10.3: Run Doctor — classify run failures and suggest next action.
        try:
            from ...workflow.run_doctor import diagnose_run

            run_doctor = diagnose_run(repo, run_data, chapter)
        except Exception:
            run_doctor = {}

        try:
            core_loop_diagnostics = get_core_loop_diagnostics_for_chapter(
                repo,
                run_data["project_id"],
                run_data["chapter_number"],
            )
        except Exception:
            core_loop_diagnostics = None

        # v6.6.14: Fetch memory context audit from planner artifact
        memory_context_audit: dict = {}
        try:
            _conn = repo._conn()
            try:
                _row = _conn.execute(
                    "SELECT content_json FROM agent_artifacts "
                    "WHERE workflow_run_id=? AND agent_id='planner' "
                    "AND artifact_type='memory_context_audit' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (run_id,),
                ).fetchone()
                if _row and _row["content_json"]:
                    import json as _json
                    memory_context_audit = _json.loads(_row["content_json"])
            finally:
                _conn.close()
        except Exception:
            pass

        return envelope_response({
            "run_id": run_id,
            "project_id": run_data["project_id"],
            "project_name": project_name,
            "chapter_number": run_data["chapter_number"],
            "workflow_status": run_data.get("status", "unknown"),
            "chapter_status": chapter.get("status", "unknown") if chapter else "unknown",
            "current_node": run_data.get("current_node"),
            "llm_mode": llm_mode,
            "started_at": run_data.get("started_at", ""),
            "completed_at": run_data.get("completed_at", ""),
            "error_message": error_message,
            "steps": steps,
            # v5.2: Token usage statistics
            "prompt_tokens": run_data.get("prompt_tokens", 0),
            "completion_tokens": run_data.get("completion_tokens", 0),
            "total_tokens": run_data.get("total_tokens", 0),
            "duration_ms": run_data.get("duration_ms", 0),
            "reconciled_terminal_run": bool(reconciliation.get("runs")),
            "reconciled_running_tasks": reconciliation.get("tasks", 0),
            # v6.6.6: Recovery state
            "recovery_state": recovery_state.get("recovery_state", recovery_state),
            # v6.6.7: Memory status
            "memory_status": memory_status,
            # v6.6.10: Unified domain result
            "domain_result": domain_result.to_dict(),
            # v6.10.3: Failure attribution and next-action diagnosis
            "run_doctor": run_doctor,
            # v6.10.7: Core-loop evidence diagnostics
            "core_loop_diagnostics": core_loop_diagnostics,
            # v6.6.14: Memory context audit
            "memory_context_audit": memory_context_audit,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行详情失败: {str(e)}")


@router.get("/runs/{run_id}/recovery")
async def get_run_recovery(request: Request, run_id: str) -> EnvelopeResponse:
    """Return safe recovery options for a workflow run."""
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        try:
            settings = get_settings(request)
            max_retries = settings.quality_gate.max_retries
            timeout_minutes = settings.workflow.task_timeout_minutes
        except Exception:
            max_retries = 3
            timeout_minutes = 30
        run_data = _get_run_by_id(repo, run_id)
        if not run_data:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        return envelope_response(_build_recovery_state(
            repo,
            run_data,
            max_retries=max_retries,
            timeout_minutes=timeout_minutes,
        ))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行恢复状态失败: {str(e)}")


@router.post("/runs/{run_id}/recovery/reset")
async def reset_run_chapter(
    request: Request,
    run_id: str,
    body: RunRecoveryResetRequest,
) -> EnvelopeResponse:
    """Reset a blocked/revision chapter from a run detail page.

    This is a run-scoped facade over chapter reset. It never deletes content or
    artifacts; it only moves the chapter back to planned, inserts an audit task,
    and clears stale LangGraph checkpoints.
    """
    from ..deps import get_repo
    from ...workflow.checkpoint import delete_checkpoint_thread

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认恢复操作")

        repo = get_repo(request)
        settings = _get_run_recovery_settings(request)
        run_data = _get_run_by_id(repo, run_id)
        if not run_data:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        project_id = run_data["project_id"]
        chapter_number = run_data["chapter_number"]
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        current_status = chapter.get("status", "")
        preserve_chapter_status = _run_recovery_preserves_chapter_status(run_data, current_status)
        recoverable_node = _resolve_recoverable_node(repo, run_data)
        memory_trusted = has_trusted_memory_batch(repo, project_id, chapter_number)
        if (
            current_status in PUBLISH_READY_CHAPTER_STATUSES
            and recoverable_node == "memory_curator"
            and not memory_trusted
            and run_data.get("status") in {"blocked", "failed", "running"}
        ):
            message = "记忆整理节点失败或超时，请补跑记忆提取，不要清除为发布态。"
            return error_response(
                "MEMORY_BACKFILL_REQUIRED",
                message,
                details={
                    "run_id": run_id,
                    "project_id": project_id,
                    "chapter_number": chapter_number,
                    "failed_node": recoverable_node,
                    "domain_result": blocked(
                        message,
                        user_message=message,
                        next_action="backfill_memory",
                        action_label="补跑记忆提取",
                        details={
                            "run_id": run_id,
                            "project_id": project_id,
                            "chapter_number": chapter_number,
                            "failed_node": recoverable_node,
                            "error_code": "MEMORY_BACKFILL_REQUIRED",
                        },
                        flags={"memory_backfill_required": True},
                    ).to_dict(),
                },
            )
        if current_status not in RESETTABLE_CHAPTER_STATUSES and not preserve_chapter_status:
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'blocking'、'revision'、'planned'、'review' 或存在阻塞运行的发布就绪状态可恢复",
                details={"current_status": current_status},
            )

        retry_count_before = repo.get_chapter_retry_count(project_id, chapter_number)
        checkpoint_before = _checkpoint_exists(repo, project_id, chapter_number)

        if current_status in ("blocking", "revision"):
            reset = repo.reset_chapter(project_id, chapter_number, workflow_run_id=run_id)
            if not reset:
                return error_response("RESET_FAILED", "恢复章节失败")
        # For planned or publish-ready cleanup: no chapter state reset needed.

        recovered_blocked_runs = 0
        if hasattr(repo, "recover_active_workflow_runs_for_chapter"):
            recovered_blocked_runs = repo.recover_active_workflow_runs_for_chapter(
                project_id,
                chapter_number,
                run_id=run_id,
            )
            invalidated_runs = recovered_blocked_runs
        else:
            if hasattr(repo, "mark_blocked_workflow_runs_recovered_for_chapter"):
                recovered_blocked_runs = repo.mark_blocked_workflow_runs_recovered_for_chapter(
                    project_id,
                    chapter_number,
                    run_id=run_id,
                )
            invalidated_runs = repo.invalidate_running_workflow_runs_for_chapter(
                project_id,
                chapter_number,
                "章节已恢复重置，旧运行已作废，请重新开始新的工作流。",
            )

        checkpoint_cleared = delete_checkpoint_thread(repo.db_path, project_id, chapter_number)
        retry_count_after = repo.get_chapter_retry_count(project_id, chapter_number)
        recovery = _build_recovery_state(
            repo,
            run_data,
            max_retries=settings.quality_gate.max_retries,
            timeout_minutes=settings.workflow.task_timeout_minutes,
        )

        # v6.6.12: Build domain_result for recovery reset
        domain_result = success(
            (
                f"运行已恢复清理：章节保持 {current_status}"
                if preserve_chapter_status
                else f"章节已恢复重置：{current_status} → planned"
            ),
            user_message=(
                f"第 {chapter_number} 章已清理阻塞运行，章节状态保持 {current_status}"
                if preserve_chapter_status
                else f"第 {chapter_number} 章已恢复到 planned 状态，可重新开始生成"
            ),
            details={
                "previous_status": current_status,
                "new_status": current_status if preserve_chapter_status else "planned",
                "retries_cleared": max(0, retry_count_before - retry_count_after),
                "next_action": "publish" if preserve_chapter_status else "start_workflow",
                "action_label": "继续发布" if preserve_chapter_status else "开始生成",
            },
            flags={"recovery_reset": True},
        ).to_dict()

        return envelope_response({
            "recovered": True,
            "run_id": run_id,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "previous_status": current_status,
            "new_status": current_status if preserve_chapter_status else "planned",
            "retry_count_before": retry_count_before,
            "retry_count_after": retry_count_after,
            "retries_cleared": max(0, retry_count_before - retry_count_after),
            "recovered_blocked_runs": recovered_blocked_runs,
            "invalidated_runs": invalidated_runs,
            "checkpoint_before": checkpoint_before,
            "checkpoint_cleared": checkpoint_cleared,
            "recovery": recovery,
            "domain_result": domain_result,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"恢复运行失败: {str(e)}")


@router.post("/runs/{run_id}/recovery/mark-stuck")
async def mark_stuck_run(
    request: Request,
    run_id: str,
    body: RunRecoveryMarkStuckRequest,
) -> EnvelopeResponse:
    """Mark a confirmed stuck running run as blocked.

    This does not delete content or artifacts. It converts a stale running run
    into an explicit blocked state and moves the chapter to blocking so the
    normal recovery reset path can take over.
    """
    from ..deps import get_repo, get_settings

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认标记卡住运行")

        repo = get_repo(request)
        settings = get_settings(request)
        result = _mark_stuck_run_for_recovery(repo, settings, run_id)
        if not result["ok"]:
            return error_response(
                result["error_code"],
                result["message"],
                details=result.get("details"),
            )

        # v6.6.12: Build domain_result for mark-stuck
        domain_result = blocked(
            "运行已标记为卡住",
            user_message="运行已标记为卡住，需要恢复重置后重新开始",
            next_action="reset_chapter",
            action_label="恢复重置",
            details={
                "run_id": run_id,
                "marked_stuck": True,
            },
            flags={"workflow_stuck": True},
        ).to_dict()

        return envelope_response({
            **result["data"],
            "domain_result": domain_result,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"标记卡住运行失败: {str(e)}")


@router.post("/runs/{run_id}/recovery/retry-node")
async def retry_run_node(
    request: Request,
    run_id: str,
    body: RunRecoveryRetryNodeRequest,
) -> EnvelopeResponse:
    """Recover a blocked node to the last safe status instead of planned.

    For example, an Author timeout should preserve screenwriter output and move
    the chapter back to ``scripted`` so the next run starts at Author directly.
    """
    from ..deps import get_repo, get_settings

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认节点重试操作")

        repo = get_repo(request)
        settings = get_settings(request)
        run_data = _get_run_by_id(repo, run_id)
        if not run_data:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        recoverable_node = _resolve_recoverable_node(repo, run_data)
        if recoverable_node == "memory_curator" and not has_trusted_memory_batch(
            repo,
            run_data.get("project_id"),
            int(run_data.get("chapter_number") or 0),
        ):
            message = "记忆整理节点失败或超时，请补跑记忆提取，不要重置整章。"
            return error_response(
                "MEMORY_BACKFILL_REQUIRED",
                message,
                details={
                    "run_id": run_id,
                    "project_id": run_data.get("project_id"),
                    "chapter_number": run_data.get("chapter_number"),
                    "failed_node": recoverable_node,
                    "domain_result": blocked(
                        message,
                        user_message=message,
                        next_action="backfill_memory",
                        action_label="补跑记忆提取",
                        details={
                            "run_id": run_id,
                            "failed_node": recoverable_node,
                            "error_code": "MEMORY_BACKFILL_REQUIRED",
                        },
                        flags={"memory_backfill_required": True},
                    ).to_dict(),
                },
            )

        target = _node_retry_target(recoverable_node)
        if not target:
            return error_response(
                "NODE_RETRY_UNSUPPORTED",
                "当前节点不支持定点重试，请使用完整恢复重置。",
                details={
                    "current_node": run_data.get("current_node"),
                    "failed_node": recoverable_node,
                },
            )

        project_id = run_data["project_id"]
        chapter_number = run_data["chapter_number"]
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        current_status = chapter.get("status", "")
        if current_status not in ("blocking", "revision"):
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅阻塞/返修状态可定点重试",
                details={"current_status": current_status},
            )

        previous_status = current_status
        next_status = target["status"]
        message = (
            f"人工恢复：保留已有产物，从{target['label']}重新继续。"
            f" {previous_status} → {next_status}"
        )
        _set_chapter_status_unchecked(repo, project_id, chapter_number, next_status)
        repo.update_workflow_run(
            run_id,
            status="completed",
            current_node=f"{target['node']}_retry_recovery",
            clear_error=True,
        )
        _insert_recovery_audit(
            repo,
            project_id,
            chapter_number,
            workflow_run_id=run_id,
            message=message,
            task_type="recover",
            agent_id="human",
        )

        refreshed = _get_run_by_id(repo, run_id) or run_data

        # v6.6.12: Build domain_result for node retry
        domain_result = success(
            f"节点重试恢复成功：{previous_status} → {next_status}",
            user_message=f"已保留已有产物，可从 {target['label']} 重新继续",
            details={
                "previous_status": previous_status,
                "new_status": next_status,
                "retry_node": target["node"],
                "retry_label": target["label"],
                "next_action": "start_workflow",
                "action_label": "继续生成",
            },
            flags={"node_retry_recovery": True},
        ).to_dict()

        return envelope_response({
            "recovered": True,
            "run_id": run_id,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "previous_status": previous_status,
            "new_status": next_status,
            "retry_node": target["node"],
            "retry_label": target["label"],
            "resolved_failed_node": recoverable_node,
            "message": message,
            "recovery": _build_recovery_state(
                repo,
                refreshed,
                max_retries=settings.quality_gate.max_retries,
                timeout_minutes=settings.workflow.task_timeout_minutes,
            ),
            "domain_result": domain_result,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"定点重试恢复失败: {str(e)}")


@router.post("/runs/{run_id}/memory/backfill")
async def backfill_run_memory(
    request: Request,
    run_id: str,
    body: RunMemoryBackfillRequest,
) -> EnvelopeResponse:
    """Backfill MemoryCurator for a reviewed/awaiting/published chapter.

    v6.6.7:
    - force=true ignores old fallback/untrusted batches and re-runs extraction.
    - Only skips when a trusted batch exists AND force=false.
    - Returns clear semantics: trusted vs fallback vs failed.

    v6.6.10:
    - Response now includes domain_result with unified domain_status.
    """
    from ..deps import (
        get_repo,
        get_llm_fallback_provider_for_agent,
        get_llm_provider_for_agent,
        get_llm_mode,
        LLMConfigMissingError,
    )
    from ...agents.memory_curator import MemoryCuratorAgent
    from ...skills.registry import SkillRegistry

    try:
        if not body.confirm:
            message = "请确认补跑记忆提取"
            return error_response(
                "CONFIRM_REQUIRED",
                message,
                details={
                    "domain_result": blocked(
                        message,
                        user_message=message,
                        next_action="confirm_memory_backfill",
                        action_label="确认补跑",
                        details={"run_id": run_id, "error_code": "CONFIRM_REQUIRED"},
                        flags={"memory_backfill_blocked": True},
                    ).to_dict()
                },
            )

        repo = get_repo(request)
        run_data = _get_run_by_id(repo, run_id)
        if not run_data:
            message = f"运行记录 '{run_id}' 不存在"
            return error_response(
                "RUN_NOT_FOUND",
                message,
                details={
                    "domain_result": failed(
                        message,
                        user_message="运行记录不存在，无法补跑记忆",
                        retryable=False,
                        details={"run_id": run_id, "error_code": "RUN_NOT_FOUND"},
                        flags={"memory_backfill_failed": True},
                    ).to_dict()
                },
            )

        project_id = run_data["project_id"]
        chapter_number = int(run_data["chapter_number"])
        if _block_memory_curator_timeout_run_if_needed(repo, run_data):
            run_data = _get_run_by_id(repo, run_id, reconcile=False) or run_data
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            message = f"章节 {chapter_number} 不存在"
            return error_response(
                "CHAPTER_NOT_FOUND",
                message,
                details={
                    "domain_result": failed(
                        message,
                        user_message="章节不存在，无法补跑记忆",
                        retryable=False,
                        details={
                            "run_id": run_id,
                            "project_id": project_id,
                            "chapter_number": chapter_number,
                            "error_code": "CHAPTER_NOT_FOUND",
                        },
                        flags={"memory_backfill_failed": True},
                    ).to_dict()
                },
            )

        current_status = chapter.get("status", "")
        if current_status not in ("reviewed", "awaiting_publish", "published") and not body.force:
            message = (
                f"章节状态为 '{current_status}'，仅 reviewed / awaiting_publish / published 可补跑记忆提取"
            )
            return error_response(
                "INVALID_STATUS",
                message,
                details={
                    "current_status": current_status,
                    "domain_result": blocked(
                        message,
                        user_message="当前章节状态不允许补跑记忆",
                        next_action="run_chapter",
                        action_label="继续生成章节",
                        details={
                            "run_id": run_id,
                            "project_id": project_id,
                            "chapter_number": chapter_number,
                            "current_status": current_status,
                            "error_code": "INVALID_STATUS",
                        },
                        flags={"memory_backfill_blocked": True},
                    ).to_dict(),
                },
            )

        # v6.6.7: Only skip if trusted batch exists AND force=false
        if has_trusted_memory_batch(repo, project_id, chapter_number) and not body.force:
            completed_runs = complete_memory_curator_recovery_if_trusted(
                repo,
                project_id,
                chapter_number,
                run_id=run_id,
            )
            from ..contracts import success as domain_success
            return envelope_response({
                "skipped": True,
                "project_id": project_id,
                "chapter": chapter_number,
                "chapter_status": current_status,
                "completed_recovery_runs": completed_runs,
                "message": "该章节已有可信记忆收件箱批次，未重复补跑。",
                "domain_result": domain_success(
                    "记忆提取已存在可信结果，无需重复补跑",
                    flags={"memory_trusted": True, "skipped": True},
                ).to_dict(),
            })

        lock = None
        if hasattr(repo, "get_memory_curator_lock"):
            try:
                lock = repo.get_memory_curator_lock(project_id, chapter_number)
            except Exception:
                lock = None
        if lock and str(lock.get("status") or "") == "running":
            active_run_id = lock.get("run_id")
            if _release_memory_timeout_lock_if_recoverable(
                repo,
                project_id,
                chapter_number,
                str(active_run_id or ""),
            ):
                lock = repo.get_memory_curator_lock(project_id, chapter_number) if hasattr(repo, "get_memory_curator_lock") else None

        if lock and str(lock.get("status") or "") == "running":
            active_run_id = lock.get("run_id")
            same_source_run = active_run_id and str(active_run_id) == str(run_id)
            run_status = str(run_data.get("status") or "")
            current_node = str(run_data.get("current_node") or "")
            recoverable_memory_timeout = (
                same_source_run
                and current_node == "memory_curator"
                and run_status in {"blocked", "failed"}
            )
            if (
                not recoverable_memory_timeout
                and same_source_run
                and current_node == "memory_curator"
                and run_status == "running"
            ):
                try:
                    settings = _get_run_recovery_settings(request)
                    recoverable_memory_timeout = bool(
                        _detect_stuck_run(
                            repo,
                            run_data,
                            settings.workflow.task_timeout_minutes,
                        ).get("stuck")
                    )
                except Exception:
                    recoverable_memory_timeout = False
            if recoverable_memory_timeout and hasattr(repo, "release_memory_curator_lock"):
                repo.release_memory_curator_lock(project_id, chapter_number, run_id=run_id)
                lock = None

        if lock and str(lock.get("status") or "") == "running":
            active_run_id = lock.get("run_id")
            message = f"第 {chapter_number} 章记忆提取正在进行中，请等待完成后再重试。"
            technical_message = f"第 {chapter_number} 章记忆正在提取，不能重复启动。"
            if active_run_id:
                technical_message = f"{technical_message} 当前运行: {active_run_id}"
            details = {
                "run_id": active_run_id,
                "project_id": project_id,
                "chapter_number": chapter_number,
                "active_run_id": active_run_id,
                "memory_lock": lock,
                "technical_message": technical_message,
                "domain_result": _memory_curator_running_domain_result(project_id, chapter_number, lock),
            }
            return error_response("MEMORY_CURATOR_RUNNING", message, details=details)

        # v6.6.7: If force=true, mark old fallback batches as ignored before re-running
        if body.force:
            try:
                from ...api.routes._memory_curator_gate import ignore_state_card_fallback_batches_for_chapter

                ignored = ignore_state_card_fallback_batches_for_chapter(repo, project_id, chapter_number)
                if ignored:
                    logger.info("backfill force=true: ignored %d old fallback batches", ignored)
            except Exception:
                pass

        backfill_run_id = repo.create_workflow_run(
            project_id,
            chapter_number,
            graph_name="memory_backfill",
        )
        repo.update_workflow_run(backfill_run_id, status="running", current_node="memory_curator")
        repo.create_workflow_node_event(
            run_id=backfill_run_id,
            project_id=project_id,
            chapter_number=chapter_number,
            node_name="memory_curator",
            event_type="started",
            status="running",
            message="运行详情页手动补跑记忆提取",
        )

        try:
            llm = get_llm_provider_for_agent(request, "memory_curator")
            fallback_llm = get_llm_fallback_provider_for_agent(request, "memory_curator")
        except LLMConfigMissingError as exc:
            error = str(exc)
            repo.create_workflow_node_event(
                run_id=backfill_run_id,
                project_id=project_id,
                chapter_number=chapter_number,
                node_name="memory_curator",
                event_type="failed",
                status="failed",
                error_message=error,
            )
            repo.update_workflow_run(backfill_run_id, status="failed", current_node="memory_curator", error_message=error)
            details = {
                "run_id": backfill_run_id,
                "domain_result": failed(
                    error,
                    user_message="补跑记忆提取失败：LLM 配置缺失",
                    retryable=True,
                    next_action="configure_llm",
                    action_label="配置 LLM",
                    details={"run_id": backfill_run_id, "error_code": "LLM_CONFIG_MISSING"},
                    flags={"memory_backfill_failed": True, "llm_config_missing": True},
                ).to_dict(),
            }
            return error_response("LLM_CONFIG_MISSING", error, details=details)

        agent = MemoryCuratorAgent(repo, llm, skill_registry=SkillRegistry(), fallback_llm=fallback_llm)
        result = await asyncio.to_thread(
            agent.run,
            {
                "project_id": project_id,
                "chapter_number": chapter_number,
                "chapter_status": current_status,
                "workflow_run_id": backfill_run_id,
                "llm_mode": get_llm_mode(request),
            },
        )

        if result.get("error"):
            error = str(result["error"])
            repo.create_workflow_node_event(
                run_id=backfill_run_id,
                project_id=project_id,
                chapter_number=chapter_number,
                node_name="memory_curator",
                event_type="failed",
                status="failed",
                error_message=error,
            )
            repo.update_workflow_run(backfill_run_id, status="failed", current_node="memory_curator", error_message=error)
            details = {
                "run_id": backfill_run_id,
                "domain_result": failed(
                    error,
                    user_message="补跑记忆提取失败，可尝试重新补跑",
                    retryable=True,
                    next_action="backfill_memory",
                    action_label="重新补跑记忆",
                    details={"run_id": backfill_run_id, "error_code": "MEMORY_CURATOR_FAILED"},
                    flags={"memory_backfill_failed": True},
                ).to_dict(),
            }
            return error_response("MEMORY_CURATOR_FAILED", error, details=details)

        extraction_success = result.get("extraction_success", True)
        incomplete = memory_result_is_incomplete(repo, project_id, chapter_number, result)
        repo.create_workflow_node_event(
            run_id=backfill_run_id,
            project_id=project_id,
            chapter_number=chapter_number,
            node_name="memory_curator",
            event_type="completed",
            status="warning" if incomplete else "completed",
            message="运行详情页手动补跑记忆提取完成" if not incomplete else "运行详情页手动补跑未成功，未生成可信记忆批次",
            output_summary=f"{result.get('memory_items_count', 0)} 条候选记忆",
        )
        if incomplete:
            message = memory_incomplete_message(result)
            repo.update_workflow_run(
                backfill_run_id,
                status="failed",
                current_node="memory_curator",
                error_message=message,
            )
            # v6.6.10: Determine domain result for incomplete extraction
            from ..contracts import fallback as domain_fallback, failed as domain_failed, degraded as domain_degraded
            incomplete_details = memory_incomplete_details(
                result,
                project_id=project_id,
                chapter_number=chapter_number,
                run_id=backfill_run_id,
            )
            if result.get("fallback_created") or result.get("memory_curator_fallback"):
                domain_result = domain_fallback(
                    message,
                    user_message="补跑记忆提取仅产生低可信候选，不可作为后续章节可信记忆",
                    next_action="backfill_memory",
                    action_label="重新补跑记忆",
                    details=incomplete_details,
                )
            elif result.get("memory_curator_degraded"):
                domain_result = domain_degraded(
                    message,
                    user_message="MemoryCurator 降级，未生成可信记忆",
                    next_action="backfill_memory",
                    action_label="重新补跑记忆",
                    details=incomplete_details,
                )
            else:
                domain_result = domain_failed(
                    message,
                    user_message="补跑记忆提取失败，可尝试重新补跑",
                    next_action="backfill_memory",
                    action_label="重新补跑记忆",
                    details=incomplete_details,
                )
            incomplete_details["domain_result"] = domain_result.to_dict()
            return error_response(
                "MEMORY_CURATOR_INCOMPLETE",
                message,
                details=incomplete_details,
            )

        repo.update_workflow_run(backfill_run_id, status="completed", current_node="memory_curator", clear_error=True)

        # v6.6.10: Domain result for successful extraction
        from ..contracts import success as domain_success, fallback as domain_fallback
        if extraction_success and not result.get("fallback_created", False):
            domain_result = domain_success(
                f"记忆提取补跑完成：{result.get('memory_items_count', 0)} 条可信候选",
                flags={"memory_trusted": True},
            )
        else:
            domain_result = domain_fallback(
                f"记忆提取补跑产生低可信候选：{result.get('memory_items_count', 0)} 条",
                user_message="补跑仅产生低可信候选，不可作为后续章节可信记忆",
                next_action="backfill_memory",
                action_label="重新补跑记忆",
                flags={"memory_trusted": False, "memory_fallback": True},
            )

        return envelope_response({
            "skipped": False,
            "run_id": backfill_run_id,
            "source_run_id": run_id,
            "project_id": project_id,
            "chapter": chapter_number,
            "chapter_status": current_status,
            "memory_batch_id": result.get("memory_batch_id"),
            "memory_items_count": result.get("memory_items_count", 0),
            # v6.6.7: Clear three-category semantics
            "extraction_success": extraction_success,
            "fallback_created": result.get("fallback_created", False),
            "trusted": extraction_success and not result.get("fallback_created", False),
            "memory_curator_degraded": result.get("memory_curator_degraded", False),
            "memory_curator_fallback": result.get("memory_curator_fallback"),
            "message": (
                f"记忆提取补跑完成：{result.get('memory_items_count', 0)} 条可信候选"
                if extraction_success
                else f"记忆提取失败，仅生成低可信候选：{result.get('memory_items_count', 0)} 条"
            ),
            # v6.6.10: Unified domain result
            "domain_result": domain_result.to_dict(),
        })
    except Exception as e:
        message = f"补跑记忆提取失败: {str(e)}"
        return error_response(
            "INTERNAL_ERROR",
            message,
            details={
                "domain_result": failed(
                    message,
                    user_message="补跑记忆提取失败，可稍后重试",
                    retryable=True,
                    next_action="backfill_memory",
                    action_label="重新补跑记忆",
                    details={"run_id": run_id, "error_code": "INTERNAL_ERROR"},
                    flags={"memory_backfill_failed": True},
                ).to_dict()
            },
        )


def _get_run_by_id(repo, run_id: str, *, reconcile: bool = True) -> dict | None:
    """Fetch workflow_run by id."""
    conn = repo._conn()
    try:
        row = conn.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        run_data = dict(row) if row else None
    finally:
        conn.close()
    if not run_data:
        return None

    if reconcile and hasattr(repo, "restore_memory_curator_reset_recovery_runs"):
        restored = repo.restore_memory_curator_reset_recovery_runs(run_id=run_id)
        if restored:
            return _get_run_by_id(repo, run_id, reconcile=False)

    if reconcile and complete_memory_curator_recovery_if_trusted(
        repo,
        run_data["project_id"],
        int(run_data["chapter_number"]),
        run_id=run_id,
    ):
        return _get_run_by_id(repo, run_id, reconcile=False)

    if reconcile and complete_memory_curator_run_if_batch_exists(
        repo,
        run_data["project_id"],
        int(run_data["chapter_number"]),
        run_id=run_id,
    ):
        return _get_run_by_id(repo, run_id, reconcile=False)

    if reconcile and _block_memory_curator_timeout_run_if_needed(repo, run_data):
        return _get_run_by_id(repo, run_id, reconcile=False)

    chapter = repo.get_chapter(run_data["project_id"], run_data["chapter_number"])
    if (
        reconcile
        and chapter
        and run_data.get("status") == "running"
        and chapter.get("status") in ("reviewed", "awaiting_publish", "published")
        and hasattr(repo, "reconcile_terminal_chapter_running_workflows")
    ):
        reconciliation = repo.reconcile_terminal_chapter_running_workflows(
            project_id=run_data["project_id"],
            chapter_number=run_data["chapter_number"],
            run_id=run_id,
        )
        if reconciliation.get("runs"):
            return _get_run_by_id(repo, run_id)
    return run_data


def _has_memory_curator_evidence(repo, project_id: str, chapter_number: int) -> bool:
    """Return True when a trusted user-visible memory batch exists."""
    return _has_memory_batch_for_chapter(repo, project_id, chapter_number)


def _has_memory_batch_for_chapter(repo, project_id: str, chapter_number: int) -> bool:
    """Return True only when the chapter has a trusted memory inbox batch."""
    return has_trusted_memory_batch(repo, project_id, chapter_number)


def _is_trusted_memory_batch(repo, batch: dict) -> bool:
    """Exclude ignored batches and state-card fallback hints from memory evidence."""
    return is_trusted_memory_batch(repo, batch)


def _checkpoint_exists(repo, project_id: str, chapter_number: int) -> bool:
    """Best-effort checkpoint existence probe."""
    try:
        from ...workflow.checkpoint import checkpoint_thread_exists

        return checkpoint_thread_exists(repo.db_path, project_id, chapter_number)
    except Exception:
        return False


def _list_run_health_rows(repo, project_id: str | None, limit: int) -> list[dict]:
    """List recent issue-bearing runs for the health dashboard."""
    if hasattr(repo, "reconcile_terminal_chapter_running_workflows"):
        repo.reconcile_terminal_chapter_running_workflows(project_id=project_id)
    conn = repo._conn()
    try:
        where = "WHERE wr.status IN ('running', 'blocked', 'failed')"
        params: list[object] = []
        if project_id:
            where += " AND wr.project_id=?"
            params.append(project_id)
        params.append(limit)
        rows = conn.execute(
            "SELECT wr.*, p.name AS project_name, c.status AS chapter_status "
            "FROM workflow_runs wr "
            "LEFT JOIN projects p ON p.project_id = wr.project_id "
            "LEFT JOIN chapters c ON c.project_id = wr.project_id "
            "AND c.chapter_number = wr.chapter_number "
            f"{where} "
            "ORDER BY wr.started_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _build_run_health_item(repo, run_data: dict, timeout_minutes: int) -> dict:
    """Build a single run health row."""
    stuck_info = _detect_stuck_run(repo, run_data, timeout_minutes)
    chapter_status = run_data.get("chapter_status") or "unknown"
    can_mark_stuck = bool(stuck_info.get("stuck")) and chapter_status != "unknown"
    return {
        "run_id": run_data.get("id"),
        "project_id": run_data.get("project_id"),
        "project_name": run_data.get("project_name") or run_data.get("project_id"),
        "chapter_number": run_data.get("chapter_number"),
        "workflow_status": run_data.get("status", "unknown"),
        "chapter_status": chapter_status,
        "current_node": run_data.get("current_node"),
        "started_at": run_data.get("started_at"),
        "completed_at": run_data.get("completed_at"),
        "error_message": run_data.get("error_message"),
        "elapsed_minutes": stuck_info.get("elapsed_minutes"),
        "stuck": bool(stuck_info.get("stuck", False)),
        "stuck_reason": stuck_info.get("reason"),
        "running_tasks": stuck_info.get("running_tasks", []),
        "actions": {
            "mark_stuck_blocked": {
                "enabled": can_mark_stuck,
                "reason": (
                    stuck_info.get("reason")
                    if can_mark_stuck
                    else "运行未达到卡住阈值或章节状态不可标记。"
                ),
            },
        },
    }


def _mark_stuck_run_for_recovery(repo, settings, run_id: str) -> dict:
    """Shared implementation for single and batch mark-stuck actions."""
    timeout_minutes = settings.workflow.task_timeout_minutes
    run_data = _get_run_by_id(repo, run_id, reconcile=False)
    if not run_data:
        return {
            "ok": False,
            "run_id": run_id,
            "error_code": "RUN_NOT_FOUND",
            "message": f"运行记录 '{run_id}' 不存在",
        }

    recovery = _build_recovery_state(
        repo,
        run_data,
        max_retries=settings.quality_gate.max_retries,
        timeout_minutes=timeout_minutes,
    )
    if not recovery.get("stuck", False):
        return {
            "ok": False,
            "run_id": run_id,
            "error_code": "RUN_NOT_STUCK",
            "message": "运行尚未超过卡住阈值，不能标记为阻塞",
            "details": {
                "elapsed_minutes": recovery.get("elapsed_minutes"),
                "timeout_minutes": timeout_minutes,
            },
        }

    project_id = run_data["project_id"]
    chapter_number = run_data["chapter_number"]
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter:
        return {
            "ok": False,
            "run_id": run_id,
            "error_code": "CHAPTER_NOT_FOUND",
            "message": f"章节 {chapter_number} 不存在",
        }

    current_status = chapter.get("status", "")
    preserve_chapter_status = current_status in PUBLISH_READY_CHAPTER_STATUSES
    new_chapter_status = current_status if preserve_chapter_status else "blocking"

    message = (
        f"运行疑似卡住：超过 {timeout_minutes} 分钟仍为 running。"
        f" current_node={run_data.get('current_node') or '-'}"
    )
    repo.update_workflow_run(run_id, status="blocked", error_message=message)
    closed_running_tasks = _fail_running_tasks_for_run(
        repo,
        project_id,
        chapter_number,
        workflow_run_id=run_id,
        message=message,
    )
    released_memory_lock = False
    if hasattr(repo, "release_memory_curator_lock"):
        released_memory_lock = bool(
            repo.release_memory_curator_lock(project_id, chapter_number, run_id=run_id)
        )
    if not preserve_chapter_status:
        _set_chapter_status_unchecked(repo, project_id, chapter_number, "blocking")
    _insert_recovery_audit(
        repo,
        project_id,
        chapter_number,
        workflow_run_id=run_id,
        message=message,
        task_type="recover",
        agent_id="system",
    )

    refreshed = _get_run_by_id(repo, run_id) or run_data
    return {
        "ok": True,
        "run_id": run_id,
        "data": {
            "marked": True,
            "run_id": run_id,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "previous_chapter_status": current_status,
            "new_chapter_status": new_chapter_status,
            "workflow_status": "blocked",
            "message": message,
            "closed_running_tasks": closed_running_tasks,
            "released_memory_lock": released_memory_lock,
            "recovery": _build_recovery_state(
                repo,
                refreshed,
                max_retries=settings.quality_gate.max_retries,
                timeout_minutes=timeout_minutes,
            ),
        },
    }


def _build_recovery_state(
    repo,
    run_data: dict,
    max_retries: int = 3,
    timeout_minutes: int = 30,
) -> dict:
    """Build user-facing recovery state for a run.

    v6.6.6: Uses derive_workflow_recovery_state() for canonical recovery state,
    then merges with existing fields for backward compatibility.
    """
    from ...workflow.state_integrity import derive_workflow_recovery_state
    from ...workflow.checkpoint import inspect_checkpoint_thread

    project_id = run_data["project_id"]
    chapter_number = run_data["chapter_number"]
    chapter = repo.get_chapter(project_id, chapter_number)
    chapter_status = chapter.get("status", "unknown") if chapter else "unknown"
    retry_count = repo.get_chapter_retry_count(project_id, chapter_number)
    stuck_info = _detect_stuck_run(repo, run_data, timeout_minutes)
    can_mark_stuck = bool(stuck_info.get("stuck", False)) and chapter_status != "unknown"
    recoverable_node = _resolve_recoverable_node(repo, run_data)
    memory_trusted = has_trusted_memory_batch(repo, project_id, chapter_number)
    preserve_chapter_status = _run_recovery_preserves_chapter_status(run_data, chapter_status)
    memory_backfill_only = (
        recoverable_node == "memory_curator"
        and not memory_trusted
        and chapter_status in PUBLISH_READY_CHAPTER_STATUSES
        and run_data.get("status") in {"running", "blocked", "failed"}
    )
    can_reset = (chapter_status in RESETTABLE_CHAPTER_STATUSES or preserve_chapter_status) and not memory_backfill_only
    retry_target = _node_retry_target(recoverable_node)
    can_retry_node = bool(retry_target and chapter_status in ("blocking", "revision"))
    reason = None
    if not chapter:
        reason = "章节不存在"
    elif memory_backfill_only:
        reason = "记忆整理节点失败或超时；正文已通过审核，应补跑记忆提取，不应重置整章。"
    elif chapter_status == "planned":
        reason = "章节已为 planned，可清除旧运行和 checkpoint 后重新开始工作流。"
    elif preserve_chapter_status:
        reason = f"章节已处于 {chapter_status}，可清理阻塞运行和 checkpoint 后继续后续操作。"
    elif can_reset:
        reason = "可清除阻塞/返修状态并回到 planned，重新开始工作流。"
    else:
        reason = f"章节状态为 '{chapter_status}'，无需或不可执行恢复。"

    # v6.6.6: Get checkpoint info for recovery state derivation
    checkpoint_info = None
    try:
        checkpoint_info = inspect_checkpoint_thread(repo.db_path, project_id, chapter_number)
    except Exception:
        checkpoint_info = {"checkpoint_exists": False}

    # v6.6.6: Derive canonical recovery state
    has_existing_content = bool(chapter and chapter.get("content"))
    recovery_run_data = run_data
    if stuck_info.get("active_node_started_at"):
        recovery_run_data = {
            **run_data,
            "started_at": stuck_info["active_node_started_at"],
        }
    recovery_state = derive_workflow_recovery_state(
        chapter=chapter,
        latest_run=recovery_run_data,
        checkpoint_info=checkpoint_info,
        has_existing_content=has_existing_content,
    )

    # Merge canonical state with legacy fields for backward compatibility
    return {
        "run_id": run_data.get("id"),
        "project_id": project_id,
        "chapter_number": chapter_number,
        "workflow_status": run_data.get("status", "unknown"),
        "chapter_status": chapter_status,
        "error_message": _resolve_run_error_message(repo, run_data, chapter),
        "retry_count": retry_count,
        "max_retries": max_retries,
        "timeout_minutes": timeout_minutes,
        "elapsed_minutes": stuck_info.get("elapsed_minutes"),
        "active_node_elapsed_minutes": stuck_info.get("active_node_elapsed_minutes"),
        "stuck": stuck_info.get("stuck", False),
        "stuck_reason": stuck_info.get("reason"),
        "running_tasks": stuck_info.get("running_tasks", []),
        "checkpoint_exists": _checkpoint_exists(repo, project_id, chapter_number),
        "can_reset": can_reset,
        "actions": {
            "reset_to_planned": {
                "enabled": can_reset,
                "label": "清除阻塞运行" if preserve_chapter_status else "清除阻塞并回到 planned",
                "reason": reason,
            },
            "mark_stuck_blocked": {
                "enabled": can_mark_stuck,
                "label": "标记为阻塞",
                "reason": (
                    stuck_info.get("reason")
                    if can_mark_stuck
                    else "运行未达到卡住阈值或章节状态不可标记。"
                ),
            },
            "retry_current_node": {
                "enabled": can_retry_node,
                "label": f"重试{retry_target['label']}" if retry_target else "定点重试",
                "reason": (
                    f"保留已有产物，将章节恢复到 {retry_target['status']}，"
                    f"下次生成直接从{retry_target['label']}继续。"
                    if retry_target
                    else "当前节点不支持定点重试。"
                ),
                "target_status": retry_target["status"] if retry_target else None,
                "target_node": retry_target["node"] if retry_target else None,
                "resolved_failed_node": recoverable_node,
            },
            "backfill_memory": {
                "enabled": memory_backfill_only,
                "label": "补跑记忆提取",
                "reason": (
                    "只重跑 Memory Curator，不覆盖正文、版本和审核结果。"
                    if memory_backfill_only
                    else "当前运行不需要补跑记忆。"
                ),
            },
        },
        # v6.6.6: Canonical recovery state
        "recovery_state": recovery_state,
    }


def _node_retry_target(current_node: str | None) -> dict | None:
    """Return the last safe DB status for retrying a failed node."""
    return node_retry_target(current_node)


def _parse_db_datetime(value: str | None) -> datetime | None:
    """Parse DB datetime strings written as UTC+8 wall-clock time."""
    if not value:
        return None
    try:
        normalized = value.replace("T", " ").replace("Z", "")
        return datetime.fromisoformat(normalized).replace(tzinfo=timezone(timedelta(hours=8)))
    except Exception:
        return None


def _normalize_timestamp(ts: str | None) -> str | None:
    """Normalize timestamp to ISO 8601 format with UTC+8 timezone."""
    if not ts:
        return None
    if "T" in ts and ("+" in ts or "Z" in ts or ts.endswith("00:00")):
        return ts
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone(timedelta(hours=8))).isoformat()
    except (ValueError, TypeError):
        return ts


def _elapsed_minutes_since(value: str | None) -> float | None:
    started = _parse_db_datetime(value)
    if not started:
        return None
    now = datetime.now(tz=timezone(timedelta(hours=8)))
    return max(0.0, (now - started).total_seconds() / 60)


def _detect_stuck_run(repo, run_data: dict, timeout_minutes: int) -> dict:
    """Detect whether a workflow run or its running tasks are stale."""
    if run_data.get("status") != "running":
        return {"stuck": False, "reason": None, "running_tasks": []}

    elapsed = _elapsed_minutes_since(run_data.get("started_at"))

    project_id = run_data.get("project_id")
    chapter_number = run_data.get("chapter_number")
    run_id = str(run_data.get("id") or run_data.get("run_id") or "")
    running_tasks = []
    task_stuck = False
    try:
        conn = repo._conn()
        try:
            rows = conn.execute(
                "SELECT id, task_type, agent_id, started_at FROM task_status "
                "WHERE project_id=? AND chapter_number=? AND status='running' "
                "AND workflow_run_id=? "
                "ORDER BY started_at DESC",
                (project_id, chapter_number, run_data.get("id")),
            ).fetchall()
            for row in rows:
                task_elapsed = _elapsed_minutes_since(row["started_at"])
                task_type = row["task_type"]
                agent_id = row["agent_id"]
                task = {
                    "id": row["id"],
                    "task_type": task_type,
                    "task_label": _task_type_display_name(task_type),
                    "agent_id": agent_id,
                    "agent_label": _agent_display_name(agent_id),
                    "started_at": row["started_at"],
                    "elapsed_minutes": task_elapsed,
                    "stuck": task_elapsed is not None and task_elapsed >= timeout_minutes,
                }
                if task["stuck"]:
                    task_stuck = True
                running_tasks.append(task)
        finally:
            conn.close()
    except Exception:
        running_tasks = []

    active_node_started_at = None
    active_node_elapsed = None
    active_node_stuck = False
    current_node = str(run_data.get("current_node") or "").strip()
    try:
        events = repo.get_workflow_node_events(run_id) if run_id else []
        active_node_started_at = active_node_started_at_from_events(events, current_node)
    except Exception:
        active_node_started_at = None
    if active_node_started_at:
        active_node_elapsed = _elapsed_minutes_since(active_node_started_at)
        active_node_stuck = active_node_elapsed is not None and active_node_elapsed >= timeout_minutes
        if not running_tasks and current_node:
            target = _node_retry_target(current_node)
            node_label = target["label"] if target else _agent_display_name(current_node)
            running_tasks.append({
                "id": None,
                "task_type": current_node,
                "task_label": f"{node_label}节点",
                "agent_id": current_node,
                "agent_label": node_label,
                "started_at": active_node_started_at,
                "elapsed_minutes": active_node_elapsed,
                "stuck": active_node_stuck,
                "source": "workflow_node_event",
            })

    fallback_run_stuck = (
        elapsed is not None
        and elapsed >= timeout_minutes
        and not running_tasks
        and not active_node_started_at
    )

    memory_timeout_event = _has_memory_curator_timeout_event(repo, run_id)
    stuck = fallback_run_stuck or task_stuck or active_node_stuck or memory_timeout_event
    reason = None
    if memory_timeout_event:
        reason = "MemoryCurator 已记录节点超时/失败事件，可直接标记阻塞并释放记忆锁。"
    elif active_node_stuck:
        node_label = _node_retry_target(current_node) or {}
        display = node_label.get("label") or _agent_display_name(current_node)
        reason = (
            f"当前节点{display}已超过 {timeout_minutes} 分钟未完成，"
            "可先标记为阻塞再执行定点重试。"
        )
    elif task_stuck:
        reason = (
            f"当前运行任务已超过 {timeout_minutes} 分钟未完成，"
            "可先标记为阻塞再执行恢复。"
        )
    elif stuck:
        reason = (
            f"运行已超过 {timeout_minutes} 分钟仍处于 running，"
            "可先标记为阻塞再执行恢复。"
        )
    return {
        "stuck": stuck,
        "reason": reason,
        "elapsed_minutes": elapsed,
        "active_node_started_at": active_node_started_at,
        "active_node_elapsed_minutes": active_node_elapsed,
        "running_tasks": running_tasks,
    }


def _has_memory_curator_timeout_event(repo, run_id: str) -> bool:
    """Return True when MemoryCurator already recorded a timeout/failure event."""
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


def _block_memory_curator_timeout_run_if_needed(repo, run_data: dict) -> bool:
    """Convert a timed-out MemoryCurator run to an explicit blocked node."""
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
    recoverable_node = _resolve_recoverable_node(repo, run_data)
    if recoverable_node != "memory_curator":
        return False
    _release_memory_timeout_lock_if_recoverable(
        repo,
        project_id,
        chapter_number,
        run_id,
    )
    return True


def _release_memory_timeout_lock_if_recoverable(
    repo,
    project_id: str,
    chapter_number: int,
    run_id: str,
) -> bool:
    """Release a MemoryCurator lock after that same run already timed out.

    This is intentionally not a publish-ready reconciliation. The original run
    stays at memory_curator and becomes blocked, so the UI still shows the
    correct failed node and does not expose publish as the primary action.
    """
    if not run_id or not _has_memory_curator_timeout_event(repo, run_id):
        return False
    released = False
    if hasattr(repo, "release_memory_curator_lock"):
        released = bool(repo.release_memory_curator_lock(project_id, chapter_number, run_id=run_id))
    try:
        repo.update_workflow_run(
            run_id,
            status="blocked",
            current_node="memory_curator",
            error_message="节点 memory_curator 执行超时（>600秒），需要补跑记忆提取",
        )
    except Exception:
        pass
    return released


def _set_chapter_status_unchecked(
    repo,
    project_id: str,
    chapter_number: int,
    status: str,
) -> None:
    """Set chapter status for system recovery audit paths."""
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE chapters SET status=?, updated_at=datetime('now','+8 hours') "
            "WHERE project_id=? AND chapter_number=?",
            (status, project_id, chapter_number),
        )
        conn.commit()
    finally:
        conn.close()


def _fail_running_tasks_for_run(
    repo,
    project_id: str,
    chapter_number: int,
    workflow_run_id: str,
    message: str,
) -> int:
    """Close run-scoped running task rows when a run is marked stuck."""
    conn = repo._conn()
    try:
        cursor = conn.execute(
            "UPDATE task_status SET status='failed', completed_at=datetime('now','+8 hours'), "
            "error_message=? "
            "WHERE project_id=? AND chapter_number=? AND workflow_run_id=? "
            "AND status='running'",
            (message, project_id, chapter_number, workflow_run_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def _insert_recovery_audit(
    repo,
    project_id: str,
    chapter_number: int,
    workflow_run_id: str,
    message: str,
    task_type: str,
    agent_id: str,
) -> None:
    """Insert a run-scoped recovery audit row."""
    conn = repo._conn()
    try:
        conn.execute(
            "INSERT INTO task_status "
            "(project_id, chapter_number, task_type, agent_id, status, "
            "started_at, completed_at, error_message, workflow_run_id) "
            "VALUES (?, ?, ?, ?, 'completed', datetime('now','+8 hours'), "
            "datetime('now','+8 hours'), ?, ?)",
            (project_id, chapter_number, task_type, agent_id, message, workflow_run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _resolve_run_error_message(repo, run_data: dict, chapter: dict | None) -> str | None:
    """Resolve a user-facing error for historical blocked runs with empty errors."""
    error_message = run_data.get("error_message")
    if error_message:
        return error_message

    if run_data.get("status") != "blocked":
        return None

    chapter_status = chapter.get("status") if chapter else None
    if chapter_status != "blocking":
        return None

    project_id = run_data.get("project_id", "")
    chapter_number = run_data.get("chapter_number", 0)
    started_at = run_data.get("started_at", "")

    previous_error = None
    try:
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT error_message FROM workflow_runs "
                "WHERE project_id=? AND chapter_number=? "
                "AND error_message IS NOT NULL AND error_message != '' "
                "AND started_at <= ? AND id != ? "
                "ORDER BY started_at DESC LIMIT 1",
                (project_id, chapter_number, started_at, run_data.get("id")),
            ).fetchone()
            if row:
                previous_error = row["error_message"]
        finally:
            conn.close()
    except Exception:
        previous_error = None

    message = "章节已处于阻塞状态，请先解除阻塞后再重新执行工作流。"
    if previous_error:
        message += f" 历史阻塞原因: {previous_error}"
    return message


def _build_steps_timeline(
    run_data: dict,
    chapter: dict | None,
    llm_mode: str,
    repo=None,
) -> list[dict]:
    """Build steps timeline from run data and chapter status.

    Derives step status from:
    1. workflow_runs.current_node (last running agent)
    2. chapter.status (final status)
    3. STATUS_ROUTE (expected flow)
    4. task_status table (per-agent lifecycle and error messages)
    5. agent_artifacts table (per-agent artifact summaries)
    """
    workflow_status = run_data.get("status", "unknown")
    current_node = run_data.get("current_node")
    error_message = run_data.get("error_message")
    chapter_number = run_data.get("chapter_number", 1)
    project_id = run_data.get("project_id", "")
    graph_name = run_data.get("graph_name", "chapter_production")

    if graph_name in {"memory_backfill", "manual_publish_memory"}:
        logs: list[dict] = []
        if repo and run_data.get("id"):
            try:
                events = repo.get_workflow_node_events(run_data["id"])
            except Exception:
                events = []
            for event in events:
                if event.get("node_name") != "memory_curator":
                    continue
                level = "info"
                if event.get("status") in {"failed", "error"} or event.get("event_type") == "failed":
                    level = "error"
                elif event.get("status") == "warning":
                    level = "warning"
                elif event.get("status") in {"completed", "success"} or event.get("event_type") == "completed":
                    level = "success"
                logs.append({
                    "timestamp": event.get("created_at") or event.get("timestamp"),
                    "level": level,
                    "message": event.get("message") or event.get("error_message") or "记忆整理事件",
                })
        step_status = "pending"
        if workflow_status == "running":
            step_status = "running"
        elif workflow_status == "completed":
            step_status = "completed"
        elif workflow_status == "failed":
            step_status = "failed"
        elif workflow_status == "blocked":
            step_status = "blocked"
        return [{
            "key": "memory_curator",
            "label": "记忆整理",
            "description": "补跑章节记忆提取",
            "status": step_status,
            "agent_id": "memory_curator",
            "artifacts": None,
            "logs": logs,
            "error_message": error_message if workflow_status == "failed" else None,
        }]

    # Determine final chapter status
    final_status = chapter.get("status", "planned") if chapter else "planned"
    if (
        graph_name == "chapter_production"
        and workflow_status == "running"
        and current_node != "memory_curator"
        and final_status in ("reviewed", "awaiting_publish", "published")
    ):
        workflow_status = "completed"
        current_node = "publish" if final_status == "published" else "awaiting_publish"
        error_message = None

    # Fetch task_status for per-agent error info
    # P1: Prefer run-isolated rows; fallback to chapter-level for legacy data.
    task_errors: dict[str, str] = {}
    task_errors_legacy: dict[str, str] = {}
    task_logs: dict[str, list[dict]] = {}
    failed_event_node: str | None = None
    failed_event_error: str | None = None
    if repo:
        try:
            conn = repo._conn()
            try:
                run_id = run_data.get("id")
                # Try run-isolated query first
                if run_id:
                    rows = conn.execute(
                        "SELECT agent_id, status, error_message FROM task_status "
                        "WHERE project_id=? AND chapter_number=? AND status='failed' "
                        "AND workflow_run_id=?",
                        (project_id, chapter_number, run_id),
                    ).fetchall()
                    for r in rows:
                        agent_id = r["agent_id"]
                        if r["error_message"]:
                            task_errors[agent_id] = r["error_message"]
                # Legacy fallback: rows without workflow_run_id
                legacy_rows = conn.execute(
                    "SELECT agent_id, status, error_message FROM task_status "
                    "WHERE project_id=? AND chapter_number=? AND status='failed' "
                    "AND workflow_run_id IS NULL",
                    (project_id, chapter_number),
                ).fetchall()
                for r in legacy_rows:
                    agent_id = r["agent_id"]
                    if r["error_message"]:
                        task_errors_legacy[agent_id] = r["error_message"]

                if run_id:
                    lifecycle_rows = conn.execute(
                        "SELECT agent_id, task_type, status, error_message, started_at, completed_at "
                        "FROM task_status "
                        "WHERE project_id=? AND chapter_number=? AND workflow_run_id=? "
                        "ORDER BY started_at ASC, id ASC",
                        (project_id, chapter_number, run_id),
                    ).fetchall()
                else:
                    lifecycle_rows = []
                for r in lifecycle_rows:
                    agent_id = r["agent_id"]
                    task_label = _task_type_display_name(r["task_type"])
                    task_type = r["task_type"]
                    agent_label = _agent_display_name(agent_id)
                    if agent_id not in task_logs:
                        task_logs[agent_id] = []
                    if r["started_at"]:
                        started_message = (
                            f"返修已派发给{agent_label}。"
                            if task_type == "revise"
                            else f"{task_label}已开始处理。"
                        )
                        task_logs[agent_id].append({
                            "timestamp": _normalize_timestamp(r["started_at"]),
                            "level": "info",
                            "message": started_message,
                        })
                    if r["status"] == "completed" and r["completed_at"]:
                        completed_message = (
                            f"返修派发已确认，等待{agent_label}节点执行。"
                            if task_type == "revise"
                            else f"{task_label}已完成。"
                        )
                        task_logs[agent_id].append({
                            "timestamp": _normalize_timestamp(r["completed_at"]),
                            "level": "success",
                            "message": completed_message,
                        })
                    elif r["status"] == "failed":
                        task_logs[agent_id].append({
                            "timestamp": _normalize_timestamp(r["completed_at"] or r["started_at"]),
                            "level": "error",
                            "message": r["error_message"] or f"{task_label}失败。",
                        })
            finally:
                conn.close()
        except Exception:
            pass  # Graceful degradation

        if run_data.get("id"):
            try:
                failed_events = [
                    ev for ev in repo.get_workflow_node_events(run_data["id"])
                    if ev.get("node_name") in {step["key"] for step in AGENT_STEPS}
                    and (
                        ev.get("status") in {"failed", "error"}
                        or ev.get("event_type") in {"failed", "node_failed"}
                        or ev.get("error_message")
                    )
                ]
                if failed_events:
                    latest_failed = failed_events[-1]
                    failed_event_node = latest_failed.get("node_name")
                    failed_event_error = (
                        latest_failed.get("error_message")
                        or latest_failed.get("message")
                        or error_message
                    )
            except Exception:
                pass  # Graceful degradation

    # Fetch agent_artifacts for per-agent artifact summaries
    # P1 fix: Prefer run-level isolation; fallback to chapter-level for legacy data
    agent_artifacts: dict[str, list[dict]] = {}
    artifacts_source = "run"  # 'run' | 'chapter_fallback'
    if repo:
        try:
            run_id = run_data.get("id")
            if run_id:
                artifacts = repo.get_artifacts_for_chapter(
                    project_id, chapter_number, workflow_run_id=run_id
                )
                if not artifacts:
                    # Fallback: legacy artifacts without run_id
                    artifacts = repo.get_artifacts_for_chapter(project_id, chapter_number)
                    artifacts_source = "chapter_fallback"
            else:
                artifacts = repo.get_artifacts_for_chapter(project_id, chapter_number)
                artifacts_source = "chapter_fallback"
            for a in artifacts:
                aid = a.get("agent_id", "")
                if aid not in agent_artifacts:
                    agent_artifacts[aid] = []
                agent_artifacts[aid].append(a)
        except Exception:
            pass  # Graceful degradation

    # Determine which steps completed
    # Based on STATUS_ROUTE: planned -> screenwriter -> author -> polisher -> editor -> publish
    completed_agents = []
    if final_status in ("scripted", "drafted", "polished", "reviewed", "published"):
        completed_agents.append("screenwriter")
    if final_status in ("drafted", "polished", "reviewed", "published"):
        completed_agents.append("author")
    if final_status in ("polished", "reviewed", "published"):
        completed_agents.append("polisher")
    if final_status in ("reviewed", "published"):
        completed_agents.append("editor")
    if final_status == "published":
        completed_agents.append("publish")
    for key in ("planner", "screenwriter", "author", "polisher", "editor", "publish"):
        if key in agent_artifacts and key not in completed_agents:
            completed_agents.append(key)

    blocked_agent = current_node
    if workflow_status == "blocked" and current_node == "human_review":
        if failed_event_node:
            blocked_agent = failed_event_node
            if failed_event_error:
                task_errors.setdefault(failed_event_node, failed_event_error)
        elif "editor" in agent_artifacts or final_status in ("blocking", "revision"):
            blocked_agent = "editor"
        elif "polisher" in agent_artifacts:
            blocked_agent = "polisher"
        elif "author" in agent_artifacts:
            blocked_agent = "author"
        elif "screenwriter" in agent_artifacts:
            blocked_agent = "screenwriter"

    # Build steps. Planner is an optional pre-step: only show it when it
    # actually participated in the run, otherwise the normal chapter workflow
    # remains the compact five-step timeline.
    visible_step_configs = [
        step for step in AGENT_STEPS
        if step["key"] != "planner"
        or current_node == "planner"
        or "planner" in completed_agents
        or "planner" in agent_artifacts
    ]
    steps = []
    for step_config in visible_step_configs:
        key = step_config["key"]
        is_completed = key in completed_agents
        is_publish_node = key == "publish" and current_node in ("publish", "publisher", "awaiting_publish")
        is_running = (current_node == key or is_publish_node) and workflow_status == "running"
        is_failed = (current_node == key or is_publish_node) and workflow_status == "failed"
        is_blocked = (blocked_agent == key) and workflow_status == "blocked"

        if is_failed:
            step_status = "failed"
        elif is_blocked:
            step_status = "blocked"
        elif is_running:
            step_status = "running"
        elif is_completed:
            step_status = "completed"
        else:
            step_status = "pending"

        step = {
            "key": key,
            "label": step_config["label"],
            "description": step_config["description"],
            "status": step_status,
            "agent_id": key,
        }

        logs = list(task_logs.get(key, []))
        if not logs:
            if step_status == "running":
                logs.append({
                    "timestamp": run_data.get("started_at"),
                    "level": "info",
                    "message": f"{step_config['label']}节点运行中，正在等待模型或工具返回。",
                })
            elif step_status == "completed":
                logs.append({
                    "timestamp": run_data.get("completed_at") or run_data.get("started_at"),
                    "level": "success",
                    "message": f"{step_config['label']}节点已完成。",
                })
            elif step_status in ("failed", "blocked"):
                # v6.6.21: Always emit a started log so node_started is not conflated with failure
                logs.append({
                    "timestamp": run_data.get("started_at"),
                    "level": "info",
                    "message": f"{step_config['label']}节点已开始处理。",
                })
                logs.append({
                    "timestamp": run_data.get("completed_at") or run_data.get("started_at"),
                    "level": "error" if step_status == "failed" else "warning",
                    "message": error_message or f"{step_config['label']}节点需要人工处理。",
                })

        # Add error message for failed step
        if (is_failed or is_blocked) and error_message:
            step["error_message"] = error_message
        elif key in task_errors:
            step["error_message"] = task_errors[key]
        elif key in task_errors_legacy:
            step["error_message"] = task_errors_legacy[key]
            step["error_is_legacy"] = True

        # Add artifacts for completed steps
        stub_artifacts = _generate_stub_artifacts(key, chapter_number) if is_completed and llm_mode == "stub" else None
        if stub_artifacts:
            step["artifacts"] = stub_artifacts
        elif key in agent_artifacts and agent_artifacts[key]:
            # Build artifacts summary from DB
            artifacts_list = agent_artifacts[key]
            step["artifacts"] = _build_artifact_display_summary(artifacts_list)
            # P1: indicate if artifacts came from legacy fallback (not run-isolated)
            step["artifacts"]["is_legacy_fallback"] = artifacts_source == "chapter_fallback"
        else:
            step["artifacts"] = None

        if step["artifacts"] and step_status == "completed":
            logs.append({
                "timestamp": run_data.get("completed_at") or run_data.get("started_at"),
                "level": "info",
                "message": f"已生成产物：{step['artifacts'].get('summary', 'Agent 产物')}",
            })

        if logs:
            step["logs"] = logs

        steps.append(step)

    return steps


@router.get("/run/chapter/stream")
async def run_chapter_stream(
    request: Request,
    project_id: str,
    chapter: int,
) -> StreamingResponse:
    """Run chapter with SSE streaming (v5.2 Phase C).

    Streams real-time progress events during chapter generation.

    Event types:
    - step_start: Agent started processing
    - step_complete: Agent finished with timing info
    - run_complete: Workflow finished successfully
    - run_error: Workflow failed with error
    """
    from ..deps import get_repo, get_settings, get_llm_mode
    from ...workflow.runner import run_with_graph_stream

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        llm_mode = get_llm_mode(request)

        # v5.5.15: Unified run guard — same checks as POST /run/chapter.
        # For SSE, guard violations are returned as structured error events
        # rather than HTTP error responses so the client can display them.
        from ._run_guards import check_chapter_run_guard

        guard_error, preflight_warnings = check_chapter_run_guard(repo, project_id, chapter)
        if guard_error:

            async def guard_event():
                error_data = {'type': 'run_error', 'error': guard_error.message, 'code': guard_error.code, 'details': guard_error.details}
                if preflight_warnings:
                    error_data['preflight_warnings'] = preflight_warnings
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                guard_event(),
                media_type="text/event-stream",
            )

        def next_stream_event(iterator):
            try:
                return False, next(iterator)
            except StopIteration:
                return True, None

        async def event_generator():
            """Generate SSE events from runner stream."""
            # v6.7.2: Emit preflight_warnings as initial event
            if preflight_warnings:
                yield f"data: {json.dumps({'type': 'preflight_warnings', 'warnings': preflight_warnings}, ensure_ascii=False)}\n\n"

            iterator = run_with_graph_stream(
                project_id=project_id,
                chapter_number=chapter,
                settings=settings,
                repo=repo,
                llm_mode=llm_mode,
            )
            while True:
                done, event = await asyncio.to_thread(next_stream_event, iterator)
                if done:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    except Exception as e:
        # For SSE, errors are returned as error events
        async def error_event():
            yield f"data: {json.dumps({'type': 'run_error', 'error': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            error_event(),
            media_type="text/event-stream",
        )
