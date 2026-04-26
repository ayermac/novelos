"""Dashboard API endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(request: Request) -> EnvelopeResponse:
    """Get dashboard overview data.

    Returns:
        - Project count
        - Recent runs
        - Queue status
        - Review status
    """
    from ..deps import get_repo, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        # Get projects
        projects = repo.list_projects()
        project_count = len(projects)

        # Get recent runs (simplified)
        recent_runs = []
        for p in projects[:5]:
            runs = repo.get_workflow_runs_for_project(p["project_id"], limit=3)
            for run in runs:
                recent_runs.append({
                    "run_id": run.get("id", ""),
                    "project_id": p["project_id"],
                    "project_name": p.get("name", ""),
                    "chapter": run.get("chapter_number"),
                    "status": run.get("status", ""),
                    "created_at": run.get("started_at", ""),
                })

        # Sort by created_at desc
        recent_runs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        recent_runs = recent_runs[:10]

        # Get queue status
        queue_items = repo.list_queue_items(status="pending")
        queue_count = len(queue_items)

        # Get review status (simplified)
        review_count = 0
        for p in projects:
            chapters = repo.list_chapters(p["project_id"])
            review_count += sum(1 for ch in chapters if ch.get("status") == "review")

        return envelope_response({
            "project_count": project_count,
            "recent_runs": recent_runs,
            "queue_count": queue_count,
            "review_count": review_count,
            "llm_mode": llm_mode,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取仪表盘数据失败: {str(e)}")
