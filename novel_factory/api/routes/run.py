"""Run chapter API endpoints."""

from __future__ import annotations

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
    """
    from ..deps import get_repo, get_dispatcher, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = body.llm_mode or get_llm_mode(request)

        # Verify project exists
        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(body.project_id, body.chapter)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {body.chapter} 不存在")

        # Build dispatcher
        dispatcher = get_dispatcher(request, llm_mode=llm_mode)

        # Run chapter (stub mode returns mock result)
        result = dispatcher.run_chapter(
            project_id=body.project_id,
            chapter_number=body.chapter,
        )

        # Determine workflow_status from dispatcher result
        chapter_status = result.get("chapter_status")
        requires_human = result.get("requires_human", False)
        error = result.get("error")

        if error:
            workflow_status = "failed"
            message = "章节生成失败"
        elif requires_human or chapter_status == "blocking":
            workflow_status = "blocked"
            message = "章节生成被阻塞，需要人工处理"
        elif chapter_status == "published":
            workflow_status = "completed"
            message = "章节生成完成"
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
            "error": error,
            "llm_mode": llm_mode,
            "message": message,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"运行章节失败: {str(e)}")
