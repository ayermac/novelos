"""v6.10.19: WorldStore - aggregates story_fact + plot_hole + memory queries."""

from __future__ import annotations

from .base import BaseStore


class WorldStore(BaseStore):
    """Aggregates world state: story facts, plot holes, and agent memories."""

    def get_world_state(self, project_id: str) -> dict:
        """Full world state snapshot for a project.

        Uses lightweight fact_index instead of full facts to avoid N+1 on
        large fact sets (v6.10.15 tiered loading optimization).
        """
        return {
            "fact_index": self._safe_list_fact_index(project_id),
            "active_plot_holes": self.get_active_plot_holes(project_id),
            "resolved_plot_holes": self._safe_list_plot_holes(project_id, status="resolved"),
            "memories": self.get_recent_memories(project_id, limit=50),
        }

    def get_active_plot_holes(self, project_id: str) -> list[dict]:
        """Active (planted) plot holes."""
        return self._safe_list_plot_holes(project_id, status="planted")

    def get_facts_by_type(self, project_id: str, fact_type: str) -> list[dict]:
        """Story facts filtered by type."""
        facts = self._safe_list_story_facts(project_id)
        if not isinstance(facts, list):
            return []
        return [f for f in facts if f.get("fact_type") == fact_type]

    def get_recent_memories(self, project_id: str, limit: int = 20) -> list[dict]:
        """Recent agent memories for a project."""
        memories = self._safe_list_for_project(project_id)
        if not isinstance(memories, list):
            return []
        return memories[:limit]

    def get_fact_timeline(self, project_id: str) -> list[dict]:
        """Fact event timeline for a project."""
        events = self._safe_list_fact_events(project_id)
        return events if isinstance(events, list) else []

    # ── Internal helpers ──────────────────────────────────────────

    def _safe_list_fact_index(self, project_id: str) -> list[dict]:
        try:
            result = self._repo.list_story_fact_index(project_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_list_plot_holes(self, project_id: str, status: str | None = None) -> list[dict]:
        try:
            result = self._repo.list_plot_holes(project_id, status=status)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_list_story_facts(self, project_id: str) -> list[dict]:
        try:
            result = self._repo.list_story_facts(project_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_list_for_project(self, project_id: str) -> list[dict]:
        try:
            result = self._repo.list_for_project(project_id, enabled_only=True)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_list_fact_events(self, project_id: str) -> list[dict]:
        try:
            result = self._repo.list_fact_events(project_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []
