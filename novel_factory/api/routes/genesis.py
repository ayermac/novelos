"""Genesis API endpoints for project bible generation."""

from __future__ import annotations

import json
import asyncio
import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ...agent_runtime.title_contract import build_title_contract
from ...llm.provider import is_configured_live_provider
from ...quality.genesis_quality_gate import evaluate_genesis_draft

router = APIRouter()
logger = logging.getLogger(__name__)


GENESIS_RUNNING_TIMEOUT_MINUTES = 30


GENESIS_REQUIRED_SECTIONS = {
    "project_description": "项目简介",
    "world_settings": "世界观设定",
    "characters": "角色",
    "factions": "势力/组织",
    "outlines": "大纲",
    "plot_holes": "伏笔/悬念",
    "instructions": "章节指令",
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


class GenesisForceApplyBody(BaseModel):
    """Body for path-style approve route with optional force flag."""

    force_apply: bool = False
    confirm_quality_risk: bool = False


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


def _generate_stub_draft(body: GenesisGenerateRequest) -> dict:
    """Generate a deterministic stub genesis draft."""
    title = body.title or "未命名项目"
    genre = body.genre or "奇幻"
    premise = body.premise or "一个关于冒险与成长的故事"

    return {
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
        "characters": [
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
        ],
        "factions": [
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
        ],
        "outlines": [
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
        ],
        "plot_holes": [
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
        ],
        "instructions": [
            {
                "chapter_number": i + 1,
                "objective": f"第 {i + 1} 章写作指令",
                "key_events": f"关键事件 {i + 1}",
                "emotion_tone": "神秘" if i == 0 else "紧张",
                "word_target": body.target_words // body.target_chapters,
            }
            for i in range(min(body.target_chapters, 10))
        ],
    }


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


def _generate_genesis_scaffold(body: GenesisGenerateRequest) -> dict:
    """Create a complete editable Genesis draft when live output is incomplete.

    This is a last-resort safety net. It preserves the user's title/genre/brief
    and avoids letting a new project fail initialization just because a provider
    returned an empty or section-only JSON payload.

    v6.6.3: Scaffold drafts are now explicitly marked with _meta.quality_status
    to prevent silent masquerading as high-quality LLM output.
    """
    title = body.title.strip() or "未命名项目"
    genre = body.genre.strip() or "小说"
    premise = body.premise.strip() or f"围绕《{title}》展开的{genre}故事。"
    terms = _genre_terms(body)
    target_chapters = max(body.target_chapters, 1)
    target_words = _target_word_count(body)
    arc_mid = max(1, min(target_chapters, max(3, target_chapters // 3)))
    arc_two_end = max(arc_mid + 1, min(target_chapters, arc_mid * 2))
    protagonist = _infer_protagonist_name(body)
    anomaly_mode = _is_anomaly_genesis(body)
    ally = "许知夏" if anomaly_mode else "顾清禾"
    antagonist = "魏承霜" if anomaly_mode else "陆怀川"
    observer = "周砚白" if anomaly_mode else "闻人述"
    primary_faction = "异常处理局深城分部" if anomaly_mode else "星环事务所"
    rival_faction = "监管组第七办公室" if anomaly_mode else "曜石评议会"
    hidden_faction = "白塔观测会" if anomaly_mode else "雾港档案馆"
    neutral_faction = "旧城区互助网络" if anomaly_mode else "灰鲸情报社"

    instruction_templates = [
        (
            f"{protagonist}在旧城区废弃地铁站完成第一次异常勘察，目标是救出被困住的住户并确认修正系统的任务边界",
            f"{protagonist}抵达旧城区废弃地铁站后发现监控画面与现场时间不一致；{ally}在处理局终端协助定位被困住户；修正系统要求直接抹除异常表征，结果会连同住户记忆一起清空；{protagonist}选择先隔离站台入口再救人，因此被系统记录一次违规",
            f"{protagonist}看到任务结算里出现一行被隐藏的失败名单",
            "下一章必须追查失败名单中的第一个名字，并延续系统违规记录",
        ),
        (
            f"{protagonist}追查失败名单上的失踪修正员，目标是弄清对方是否死于异常还是死于处理局善后",
            f"{protagonist}在市立医院精神科找到失踪修正员留下的病历；{ally}发现病历里的脑波图与修正系统接口频率一致；{antagonist}以监管名义要求{protagonist}交出证据；{protagonist}把病历复制进私人终端，导致同化度首次上升",
            f"病历最后一页写着：系统比异常更早抵达现场",
            "下一章必须让监管组介入，并让同化度变化影响主角判断",
        ),
        (
            f"{protagonist}在监管审查中保住证据，目标是证明修正系统给出的最优解会伤害普通人",
            f"监管组在处理局深城分部对{protagonist}进行问询；{antagonist}展示被清洗记忆的幸存者录像；{protagonist}发现录像中幸存者仍能听见异常噪音；{observer}暗中递来一份未登记异常坐标，结果把{protagonist}引向更高等级事件",
            "未登记坐标的位置正好是富人区净化装置地下",
            "下一章必须进入富人区净化装置，并揭露异常处理的阶层差异",
        ),
        (
            f"{protagonist}潜入富人区净化装置地下层，目标是确认装置是否在把异常转嫁给旧城区",
            f"{protagonist}借维修通道进入净化装置地下层；{ally}发现装置排出的不是污染而是异常残响；旧城区居民的失眠病例与排放周期吻合；{protagonist}关闭一组阀门后让市中心短暂出现异常影像，结果引来处理局高层关注",
            "市中心屏幕上闪过一句话：转嫁协议执行中",
            "下一章必须处理高层关注，并让旧城区病例成为现实压力",
        ),
        (
            f"{protagonist}面对高层封口命令，目标是在不暴露异常真相的前提下保住旧城区居民证词",
            f"处理局要求{protagonist}提交全部调查资料；{antagonist}安排记忆清洗小队接触旧城区居民；{protagonist}用记忆编织伪造一份无害证词；伪造行为保护了居民却让系统判定修正失败，结果扣除权限积分",
            "被保护的居民突然认出{protagonist}后颈的接口编号",
            "下一章必须追查接口编号来源，并让权限扣除限制主角行动",
        ),
        (
            f"{protagonist}追查自己的接口编号，目标是弄清自己是否早在入职前就被系统标记",
            f"{protagonist}进入处理局档案室查询接口记录；{ally}冒险帮他绕过低级权限墙；档案显示{protagonist}的编号来自一批已注销实验体；{observer}承认白塔观测会一直在记录系统同化数据，结果让{protagonist}开始怀疑所有任务来源",
            "注销名单里出现了{protagonist}亲属的名字",
            "下一章必须让亲属线索与异常任务发生碰撞",
        ),
        (
            f"{protagonist}调查亲属注销记录，目标是找回被处理局删除的家庭记忆",
            f"{protagonist}回到儿时居住的老楼寻找残留物；楼道异常会重放被删除的家庭晚餐；系统建议立即抹除整栋楼记忆以防扩散；{protagonist}拒绝执行并用现实锚定保留一段影像，结果同化度升到危险阈值",
            "影像里的亲属对镜头说：不要相信裁衡",
            "下一章必须解释裁衡代号，并让同化危险影响任务选择",
        ),
        (
            f"{protagonist}在同化警报下接到Ⅲ类异常任务，目标是救人同时验证裁衡是否故意隐瞒信息",
            f"商业综合体出现时间错乱点并困住上百名普通人；裁衡只标记一个出口却隐藏第二个低风险通道；{protagonist}依靠前几章证据找到隐藏通道；{antagonist}现场接管指挥并要求牺牲少数人换取稳定，结果双方公开冲突",
            "隐藏通道尽头不是出口，而是一间白塔观测室",
            "下一章必须进入白塔观测室，并揭示异常不是随机出现",
        ),
        (
            f"{protagonist}进入白塔观测室，目标是确认异常爆发与人类决策之间的因果关系",
            f"观测室保存着多起异常爆发前的社会冲突记录；{observer}说明白塔只观测不制造，但裁衡会根据人类选择调整任务目标；{ally}发现处理局高层与白塔共享同化数据；{protagonist}意识到修正成功可能是在训练修正员放弃道德判断",
            "白塔档案把{protagonist}标注为可偏离样本",
            "下一章必须让主角做出第一次明确偏离系统规则的选择",
        ),
        (
            f"{protagonist}在处理局围堵中选择偏离系统规则，目标是保住现实世界而不是完成裁衡定义的修正",
            f"处理局封锁旧城区并准备执行大范围记忆清洗；裁衡给出最快修正方案：牺牲旧城区作为隔离带；{protagonist}联合{ally}和旧城区互助网络公开异常后果的伪装证据；他用现实锚定把异常锁在自己身上，结果赢得短暂喘息也让同化进入下一层",
            "裁衡第一次用非任务语气询问：你想成为例外吗",
            "下一阶段必须围绕主角如何利用而非服从系统展开",
        ),
    ]
    if not anomaly_mode:
        instruction_templates = [
            (
                f"{protagonist}在开场地点遭遇现实压力，目标是保住一项会改变命运的关键资源",
                f"{protagonist}在旧宅或工作场所发现资源被{antagonist}夺走；{ally}带来一条能证明真相的线索；{protagonist}选择冒险追查而不是妥协，结果得罪{rival_faction}",
                f"{protagonist}发现关键资源上刻着{hidden_faction}的标记",
                "下一章必须追查标记来源，并延续主角与对立势力的冲突",
            ),
            (
                f"{protagonist}追查{hidden_faction}的标记，目标是找到资源背后的真正交易方",
                f"{protagonist}进入{neutral_faction}控制的情报场所；{ally}用私人关系换到交易记录；{antagonist}派人封锁出口；{protagonist}带着半份记录逃脱，结果暴露自己的行动路线",
                f"交易记录缺失的半页指向{primary_faction}内部",
                "下一章必须让主角进入核心组织内部，并处理行动暴露的后果",
            ),
            (
                f"{protagonist}进入{primary_faction}内部核对交易记录，目标是确认谁在操控局面",
                f"{protagonist}借助{ally}身份进入资料室；资料显示{rival_faction}只是执行者；{observer}提醒主角不要相信公开档案；{protagonist}复制档案后触发警报，结果被迫与{antagonist}正面对峙",
                f"{observer}留下的坐标指向一处被地图抹掉的地点",
                "下一章必须前往被抹掉的地点，并揭示更高层级势力",
            ),
        ]
        while len(instruction_templates) < target_chapters:
            chapter = len(instruction_templates) + 1
            instruction_templates.append(
                (
                    f"{protagonist}在第 {chapter} 章围绕前章坐标展开行动，目标是取得能改变局势的证据",
                    f"{protagonist}抵达新地点后发现证据被转移；{ally}与{neutral_faction}交换情报；{antagonist}制造阻碍迫使主角选择公开或隐藏真相；{protagonist}选择保留关键证据，结果让局势转向下一轮对抗",
                    f"证据中出现一个与{protagonist}过去有关的名字",
                    f"下一章必须解释第 {chapter} 章证据中的名字，并让主角付出代价",
                )
            )

    instructions = []
    for chapter in range(1, target_chapters + 1):
        objective, key_events, hook, continuity_seed = instruction_templates[(chapter - 1) % len(instruction_templates)]
        instructions.append({
            "chapter_number": chapter,
            "objective": objective,
            "key_events": key_events,
            "plots_to_plant": ["裁衡系统真实目的", "异常转嫁协议"] if chapter == 1 else [],
            "plots_to_resolve": [],
            "emotion_tone": terms["tone"],
            "ending_hook": hook,
            "continuity_seed": continuity_seed,
            "word_target": target_words,
        })

    return {
        "_meta": {
            "source": "scaffold_fallback",
            "quality_status": "scaffold_fallback",
            "warnings": ["此草案由系统兜底模板生成，不建议直接批准"],
        },
        "project_updates": {"description": _project_description_from_body(body)},
        "world_settings": [
            {
                "title": "故事基础世界",
                "category": "世界观",
                "content": terms["setting"],
            },
            {
                "title": terms["power"],
                "category": "力量规则",
                "content": f"故事的核心成长依赖{terms['resource']}。主角需要通过行动、判断和代价逐步掌握更高层级的力量。",
            },
            {
                "title": "冲突结构",
                "category": "叙事规则",
                "content": terms["conflict"],
            },
            {
                "title": "首批章节舞台",
                "category": "场景",
                "content": f"首批章节围绕《{title}》的核心卖点展开，从主角个人处境切入，逐步扩展到组织、资源和主线谜团。",
            },
        ],
        "characters": [
            {
                "name": protagonist,
                "role": "protagonist",
                "description": f"《{title}》的核心人物，当前目标是在制度压力和现实危机中保住自己的判断权。\n内在矛盾/秘密: 他既依赖系统能力，又怀疑系统会把人训练成工具。\n与主角利益关系: 本人，所有组织选择都直接影响他的同化风险。",
                "traits": "克制、警觉、共情尚未完全磨损、会用规则漏洞保护普通人",
            },
            {
                "name": ally,
                "role": "supporting",
                "description": f"{primary_faction}的数据分析员，当前目标是查清异常任务记录被篡改的来源。\n内在矛盾/秘密: 她的家人曾被善后程序清洗记忆，因此不完全信任处理局。\n与主角利益关系: 帮助{protagonist}取得情报，也要求他别把普通人当任务代价。",
                "traits": "敏锐、嘴硬、技术强、对制度有保留的忠诚",
            },
            {
                "name": antagonist,
                "role": "antagonist",
                "description": f"{rival_faction}负责人，当前目标是把{protagonist}的偏离行为压回系统流程。\n内在矛盾/秘密: 他知道系统存在漏洞，但认为牺牲少数人是维持现实稳定的必要成本。\n与主角利益关系: 代表处理局强硬秩序，持续阻断主角的第三条路。",
                "traits": "冷静、强硬、擅长审讯和流程压制",
            },
            {
                "name": observer,
                "role": "supporting",
                "description": f"{hidden_faction}联络人，当前目标是观察{protagonist}是否能偏离系统最优解。\n内在矛盾/秘密: 他曾经也是修正员，保留着被判定失败的任务记忆。\n与主角利益关系: 提供线索但不直接救人，逼迫主角自己做选择。",
                "traits": "克制、讽刺、信息量大、立场暧昧",
            },
        ],
        "factions": [
            {
                "name": primary_faction,
                "type": "官方一线机构",
                "description": f"掌握修正系统、任务调度和异常善后资源。当前阶段要求{protagonist}完成低级异常任务，同时限制他接触高层情报。\n资源/手段: 任务权限、异常档案、记忆清洗队、修正装备。\n当前阶段行动: 继续派发任务并记录主角的同化数据。",
                "relationship_with_protagonist": "工作所属，同时是限制主角真相探索的制度来源",
            },
            {
                "name": rival_faction,
                "type": "内部监管势力",
                "description": f"负责审查修正员偏离行为和封存敏感任务。当前阶段将{protagonist}列入观察名单。\n资源/手段: 审讯权限、任务冻结、记忆审查、处分流程。\n当前阶段行动: 通过程序压力迫使主角交出异常调查证据。",
                "relationship_with_protagonist": "早期直接冲突对象",
            },
            {
                "name": hidden_faction,
                "type": "主线谜团势力",
                "description": f"记录异常、系统和人类选择之间的关系。当前阶段只向{protagonist}投放线索，不承诺帮助。\n资源/手段: 未登记异常坐标、同化样本档案、失踪修正员记录。\n当前阶段行动: 测试主角是否会为了现实世界违背系统指令。",
                "relationship_with_protagonist": "观察、试探、潜在合作但不可信",
            },
            {
                "name": neutral_faction,
                "type": "资源/情报势力",
                "description": f"由异常幸存者、旧城区居民和被边缘化研究者组成。当前阶段掌握官方没有登记的异常后果。\n资源/手段: 民间目击记录、地下避难点、未清洗记忆者。\n当前阶段行动: 在保护自身安全的前提下向{protagonist}提供碎片证词。",
                "relationship_with_protagonist": "可争取对象",
            },
        ],
        "outlines": [
            {
                "chapters_range": f"1-{arc_mid}",
                "title": "开局压迫与觉醒",
                "content": f"{premise} 阶段冲突: {protagonist}必须在{primary_faction}任务规则和普通人安全之间做选择。转折: 他发现系统的修正成功会掩盖现实代价。阶段结果: 主角被监管关注，但保留了第一份质疑系统的证据。",
                "level": "arc",
                "sequence": 1,
            },
            {
                "chapters_range": f"{arc_mid + 1}-{arc_two_end}" if arc_mid + 1 <= arc_two_end else f"{arc_mid}",
                "title": "能力验证与势力入场",
                "content": f"阶段冲突: {protagonist}追查异常善后链条时遭到{rival_faction}压制。转折: {hidden_faction}投放未登记坐标，证明异常处理存在转嫁机制。阶段结果: 主角获得线索，同时同化度和处分风险一起上升。",
                "level": "arc",
                "sequence": 2,
            },
            {
                "chapters_range": f"{arc_two_end + 1}-{target_chapters}" if arc_two_end + 1 <= target_chapters else f"{target_chapters}",
                "title": "阶段高潮与主线揭示",
                "content": f"阶段冲突: 处理局要求{protagonist}牺牲局部现实稳定来完成系统定义的修正。转折: 白塔档案显示异常并非随机出现，而是会响应人类选择。阶段结果: 主角第一次明确偏离系统规则，把系统当作可利用但不可服从的工具。",
                "level": "arc",
                "sequence": 3,
            },
        ],
        "plot_holes": [
            {
                "code": "PH-001",
                "type": "主线谜团",
                "title": "裁衡系统为何选择林泽",
                "description": f"触发场景: {protagonist}第一次违规后仍获得任务结算。读者表象: 系统像是在容忍新人错误。真相方向: 裁衡需要观察能偏离最优解的样本。预计兑现: 第 {min(target_chapters, 10)} 章以后逐步揭示。",
                "planted_chapter": 1,
                "planned_resolve_chapter": min(target_chapters, 10),
                "status": "planted",
            },
            {
                "code": "PH-002",
                "type": "势力伏笔",
                "title": "白塔观测会的可偏离样本档案",
                "description": f"触发场景: {observer}向{protagonist}投放未登记坐标。读者表象: 白塔像是在帮助主角。真相方向: 白塔只记录选择结果，并不保证人类安全。预计兑现: 第 {min(target_chapters, 12)} 章后揭露观测目的。",
                "planted_chapter": 2,
                "planned_resolve_chapter": min(target_chapters, 12),
                "status": "planted",
            },
            {
                "code": "PH-003",
                "type": "关系伏笔",
                "title": f"{ally}家属被记忆清洗的旧案",
                "description": f"触发场景: {ally}拒绝执行一次善后命令。读者表象: 她只是同情普通人。真相方向: 她的家属曾是异常善后牺牲者。预计兑现: 第 {min(target_chapters, 15)} 章后影响她与主角的信任。",
                "planted_chapter": 3,
                "planned_resolve_chapter": min(target_chapters, 15),
                "status": "planted",
            },
        ],
        "instructions": instructions,
    }


def _fill_missing_genesis_sections(body: GenesisGenerateRequest, draft: dict | None) -> dict:
    """Fill any remaining required Genesis sections from a local editable scaffold.

    v6.6.3: If any section is filled from scaffold, mark the draft with
    _meta.scaffold_sections to track which parts are fallback.
    """
    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft)) or {}
    scaffold = _generate_genesis_scaffold(body)

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
        # v6.6.4: Normalize key_events array into structured text without losing info
        raw_key_events = item.get("key_events", "")
        if isinstance(raw_key_events, list):
            key_events = "；".join(str(ev) for ev in raw_key_events if ev)
        else:
            key_events = _as_text(raw_key_events)
        return {
            **item,
            "chapter_number": chapter_number,
            "objective": _as_text(item.get("objective", "")),
            "key_events": key_events,
            "emotion_tone": _as_text(item.get("emotion_tone", "")),
            "ending_hook": _as_text(item.get("ending_hook", "")),
            "continuity_seed": _as_text(item.get("continuity_seed", "")),
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
    }


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


async def _generate_real_draft(body: GenesisGenerateRequest, settings) -> dict:
    """Generate a genesis draft using real LLM."""
    llm = _build_genesis_llm(settings)
    title_contract = build_title_contract({
        "name": body.title,
        "genre": body.genre,
        "description": body.premise,
        "target_words": body.target_words,
        "total_chapters_planned": body.target_chapters,
    })
    # v6.3.1: When premise is empty, ask the LLM to infer from title + genre.
    premise_display = body.premise.strip() or f"基于标题《{body.title}》和类型「{body.genre}」自动推断故事前提"
    prompt = (
        "你是一个小说项目设定专家。根据以下创作意图，生成完整的项目圣经草案。\n"
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {premise_display}\n"
        "创世范围说明: 本次需要生成整本书的底盘设定，并只展开首批章节指令。\n"
        f"首批章节规划范围: 前 {body.target_chapters} 章，首批合计约 {body.target_words} 字\n"
        "注意: 上面的章数和字数不是整本书总篇幅，后续章节会通过章节批次规划继续延展。\n"
        f"读者: {body.target_audience}\n"
        f"风格: {body.style_preference}\n"
        f"约束: {body.constraints}\n\n"
        f"{title_contract}\n\n"
        "请返回严格的 JSON 格式（不要用 Markdown 代码块包裹），包含以下字段:\n"
        "- project_updates: {\"description\": \"项目描述\"}\n"
        "- world_settings: [{\"title\": \"\", \"category\": \"\", \"content\": \"\"}]\n"
        "- characters: [{\"name\": \"\", \"role\": \"protagonist|antagonist|supporting\", \"description\": \"\", \"traits\": \"\"}]\n"
        "- factions: [{\"name\": \"\", \"type\": \"\", \"description\": \"\", \"relationship_with_protagonist\": \"\"}]\n"
        "- outlines: [{\"chapters_range\": \"1-3\", \"title\": \"\", \"content\": \"\", \"level\": \"arc\", \"sequence\": 1}]\n"
        "- plot_holes: [{\"code\": \"PH-001\", \"type\": \"\", \"title\": \"\", \"description\": \"\", \"planted_chapter\": 1, \"planned_resolve_chapter\": 10, \"status\": \"planted\"}]\n"
        "- instructions: [{\"chapter_number\": 1, \"objective\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"ending_hook\": \"\", \"continuity_seed\": \"\", \"word_target\": 3000}]\n\n"
        "【章节指令深度要求 - 必须逐章具体】\n"
        "每章 instructions 必须包含：\n"
        "- chapter_number: 章序号\n"
        "- objective: 具体到本章的主角目标、遇到的阻力、以及结果变化。禁止使用\"扩大冲突/推动剧情/获得主动权/进入复杂局面\"等抽象表达。\n"
        "- key_events: 至少 3 个具体事件，不能只有\"冲突升级/主角成长/势力入场\"。必须写出谁、在哪里、做了什么、产生了什么后果。\n"
        "- emotion_tone: 本章情感基调\n"
        "- ending_hook: 本章结尾钩子，明确写出悬念或转折\n"
        "- continuity_seed: 给下一章必须继承的悬念、时间或任务\n"
        "- word_target: 本章目标字数\n"
        "相邻章节的 objective 和 key_events 不得复用同一抽象目标或同一套事件。\n\n"
        "【角色深度要求】\n"
        "每个角色必须包含：\n"
        "- 具体姓名（不能是\"主角\"\"反派\"等通用称呼）\n"
        "- 角色功能（protagonist/antagonist/supporting）\n"
        "- 当前欲望/目标\n"
        "- 内在矛盾或秘密\n"
        "- 与主角的利益关系\n\n"
        "【势力深度要求】\n"
        "每个势力必须包含：\n"
        "- 具体名称（不能是\"主角阵营\"\"敌对势力\"等通用称呼）\n"
        "- 资源/手段\n"
        "- 对主角的态度\n"
        "- 当前阶段会采取的行动\n\n"
        "【伏笔深度要求】\n"
        "每个伏笔必须包含：\n"
        "- 触发场景\n"
        "- 读者看到的表象\n"
        "- 真相方向\n"
        "- 预计推进/兑现章节\n\n"
        "【大纲深度要求】\n"
        "大纲不能只写\"前期/中期/高潮\"等阶段标签，必须写出：\n"
        "- 阶段冲突（谁和谁因什么发生冲突）\n"
        "- 转折（什么事件打破了原有平衡）\n"
        "- 阶段结果（这一阶段结束时主角和局势发生了什么变化）\n\n"
        "重要规则：\n"
        "1. 输出必须是纯 JSON，不要添加任何注释、解释或 Markdown 标记\n"
        "2. 不要在 JSON 中使用尾逗号\n"
        "3. 所有字符串值必须使用双引号\n"
        "4. 数值字段（planted_chapter, planned_resolve_chapter, chapter_number, word_target, sequence）必须是整数，不要用引号包裹\n"
        "5. 世界观、角色、大纲和章节指令必须严格兑现【书名契约】，不得生成与书名无关的通用故事模板\n"
    )

    return await asyncio.to_thread(
        llm.invoke_json,
        [
            {
                "role": "system",
                "content": "你只输出纯 JSON 对象，不要输出任何 Markdown 代码块、注释或解释文字。不要在 JSON 中添加尾逗号。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=7000,
        max_retries=2,
    )


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
        "- instructions: [{\"chapter_number\": 1, \"objective\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"word_target\": 3000}]\n\n"
        "要求：\n"
        "1. 角色至少包含主角、核心盟友/女主/重要配角、主要反派或对立势力人物，必须有具体姓名、目标、矛盾和利益关系。\n"
        "2. 大纲至少覆盖首批章节范围，必须包含阶段冲突、转折和阶段结果。\n"
        "3. 章节指令必须覆盖首批每一章，包含 objective、key_events、ending_hook、continuity_seed。\n"
        "4. 输出纯 JSON，不要 Markdown、解释、注释或尾逗号。"
    )


async def _complete_real_genesis_draft(
    body: GenesisGenerateRequest,
    settings,
    draft: dict,
) -> dict:
    """Repair incomplete real Genesis output before it becomes reviewable."""
    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft)) or {}
    missing = _missing_required_genesis_sections(normalized)
    if not missing:
        return normalized

    llm = _build_genesis_llm(settings)
    for _attempt in range(2):
        prompt = _build_genesis_completion_prompt(body, normalized, missing)
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
        else "recovered_from_provider_error"
        if reason == "provider_error"
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


async def _generate_real_draft_with_scaffold_fallback(
    body: GenesisGenerateRequest,
    settings,
) -> dict:
    """Generate Genesis with real LLM, falling back for recoverable provider failures."""
    from ...llm.openai_compatible import (
        LLMConnectionError,
        LLMTimeoutError,
        OutputValidationError,
        RateLimitError,
    )

    try:
        draft = await _generate_real_draft(body, settings)
        return await _complete_real_genesis_draft(body, settings, draft)
    except OutputValidationError as exc:
        logger.warning(
            "Genesis real LLM returned invalid JSON; using scaffold fallback title=%s genre=%s",
            body.title,
            body.genre,
            exc_info=True,
        )
        return _build_genesis_recovery_draft(
            body,
            reason="invalid_json",
            error_message=str(exc),
        )
    except (LLMConnectionError, LLMTimeoutError, RateLimitError) as exc:
        logger.warning(
            "Genesis real LLM provider failed; using local recovery title=%s genre=%s",
            body.title,
            body.genre,
            exc_info=True,
        )
        return _build_genesis_recovery_draft(
            body,
            reason="provider_error",
            error_message=str(exc),
        )


def _apply_genesis_to_project(repo, project_id: str, draft: dict) -> dict:
    """Apply an approved genesis draft to formal tables.

    Returns a summary of what was applied.
    """
    if not isinstance(draft, dict):
        raise ValueError("创世草案必须是 JSON 对象")

    applied = {
        "project_updated": False,
        "world_settings_created": 0,
        "characters_created": 0,
        "factions_created": 0,
        "outlines_created": 0,
        "plot_holes_created": 0,
        "instructions_created": 0,
    }

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
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

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
            return error_response(
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
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

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

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取创世记录失败: {str(e)[:200]}")


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
    """
    from ..deps import get_repo

    # Extract force_apply flags from body if provided
    force_apply = body.force_apply if body else False
    confirm_quality_risk = body.confirm_quality_risk if body else False

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        genesis = repo.get_genesis_run(genesis_id)
        if not genesis:
            return error_response("GENESIS_NOT_FOUND", "创世记录不存在")

        if genesis["project_id"] != project_id:
            return error_response("GENESIS_NOT_FOUND", "创世记录不属于该项目")

        if genesis["status"] != "generated":
            return error_response(
                "INVALID_GENESIS_STATUS",
                f"只能批准已生成的创世记录，当前状态: {genesis['status']}",
            )

        # Parse draft
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

        # v6.6.3: Block if quality gate failed (unless force_apply)
        if not quality_report.passed:
            if not (force_apply and confirm_quality_risk):
                return error_response(
                    "GENESIS_QUALITY_BLOCKED",
                    "创世草案质量不足，请重新生成或人工补全后再批准",
                    {
                        "quality_report": _quality_report_payload(quality_report)
                    },
                )

        # Apply to formal tables
        applied = _apply_genesis_to_project(repo, project_id, draft)

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
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        genesis = repo.get_genesis_run(genesis_id)
        if not genesis:
            return error_response("GENESIS_NOT_FOUND", "创世记录不存在")

        if genesis["project_id"] != project_id:
            return error_response("GENESIS_NOT_FOUND", "创世记录不属于该项目")

        if genesis["status"] not in ("generated", "failed"):
            return error_response(
                "INVALID_GENESIS_STATUS",
                f"只能拒绝已生成或失败的创世记录，当前状态: {genesis['status']}",
            )

        repo.update_genesis_run(genesis_id, {"status": "rejected"})

        return envelope_response({
            "genesis_id": genesis_id,
            "status": "rejected",
        })

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

        applied = _apply_genesis_to_project(repo, body.project_id, draft)

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
