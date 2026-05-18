"""Genesis API endpoints for project bible generation."""

from __future__ import annotations

import json
import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ...agent_runtime.title_contract import build_title_contract
from ...llm.provider import is_configured_live_provider
from ...quality.genesis_quality_gate import evaluate_genesis_draft

router = APIRouter()


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
    """Evaluate and serialize quality for a persisted genesis run."""
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
    return _quality_report_payload(quality_report)


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
            return normalized
        if isinstance(value, str):
            try:
                value = json.loads(value)
                continue
            except json.JSONDecodeError:
                return None
        return None
    return _normalize_genesis_draft(value)


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
    normalized = _normalize_genesis_draft(draft)
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
            merged[key] = list(merged.get(key) or []) + incoming
        elif key not in merged:
            merged[key] = []

    return merged


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

    instructions = []
    for chapter in range(1, target_chapters + 1):
        if chapter == 1:
            objective = "建立主角处境、核心目标和第一处关键冲突"
            key_events = "主角登场；展示现实压力；触发核心机会或危机；埋下主线谜团"
            hook = "主角发现事件背后还有更大的力量正在逼近"
        elif chapter <= arc_mid:
            objective = "完成开局冲突升级，让主角获得初步主动权"
            key_events = "主角尝试解决眼前困境；盟友或对手登场；第一次能力/策略展示；反派压力升级"
            hook = "新的敌意或更高层级势力注意到主角"
        elif chapter <= arc_two_end:
            objective = "扩大冲突范围，推动主角进入更复杂的势力局面"
            key_events = "主角主动出击；关键资源或情报出现；对手设局；主角用成长成果反击"
            hook = "主线谜团出现新的证据"
        else:
            objective = "收束首批章节阶段性冲突，并引出下一阶段主线"
            key_events = "阶段反派被击退；主角关系网变化；核心谜团推进；更大危机浮出水面"
            hook = "真正的幕后力量露出线索"
        instructions.append({
            "chapter_number": chapter,
            "objective": objective,
            "key_events": key_events,
            "plots_to_plant": ["主角身世/能力来源", "幕后势力动机"] if chapter == 1 else [],
            "plots_to_resolve": [],
            "emotion_tone": terms["tone"],
            "ending_hook": hook,
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
                "name": "主角",
                "role": "protagonist",
                "description": f"《{title}》的核心人物，初始处于压力或困境中，但拥有改变命运的关键潜力。",
                "traits": "隐忍、聪明、目标感强、会在冲突中快速成长",
            },
            {
                "name": "核心盟友",
                "role": "supporting",
                "description": "较早理解或帮助主角的人物，承担情报、情感支持或行动协作功能。",
                "traits": "可靠、敏锐、与主角形成互补",
            },
            {
                "name": "阶段反派",
                "role": "antagonist",
                "description": "首批章节中直接压迫主角的人物，代表既有秩序或敌对利益。",
                "traits": "强势、自负、会推动主角被迫反击",
            },
            {
                "name": "神秘观察者",
                "role": "supporting",
                "description": "掌握更高层级信息的人物，负责把故事从局部冲突引向主线谜团。",
                "traits": "神秘、克制、目的不明",
            },
        ],
        "factions": [
            {
                "name": "主角阵营",
                "type": "成长阵营",
                "description": "围绕主角逐步形成的行动网络，初期弱小但机动性强。",
                "relationship_with_protagonist": "核心所属",
            },
            {
                "name": "既有权力方",
                "type": "压迫/竞争势力",
                "description": "掌握资源和规则解释权的势力，对主角的崛起保持警惕或敌意。",
                "relationship_with_protagonist": "早期冲突对象",
            },
            {
                "name": "隐秘组织",
                "type": "主线谜团势力",
                "description": "隐藏在表层冲突后的组织，掌握更深层秘密。",
                "relationship_with_protagonist": "观察、试探、潜在敌对",
            },
            {
                "name": "中立资源方",
                "type": "资源/情报势力",
                "description": "拥有关键资源或信息，会根据利益变化与主角合作或对立。",
                "relationship_with_protagonist": "可争取对象",
            },
        ],
        "outlines": [
            {
                "chapters_range": f"1-{arc_mid}",
                "title": "开局压迫与觉醒",
                "content": f"{premise} 首批开局聚焦主角处境、核心机会出现以及第一次反击。",
                "level": "arc",
                "sequence": 1,
            },
            {
                "chapters_range": f"{arc_mid + 1}-{arc_two_end}" if arc_mid + 1 <= arc_two_end else f"{arc_mid}",
                "title": "能力验证与势力入场",
                "content": "主角的行动引起外部势力注意，冲突从个人层面扩展到资源和组织层面。",
                "level": "arc",
                "sequence": 2,
            },
            {
                "chapters_range": f"{arc_two_end + 1}-{target_chapters}" if arc_two_end + 1 <= target_chapters else f"{target_chapters}",
                "title": "阶段高潮与主线揭示",
                "content": "首批章节收束阶段冲突，同时揭示更高层级的主线谜团和后续威胁。",
                "level": "arc",
                "sequence": 3,
            },
        ],
        "plot_holes": [
            {
                "code": "PH-001",
                "type": "主线谜团",
                "title": "主角关键能力或机会的来源",
                "description": "主角获得改变命运机会的真正来源尚未完全解释，后续需要逐步揭示。",
                "planted_chapter": 1,
                "planned_resolve_chapter": min(target_chapters, 10),
                "status": "planted",
            },
            {
                "code": "PH-002",
                "type": "势力伏笔",
                "title": "隐秘组织为何关注主角",
                "description": "更高层级势力对主角表现出异常关注，其真实目的需要后续推进。",
                "planted_chapter": 2,
                "planned_resolve_chapter": min(target_chapters, 12),
                "status": "planted",
            },
            {
                "code": "PH-003",
                "type": "关系伏笔",
                "title": "核心盟友的隐藏立场",
                "description": "核心盟友与主角的关系将随着冲突升级接受考验。",
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
    normalized = _normalize_genesis_draft(draft) or {}
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

    return normalized


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
        return {
            **item,
            "name": name,
            "role": _normalize_character_role(_as_text(item.get("role", "supporting"))),
            "description": _as_text(item.get("description", "")),
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
        return item
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
        return {
            **item,
            "level": _as_text(item.get("level", "arc")) or "arc",
            "sequence": _as_int(item.get("sequence"), index),
            "title": _as_text(item.get("title", "")) or f"大纲 {index}",
            "content": _as_text(item.get("content", "")),
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
        return {
            **item,
            "code": code,
            "type": _as_text(item.get("type", "")),
            "title": _as_text(item.get("title", "")) or code,
            "description": _as_text(item.get("description", "")),
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
        return {
            **item,
            "chapter_number": chapter_number,
            "objective": _as_text(item.get("objective", "")),
            "key_events": _as_text(item.get("key_events", "")),
            "emotion_tone": _as_text(item.get("emotion_tone", "")),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "chapter_number": index,
        "objective": text,
        "key_events": text,
        "emotion_tone": "",
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
        "- instructions: [{\"chapter_number\": 1, \"objective\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"word_target\": 3000}]\n\n"
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
        "1. 角色至少包含主角、核心盟友/女主/重要配角、主要反派或对立势力人物。\n"
        "2. 大纲至少覆盖首批章节范围。\n"
        "3. 章节指令必须覆盖首批每一章。\n"
        "4. 输出纯 JSON，不要 Markdown、解释、注释或尾逗号。"
    )


async def _complete_real_genesis_draft(
    body: GenesisGenerateRequest,
    settings,
    draft: dict,
) -> dict:
    """Repair incomplete real Genesis output before it becomes reviewable."""
    normalized = _normalize_genesis_draft(draft) or {}
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
        normalized_patch = _normalize_genesis_draft(patch)
        normalized = _merge_genesis_drafts(normalized, normalized_patch)
        missing = _missing_required_genesis_sections(normalized)
        if not missing:
            return normalized

    return _fill_missing_genesis_sections(body, normalized)


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
        instruction_data = {
            **inst,
            "objective": _as_text(inst.get("objective", "")),
            "key_events": _as_text(inst.get("key_events", "")),
            "emotion_tone": _as_text(inst.get("emotion_tone", "")),
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
                draft = await _generate_real_draft(body, settings)
                draft = await _complete_real_genesis_draft(body, settings, draft)
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
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        genesis = repo.get_latest_genesis_run(project_id)
        if not genesis:
            return envelope_response(None)

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
                    "创世草案质量门未通过，请重新生成或人工补全",
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
        if latest and latest["status"] == "running":
            return error_response("GENESIS_IN_PROGRESS", "已有正在运行的创世任务，请等待完成")

        input_json = json.dumps(body.model_dump(), ensure_ascii=False)
        genesis_run = repo.create_genesis_run(project_id, input_json, status="running")

        try:
            if llm_mode == "stub":
                draft = _generate_stub_draft(body)
            else:
                draft = await _generate_real_draft(body, settings)
                draft = await _complete_real_genesis_draft(body, settings, draft)
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
                    "创世草案质量门未通过，请重新生成或人工补全。如需强制应用，请设置 force_apply=true 和 confirm_quality_risk=true",
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
