"""Run chapter API endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ..contracts import (
    OperationResult,
    success,
    partial_success,
    failed,
    blocked,
    needs_human,
    degraded,
)
from ._memory_curator_gate import (
    has_trusted_memory_batch,
    memory_incomplete_details,
    memory_incomplete_message,
    memory_result_is_incomplete,
)

router = APIRouter()

PUBLISHABLE_CHAPTER_STATUSES = frozenset({"reviewed", "awaiting_publish"})
PUBLISH_COMPATIBLE_BLOCKED_NODES = frozenset({
    "human_review",
    "awaiting_publish",
    "publisher",
    "publish",
})


class RunChapterRequest(BaseModel):
    """Run chapter request."""

    project_id: str
    chapter: int
    llm_mode: str | None = None


def _publish_guard_can_ignore_run(
    latest_run: dict | None,
    chapter_status: str | None,
    *,
    memory_ready: bool = False,
) -> bool:
    """Allow publishing reviewed content when only post-review housekeeping failed."""
    if chapter_status not in PUBLISHABLE_CHAPTER_STATUSES or not latest_run:
        return False
    if latest_run.get("status") not in ("blocked", "failed"):
        return False
    current_node = latest_run.get("current_node") or ""
    if current_node == "memory_curator":
        return memory_ready
    return current_node in PUBLISH_COMPATIBLE_BLOCKED_NODES


def _publish_workflow_recovery_error(repo, body: PublishChapterRequest, current_status: str | None):
    """Return a publish-blocking response when workflow recovery is still needed."""
    latest_runs = repo.get_workflow_runs_for_project(
        body.project_id, chapter_number=body.chapter, limit=1
    )
    latest_run = latest_runs[0] if latest_runs else None
    if not latest_run:
        return None
    run_status = latest_run.get("status")
    memory_ready = _has_memory_curator_evidence(repo, body.project_id, body.chapter)
    ignore_broken_run_for_publish = _publish_guard_can_ignore_run(
        latest_run,
        current_status,
        memory_ready=memory_ready,
    )
    run_is_broken = run_status in ("blocked", "failed") and not ignore_broken_run_for_publish
    run_is_stale = False
    if run_status == "running":
        from ...workflow.state_integrity import _run_is_recent
        if not _run_is_recent(latest_run.get("started_at")):
            run_is_stale = True
    if not run_is_broken and not run_is_stale:
        return None
    reason = (
        "工作流被阻塞" if run_status == "blocked"
        else "工作流运行失败" if run_status == "failed"
        else "工作流运行超时"
    )
    message = f"{reason}，需先恢复工作流再发布"
    return error_response(
        "WORKFLOW_RECOVERY_REQUIRED",
        message,
        details={
            "run_status": run_status,
            "run_id": latest_run.get("id"),
            "domain_result": blocked(
                message,
                user_message=f"{reason}，请先处理工作流恢复",
                next_action="view_workflow",
                action_label="查看工作流恢复",
                details={
                    "project_id": body.project_id,
                    "chapter": body.chapter,
                    "run_status": run_status,
                    "run_id": latest_run.get("id"),
                },
                flags={"publish_blocked": True, "workflow_needs_recovery": True},
            ).to_dict(),
        },
    )


def _run_guard_domain_result(guard_error) -> dict:
    """Build domain_result for run guard blocks."""
    details = dict(getattr(guard_error, "details", {}) or {})
    hint = details.get("hint")
    action_labels = {
        "generate_genesis": "生成项目设定",
        "generate_missing_context": "补齐项目资料",
        "reset_chapter": "重置章节",
        "review_existing_content": "查看现有正文",
        "view_workflow": "查看工作流",
    }
    next_action = hint or ("view_workflow" if guard_error.code == "WORKFLOW_ALREADY_RUNNING" else "resolve_blocker")
    return blocked(
        getattr(guard_error, "message", "章节生成被阻止"),
        user_message=getattr(guard_error, "message", "章节生成被阻止"),
        next_action=next_action,
        action_label=action_labels.get(next_action, "处理后重试"),
        details={
            **details,
            "error_code": getattr(guard_error, "code", "RUN_GUARD_BLOCKED"),
        },
        flags={"run_guard_blocked": True},
    ).to_dict()


def _run_chapter_background(
    project_id: str,
    chapter: int,
    db_path: str,
    settings,
    llm_mode: str,
    run_id: str,
) -> None:
    """Run chapter production outside the browser/SSE connection lifecycle."""
    from ...db.repository import Repository
    from ...workflow.runner import run_with_graph

    repo = Repository(db_path)
    try:
        result = run_with_graph(
            project_id=project_id,
            chapter_number=chapter,
            settings=settings,
            repo=repo,
            llm_mode=llm_mode,
            workflow_run_id=run_id,
        )
        if result.get("error"):
            # Some setup failures return before a workflow node can finalize.
            status = "blocked" if result.get("workflow_interrupted") else "failed"
            repo.update_workflow_run(
                run_id,
                status=status,
                error_message=result.get("error"),
            )
    except Exception as exc:
        repo.update_workflow_run(run_id, status="failed", error_message=str(exc))


@router.post("/run/chapter/start")
async def start_chapter_run(
    request: Request,
    background_tasks: BackgroundTasks,
    body: RunChapterRequest,
) -> EnvelopeResponse:
    """Start chapter production as a server-side background job.

    The returned run_id can be observed through the workflow timeline/stream
    endpoints. Unlike /run/chapter/stream, disconnecting the browser no longer
    cancels the production workflow.
    """
    from ..deps import get_repo, get_settings, get_llm_mode

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        llm_mode = body.llm_mode or get_llm_mode(request)

        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        chapter = repo.get_chapter(body.project_id, body.chapter)
        if not chapter:
            repo.add_chapter(
                project_id=body.project_id,
                chapter_number=body.chapter,
                title=f"第 {body.chapter} 章",
                status="planned",
            )
            chapter = repo.get_chapter(body.project_id, body.chapter)

        if chapter and chapter.get("status") == "pending":
            repo.update_chapter_status(body.project_id, body.chapter, "planned")

        from ._run_guards import check_chapter_run_guard

        guard_error, preflight_warnings = check_chapter_run_guard(repo, body.project_id, body.chapter)
        if guard_error:
            return error_response(
                guard_error.code,
                guard_error.message,
                details={
                    **guard_error.details,
                    "preflight_warnings": preflight_warnings,
                    "domain_result": _run_guard_domain_result(guard_error),
                },
            )

        run_id = repo.create_workflow_run(body.project_id, body.chapter)
        background_tasks.add_task(
            _run_chapter_background,
            body.project_id,
            body.chapter,
            repo.db_path,
            settings,
            llm_mode,
            run_id,
        )

        # v6.6.12: Build domain_result for chapter run start
        domain_result = OperationResult(
            ok=True,
            domain_status="pending",
            message="章节生成已在后台启动",
            user_message="章节生成已在后台启动，可通过工作流时间线查看进度",
            severity="info",
            flags={"workflow_running": True},
            details={
                "run_id": run_id,
                "chapter": body.chapter,
            },
        ).to_dict()

        return envelope_response({
            "run_id": run_id,
            "preflight_warnings": preflight_warnings,  # v6.7.2: Expose warnings on success
            "project_id": body.project_id,
            "chapter": body.chapter,
            "workflow_status": "running",
            "status": "running",
            "llm_mode": llm_mode,
            "message": "章节生成已在后台启动",
            "domain_result": domain_result,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"启动章节生成失败: {str(e)}")


@router.post("/run/chapter")
async def run_chapter(request: Request, body: RunChapterRequest) -> EnvelopeResponse:
    """Run a single chapter production.

    In stub mode, returns mock result without real LLM calls.
    v5.1.6: Uses LangGraph-based run_with_graph() instead of Dispatcher.
    """
    from ..deps import get_repo, get_settings, get_llm_mode
    from ...workflow.runner import run_with_graph

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        llm_mode = body.llm_mode or get_llm_mode(request)

        # Verify project exists
        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        # Verify chapter exists — auto-create if missing (sequential creation)
        chapter = repo.get_chapter(body.project_id, body.chapter)
        if not chapter:
            repo.add_chapter(
                project_id=body.project_id,
                chapter_number=body.chapter,
                title=f"第 {body.chapter} 章",
                status="planned",
            )
            chapter = repo.get_chapter(body.project_id, body.chapter)

        # Normalize legacy 'pending' status to 'planned' for compatibility
        # Old Web API created chapters with status='pending', but agents expect 'planned'
        if chapter.get("status") == "pending":
            repo.update_chapter_status(body.project_id, body.chapter, "planned")

        # v5.5.15: Unified run guard — check both running workflow and
        # terminal chapter status via the shared helper.
        from ._run_guards import check_chapter_run_guard

        guard_error, preflight_warnings = check_chapter_run_guard(repo, body.project_id, body.chapter)
        if guard_error:
            return error_response(
                guard_error.code,
                guard_error.message,
                details={
                    **guard_error.details,
                    "preflight_warnings": preflight_warnings,
                    "domain_result": _run_guard_domain_result(guard_error),
                },
            )

        # Run chapter via LangGraph workflow
        result = await asyncio.to_thread(
            run_with_graph,
            project_id=body.project_id,
            chapter_number=body.chapter,
            settings=settings,
            repo=repo,
            llm_mode=llm_mode,
        )

        # Determine workflow_status from dispatcher result
        chapter_status = result.get("chapter_status")
        requires_human = result.get("requires_human", False)
        error = result.get("error")
        awaiting_publish = result.get("awaiting_publish", False)

        # v5.3.0: Handle Context Readiness Gate failure
        if result.get("context_incomplete"):
            domain_result = blocked(
                error or "项目资料不完整，无法生成章节",
                user_message=error or "项目资料不完整，无法生成章节",
                next_action="generate_missing_context",
                action_label="补齐项目资料",
                details={
                    "missing": result.get("missing", []),
                    "chapter_status": chapter_status,
                },
                flags={"context_incomplete": True},
            ).to_dict()
            return error_response(
                "PROJECT_CONTEXT_INCOMPLETE",
                error or "项目资料不完整，无法生成章节",
                details={
                    "missing": result.get("missing", []),
                    "actions": result.get("actions", []),
                    "chapter_status": chapter_status,
                    "domain_result": domain_result,
                },
            )

        if error and result.get("workflow_interrupted"):
            workflow_status = "blocked"
            message = "章节生成提前结束，需要继续生成或人工检查"
        elif error:
            workflow_status = "failed"
            message = "章节生成失败"
        elif requires_human or chapter_status == "blocking":
            workflow_status = "blocked"
            message = "章节生成被阻塞，需要人工处理"
        elif chapter_status == "published":
            workflow_status = "completed"
            message = "章节生成完成"
        elif awaiting_publish or (chapter_status == "reviewed" and llm_mode == "real"):
            # v5.3.0: Real mode editor pass — await manual publish
            workflow_status = "completed"
            awaiting_publish = True
            requires_human = True
            message = "AI 审核通过，等待人工确认发布"
        else:
            workflow_status = "completed"
            message = "章节生成完成" if llm_mode == "stub" else "章节已提交生成"

        # v6.6.12: Build domain_result based on workflow outcome
        domain_result = _build_run_chapter_domain_result(
            workflow_status=workflow_status,
            chapter_status=chapter_status,
            error=error,
            requires_human=requires_human,
            awaiting_publish=awaiting_publish,
            has_trusted_memory=has_trusted_memory_batch(repo, body.project_id, body.chapter),
            llm_mode=llm_mode,
            run_id=result.get("run_id", ""),
        )

        return envelope_response({
            "run_id": result.get("run_id", ""),
            "preflight_warnings": preflight_warnings,  # v6.7.2: Expose warnings on success
            "project_id": body.project_id,
            "chapter": body.chapter,
            "workflow_status": workflow_status,
            "chapter_status": chapter_status,
            "status": workflow_status,  # backward compatibility
            "requires_human": requires_human,
            "awaiting_publish": awaiting_publish,
            "error": error,
            "workflow_interrupted": bool(result.get("workflow_interrupted")),
            "llm_mode": llm_mode,
            "message": message,
            "prompt_tokens": result.get("prompt_tokens", 0),
            "completion_tokens": result.get("completion_tokens", 0),
            "total_tokens": result.get("total_tokens", 0),
            "duration_ms": result.get("duration_ms", 0),
            "domain_result": domain_result,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"运行章节失败: {str(e)}")


class PublishChapterRequest(BaseModel):
    """v5.3.0: Manual publish chapter request."""

    project_id: str
    chapter: int


def _has_memory_curator_evidence(repo, project_id: str, chapter_number: int) -> bool:
    """Return True when a user-visible memory batch already exists.

    Manual publish only needs to avoid re-running MemoryCurator once the chapter
    already has a durable batch. Trust is reported separately in the publish
    domain_result; the manual backfill endpoint keeps the stricter trusted-only
    skip rule.
    """
    try:
        for batch in repo.list_memory_batches(project_id):
            if int(batch.get("chapter_number") or 0) != int(chapter_number):
                continue
            if str(batch.get("status") or "") == "ignored":
                continue
            try:
                if repo.list_memory_items(batch["id"]):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _memory_curator_running_domain_result(project_id: str, chapter_number: int, lock: dict | None) -> dict:
    """Build a blocked domain result for an active MemoryCurator lock."""
    active_run_id = (lock or {}).get("run_id")
    message = f"第 {chapter_number} 章记忆提取正在进行中，请等待完成后再发布。"
    technical_message = f"第 {chapter_number} 章记忆正在提取，不能重复启动。"
    if active_run_id:
        technical_message = f"{technical_message} 当前运行: {active_run_id}"
    return blocked(
        message,
        user_message="记忆提取正在进行中，请等待完成后再发布。",
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


async def _ensure_memory_curated_before_publish(request: Request, repo, project_id: str, chapter_number: int) -> dict:
    """Run MemoryCurator once before manual publish when evidence is missing."""
    lock = None
    if hasattr(repo, "get_memory_curator_lock"):
        try:
            lock = repo.get_memory_curator_lock(project_id, chapter_number)
        except Exception:
            lock = None
    if lock and str(lock.get("status") or "") == "running":
        active_run_id = lock.get("run_id")
        message = f"第 {chapter_number} 章记忆提取正在进行中，请等待完成后再发布。"
        technical_message = f"第 {chapter_number} 章记忆正在提取，不能重复启动。"
        if active_run_id:
            technical_message = f"{technical_message} 当前运行: {active_run_id}"
        return {
            "error": message,
            "memory_curator_locked": True,
            "memory_curator_processed": False,
            "memory_curator_warning": message,
            "memory_curator_technical_warning": technical_message,
            "memory_run_id": active_run_id,
            "active_run_id": active_run_id,
            "domain_result": _memory_curator_running_domain_result(project_id, chapter_number, lock),
        }

    if _has_memory_curator_evidence(repo, project_id, chapter_number):
        return {"memory_curator_processed": False, "memory_curator_skipped": True}

    from ..deps import (
        get_llm_fallback_provider_for_agent,
        get_llm_provider_for_agent,
        LLMConfigMissingError,
        get_llm_mode,
    )
    from ...agents.memory_curator import MemoryCuratorAgent
    from ...skills.registry import SkillRegistry

    run_id = repo.create_workflow_run(
        project_id,
        chapter_number,
        graph_name="manual_publish_memory",
    )
    repo.update_workflow_run(run_id, status="running", current_node="memory_curator")
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id=project_id,
        chapter_number=chapter_number,
        node_name="memory_curator",
        event_type="started",
        status="running",
        message="人工发布前补充记忆提取",
    )

    try:
        llm = get_llm_provider_for_agent(request, "memory_curator")
        fallback_llm = get_llm_fallback_provider_for_agent(request, "memory_curator")
    except LLMConfigMissingError as exc:
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=chapter_number,
            node_name="memory_curator",
            event_type="failed",
            status="failed",
            error_message=str(exc),
        )
        repo.update_workflow_run(run_id, status="failed", current_node="memory_curator", error_message=str(exc))
        return {"error": str(exc), "run_id": run_id}

    agent = MemoryCuratorAgent(repo, llm, skill_registry=SkillRegistry(), fallback_llm=fallback_llm)
    result = await asyncio.to_thread(
        agent.run,
        {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "chapter_status": "reviewed",
            "workflow_run_id": run_id,
            "llm_mode": get_llm_mode(request),
        },
    )

    if result.get("error"):
        error = str(result.get("error"))
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=chapter_number,
            node_name="memory_curator",
            event_type="failed",
            status="failed",
            error_message=error,
        )
        repo.update_workflow_run(run_id, status="failed", current_node="memory_curator", error_message=error)
        return {"error": error, "run_id": run_id}

    extraction_success = result.get("extraction_success", True)
    incomplete = memory_result_is_incomplete(repo, project_id, chapter_number, result)
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id=project_id,
        chapter_number=chapter_number,
        node_name="memory_curator",
        event_type="completed",
        status="warning" if incomplete else "completed",
        message="人工发布前记忆提取完成" if not incomplete else "人工发布前记忆提取未成功，未生成可信记忆批次",
        output_summary=f"{result.get('memory_items_count', 0)} 条候选记忆",
    )
    if incomplete:
        message = memory_incomplete_message(result)
        repo.update_workflow_run(run_id, status="failed", current_node="memory_curator", error_message=message)
        return {
            "error": message,
            "memory_incomplete": True,
            "memory_curator_processed": True,
            "memory_run_id": run_id,
            "memory_batch_id": result.get("memory_batch_id"),
            "memory_items_count": result.get("memory_items_count", 0),
            "extraction_success": extraction_success,
            "fallback_created": result.get("fallback_created", False),
            "memory_curator_degraded": result.get("memory_curator_degraded", False),
            "memory_curator_fallback": result.get("memory_curator_fallback"),
            "memory_curator_warning": result.get("memory_curator_warning"),
        }
    repo.update_workflow_run(run_id, status="completed", current_node="memory_curator", clear_error=True)
    return {
        "memory_curator_processed": True,
        "memory_run_id": run_id,
        "memory_batch_id": result.get("memory_batch_id"),
        "memory_items_count": result.get("memory_items_count", 0),
        "extraction_success": extraction_success,
        "fallback_created": result.get("fallback_created", False),
        "memory_curator_degraded": result.get("memory_curator_degraded", False),
        "memory_curator_fallback": result.get("memory_curator_fallback"),
    }


@router.post("/publish/chapter")
async def publish_chapter(request: Request, body: PublishChapterRequest) -> EnvelopeResponse:
    """v5.3.0: Manually publish a reviewed or awaiting_publish chapter.

    This endpoint is for real mode where auto-publish is disabled.
    Only chapters with status='reviewed' or 'awaiting_publish' can be published.
    Before publishing, it also guarantees MemoryCurator has run at least once
    for this chapter.

    v6.7.9: Added narrative continuity gate — blocking continuity issues
    prevent publication even when status is 'reviewed'.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(body.project_id, body.chapter)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 '{body.chapter}' 不存在")

        # Verify chapter status is publishable.
        current_status = chapter.get("status")
        if current_status not in PUBLISHABLE_CHAPTER_STATUSES:
            message = f"章节状态为 '{current_status}'，只有 'reviewed' 或 'awaiting_publish' 状态的章节可以发布"
            return error_response(
                "INVALID_STATUS",
                message,
                details={
                    "current_status": current_status,
                    "domain_result": blocked(
                        message,
                        user_message="当前章节状态不允许发布",
                        next_action="run_chapter",
                        action_label="继续生成章节",
                        details={
                            "project_id": body.project_id,
                            "chapter": body.chapter,
                            "current_status": current_status,
                            "error_code": "INVALID_STATUS",
                        },
                        flags={"publish_blocked": True},
                    ).to_dict(),
                },
            )

        workflow_error = _publish_workflow_recovery_error(repo, body, current_status)
        if workflow_error is not None:
            return workflow_error

        # v6.7.9: Narrative continuity gate — hard block before publish
        from ...quality.continuity_gate import evaluate_publish_continuity, SEVERITY_BLOCKING

        continuity_result = evaluate_publish_continuity(
            repo, body.project_id, body.chapter,
        )
        if continuity_result.should_block_publish or continuity_result.severity == SEVERITY_BLOCKING:
            message = "连续性检查未通过，发布被拒绝"
            return error_response(
                "CONTINUITY_GATE_BLOCKED",
                message,
                details={
                    "issues": continuity_result.issues,
                    "suggestions": continuity_result.suggestions,
                    "domain_result": blocked(
                        message,
                        user_message="本章存在叙事连续性问题，请修复后再发布",
                        next_action="run_chapter",
                        action_label="重新生成/修复章节",
                        details={
                            "project_id": body.project_id,
                            "chapter": body.chapter,
                            "continuity_issues": continuity_result.issues,
                            "continuity_suggestions": continuity_result.suggestions,
                            "error_code": "CONTINUITY_GATE_BLOCKED",
                        },
                        flags={"publish_blocked": True, "continuity_blocking": True},
                    ).to_dict(),
                },
            )

        # v6.10.3: Publish-time title hard guard with deterministic metadata repair.
        from ...quality.title_guard import repair_publish_title, validate_publish_title

        title_guard = validate_publish_title(chapter.get("title"), chapter.get("content"))
        title_repair_details = None
        title_guard_warning = None
        if not title_guard.passed:
            title_repair = repair_publish_title(chapter.get("title"), chapter.get("content"), body.chapter)
            title_repair_details = title_repair.to_dict()
            if title_repair.repaired and title_repair.title is not None:
                repo.save_chapter_content(
                    body.project_id,
                    body.chapter,
                    title_repair.content if title_repair.content is not None else chapter.get("content", ""),
                    title=title_repair.title,
                )
                chapter = repo.get_chapter(body.project_id, body.chapter) or chapter
                title_guard = title_repair.guard or validate_publish_title(chapter.get("title"), chapter.get("content"))
            if not title_guard.passed:
                title_guard_warning = {
                    "issues": title_guard.issues,
                    "suggestions": title_guard.suggestions,
                    "evidence": title_guard.evidence,
                    "repair": title_repair_details,
                }

        memory_result = await _ensure_memory_curated_before_publish(
            request,
            repo,
            body.project_id,
            body.chapter,
        )
        if memory_result.get("memory_curator_locked"):
            message = memory_result.get("memory_curator_warning") or memory_result.get("error") or "记忆正在提取，不能重复启动。"
            details = {
                "project_id": body.project_id,
                "chapter_number": body.chapter,
                "active_run_id": memory_result.get("active_run_id") or memory_result.get("memory_run_id"),
                "technical_message": memory_result.get("memory_curator_technical_warning"),
                "domain_result": memory_result.get("domain_result"),
            }
            return error_response("MEMORY_CURATOR_RUNNING", message, details=details)

        memory_incomplete = bool(memory_result.get("memory_incomplete"))
        if memory_result.get("error") and not memory_incomplete:
            code = "MEMORY_CURATOR_INCOMPLETE" if memory_result.get("memory_incomplete") else "MEMORY_CURATOR_FAILED"
            details = memory_incomplete_details(
                memory_result,
                project_id=body.project_id,
                chapter_number=body.chapter,
                run_id=memory_result.get("memory_run_id") or memory_result.get("run_id"),
            )
            details["domain_result"] = blocked(
                f"发布前记忆提取失败: {memory_result['error']}",
                user_message="发布被阻塞：记忆提取未成功，请先补跑记忆",
                next_action="backfill_memory",
                action_label="补跑记忆",
                details=details,
                flags={"publish_blocked": True, "memory_trusted": False},
            ).to_dict()
            return error_response(
                code,
                f"发布前记忆提取失败: {memory_result['error']}",
                details=details,
        )

        from .memory_updates import apply_pending_memory_batches_for_chapter

        memory_apply_result = apply_pending_memory_batches_for_chapter(
            repo,
            body.project_id,
            body.chapter,
        )
        if not memory_apply_result.get("ok", False):
            message = memory_apply_result.get("error") or "发布前记忆应用失败"
            details = {
                "project_id": body.project_id,
                "chapter_number": body.chapter,
                "memory_apply": memory_apply_result,
                "domain_result": blocked(
                    message,
                    user_message="发布被阻塞：记忆应用失败，请先处理记忆收件箱中的失败项",
                    next_action="open_memory_inbox",
                    action_label="查看记忆收件箱",
                    details={
                        "project_id": body.project_id,
                        "chapter_number": body.chapter,
                        "failed_batches": memory_apply_result.get("failed_batches", []),
                        "error_code": "MEMORY_APPLY_FAILED",
                    },
                    flags={"publish_blocked": True, "memory_apply_failed": True},
                ).to_dict(),
            }
            return error_response("MEMORY_APPLY_FAILED", message, details=details)

        # Publish the chapter
        ok = repo.publish_chapter(body.project_id, body.chapter, expected_status=current_status)
        if not ok:
            message = "发布章节失败"
            return error_response(
                "PUBLISH_FAILED",
                message,
                details={
                    "domain_result": failed(
                        message,
                        user_message="发布章节失败，请重试或查看章节状态",
                        retryable=True,
                        next_action="publish_chapter",
                        action_label="重试发布",
                        details={
                            "project_id": body.project_id,
                            "chapter": body.chapter,
                            "error_code": "PUBLISH_FAILED",
                        },
                        flags={"publish_failed": True},
                    ).to_dict()
                },
            )

        # v6.6.12: Build domain_result for publish
        has_trusted_mem = has_trusted_memory_batch(repo, body.project_id, body.chapter)
        if has_trusted_mem:
            domain_result = success(
                f"第 {body.chapter} 章已发布",
                user_message="章节已成功发布，可信记忆已入库",
                details={
                    "chapter_status": "published",
                    "memory_curator_processed": memory_result.get("memory_curator_processed", False),
                    "memory_apply": memory_apply_result,
                    "title_guard_warning": title_guard_warning,
                },
                flags={
                    "chapter_published": True,
                    "memory_trusted": True,
                    "title_warning": bool(title_guard_warning),
                },
            ).to_dict()
        else:
            domain_result = partial_success(
                f"第 {body.chapter} 章已发布，但记忆提取未成功",
                user_message="章节已发布，但记忆提取为降级/兜底状态，建议补跑记忆",
                next_action="backfill_memory",
                action_label="补跑记忆",
                details={
                    "chapter_status": "published",
                    "memory_curator_processed": memory_result.get("memory_curator_processed", False),
                    "memory_incomplete": memory_result.get("memory_incomplete", False),
                    "memory_apply": memory_apply_result,
                    "title_guard_warning": title_guard_warning,
                },
                flags={
                    "chapter_published": True,
                    "memory_trusted": False,
                    "title_warning": bool(title_guard_warning),
                },
            ).to_dict()

        response_data = {
            "project_id": body.project_id,
            "chapter": body.chapter,
            "chapter_status": "published",
            **memory_result,
            "memory_apply": memory_apply_result,
            "message": f"第 {body.chapter} 章已发布",
            "domain_result": domain_result,
        }
        if title_repair_details:
            response_data["title_repair"] = title_repair_details
        if title_guard_warning:
            response_data["title_guard_warning"] = title_guard_warning
        return envelope_response(response_data)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"发布章节失败: {str(e)}")


# ---------------------------------------------------------------------------
# v6.6.12: Domain result helpers
# ---------------------------------------------------------------------------


def _build_run_chapter_domain_result(
    workflow_status: str,
    chapter_status: str | None,
    error: str | None,
    requires_human: bool,
    awaiting_publish: bool,
    has_trusted_memory: bool,
    llm_mode: str,
    run_id: str,
) -> dict:
    """Build domain_result for run_chapter endpoint.

    Maps workflow outcomes to domain-level semantics:
    - failed -> failed
    - blocked + revision -> needs_human
    - blocked -> blocked
    - completed + awaiting_publish + memory issue -> partial_success
    - completed -> success
    """
    if workflow_status == "failed":
        return failed(
            error or "章节生成失败",
            user_message="章节生成失败，可重试或查看详情",
            retryable=True,
            next_action="retry_workflow",
            action_label="重试工作流",
            details={
                "workflow_status": workflow_status,
                "chapter_status": chapter_status,
                "run_id": run_id,
            },
            flags={"workflow_failed": True},
        ).to_dict()

    if workflow_status == "blocked":
        if chapter_status == "revision":
            return needs_human(
                "章节需要返修",
                user_message="审核未通过，需要返修处理",
                next_action="retry_node",
                action_label="重试失败节点",
                details={
                    "workflow_status": workflow_status,
                    "chapter_status": chapter_status,
                    "run_id": run_id,
                },
                flags={"workflow_blocked": True, "revision_needed": True},
            ).to_dict()
        return blocked(
            "章节生成被阻塞",
            user_message="章节生成被阻塞，需要人工处理",
            next_action="reset_chapter",
            action_label="重置章节",
            details={
                "workflow_status": workflow_status,
                "chapter_status": chapter_status,
                "run_id": run_id,
            },
            flags={"workflow_blocked": True},
        ).to_dict()

    if workflow_status == "completed":
        # Check for partial success: awaiting_publish but memory issue
        if awaiting_publish or chapter_status == "reviewed":
            if not has_trusted_memory:
                return partial_success(
                    "章节已到待发布状态，但记忆提取未成功",
                    user_message="章节正文已通过审核，但记忆提取为降级/兜底状态，建议补跑记忆",
                    next_action="backfill_memory",
                    action_label="补跑记忆",
                    details={
                        "workflow_status": workflow_status,
                        "chapter_status": chapter_status,
                        "run_id": run_id,
                    },
                    flags={
                        "workflow_completed": True,
                        "awaiting_publish": True,
                        "memory_degraded": True,
                    },
                ).to_dict()
            return success(
                "AI 审核通过，等待人工确认发布",
                user_message="章节已通过审核，可确认发布",
                details={
                    "workflow_status": workflow_status,
                    "chapter_status": chapter_status,
                    "run_id": run_id,
                },
                flags={
                    "workflow_completed": True,
                    "awaiting_publish": True,
                    "memory_trusted": True,
                },
            ).to_dict()

        if chapter_status == "published":
            if not has_trusted_memory:
                return partial_success(
                    "章节已发布，但记忆提取未成功",
                    user_message="章节已发布，但记忆提取为降级/兜底状态，建议补跑记忆",
                    next_action="backfill_memory",
                    action_label="补跑记忆",
                    details={
                        "workflow_status": workflow_status,
                        "chapter_status": chapter_status,
                        "run_id": run_id,
                    },
                    flags={
                        "workflow_completed": True,
                        "chapter_published": True,
                        "memory_degraded": True,
                    },
                ).to_dict()
            return success(
                "章节生成完成",
                user_message="章节已成功生成并发布",
                details={
                    "workflow_status": workflow_status,
                    "chapter_status": chapter_status,
                    "run_id": run_id,
                },
                flags={
                    "workflow_completed": True,
                    "chapter_published": True,
                    "memory_trusted": True,
                },
            ).to_dict()

        # Generic completed case
        return success(
            "章节生成完成" if llm_mode == "stub" else "章节已提交生成",
            user_message="章节生成完成" if llm_mode == "stub" else "章节已提交生成",
            details={
                "workflow_status": workflow_status,
                "chapter_status": chapter_status,
                "run_id": run_id,
            },
            flags={"workflow_completed": True},
        ).to_dict()

    # Fallback: pending/unknown
    return OperationResult(
        ok=True,
        domain_status="pending",
        message=f"工作流状态: {workflow_status}",
        details={"workflow_status": workflow_status, "chapter_status": chapter_status, "run_id": run_id},
    ).to_dict()
