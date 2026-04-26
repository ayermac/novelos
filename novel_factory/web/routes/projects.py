"""Projects routes - list and detail views."""

from __future__ import annotations

from typing import Any

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


def _build_workspace_read_model(repo, project_id: str) -> dict[str, Any]:
    """Build lightweight read model for project workspace.
    
    Gathers data from multiple sources but gracefully handles missing data.
    """
    workspace = {
        "project": None,
        "chapters": [],
        "chapter_stats": {},
        "recent_runs": [],
        "queue_items": [],
        "serial_plans": [],
        "style_bible": None,
        "style_gate": None,
        "style_samples": [],
        "pending_style_proposals": [],
        "next_best_action": None,
    }
    
    # 1. Project basic info
    project = repo.get_project(project_id)
    if not project:
        return workspace
    workspace["project"] = project
    
    # 2. Chapters and stats
    try:
        chapters = repo.list_chapters(project_id)
        workspace["chapters"] = chapters
        
        # Calculate chapter stats by status
        status_counts = {}
        for ch in chapters:
            status = ch.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        workspace["chapter_stats"] = status_counts
    except Exception:
        pass  # Keep empty chapters
    
    # 3. Recent workflow runs
    try:
        runs = repo.get_workflow_runs_for_project(project_id, limit=10)
        workspace["recent_runs"] = runs
    except Exception:
        pass  # Keep empty runs
    
    # 4. Queue items
    try:
        queue_items = repo.list_queue_items(project_id=project_id, limit=10)
        workspace["queue_items"] = queue_items
    except Exception:
        pass  # Keep empty queue
    
    # 5. Serial plans
    try:
        serial_plans = repo.list_serial_plans(project_id=project_id)
        workspace["serial_plans"] = serial_plans
    except Exception:
        pass  # Keep empty serial plans
    
    # 6. Style Bible
    try:
        style_bible = repo.get_style_bible(project_id)
        workspace["style_bible"] = style_bible
    except Exception:
        pass  # Keep None
    
    # 7. Style Gate Config
    try:
        style_gate = repo.get_style_gate_config(project_id)
        workspace["style_gate"] = style_gate
    except Exception:
        pass  # Keep None
    
    # 8. Style Samples
    try:
        style_samples = repo.list_style_samples(project_id)
        workspace["style_samples"] = style_samples
    except Exception:
        pass  # Keep empty samples
    
    # 9. Pending Style Evolution Proposals
    try:
        pending_proposals = repo.list_style_evolution_proposals(project_id, status="pending")
        workspace["pending_style_proposals"] = pending_proposals
    except Exception:
        pass  # Keep empty proposals
    
    # 10. Determine next best action
    workspace["next_best_action"] = _determine_next_best_action(workspace)
    
    return workspace


def _determine_next_best_action(workspace: dict[str, Any]) -> dict[str, Any]:
    """Determine the next best action for the author.
    
    Priority:
    1. Blocking chapters -> Review/Handle blocking
    2. Chapters awaiting review (status='review') -> Review Workbench
    3. Failed queue items -> Queue management
    4. Pending style proposals -> Style page
    5. Planned/scripted/drafted/polished chapters -> Run Chapter
    6. No Style Bible -> Initialize Style Bible
    7. Default -> Batch or Serial production
    """
    chapters = workspace.get("chapters", [])
    queue_items = workspace.get("queue_items", [])
    style_bible = workspace.get("style_bible")
    pending_proposals = workspace.get("pending_style_proposals", [])
    
    # Check for blocking chapters
    blocking_chapters = [ch for ch in chapters if ch.get("status") == "blocking"]
    if blocking_chapters:
        return {
            "action": "review_blocking",
            "label": "处理阻塞章节",
            "description": f"有 {len(blocking_chapters)} 个章节需要人工处理",
            "url": f"/review?project_id={workspace['project']['project_id']}",
            "priority": 1,
        }
    
    # Check for chapters in review state (status='review' means awaiting review)
    review_chapters = [ch for ch in chapters if ch.get("status") == "review"]
    if review_chapters:
        return {
            "action": "review",
            "label": "审核待审章节",
            "description": f"有 {len(review_chapters)} 个章节等待审核",
            "url": f"/review?project_id={workspace['project']['project_id']}",
            "priority": 2,
        }
    
    # Check for failed queue items
    failed_queue = [q for q in queue_items if q.get("status") in ["failed", "timeout"]]
    if failed_queue:
        return {
            "action": "queue",
            "label": "处理队列失败项",
            "description": f"有 {len(failed_queue)} 个队列项失败或超时",
            "url": f"/queue?project_id={workspace['project']['project_id']}",
            "priority": 3,
        }
    
    # Check for pending style proposals
    if pending_proposals:
        return {
            "action": "style",
            "label": "处理风格演进提案",
            "description": f"有 {len(pending_proposals)} 个待处理的风格提案",
            "url": f"/style?project_id={workspace['project']['project_id']}",
            "priority": 4,
        }
    
    # Check for chapters in progress (planned, scripted, drafted, polished)
    in_progress_statuses = ["planned", "scripted", "drafted", "polished"]
    in_progress = [ch for ch in chapters if ch.get("status") in in_progress_statuses]
    if in_progress:
        first_in_progress = in_progress[0]
        return {
            "action": "run_chapter",
            "label": f"运行第 {first_in_progress['chapter_number']} 章",
            "description": f"有 {len(in_progress)} 个章节待生产",
            "url": f"/run?project_id={workspace['project']['project_id']}&chapter={first_in_progress['chapter_number']}",
            "priority": 5,
        }
    
    # Check if Style Bible exists
    if not style_bible:
        return {
            "action": "style",
            "label": "初始化 Style Bible",
            "description": "项目还没有 Style Bible",
            "url": f"/style?project_id={workspace['project']['project_id']}",
            "priority": 6,
        }
    
    # Default: continue production
    serial_plans = workspace.get("serial_plans", [])
    if serial_plans:
        return {
            "action": "serial",
            "label": "继续连载计划",
            "description": "查看连载进度",
            "url": f"/serial/{serial_plans[0]['id']}",
            "priority": 6,
        }
    
    return {
        "action": "batch",
        "label": "批量生产",
        "description": "开始批量生产新章节",
        "url": f"/batch?project_id={workspace['project']['project_id']}",
        "priority": 7,
    }


@router.get("/{project_id}")
async def project_detail(request: Request, project_id: str):
    """Show project workspace / author cockpit."""
    try:
        repo = get_repo(request)
        workspace = _build_workspace_read_model(repo, project_id)
        
        if not workspace["project"]:
            return render(
                request,
                "project_detail.html",
                {
                    "error": f"项目 '{project_id}' 不存在",
                    "project_id": project_id,
                },
                status_code=404,
            )
        
        return render(
            request,
            "project_detail.html",
            {
                "workspace": workspace,
                "project": workspace["project"],
                "project_id": project_id,
            },
        )
    except Exception as e:
        return render(
            request,
            "project_detail.html",
            {
                "error": safe_error_message(e),
                "project_id": project_id,
            },
        )
