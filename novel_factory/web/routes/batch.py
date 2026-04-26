"""Batch production routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Form

from ..deps import get_repo, render, safe_error_message, build_dispatcher_for_web

router = APIRouter()


@router.get("")
async def batch_form(request: Request):
    """Show batch production form."""
    try:
        repo = get_repo(request)
        projects = repo.list_projects()
        recent_runs = repo.list_production_runs(limit=10)
        return render(request, "batch.html", {"projects": projects, "recent_runs": recent_runs})
    except Exception as e:
        return render(request, "batch.html", {"error": safe_error_message(e)})


@router.post("/run")
async def batch_run(
    request: Request,
    project_id: str = Form(...),
    from_chapter: int = Form(...),
    to_chapter: int = Form(...),
    llm_mode: str = Form("stub"),
):
    """Execute batch production."""
    try:
        dispatcher = build_dispatcher_for_web(request, llm_mode=llm_mode)
        result = dispatcher.run_batch(
            project_id=project_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
        )
        return render(request, "batch.html", {"result": result, "project_id": project_id})
    except Exception as e:
        return render(request, "batch.html", {"error": safe_error_message(e)})


@router.get("/status")
async def batch_status(request: Request, run_id: str = ""):
    """Show batch run status."""
    try:
        if not run_id:
            return render(request, "batch.html", {"error": "run_id required"})

        repo = get_repo(request)
        run = repo.get_production_run(run_id)
        if not run:
            return render(request, "batch.html", {"error": f"Run '{run_id}' not found"})

        items = repo.list_production_run_items(run_id)
        return render(request, "batch.html", {"run": run, "items": items, "run_id": run_id})
    except Exception as e:
        return render(request, "batch.html", {"error": safe_error_message(e)})


@router.post("/review")
async def batch_review(
    request: Request,
    run_id: str = Form(...),
    decision: str = Form(...),
    notes: str = Form(""),
):
    """Record batch review decision."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.review_batch(run_id=run_id, decision=decision, notes=notes)
        return render(request, "batch.html", {"result": result, "run_id": run_id})
    except Exception as e:
        return render(request, "batch.html", {"error": safe_error_message(e)})
