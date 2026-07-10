"""v6.10.19: ProgressStore - aggregates workflow + execution_event queries."""

from __future__ import annotations

from .base import BaseStore


class ProgressStore(BaseStore):
    """Aggregates workflow run status and execution events for progress tracking."""

    def get_project_progress(self, project_id: str) -> dict:
        """Project-level progress snapshot.

        Returns dict with: total_token_usage, recent_runs, active_runs,
        failed_run_count_recent.
        """
        return {
            "total_token_usage": self._repo.get_project_workflow_token_total(project_id),
            "recent_runs": self._repo.get_workflow_runs_for_project(project_id, limit=10),
            "active_runs": self._collect_active_runs(project_id),
            "failed_run_count_recent": self._count_recent_failures(project_id),
        }

    def get_chapter_workflow_status(self, project_id: str, chapter_number: int) -> dict:
        """Single-chapter workflow status."""
        return {
            "retry_count": self._repo.get_chapter_retry_count(project_id, chapter_number),
            "total_retry_count": self._repo.get_chapter_total_retry_count(project_id, chapter_number),
            "failed_runs_recent": self._repo.count_recent_failed_workflow_runs(project_id, chapter_number),
            "reset_marker": self._repo.get_latest_chapter_reset_marker(project_id, chapter_number),
            "latest_event": self._safe_latest_event(project_id, chapter_number),
        }

    def get_recent_events(self, project_id: str, limit: int = 20) -> list[dict]:
        """Recent execution events for a project."""
        events = self._safe_call(
            self._repo.get_workflow_execution_events, project_id=project_id, limit=limit
        )
        return events if isinstance(events, list) else []

    def get_recent_runs(self, project_id: str, limit: int = 10) -> list[dict]:
        """Recent workflow runs for a project. Thin wrapper over repo method."""
        runs = self._safe_call(
            self._repo.get_workflow_runs_for_project, project_id=project_id, limit=limit
        )
        return runs if isinstance(runs, list) else []

    def get_active_runs(self, project_id: str) -> list[dict]:
        """Active workflow runs across all chapters in a project."""
        return self._collect_active_runs(project_id)

    # ── Internal helpers ──────────────────────────────────────────

    def _collect_active_runs(self, project_id: str) -> list[dict]:
        """Collect active runs by scanning non-terminal chapters."""
        runs: list[dict] = []
        chapters = self._safe_call(
            self._repo.get_non_terminal_chapters, project_id=project_id
        )
        if not isinstance(chapters, list):
            return runs
        for ch in chapters:
            chapter_number = ch.get("chapter_number")
            if chapter_number is None:
                continue
            active = self._safe_call(
                self._repo.recover_active_workflow_runs_for_chapter,
                project_id=project_id, chapter_number=chapter_number,
            )
            if isinstance(active, list):
                runs.extend(active)
        return runs

    def _count_recent_failures(self, project_id: str) -> int:
        """Count recent failed runs across project chapters."""
        total = 0
        chapters = self._safe_call(self._repo.list_chapters, project_id=project_id)
        if not isinstance(chapters, list):
            return 0
        for ch in chapters:
            chapter_number = ch.get("chapter_number")
            if chapter_number is None:
                continue
            count = self._safe_call(
                self._repo.count_recent_failed_workflow_runs,
                project_id=project_id, chapter_number=chapter_number,
            )
            if isinstance(count, int):
                total += count
        return total

    def _safe_latest_event(self, project_id: str, chapter_number: int) -> dict | None:
        result = self._safe_call(
            self._repo.get_latest_workflow_execution_event,
            project_id=project_id, chapter_number=chapter_number,
        )
        return result if isinstance(result, dict) else None

    def _safe_call(self, func, **kwargs):
        """Call a repo method, returning None on AttributeError (method may not exist)."""
        try:
            return func(**kwargs)
        except (AttributeError, TypeError):
            return None
