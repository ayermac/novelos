"""Style management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/style/console")
async def get_style_console(request: Request) -> EnvelopeResponse:
    """Get style management console data.

    Returns:
        - Style bible status
        - Style gate status
        - Style samples
        - Health summary
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        projects = repo.list_projects()

        # Get style bible for each project
        style_bibles = []
        for p in projects:
            bible = repo.get_style_bible(p["project_id"])
            if bible:
                style_bibles.append({
                    "project_id": p["project_id"],
                    "project_name": p.get("name", ""),
                    "status": bible.get("status", "unknown"),
                    "version": bible.get("version", 0),
                    "updated_at": bible.get("updated_at", ""),
                })

        # Get style gate status (simplified - just config)
        style_gate_configs = []
        for p in projects[:5]:
            config = repo.get_style_gate_config(p["project_id"])
            if config:
                style_gate_configs.append({
                    "project_id": p["project_id"],
                    "project_name": p.get("name", ""),
                    "enabled": config.get("enabled", False),
                    "threshold": config.get("threshold", 0.8),
                })

        # Get style samples
        style_samples = []
        for p in projects[:3]:
            samples = repo.list_style_samples(p["project_id"])
            for sample in samples[:5]:
                style_samples.append({
                    "project_id": p["project_id"],
                    "sample_id": sample.get("sample_id", ""),
                    "source": sample.get("source", ""),
                    "word_count": sample.get("word_count", 0),
                })

        # Health summary
        health = {
            "total_projects": len(projects),
            "projects_with_bible": len(style_bibles),
            "gate_configs": len(style_gate_configs),
        }

        return envelope_response({
            "style_bibles": style_bibles,
            "style_gate_configs": style_gate_configs,
            "style_samples": style_samples,
            "health": health,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取风格管理数据失败: {str(e)}")
