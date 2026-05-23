"""Agent Memory repository for v6.0.

Stores project preference memory, recurring failure memory, user feedback,
agent feedback, and strategy notes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentMemoryRepository:
    """Repository for agent memory CRUD."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def create(
        self,
        project_id: str,
        agent_id: str,
        memory_type: str,
        key: str,
        value: dict[str, Any],
        confidence: float = 1.0,
        source_run_id: str | None = None,
        source_chapter_number: int | None = None,
    ) -> dict[str, Any]:
        sql = """
            INSERT INTO agent_memories
            (project_id, agent_id, memory_type, key, value_json, confidence, source_run_id, source_chapter_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(sql, (
            project_id, agent_id, memory_type, key,
            json.dumps(value, ensure_ascii=False),
            confidence, source_run_id, source_chapter_number,
        ))
        self.conn.commit()
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "agent_id": agent_id,
            "memory_type": memory_type,
            "key": key,
            "value": value,
            "confidence": confidence,
        }

    def list_for_project(
        self,
        project_id: str,
        agent_id: str | None = None,
        memory_type: str | None = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM agent_memories WHERE project_id = ?"
        params: list[Any] = [project_id]
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)
        if enabled_only:
            sql += " AND enabled = 1"
        sql += " ORDER BY created_at DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get(self, memory_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM agent_memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row:
            return self._row_to_dict(row)
        return None

    def set_enabled(self, memory_id: int, enabled: bool) -> bool:
        cursor = self.conn.execute(
            "UPDATE agent_memories SET enabled = ?, updated_at = datetime('now', '+8 hours') WHERE id = ?",
            (1 if enabled else 0, memory_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, memory_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM agent_memories WHERE id = ?", (memory_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_by_project(self, project_id: str) -> int:
        cursor = self.conn.execute(
            "DELETE FROM agent_memories WHERE project_id = ?", (project_id,)
        )
        self.conn.commit()
        return cursor.rowcount

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        value_json = row["value_json"] or "{}"
        try:
            value = json.loads(value_json)
        except Exception:
            value = {}
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "agent_id": row["agent_id"],
            "memory_type": row["memory_type"],
            "key": row["key"],
            "value": value,
            "confidence": row["confidence"],
            "source_run_id": row["source_run_id"],
            "source_chapter_number": row["source_chapter_number"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
