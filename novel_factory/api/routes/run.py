"""Run chapter API endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class RunChapterRequest(BaseModel):
    """Run chapter request."""

    project_id: str
    chapter: int
    llm_mode: str | None = None


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
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"运行章节失败: {str(e)}")


class PublishChapterRequest(BaseModel):
    """v5.3.0: Manual publish chapter request."""

    project_id: str
    chapter: int


@router.post("/publish/chapter")
async def publish_chapter(request: Request, body: PublishChapterRequest) -> EnvelopeResponse:
    """v5.3.0: Manually publish a reviewed chapter.

    This endpoint is for real mode where auto-publish is disabled.
    Only chapters with status='reviewed' can be published.
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

        # Publish the chapter
        ok = repo.publish_chapter(body.project_id, body.chapter, expected_status="reviewed")
        if not ok:
            return error_response("PUBLISH_FAILED", "发布章节失败")

        return envelope_response({
            "project_id": body.project_id,
            "chapter": body.chapter,
            "chapter_status": "published",
            "message": f"第 {body.chapter} 章已发布",
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"发布章节失败: {str(e)}")
