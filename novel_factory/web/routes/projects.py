"""Projects routes - list and detail views."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_repo, render, safe_error_message

router = APIRouter()


@router.get("")
async def list_projects(request: Request):
    """List all projects."""
    try:
        repo = get_repo(request)
        projects = repo.list_projects()
        return render(request, "projects.html", {"projects": projects, "show_onboarding": True})
    except Exception as e:
        return render(request, "projects.html", {"error": safe_error_message(e)})


@router.get("/{project_id}")
async def project_detail(request: Request, project_id: str):
    """Show project details and chapters."""
    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return render(
                request,
                "project_detail.html",
                {
                    "error": f"Project '{project_id}' not found",
                    "project": {"project_id": project_id, "name": "Not Found"},
                },
                status_code=404,
            )

        chapters = repo.list_chapters(project_id)

        # Get latest workflow run for each chapter
        chapter_runs = {}
        for ch in chapters:
            runs = repo.list_workflow_runs(project_id, ch["chapter_number"], limit=1)
            if runs:
                chapter_runs[ch["chapter_number"]] = runs[0]

        return render(
            request,
            "project_detail.html",
            {
                "project": project,
                "chapters": chapters,
                "chapter_runs": chapter_runs,
            },
        )
    except Exception as e:
        return render(
            request,
            "project_detail.html",
            {
                "error": safe_error_message(e),
                "project": {"project_id": project_id, "name": "Error"},
            },
        )
