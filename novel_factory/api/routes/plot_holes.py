"""Plot holes (伏笔) API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/plot-holes")
async def list_plot_holes(
    request: Request, project_id: str, status: str | None = None
) -> EnvelopeResponse:
    """List plot holes for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        plot_holes = repo.list_plot_holes(project_id, status=status)
        return envelope_response(plot_holes)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取伏笔列表失败: {str(e)}")


@router.get("/projects/{project_id}/plot-holes/{plot_id}")
async def get_plot_hole(
    request: Request, project_id: str, plot_id: int
) -> EnvelopeResponse:
    """Get a specific plot hole."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        plot_hole = repo.get_plot_hole(project_id, plot_id)
        if not plot_hole:
            return error_response("PLOT_HOLE_NOT_FOUND", f"伏笔 {plot_id} 不存在")

        return envelope_response(plot_hole)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取伏笔详情失败: {str(e)}")


@router.post("/projects/{project_id}/plot-holes")
async def create_plot_hole(request: Request, project_id: str) -> EnvelopeResponse:
    """Create a new plot hole."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        body = await request.json()
        code = body.get("code", "")
        title = body.get("title", "")

        if not code:
            return error_response("VALIDATION_ERROR", "伏笔编码不能为空")
        if not title:
            return error_response("VALIDATION_ERROR", "伏笔标题不能为空")

        plot_hole = repo.create_plot_hole(
            project_id=project_id,
            code=code,
            type=body.get("type", ""),
            title=title,
            description=body.get("description", ""),
            planted_chapter=body.get("planted_chapter"),
            planned_resolve_chapter=body.get("planned_resolve_chapter"),
            status=body.get("status", "planted"),
            notes=body.get("notes", ""),
        )

        return envelope_response(plot_hole)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建伏笔失败: {str(e)}")


@router.put("/projects/{project_id}/plot-holes/{plot_id}")
async def update_plot_hole(
    request: Request, project_id: str, plot_id: int
) -> EnvelopeResponse:
    """Update a plot hole."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        existing = repo.get_plot_hole(project_id, plot_id)
        if not existing:
            return error_response("PLOT_HOLE_NOT_FOUND", f"伏笔 {plot_id} 不存在")

        body = await request.json()
        data = {}
        for key in ("code", "type", "title", "description", "planted_chapter",
                     "planned_resolve_chapter", "resolved_chapter", "status", "notes"):
            if key in body:
                data[key] = body[key]

        if not data:
            return envelope_response(existing)

        plot_hole = repo.update_plot_hole(project_id, plot_id, data)
        return envelope_response(plot_hole)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新伏笔失败: {str(e)}")


@router.delete("/projects/{project_id}/plot-holes/{plot_id}")
async def delete_plot_hole(
    request: Request, project_id: str, plot_id: int
) -> EnvelopeResponse:
    """Delete a plot hole."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_plot_hole(project_id, plot_id)
        if not deleted:
            return error_response("PLOT_HOLE_NOT_FOUND", f"伏笔 {plot_id} 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除伏笔失败: {str(e)}")
