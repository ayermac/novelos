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
        recent_runs = repo.list_production_runs(limit=20)
        return render(request, "batch.html", {"projects": projects, "recent_runs": recent_runs})
    except Exception as e:
        repo = get_repo(request)
        projects = repo.list_projects()
        return render(request, "batch.html", {"error": safe_error_message(e), "projects": projects})


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
        repo = get_repo(request)
        dispatcher = build_dispatcher_for_web(request, llm_mode=llm_mode)
        result = dispatcher.run_batch(
            project_id=project_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
        )
        # Refresh recent runs list
        projects = repo.list_projects()
        recent_runs = repo.list_production_runs(limit=20)
        return render(request, "batch.html", {
            "result": result, 
            "project_id": project_id,
            "projects": projects,
            "recent_runs": recent_runs
        })
    except Exception as e:
        repo = get_repo(request)
        projects = repo.list_projects()
        recent_runs = repo.list_production_runs(limit=20)
        return render(request, "batch.html", {
            "error": safe_error_message(e),
            "projects": projects,
            "recent_runs": recent_runs
        })


@router.get("/status")
async def batch_status(request: Request, run_id: str = ""):
    """Show batch run status."""
    try:
        repo = get_repo(request)
        projects = repo.list_projects()
        recent_runs = repo.list_production_runs(limit=20)
        
        if not run_id:
            return render(request, "batch.html", {
                "error": "run_id required",
                "projects": projects,
                "recent_runs": recent_runs
            })

        run = repo.get_production_run(run_id)
        if not run:
            return render(request, "batch.html", {
                "error": f"Run '{run_id}' not found",
                "projects": projects,
                "recent_runs": recent_runs
            })

        items = repo.get_production_run_items(run_id)
        return render(request, "batch.html", {
            "run": run, 
            "items": items, 
            "run_id": run_id,
            "projects": projects,
            "recent_runs": recent_runs
        })
    except Exception as e:
        repo = get_repo(request)
        projects = repo.list_projects()
        recent_runs = repo.list_production_runs(limit=20)
        return render(request, "batch.html", {
            "error": safe_error_message(e),
            "projects": projects,
            "recent_runs": recent_runs
        })


@router.post("/review")
async def batch_review(
    request: Request,
    run_id: str = Form(...),
    decision: str = Form(...),
    notes: str = Form(""),
):
    """Record batch review decision."""
    try:
        repo = get_repo(request)
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.review_batch(run_id=run_id, decision=decision, notes=notes)
        
        # Refresh data
        projects = repo.list_projects()
        recent_runs = repo.list_production_runs(limit=20)
        run = repo.get_production_run(run_id)
        items = repo.get_production_run_items(run_id) if run else []
        
        return render(request, "batch.html", {
            "result": result, 
            "run_id": run_id,
            "run": run,
            "items": items,
            "projects": projects,
            "recent_runs": recent_runs
        })
    except Exception as e:
        repo = get_repo(request)
        projects = repo.list_projects()
        recent_runs = repo.list_production_runs(limit=20)
        return render(request, "batch.html", {
            "error": safe_error_message(e),
            "projects": projects,
            "recent_runs": recent_runs
        })
