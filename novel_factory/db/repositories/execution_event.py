"""Repository mixin for workflow execution events (v6.1).

Provides CRUD for fine-grained agent-level execution evidence,
separate from coarse node lifecycle events (workflow_node_events).
"""

from __future__ import annotations

import json
from typing import Any

from ..connection import row_to_dict


class ExecutionEventRepositoryMixin:

    def create_workflow_execution_event(
        self,
        run_id: str,
        project_id: str,
        chapter_number: int,
        node_name: str,
        event_type: str,
        agent_id: str | None = None,
        status: str = "info",
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        artifact_refs: list[dict] | None = None,
        token_count: int | None = None,
        latency_ms: int | None = None,
    ) -> int:
        """Create a workflow execution event. Returns event id."""
        conn = self._conn()
        try:
            payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
            artifact_refs_json = (
                json.dumps(artifact_refs, ensure_ascii=False) if artifact_refs else None
            )
            cursor = conn.execute(
                "INSERT INTO workflow_execution_events "
                "(run_id, project_id, chapter_number, node_name, agent_id, "
                "event_type, status, message, payload_json, artifact_refs_json, "
                "token_count, latency_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, project_id, chapter_number, node_name, agent_id,
                    event_type, status, message, payload_json, artifact_refs_json,
                    token_count, latency_ms,
                ),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        finally:
            conn.close()

    def get_workflow_execution_events(
        self,
        run_id: str,
    ) -> list[dict]:
        """Get all execution events for a workflow run, ordered by time."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM workflow_execution_events "
                "WHERE run_id=? ORDER BY created_at ASC, id ASC",
                (run_id,),
            ).fetchall()
            return [self._parse_exec_event(row) for row in rows]
        finally:
            conn.close()

    def get_workflow_execution_events_for_chapter(
        self,
        project_id: str,
        chapter_number: int,
        run_id: str | None = None,
    ) -> list[dict]:
        """Get execution events for a chapter, optionally filtered by run_id."""
        conn = self._conn()
        try:
            if run_id:
                rows = conn.execute(
                    "SELECT * FROM workflow_execution_events "
                    "WHERE project_id=? AND chapter_number=? AND run_id=? "
                    "ORDER BY created_at ASC, id ASC",
                    (project_id, chapter_number, run_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_execution_events "
                    "WHERE project_id=? AND chapter_number=? "
                    "ORDER BY created_at ASC, id ASC",
                    (project_id, chapter_number),
                ).fetchall()
            return [self._parse_exec_event(row) for row in rows]
        finally:
            conn.close()

    def get_latest_workflow_execution_event(
        self,
        run_id: str,
        node_name: str | None = None,
        event_type: str | None = None,
    ) -> dict | None:
        """Get the latest execution event matching filters."""
        conn = self._conn()
        try:
            query = "SELECT * FROM workflow_execution_events WHERE run_id=?"
            params: list[Any] = [run_id]
            if node_name:
                query += " AND node_name=?"
                params.append(node_name)
            if event_type:
                query += " AND event_type=?"
                params.append(event_type)
            query += " ORDER BY created_at DESC, id DESC LIMIT 1"
            row = conn.execute(query, params).fetchone()
            return self._parse_exec_event(row) if row else None
        finally:
            conn.close()

    def get_workflow_execution_events_since(
        self,
        run_id: str,
        since_id: int | None = None,
        since_created_at: str | None = None,
    ) -> list[dict]:
        """Get execution events after a given point for SSE streaming."""
        conn = self._conn()
        try:
            query = "SELECT * FROM workflow_execution_events WHERE run_id=?"
            params: list[Any] = [run_id]
            if since_id is not None:
                query += " AND id > ?"
                params.append(since_id)
            elif since_created_at is not None:
                query += " AND created_at > ?"
                params.append(since_created_at)
            query += " ORDER BY created_at ASC, id ASC"
            rows = conn.execute(query, params).fetchall()
            return [self._parse_exec_event(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _parse_exec_event(row: Any) -> dict:
        """Parse a row into an execution event dict with JSON fields decoded."""
        d = row_to_dict(row)
        if d.get("payload_json"):
            try:
                d["payload"] = json.loads(d["payload_json"])
            except (json.JSONDecodeError, TypeError):
                d["payload"] = {}
        else:
            d["payload"] = {}
        if d.get("artifact_refs_json"):
            try:
                d["artifact_refs"] = json.loads(d["artifact_refs_json"])
            except (json.JSONDecodeError, TypeError):
                d["artifact_refs"] = []
        else:
            d["artifact_refs"] = []
        return d
