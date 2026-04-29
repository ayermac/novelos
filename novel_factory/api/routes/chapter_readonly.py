"""Read-only chapter and project data endpoints.

Provides access to: state-history, versions, quality-reports,
continuity-reports, and agent artifacts.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


# ── Chapter state history ─────────────────────────────────────

@router.get("/projects/{project_id}/chapters/{chapter_number}/state-history")
async def list_state_history(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """List state history for a chapter."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        history = repo.list_state_history(project_id, chapter_number)
        return envelope_response(history)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取状态历史失败: {str(e)}")


# ── Chapter versions ──────────────────────────────────────────

@router.get("/projects/{project_id}/chapters/{chapter_number}/versions")
async def list_versions(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """List all versions for a chapter."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        versions = repo.list_chapter_versions(project_id, chapter_number)
        return envelope_response(versions)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取版本列表失败: {str(e)}")


@router.get("/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}/diff")
async def get_version_diff(
    request: Request, project_id: str, chapter_number: int, version_id: int
) -> EnvelopeResponse:
    """Get a specific version with content for diff comparison."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        version = repo.get_version_by_id(project_id, version_id)
        if not version:
            return error_response("VERSION_NOT_FOUND", f"版本 {version_id} 不存在")

        # Also get the previous version for diff
        versions = repo.list_chapter_versions(project_id, chapter_number)
        prev_version = None
        for v in versions:
            if v["id"] == version_id:
                idx = versions.index(v)
                if idx + 1 < len(versions):
                    prev_version = repo.get_version_by_id(project_id, versions[idx + 1]["id"])
                break

        return envelope_response({
            "current": version,
            "previous": prev_version,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取版本差异失败: {str(e)}")


# ── Quality reports ───────────────────────────────────────────

@router.get("/projects/{project_id}/quality-reports")
async def list_quality_reports(
    request: Request,
    project_id: str,
    chapter_number: int | None = None,
    stage: str | None = None,
    limit: int = 20,
) -> EnvelopeResponse:
    """List quality reports for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        reports = repo.get_quality_reports(
            project_id, chapter_number=chapter_number, stage=stage, limit=limit
        )
        return envelope_response(reports)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取质量报告失败: {str(e)}")


# ── Continuity reports ────────────────────────────────────────

@router.get("/projects/{project_id}/continuity-reports")
async def list_continuity_reports(
    request: Request, project_id: str, limit: int = 20
) -> EnvelopeResponse:
    """List continuity gate reports for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        runs = repo.get_workflow_runs_for_project(project_id, limit=limit)
        reports = []
        for run in runs:
            run_id = run.get("id")
            if run_id:
                gate = repo.get_latest_batch_continuity_gate(run_id)
                if gate:
                    gate["run_id"] = run_id
                    gate["chapter_number"] = run.get("chapter_number")
                    reports.append(gate)

        return envelope_response(reports)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取连续性报告失败: {str(e)}")


# ── Agent artifacts ───────────────────────────────────────────

@router.get("/projects/{project_id}/artifacts")
async def list_artifacts(
    request: Request, project_id: str, limit: int = 50
) -> EnvelopeResponse:
    """List agent artifacts for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        artifacts = repo.list_artifacts(project_id, limit=limit)
        return envelope_response(artifacts)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取 Agent 产物失败: {str(e)}")
