"""v6.10.19: CheckpointStore - aggregates chapter_versions + state_history queries."""

from __future__ import annotations

from .base import BaseStore


class CheckpointStore(BaseStore):
    """Aggregates chapter versions and state history for checkpoint tracking."""

    def get_chapter_checkpoint(self, project_id: str, chapter_number: int) -> dict | None:
        """Latest version + state snapshot for a chapter."""
        chapter = self._repo.get_chapter(project_id, chapter_number)
        if chapter is None:
            return None
        return {
            "chapter_id": chapter.get("id"),
            "status": self._repo.get_chapter_status(project_id, chapter_number),
            "latest_version": self._safe_get_version(project_id, chapter_number),
            "state": self._repo.get_chapter_state(project_id, chapter_number),
            "version_count": self._repo.get_chapter_version_count(project_id, chapter_number),
            "diff": self._safe_get_version_diff(project_id, chapter_number),
        }

    def get_checkpoint_history(self, project_id: str, chapter_number: int) -> list[dict]:
        """Version history + state history for a chapter."""
        return {
            "versions": self._repo.list_chapter_versions(project_id, chapter_number),
            "state_history": self._repo.list_state_history(project_id, chapter_number),
        }

    def get_latest_state(self, project_id: str, chapter_number: int) -> dict | None:
        """Latest chapter state."""
        return self._repo.get_chapter_state(project_id, chapter_number)

    def _safe_get_version(self, project_id: str, chapter_number: int) -> dict | None:
        try:
            version_id = self._repo.get_latest_version_id(project_id, chapter_number)
            if version_id is None:
                return None
            result = self._repo.get_version_by_id(project_id, version_id)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None

    def _safe_get_version_diff(self, project_id: str, chapter_number: int) -> dict | None:
        try:
            result = self._repo.get_version_diff(project_id, chapter_number)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None
