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
from .coercer import (
    _coerce_world_setting,
    _coerce_character,
    _coerce_named_item,
    _coerce_outline,
    _coerce_plot_hole,
    _coerce_instruction,
    _normalize_character_role,
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

def _apply_genesis_to_project(repo, project_id: str, draft: dict, chapter_cleanup_mode: str | None = None) -> dict:
    """Apply an approved genesis draft to formal tables.

    v6.8.5: Added chapter_cleanup_mode for re-genesis protection.

    Args:
        repo: Repository instance.
        project_id: Project identifier.
        draft: Genesis draft data.
        chapter_cleanup_mode: How to handle existing chapters:
            - "keep_published": Keep published/reviewed/awaiting_publish, reset others
            - "reset_all": Reset ALL chapters including terminal ones
            - "delete_all": Delete ALL chapters
            - None: No chapter cleanup (default, preserves all chapters)

    Returns:
        A summary of what was applied.
    """
    if not isinstance(draft, dict):
        raise ValueError("创世草案必须是 JSON 对象")

    applied = {
        "project_updated": False,
        "context_replaced": False,
        "world_settings_deleted": 0,
        "characters_deleted": 0,
        "factions_deleted": 0,
        "outlines_deleted": 0,
        "plot_holes_deleted": 0,
        "instructions_deleted": 0,
        "story_facts_deleted": 0,
        "story_fact_events_deleted": 0,
        "memory_items_deleted": 0,
        "memory_batches_deleted": 0,
        "agent_memories_deleted": 0,
        "chapter_states_deleted": 0,
        "state_history_deleted": 0,
        "world_settings_created": 0,
        "characters_created": 0,
        "factions_created": 0,
        "outlines_created": 0,
        "plot_holes_created": 0,
        "instructions_created": 0,
    }

    has_prior_approved_genesis = any(
        run.get("status") == "approved" for run in repo.list_genesis_runs(project_id)
    )

    # v6.8.5: Chapter cleanup before applying new genesis
    chapter_cleanup_summary = {"mode": chapter_cleanup_mode, "chapters_affected": 0}
    if chapter_cleanup_mode:
        if chapter_cleanup_mode == "keep_published":
            # Keep published/reviewed/awaiting_publish, reset others to planned
            chapter_cleanup_summary["chapters_affected"] = repo.reset_non_terminal_chapters(project_id)
            # Reset current_chapter to 1
            repo.update_project(project_id, current_chapter=1)
            chapter_cleanup_summary["current_chapter_reset"] = True
        elif chapter_cleanup_mode == "reset_all":
            # Reset ALL chapters including terminal ones
            chapter_cleanup_summary["chapters_affected"] = repo.reset_all_chapters(project_id)
            repo.update_project(project_id, current_chapter=1)
            chapter_cleanup_summary["current_chapter_reset"] = True
        elif chapter_cleanup_mode == "delete_all":
            # Delete ALL chapters
            chapter_cleanup_summary["chapters_affected"] = repo.delete_all_chapters(project_id)
            repo.update_project(project_id, current_chapter=1)
            chapter_cleanup_summary["current_chapter_reset"] = True
        logger.info("Re-genesis chapter cleanup: %s", chapter_cleanup_summary)
    applied["chapter_cleanup"] = chapter_cleanup_summary

    applied["memory_items_deleted"] = repo.delete_memory_items_by_project(project_id)
    applied["memory_batches_deleted"] = repo.delete_memory_batches_by_project(project_id)
    applied["story_fact_events_deleted"] = repo.delete_fact_events_by_project(project_id)
    applied["story_facts_deleted"] = repo.delete_story_facts_by_project(project_id)
    applied["world_settings_deleted"] = repo.delete_world_settings_by_project(project_id)
    applied["characters_deleted"] = repo.delete_characters_by_project(project_id)
    applied["factions_deleted"] = repo.delete_factions_by_project(project_id)
    applied["outlines_deleted"] = repo.delete_outlines_by_project(project_id)
    applied["plot_holes_deleted"] = repo.delete_plot_holes_by_project(project_id)
    applied["instructions_deleted"] = repo.delete_instructions_by_project(project_id)
    if hasattr(repo, "delete_agent_memories_by_project"):
        applied["agent_memories_deleted"] = repo.delete_agent_memories_by_project(project_id)
    if hasattr(repo, "delete_chapter_states_by_project"):
        applied["chapter_states_deleted"] = repo.delete_chapter_states_by_project(project_id)
    if hasattr(repo, "delete_state_history_by_project"):
        applied["state_history_deleted"] = repo.delete_state_history_by_project(project_id)
    applied["context_replaced"] = has_prior_approved_genesis or any(
        applied[key] > 0
        for key in (
            "memory_items_deleted",
            "memory_batches_deleted",
            "story_fact_events_deleted",
            "story_facts_deleted",
            "world_settings_deleted",
            "characters_deleted",
            "factions_deleted",
            "outlines_deleted",
            "plot_holes_deleted",
            "instructions_deleted",
            "agent_memories_deleted",
            "chapter_states_deleted",
            "state_history_deleted",
        )
    )

    # Update project description
    project_updates = draft.get("project_updates", {})
    if not isinstance(project_updates, dict):
        project_updates = {"description": _as_text(project_updates)}
    if project_updates.get("description"):
        repo.update_project(project_id, description=project_updates["description"])
        applied["project_updated"] = True

    # World settings - upsert by title
    existing_ws = repo.list_world_settings(project_id)
    ws_by_title = {w["title"]: w for w in existing_ws}
    for idx, raw_ws in enumerate(_as_list(draft.get("world_settings", [])), start=1):
        ws = _coerce_world_setting(raw_ws, idx)
        if not ws:
            continue
        title = ws.get("title", "")
        if title in ws_by_title:
            repo.update_world_setting(project_id, ws_by_title[title]["id"], ws)
        else:
            repo.create_world_setting(
                project_id,
                category=ws.get("category", ""),
                title=title,
                content=ws.get("content", ""),
            )
            applied["world_settings_created"] += 1

    # Characters - upsert by name
    existing_chars = repo.list_characters(project_id)
    char_by_name = {c["name"]: c for c in existing_chars}
    for idx, raw_ch in enumerate(_as_list(draft.get("characters", [])), start=1):
        ch = _coerce_character(raw_ch, idx)
        if not ch:
            continue
        name = ch.get("name", "")
        char_data = {
            **ch,
            "role": _normalize_character_role(ch.get("role", "supporting")),
            "description": _as_text(ch.get("description", "")),
            "traits": _as_text(ch.get("traits", "")),
        }
        if name in char_by_name:
            repo.update_character(project_id, char_by_name[name]["id"], char_data)
        else:
            repo.create_character(
                project_id,
                name=name,
                role=char_data["role"],
                description=char_data["description"],
                traits=char_data["traits"],
            )
            applied["characters_created"] += 1

    # Factions - upsert by name
    existing_factions = repo.list_factions(project_id)
    fac_by_name = {f["name"]: f for f in existing_factions}
    for idx, raw_f in enumerate(_as_list(draft.get("factions", [])), start=1):
        f = _coerce_named_item(raw_f, idx, "势力")
        if not f:
            continue
        name = f.get("name", "")
        if name in fac_by_name:
            repo.update_faction(project_id, fac_by_name[name]["id"], f)
        else:
            repo.create_faction(
                project_id,
                name=name,
                type=f.get("type", ""),
                description=f.get("description", ""),
                relationship_with_protagonist=f.get("relationship_with_protagonist", ""),
            )
            applied["factions_created"] += 1

    # Outlines - upsert by (level, sequence)
    existing_outlines = repo.list_outlines(project_id)
    outline_by_key = {(o.get("level", ""), o.get("sequence", 0)): o for o in existing_outlines}
    for idx, raw_o in enumerate(_as_list(draft.get("outlines", [])), start=1):
        o = _coerce_outline(raw_o, idx)
        if not o:
            continue
        key = (o.get("level", "arc"), o.get("sequence", 0))
        if key in outline_by_key:
            repo.update_outline(project_id, outline_by_key[key]["id"], o)
        else:
            repo.create_outline(
                project_id,
                level=o.get("level", "arc"),
                sequence=o.get("sequence", 1),
                title=o.get("title", ""),
                content=o.get("content", ""),
                chapters_range=o.get("chapters_range", ""),
            )
            applied["outlines_created"] += 1

    # Plot holes - upsert by code
    existing_phs = repo.list_plot_holes(project_id)
    ph_by_code = {p["code"]: p for p in existing_phs if p.get("code")}
    for idx, raw_ph in enumerate(_as_list(draft.get("plot_holes", [])), start=1):
        ph = _coerce_plot_hole(raw_ph, idx)
        if not ph:
            continue
        code = ph.get("code", "")
        plot_data = {
            **ph,
            "type": _as_text(ph.get("type", "")),
            "title": _as_text(ph.get("title", "")),
            "description": _as_text(ph.get("description", "")),
            "status": _normalize_plot_status(ph.get("status", "planted")),
        }
        if code in ph_by_code:
            repo.update_plot_hole(project_id, ph_by_code[code]["id"], plot_data)
        else:
            repo.create_plot_hole(
                project_id,
                code=code,
                type=plot_data["type"],
                title=plot_data["title"],
                description=plot_data["description"],
                planted_chapter=plot_data.get("planted_chapter"),
                planned_resolve_chapter=plot_data.get("planned_resolve_chapter"),
                status=plot_data["status"],
            )
            applied["plot_holes_created"] += 1

    # Instructions - upsert by chapter_number
    for idx, raw_inst in enumerate(_as_list(draft.get("instructions", [])), start=1):
        inst = _coerce_instruction(raw_inst, idx)
        if not inst:
            continue
        ch_num = inst.get("chapter_number")
        if ch_num is None:
            continue
        # v6.6.4: Merge ending_hook/continuity_seed into key_events/emotion_tone if DB lacks columns
        objective = _as_text(inst.get("objective", ""))
        key_events = _as_text(inst.get("key_events", ""))
        emotion_tone = _as_text(inst.get("emotion_tone", ""))
        ending_hook = _as_text(inst.get("ending_hook", ""))
        continuity_seed = _as_text(inst.get("continuity_seed", ""))
        contract_details = _format_instruction_contract_details(inst)
        if contract_details and contract_details not in key_events:
            key_events = f"{key_events}\n{contract_details}".strip()
        if ending_hook and ending_hook not in key_events:
            key_events = f"{key_events}\n结尾钩子: {ending_hook}".strip()
        if continuity_seed and continuity_seed not in emotion_tone:
            emotion_tone = f"{emotion_tone}\n继承点: {continuity_seed}".strip()
        instruction_data = {
            **inst,
            "objective": objective,
            "key_events": key_events,
            "emotion_tone": emotion_tone,
        }
        existing_inst = repo.get_instruction_by_chapter(project_id, ch_num)
        if existing_inst:
            repo.update_instruction(project_id, existing_inst["id"], instruction_data)
        else:
            repo.create_instruction(
                project_id,
                chapter_number=ch_num,
                objective=instruction_data["objective"],
                key_events=instruction_data["key_events"],
                emotion_tone=instruction_data["emotion_tone"],
                word_target=instruction_data.get("word_target"),
            )
            applied["instructions_created"] += 1

    return applied

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
