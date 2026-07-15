"""Genesis API endpoints for project bible generation.

v6.11.0 refactor: Split into modular package structure.
Original 3,587-line file refactored into:
- models.py: Pydantic request/response models
- progress.py: SSE progress streaming
- utils.py: Type conversion utilities
- normalizer.py: Draft parsing and normalization
- scaffold.py: Fallback draft template generation
- coercer.py: Type coercion functions
- llm.py: LLM invocation, prompt building, and repair
- applier.py: Apply draft to project context
- _endpoints.py: FastAPI route handlers (remaining)
"""

from __future__ import annotations

import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from novel_factory.api.envelope import envelope_response, error_response, EnvelopeResponse
from novel_factory.exceptions import APIValidationError
from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft

# Import from split modules
from .models import (
    GenesisGenerateRequest,
    GenesisApproveRequest,
    GenesisRejectRequest,
    GenesisApproveWithForceRequest,
    GenesisForceApplyBody,
)
from .progress import (
    GENESIS_RUNNING_TIMEOUT_MINUTES,
    GENESIS_SEGMENT_LABELS,
    GENESIS_REQUIRED_SECTIONS,
    _push_progress,
    _make_progress_event,
    ProgressCallback,
    get_progress_queue,
    create_progress_queue,
    remove_progress_queue,
)
from .utils import (
    _as_text,
    _as_list,
    _as_int,
    _merge_key_text,
    _short_title,
)
from .normalizer import (
    _normalize_genesis_draft,
    _dedupe_genesis_draft,
    _parse_genesis_draft_json,
)
from .scaffold import (
    _generate_genesis_scaffold,
    _generate_stub_draft,
    _fill_missing_genesis_sections,
    _missing_required_genesis_sections,
    _validate_complete_genesis_draft,
    _incomplete_genesis_message,
    _merge_genesis_drafts,
    _project_description_from_body,
)
from .llm import (
    _generate_real_draft,
    _generate_real_draft_with_scaffold_fallback,
    _complete_real_genesis_draft,
    _build_genesis_segment_prompt,
    _build_genesis_completion_prompt,
    _build_genesis_llm,
    _invoke_genesis_segment,
    _instruction_repair_issue_count,
    _has_instruction_repair_target,
    _format_genesis_quality_issues_for_prompt,
    _instruction_repair_rank,
    _build_local_instruction_repair_candidate,
    _repair_genesis_instruction_quality,
    _mark_genesis_generation_fallback,
    _mark_genesis_local_recovery,
    _build_genesis_recovery_draft,
    _recover_genesis_from_partial_draft,
    _build_genesis_instruction_repair_prompt,
)
from .applier import _apply_genesis_to_project

router = APIRouter()
logger = logging.getLogger(__name__)

def _parse_genesis_timestamp(value) -> datetime | None:
    """Parse genesis timestamps stored as SQLite datetime strings."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None

def _genesis_timeout_minutes(settings=None) -> int:
    """Return the stale-running timeout for genesis runs."""
    workflow = getattr(settings, "workflow", None)
    configured = getattr(workflow, "task_timeout_minutes", GENESIS_RUNNING_TIMEOUT_MINUTES)
    try:
        timeout = int(configured)
    except (TypeError, ValueError):
        timeout = GENESIS_RUNNING_TIMEOUT_MINUTES
    return max(10, timeout)

def _recover_stale_running_genesis(repo, genesis: dict | None, timeout_minutes: int | None = None) -> dict | None:
    """Mark an abandoned running genesis as failed so the UI can retry.

    A genesis request writes the run row before calling the LLM. If the desktop
    sidecar is restarted, killed, or disconnected mid-request, the normal
    exception handler never gets a chance to flip the row out of ``running``.
    """
    if not genesis or genesis.get("status") != "running":
        return genesis

    timeout = timeout_minutes or GENESIS_RUNNING_TIMEOUT_MINUTES
    timestamp = _parse_genesis_timestamp(genesis.get("updated_at") or genesis.get("created_at"))
    if timestamp is None:
        return genesis

    now_local = datetime.utcnow() + timedelta(hours=8)
    elapsed_minutes = (now_local - timestamp).total_seconds() / 60
    if elapsed_minutes < timeout:
        return genesis

    message = (
        f"创世任务超过 {timeout} 分钟未更新，已自动标记失败。"
        "可能是本地服务重启、请求断开或 LLM 超时导致，请重新生成。"
    )
    updated = repo.update_genesis_run(genesis["id"], {
        "status": "failed",
        "error_message": message,
    })
    return updated or {**genesis, "status": "failed", "error_message": message}

def _fail_orphaned_running_genesis(repo, genesis: dict) -> dict:
    """Fail a running Genesis row that no longer has an in-process producer."""
    message = (
        "创世任务已中断，可能是客户端关闭或本地服务重启导致。"
        "请重新生成。"
    )
    updated = repo.update_genesis_run(genesis["id"], {
        "status": "failed",
        "error_message": message,
    })
    return updated or {**genesis, "status": "failed", "error_message": message}

def _quality_report_payload(quality_report) -> dict:
    """Serialize a Genesis quality report for API responses and audit metadata."""
    return {
        "passed": quality_report.passed,
        "score": quality_report.score,
        "quality_status": quality_report.quality_status,
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "message": issue.message,
                "section": issue.section,
                "item_ref": issue.item_ref,
                "suggestion": issue.suggestion,
            }
            for issue in quality_report.issues
        ],
        "metrics": quality_report.metrics,
    }

def _approve_genesis_run_with_quality_audit(
    repo,
    genesis_id: str,
    draft: dict,
    quality_report,
    *,
    forced_apply: bool,
) -> None:
    """Mark a genesis run approved and persist force-apply audit in draft_json."""
    update_data: dict = {"status": "approved"}
    if forced_apply:
        audited_draft = dict(draft)
        meta = audited_draft.get("_meta")
        if not isinstance(meta, dict):
            meta = {}
        meta["forced_quality_apply"] = True
        meta["quality_report_snapshot"] = _quality_report_payload(quality_report)
        audited_draft["_meta"] = meta
        update_data["draft_json"] = json.dumps(audited_draft, ensure_ascii=False)
    repo.update_genesis_run(genesis_id, update_data)

def _quality_report_for_genesis(genesis: dict, project: dict) -> dict | None:
    """Evaluate and serialize quality for a persisted genesis run.

    v6.6.4: Recomputes quality from current draft_json. Preserves _meta audit
    if the draft was previously force-applied.
    """
    draft = _parse_genesis_draft_json(genesis.get("draft_json"))
    if draft is None:
        return None

    input_json = genesis.get("input_json", "{}")
    try:
        input_data = json.loads(input_json) if isinstance(input_json, str) else input_json
    except json.JSONDecodeError:
        input_data = {}
    if not isinstance(input_data, dict):
        input_data = {}

    quality_report = evaluate_genesis_draft(
        draft,
        title=input_data.get("title", project.get("name", "")),
        genre=input_data.get("genre", project.get("genre", "")),
        premise=input_data.get("premise", project.get("description", "")),
        target_chapters=input_data.get("target_chapters", project.get("total_chapters_planned", 10) or 10),
    )
    payload = _quality_report_payload(quality_report)

    # v6.6.4: Preserve forced_quality_apply audit in quality report
    meta = draft.get("_meta") if isinstance(draft, dict) else None
    if isinstance(meta, dict) and meta.get("forced_quality_apply"):
        payload["_meta"] = {
            "forced_quality_apply": True,
            "quality_report_snapshot": meta.get("quality_report_snapshot"),
        }

    return payload

def _validate_genesis_generate_request(body: GenesisGenerateRequest) -> tuple[str, str] | None:
    """Return a validation error for empty or nonsensical genesis input.

    v6.3.1: premise is optional — AI can infer it from title + genre + description.
    """
    if not body.title.strip():
        return "GENESIS_INPUT_REQUIRED", "请填写项目标题后再生成创世设定"
    if not body.genre.strip():
        return "GENESIS_INPUT_REQUIRED", "请填写作品类型后再生成创世设定"
    if body.target_chapters < 1:
        return "GENESIS_INPUT_REQUIRED", "首批规划章数必须大于 0"
    if body.target_words < 1:
        return "GENESIS_INPUT_REQUIRED", "首批规划字数必须大于 0"
    return None

def _with_project_defaults(
    body: GenesisGenerateRequest,
    project: dict,
    project_id: str | None = None,
) -> GenesisGenerateRequest:
    """Fill genesis input from project fields already collected during onboarding."""
    return body.model_copy(update={
        "project_id": body.project_id or project_id or project.get("project_id", ""),
        "title": body.title.strip() or project.get("name", ""),
        "genre": body.genre.strip() or project.get("genre", ""),
        "premise": body.premise.strip() or project.get("description", ""),
    })

@router.post("/projects/{project_id}/genesis/generate")
async def generate_genesis(
    request: Request,
    project_id: str,
    body: GenesisGenerateRequest,
) -> EnvelopeResponse:
    """Generate a project bible draft from creative intent."""
    from novel_factory.api.deps import get_repo, get_llm_mode, get_settings

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)
        settings = get_settings(request)

        project = repo.get_project(project_id)
        if not project:
            raise APIValidationError("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        body = _with_project_defaults(body, project, project_id)
        validation_error = _validate_genesis_generate_request(body)
        if validation_error:
            return error_response(*validation_error)

        # Check for running genesis
        latest = repo.get_latest_genesis_run(project_id)
        latest = _recover_stale_running_genesis(
            repo,
            latest,
            _genesis_timeout_minutes(settings),
        )
        if latest and latest["status"] == "running":
            raise APIValidationError(
                "GENESIS_IN_PROGRESS",
                "已有正在运行的创世任务，请等待完成",
            )

        # Create genesis run record
        input_json = json.dumps(body.model_dump(), ensure_ascii=False)
        genesis_run = repo.create_genesis_run(project_id, input_json, status="running")

        try:
            if llm_mode == "stub":
                draft = _generate_stub_draft(body)
            else:
                draft = await _generate_real_draft_with_scaffold_fallback(body, settings)
            draft, missing_sections = _validate_complete_genesis_draft(draft)
            if draft is None:
                raise ValueError("创世草案数据格式错误，未生成可应用的 JSON 对象")
            if missing_sections:
                raise ValueError(_incomplete_genesis_message(missing_sections))

            # v6.6.3: Run quality gate
            quality_report = evaluate_genesis_draft(
                draft,
                title=body.title,
                genre=body.genre,
                premise=body.premise,
                target_chapters=body.target_chapters,
            )

            repo.update_genesis_run(genesis_run["id"], {
                "status": "generated",
                "draft_json": json.dumps(draft, ensure_ascii=False),
            })
            genesis_run = repo.get_genesis_run(genesis_run["id"])

            # v6.6.3: Include quality report in response
            response_data = dict(genesis_run)
            response_data["quality_report"] = _quality_report_payload(quality_report)

        except Exception as e:
            repo.update_genesis_run(genesis_run["id"], {
                "status": "failed",
                "error_message": str(e)[:500],
            })
            return error_response("GENESIS_FAILED", f"项目设定生成失败: {str(e)[:200]}")

        return envelope_response(response_data)

    except APIValidationError as e:
        return error_response(e.code, e.message)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"生成项目设定失败: {str(e)[:200]}")

@router.get("/projects/{project_id}/genesis/latest")
async def get_latest_genesis(request: Request, project_id: str) -> EnvelopeResponse:
    """Get the latest genesis run for a project."""
    from novel_factory.api.deps import get_repo, get_settings

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            raise APIValidationError("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        genesis = repo.get_latest_genesis_run(project_id)
        if not genesis:
            return envelope_response(None)
        genesis = _recover_stale_running_genesis(
            repo,
            genesis,
            _genesis_timeout_minutes(get_settings(request)),
        )

        response_data = dict(genesis)
        quality_report = _quality_report_for_genesis(genesis, project)
        if quality_report is not None:
            response_data["quality_report"] = quality_report

        return envelope_response(response_data)

    except APIValidationError as e:
        return error_response(e.code, e.message)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取创世记录失败: {str(e)[:200]}")

@router.get("/projects/{project_id}/genesis/{genesis_id}/chapter-impact")
async def get_genesis_chapter_impact(
    request: Request,
    project_id: str,
    genesis_id: str,
) -> EnvelopeResponse:
    """v6.8.5: Pre-check chapter impact before approving genesis.

    Returns chapter status summary and warnings for re-genesis scenarios.
    """
    from novel_factory.api.deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            raise APIValidationError("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        genesis = repo.get_genesis_run(genesis_id)
        if not genesis:
            raise APIValidationError("GENESIS_NOT_FOUND", "创世记录不存在")

        if genesis["project_id"] != project_id:
            raise APIValidationError("GENESIS_NOT_FOUND", "创世记录不属于该项目")

        # Get chapter status summary
        chapter_status_counts = repo.count_chapters_by_status(project_id)
        terminal_chapters = repo.get_terminal_chapters(project_id)
        non_terminal_chapters = repo.get_non_terminal_chapters(project_id)

        total_chapters = sum(chapter_status_counts.values())
        has_existing_chapters = total_chapters > 0

        # Build warnings
        warnings = []
        if terminal_chapters:
            warnings.append({
                "type": "terminal_chapters_exist",
                "message": f"项目已有 {len(terminal_chapters)} 个终态章节（已发布/已审核/等待发布），重新创世将导致这些章节内容与新设定脱节",
                "chapters": [ch["chapter_number"] for ch in terminal_chapters],
            })
        if non_terminal_chapters:
            warnings.append({
                "type": "non_terminal_chapters_exist",
                "message": f"项目已有 {len(non_terminal_chapters)} 个非终态章节，重新创世将重置这些章节",
                "chapters": [ch["chapter_number"] for ch in non_terminal_chapters],
            })

        # Build cleanup options
        cleanup_options = []
        if terminal_chapters:
            cleanup_options.append({
                "mode": "keep_published",
                "label": "保留已发布章节",
                "description": f"保留 {len(terminal_chapters)} 个终态章节，重置 {len(non_terminal_chapters)} 个非终态章节",
            })
            cleanup_options.append({
                "mode": "reset_all",
                "label": "全部重来",
                "description": f"重置所有 {total_chapters} 个章节（包括已发布章节）",
            })
            cleanup_options.append({
                "mode": "delete_all",
                "label": "删除所有章节",
                "description": f"删除所有 {total_chapters} 个章节",
            })
        elif non_terminal_chapters:
            cleanup_options.append({
                "mode": "keep_published",
                "label": "重置非终态章节",
                "description": f"重置 {len(non_terminal_chapters)} 个非终态章节",
            })
            cleanup_options.append({
                "mode": "delete_all",
                "label": "删除所有章节",
                "description": f"删除所有 {total_chapters} 个章节",
            })

        return envelope_response({
            "project_id": project_id,
            "genesis_id": genesis_id,
            "chapter_status_counts": chapter_status_counts,
            "total_chapters": total_chapters,
            "has_existing_chapters": has_existing_chapters,
            "terminal_chapters_count": len(terminal_chapters),
            "non_terminal_chapters_count": len(non_terminal_chapters),
            "warnings": warnings,
            "cleanup_options": cleanup_options,
            "recommended_mode": "keep_published" if terminal_chapters else ("keep_published" if non_terminal_chapters else None),
        })

    except APIValidationError as e:
        return error_response(e.code, e.message)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取章节影响分析失败: {str(e)[:200]}")

@router.post("/projects/{project_id}/genesis/{genesis_id}/approve")
async def approve_genesis(
    request: Request,
    project_id: str,
    genesis_id: str,
    body: GenesisForceApplyBody | None = None,
) -> EnvelopeResponse:
    """Approve a genesis draft and write to formal tables.

    v6.6.3: Runs quality gate before approval. Blocked drafts cannot be approved
    without explicit force_apply + confirm_quality_risk flags.
    v6.8.5: Added chapter_cleanup_mode for re-genesis protection.
    """
    from novel_factory.api.deps import get_repo

    # Extract force_apply flags from body if provided
    force_apply = body.force_apply if body else False
    confirm_quality_risk = body.confirm_quality_risk if body else False

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            raise APIValidationError("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        genesis = repo.get_genesis_run(genesis_id)
        if not genesis:
            raise APIValidationError("GENESIS_NOT_FOUND", "创世记录不存在")

        if genesis["project_id"] != project_id:
            raise APIValidationError("GENESIS_NOT_FOUND", "创世记录不属于该项目")

        if genesis["status"] != "generated":
            raise APIValidationError(
                "INVALID_GENESIS_STATUS",
                f"只能批准已生成的创世记录，当前状态: {genesis['status']}",
            )

        # Parse draft
        draft = _parse_genesis_draft_json(genesis.get("draft_json"))
        if draft is None:
            raise APIValidationError("INVALID_DRAFT", "创世草案数据格式错误")
        missing_sections = _missing_required_genesis_sections(draft)
        if missing_sections:
            raise APIValidationError("INCOMPLETE_DRAFT", _incomplete_genesis_message(missing_sections))

        # v6.6.3: Run quality gate
        input_json = genesis.get("input_json", "{}")
        try:
            input_data = json.loads(input_json) if isinstance(input_json, str) else input_json
        except json.JSONDecodeError:
            input_data = {}

        quality_report = evaluate_genesis_draft(
            draft,
            title=input_data.get("title", project.get("name", "")),
            genre=input_data.get("genre", project.get("genre", "")),
            premise=input_data.get("premise", project.get("description", "")),
            target_chapters=input_data.get("target_chapters", 10),
        )

        # v6.6.3: Block if quality gate failed (unless force_apply)
        if not quality_report.passed:
            if not (force_apply and confirm_quality_risk):
                raise APIValidationError(
                    "GENESIS_QUALITY_BLOCKED",
                    "创世草案质量不足，请重新生成或人工补全后再批准",
                )

        # Apply to formal tables
        # v6.8.5: Pass chapter_cleanup_mode for re-genesis protection
        chapter_cleanup_mode = body.chapter_cleanup_mode if body else None
        applied = _apply_genesis_to_project(repo, project_id, draft, chapter_cleanup_mode=chapter_cleanup_mode)

        forced_apply = force_apply and not quality_report.passed
        _approve_genesis_run_with_quality_audit(
            repo,
            genesis_id,
            draft,
            quality_report,
            forced_apply=forced_apply,
        )

        return envelope_response({
            "genesis_id": genesis_id,
            "status": "approved",
            "applied": applied,
            "quality_report": _quality_report_payload(quality_report),
            "forced_apply": forced_apply,
        })

    except APIValidationError as e:
        return error_response(e.code, e.message)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"批准创世记录失败: {str(e)[:200]}")

@router.post("/projects/{project_id}/genesis/{genesis_id}/reject")
async def reject_genesis(
    request: Request,
    project_id: str,
    genesis_id: str,
) -> EnvelopeResponse:
    """Reject a genesis draft."""
    from novel_factory.api.deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            raise APIValidationError("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        genesis = repo.get_genesis_run(genesis_id)
        if not genesis:
            raise APIValidationError("GENESIS_NOT_FOUND", "创世记录不存在")

        if genesis["project_id"] != project_id:
            raise APIValidationError("GENESIS_NOT_FOUND", "创世记录不属于该项目")

        if genesis["status"] not in ("generated", "failed"):
            raise APIValidationError(
                "INVALID_GENESIS_STATUS",
                f"只能拒绝已生成或失败的创世记录，当前状态: {genesis['status']}",
            )

        repo.update_genesis_run(genesis_id, {"status": "rejected"})

        return envelope_response({
            "genesis_id": genesis_id,
            "status": "rejected",
        })

    except APIValidationError as e:
        return error_response(e.code, e.message)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"拒绝创世记录失败: {str(e)[:200]}")

# ---------------------------------------------------------------------------
# Canonical body-style routes (API Contract §4)
# ---------------------------------------------------------------------------

@router.post("/genesis/generate")
async def generate_genesis_canonical(
    request: Request, body: GenesisGenerateRequest
) -> EnvelopeResponse:
    """Canonical body-style route for genesis generate."""
    from novel_factory.api.deps import get_repo, get_llm_mode, get_settings

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)
        settings = get_settings(request)
        project_id = body.project_id

        if not project_id:
            return error_response("VALIDATION_ERROR", "project_id 不能为空")

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        body = _with_project_defaults(body, project, project_id)
        validation_error = _validate_genesis_generate_request(body)
        if validation_error:
            return error_response(*validation_error)

        latest = repo.get_latest_genesis_run(project_id)
        latest = _recover_stale_running_genesis(
            repo,
            latest,
            _genesis_timeout_minutes(settings),
        )
        if latest and latest["status"] == "running":
            return error_response("GENESIS_IN_PROGRESS", "已有正在运行的创世任务，请等待完成")

        input_json = json.dumps(body.model_dump(), ensure_ascii=False)
        genesis_run = repo.create_genesis_run(project_id, input_json, status="running")

        try:
            if llm_mode == "stub":
                draft = _generate_stub_draft(body)
            else:
                draft = await _generate_real_draft_with_scaffold_fallback(body, settings)
            draft, missing_sections = _validate_complete_genesis_draft(draft)
            if draft is None:
                raise ValueError("创世草案数据格式错误，未生成可应用的 JSON 对象")
            if missing_sections:
                raise ValueError(_incomplete_genesis_message(missing_sections))

            # v6.6.3: Run quality gate
            quality_report = evaluate_genesis_draft(
                draft,
                title=body.title,
                genre=body.genre,
                premise=body.premise,
                target_chapters=body.target_chapters,
            )

            repo.update_genesis_run(genesis_run["id"], {
                "status": "generated",
                "draft_json": json.dumps(draft, ensure_ascii=False),
            })
            genesis_run = repo.get_genesis_run(genesis_run["id"])

            # v6.6.3: Include quality report in response
            response_data = dict(genesis_run)
            response_data["quality_report"] = _quality_report_payload(quality_report)
        except Exception as e:
            repo.update_genesis_run(genesis_run["id"], {
                "status": "failed",
                "error_message": str(e)[:500],
            })
            return error_response("GENESIS_FAILED", f"项目设定生成失败: {str(e)[:200]}")

        return envelope_response(response_data)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"生成项目设定失败: {str(e)[:200]}")

@router.post("/genesis/approve")
async def approve_genesis_canonical(
    request: Request, body: GenesisApproveWithForceRequest
) -> EnvelopeResponse:
    """Canonical body-style route for genesis approve.

    v6.6.3: Supports force_apply + confirm_quality_risk for blocked drafts.
    """
    from novel_factory.api.deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        genesis = repo.get_genesis_run(body.genesis_id)
        if not genesis:
            return error_response("GENESIS_NOT_FOUND", "创世记录不存在")

        if genesis["project_id"] != body.project_id:
            return error_response("GENESIS_NOT_FOUND", "创世记录不属于该项目")

        if genesis["status"] != "generated":
            return error_response(
                "INVALID_GENESIS_STATUS",
                f"只能批准已生成的创世记录，当前状态: {genesis['status']}",
            )

        draft = _parse_genesis_draft_json(genesis.get("draft_json"))
        if draft is None:
            return error_response("INVALID_DRAFT", "创世草案数据格式错误")
        missing_sections = _missing_required_genesis_sections(draft)
        if missing_sections:
            return error_response("INCOMPLETE_DRAFT", _incomplete_genesis_message(missing_sections))

        # v6.6.3: Run quality gate
        input_json = genesis.get("input_json", "{}")
        try:
            input_data = json.loads(input_json) if isinstance(input_json, str) else input_json
        except json.JSONDecodeError:
            input_data = {}

        quality_report = evaluate_genesis_draft(
            draft,
            title=input_data.get("title", project.get("name", "")),
            genre=input_data.get("genre", project.get("genre", "")),
            premise=input_data.get("premise", project.get("description", "")),
            target_chapters=input_data.get("target_chapters", 10),
        )

        # v6.6.3: Block if quality gate failed, unless force_apply is set
        if not quality_report.passed:
            if not (body.force_apply and body.confirm_quality_risk):
                return error_response(
                    "GENESIS_QUALITY_BLOCKED",
                    "创世草案质量不足，请重新生成或人工补全后再批准。如需强制应用，请设置 force_apply=true 和 confirm_quality_risk=true",
                    {
                        "quality_report": _quality_report_payload(quality_report)
                    },
                )

        # v6.8.5: Pass chapter_cleanup_mode for re-genesis protection
        applied = _apply_genesis_to_project(repo, body.project_id, draft, chapter_cleanup_mode=body.chapter_cleanup_mode)

        forced_apply = not quality_report.passed and body.force_apply
        _approve_genesis_run_with_quality_audit(
            repo,
            body.genesis_id,
            draft,
            quality_report,
            forced_apply=forced_apply,
        )

        return envelope_response({
            "genesis_id": body.genesis_id,
            "status": "approved",
            "applied": applied,
            "quality_report": _quality_report_payload(quality_report),
            "forced_apply": forced_apply,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"批准创世记录失败: {str(e)[:200]}")

@router.post("/genesis/reject")
async def reject_genesis_canonical(
    request: Request, body: GenesisRejectRequest
) -> EnvelopeResponse:
    """Canonical body-style route for genesis reject."""
    from novel_factory.api.deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        genesis = repo.get_genesis_run(body.genesis_id)
        if not genesis:
            return error_response("GENESIS_NOT_FOUND", "创世记录不存在")

        if genesis["project_id"] != body.project_id:
            return error_response("GENESIS_NOT_FOUND", "创世记录不属于该项目")

        if genesis["status"] not in ("generated", "failed"):
            return error_response(
                "INVALID_GENESIS_STATUS",
                f"只能拒绝已生成或失败的创世记录，当前状态: {genesis['status']}",
            )

        repo.update_genesis_run(body.genesis_id, {"status": "rejected"})

        return envelope_response({
            "genesis_id": body.genesis_id,
            "status": "rejected",
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"拒绝创世记录失败: {str(e)[:200]}")

# ---------------------------------------------------------------------------
# v6.7.7: Genesis progress streaming endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/genesis/generate/start")
async def start_genesis_generate(
    request: Request,
    project_id: str,
    body: GenesisGenerateRequest,
) -> EnvelopeResponse:
    """Start async Genesis generation with progress streaming.

    v6.7.7: Creates a running genesis run and kicks off background generation.
    Returns run_id and stream_url for SSE progress monitoring.
    The existing synchronous POST /genesis/generate is preserved for backward compatibility.
    """
    from novel_factory.api.deps import get_repo, get_llm_mode, get_settings

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)
        settings = get_settings(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        body = _with_project_defaults(body, project, project_id)
        body.project_id = project_id
        validation_error = _validate_genesis_generate_request(body)
        if validation_error:
            return error_response(*validation_error)

        # Check for running genesis
        latest = repo.get_latest_genesis_run(project_id)
        latest = _recover_stale_running_genesis(
            repo, latest, _genesis_timeout_minutes(settings),
        )
        if latest and latest["status"] == "running":
            return error_response(
                "GENESIS_IN_PROGRESS",
                "已有正在运行的创世任务，请等待完成",
            )

        # Create genesis run record
        input_json = json.dumps(body.model_dump(), ensure_ascii=False)
        genesis_run = repo.create_genesis_run(project_id, input_json, status="running")
        run_id = genesis_run["id"]

        # Create progress queue
        queue = create_progress_queue(run_id)

        # Emit started event
        _push_progress(run_id, _make_progress_event("genesis_started", run_id))

        # Launch background task
        asyncio.create_task(
            _run_genesis_background(
                run_id=run_id,
                project_id=project_id,
                body=body,
                llm_mode=llm_mode,
                settings=settings,
                db_path=getattr(request.app.state, "db_path", None),
                config_path=getattr(request.app.state, "config_path", None),
            )
        )

        stream_url = f"/api/projects/{project_id}/genesis/generate/stream/{run_id}"

        return envelope_response({
            "run_id": run_id,
            "stream_url": stream_url,
            "status": "running",
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"启动创世生成失败: {str(e)[:200]}")

async def _run_genesis_background(
    *,
    run_id: str,
    project_id: str,
    body: GenesisGenerateRequest,
    llm_mode: str,
    settings,
    db_path: str | None,
    config_path: str | None,
) -> None:
    """Background task for async Genesis generation with progress streaming.

    v6.7.7: Runs the full generation pipeline and emits progress events.
    """
    from novel_factory.db.repository import Repository
    from novel_factory.config.loader import load_settings_with_cli

    repo = Repository(db_path) if db_path else Repository()

    def _progress_callback(event_type: str, data: dict) -> None:
        _push_progress(run_id, _make_progress_event(event_type, run_id, **{k: v for k, v in data.items() if k != "run_id"}))

    try:
        if llm_mode == "stub":
            draft = _generate_stub_draft(body, run_id=run_id, progress=_progress_callback)
        else:
            draft = await _generate_real_draft_with_scaffold_fallback(
                body, settings, run_id=run_id, progress=_progress_callback,
            )

        # Validation phase (structural completeness check)
        draft, missing_sections = _validate_complete_genesis_draft(draft)
        if draft is None:
            raise ValueError("创世草案数据格式错误，未生成可应用的 JSON 对象")
        if missing_sections:
            raise ValueError(_incomplete_genesis_message(missing_sections))

        # Quality report phase
        _progress_callback("segment_started", {"segment": "quality_report", "label": GENESIS_SEGMENT_LABELS["quality_report"]})
        quality_report = evaluate_genesis_draft(
            draft,
            title=body.title,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
        )
        _progress_callback("segment_completed", {"segment": "quality_report", "label": GENESIS_SEGMENT_LABELS["quality_report"]})

        # Update genesis run (use 'generated' for consistency with existing system)
        repo.update_genesis_run(run_id, {
            "status": "generated",
            "draft_json": json.dumps(draft, ensure_ascii=False),
        })
        genesis_run = repo.get_genesis_run(run_id)

        # Build completion payload
        response_data = dict(genesis_run) if genesis_run else {}
        response_data["quality_report"] = _quality_report_payload(quality_report)

        # Emit completed event
        _push_progress(run_id, _make_progress_event(
            "genesis_completed", run_id,
            genesis_run=response_data,
        ))

    except Exception as e:
        logger.error("Genesis background generation failed for run %s: %s", run_id, str(e), exc_info=True)
        error_msg = str(e)[:500]
        repo.update_genesis_run(run_id, {
            "status": "failed",
            "error_message": error_msg,
        })
        _push_progress(run_id, _make_progress_event(
            "genesis_failed", run_id,
            error=error_msg,
        ))
    finally:
        # Clean up queue after a delay (allow final events to be consumed)
        await asyncio.sleep(5)
        remove_progress_queue(run_id)

@router.get("/projects/{project_id}/genesis/generate/stream/{run_id}")
async def stream_genesis_progress(
    request: Request,
    project_id: str,
    run_id: str,
):
    """SSE endpoint for real-time Genesis generation progress.

    v6.7.7: Streams progress events as text/event-stream.
    Pushes segment_started, segment_completed, chapter_start, chapter_end events,
    then genesis_completed or genesis_failed when done.
    """
    from novel_factory.api.deps import get_repo

    repo = get_repo(request)

    # Validate run exists and belongs to project
    genesis_run = repo.get_genesis_run(run_id)
    if not genesis_run:
        async def not_found_stream():
            yield f"event: genesis_failed\ndata: {json.dumps({'run_id': run_id, 'error': 'GENESIS_NOT_FOUND'})}\n\n"
        return StreamingResponse(not_found_stream(), media_type="text/event-stream")

    if genesis_run["project_id"] != project_id:
        async def mismatch_stream():
            yield f"event: genesis_failed\ndata: {json.dumps({'run_id': run_id, 'error': 'PROJECT_MISMATCH'})}\n\n"
        return StreamingResponse(mismatch_stream(), media_type="text/event-stream")

    # If already completed/failed, send final event immediately
    if genesis_run["status"] in ("generated", "completed"):
        quality_report = _quality_report_for_genesis(genesis_run, repo.get_project(project_id))
        response_data = dict(genesis_run)
        if quality_report is not None:
            response_data["quality_report"] = quality_report
        async def done_stream():
            yield f"event: genesis_completed\ndata: {json.dumps({'run_id': run_id, 'genesis_run': response_data}, ensure_ascii=False)}\n\n"
        return StreamingResponse(done_stream(), media_type="text/event-stream")

    if genesis_run["status"] == "failed":
        async def failed_stream():
            yield f"event: genesis_failed\ndata: {json.dumps({'run_id': run_id, 'error': genesis_run.get('error_message', 'Unknown error')}, ensure_ascii=False)}\n\n"
        return StreamingResponse(failed_stream(), media_type="text/event-stream")

    # For running status, the queue is the in-process producer contract.
    # If it is missing, the desktop sidecar or local API process was restarted
    # and no background task can still emit progress for this run.
    queue = get_progress_queue(run_id)
    if queue is None:
        # The task may have completed between the check above and now, re-check
        genesis_run = repo.get_genesis_run(run_id)
        if genesis_run and genesis_run["status"] != "running":
            # Re-route to done/failed
            if genesis_run["status"] in ("generated", "completed"):
                response_data = dict(genesis_run)
                async def done_stream2():
                    yield f"event: genesis_completed\ndata: {json.dumps({'run_id': run_id, 'genesis_run': response_data}, ensure_ascii=False)}\n\n"
                return StreamingResponse(done_stream2(), media_type="text/event-stream")
            else:
                async def failed_stream2():
                    yield f"event: genesis_failed\ndata: {json.dumps({'run_id': run_id, 'error': genesis_run.get('error_message', 'Unknown')}, ensure_ascii=False)}\n\n"
                return StreamingResponse(failed_stream2(), media_type="text/event-stream")

        if genesis_run and genesis_run["status"] == "running":
            genesis_run = _fail_orphaned_running_genesis(repo, genesis_run)
            async def orphaned_stream():
                yield f"event: genesis_failed\ndata: {json.dumps({'run_id': run_id, 'error': genesis_run.get('error_message', 'Unknown')}, ensure_ascii=False)}\n\n"
            return StreamingResponse(orphaned_stream(), media_type="text/event-stream")

        async def missing_stream():
            yield f"event: genesis_failed\ndata: {json.dumps({'run_id': run_id, 'error': 'GENESIS_NOT_FOUND'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(missing_stream(), media_type="text/event-stream")

    async def event_stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = event.get("event", "progress")
                    data = event.get("data", {})
                    yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    # If terminal event, stop
                    if event_type in ("genesis_completed", "genesis_failed"):
                        break
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
