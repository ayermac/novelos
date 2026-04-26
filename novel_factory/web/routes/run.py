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
async def run_form(
    request: Request,
    project_id: str | None = None,
    chapter: int | None = None,
    llm_mode: str | None = None,
):
    """Show run chapter form with optional query param pre-fill."""
    try:
        repo = get_repo(request)
        projects = repo.list_projects()
        
        # Validate project exists if project_id is provided
        project = None
        if project_id:
            project = repo.get_project(project_id)
            if not project:
                return render(
                    request,
                    "run_chapter.html",
                    {
                        "error": f"项目 '{project_id}' 不存在",
                        "projects": projects,
                        "project_id": project_id,
                        "chapter": chapter,
                    },
                    status_code=404,
                )
        
        # Validate chapter exists if both project_id and chapter are provided
        if project_id and chapter:
            chapter_record = repo.get_chapter(project_id, chapter)
            if not chapter_record:
                return render(
                    request,
                    "run_chapter.html",
                    {
                        "error": f"项目 '{project_id}' 的第 {chapter} 章不存在",
                        "projects": projects,
                        "project_id": project_id,
                        "project": project,
                    },
                    status_code=404,
                )
        
        return render(
            request,
            "run_chapter.html",
            {
                "projects": projects,
                "project_id": project_id,
                "chapter": chapter,
                "llm_mode": llm_mode or "stub",
                "project": project,
            },
        )
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
        repo = get_repo(request)
        dispatcher = build_dispatcher_for_web(request, llm_mode=llm_mode)

        result = dispatcher.run_chapter(
            project_id=project_id,
            chapter_number=chapter,
            max_steps=max_steps,
        )

        # Get the latest workflow run for this chapter
        workflow_runs = repo.get_workflow_runs_for_project(project_id, chapter, limit=1)
        workflow_run = workflow_runs[0] if workflow_runs else None
        
        # Get projects list for form dropdown
        projects = repo.list_projects()

        return render(
            request,
            "run_chapter.html",
            {
                "result": result,
                "project_id": project_id,
                "chapter": chapter,
                "llm_mode": llm_mode,
                "max_steps": max_steps,
                "workflow_run": workflow_run,
                "projects": projects,
            },
        )
    except Exception as e:
        # Get projects list for form dropdown even on error
        repo = get_repo(request)
        projects = repo.list_projects()
        
        return render(
            request,
            "run_chapter.html",
            {
                "error": safe_error_message(e),
                "project_id": project_id,
                "chapter": chapter,
                "projects": projects,
            },
        )
