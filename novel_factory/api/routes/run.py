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


class RunChapterRequest(BaseModel):
    """Run chapter request."""

    project_id: str
    chapter: int
    llm_mode: str | None = None


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
            repo.update_workflow_run(
                run_id,
                status="failed",
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

        guard_error = check_chapter_run_guard(repo, body.project_id, body.chapter)
        if guard_error:
            return error_response(
                guard_error.code,
                guard_error.message,
                details={
                    **guard_error.details,
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

        guard_error = check_chapter_run_guard(repo, body.project_id, body.chapter)
        if guard_error:
            return error_response(
                guard_error.code,
                guard_error.message,
                details={
                    **guard_error.details,
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

        if error:
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
            "project_id": body.project_id,
            "chapter": body.chapter,
            "workflow_status": workflow_status,
            "chapter_status": chapter_status,
            "status": workflow_status,  # backward compatibility
            "requires_human": requires_human,
            "awaiting_publish": awaiting_publish,
            "error": error,
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
    """Return True when a trusted user-visible memory batch exists.

    Node events are not enough: a run can log that memory_curator executed while
    the inbox has no batch, or only has a low-confidence state-card fallback.
    """
    return has_trusted_memory_batch(repo, project_id, chapter_number)


async def _ensure_memory_curated_before_publish(request: Request, repo, project_id: str, chapter_number: int) -> dict:
    """Run MemoryCurator once before manual publish when evidence is missing."""
    if _has_memory_curator_evidence(repo, project_id, chapter_number):
        return {"memory_curator_processed": False, "memory_curator_skipped": True}

    from ..deps import get_llm_provider_for_agent, LLMConfigMissingError, get_llm_mode
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

    agent = MemoryCuratorAgent(repo, llm, skill_registry=SkillRegistry())
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
    """v5.3.0: Manually publish a reviewed chapter.

    This endpoint is for real mode where auto-publish is disabled.
    Only chapters with status='reviewed' can be published. Before publishing,
    it also guarantees MemoryCurator has run at least once for this chapter.
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

        # Verify chapter status is 'reviewed'
        current_status = chapter.get("status")
        if current_status != "reviewed":
            message = f"章节状态为 '{current_status}'，只有 'reviewed' 状态的章节可以发布"
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

        memory_result = await _ensure_memory_curated_before_publish(
            request,
            repo,
            body.project_id,
            body.chapter,
        )
        if memory_result.get("error"):
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

        # Publish the chapter
        ok = repo.publish_chapter(body.project_id, body.chapter, expected_status="reviewed")
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
                },
                flags={"chapter_published": True, "memory_trusted": True},
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
                },
                flags={"chapter_published": True, "memory_trusted": False},
            ).to_dict()

        return envelope_response({
            "project_id": body.project_id,
            "chapter": body.chapter,
            "chapter_status": "published",
            **memory_result,
            "message": f"第 {body.chapter} 章已发布",
            "domain_result": domain_result,
        })

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
