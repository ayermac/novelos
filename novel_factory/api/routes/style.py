"""Style management API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class UpdateStyleBibleRequest(BaseModel):
    """Update style bible request (v5.2 Phase C)."""

    project_id: str
    content: str  # JSON string containing style bible content


class InitStyleBibleRequest(BaseModel):
    """Initialize style bible request (v5.2 Phase C)."""

    project_id: str
    reference_text: str | None = None  # Optional reference text to analyze


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
        err_msg = str(e).lower()
        # Graceful degradation when style tables don't exist (old DB or empty DB)
        if "no such table" in err_msg or "does not exist" in err_msg:
            # Still get project count from repo (style tables don't affect projects)
            try:
                repo = get_repo(request)
                projects = repo.list_projects()
                total_projects = len(projects)
            except Exception:
                total_projects = 0
            return envelope_response({
                "style_bibles": [],
                "style_gate_configs": [],
                "style_samples": [],
                "health": {
                    "total_projects": total_projects,
                    "projects_with_bible": 0,
                    "gate_configs": 0,
                },
            })
        return error_response("INTERNAL_ERROR", f"获取风格管理数据失败: {str(e)}")


@router.put("/style/bible")
async def update_style_bible(
    request: Request, body: UpdateStyleBibleRequest
) -> EnvelopeResponse:
    """Update style bible for a project (v5.2 Phase C).

    Updates the style bible content. Creates a new version if one exists.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        # Parse content JSON
        try:
            bible_dict = json.loads(body.content)
        except json.JSONDecodeError as e:
            return error_response("INVALID_JSON", f"Style Bible 内容 JSON 解析失败: {str(e)}")

        # Check if style bible exists
        existing = repo.get_style_bible(body.project_id)

        if existing:
            # Update existing style bible
            updated = repo.update_style_bible(body.project_id, bible_dict)
            if not updated:
                return error_response("UPDATE_FAILED", "更新 Style Bible 失败")
            return envelope_response({
                "updated": True,
                "project_id": body.project_id,
                "version": bible_dict.get("version", existing.get("version", "1.0.0")),
            })
        else:
            # Create new style bible
            try:
                bible_id = repo.save_style_bible(body.project_id, bible_dict)
                return envelope_response({
                    "created": True,
                    "project_id": body.project_id,
                    "bible_id": bible_id,
                    "version": bible_dict.get("version", "1.0.0"),
                })
            except ValueError as e:
                return error_response("ALREADY_EXISTS", str(e))

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新 Style Bible 失败: {str(e)}")


@router.post("/style/init")
async def init_style_bible(
    request: Request, body: InitStyleBibleRequest
) -> EnvelopeResponse:
    """Initialize style bible for a project (v5.2 Phase C).

    Creates a default style bible if none exists. Optionally analyzes
    reference text to generate initial style rules.
    """
    from ..deps import get_repo, get_settings, get_llm_mode

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        # Check if style bible already exists
        existing = repo.get_style_bible(body.project_id)
        if existing:
            return error_response(
                "ALREADY_EXISTS",
                f"项目 '{body.project_id}' 已有 Style Bible，请使用 PUT /style/bible 更新"
            )

        # Generate default style bible content
        if body.reference_text:
            # TODO: In real mode, use LLM to analyze reference text
            # For now, use a template
            bible_dict = {
                "project_name": project.get("name", ""),
                "genre": project.get("genre", ""),
                "generated_from_reference": True,
                "voice": {
                    "tone": "从参考文本中分析",
                    "formality": "适中"
                },
                "narrative": {
                    "pov": "第三人称",
                    "tense": "过去时"
                },
                "reference_length": len(body.reference_text)
            }
        else:
            # Default template
            bible_dict = {
                "project_name": project.get("name", ""),
                "genre": project.get("genre", ""),
                "voice": {
                    "tone": "轻松活泼",
                    "formality": "适中"
                },
                "narrative": {
                    "pov": "第三人称",
                    "tense": "过去时"
                },
                "prose": {
                    "sentence_length": "中短句为主",
                    "dialogue_style": "口语化"
                }
            }

        # Create style bible
        try:
            bible_id = repo.save_style_bible(body.project_id, bible_dict)
        except ValueError as e:
            return error_response("ALREADY_EXISTS", str(e))

        return envelope_response({
            "created": True,
            "project_id": body.project_id,
            "bible_id": bible_id,
            "version": bible_dict.get("version", "1.0.0"),
            "has_reference": body.reference_text is not None,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"初始化 Style Bible 失败: {str(e)}")
