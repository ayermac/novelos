"""Review workbench routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Form

from ..deps import get_repo, render, safe_error_message, build_dispatcher_for_web

router = APIRouter()


@router.get("")
async def review_form(request: Request):
    """Show review workbench form."""
    try:
        repo = get_repo(request)
        projects = repo.list_projects()
        return render(request, "review.html", {"projects": projects})
    except Exception as e:
        return render(request, "review.html", {"error": safe_error_message(e)})


@router.get("/pack")
async def review_pack(
    request: Request,
    run_id: str = "",
    serial_plan_id: str = "",
    project_id: str = "",
    from_chapter: int = 0,
    to_chapter: int = 0,
):
    """Build a review pack."""
    try:
        repo = get_repo(request)
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.build_review_pack(
            run_id=run_id or None,
            serial_plan_id=serial_plan_id or None,
            project_id=project_id or None,
            from_chapter=from_chapter or None,
            to_chapter=to_chapter or None,
        )
        # Fetch projects for form dropdown
        projects = repo.list_projects()
        return render(request, "review.html", {"result": result, "projects": projects})
    except Exception as e:
        repo = get_repo(request)
        projects = repo.list_projects()
        return render(request, "review.html", {"error": safe_error_message(e), "projects": projects})


@router.get("/chapter")
async def review_chapter(request: Request, project_id: str, chapter: int):
    """Get review view for a chapter."""
    try:
        repo = get_repo(request)
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.get_review_chapter(project_id=project_id, chapter=chapter)
        projects = repo.list_projects()
        return render(request, "review.html", {"result": result, "projects": projects})
    except Exception as e:
        repo = get_repo(request)
        projects = repo.list_projects()
        return render(request, "review.html", {"error": safe_error_message(e), "projects": projects})


@router.get("/timeline")
async def review_timeline(
    request: Request,
    run_id: str = "",
    project_id: str = "",
    chapter: int = 0,
):
    """Get timeline events."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.get_review_timeline(
            run_id=run_id or None,
            project_id=project_id or None,
            chapter=chapter or None,
        )
        return render(request, "review.html", {"result": result})
    except Exception as e:
        return render(request, "review.html", {"error": safe_error_message(e)})


@router.get("/diff")
async def review_diff(
    request: Request,
    project_id: str,
    chapter: int,
    from_version: str = "",
    to_version: str = "",
):
    """Get diff between chapter versions."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.get_review_diff(
            project_id=project_id,
            chapter=chapter,
            from_version=from_version or None,
            to_version=to_version or None,
        )
        return render(request, "review.html", {"result": result})
    except Exception as e:
        return render(request, "review.html", {"error": safe_error_message(e)})


@router.post("/export")
async def review_export(
    request: Request,
    run_id: str = Form(""),
    project_id: str = Form(""),
    from_chapter: int = Form(0),
    to_chapter: int = Form(0),
    output: str = Form(...),
    force: bool = Form(False),
):
    """Export review pack."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.export_review_pack(
            run_id=run_id or None,
            project_id=project_id or None,
            from_chapter=from_chapter or None,
            to_chapter=to_chapter or None,
            output=output,
            force=force,
        )
        return render(request, "review.html", {"result": result})
    except Exception as e:
        return render(request, "review.html", {"error": safe_error_message(e)})
