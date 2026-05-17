"""Run chapter API endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class RunChapterRequest(BaseModel):
    """Run chapter request."""

    project_id: str
    chapter: int
    llm_mode: str | None = None


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
            return error_response(guard_error.code, guard_error.message, details=guard_error.details)

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

        return envelope_response({
            "run_id": run_id,
            "project_id": body.project_id,
            "chapter": body.chapter,
            "workflow_status": "running",
            "status": "running",
            "llm_mode": llm_mode,
            "message": "章节生成已在后台启动",
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
            return error_response(guard_error.code, guard_error.message, details=guard_error.details)

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
            return error_response(
                "PROJECT_CONTEXT_INCOMPLETE",
                error or "项目资料不完整，无法生成章节",
                details={
                    "missing": result.get("missing", []),
                    "actions": result.get("actions", []),
                    "chapter_status": chapter_status,
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
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"运行章节失败: {str(e)}")


class PublishChapterRequest(BaseModel):
    """v5.3.0: Manual publish chapter request."""

    project_id: str
    chapter: int


def _has_memory_curator_evidence(repo, project_id: str, chapter_number: int) -> bool:
    """Return True when memory extraction already ran for this chapter.

    A reviewed chapter can legitimately produce zero memory patches, so this
    checks both created memory batches and completed memory_curator node events.
    """
    try:
        for batch in repo.list_memory_batches(project_id):
            if int(batch.get("chapter_number") or 0) == int(chapter_number):
                return True
    except Exception:
        pass

    try:
        events = repo.get_workflow_node_events_for_chapter(project_id, chapter_number)
        return any(
            ev.get("node_name") == "memory_curator"
            and ev.get("event_type") == "completed"
            and ev.get("status") == "completed"
            for ev in events
        )
    except Exception:
        return False


def _ensure_memory_curated_before_publish(request: Request, repo, project_id: str, chapter_number: int) -> dict:
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
    result = agent.run({
        "project_id": project_id,
        "chapter_number": chapter_number,
        "chapter_status": "reviewed",
        "workflow_run_id": run_id,
        "llm_mode": get_llm_mode(request),
    })

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

    repo.create_workflow_node_event(
        run_id=run_id,
        project_id=project_id,
        chapter_number=chapter_number,
        node_name="memory_curator",
        event_type="completed",
        status="completed",
        message="人工发布前记忆提取完成",
        output_summary=f"{result.get('memory_items_count', 0)} 条候选记忆",
    )
    repo.update_workflow_run(run_id, status="completed", current_node="memory_curator", clear_error=True)
    return {
        "memory_curator_processed": True,
        "memory_run_id": run_id,
        "memory_batch_id": result.get("memory_batch_id"),
        "memory_items_count": result.get("memory_items_count", 0),
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
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，只有 'reviewed' 状态的章节可以发布",
                details={"current_status": current_status},
            )

        memory_result = _ensure_memory_curated_before_publish(
            request,
            repo,
            body.project_id,
            body.chapter,
        )
        if memory_result.get("error"):
            return error_response(
                "MEMORY_CURATOR_FAILED",
                f"发布前记忆提取失败: {memory_result['error']}",
                details={
                    "project_id": body.project_id,
                    "chapter": body.chapter,
                    "run_id": memory_result.get("run_id"),
                },
            )

        # Publish the chapter
        ok = repo.publish_chapter(body.project_id, body.chapter, expected_status="reviewed")
        if not ok:
            return error_response("PUBLISH_FAILED", "发布章节失败")

        return envelope_response({
            "project_id": body.project_id,
            "chapter": body.chapter,
            "chapter_status": "published",
            **memory_result,
            "message": f"第 {body.chapter} 章已发布",
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"发布章节失败: {str(e)}")
