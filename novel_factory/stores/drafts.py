"""v6.10.19: DraftStore - aggregates chapter + instruction + scene_beats queries."""

from __future__ import annotations

from .base import BaseStore


class DraftStore(BaseStore):
    """Aggregates chapter drafts, instructions, and scene beats."""

    def get_chapter_with_drafts(self, project_id: str, chapter_number: int) -> dict | None:
        """Chapter + all draft versions."""
        chapter = self._repo.get_chapter(project_id, chapter_number)
        if chapter is None:
            return None
        return {
            "chapter": chapter,
            "status": self._repo.get_chapter_status(project_id, chapter_number),
            "versions": self._repo.list_chapter_versions(project_id, chapter_number),
            "version_count": self._repo.get_chapter_version_count(project_id, chapter_number),
            "latest_version_id": self._safe_latest_version_id(project_id, chapter_number),
        }

    def get_latest_draft(self, project_id: str, chapter_number: int) -> dict | None:
        """Latest draft version (by id lookup then fetch)."""
        version_id = self._safe_latest_version_id(project_id, chapter_number)
        if version_id is None:
            return None
        return self._safe_get_version_by_id(project_id, version_id)

    def get_draft_history(self, project_id: str, chapter_number: int) -> list[dict]:
        """Full draft version history."""
        versions = self._repo.list_chapter_versions(project_id, chapter_number)
        return versions if isinstance(versions, list) else []

    def get_chapter_full_context(self, project_id: str, chapter_number: int) -> dict | None:
        """Chapter + instruction + scene beats + state + latest version."""
        chapter = self._repo.get_chapter(project_id, chapter_number)
        if chapter is None:
            return None
        return {
            "chapter": chapter,
            "instruction": self._safe_get_instruction(project_id, chapter_number),
            "scene_beats": self._safe_get_scene_beats(project_id, chapter_number),
            "chapter_state": self._safe_get_chapter_state(project_id, chapter_number),
            "latest_version": self.get_latest_draft(project_id, chapter_number),
        }

    # ── Internal helpers ──────────────────────────────────────────

    def _safe_latest_version_id(self, project_id: str, chapter_number: int) -> int | None:
        try:
            result = self._repo.get_latest_version_id(project_id, chapter_number)
            return result if isinstance(result, int) else None
        except (AttributeError, TypeError):
            return None

    def _safe_get_version_by_id(self, project_id: str, version_id: int) -> dict | None:
        try:
            result = self._repo.get_version_by_id(project_id, version_id)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None

    def _safe_get_instruction(self, project_id: str, chapter_number: int) -> dict | None:
        try:
            result = self._repo.get_instruction_by_chapter(project_id, chapter_number)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None

    def _safe_get_scene_beats(self, project_id: str, chapter_number: int) -> list[dict]:
        try:
            result = self._repo.get_scene_beats(project_id, chapter_number)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_get_chapter_state(self, project_id: str, chapter_number: int) -> dict | None:
        try:
            result = self._repo.get_chapter_state(project_id, chapter_number)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None
