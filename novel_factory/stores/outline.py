"""v6.10.19: OutlineStore - aggregates outline + instruction queries."""

from __future__ import annotations

from .base import BaseStore


class OutlineStore(BaseStore):
    """Aggregates outline and instruction data."""

    def get_arc_outline(self, project_id: str, arc_id: str | int) -> dict | None:
        """Single outline with instructions for its chapters."""
        outline = self._repo.get_outline(project_id, int(arc_id))
        if outline is None:
            return None
        outline["instructions"] = self._get_instructions_for_range(
            project_id, outline.get("chapters_range", "")
        )
        return outline

    def get_chapter_instructions(self, project_id: str) -> list[dict]:
        """All chapter instructions for a project."""
        instructions = self._repo.list_instructions(project_id)
        return instructions if isinstance(instructions, list) else []

    def get_outline_progress(self, project_id: str) -> dict:
        """Outline vs instruction completion mapping."""
        outlines = self._repo.list_outlines(project_id)
        instructions = self._repo.list_instructions(project_id)
        inst_chapters = {i.get("chapter_number") for i in instructions if isinstance(i, dict)}
        return {
            "total_outlines": len(outlines) if isinstance(outlines, list) else 0,
            "total_instructions": len(instructions) if isinstance(instructions, list) else 0,
            "chapters_with_instructions": sorted(inst_chapters),
            "outlines": outlines if isinstance(outlines, list) else [],
        }

    def _get_instructions_for_range(self, project_id: str, chapters_range: str) -> list[dict]:
        """Get instructions matching a chapters range string."""
        instructions = self._repo.list_instructions(project_id)
        if not isinstance(instructions, list) or not chapters_range:
            return []
        # Simple parsing: "1-3" or "1,2,3"
        nums = set()
        for part in str(chapters_range).split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    nums.update(range(int(start), int(end) + 1))
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    nums.add(int(part))
                except (ValueError, TypeError):
                    pass
        return [i for i in instructions if i.get("chapter_number") in nums]
