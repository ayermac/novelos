"""v6.10.19: SignalStore - aggregates genesis + project + queue + serial + batch."""

from __future__ import annotations

from .base import BaseStore


class SignalStore(BaseStore):
    """Aggregates project signal data: genesis status, queue depth, batch progress."""

    def get_project_signal(self, project_id: str) -> dict:
        """Full project signal snapshot."""
        return {
            "latest_genesis": self._safe_latest_genesis(project_id),
            "queue_depth": self.get_queue_depth(project_id),
            "active_batches": self._safe_list_production_runs(project_id),
            "active_serials": self._safe_list_serial_plans(project_id),
        }

    def get_queue_depth(self, project_id: str) -> int:
        """Pending queue item count for a project."""
        items = self._safe_list_queue_items(project_id)
        return len(items)

    def get_batch_progress(self, project_id: str, run_id: str | None = None) -> dict:
        """Batch production run status with items."""
        if run_id:
            run = self._safe_get_production_run(run_id)
            if run:
                run["items"] = self._safe_get_production_run_items(run_id)
            return {"run": run}
        runs = self._safe_list_production_runs(project_id)
        return {"runs": runs}

    def _safe_latest_genesis(self, project_id: str) -> dict | None:
        try:
            result = self._repo.get_latest_genesis_run(project_id)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None

    def _safe_list_queue_items(self, project_id: str) -> list[dict]:
        try:
            result = self._repo.list_queue_items(project_id=project_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_list_production_runs(self, project_id: str) -> list[dict]:
        try:
            result = self._repo.list_production_runs(project_id=project_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_get_production_run(self, run_id: str) -> dict | None:
        try:
            result = self._repo.get_production_run(run_id)
            return result if isinstance(result, dict) else None
        except (AttributeError, TypeError):
            return None

    def _safe_get_production_run_items(self, run_id: str) -> list[dict]:
        try:
            result = self._repo.get_production_run_items(run_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _safe_list_serial_plans(self, project_id: str) -> list[dict]:
        try:
            result = self._repo.list_serial_plans(project_id=project_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []
