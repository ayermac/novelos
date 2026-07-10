"""Genesis API endpoints for project bible generation."""

from __future__ import annotations

import json
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ...exceptions import APIValidationError
from ...agent_runtime.title_contract import build_title_contract
from ...llm.provider import is_configured_live_provider
from ...quality.genesis_quality_gate import evaluate_genesis_draft
from ...validators.chapter_checker import DEFAULT_INSTRUCTION_WORD_TARGET

router = APIRouter()
logger = logging.getLogger(__name__)


GENESIS_RUNNING_TIMEOUT_MINUTES = 30

# ---------------------------------------------------------------------------
# v6.7.7: Genesis progress streaming — in-memory progress store
# ---------------------------------------------------------------------------

# Maps run_id -> asyncio.Queue for SSE streaming
_genesis_progress_queues: dict[str, asyncio.Queue] = {}

# Segment display names for UI
GENESIS_SEGMENT_LABELS = {
    "foundation": "正在生成基础设定",
    "cast": "正在生成角色与势力",
    "plot": "正在生成剧情大纲",
    "instructions": "正在生成章节指令",
    "repair": "正在校验设定完整性",
    "quality_report": "正在评估草案质量",
}


def _push_progress(run_id: str, event: dict) -> None:
    """Push a progress event to the SSE queue for a given run."""
    queue = _genesis_progress_queues.get(run_id)
    if queue is not None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Genesis progress queue full for run %s, dropping event", run_id)


def _make_progress_event(event_type: str, run_id: str, **kwargs) -> dict:
    """Build a standard progress event dict."""
    evt = {"event": event_type, "data": {"run_id": run_id, **kwargs}}
    return evt


# Type alias for progress callback
ProgressCallback = "Callable[[str, dict], None] | None"


GENESIS_REQUIRED_SECTIONS = {
    "project_description": "项目简介",
    "world_settings": "世界观设定",
    "characters": "角色",
    "factions": "势力/组织",
    "outlines": "大纲",
    "plot_holes": "伏笔/悬念",
    "instructions": "章节指令",
}

GENESIS_SEGMENT_MAX_TOKENS = {
    "foundation": 2400,
    "cast": 3000,
    "plot": 3200,
}
GENESIS_INSTRUCTION_CHUNK_SIZE = 5
GENESIS_REPAIRABLE_INSTRUCTION_CODES = {
    "ABSTRACT_OBJECTIVE",
    "GENERIC_INSTRUCTIONS",
    "MISSING_CONTINUITY_SEED",
    "REPETITIVE_KEY_EVENTS",
    "REPETITIVE_OBJECTIVE",
    "SHALLOW_INSTRUCTION",
    "WEAK_KEY_EVENTS",
}


class GenesisGenerateRequest(BaseModel):
    """Input for project genesis generation."""

    project_id: str = ""
    title: str = ""
    genre: str = ""
    premise: str = ""
    target_chapters: int = 10
    target_words: int = 30000
    target_audience: str = ""
    style_preference: str = ""
    constraints: str = ""


class GenesisApproveRequest(BaseModel):
    """Canonical body for genesis approve action."""

    project_id: str
    genesis_id: str


class GenesisRejectRequest(BaseModel):
    """Canonical body for genesis reject action."""

    project_id: str
    genesis_id: str


class GenesisApproveWithForceRequest(BaseModel):
    """Canonical body for genesis approve with optional force flag."""

    project_id: str
    genesis_id: str
    force_apply: bool = False
    confirm_quality_risk: bool = False
    # v6.8.5: Chapter cleanup mode for re-genesis
    chapter_cleanup_mode: str | None = None


class GenesisForceApplyBody(BaseModel):
    """Body for path-style approve route with optional force flag."""

    force_apply: bool = False
    confirm_quality_risk: bool = False
    # v6.8.5: Chapter cleanup mode for re-genesis
    # "keep_published" - Keep published/reviewed/awaiting_publish chapters, reset others
    # "reset_all" - Reset ALL chapters including terminal ones
    # "delete_all" - Delete ALL chapters
    # None - No chapter cleanup (default, preserves all chapters)
    chapter_cleanup_mode: str | None = None


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


def _generate_stub_draft(
    body: GenesisGenerateRequest,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Generate a deterministic stub genesis draft.

    v6.7.7: Accepts optional progress callback for SSE streaming.
    In stub mode, simulates realistic progress events with short delays.
    """
    import time

    title = body.title or "未命名项目"
    genre = body.genre or "奇幻"
    premise = body.premise or "一个关于冒险与成长的故事"

    def _emit(event_type: str, **kwargs):
        if progress and run_id:
            progress(event_type, {"run_id": run_id, **kwargs})

    # Stub: simulate foundation segment
    _emit("segment_started", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])
    time.sleep(0.05)  # simulate work

    draft: dict = {
        "project_updates": {
            "description": f"《{title}》是一部{genre}题材小说。{premise}",
        },
        "world_settings": [
            {
                "title": "世界观基础",
                "category": "地理",
                "content": f"故事发生在{genre}世界中，存在多个势力和未知领域。",
            },
            {
                "title": "力量体系",
                "category": "规则",
                "content": "修炼体系分为九个大境界，每个境界有初期、中期、后期三个小阶段。",
            },
        ],
    }
    _emit("segment_completed", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])

    # Stub: simulate cast segment
    _emit("segment_started", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])
    time.sleep(0.05)

    draft["characters"] = [
        {
            "name": "主角",
            "role": "protagonist",
            "description": f"《{title}》的核心人物，性格坚毅，有着不为人知的过去。",
            "traits": "聪明、执着、重情义",
        },
        {
            "name": "挚友",
            "role": "supporting",
            "description": "主角的青梅竹马，性格开朗，擅长情报收集。",
            "traits": "机智、幽默、忠诚",
        },
        {
            "name": "反派首领",
            "role": "antagonist",
            "description": "幕后黑手，行事隐秘，目的不明。",
            "traits": "狡猾、冷酷、有魅力",
        },
    ]
    draft["factions"] = [
        {
            "name": "主角所属势力",
            "type": "宗门",
            "description": "主角成长的根据地，历史悠久但近来衰落。",
            "relationship_with_protagonist": "所属",
        },
        {
            "name": "敌对势力",
            "type": "组织",
            "description": "暗中操控局势的神秘组织。",
            "relationship_with_protagonist": "敌对",
        },
    ]
    _emit("segment_completed", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])

    # Stub: simulate plot segment
    _emit("segment_started", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])
    time.sleep(0.05)

    draft["outlines"] = [
        {
            "chapters_range": "1-3",
            "title": "开篇",
            "content": "主角出场，建立日常世界，引出核心冲突。",
            "level": "arc",
            "sequence": 1,
        },
        {
            "chapters_range": "4-6",
            "title": "启程",
            "content": "主角踏上旅程，遇到第一个挑战和盟友。",
            "level": "arc",
            "sequence": 2,
        },
        {
            "chapters_range": "7-10",
            "title": "第一幕高潮",
            "content": "主角面对第一个重大考验，揭示更大的阴谋。",
            "level": "arc",
            "sequence": 3,
        },
    ]
    draft["plot_holes"] = [
        {
            "code": "PH-001",
            "type": "悬念",
            "title": "主角身世之谜",
            "description": "主角的真实身份和家族秘密。",
            "planted_chapter": 1,
            "planned_resolve_chapter": 20,
            "status": "planted",
        },
        {
            "code": "PH-002",
            "type": "伏笔",
            "title": "神秘信物",
            "description": "主角随身携带的古旧物品的来历。",
            "planted_chapter": 1,
            "planned_resolve_chapter": 10,
            "status": "planted",
        },
    ]
    _emit("segment_completed", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])

    # Stub: simulate instructions segment (per-chunk)
    chapter_count = min(body.target_chapters, 10)
    chunk_size = GENESIS_INSTRUCTION_CHUNK_SIZE
    instructions: list = []
    for chunk_start in range(0, chapter_count, chunk_size):
        chunk_end = min(chapter_count, chunk_start + chunk_size)
        _emit("chapter_start", chapter_start=chunk_start + 1, chapter_end=chunk_end,
              label=f"正在生成章节指令 {chunk_start + 1}-{chunk_end}")
        time.sleep(0.03)
        for i in range(chunk_start, chunk_end):
            instructions.append({
                "chapter_number": i + 1,
                "objective": f"第 {i + 1} 章写作指令",
                "key_events": f"关键事件 {i + 1}",
                "emotion_tone": "神秘" if i == 0 else "紧张",
                "word_target": body.target_words // body.target_chapters,
            })
        _emit("chapter_end", chapter_start=chunk_start + 1, chapter_end=chunk_end,
              label=f"章节指令 {chunk_start + 1}-{chunk_end} 完成")
    draft["instructions"] = instructions

    return draft


def _as_text(value) -> str:
    """Normalize LLM scalar/list/dict output into DB-safe text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _as_list(value) -> list:
    """Normalize free-form LLM list output into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_int(value, fallback: int) -> int:
    """Normalize LLM numeric fields into an int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_genesis_draft(value) -> dict | None:
    """Normalize provider draft output into the canonical genesis object shape."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return None

    grouped = {
        "world_settings": [],
        "characters": [],
        "factions": [],
        "outlines": [],
        "plot_holes": [],
        "instructions": [],
    }
    for item in value:
        if not isinstance(item, dict):
            continue
        keys = set(item.keys())
        if {"title", "category", "content"} <= keys:
            grouped["world_settings"].append(item)
        elif "chapter_number" in keys:
            grouped["instructions"].append(item)
        elif "chapters_range" in keys or {"level", "sequence", "content"} <= keys:
            grouped["outlines"].append(item)
        elif "code" in keys:
            grouped["plot_holes"].append(item)
        elif "relationship_with_protagonist" in keys or ("name" in keys and "type" in keys):
            grouped["factions"].append(item)
        elif "name" in keys:
            grouped["characters"].append(item)

    normalized = {key: items for key, items in grouped.items() if items}
    return normalized or None


def _merge_key_text(value) -> str:
    """Normalize text for Genesis merge/dedup keys."""
    return " ".join(_as_text(value).split()).strip().lower()


def _world_setting_semantic_key(item: dict) -> str | None:
    """Collapse common Genesis worldbuilding duplicates into stable slots."""
    title = _as_text(item.get("title"))
    text = f"{title} {_as_text(item.get('category'))} {_as_text(item.get('content'))}"

    if "异常" in title and any(term in title for term in ("定义", "分类", "起源")):
        return "anomaly_definition"
    if "异常" in title and any(term in title for term in ("规律", "进化", "目的", "深层")):
        return "anomaly_pattern"
    if "异常处理局" in text or "国家异常事态处理局" in text:
        return "anomaly_bureau"
    if "修正系统" in text or "裁衡" in text:
        return "correction_system"
    if "同化" in title:
        return "assimilation"
    if "修正员" in title and any(term in title for term in ("等级", "能力", "体系")):
        return "corrector_capability"
    if "2056" in title or "世界" in title or "时代" in title or "社会" in title:
        return "era_background"
    return None


def _genesis_item_key(section: str, item, index: int) -> str:
    """Return a stable semantic key for a Genesis list item."""
    if not isinstance(item, dict):
        return f"raw:{index}:{_merge_key_text(item)[:80]}"

    if section == "world_settings":
        semantic_key = _world_setting_semantic_key(item)
        if semantic_key:
            return f"world:{semantic_key}"
        title = _merge_key_text(item.get("title"))
        category = _merge_key_text(item.get("category"))
        content = _merge_key_text(item.get("content"))
        return f"title:{category}:{title}" if title else f"content:{content[:100]}"

    if section in ("characters", "factions"):
        name = _merge_key_text(item.get("name"))
        return f"name:{name}" if name else f"idx:{index}"

    if section == "outlines":
        level = _merge_key_text(item.get("level", "arc"))
        sequence = item.get("sequence")
        if sequence not in (None, ""):
            return f"seq:{level}:{sequence}"
        chapters_range = _merge_key_text(item.get("chapters_range"))
        if chapters_range:
            return f"range:{chapters_range}"
        return f"title:{_merge_key_text(item.get('title'))}"

    if section == "plot_holes":
        code = _merge_key_text(item.get("code"))
        if code:
            return f"code:{code}"
        return f"title:{_merge_key_text(item.get('title'))}"

    if section == "instructions":
        chapter_number = item.get("chapter_number")
        if chapter_number not in (None, ""):
            try:
                return f"chapter:{int(chapter_number)}"
            except (TypeError, ValueError):
                return f"chapter:{_merge_key_text(chapter_number)}"
        return f"objective:{_merge_key_text(item.get('objective'))}"

    return f"idx:{index}"


def _merge_genesis_item(existing, incoming):
    """Merge duplicate Genesis items without letting empty incoming values erase data."""
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return incoming if incoming not in (None, "", [], {}) else existing
    merged = dict(existing)
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def _merge_unique_genesis_list(existing: list, incoming: list, section: str) -> list:
    """Merge Genesis list sections by semantic keys instead of blindly appending."""
    result: list = []
    key_to_index: dict[str, int] = {}

    for source in (existing or [], incoming or []):
        for item in source:
            key = _genesis_item_key(section, item, len(result) + 1)
            if key in key_to_index:
                idx = key_to_index[key]
                result[idx] = _merge_genesis_item(result[idx], item)
            else:
                key_to_index[key] = len(result)
                result.append(item)
    return result


def _dedupe_genesis_draft(draft: dict | None) -> dict | None:
    """Deduplicate all repeatable Genesis sections in a normalized draft."""
    if not isinstance(draft, dict):
        return draft
    deduped = dict(draft)
    for key in (
        "world_settings",
        "characters",
        "factions",
        "outlines",
        "plot_holes",
        "instructions",
    ):
        value = deduped.get(key)
        if isinstance(value, list):
            deduped[key] = _merge_unique_genesis_list([], value, key)
    return deduped


def _parse_genesis_draft_json(raw_value) -> dict | None:
    """Parse genesis draft_json into a JSON object.

    Historical/real-provider failures can leave draft_json double-encoded or
    shaped as a JSON string/list. Approval must reject those cleanly instead of
    failing later with "'str' object has no attribute 'get'" after partial work.
    """
    value = raw_value
    for _ in range(2):
        normalized = _normalize_genesis_draft(value)
        if normalized is not None:
            return _dedupe_genesis_draft(normalized)
        if isinstance(value, str):
            try:
                value = json.loads(value)
                continue
            except json.JSONDecodeError:
                return None
        return None
    return _dedupe_genesis_draft(_normalize_genesis_draft(value))


def _missing_required_genesis_sections(draft: dict | None) -> list[str]:
    """Return required genesis sections that are absent or empty."""
    if not isinstance(draft, dict):
        return list(GENESIS_REQUIRED_SECTIONS.values())
    missing: list[str] = []
    project_updates = draft.get("project_updates")
    description = ""
    if isinstance(project_updates, dict):
        description = _as_text(project_updates.get("description", "")).strip()
    else:
        description = _as_text(project_updates).strip()
    if not description:
        missing.append(GENESIS_REQUIRED_SECTIONS["project_description"])
    for key, label in GENESIS_REQUIRED_SECTIONS.items():
        if key == "project_description":
            continue
        value = draft.get(key)
        if isinstance(value, list) and value:
            continue
        if value and not isinstance(value, list):
            continue
        missing.append(label)
    return missing


def _validate_complete_genesis_draft(draft: dict | None) -> tuple[dict | None, list[str]]:
    """Normalize and validate that a generated draft can initialize a project."""
    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft))
    missing = _missing_required_genesis_sections(normalized)
    return normalized, missing


def _incomplete_genesis_message(missing: list[str]) -> str:
    return f"创世草案不完整，缺少：{', '.join(missing)}。请拒绝当前草案后重新生成。"


def _merge_genesis_drafts(base: dict | None, patch: dict | None) -> dict:
    """Merge a missing-section patch into a genesis draft."""
    merged = dict(base or {})
    patch = patch or {}
    if not isinstance(patch, dict):
        return merged

    project_updates = patch.get("project_updates")
    if isinstance(project_updates, dict) and project_updates:
        merged_project = dict(merged.get("project_updates") or {})
        merged_project.update(project_updates)
        merged["project_updates"] = merged_project

    for key in (
        "world_settings",
        "characters",
        "factions",
        "outlines",
        "plot_holes",
        "instructions",
    ):
        incoming = patch.get(key)
        if isinstance(incoming, list) and incoming:
            merged[key] = _merge_unique_genesis_list(merged.get(key) or [], incoming, key)
        elif key not in merged:
            merged[key] = []

    return _dedupe_genesis_draft(merged) or {}


def _project_description_from_body(body: GenesisGenerateRequest) -> str:
    """Build a project description when the provider omits project_updates."""
    title = body.title.strip() or "未命名项目"
    genre = body.genre.strip() or "小说"
    premise = body.premise.strip()
    if premise:
        return f"《{title}》是一部{genre}题材长篇小说。{premise}"
    return f"《{title}》是一部{genre}题材长篇小说，围绕主角的成长、冲突升级和核心谜团展开。"


def _target_word_count(body: GenesisGenerateRequest) -> int:
    chapters = max(body.target_chapters, 1)
    return max(body.target_words // chapters, 1500)


def _infer_protagonist_name(body: GenesisGenerateRequest) -> str:
    """Infer a concrete protagonist name from user input when possible."""
    source = f"{body.title} {body.premise}"
    patterns = [
        r"([\u4e00-\u9fff]{2,4})作为",
        r"主角[：:，,]?\s*([\u4e00-\u9fff]{2,4})",
    ]
    generic = {
        "故事",
        "异常",
        "系统",
        "现实",
        "修正",
        "修正员",
        "处理局",
        "普通人",
        "政府",
        "地球",
    }
    for pattern in patterns:
        for match in re.finditer(pattern, source):
            name = match.group(1).strip()
            if name and name not in generic and len(name) <= 4:
                return name
    return "林泽" if "异常" in source or "修正" in source else "沈砚"


def _is_anomaly_genesis(body: GenesisGenerateRequest) -> bool:
    source = f"{body.title} {body.genre} {body.premise}"
    return any(token in source for token in ("异常", "修正员", "异常处理局", "超自然", "灵异"))


def _genre_terms(body: GenesisGenerateRequest) -> dict[str, str]:
    """Return lightweight genre-aware labels for deterministic fallback drafts."""
    text = f"{body.genre} {body.title} {body.premise}".lower()
    if any(token in text for token in ("xianxia", "玄幻", "仙侠", "修仙", "仙帝")):
        return {
            "power": "修炼体系",
            "setting": "修行世界与凡俗秩序并存，力量、资源和势力共同决定人物命运。",
            "resource": "灵气、功法、丹药、秘境和传承",
            "conflict": "宗门、家族、隐秘组织与主角成长路线之间的冲突",
            "tone": "热血、逆袭、压迫后的爆发",
        }
    if any(token in text for token in ("urban", "都市", "科技", "机甲")):
        return {
            "power": "都市能力体系",
            "setting": "现代都市表层秩序下隐藏着技术、资本和特殊力量的暗线博弈。",
            "resource": "技术资源、资本、人脉和关键情报",
            "conflict": "校园、财阀、官方机构与地下势力围绕主角能力展开争夺",
            "tone": "爽感、成长、现实压迫下的反击",
        }
    if any(token in text for token in ("sci", "科幻", "未来")):
        return {
            "power": "科技规则体系",
            "setting": "未来科技社会中，资源、算法、组织权力和未知技术共同推动冲突。",
            "resource": "核心技术、数据、能源和实验设施",
            "conflict": "科研机构、企业、官方力量与未知威胁之间的争夺",
            "tone": "探索、危机、理性推演后的震撼",
        }
    return {
        "power": "核心成长体系",
        "setting": "故事世界由日常秩序、隐藏规则和持续升级的外部冲突构成。",
        "resource": "资源、情报、盟友和关键机会",
        "conflict": "主角目标与反派、组织、环境压力之间的持续冲突",
        "tone": "成长、悬念、冲突升级",
    }


def _scaffold_seed_items(seed_draft: dict | None, section: str) -> list[dict]:
    if not isinstance(seed_draft, dict):
        return []
    value = seed_draft.get(section)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _clean_scaffold_entity_name(value: str, fallback: str) -> str:
    name = _as_text(value).strip()
    generic = {
        "",
        "主角",
        "男主",
        "女主",
        "本章主角",
        "角色",
        "反派",
        "配角",
        "未知",
        "无",
    }
    return name if name not in generic and len(name) <= 12 else fallback


def _pick_seed_character(
    characters: list[dict],
    *,
    role_terms: tuple[str, ...],
    fallback: str,
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()
    for item in characters:
        role_text = _as_text(item.get("role", "")).lower()
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if not name or name in exclude:
            continue
        if any(term in role_text for term in role_terms):
            return name
    for item in characters:
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if name and name not in exclude:
            return name
    return fallback


def _pick_seed_faction(
    factions: list[dict],
    *,
    preferred_terms: tuple[str, ...],
    fallback: str,
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()
    for item in factions:
        text = " ".join(
            _as_text(item.get(key, ""))
            for key in ("name", "type", "description", "relationship_with_protagonist")
        )
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if name and name not in exclude and any(term in text for term in preferred_terms):
            return name
    for item in factions:
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if name and name not in exclude:
            return name
    return fallback


def _detect_scaffold_story_mode(body: GenesisGenerateRequest, seed_draft: dict | None) -> str:
    seed_text = ""
    if isinstance(seed_draft, dict):
        seed_text = json.dumps(seed_draft, ensure_ascii=False)[:12000]
    text = f"{body.title} {body.genre} {body.premise} {seed_text}"
    if any(term in text for term in ("召唤", "神军", "战灵", "异兽潮", "觉醒者", "职业评级")):
        return "urban_summon"
    if any(term in text for term in ("签到", "打卡", "奖励", "返现", "系统奖励")):
        return "urban_signin"
    if _is_anomaly_genesis(body) or any(term in text for term in ("异常处理", "修正系统", "同化")):
        return "anomaly"
    if any(term in text for term in ("修仙", "宗门", "灵根", "仙帝", "玄幻")):
        return "xianxia"
    return "generic"


def _default_scaffold_entities(
    body: GenesisGenerateRequest,
    seed_draft: dict | None,
) -> dict[str, str]:
    mode = _detect_scaffold_story_mode(body, seed_draft)
    characters = _scaffold_seed_items(seed_draft, "characters")
    factions = _scaffold_seed_items(seed_draft, "factions")

    mode_defaults = {
        "urban_summon": {
            "protagonist": "陆沉",
            "ally": "林破军",
            "second_ally": "苏晚晴",
            "antagonist": "赵天罡",
            "observer": "军方观察员",
            "primary_faction": "江海市城防军",
            "rival_faction": "赵家",
            "hidden_faction": "深渊黑潮",
            "neutral_faction": "觉醒者协会",
        },
        "urban_signin": {
            "protagonist": "林辰",
            "ally": "秦伯",
            "second_ally": "苏晚晴",
            "antagonist": "赵天朗",
            "observer": "帝豪经理",
            "primary_faction": "帝豪酒店",
            "rival_faction": "赵家",
            "hidden_faction": "猩红之夜",
            "neutral_faction": "江城商会",
        },
        "anomaly": {
            "protagonist": "林泽",
            "ally": "许知夏",
            "second_ally": "顾清禾",
            "antagonist": "魏承霜",
            "observer": "周砚白",
            "primary_faction": "异常处理局深城分部",
            "rival_faction": "监管组第七办公室",
            "hidden_faction": "白塔观测会",
            "neutral_faction": "旧城区互助网络",
        },
        "xianxia": {
            "protagonist": "沈砚",
            "ally": "洛青辞",
            "second_ally": "白迟",
            "antagonist": "陆怀川",
            "observer": "藏经阁守阁人",
            "primary_faction": "青云宗",
            "rival_faction": "陆家",
            "hidden_faction": "上古秘境",
            "neutral_faction": "万宝楼",
        },
        "generic": {
            "protagonist": _infer_protagonist_name(body),
            "ally": "顾清禾",
            "second_ally": "林越",
            "antagonist": "陆怀川",
            "observer": "闻人述",
            "primary_faction": "主线组织",
            "rival_faction": "敌对势力",
            "hidden_faction": "隐藏势力",
            "neutral_faction": "中立情报方",
        },
    }
    defaults = mode_defaults[mode]
    protagonist = _pick_seed_character(
        characters,
        role_terms=("protagonist", "主角", "男主", "女主"),
        fallback=defaults["protagonist"],
    )
    antagonist = _pick_seed_character(
        characters,
        role_terms=("antagonist", "反派", "敌"),
        fallback=defaults["antagonist"],
        exclude={protagonist},
    )
    ally = _pick_seed_character(
        characters,
        role_terms=("supporting", "配角", "盟友", "support"),
        fallback=defaults["ally"],
        exclude={protagonist, antagonist},
    )
    second_ally = _pick_seed_character(
        characters,
        role_terms=("supporting", "配角", "盟友", "support"),
        fallback=defaults["second_ally"],
        exclude={protagonist, antagonist, ally},
    )

    primary_faction = _pick_seed_faction(
        factions,
        preferred_terms=("军", "官方", "学院", "大学", "协会", "宗门", "集团", "酒店", "主角"),
        fallback=defaults["primary_faction"],
    )
    rival_faction = _pick_seed_faction(
        factions,
        preferred_terms=("敌", "对立", "豪门", "赵家", "陆家", "监管", "黑市", "反派"),
        fallback=defaults["rival_faction"],
        exclude={primary_faction},
    )
    hidden_faction = _pick_seed_faction(
        factions,
        preferred_terms=("深渊", "黑潮", "裂缝", "隐藏", "神秘", "异界", "白塔", "黑市", "幕后"),
        fallback=defaults["hidden_faction"],
        exclude={primary_faction, rival_faction},
    )
    neutral_faction = _pick_seed_faction(
        factions,
        preferred_terms=("协会", "大学", "商会", "情报", "中立", "互助", "医疗"),
        fallback=defaults["neutral_faction"],
        exclude={primary_faction, rival_faction, hidden_faction},
    )

    return {
        "mode": mode,
        "protagonist": protagonist,
        "ally": ally,
        "second_ally": second_ally,
        "antagonist": antagonist,
        "observer": defaults["observer"],
        "primary_faction": primary_faction,
        "rival_faction": rival_faction,
        "hidden_faction": hidden_faction,
        "neutral_faction": neutral_faction,
    }


def _build_scaffold_instruction_templates(
    mode: str,
    entities: dict[str, str],
) -> list[tuple[str, str, str, str, str, list[str], str, str]]:
    protagonist = entities["protagonist"]
    ally = entities["ally"]
    second_ally = entities["second_ally"]
    antagonist = entities["antagonist"]
    observer = entities["observer"]
    primary_faction = entities["primary_faction"]
    rival_faction = entities["rival_faction"]
    hidden_faction = entities["hidden_faction"]
    neutral_faction = entities["neutral_faction"]

    if mode == "urban_summon":
        return [
            (
                f"{protagonist}在觉醒日公开验证F级召唤师评级，必须保住母亲遗物并证明自己不是家族废物",
                "江海大学觉醒广场",
                f"{rival_faction}与{antagonist}的当众羞辱",
                f"{protagonist}被判定只能召唤灰铁战灵；{antagonist}推动退学和逐出家族；母亲古戒在精神力崩溃时激活帝皇序列",
                f"{protagonist}召出第一名灰铁战灵并挡下雷系压迫，F级废柴标签第一次被撕开裂缝",
                [f"{protagonist}完成觉醒仪式", f"{antagonist}当众打压召唤师评级", f"青铜古戒激活第一名灰铁战灵"],
                "灰铁战灵单膝跪地称王，检测屏却显示召唤位仍为零",
                "下一章必须解释召唤位异常，并让校园评级规则继续压迫主角",
            ),
            (
                f"{protagonist}在实战课测试召唤位异常，目标是用低阶战灵打破召唤师只能当后勤的结论",
                "江海大学实战训练场",
                "导师评级体系和高阶学生围观施压",
                f"{ally}观察战灵队列稳定性；{protagonist}让十名灰铁战灵完成盾墙、突刺、轮换；高阶学生强行挑战并被军阵压制",
                "学院数据库记录到异常统御波形，召唤师评级从个人废柴转为制度争议",
                [f"{protagonist}测试十名战灵同步行动", f"{ally}发现精神负荷没有上升", "战灵军阵击退高阶学生挑战"],
                "训练场后台弹出一条被封存的军团召唤路径",
                "下一章必须围绕军团召唤路径和协会注册资格展开",
            ),
            (
                f"{protagonist}申请觉醒者协会注册，必须在制度刁难下拿到独立接任务资格",
                f"{neutral_faction}评级大厅",
                f"{neutral_faction}的F级召唤师限制条款",
                f"评级员拒绝给{protagonist}前线资格；{second_ally}用治疗增幅短暂强化战灵；城门裂缝警报打断注册流程",
                f"{protagonist}以临时征召身份奔赴城门，获得第一次公开战场验证机会",
                [f"{protagonist}提交注册申请", f"{second_ally}证明治疗术可增幅召唤物", "城门裂缝警报迫使协会临时放行"],
                "城门外传来兽潮预警，后勤名单上只有陆沉一个召唤师",
                "下一章必须让主角在真实兽潮里兑现军团价值",
            ),
            (
                f"{protagonist}在东海城门兽潮中救下被围连队，目标是证明量产战灵能改变战场数量劣势",
                "东海城门外防线",
                f"{hidden_faction}先遣兽潮与军方旧战法",
                f"{primary_faction}连队被异兽切断；{protagonist}召出百名灰铁战灵组成三层盾枪阵；{ally}确认战损后战灵可重组",
                f"{primary_faction}把{protagonist}列为特殊统帅型觉醒者，豪门开始意识到威胁",
                [f"{protagonist}抵达城门防线", "百名灰铁战灵组成盾枪阵", f"{ally}救下被围连队并提交军报"],
                "军报备注写着：一人成军雏形，建议封存",
                "下一章必须让豪门势力因军报介入并制造资源封锁",
            ),
            (
                f"{protagonist}面对豪门资源封锁，目标是夺回召唤材料并建立第一处军团锚点",
                f"{rival_faction}控制的材料仓库",
                f"{rival_faction}的合同陷阱和私军拦截",
                f"{antagonist}冻结{protagonist}采购权限；{protagonist}带战灵潜入材料仓库查账；他用战功授权反向扣押一批灰铁核心",
                "第一座临时兵营锚点完成，战灵数量上限从百名提升到千名",
                [f"{antagonist}冻结召唤材料渠道", f"{protagonist}查出材料被豪门截留", "战功授权帮助主角建立临时兵营锚点"],
                "兵营锚点深处出现母亲留下的帝皇序列第二条命令",
                "下一章必须解锁千人军阵，并把压力转回城防战场",
            ),
            (
                f"{protagonist}用千人军阵迎击第二波裂缝兽潮，目标是让城防军承认军团召唤的战略价值",
                "东海二号裂缝前沿",
                f"{hidden_faction}的淹没式兽潮",
                f"常规高阶觉醒者被数量压制；{protagonist}把千名战灵拆成盾、枪、弓三阵；{ally}用军方炮火配合战灵轮换推进",
                f"裂缝前沿被夺回，{protagonist}获得军方临时指挥权限",
                ["高阶觉醒者防线被冲散", f"{protagonist}部署千人三阵", f"{primary_faction}授予临时指挥权限"],
                "裂缝深处传来能让战灵集体失控的号角声",
                "下一章必须处理战灵失控风险，并让后勤核心发挥作用",
            ),
            (
                f"{protagonist}处理战灵失控风险，目标是借助治疗增幅稳定军团意志",
                "战地医疗营",
                "异界号角和召唤反噬质疑",
                f"{second_ally}发现治疗术能修复战灵锚点；{protagonist}让失控战灵撤入医疗阵；{antagonist}借机指控军团召唤不可控",
                "生命增幅与军团锚点建立协同，主角阵营形成前线后勤闭环",
                [f"{second_ally}测试治疗术增幅战灵", f"{protagonist}压住失控战灵", f"{antagonist}发起不可控指控"],
                "治疗阵短暂照出一名黄金战灵的影子",
                "下一章必须追查黄金战灵来源，并揭露异界渗透",
            ),
            (
                f"{protagonist}追查黄金战灵影子，目标是找出城内谁在给兽潮传递军团情报",
                "城内黑市与裂缝物资站",
                f"{hidden_faction}潜伏者和{rival_faction}利益链",
                f"{protagonist}跟踪异常材料流向黑市；{ally}截获加密军报；潜伏者释放腐蚀瘴气试图污染战灵锚点",
                f"主角确认兽潮不是随机爆发，而是有人按城防弱点引导",
                [f"{protagonist}进入黑市追查材料", f"{ally}截获被篡改军报", "潜伏者用腐蚀瘴气攻击兵营锚点"],
                "被抓潜伏者临死前说出第七次黑潮已经进城",
                "下一章必须让主角在制度审查中公开部分证据",
            ),
            (
                f"{protagonist}在联合审查会上公开兽潮渗透证据，目标是打破召唤师后勤化军改",
                f"{neutral_faction}联合审查会",
                f"{rival_faction}的舆论绞杀和制度否认",
                f"{antagonist}质疑战功数据造假；{protagonist}展示战灵视角记录；{primary_faction}证明二号裂缝战果无法由个人高阶战力完成",
                "召唤师后勤化政策被暂停，主角从个体逆袭进入制度改写阶段",
                [f"{antagonist}发起审查", f"{protagonist}公开战灵视角证据", f"{primary_faction}为军团战果背书"],
                "审查会外，城墙结界同时亮起七处黑潮裂缝",
                "下一章必须以阶段高潮证明一人成国的雏形",
            ),
            (
                f"{protagonist}面对七处裂缝同时开启，目标是用军团分线守城完成第一阶段封神",
                "江海市七段城墙",
                f"{hidden_faction}发动的第七次黑潮前奏",
                f"{protagonist}把战灵军团拆分到七段城墙；{second_ally}维持生命增幅；{ally}接入军方炮火网；主角亲自镇守最危险主裂缝",
                "江海市守住第一轮黑潮，主角获得一人成国称号但也被更高层异界意志锁定",
                ["七处裂缝同时开启", f"{protagonist}分线部署军团", "主裂缝中的异界意志锁定主角"],
                "主裂缝深处传来王座召唤，要求陆沉交出帝皇序列",
                "下一阶段必须围绕帝皇序列来源和真正黑潮王座展开",
            ),
        ]

    generic_locations = ["开场核心场景", "资源交易现场", "第一处对抗地点", "组织内部节点", "公开审查场", "危机前线", "隐藏档案处", "盟友据点", "阶段决战场", "下一阶段入口"]
    generic_actions = [
        ("保住关键资源", "现实压力和身份否定", "主角夺回第一份主动权"),
        ("追查资源来源", "敌对势力的封锁", "主角拿到半份证据"),
        ("进入核心组织", "内部规则和追兵", "幕后操盘者露出线索"),
        ("验证新能力", "同伴质疑和外部危机", "能力第一次公开兑现"),
        ("反击资源封锁", "合同陷阱和舆论打压", "主角建立稳定据点"),
        ("处理外部危机", "数量劣势和规则限制", "主角获得临时权限"),
        ("修复能力代价", "反噬风险和敌人指控", "团队协作关系成型"),
        ("追查城内内鬼", "潜伏者和利益链", "主角确认危机被人为引导"),
        ("公开阶段证据", "制度审查和舆论围攻", "旧规则被迫让步"),
        ("完成阶段决战", "多线危机和最终压迫", "主角取得第一阶段胜利"),
    ]
    templates: list[tuple[str, str, str, str, str, list[str], str, str]] = []
    for idx, (goal, obstacle, result) in enumerate(generic_actions, start=1):
        location = generic_locations[idx - 1]
        templates.append(
            (
                f"{protagonist}在{location}{goal}，目标是在{obstacle}下推动局势进入新阶段",
                location,
                obstacle,
                f"{protagonist}在{location}{goal}；{ally}针对{obstacle}提供第 {idx} 轮关键协助；{antagonist}或{rival_faction}制造阻碍；{result}",
                result,
                [f"{protagonist}在{location}{goal}", f"{ally}针对{obstacle}提供协助", f"{antagonist}制造第 {idx} 轮阻碍后被主角反制"],
                f"{hidden_faction}留下第 {idx} 条更高层线索",
                f"下一章必须承接第 {idx} 条线索，并让主角付出新的可见代价",
            )
        )
    return templates


def _generate_genesis_scaffold(
    body: GenesisGenerateRequest,
    seed_draft: dict | None = None,
) -> dict:
    """Create a seed-aware editable Genesis draft when live output is incomplete."""
    title = body.title.strip() or "未命名项目"
    genre = body.genre.strip() or "小说"
    premise = body.premise.strip() or f"围绕《{title}》展开的{genre}故事。"
    target_chapters = max(body.target_chapters, 1)
    target_words = _target_word_count(body)
    arc_mid = max(1, min(target_chapters, max(3, target_chapters // 3)))
    arc_two_end = max(arc_mid + 1, min(target_chapters, arc_mid * 2))
    terms = _genre_terms(body)
    entities = _default_scaffold_entities(body, seed_draft)
    mode = entities["mode"]
    protagonist = entities["protagonist"]
    ally = entities["ally"]
    second_ally = entities["second_ally"]
    antagonist = entities["antagonist"]
    observer = entities["observer"]
    primary_faction = entities["primary_faction"]
    rival_faction = entities["rival_faction"]
    hidden_faction = entities["hidden_faction"]
    neutral_faction = entities["neutral_faction"]

    instruction_templates = _build_scaffold_instruction_templates(mode, entities)
    instructions: list[dict] = []
    for chapter in range(1, target_chapters + 1):
        (
            objective,
            primary_location,
            opposing_force,
            key_events,
            visible_result,
            action_chain,
            ending_hook,
            continuity_seed,
        ) = instruction_templates[(chapter - 1) % len(instruction_templates)]
        if chapter > len(instruction_templates):
            objective = f"{protagonist}承接第 {chapter - 1} 章后果，在新战场解决第 {chapter} 章核心危机"
            key_events = f"{protagonist}复盘上一章代价；{ally}带来第 {chapter} 章新线索；{antagonist}升级阻挠；主角用已建立能力完成一次可见兑现"
            ending_hook = f"第 {chapter} 章结尾出现下一阶段更高层威胁"
            continuity_seed = f"下一章必须承接第 {chapter} 章新威胁，并保留主角上一章取得的资源或权限"
            action_chain = [f"复盘第 {chapter - 1} 章后果", "追查新线索", "完成能力兑现"]
            visible_result = "主角能力、资源或阵营关系产生可见升级"
            primary_location = f"第 {chapter} 章新战场"
            opposing_force = f"{hidden_faction}升级后的外部压力"
        instructions.append({
            "chapter_number": chapter,
            "objective": objective,
            "protagonist": protagonist,
            "primary_location": primary_location,
            "opposing_force": opposing_force,
            "action_chain": action_chain,
            "visible_result": visible_result,
            "state_change": f"第 {chapter} 章结束时，{protagonist}相对上一章获得新的资源、权限或敌情，但也暴露新的风险",
            "key_events": key_events,
            "plots_to_plant": [f"{hidden_faction}的真正目标"] if chapter == 1 else [],
            "plots_to_resolve": [],
            "emotion_tone": terms["tone"],
            "ending_hook": ending_hook,
            "continuity_seed": continuity_seed,
            "word_target": target_words,
        })

    if mode == "urban_summon":
        world_settings = [
            {
                "title": "觉醒纪元与都市防线",
                "category": "时代背景",
                "content": "现代都市在觉醒者体系、城墙防线和空间裂缝威胁下维持秩序，天赋评级决定教育、军功和资源分配。",
            },
            {
                "title": "军团召唤与评级误判",
                "category": "能力规则",
                "content": f"{protagonist}表面是F级量产召唤师，实则可用统御锚点替代精神微操，将低阶战灵组成军团。",
            },
            {
                "title": "守城爽点循环",
                "category": "叙事规则",
                "content": "每轮冲突必须包含压迫、召唤扩编、军阵兑现、敌方反噬和更高层裂缝威胁。",
            },
        ]
        characters = [
            {
                "name": protagonist,
                "role": "protagonist",
                "description": f"F级召唤师，目标是以军团召唤证明战略价值并守住城市。\n内在矛盾/秘密: 帝皇序列来源未明，过早暴露会引来豪门和异界双重抹杀。\n与主角利益关系: 本人，所有资源、军功和身份变化都直接推动一人成国路线。",
                "traits": "隐忍、强硬、战场判断快、重视普通人伤亡",
            },
            {
                "name": ally,
                "role": "supporting",
                "description": f"{primary_faction}关键支持者，目标是找到能打破兽潮数量劣势的统帅型觉醒者。\n与主角利益关系: 为{protagonist}提供军方背书和实战战场。",
                "traits": "务实、果断、重军功",
            },
            {
                "name": second_ally,
                "role": "supporting",
                "description": f"治疗或后勤核心，目标是建立不按评级放弃低阶觉醒者的支援体系。\n与主角利益关系: 强化召唤军团续航，是主角军团闭环的重要拼图。",
                "traits": "冷静、善良、有豪门资源但不盲从豪门",
            },
            {
                "name": antagonist,
                "role": "antagonist",
                "description": f"旧秩序代表，目标是维持高评级职业和豪门资源垄断。\n与主角利益关系: 视{protagonist}为动摇制度的威胁，会从舆论、资源和武力层面压制。",
                "traits": "骄傲、强势、擅长调动规则",
            },
        ]
        factions = [
            {
                "name": primary_faction,
                "type": "国家/军方力量",
                "description": "掌握城防、军功和前线资源，当前急需能应对淹没式兽潮的新战法。",
                "relationship_with_protagonist": "潜在靠山和实战舞台",
            },
            {
                "name": rival_faction,
                "type": "豪门/旧秩序势力",
                "description": "依靠高评级觉醒者和资源垄断维持地位，当前试图压制军团召唤复苏。",
                "relationship_with_protagonist": "直接压迫和反噬对象",
            },
            {
                "name": hidden_faction,
                "type": "外部入侵势力",
                "description": "通过裂缝、兽潮和潜伏者冲击城市防线，正在酝酿更大规模黑潮。",
                "relationship_with_protagonist": "长期主线敌人",
            },
            {
                "name": neutral_faction,
                "type": "教育/行业机构",
                "description": "掌握评级、注册和任务资格，当前被既有评价标准限制。",
                "relationship_with_protagonist": "可被战绩改写的制度入口",
            },
        ]
        outlines = [
            {
                "chapters_range": f"1-{arc_mid}",
                "title": "F级压迫与军团觉醒",
                "content": f"阶段冲突: {protagonist}被F级评级和豪门羞辱压入谷底。转折: 帝皇序列让低阶战灵形成军阵。阶段结果: 主角从废柴标签中撕开第一道口子。",
                "level": "arc",
                "sequence": 1,
            },
            {
                "chapters_range": f"{arc_mid + 1}-{arc_two_end}" if arc_mid + 1 <= arc_two_end else f"{arc_mid}",
                "title": "能力验证与军方入场",
                "content": f"阶段冲突: {rival_faction}和评级制度否认召唤师价值。转折: {protagonist}在真实兽潮中用军阵救下{primary_faction}。阶段结果: 军团召唤从个人逆袭升级为战略争夺。",
                "level": "arc",
                "sequence": 2,
            },
            {
                "chapters_range": f"{arc_two_end + 1}-{target_chapters}" if arc_two_end + 1 <= target_chapters else f"{target_chapters}",
                "title": "黑潮前奏与一人成国",
                "content": f"阶段冲突: {hidden_faction}发动更高强度渗透，旧制度仍试图夺走主角战果。转折: 主角分线守城并证明军团召唤可替代单点高阶战力。阶段结果: 一人成国雏形出现，下一阶段引出帝皇序列来源。",
                "level": "arc",
                "sequence": 3,
            },
        ]
        plot_holes = [
            {
                "code": "PH-001",
                "type": "能力伏笔",
                "title": "帝皇序列为何选择主角",
                "description": f"触发场景: {protagonist}F级觉醒时古戒激活。读者表象: 母亲遗物救场。真相方向: 古戒与上古军团召唤禁区有关。预计兑现: 第 {min(target_chapters, 10)} 章后逐步揭示。",
                "planted_chapter": 1,
                "planned_resolve_chapter": min(target_chapters, 10),
                "status": "planted",
            },
            {
                "code": "PH-002",
                "type": "势力伏笔",
                "title": f"{hidden_faction}提前渗透城内",
                "description": f"触发场景: 兽潮总能避开强防线。读者表象: 裂缝随机扩张。真相方向: 城内有人向{hidden_faction}泄露城防信息。预计兑现: 第 {min(target_chapters, 8)} 章。",
                "planted_chapter": 3,
                "planned_resolve_chapter": min(target_chapters, 8),
                "status": "planted",
            },
            {
                "code": "PH-003",
                "type": "关系伏笔",
                "title": f"{second_ally}与军团完全体的关系",
                "description": f"触发场景: {second_ally}治疗术对战灵产生异常增幅。读者表象: 辅助能力适配。真相方向: 生命锚点是军团召唤完全体必要条件。预计兑现: 第 {min(target_chapters, 12)} 章。",
                "planted_chapter": 4,
                "planned_resolve_chapter": min(target_chapters, 12),
                "status": "planted",
            },
        ]
    else:
        world_settings = [
            {
                "title": "故事基础世界",
                "category": "世界观",
                "content": terms["setting"],
            },
            {
                "title": terms["power"],
                "category": "力量规则",
                "content": f"故事的核心成长依赖{terms['resource']}，主角必须通过具体行动逐步兑现能力或资源优势。",
            },
            {
                "title": "冲突结构",
                "category": "叙事规则",
                "content": terms["conflict"],
            },
        ]
        characters = [
            {
                "name": protagonist,
                "role": "protagonist",
                "description": f"《{title}》的核心人物，目标是在压迫和危机中夺回主动权。\n内在矛盾/秘密: 掌握的关键能力或资源尚未被外界理解。\n与主角利益关系: 本人，所有选择推动主线升级。",
                "traits": "克制、果断、能在压力下反击",
            },
            {
                "name": ally,
                "role": "supporting",
                "description": f"主角早期盟友，目标是帮助{protagonist}拿到第一轮关键证据或资源。",
                "traits": "敏锐、可靠、有行动力",
            },
            {
                "name": antagonist,
                "role": "antagonist",
                "description": f"早期对抗者，目标是阻止{protagonist}打破既有秩序。",
                "traits": "强势、谨慎、擅长调动资源",
            },
            {
                "name": observer,
                "role": "supporting",
                "description": f"隐藏线索观察者，目标是测试{protagonist}是否能触及更高层真相。\n内在矛盾/秘密: 掌握关键情报但不会直接替主角解决危机。\n与主角利益关系: 提供方向，同时制造信息压力。",
                "traits": "克制、信息量大、立场暧昧",
            },
        ]
        factions = [
            {
                "name": primary_faction,
                "type": "主线组织",
                "description": "提供任务、资源或冲突舞台，是主角进入更大世界的入口。",
                "relationship_with_protagonist": "既提供机会也形成限制",
            },
            {
                "name": rival_faction,
                "type": "敌对势力",
                "description": "维护旧秩序并压制主角崛起。",
                "relationship_with_protagonist": "早期主要对手",
            },
            {
                "name": hidden_faction,
                "type": "隐藏势力",
                "description": "掌握更高层真相，持续投放线索或威胁。",
                "relationship_with_protagonist": "长期谜团来源",
            },
        ]
        outlines = [
            {
                "chapters_range": f"1-{arc_mid}",
                "title": "开局压迫与能力显形",
                "content": f"{premise} 阶段冲突: {protagonist}在现实压力下保住关键资源。转折: 主角完成第一次可见兑现。阶段结果: 对抗从个人压迫升级为组织关注。",
                "level": "arc",
                "sequence": 1,
            },
            {
                "chapters_range": f"{arc_mid + 1}-{arc_two_end}" if arc_mid + 1 <= arc_two_end else f"{arc_mid}",
                "title": "势力入场与规则碰撞",
                "content": f"阶段冲突: {rival_faction}压制主角扩大影响。转折: {hidden_faction}线索证明危机背后另有操盘者。阶段结果: 主角获得新资源但暴露行动路线。",
                "level": "arc",
                "sequence": 2,
            },
            {
                "chapters_range": f"{arc_two_end + 1}-{target_chapters}" if arc_two_end + 1 <= target_chapters else f"{target_chapters}",
                "title": "阶段高潮与主线升级",
                "content": f"阶段冲突: {protagonist}必须在公开反击和隐藏真相之间选择。转折: 主角把前期资源集中兑现。阶段结果: 第一阶段敌人反噬，更高层危机开启。",
                "level": "arc",
                "sequence": 3,
            },
        ]
        plot_holes = [
            {
                "code": "PH-001",
                "type": "主线谜团",
                "title": f"{hidden_faction}为何关注{protagonist}",
                "description": f"触发场景: {protagonist}第一次反击后出现隐藏线索。读者表象: 偶然被卷入。真相方向: 主角能力或身份与更高层规则有关。预计兑现: 第 {min(target_chapters, 10)} 章。",
                "planted_chapter": 1,
                "planned_resolve_chapter": min(target_chapters, 10),
                "status": "planted",
            },
            {
                "code": "PH-002",
                "type": "势力伏笔",
                "title": f"{rival_faction}背后的资源链",
                "description": f"触发场景: {rival_faction}能提前封锁主角行动。读者表象: 对手资源强。真相方向: 资源链背后连接更高层危机。预计兑现: 第 {min(target_chapters, 8)} 章。",
                "planted_chapter": 2,
                "planned_resolve_chapter": min(target_chapters, 8),
                "status": "planted",
            },
        ]

    return {
        "_meta": {
            "source": "scaffold_fallback",
            "quality_status": "scaffold_fallback",
            "warnings": ["此草案由系统兜底模板生成，不建议直接批准"],
        },
        "project_updates": {"description": _project_description_from_body(body)},
        "world_settings": world_settings,
        "characters": characters,
        "factions": factions,
        "outlines": outlines,
        "plot_holes": plot_holes,
        "instructions": instructions,
    }


def _fill_missing_genesis_sections(body: GenesisGenerateRequest, draft: dict | None) -> dict:
    """Fill any remaining required Genesis sections from a local editable scaffold.

    v6.6.3: If any section is filled from scaffold, mark the draft with
    _meta.scaffold_sections to track which parts are fallback.
    """
    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft)) or {}
    scaffold = _generate_genesis_scaffold(body, seed_draft=normalized)

    scaffold_sections: list[str] = []

    project_updates = normalized.get("project_updates")
    description = ""
    if isinstance(project_updates, dict):
        description = _as_text(project_updates.get("description", "")).strip()
    else:
        description = _as_text(project_updates).strip()
    if not description:
        normalized["project_updates"] = scaffold["project_updates"]
        scaffold_sections.append("project_updates")

    for key in ("world_settings", "characters", "factions", "outlines", "plot_holes", "instructions"):
        value = normalized.get(key)
        if not isinstance(value, list) or not value:
            normalized[key] = scaffold[key]
            scaffold_sections.append(key)

    # v6.6.3: Mark if any scaffold sections were used
    if scaffold_sections:
        meta = normalized.get("_meta", {})
        if not isinstance(meta, dict):
            meta = {}
        meta["scaffold_sections"] = scaffold_sections
        meta["quality_status"] = "scaffold_fallback"
        meta["warnings"] = [f"以下部分由系统模板补齐：{', '.join(scaffold_sections)}"]
        normalized["_meta"] = meta

    return _dedupe_genesis_draft(normalized) or {}


def _short_title(text: str, fallback: str, limit: int = 24) -> str:
    """Create a compact title from free-form text."""
    clean = " ".join(_as_text(text).split())
    if not clean:
        return fallback
    return clean[:limit]


def _coerce_world_setting(item, index: int) -> dict | None:
    if isinstance(item, dict):
        title = _as_text(item.get("title", "")) or f"世界设定 {index}"
        return {
            "title": title,
            "category": _as_text(item.get("category", "其他")) or "其他",
            "content": _as_text(item.get("content", "")),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {"title": _short_title(text, f"世界设定 {index}"), "category": "其他", "content": text}


def _coerce_character(item, index: int) -> dict | None:
    if isinstance(item, dict):
        name = _as_text(item.get("name", "")) or f"角色 {index}"
        # v6.6.4: Merge extra depth fields into description so nothing is lost on approval
        description = _as_text(item.get("description", ""))
        goal = _as_text(item.get("goal", "")) or _as_text(item.get("desire", "")) or _as_text(item.get("current_goal", ""))
        conflict = _as_text(item.get("conflict", "")) or _as_text(item.get("inner_conflict", "")) or _as_text(item.get("secret", ""))
        interest = _as_text(item.get("interest_relation", "")) or _as_text(item.get("relationship_with_protagonist", ""))
        if goal and goal not in description:
            description = f"{description}\n当前目标: {goal}".strip()
        if conflict and conflict not in description:
            description = f"{description}\n内在矛盾/秘密: {conflict}".strip()
        if interest and interest not in description:
            description = f"{description}\n与主角利益关系: {interest}".strip()
        return {
            **item,
            "name": name,
            "role": _normalize_character_role(_as_text(item.get("role", "supporting"))),
            "description": description,
            "traits": _as_text(item.get("traits", "")),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "name": _short_title(text, f"角色 {index}", limit=12),
        "role": "supporting",
        "description": text,
        "traits": "",
    }


def _coerce_named_item(item, index: int, fallback_prefix: str) -> dict | None:
    if isinstance(item, dict):
        # v6.6.4: Merge extra depth fields into description for factions
        description = _as_text(item.get("description", ""))
        resources = _as_text(item.get("resources", "")) or _as_text(item.get("means", ""))
        attitude = _as_text(item.get("attitude", "")) or _as_text(item.get("attitude_toward_protagonist", ""))
        action = _as_text(item.get("action", "")) or _as_text(item.get("current_action", ""))
        if resources and resources not in description:
            description = f"{description}\n资源/手段: {resources}".strip()
        if attitude and attitude not in description:
            description = f"{description}\n对主角态度: {attitude}".strip()
        if action and action not in description:
            description = f"{description}\n当前阶段行动: {action}".strip()
        return {
            **item,
            "description": description,
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "name": _short_title(text, f"{fallback_prefix} {index}", limit=16),
        "type": "",
        "description": text,
        "relationship_with_protagonist": "",
    }


def _coerce_outline(item, index: int) -> dict | None:
    if isinstance(item, dict):
        # v6.6.4: Merge extra depth fields into content for outlines
        content = _as_text(item.get("content", ""))
        stage_conflict = _as_text(item.get("stage_conflict", "")) or _as_text(item.get("conflict", ""))
        twist = _as_text(item.get("twist", "")) or _as_text(item.get("turning_point", ""))
        stage_result = _as_text(item.get("stage_result", "")) or _as_text(item.get("result", ""))
        if stage_conflict and stage_conflict not in content:
            content = f"{content}\n阶段冲突: {stage_conflict}".strip()
        if twist and twist not in content:
            content = f"{content}\n转折: {twist}".strip()
        if stage_result and stage_result not in content:
            content = f"{content}\n阶段结果: {stage_result}".strip()
        return {
            **item,
            "level": _as_text(item.get("level", "arc")) or "arc",
            "sequence": _as_int(item.get("sequence"), index),
            "title": _as_text(item.get("title", "")) or f"大纲 {index}",
            "content": content,
            "chapters_range": _as_text(item.get("chapters_range", "")),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "level": "arc",
        "sequence": index,
        "title": _short_title(text, f"大纲 {index}"),
        "content": text,
        "chapters_range": "",
    }


def _coerce_plot_hole(item, index: int) -> dict | None:
    if isinstance(item, dict):
        code = _as_text(item.get("code", "")) or f"PH-{index:03d}"
        # v6.6.4: Merge extra depth fields into description for plot holes
        description = _as_text(item.get("description", ""))
        trigger_scene = _as_text(item.get("trigger_scene", "")) or _as_text(item.get("trigger", ""))
        appearance = _as_text(item.get("reader_appearance", "")) or _as_text(item.get("appearance", ""))
        truth_direction = _as_text(item.get("truth_direction", "")) or _as_text(item.get("truth", ""))
        resolve_plan = _as_text(item.get("resolve_plan", "")) or _as_text(item.get("planned_resolve_chapter", ""))
        if trigger_scene and trigger_scene not in description:
            description = f"{description}\n触发场景: {trigger_scene}".strip()
        if appearance and appearance not in description:
            description = f"{description}\n读者表象: {appearance}".strip()
        if truth_direction and truth_direction not in description:
            description = f"{description}\n真相方向: {truth_direction}".strip()
        if resolve_plan and str(resolve_plan) not in description:
            description = f"{description}\n预计兑现: {resolve_plan}".strip()
        return {
            **item,
            "code": code,
            "type": _as_text(item.get("type", "")),
            "title": _as_text(item.get("title", "")) or code,
            "description": description,
            "status": _normalize_plot_status(_as_text(item.get("status", "planted"))),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    code = f"PH-{index:03d}"
    return {"code": code, "type": "", "title": _short_title(text, code), "description": text, "status": "planted"}


def _coerce_instruction(item, index: int) -> dict | None:
    if isinstance(item, dict):
        chapter_number = _as_int(item.get("chapter_number"), index)
        word_target = _as_int(
            item.get("word_target"),
            DEFAULT_INSTRUCTION_WORD_TARGET,
        )
        if word_target <= 0:
            word_target = DEFAULT_INSTRUCTION_WORD_TARGET
        # v6.6.4: Normalize key_events array into structured text without losing info
        raw_key_events = item.get("key_events", "")
        if isinstance(raw_key_events, list):
            key_events = "；".join(str(ev) for ev in raw_key_events if ev)
        else:
            key_events = _as_text(raw_key_events)
        raw_action_chain = item.get("action_chain", [])
        if isinstance(raw_action_chain, list):
            action_chain = [_as_text(action) for action in raw_action_chain if _as_text(action)]
        elif raw_action_chain:
            action_chain = [_as_text(raw_action_chain)]
        else:
            action_chain = []
        return {
            **item,
            "chapter_number": chapter_number,
            "objective": _as_text(item.get("objective", "")),
            "protagonist": _as_text(item.get("protagonist", "")),
            "primary_location": _as_text(item.get("primary_location", "")),
            "opposing_force": _as_text(item.get("opposing_force", "")),
            "action_chain": action_chain,
            "visible_result": _as_text(item.get("visible_result", "")),
            "state_change": _as_text(item.get("state_change", "")),
            "key_events": key_events,
            "emotion_tone": _as_text(item.get("emotion_tone", "")),
            "ending_hook": _as_text(item.get("ending_hook", "")),
            "continuity_seed": _as_text(item.get("continuity_seed", "")),
            "word_target": word_target,
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "chapter_number": index,
        "objective": text,
        "key_events": text,
        "emotion_tone": "",
        "ending_hook": "",
        "continuity_seed": "",
        "word_target": DEFAULT_INSTRUCTION_WORD_TARGET,
    }


def _format_instruction_contract_details(instruction: dict) -> str:
    """Format structured instruction contract fields for legacy key_events storage."""
    lines: list[str] = []
    label_by_key = {
        "protagonist": "本章主角",
        "primary_location": "主要场景",
        "opposing_force": "阻力来源",
        "visible_result": "可见结果",
        "state_change": "状态变化",
    }
    for key, label in label_by_key.items():
        value = _as_text(instruction.get(key, "")).strip()
        if value:
            lines.append(f"{label}: {value}")

    action_chain = instruction.get("action_chain")
    if isinstance(action_chain, list):
        actions = [_as_text(action).strip() for action in action_chain if _as_text(action).strip()]
    else:
        action_text = _as_text(action_chain).strip()
        actions = [action_text] if action_text else []
    if actions:
        lines.append("行动链: " + "；".join(actions))

    return "\n".join(lines)


def _normalize_character_role(role: str | None) -> str:
    """Map real LLM Chinese role labels to canonical character roles."""
    role_text = (role or "").strip().lower()
    mapping = {
        "主角": "protagonist",
        "男主": "protagonist",
        "女主": "protagonist",
        "protagonist": "protagonist",
        "反派": "antagonist",
        "反派boss": "antagonist",
        "antagonist": "antagonist",
        "配角": "supporting",
        "supporting": "supporting",
    }
    if role_text in mapping:
        return mapping[role_text]
    if "主角" in role_text or "男主" in role_text or "女主" in role_text:
        return "protagonist"
    if "反派" in role_text or "boss" in role_text:
        return "antagonist"
    return role or "supporting"


def _normalize_plot_status(status: str | None) -> str:
    """Map free-form LLM plot-hole statuses to canonical values."""
    status_text = (status or "").strip().lower()
    if status_text in ("planted", "resolved", "abandoned"):
        return status_text
    if "解决" in status_text or "resolved" in status_text:
        return "resolved"
    if "废弃" in status_text or "abandoned" in status_text:
        return "abandoned"
    return "planted"


def _build_genesis_common_context(body: GenesisGenerateRequest) -> str:
    """Build shared project context for segmented Genesis prompts."""
    title_contract = build_title_contract({
        "name": body.title,
        "genre": body.genre,
        "description": body.premise,
        "target_words": body.target_words,
        "total_chapters_planned": body.target_chapters,
    })
    premise_display = body.premise.strip() or f"基于标题《{body.title}》和类型「{body.genre}」自动推断故事前提"
    return (
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {premise_display}\n"
        "创世范围说明: 本次需要生成整本书的底盘设定，并只展开首批章节指令。\n"
        f"首批章节规划范围: 前 {body.target_chapters} 章，首批合计约 {body.target_words} 字\n"
        "注意: 上面的章数和字数不是整本书总篇幅，后续章节会通过章节批次规划继续延展。\n"
        f"读者: {body.target_audience}\n"
        f"风格: {body.style_preference}\n"
        f"约束: {body.constraints}\n\n"
        f"{title_contract}\n"
    )


def _build_genesis_segment_prompt(
    body: GenesisGenerateRequest,
    *,
    segment: str,
    draft_json: str | None = None,
    chapter_start: int | None = None,
    chapter_end: int | None = None,
) -> str:
    """Build a short, focused Genesis prompt for one segment."""
    context = _build_genesis_common_context(body)
    draft_block = ""
    if draft_json:
        draft_block = f"【已有草案 JSON】\n{draft_json}\n\n"

    if segment == "foundation":
        return (
            "【生成段落】foundation\n"
            f"{context}\n"
            "请只返回严格 JSON 对象，且只包含以下字段:\n"
            "- project_updates: {\"description\": \"项目描述\"}\n"
            "- world_settings: [{\"title\": \"\", \"category\": \"\", \"content\": \"\"}]\n\n"
            "要求：\n"
            "1. 只生成世界观底座、时代背景、能力规则、冲突结构，不要返回角色、势力、大纲、伏笔或章节指令。\n"
            "2. project_updates 的 description 要用一句话概括项目核心卖点。\n"
            "3. world_settings 至少 3 项，避免空泛和重复。\n"
            "4. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    if segment == "cast":
        return (
            "【生成段落】cast\n"
            f"{context}\n"
            f"{draft_block}"
            "请只返回严格 JSON 对象，且只包含以下字段:\n"
            "- characters: [{\"name\": \"\", \"role\": \"protagonist|antagonist|supporting\", \"description\": \"\", \"traits\": \"\"}]\n"
            "- factions: [{\"name\": \"\", \"type\": \"\", \"description\": \"\", \"relationship_with_protagonist\": \"\"}]\n\n"
            "要求：\n"
            "1. 角色必须包含主角、核心盟友或重要配角、主要反派或对立人物。\n"
            "2. 每个角色必须写清目标、矛盾或秘密、与主角的利益关系。\n"
            "3. 势力必须写清资源/手段、当前阶段行动、对主角态度。\n"
            "4. 不要返回 project_updates、world_settings、outlines、plot_holes 或 instructions。\n"
            "5. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    if segment == "plot":
        return (
            "【生成段落】plot\n"
            f"{context}\n"
            f"{draft_block}"
            "请只返回严格 JSON 对象，且只包含以下字段:\n"
            "- outlines: [{\"chapters_range\": \"1-3\", \"title\": \"\", \"content\": \"\", \"level\": \"arc\", \"sequence\": 1}]\n"
            "- plot_holes: [{\"code\": \"PH-001\", \"type\": \"\", \"title\": \"\", \"description\": \"\", \"planted_chapter\": 1, \"planned_resolve_chapter\": 10, \"status\": \"planted\"}]\n\n"
            "要求：\n"
            "1. 大纲必须写出阶段冲突、转折、阶段结果。\n"
            "2. 伏笔必须写出触发场景、读者看到的表象、真相方向、预计兑现章节。\n"
            "3. 不要返回 project_updates、world_settings、characters、factions 或 instructions。\n"
            "4. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    if segment == "instructions":
        if chapter_start is None or chapter_end is None:
            raise ValueError("instructions segment requires chapter range")
        return (
            f"【生成段落】instructions:{chapter_start}-{chapter_end}\n"
            f"{context}\n"
            f"{draft_block}"
            f"请只返回第 {chapter_start}-{chapter_end} 章的章节指令，且只包含以下字段:\n"
            "- instructions: [{\"chapter_number\": 1, \"objective\": \"\", \"protagonist\": \"\", \"primary_location\": \"\", \"opposing_force\": \"\", \"action_chain\": [\"\", \"\", \"\"], \"visible_result\": \"\", \"state_change\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"ending_hook\": \"\", \"continuity_seed\": \"\", \"word_target\": 3000}]\n\n"
            "要求：\n"
            "1. 只生成当前章段，不要补写其他章。\n"
            "2. 每章必须是一张可执行施工单，不是阶段大纲；必须写清谁、在哪里、被谁阻拦、连续做了什么、最后局势如何改变。\n"
            "3. objective 必须包含本章具体目标、主要阻力和结果变化，禁止只写\"扩大冲突/推动剧情/获得主动权/打破定律/吸引注意\"这类抽象总结。\n"
            "4. protagonist 必须使用具体角色名；primary_location 必须具体到场景或地点；opposing_force 必须写具体人物、组织或压力源。\n"
            "5. action_chain 必须至少 3 步，每一步都要包含执行者、动作和对象，例如\"陆恒在临江觉醒者学院考核场召唤刀盾手挡住E级魔物群\"。\n"
            "6. visible_result 写读者可见的外部结果；state_change 写本章结束后主角、敌人、势力或资源状态的变化。\n"
            "7. key_events 至少写 3 个具体事件，并与 action_chain 一致；ending_hook 和 continuity_seed 必须可直接承接下一章。\n"
            "8. 不要返回 project_updates、world_settings、characters、factions、outlines 或 plot_holes。\n"
            "9. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    raise ValueError(f"Unknown genesis segment: {segment}")


async def _invoke_genesis_segment(
    llm,
    *,
    prompt: str,
    max_tokens: int,
) -> dict:
    """Invoke one Genesis segment with a bounded response budget."""
    return await asyncio.to_thread(
        llm.invoke_json,
        [
            {
                "role": "system",
                "content": "你只输出纯 JSON 对象，不要输出任何 Markdown 代码块、注释或解释文字。不要在 JSON 中添加尾逗号。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        max_retries=2,
    )


async def _generate_real_draft(
    body: GenesisGenerateRequest,
    settings,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Generate a genesis draft using real LLM.

    v6.7.7: Accepts optional progress callback for SSE streaming.
    """
    from ...llm.openai_compatible import LLMTimeoutError

    def _emit(event_type: str, **kwargs):
        if progress and run_id:
            progress(event_type, {"run_id": run_id, **kwargs})

    llm = _build_genesis_llm(settings)
    merged: dict | None = None
    active_segment = "foundation"

    try:
        # Foundation segment
        active_segment = "foundation"
        _emit("segment_started", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])
        foundation_prompt = _build_genesis_segment_prompt(body, segment="foundation")
        foundation = await _invoke_genesis_segment(
            llm,
            prompt=foundation_prompt,
            max_tokens=GENESIS_SEGMENT_MAX_TOKENS["foundation"],
        )
        merged = _merge_genesis_drafts(None, foundation)
        _emit("segment_completed", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])

        # Cast segment
        active_segment = "cast"
        _emit("segment_started", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])
        cast_prompt = _build_genesis_segment_prompt(
            body,
            segment="cast",
            draft_json=json.dumps(merged, ensure_ascii=False)[:10000],
        )
        cast = await _invoke_genesis_segment(
            llm,
            prompt=cast_prompt,
            max_tokens=GENESIS_SEGMENT_MAX_TOKENS["cast"],
        )
        merged = _merge_genesis_drafts(merged, cast)
        _emit("segment_completed", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])

        # Plot segment
        active_segment = "plot"
        _emit("segment_started", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])
        plot_prompt = _build_genesis_segment_prompt(
            body,
            segment="plot",
            draft_json=json.dumps(merged, ensure_ascii=False)[:10000],
        )
        plot = await _invoke_genesis_segment(
            llm,
            prompt=plot_prompt,
            max_tokens=GENESIS_SEGMENT_MAX_TOKENS["plot"],
        )
        merged = _merge_genesis_drafts(merged, plot)
        _emit("segment_completed", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])

        # Instructions segment (per-chunk)
        chapter_count = max(1, int(body.target_chapters or 1))
        chunk_size = max(1, GENESIS_INSTRUCTION_CHUNK_SIZE)
        instruction_max_tokens = min(4500, 1800 + chunk_size * 420)
        for chapter_start in range(1, chapter_count + 1, chunk_size):
            chapter_end = min(chapter_count, chapter_start + chunk_size - 1)
            active_segment = f"instructions:{chapter_start}-{chapter_end}"
            _emit("chapter_start", chapter_start=chapter_start, chapter_end=chapter_end,
                  label=f"正在生成章节指令 {chapter_start}-{chapter_end}")
            instruction_prompt = _build_genesis_segment_prompt(
                body,
                segment="instructions",
                draft_json=json.dumps(merged, ensure_ascii=False)[:12000],
                chapter_start=chapter_start,
                chapter_end=chapter_end,
            )
            instruction_patch = await _invoke_genesis_segment(
                llm,
                prompt=instruction_prompt,
                max_tokens=instruction_max_tokens,
            )
            merged = _merge_genesis_drafts(merged, instruction_patch)
            _emit("chapter_end", chapter_start=chapter_start, chapter_end=chapter_end,
                  label=f"章节指令 {chapter_start}-{chapter_end} 完成")
    except LLMTimeoutError as exc:
        logger.warning(
            "Genesis segment timed out; using local recovery segment=%s title=%s",
            active_segment,
            body.title,
            exc_info=True,
        )
        _emit("segment_started", segment="repair", label="LLM 超时，正在保留已完成分段并本地补齐")
        recovered = _recover_genesis_from_partial_draft(
            body,
            merged,
            reason=f"{active_segment}_llm_unavailable",
            error_message=str(exc),
        )
        _emit("segment_completed", segment="repair", label="已保留可用分段并完成本地补齐")
        return recovered

    return _dedupe_genesis_draft(_normalize_genesis_draft(merged)) or merged


def _build_genesis_llm(settings):
    """Build the dedicated Genesis LLM profile."""
    from ...workflow.runner import _build_llm_router

    llm = _build_llm_router(settings, "real").for_agent("genesis")
    if is_configured_live_provider(llm):
        llm.config.request_timeout_seconds = max(llm.config.request_timeout_seconds, 180)
        llm.config.retry_attempts = max(llm.config.retry_attempts, 2)
    return llm


def _build_genesis_completion_prompt(
    body: GenesisGenerateRequest,
    current_draft: dict,
    missing_sections: list[str],
) -> str:
    """Build a focused prompt that asks the LLM to fill missing Genesis sections."""
    missing_labels = "、".join(missing_sections)
    current_json = json.dumps(current_draft, ensure_ascii=False)[:12000]
    title_contract = build_title_contract({
        "name": body.title,
        "genre": body.genre,
        "description": body.premise,
        "target_words": body.target_words,
        "total_chapters_planned": body.target_chapters,
    })
    return (
        "下面的创世草案不完整。请只补齐缺失部分，保持已有设定方向一致，不要重写已有内容。\n"
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {body.premise.strip() or '根据标题和类型推断'}\n"
        f"首批章节规划范围: 前 {body.target_chapters} 章，约 {body.target_words} 字\n"
        f"缺失部分: {missing_labels}\n\n"
        f"{title_contract}\n\n"
        f"【已有草案 JSON】\n{current_json}\n\n"
        "请返回严格 JSON 对象，顶层字段可以只包含缺失部分，但字段结构必须符合：\n"
        "- world_settings: [{\"title\": \"\", \"category\": \"\", \"content\": \"\"}]\n"
        "- characters: [{\"name\": \"\", \"role\": \"protagonist|antagonist|supporting\", \"description\": \"\", \"traits\": \"\"}]\n"
        "- factions: [{\"name\": \"\", \"type\": \"\", \"description\": \"\", \"relationship_with_protagonist\": \"\"}]\n"
        "- outlines: [{\"chapters_range\": \"1-3\", \"title\": \"\", \"content\": \"\", \"level\": \"arc\", \"sequence\": 1}]\n"
        "- plot_holes: [{\"code\": \"PH-001\", \"type\": \"\", \"title\": \"\", \"description\": \"\", \"planted_chapter\": 1, \"planned_resolve_chapter\": 10, \"status\": \"planted\"}]\n"
        "- instructions: [{\"chapter_number\": 1, \"objective\": \"\", \"protagonist\": \"\", \"primary_location\": \"\", \"opposing_force\": \"\", \"action_chain\": [\"\", \"\", \"\"], \"visible_result\": \"\", \"state_change\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"ending_hook\": \"\", \"continuity_seed\": \"\", \"word_target\": 3000}]\n\n"
        "要求：\n"
        "1. 角色至少包含主角、核心盟友/女主/重要配角、主要反派或对立势力人物，必须有具体姓名、目标、矛盾和利益关系。\n"
        "2. 大纲至少覆盖首批章节范围，必须包含阶段冲突、转折和阶段结果。\n"
        "3. 章节指令必须覆盖首批每一章，包含 objective、protagonist、primary_location、opposing_force、action_chain、visible_result、state_change、key_events、ending_hook、continuity_seed。\n"
        "4. 输出纯 JSON，不要 Markdown、解释、注释或尾逗号。"
    )


async def _complete_real_genesis_draft(
    body: GenesisGenerateRequest,
    settings,
    draft: dict,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Repair incomplete real Genesis output before it becomes reviewable."""
    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft)) or {}
    missing = _missing_required_genesis_sections(normalized)
    if not missing:
        return normalized

    from ...llm.openai_compatible import LLMTimeoutError

    llm = _build_genesis_llm(settings)
    for _attempt in range(2):
        prompt = _build_genesis_completion_prompt(body, normalized, missing)
        try:
            patch = await asyncio.to_thread(
                llm.invoke_json,
                [
                    {
                        "role": "system",
                        "content": "你只输出纯 JSON 对象，用于补齐小说项目创世草案缺失部分。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=9000,
                max_retries=2,
            )
        except LLMTimeoutError as exc:
            logger.warning(
                "Genesis completion repair timed out; using local recovery title=%s",
                body.title,
                exc_info=True,
            )
            return _recover_genesis_from_partial_draft(
                body,
                normalized,
                reason="completion_llm_unavailable",
                error_message=str(exc),
            )
        normalized_patch = _dedupe_genesis_draft(_normalize_genesis_draft(patch))
        normalized = _merge_genesis_drafts(normalized, normalized_patch)
        missing = _missing_required_genesis_sections(normalized)
        if not missing:
            return normalized

    return _mark_genesis_local_recovery(
        _fill_missing_genesis_sections(body, normalized),
        reason="incomplete_json",
        error_message="真实 LLM 草案在两次补齐后仍缺少必需创世章节，系统已用本地恢复内容补齐。",
    )


def _instruction_repair_issue_count(quality_report) -> int:
    """Count repairable instruction-quality issues in a Genesis quality report."""
    return sum(
        1
        for issue in quality_report.issues
        if issue.section == "instructions"
        and issue.code in GENESIS_REPAIRABLE_INSTRUCTION_CODES
        and issue.severity == "blocker"
    )


def _has_instruction_repair_target(quality_report) -> bool:
    """Return whether a blocked Genesis draft should receive instruction-only repair."""
    return _instruction_repair_issue_count(quality_report) > 0


def _format_genesis_quality_issues_for_prompt(quality_report) -> str:
    """Format instruction quality issues for a focused repair prompt."""
    lines: list[str] = []
    for issue in quality_report.issues:
        if issue.section != "instructions":
            continue
        if issue.code not in GENESIS_REPAIRABLE_INSTRUCTION_CODES:
            continue
        lines.append(
            f"- {issue.code} [{issue.severity}]: {issue.message}"
            + (f"；修复要求: {issue.suggestion}" if issue.suggestion else "")
        )
    return "\n".join(lines) or "- 章节指令缺少具体人物、地点、行动链或结果变化"


def _build_genesis_instruction_repair_prompt(
    body: GenesisGenerateRequest,
    draft: dict,
    quality_report,
) -> str:
    """Build a focused prompt that repairs only Genesis chapter instructions."""
    current_json = json.dumps(draft, ensure_ascii=False)[:18000]
    issue_text = _format_genesis_quality_issues_for_prompt(quality_report)
    return (
        "下面的小说创世草案只有章节指令质量未达标。请只重写 instructions，不要改世界观、角色、势力、大纲或伏笔。\n"
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {body.premise.strip() or '根据标题和类型推断'}\n"
        f"首批章节范围: 前 {body.target_chapters} 章\n\n"
        f"【质量问题】\n{issue_text}\n\n"
        f"【已有草案 JSON】\n{current_json}\n\n"
        "请返回严格 JSON 对象，且只包含 instructions 字段：\n"
        "{\"instructions\": [{\"chapter_number\": 1, \"objective\": \"\", \"protagonist\": \"\", \"primary_location\": \"\", \"opposing_force\": \"\", \"action_chain\": [\"\", \"\", \"\"], \"visible_result\": \"\", \"state_change\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"ending_hook\": \"\", \"continuity_seed\": \"\", \"word_target\": 3000}]}\n\n"
        "硬性要求：\n"
        "1. 必须覆盖已有草案中的每一章，不得增删章节。\n"
        "2. 每章必须具体到人物、地点、阻力、三步以上行动链、可见结果和状态变化。\n"
        "3. objective 必须写成本章可执行目标：主角要做什么、被谁/什么阻拦、结束时局势如何变化。\n"
        "4. key_events 至少 3 个具体事件，必须与 action_chain 一致。\n"
        "5. ending_hook 和 continuity_seed 必须能直接指导下一章承接。\n"
        "6. 禁止只写阶段目标、抽象总结或营销式概括。\n"
        "7. 输出纯 JSON，不要 Markdown、解释、注释或尾逗号。"
    )


def _instruction_repair_rank(quality_report) -> tuple[int, int, int]:
    """Rank instruction repair candidates; lower is better."""
    blocking_count = sum(1 for issue in quality_report.issues if issue.severity == "blocker")
    return (
        _instruction_repair_issue_count(quality_report),
        blocking_count,
        -quality_report.score,
    )


def _build_local_instruction_repair_candidate(
    body: GenesisGenerateRequest,
    draft: dict,
):
    """Deterministically rebuild instructions from existing Genesis entities."""
    scaffold = _generate_genesis_scaffold(body, seed_draft=draft)
    repaired_instructions = scaffold.get("instructions")
    if not isinstance(repaired_instructions, list) or not repaired_instructions:
        return draft, evaluate_genesis_draft(
            draft,
            title=body.title,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
        )

    candidate = dict(draft)
    candidate["instructions"] = repaired_instructions
    meta = dict(candidate.get("_meta") or {})
    warnings = list(meta.get("warnings") or [])
    warning = "章节指令存在模板化或重复问题，已基于现有角色/势力进行本地重建。"
    if warning not in warnings:
        warnings.append(warning)
    meta.update({
        "instruction_repair_source": "local_seeded_rebuild",
        "warnings": warnings,
    })
    candidate["_meta"] = meta
    candidate = _dedupe_genesis_draft(_normalize_genesis_draft(candidate)) or candidate
    report = evaluate_genesis_draft(
        candidate,
        title=body.title,
        genre=body.genre,
        premise=body.premise,
        target_chapters=body.target_chapters,
    )
    return candidate, report


async def _repair_genesis_instruction_quality(
    body: GenesisGenerateRequest,
    settings,
    draft: dict,
    quality_report,
) -> dict:
    """Repair instruction-only Genesis quality failures without regenerating other sections."""
    if not _has_instruction_repair_target(quality_report):
        return draft

    best_draft = draft
    best_report = quality_report
    local_draft, local_report = _build_local_instruction_repair_candidate(body, draft)
    if _instruction_repair_rank(local_report) < _instruction_repair_rank(best_report):
        best_draft = local_draft
        best_report = local_report
    if not _has_instruction_repair_target(best_report):
        return best_draft

    llm = _build_genesis_llm(settings)

    for _attempt in range(2):
        prompt = _build_genesis_instruction_repair_prompt(body, best_draft, best_report)
        try:
            patch = await asyncio.to_thread(
                llm.invoke_json,
                [
                    {
                        "role": "system",
                        "content": "你只输出纯 JSON 对象，用于定向修复小说创世草案的章节指令。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=min(9000, 2600 + max(1, len(_as_list(best_draft.get("instructions", [])))) * 650),
                max_retries=2,
            )
        except Exception:
            logger.warning("Genesis instruction quality repair failed", exc_info=True)
            return best_draft

        normalized_patch = _dedupe_genesis_draft(_normalize_genesis_draft(patch)) or {}
        repaired_instructions = normalized_patch.get("instructions")
        if not isinstance(repaired_instructions, list) or not repaired_instructions:
            continue

        candidate = _merge_genesis_drafts(best_draft, {"instructions": repaired_instructions})
        candidate = _dedupe_genesis_draft(_normalize_genesis_draft(candidate)) or candidate
        candidate_report = evaluate_genesis_draft(
            candidate,
            title=body.title,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
        )

        if _instruction_repair_rank(candidate_report) < _instruction_repair_rank(best_report):
            best_draft = candidate
            best_report = candidate_report
        if not _has_instruction_repair_target(candidate_report):
            return candidate

    return best_draft


def _mark_genesis_generation_fallback(
    draft: dict,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Mark a generated Genesis draft as a degraded local fallback."""
    marked = dict(draft)
    meta = marked.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    warnings = list(meta.get("warnings") or [])
    warning = "真实 LLM 输出不是可解析 JSON，已生成系统兜底草案。请重新生成或人工补全后再批准。"
    if warning not in warnings:
        warnings.append(warning)
    meta.update({
        "source": "scaffold_fallback",
        "quality_status": "scaffold_fallback",
        "generation_fallback": True,
        "fallback_reason": reason,
        "original_error": error_message[:500],
        "warnings": warnings,
    })
    marked["_meta"] = meta
    return marked


def _mark_genesis_local_recovery(
    draft: dict,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Mark local Genesis recovery content as reviewable instead of blocked."""
    recovered = dict(draft)
    meta = dict(recovered.get("_meta") or {})
    warnings = [
        warning
        for warning in list(meta.get("warnings") or [])
        if "兜底模板" not in str(warning) and "系统模板补齐" not in str(warning)
    ]
    warning = "真实 LLM 输出不完整或不是可解析 JSON，系统已根据项目描述生成可审核的本地恢复草案。"
    if warning not in warnings:
        warnings.append(warning)
    meta.update({
        "source": "local_recovery",
        "quality_status": "recovered_from_invalid_json"
        if reason == "invalid_json"
        else "recovered_from_incomplete_json",
        "generation_fallback": True,
        "fallback_reason": reason,
        "original_error": error_message[:500],
        "warnings": warnings,
    })
    recovered["_meta"] = meta
    return recovered


def _build_genesis_recovery_draft(
    body: GenesisGenerateRequest,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Build a usable local Genesis draft after recoverable provider failure.

    Invalid provider JSON and transient provider failures are not proof that the
    user's project should degrade into an unapprovable template. This recovery
    path uses the same deterministic section builder, but marks the result as a
    reviewable local recovery draft so the normal quality gate can judge the
    actual content instead of automatically blocking it as scaffold.
    """
    return _mark_genesis_local_recovery(
        _generate_genesis_scaffold(body),
        reason=reason,
        error_message=error_message,
    )


def _recover_genesis_from_partial_draft(
    body: GenesisGenerateRequest,
    partial_draft: dict | None,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Keep any successful LLM Genesis sections and locally fill the missing ones."""
    partial = partial_draft if isinstance(partial_draft, dict) else {}
    recovered = _fill_missing_genesis_sections(body, partial)
    return _mark_genesis_local_recovery(
        recovered,
        reason=reason,
        error_message=error_message,
    )


async def _generate_real_draft_with_scaffold_fallback(
    body: GenesisGenerateRequest,
    settings,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Generate Genesis with real LLM, falling back only for invalid JSON output.

    v6.7.7: Accepts optional progress callback for SSE streaming.
    """
    from ...llm.openai_compatible import OutputValidationError

    def _emit(event_type: str, **kwargs):
        if progress and run_id:
            progress(event_type, {"run_id": run_id, **kwargs})

    try:
        draft = await _generate_real_draft(body, settings, run_id=run_id, progress=progress)

        # Repair/completion phase
        _emit("segment_started", segment="repair", label=GENESIS_SEGMENT_LABELS["repair"])
        result = await _complete_real_genesis_draft(body, settings, draft, run_id=run_id, progress=progress)
        _emit("segment_completed", segment="repair", label=GENESIS_SEGMENT_LABELS["repair"])
        quality_report = evaluate_genesis_draft(
            result,
            title=body.title,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
        )
        if _has_instruction_repair_target(quality_report):
            _emit("segment_started", segment="repair", label="正在定向修复章节指令")
            result = await _repair_genesis_instruction_quality(
                body,
                settings,
                result,
                quality_report,
            )
            _emit("segment_completed", segment="repair", label="章节指令定向修复完成")
        return result
    except OutputValidationError as exc:
        logger.warning(
            "Genesis real LLM returned invalid JSON; using scaffold fallback title=%s genre=%s",
            body.title,
            body.genre,
            exc_info=True,
        )
        _emit("segment_started", segment="repair", label="正在使用本地恢复草案")
        result = _build_genesis_recovery_draft(
            body,
            reason="invalid_json",
            error_message=str(exc),
        )
        _emit("segment_completed", segment="repair", label="本地恢复草案生成完成")
        return result


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
    from ..deps import get_repo, get_llm_mode, get_settings

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
    from ..deps import get_repo, get_settings

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
    from ..deps import get_repo

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
    from ..deps import get_repo

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
    from ..deps import get_repo

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
    from ..deps import get_repo, get_llm_mode, get_settings

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
    from ..deps import get_repo

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
    from ..deps import get_repo

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
    from ..deps import get_repo, get_llm_mode, get_settings

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
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        _genesis_progress_queues[run_id] = queue

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
    from ...db.repository import Repository
    from ...config.loader import load_settings_with_cli

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
        _genesis_progress_queues.pop(run_id, None)


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
    from ..deps import get_repo

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
    queue = _genesis_progress_queues.get(run_id)
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
