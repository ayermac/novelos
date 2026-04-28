"""Context Readiness Gate — validates project context before chapter generation.

v5.3.0: Ensures projects have complete context before allowing generation.
Prevents incomplete projects from generating low-quality chapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextReadinessResult:
    """Result of context readiness check.

    Attributes:
        ready: True if project has all required context for generation.
        missing: List of missing context items.
        actions: List of suggested actions to fix missing items.
        details: Additional details about each check.
    """

    ready: bool
    missing: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ready": self.ready,
            "missing": self.missing,
            "actions": self.actions,
            "details": self.details,
        }


def check_context_readiness(
    project: dict,
    world_settings: list[dict],
    characters: list[dict],
    outlines: list[dict],
    instruction: dict | None,
    chapter_number: int,
    chapter_status: str,
) -> ContextReadinessResult:
    """Check if project has complete context for chapter generation.

    Required context items:
    1. project.description non-empty
    2. world_settings >= 1
    3. characters >= 1 protagonist
    4. outlines covering current chapter
    5. instruction exists OR chapter status allows planner entry
    6. word_target defined (derived from project.target_words / total_chapters_planned)

    Args:
        project: Project dict from database.
        world_settings: List of world setting dicts.
        characters: List of character dicts.
        outlines: List of outline dicts.
        instruction: Instruction dict for the chapter, or None.
        chapter_number: Current chapter number.
        chapter_status: Current chapter status.

    Returns:
        ContextReadinessResult with ready status and missing items.
    """
    missing: list[str] = []
    actions: list[str] = []
    details: dict[str, Any] = {}

    # 1. Check project.description
    description = project.get("description", "")
    details["has_description"] = bool(description and description.strip())
    if not description or not description.strip():
        missing.append("项目简介")
        actions.append("请在项目设置中填写项目简介")

    # 2. Check world_settings >= 1
    details["world_settings_count"] = len(world_settings)
    if len(world_settings) < 1:
        missing.append("世界观设定")
        actions.append("请至少添加一条世界观设定")

    # 3. Check characters >= 1 protagonist
    protagonists = [c for c in characters if c.get("role") == "protagonist"]
    details["protagonist_count"] = len(protagonists)
    details["character_count"] = len(characters)
    if len(protagonists) < 1:
        missing.append("主角角色")
        actions.append("请至少添加一个主角角色")

    # 4. Check outlines covering current chapter.
    # Volume/arc outlines are enough for Planner to derive a chapter brief; a
    # chapter-level outline is helpful but should not be mandatory at creation.
    covering_outlines = [
        o
        for o in outlines
        if _outline_covers_chapter(o.get("chapters_range", ""), chapter_number)
    ]
    details["has_outline_coverage"] = len(covering_outlines) >= 1
    details["outline_count"] = len(outlines)
    if len(covering_outlines) < 1:
        # Also check if there are any outlines at all
        if len(outlines) < 1:
            missing.append("大纲")
            actions.append("请先创建项目大纲")
        else:
            missing.append(f"第{chapter_number}章大纲")
            actions.append(f"请为第{chapter_number}章创建章节大纲")

    # 5. Check instruction exists OR chapter status allows planner entry
    has_instruction = instruction is not None and bool(instruction.get("objective"))
    details["has_instruction"] = has_instruction
    details["chapter_status"] = chapter_status

    # Statuses that can go to planner: idea, outlined, planned (without instruction)
    planner_entry_statuses = {"idea", "outlined"}
    can_enter_planner = chapter_status in planner_entry_statuses or (
        chapter_status == "planned" and not has_instruction
    )

    if not has_instruction and not can_enter_planner:
        missing.append("写作指令")
        actions.append("请为本章创建写作指令，或重置章节状态让规划器生成")

    # 6. Check word_target
    target_words = project.get("target_words", 0)
    total_chapters = project.get("total_chapters_planned", 0)
    word_target = instruction.get("word_target") if instruction else None

    if word_target:
        details["word_target"] = word_target
        details["word_target_source"] = "instruction"
    elif target_words and total_chapters:
        # Derive from project settings
        derived_target = target_words // total_chapters
        details["word_target"] = derived_target
        details["word_target_source"] = "derived"
    else:
        # Use default minimum
        details["word_target"] = 2500
        details["word_target_source"] = "default"
        missing.append("目标字数")
        actions.append("请在项目设置中填写目标总字数和预计章节数")

    # Determine readiness
    ready = len(missing) == 0

    return ContextReadinessResult(
        ready=ready,
        missing=missing,
        actions=actions,
        details=details,
    )


def _outline_covers_chapter(chapters_range: str, chapter_number: int) -> bool:
    """Check if an outline's chapters_range covers the given chapter number.

    Args:
        chapters_range: Range string like "1-10", "5", "10-20".
        chapter_number: Chapter number to check.

    Returns:
        True if the chapter is within the range.
    """
    if not chapters_range:
        return False

    chapters_range = chapters_range.strip()

    # Single chapter: "5"
    if chapters_range.isdigit():
        return int(chapters_range) == chapter_number

    # Range: "1-10"
    if "-" in chapters_range:
        parts = chapters_range.split("-")
        if len(parts) == 2:
            try:
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                return start <= chapter_number <= end
            except ValueError:
                return False

    return False


def format_readiness_error(result: ContextReadinessResult) -> dict[str, Any]:
    """Format context readiness result as API error response.

    Args:
        result: ContextReadinessResult from check_context_readiness.

    Returns:
        Error dict suitable for API error response.
    """
    return {
        "error_code": "PROJECT_CONTEXT_INCOMPLETE",
        "message": "项目资料不完整，无法生成章节",
        "missing": result.missing,
        "actions": result.actions,
        "details": result.details,
    }
