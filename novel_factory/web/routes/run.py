"""Run chapter routes - execute single chapter production."""

from __future__ import annotations

from fastapi import APIRouter, Request, Form

from ..deps import (
    get_repo,
    render,
    safe_error_message,
    build_dispatcher_for_web,
    json_or_form_value,
)

router = APIRouter()


@router.get("")
async def run_form(request: Request):
    """Show run chapter form."""
    try:
        repo = get_repo(request)
        projects = repo.list_projects()
        return render(request, "run_chapter.html", {"projects": projects})
    except Exception as e:
        return render(request, "run_chapter.html", {"error": safe_error_message(e)})


@router.post("/chapter")
async def run_chapter(
    request: Request,
    project_id: str = Form(...),
    chapter: int = Form(...),
    llm_mode: str = Form("stub"),
    max_steps: int = Form(20),
):
    """Execute chapter production."""
    try:
        dispatcher = build_dispatcher_for_web(request, llm_mode=llm_mode)

        result = dispatcher.run_chapter(
            project_id=project_id,
            chapter_number=chapter,
            max_steps=max_steps,
        )

        return render(
            request,
            "run_chapter.html",
            {
                "result": result,
                "project_id": project_id,
                "chapter": chapter,
                "llm_mode": llm_mode,
                "max_steps": max_steps,
            },
        )
    except Exception as e:
        return render(
            request,
            "run_chapter.html",
            {
                "error": safe_error_message(e),
                "project_id": project_id,
                "chapter": chapter,
            },
        )
