"""Style management API endpoints (v6.10.4)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

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


class UpdateStyleBibleStructuredRequest(BaseModel):
    """Structured update request for v6.10.4 (no JSON string required)."""

    bible: dict = Field(default_factory=dict)
    gate_config: dict | None = None


# ── Helpers ─────────────────────────────────────────────────────


def _get_project_name(repo, project_id: str) -> str:
    try:
        project = repo.get_project(project_id)
        return project.get("name", "") if project else ""
    except Exception:
        return ""


def _get_canonical_bible_dict(repo, project_id: str) -> dict | None:
    """Load and normalize a style bible record into canonical dict."""
    from ...style_bible.normalizer import normalize_legacy_bible, normalize_style_bible_status

    record = repo.get_style_bible(project_id)
    if not record:
        return None
    bible_data = record.get("bible", {})
    normalized = normalize_legacy_bible(bible_data)
    normalized["project_id"] = project_id
    status = normalize_style_bible_status(record)
    # Inject gate_config if present
    gate = bible_data.get("gate_config")
    if gate:
        normalized["gate_config"] = gate
    return {
        "project_id": project_id,
        "project_name": _get_project_name(repo, project_id),
        "status": status,
        "version": record.get("version", "1.0.0"),
        "bible": normalized,
        "gate_config": gate or _default_gate_config(),
    }


def _default_gate_config() -> dict:
    return {
        "enabled": False,
        "mode": "warn",
        "blocking_threshold": 70,
        "revision_target": "polisher",
        "apply_stages": ["polished", "final_gate"],
    }


# ── Endpoints ───────────────────────────────────────────────────


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
    from ...style_bible.normalizer import normalize_style_bible_status

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
                    "status": normalize_style_bible_status(bible),
                    "version": bible.get("version", "1.0.0"),
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
                    "mode": config.get("mode", "warn"),
                    "threshold": config.get("blocking_threshold", 70),
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


@router.get("/style/bible/{project_id}")
async def get_style_bible_detail(
    request: Request, project_id: str
) -> EnvelopeResponse:
    """Get full Style Bible detail for a project (v6.10.4)."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        detail = _get_canonical_bible_dict(repo, project_id)
        if not detail:
            return error_response("NOT_FOUND", f"项目 '{project_id}' 没有 Style Bible")

        return envelope_response(detail)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取 Style Bible 失败: {str(e)}")


@router.put("/style/bible/{project_id}")
async def update_style_bible_structured(
    request: Request, project_id: str, body: UpdateStyleBibleStructuredRequest
) -> EnvelopeResponse:
    """Update Style Bible with structured JSON (v6.10.4).

    Accepts a structured bible dict and optional gate_config.
    """
    from ..deps import get_repo
    from ...models.style_bible import StyleBible
    from ...models.style_gate import StyleGateConfig

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        existing = repo.get_style_bible(project_id)
        existing_bible = dict(existing.get("bible", {}) if existing else {})

        # Validate bible through canonical model. Empty body.bible means "preserve
        # existing bible and only update gate_config"; non-empty body.bible is a
        # partial/full bible update merged over existing data.
        incoming_bible = dict(body.bible or {})
        bible_data = {**existing_bible, **incoming_bible}
        bible_data["project_id"] = project_id
        try:
            bible_obj = StyleBible(**bible_data)
        except Exception as ve:
            return error_response("VALIDATION_ERROR", f"Style Bible 字段校验失败: {str(ve)}")

        bible_dict = bible_obj.to_storage_dict()
        if incoming_bible:
            bible_dict["status"] = str(incoming_bible.get("status") or "active")
        elif existing_bible.get("status"):
            bible_dict["status"] = existing_bible["status"]

        # Merge gate_config if provided; otherwise preserve existing gate_config.
        if body.gate_config is not None:
            try:
                gate_obj = StyleGateConfig(**body.gate_config)
                bible_dict["gate_config"] = gate_obj.to_storage_dict()
            except Exception as ve:
                return error_response("VALIDATION_ERROR", f"Gate Config 字段校验失败: {str(ve)}")
        elif existing_bible.get("gate_config"):
            bible_dict["gate_config"] = existing_bible["gate_config"]

        for extra_key in ("generated_from_reference", "reference_length"):
            if extra_key in existing_bible:
                bible_dict[extra_key] = existing_bible[extra_key]

        # Bump version slightly
        current_version = str(existing.get("version", "1.0.0") if existing else "1.0.0")
        try:
            major, minor, patch = current_version.split(".")
            new_version = f"{major}.{minor}.{int(patch) + 1}"
        except Exception:
            new_version = "1.0.1"
        bible_dict["version"] = new_version

        # Check if style bible exists
        if existing:
            updated = repo.update_style_bible(project_id, bible_dict)
            if not updated:
                return error_response("UPDATE_FAILED", "更新 Style Bible 失败")
            return envelope_response({
                "updated": True,
                "project_id": project_id,
                "version": new_version,
            })
        else:
            try:
                bible_id = repo.save_style_bible(project_id, bible_dict)
                return envelope_response({
                    "created": True,
                    "project_id": project_id,
                    "bible_id": bible_id,
                    "version": new_version,
                })
            except ValueError as e:
                return error_response("ALREADY_EXISTS", str(e))

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新 Style Bible 失败: {str(e)}")


@router.put("/style/bible")
async def update_style_bible(
    request: Request, body: UpdateStyleBibleRequest
) -> EnvelopeResponse:
    """Update style bible for a project (v5.2 Phase C legacy compat).

    Updates the style bible content. Creates a new version if one exists.
    Internal implementation delegates to the new structured endpoint logic.
    """
    from ..deps import get_repo
    from ...style_bible.normalizer import normalize_legacy_bible

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

        # Normalize legacy format
        bible_dict = normalize_legacy_bible(bible_dict)
        bible_dict["project_id"] = body.project_id

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
    """Initialize style bible for a project (v6.10.4).

    Creates a canonical StyleBible from template if none exists.
    """
    from ..deps import get_repo
    from ...style_bible.templates import (
        create_style_bible_from_template,
        select_template_for_genre,
    )
    from ...models.style_bible import StyleBible
    from ...models.style_gate import StyleGateConfig

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
                f"项目 '{body.project_id}' 已有 Style Bible，请使用 PUT /style/bible/{body.project_id} 更新"
            )

        # Select template based on genre
        genre = project.get("genre", "")
        template_id = select_template_for_genre(genre)

        # Generate canonical StyleBible from template
        overrides: dict = {}
        if project.get("name"):
            overrides["name"] = f"{project['name']} 风格指南"
        if genre:
            overrides["genre"] = genre

        bible = create_style_bible_from_template(
            project_id=body.project_id,
            template_id=template_id,
            overrides=overrides,
        )

        # Ensure status starts as draft
        bible_dict = bible.to_storage_dict()
        bible_dict["status"] = "draft"
        bible_dict["project_id"] = body.project_id

        # Attach default gate config (enabled=False, mode=warn)
        default_gate = StyleGateConfig(enabled=False, mode="warn")
        bible_dict["gate_config"] = default_gate.to_storage_dict()

        # If reference text provided, note it but still use canonical schema
        if body.reference_text:
            bible_dict["generated_from_reference"] = True
            bible_dict["reference_length"] = len(body.reference_text)
            bible_dict["status"] = "needs_review"

        # Save
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
            "template_used": template_id,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"初始化 Style Bible 失败: {str(e)}")
