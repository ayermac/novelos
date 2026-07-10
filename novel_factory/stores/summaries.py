"""v6.10.19: SummaryStore - aggregates review + quality queries."""

from __future__ import annotations

from .base import BaseStore


class SummaryStore(BaseStore):
    """Aggregates review results and quality reports."""

    def get_chapter_quality_summary(self, project_id: str, chapter_number: int) -> dict:
        """Quality report + latest review for a chapter."""
        chapter = self._repo.get_chapter(project_id, chapter_number)
        chapter_id = chapter.get("id") if chapter else None
        return {
            "latest_review": self._safe_latest_review(project_id, chapter_id),
            "latest_quality_report": self._safe_latest_quality(project_id, chapter_id),
            "chapter_status": chapter.get("status") if chapter else None,
        }

    def get_review_history(self, project_id: str, chapter_number: int) -> list[dict]:
        """Review history for a chapter."""
        chapter = self._repo.get_chapter(project_id, chapter_number)
        chapter_id = chapter.get("id") if chapter else None
        if chapter_id is None:
            return []
        quality_reports = self._repo.get_quality_reports(project_id, chapter_id=chapter_id)
        return quality_reports if isinstance(quality_reports, list) else []

    def get_project_quality_trend(self, project_id: str, limit: int = 10) -> list[dict]:
        """Recent quality reports across project chapters."""
        reports = self._repo.get_quality_reports(project_id, limit=limit)
        return reports if isinstance(reports, list) else []

    def get_latest_chapter_review(self, project_id: str, chapter_number: int) -> dict | None:
        """Latest review for a chapter."""
        chapter = self._repo.get_chapter(project_id, chapter_number)
        if chapter is None:
            return None
        return self._safe_latest_review(project_id, chapter.get("id"))

    # ── helpers ──

    def _safe_latest_review(self, project_id: str, chapter_id: int | None) -> dict | None:
        if chapter_id is None:
            return None
        try:
            result = self._repo.get_latest_review(project_id, chapter_id)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None

    def _safe_latest_quality(self, project_id: str, chapter_id: int | None) -> dict | None:
        if chapter_id is None:
            return None
        try:
            result = self._repo.get_latest_quality_report(project_id, chapter_id)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None
