"""Dashboard route - main landing page."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_repo, render, get_llm_mode, get_db_path

router = APIRouter()


@router.get("/")
async def dashboard(request: Request):
    """Dashboard showing system overview."""
    try:
        repo = get_repo(request)

        # Get counts
        projects = repo.list_projects()
        project_count = len(projects)

        # Count chapters across all projects
        chapter_count = 0
        for p in projects:
            chapters = repo.list_chapters(p["project_id"])
            chapter_count += len(chapters)

        # Recent production runs (last 10)
        recent_runs = repo.list_production_runs(limit=10)

        # Recent queue items (last 10)
        recent_queue = repo.list_queue_items(limit=10)

        # Recent style samples (last 5)
        recent_samples = []
        for p in projects[:5]:
            samples = repo.list_style_samples(p["project_id"])
            recent_samples.extend(samples[:2])

        # Recent style proposals (last 5)
        recent_proposals = []
        for p in projects[:5]:
            proposals = repo.list_style_evolution_proposals(p["project_id"])
            recent_proposals.extend(proposals[:2])

        # LLM validation summary (stub)
        llm_status = "stub mode" if get_llm_mode(request) == "stub" else "real mode"

        return render(
            request,
            "dashboard.html",
            {
                "project_count": project_count,
                "chapter_count": chapter_count,
                "recent_runs": recent_runs[:10],
                "recent_queue": recent_queue[:10],
                "recent_samples": recent_samples[:5],
                "recent_proposals": recent_proposals[:5],
                "llm_status": llm_status,
                "show_onboarding": True,
            },
        )
    except Exception as e:
        from ..deps import safe_error_message

        return render(request, "dashboard.html", {"error": safe_error_message(e)})
