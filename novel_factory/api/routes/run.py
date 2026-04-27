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
        result = run_with_graph(
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
