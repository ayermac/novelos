"""Deterministic continuation planning for chapter ranges beyond genesis."""

from __future__ import annotations

from typing import Any

from ..validators.context_readiness import _outline_covers_chapter


def arc_range_for_chapter(project: dict[str, Any], chapter_number: int) -> tuple[int, int]:
    arc_start = ((chapter_number - 1) // 10) * 10 + 1
    arc_end = arc_start + 9
    total_chapters = int(project.get("total_chapters_planned") or 0)
    if total_chapters >= chapter_number:
        arc_end = min(arc_end, total_chapters)
    return arc_start, arc_end


def ensure_continuation_plan_for_chapter(
    repo: Any,
    project_id: str,
    chapter_number: int,
) -> dict[str, Any]:
    """Create next-arc planning when generation reaches a new chapter range.

    Genesis typically seeds the first 1-10 chapters. When the user continues
    into a later chapter, run entrypoints should extend the arc outline and
    chapter instructions before readiness guards block the run.
    """
    project = repo.get_project(project_id) or {}
    outlines = repo.list_outlines(project_id)
    if not outlines:
        return {"created_outlines": 0, "created_instructions": 0}

    has_covering_outline = any(
        _outline_covers_chapter(outline.get("chapters_range", ""), chapter_number)
        for outline in outlines
    )

    arc_start, arc_end = arc_range_for_chapter(project, chapter_number)
    range_str = f"{arc_start}-{arc_end}"
    created_outlines = 0
    created_instructions = 0

    if not has_covering_outline and not any(outline.get("chapters_range") == range_str for outline in outlines):
        max_sequence = max((int(outline.get("sequence") or 0) for outline in outlines), default=0)
        repo.create_outline(
            project_id=project_id,
            level="arc",
            sequence=max_sequence + 1,
            title=f"第{arc_start}-{arc_end}章续篇规划",
            content=(
                f"承接前序剧情，推进第{arc_start}至第{arc_end}章的阶段冲突、"
                "关键线索和章末钩子，保持既有世界观、角色关系与主线承诺。"
            ),
            chapters_range=range_str,
        )
        created_outlines += 1

    target_words = project.get("target_words") or 0
    total_chapters = project.get("total_chapters_planned") or 0
    word_target = int(target_words // total_chapters) if target_words and total_chapters else 3000
    existing = repo.get_instruction_by_chapter(project_id, chapter_number)
    if not (existing and existing.get("objective")):
        repo.create_instruction(
            project_id=project_id,
            chapter_number=chapter_number,
            objective=f"承接上一章，推进第 {chapter_number} 章的主线调查与阶段冲突。",
            key_events=(
                "延续既有伏笔；推进当前阶段目标；制造新的场景阻力；"
                "在章末留下可继续追踪的钩子。"
            ),
            plots_to_plant="[]",
            plots_to_resolve="[]",
            emotion_tone="紧张、克制、悬疑",
            ending_hook="留下新的未解线索。",
            word_target=word_target,
            status="active",
        )
        created_instructions += 1

    return {
        "created_outlines": created_outlines,
        "created_instructions": created_instructions,
        "chapters_range": range_str,
    }
