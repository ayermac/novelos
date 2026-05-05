"""Autonomous Production Loop API endpoints.

v5.5.3: Provides next-action guidance and AI auto-fill for project production.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class AutoFillRequest(BaseModel):
    """Request for AI auto-fill of missing project context."""

    scope: str = "missing_context"  # missing_context | arc_plan | chapter_instructions
    chapter_start: int = 1
    chapter_end: int = 10
    confirm: bool = False


class ArcPlanRequest(BaseModel):
    """Request for arc planning over a chapter range."""

    chapter_start: int = 1
    chapter_end: int = 10
    confirm: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_approved_genesis(repo, project_id: str) -> bool:
    """Check if project has an approved genesis run."""
    latest = repo.get_latest_genesis_run(project_id)
    return latest is not None and latest.get("status") == "approved"


def _has_pending_genesis(repo, project_id: str) -> bool:
    """Check if project has a pending/generated genesis draft awaiting review."""
    latest = repo.get_latest_genesis_run(project_id)
    return latest is not None and latest.get("status") == "generated"


def _has_running_genesis(repo, project_id: str) -> bool:
    """Check if project has a running genesis."""
    latest = repo.get_latest_genesis_run(project_id)
    return latest is not None and latest.get("status") == "running"


def _get_blocking_chapter(repo, project_id: str) -> dict | None:
    """Find a chapter in blocking or revision status."""
    chapters = repo.list_chapters(project_id)
    for ch in chapters:
        if ch.get("status") in ("blocking", "revision"):
            return ch
    return None


def _get_stuck_run(repo, project_id: str) -> dict | None:
    """Find a stuck workflow run (failed/blocked status)."""
    runs = repo.get_workflow_runs_for_project(project_id, limit=20)
    for run in runs:
        if run.get("status") in ("failed", "blocked"):
            return run
    return None


def _has_pending_memory_updates(repo, project_id: str) -> bool:
    """Check for pending or partial memory update batches."""
    batches = repo.list_memory_batches(project_id)
    for b in batches:
        if b.get("status") in ("pending", "partial"):
            return True
    # Also check for items with pending status
    items = repo.list_memory_items_by_project(project_id, status="pending")
    return len(items) > 0


def _build_health(repo, project_id: str, current_chapter: int) -> dict:
    """Build health snapshot for a project."""
    project = repo.get_project(project_id)
    world_settings = repo.list_world_settings(project_id)
    characters = repo.list_characters(project_id, include_inactive=True)
    outlines = repo.list_outlines(project_id)
    instruction = repo.get_instruction_by_chapter(project_id, current_chapter)
    latest_genesis = repo.get_latest_genesis_run(project_id)

    return {
        "has_project": project is not None,
        "has_genesis": latest_genesis is not None,
        "has_approved_genesis": latest_genesis is not None and latest_genesis.get("status") == "approved",
        "has_world_settings": len(world_settings) > 0,
        "has_characters": len(characters) > 0,
        "has_outlines": len(outlines) > 0,
        "has_instructions_for_current_chapter": instruction is not None and bool(instruction.get("objective")),
        "has_pending_memory_updates": _has_pending_memory_updates(repo, project_id),
        "has_blocking_chapter": _get_blocking_chapter(repo, project_id) is not None,
        "has_stuck_run": _get_stuck_run(repo, project_id) is not None,
    }


def _build_missing(health: dict, project_id: str, current_chapter: int) -> list[dict]:
    """Build list of missing items with AI action suggestions."""
    missing = []

    if not health["has_approved_genesis"]:
        missing.append({
            "key": "genesis",
            "label": "项目创世设定",
            "severity": "blocking",
            "manual_url": f"/projects/{project_id}?module=genesis",
            "ai_action": {
                "key": "generate_genesis",
                "label": "让 AI 生成项目设定",
            },
        })

    if health["has_approved_genesis"]:
        if not health["has_world_settings"]:
            missing.append({
                "key": "world_settings",
                "label": "世界观",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=worldview",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": "让 AI 补齐世界观",
                },
            })

        if not health["has_characters"]:
            missing.append({
                "key": "characters",
                "label": "角色",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=characters",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": "让 AI 补齐角色",
                },
            })

        if not health["has_outlines"]:
            missing.append({
                "key": "outlines",
                "label": "大纲",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=outline",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": "让 AI 补齐大纲",
                },
            })

        if not health["has_instructions_for_current_chapter"]:
            missing.append({
                "key": "instructions",
                "label": f"第{current_chapter}章写作指令",
                "severity": "blocking",
                "manual_url": f"/projects/{project_id}?module=instructions",
                "ai_action": {
                    "key": "generate_missing_context",
                    "label": f"让 AI 补齐第{current_chapter}章指令",
                },
            })

    return missing


def _determine_next_action(repo, project_id: str, health: dict, current_chapter: int) -> dict:
    """Determine the next production action based on project state."""

    # 1. Recover blocked runs / blocking chapters first
    if health["has_stuck_run"] or health["has_blocking_chapter"]:
        return {
            "key": "recover_blocked_run",
            "label": "恢复阻塞运行",
            "description": "检测到阻塞章节或失败的运行，建议重置后重试。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/chapters/{current_chapter}/reset",
            "method": "POST",
            "requires_confirmation": True,
        }

    # 2. Genesis flow
    if not health["has_approved_genesis"]:
        if _has_running_genesis(repo, project_id):
            return {
                "key": "wait_genesis",
                "label": "等待创世完成",
                "description": "AI 正在生成项目设定，请稍候。",
                "primary": True,
                "action_url": f"/api/projects/{project_id}/genesis/latest",
                "method": "GET",
                "requires_confirmation": False,
            }
        if _has_pending_genesis(repo, project_id):
            return {
                "key": "review_genesis",
                "label": "审核创世草案",
                "description": "项目设定已生成，请审核后批准应用。",
                "primary": True,
                "action_url": f"/api/projects/{project_id}/genesis/latest",
                "method": "GET",
                "requires_confirmation": False,
            }
        return {
            "key": "generate_genesis",
            "label": "生成项目设定",
            "description": "项目缺少基础设定，让 AI 一键生成世界观、角色、大纲等。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/genesis/generate",
            "method": "POST",
            "requires_confirmation": True,
        }

    # 3. Missing context after approved genesis
    missing_items = _build_missing(health, project_id, current_chapter)
    if missing_items:
        return {
            "key": "generate_missing_context",
            "label": "补齐缺失资料",
            "description": "项目还缺少部分资料，让 AI 自动补齐。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/production/auto-fill",
            "method": "POST",
            "requires_confirmation": True,
        }

    # 4. Memory updates
    if health["has_pending_memory_updates"]:
        return {
            "key": "apply_memory_updates",
            "label": "应用记忆更新",
            "description": "有待处理的记忆更新，建议审核并应用。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/memory-updates",
            "method": "GET",
            "requires_confirmation": False,
        }

    # 5. Chapter generation flow
    chapter = repo.get_chapter(project_id, current_chapter)
    chapter_status = chapter.get("status") if chapter else "planned"

    if chapter_status in ("planned", "scripted", "drafted", "polished", "revision"):
        return {
            "key": "generate_chapter",
            "label": f"生成第 {current_chapter} 章",
            "description": "资料已就绪，开始生成章节内容。",
            "primary": True,
            "action_url": f"/api/run",
            "method": "POST",
            "requires_confirmation": True,
        }

    if chapter_status in ("reviewed", "awaiting_publish"):
        return {
            "key": "review_chapter",
            "label": f"审核/发布第 {current_chapter} 章",
            "description": "章节已生成并通过审核，请最终确认发布。",
            "primary": True,
            "action_url": f"/api/projects/{project_id}/chapters/{current_chapter}",
            "method": "GET",
            "requires_confirmation": False,
        }

    if chapter_status == "published":
        # Check if there's a next chapter
        next_ch = current_chapter + 1
        next_chapter = repo.get_chapter(project_id, next_ch)
        if next_chapter is None:
            return {
                "key": "generate_arc_plan",
                "label": f"规划第 {next_ch} 章及后续",
                "description": "当前章节已发布，需要为下一批次生成章节规划。",
                "primary": True,
                "action_url": f"/api/projects/{project_id}/production/arc-plan",
                "method": "POST",
                "requires_confirmation": True,
            }
        return {
            "key": "continue_next_chapter",
            "label": f"继续生成第 {next_ch} 章",
            "description": "当前章节已发布，继续下一章。",
            "primary": True,
            "action_url": f"/api/run",
            "method": "POST",
            "requires_confirmation": True,
        }

    return {
        "key": "none",
        "label": "暂无操作",
        "description": "项目当前没有明确的下一步生产动作。",
        "primary": False,
        "action_url": "",
        "method": "GET",
        "requires_confirmation": False,
    }


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/production-next")
async def get_production_next(request: Request, project_id: str) -> EnvelopeResponse:
    """Get the next production action for a project.

    Returns current project health, missing items, and a recommended next action.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        current_chapter = project.get("current_chapter", 1)

        health = _build_health(repo, project_id, current_chapter)
        missing = _build_missing(health, project_id, current_chapter)
        next_action = _determine_next_action(repo, project_id, health, current_chapter)

        # Build secondary actions
        actions = []
        if next_action["key"] != "generate_genesis" and not health["has_approved_genesis"]:
            actions.append({
                "key": "generate_genesis",
                "label": "生成项目设定",
                "description": "重新生成项目基础设定",
                "action_url": f"/api/projects/{project_id}/genesis/generate",
                "method": "POST",
            })
        if next_action["key"] != "generate_arc_plan" and health["has_approved_genesis"]:
            actions.append({
                "key": "generate_arc_plan",
                "label": "生成章节计划",
                "description": "为指定章节范围生成大纲和指令",
                "action_url": f"/api/projects/{project_id}/production/arc-plan",
                "method": "POST",
            })

        return envelope_response({
            "project_id": project_id,
            "current_chapter": current_chapter,
            "next_action": next_action,
            "health": health,
            "missing": missing,
            "actions": actions,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取生产下一步失败: {str(e)}")


@router.post("/projects/{project_id}/production/auto-fill")
async def auto_fill(request: Request, project_id: str, body: AutoFillRequest) -> EnvelopeResponse:
    """AI auto-fill missing project context based on current gaps.

    Uses stub/deterministic generation when LLM mode is stub.
    Never overwrites existing user content.
    """
    from ..deps import get_repo, get_llm_mode, get_settings

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请设置 confirm=true 确认执行自动补齐")

        created = {
            "world_settings": 0,
            "characters": 0,
            "outlines": 0,
            "instructions": 0,
            "plot_holes": 0,
        }
        warnings: list[str] = []

        # Ensure genesis is approved; if not, suggest genesis first
        if not _has_approved_genesis(repo, project_id):
            warnings.append("项目创世尚未批准，建议先生成并批准创世设定")
            # Still allow stub fill for demo/testing

        # ── World Settings ──
        existing_ws = repo.list_world_settings(project_id)
        if len(existing_ws) == 0:
            if llm_mode == "stub":
                repo.create_world_setting(
                    project_id,
                    category="地理",
                    title="世界观基础",
                    content=f"故事发生在{project.get('genre', '奇幻')}世界中，存在多个势力和未知领域。",
                )
                repo.create_world_setting(
                    project_id,
                    category="规则",
                    title="力量体系",
                    content="修炼体系分为九个大境界，每个境界有初期、中期、后期三个小阶段。",
                )
                created["world_settings"] = 2
            else:
                warnings.append("real LLM world_settings generation not yet implemented")

        # ── Characters ──
        existing_chars = repo.list_characters(project_id, include_inactive=True)
        if len(existing_chars) == 0:
            if llm_mode == "stub":
                repo.create_character(
                    project_id,
                    name="主角",
                    role="protagonist",
                    description=f"《{project.get('name', '未命名')}》的核心人物，性格坚毅，有着不为人知的过去。",
                    traits="聪明、执着、重情义",
                )
                repo.create_character(
                    project_id,
                    name="挚友",
                    role="supporting",
                    description="主角的青梅竹马，性格开朗，擅长情报收集。",
                    traits="机智、幽默、忠诚",
                )
                repo.create_character(
                    project_id,
                    name="反派首领",
                    role="antagonist",
                    description="幕后黑手，行事隐秘，目的不明。",
                    traits="狡猾、冷酷、有魅力",
                )
                created["characters"] = 3
            else:
                warnings.append("real LLM character generation not yet implemented")

        # ── Outlines ──
        existing_outlines = repo.list_outlines(project_id)
        if len(existing_outlines) == 0:
            if llm_mode == "stub":
                repo.create_outline(
                    project_id,
                    level="arc",
                    sequence=1,
                    title="开篇",
                    content="主角出场，建立日常世界，引出核心冲突。",
                    chapters_range=f"{body.chapter_start}-{min(body.chapter_start + 2, body.chapter_end)}",
                )
                repo.create_outline(
                    project_id,
                    level="arc",
                    sequence=2,
                    title="启程",
                    content="主角踏上旅程，遇到第一个挑战和盟友。",
                    chapters_range=f"{body.chapter_start + 3}-{min(body.chapter_start + 5, body.chapter_end)}",
                )
                repo.create_outline(
                    project_id,
                    level="arc",
                    sequence=3,
                    title="第一幕高潮",
                    content="主角面对第一个重大考验，揭示更大的阴谋。",
                    chapters_range=f"{body.chapter_start + 6}-{body.chapter_end}",
                )
                created["outlines"] = 3
            else:
                warnings.append("real LLM outline generation not yet implemented")

        # ── Plot Holes ──
        existing_plots = repo.list_plot_holes(project_id)
        if len(existing_plots) == 0:
            if llm_mode == "stub":
                repo.create_plot_hole(
                    project_id,
                    code="PH-001",
                    type="悬念",
                    title="主角身世之谜",
                    description="主角的真实身份和家族秘密。",
                    planted_chapter=body.chapter_start,
                    planned_resolve_chapter=body.chapter_end + 10,
                    status="planted",
                )
                repo.create_plot_hole(
                    project_id,
                    code="PH-002",
                    type="伏笔",
                    title="神秘信物",
                    description="主角随身携带的古旧物品的来历。",
                    planted_chapter=body.chapter_start,
                    planned_resolve_chapter=body.chapter_start + 9,
                    status="planted",
                )
                created["plot_holes"] = 2
            else:
                warnings.append("real LLM plot_hole generation not yet implemented")

        # ── Instructions ──
        for ch_num in range(body.chapter_start, body.chapter_end + 1):
            existing_inst = repo.get_instruction_by_chapter(project_id, ch_num)
            if existing_inst is None:
                if llm_mode == "stub":
                    word_target = 3000
                    if project.get("target_words") and project.get("total_chapters_planned"):
                        word_target = project["target_words"] // project["total_chapters_planned"]
                    repo.create_instruction(
                        project_id,
                        chapter_number=ch_num,
                        objective=f"第 {ch_num} 章写作指令",
                        key_events=f"关键事件 {ch_num}",
                        plots_to_plant="[]",
                        plots_to_resolve="[]",
                        emotion_tone="神秘" if ch_num == 1 else "紧张",
                        ending_hook="",
                        word_target=word_target,
                        status="active",
                    )
                    created["instructions"] += 1
                else:
                    warnings.append(f"real LLM instruction generation for chapter {ch_num} not yet implemented")

        return envelope_response({
            "filled": True,
            "scope": body.scope,
            "created": created,
            "warnings": warnings,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"自动补齐失败: {str(e)}")


@router.post("/projects/{project_id}/production/arc-plan")
async def arc_plan(request: Request, project_id: str, body: ArcPlanRequest) -> EnvelopeResponse:
    """Generate arc plan (outlines + instructions) for a chapter range.

    Does not regenerate genesis. Does not overwrite confirmed base settings.
    """
    from ..deps import get_repo, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请设置 confirm=true 确认执行 arc plan")

        if body.chapter_start > body.chapter_end:
            return error_response("VALIDATION_ERROR", "chapter_start 不能大于 chapter_end")

        if not _has_approved_genesis(repo, project_id):
            return error_response("GENESIS_REQUIRED", "请先完成并批准项目创世设定")

        created = {
            "outlines": 0,
            "instructions": 0,
            "plot_holes": 0,
        }
        warnings: list[str] = []

        # Determine arc segmentation
        arc_size = 10
        num_arcs = max(1, (body.chapter_end - body.chapter_start + 1 + arc_size - 1) // arc_size)

        if llm_mode == "stub":
            # Generate arc-level outlines
            for arc_idx in range(num_arcs):
                arc_start = body.chapter_start + arc_idx * arc_size
                arc_end = min(arc_start + arc_size - 1, body.chapter_end)

                # Check if an outline already covers this range
                existing_outlines = repo.list_outlines(project_id)
                range_str = f"{arc_start}-{arc_end}"
                has_covering = any(
                    o.get("chapters_range") == range_str for o in existing_outlines
                )
                if not has_covering:
                    arc_titles = ["新篇章", "暗流涌动", "危机四伏", "真相浮现", "最终决战"]
                    arc_contents = [
                        "故事进入新阶段，角色面临新的挑战。",
                        "隐藏在暗处的势力开始行动，局势变得复杂。",
                        "多重危机同时爆发，主角陷入绝境。",
                        "关键线索串联起来，真相逐渐浮出水面。",
                        "所有矛盾集中爆发，迎来阶段性高潮。",
                    ]
                    title = arc_titles[arc_idx % len(arc_titles)]
                    content = arc_contents[arc_idx % len(arc_contents)]

                    # Find next sequence
                    max_seq = max((o.get("sequence", 0) for o in existing_outlines), default=0)

                    repo.create_outline(
                        project_id,
                        level="arc",
                        sequence=max_seq + 1,
                        title=title,
                        content=content,
                        chapters_range=range_str,
                    )
                    created["outlines"] += 1

            # Generate chapter instructions
            word_target = 3000
            if project.get("target_words") and project.get("total_chapters_planned"):
                word_target = project["target_words"] // project["total_chapters_planned"]

            for ch_num in range(body.chapter_start, body.chapter_end + 1):
                existing_inst = repo.get_instruction_by_chapter(project_id, ch_num)
                if existing_inst is None:
                    repo.create_instruction(
                        project_id,
                        chapter_number=ch_num,
                        objective=f"第 {ch_num} 章写作指令",
                        key_events=f"关键事件 {ch_num}",
                        plots_to_plant="[]",
                        plots_to_resolve="[]",
                        emotion_tone="紧张",
                        ending_hook="",
                        word_target=word_target,
                        status="active",
                    )
                    created["instructions"] += 1

            # Maybe add a new plot hole for the arc
            existing_plots = repo.list_plot_holes(project_id)
            max_ph = len(existing_plots)
            if max_ph < 5:
                repo.create_plot_hole(
                    project_id,
                    code=f"PH-{max_ph + 1:03d}",
                    type="伏笔",
                    title=f"新伏笔 {max_ph + 1}",
                    description=f"在第 {body.chapter_start}-{body.chapter_end} 章期间埋下新的线索。",
                    planted_chapter=body.chapter_start,
                    planned_resolve_chapter=body.chapter_end + 5,
                    status="planted",
                )
                created["plot_holes"] += 1
        else:
            warnings.append("real LLM arc planning not yet implemented")

        return envelope_response({
            "planned": True,
            "chapter_start": body.chapter_start,
            "chapter_end": body.chapter_end,
            "created": created,
            "warnings": warnings,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"Arc plan 生成失败: {str(e)}")
