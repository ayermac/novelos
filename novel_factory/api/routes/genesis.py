"""Genesis API endpoints for project bible generation."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


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
    from ...workflow.runner import _build_llm_router

    llm = _build_llm_router(settings, "real").for_agent("planner")
    prompt = (
        "你是一个小说项目设定专家。根据以下创作意图，生成完整的项目圣经草案。\n"
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {body.premise}\n"
        f"篇幅: {body.target_chapters}章, {body.target_words}字\n"
        f"读者: {body.target_audience}\n"
        f"风格: {body.style_preference}\n"
        f"约束: {body.constraints}\n\n"
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
    )

    return llm.invoke_json([
        {
            "role": "system",
            "content": "你只输出纯 JSON 对象，不要输出任何 Markdown 代码块、注释或解释文字。不要在 JSON 中添加尾逗号。",
        },
        {"role": "user", "content": prompt},
    ], max_retries=2)


def _apply_genesis_to_project(repo, project_id: str, draft: dict) -> dict:
    """Apply an approved genesis draft to formal tables.

    Returns a summary of what was applied.
    """
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
    if project_updates.get("description"):
        repo.update_project(project_id, description=project_updates["description"])
        applied["project_updated"] = True

    # World settings - upsert by title
    existing_ws = repo.list_world_settings(project_id)
    ws_by_title = {w["title"]: w for w in existing_ws}
    for ws in draft.get("world_settings", []):
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
    for ch in draft.get("characters", []):
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
    for f in draft.get("factions", []):
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
    for o in draft.get("outlines", []):
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
    for ph in draft.get("plot_holes", []):
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
    for inst in draft.get("instructions", []):
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

            repo.update_genesis_run(genesis_run["id"], {
                "status": "generated",
                "draft_json": json.dumps(draft, ensure_ascii=False),
            })
            genesis_run = repo.get_genesis_run(genesis_run["id"])

        except Exception as e:
            repo.update_genesis_run(genesis_run["id"], {
                "status": "failed",
                "error_message": str(e)[:500],
            })
            return error_response("GENESIS_FAILED", f"项目设定生成失败: {str(e)[:200]}")

        return envelope_response(genesis_run)

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

        return envelope_response(genesis)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取创世记录失败: {str(e)[:200]}")


@router.post("/projects/{project_id}/genesis/{genesis_id}/approve")
async def approve_genesis(
    request: Request,
    project_id: str,
    genesis_id: str,
) -> EnvelopeResponse:
    """Approve a genesis draft and write to formal tables."""
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

        if genesis["status"] != "generated":
            return error_response(
                "INVALID_GENESIS_STATUS",
                f"只能批准已生成的创世记录，当前状态: {genesis['status']}",
            )

        # Parse draft
        try:
            draft = json.loads(genesis["draft_json"])
        except (json.JSONDecodeError, TypeError):
            return error_response("INVALID_DRAFT", "创世草案数据格式错误")

        # Apply to formal tables
        applied = _apply_genesis_to_project(repo, project_id, draft)

        # Mark genesis as approved
        repo.update_genesis_run(genesis_id, {"status": "approved"})

        return envelope_response({
            "genesis_id": genesis_id,
            "status": "approved",
            "applied": applied,
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

            repo.update_genesis_run(genesis_run["id"], {
                "status": "generated",
                "draft_json": json.dumps(draft, ensure_ascii=False),
            })
            genesis_run = repo.get_genesis_run(genesis_run["id"])
        except Exception as e:
            repo.update_genesis_run(genesis_run["id"], {
                "status": "failed",
                "error_message": str(e)[:500],
            })
            return error_response("GENESIS_FAILED", f"项目设定生成失败: {str(e)[:200]}")

        return envelope_response(genesis_run)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"生成项目设定失败: {str(e)[:200]}")


@router.post("/genesis/approve")
async def approve_genesis_canonical(
    request: Request, body: GenesisApproveRequest
) -> EnvelopeResponse:
    """Canonical body-style route for genesis approve."""
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

        try:
            draft = json.loads(genesis["draft_json"])
        except (json.JSONDecodeError, TypeError):
            return error_response("INVALID_DRAFT", "创世草案数据格式错误")

        applied = _apply_genesis_to_project(repo, body.project_id, draft)
        repo.update_genesis_run(body.genesis_id, {"status": "approved"})

        return envelope_response({
            "genesis_id": body.genesis_id,
            "status": "approved",
            "applied": applied,
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
