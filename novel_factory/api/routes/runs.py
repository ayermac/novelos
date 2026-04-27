"""Run detail API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


# Agent step configuration
AGENT_STEPS = [
    {"key": "screenwriter", "label": "编剧", "description": "规划章节场景和情节"},
    {"key": "author", "label": "执笔", "description": "撰写章节正文"},
    {"key": "polisher", "label": "润色", "description": "优化文字表达"},
    {"key": "editor", "label": "审核", "description": "检查内容质量"},
    {"key": "publish", "label": "发布", "description": "发布章节内容"},
]

# Status to agent mapping (reverse of STATUS_ROUTE)
STATUS_TO_AGENT = {
    "planned": None,  # Initial state
    "scripted": "screenwriter",
    "drafted": "author",
    "polished": "polisher",
    "reviewed": "editor",
    "published": "publish",
}


@router.get("/runs/{run_id}")
async def get_run_detail(request: Request, run_id: str) -> EnvelopeResponse:
    """Get detailed information about a workflow run.

    Returns run metadata and step timeline.
    """
    from ..deps import get_repo, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        # Get workflow run
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?",
                (run_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        run_data = dict(row)

        # Get project info
        project = repo.get_project(run_data["project_id"])
        project_name = project.get("name", "") if project else ""

        # Get chapter info
        chapter = repo.get_chapter(run_data["project_id"], run_data["chapter_number"])

        # Build steps timeline
        steps = _build_steps_timeline(run_data, chapter, llm_mode)

        return envelope_response({
            "run_id": run_id,
            "project_id": run_data["project_id"],
            "project_name": project_name,
            "chapter_number": run_data["chapter_number"],
            "workflow_status": run_data.get("status", "unknown"),
            "chapter_status": chapter.get("status", "unknown") if chapter else "unknown",
            "llm_mode": llm_mode,
            "started_at": run_data.get("started_at", ""),
            "completed_at": run_data.get("completed_at", ""),
            "error_message": run_data.get("error_message"),
            "steps": steps,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行详情失败: {str(e)}")


def _build_steps_timeline(
    run_data: dict,
    chapter: dict | None,
    llm_mode: str,
) -> list[dict]:
    """Build steps timeline from run data and chapter status.

    Derives step status from:
    1. workflow_runs.current_node (last running agent)
    2. chapter.status (final status)
    3. STATUS_ROUTE (expected flow)
    """
    workflow_status = run_data.get("status", "unknown")
    current_node = run_data.get("current_node")
    error_message = run_data.get("error_message")

    # Determine final chapter status
    final_status = chapter.get("status", "planned") if chapter else "planned"

    # Determine which steps completed
    # Based on STATUS_ROUTE: planned -> screenwriter -> author -> polisher -> editor -> publish
    completed_agents = []
    if final_status in ("scripted", "drafted", "polished", "reviewed", "published"):
        completed_agents.append("screenwriter")
    if final_status in ("drafted", "polished", "reviewed", "published"):
        completed_agents.append("author")
    if final_status in ("polished", "reviewed", "published"):
        completed_agents.append("polisher")
    if final_status in ("reviewed", "published"):
        completed_agents.append("editor")
    if final_status == "published":
        completed_agents.append("publish")

    # Build steps
    steps = []
    for step_config in AGENT_STEPS:
        key = step_config["key"]
        is_completed = key in completed_agents
        is_running = (current_node == key) and workflow_status == "running"
        is_failed = (current_node == key) and workflow_status == "failed"
        is_blocked = (current_node == key) and workflow_status == "blocked"

        if is_failed:
            step_status = "failed"
        elif is_blocked:
            step_status = "blocked"
        elif is_running:
            step_status = "running"
        elif is_completed:
            step_status = "completed"
        else:
            step_status = "pending"

        step = {
            "key": key,
            "label": step_config["label"],
            "description": step_config["description"],
            "status": step_status,
        }

        # Add error message for failed step
        if is_failed and error_message:
            step["error_message"] = error_message

        steps.append(step)

    return steps
