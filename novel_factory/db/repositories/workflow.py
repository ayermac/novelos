"""Workflow runs, tasks, agent messages."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict

class WorkflowRepositoryMixin:
    def create_workflow_run(
        self,
        project_id: str,
        chapter_number: int,
        graph_name: str = "chapter_production",
    ) -> str:
        """Create a workflow run record. Returns run id."""
        conn = self._conn()
        try:
            run_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO workflow_runs (id, project_id, chapter_number, graph_name) "
                "VALUES (?, ?, ?, ?)",
                (run_id, project_id, chapter_number, graph_name),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()

    def update_workflow_run(
        self,
        run_id: str,
        status: str | None = None,
        current_node: str | None = None,
        error_message: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        duration_ms: int | None = None,
        clear_error: bool = False,
    ) -> bool:
        """Update workflow run status.

        Args:
            clear_error: If True, explicitly set error_message to NULL.
                         Used when status transitions to 'completed' to ensure
                         no stale error_message remains (P1 fix).

        Returns:
            True if the run was found and updated, False otherwise.
        """
        conn = self._conn()
        try:
            parts: list[str] = []
            params: list[Any] = []
            if status:
                parts.append("status=?")
                params.append(status)
            if current_node:
                parts.append("current_node=?")
                params.append(current_node)
            # P1 fix: Support clearing error_message explicitly
            if clear_error:
                parts.append("error_message=NULL")
            elif error_message:
                parts.append("error_message=?")
                params.append(error_message)
            if prompt_tokens is not None:
                parts.append("prompt_tokens=?")
                params.append(prompt_tokens)
            if completion_tokens is not None:
                parts.append("completion_tokens=?")
                params.append(completion_tokens)
            if total_tokens is not None:
                parts.append("total_tokens=?")
                params.append(total_tokens)
            if duration_ms is not None:
                parts.append("duration_ms=?")
                params.append(duration_ms)
            if status in ("completed", "failed", "blocked"):
                parts.append("completed_at=datetime('now','+8 hours')")
            if not parts:
                return False
            params.append(run_id)
            cursor = conn.execute(
                f"UPDATE workflow_runs SET {', '.join(parts)} WHERE id=?", params
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Plots ─────────────────────────────────────────────────

    def get_workflow_runs_for_project(
        self,
        project_id: str,
        chapter_number: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get workflow runs for a project, most recent first.

        Args:
            project_id: Project identifier.
            chapter_number: Optional chapter filter.
            limit: Maximum number of runs to return.

        Returns:
            List of dicts with run_id (mapped from id), chapter_number, status,
            created_at, error_message, etc.
        """
        conn = self._conn()
        try:
            if chapter_number is not None:
                rows = conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=? AND chapter_number=? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (project_id, chapter_number, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            results = []
            for r in rows:
                d = row_to_dict(r)
                # Also expose run_id for API consistency while keeping id for internal use
                d["run_id"] = d.get("id")
                results.append(d)
            return results
        finally:
            conn.close()

    def start_task(
        self,
        project_id: str,
        chapter_number: int,
        task_type: str,
        agent_id: str,
    ) -> int:
        """Start a new task. Returns task id."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO task_status "
                "(project_id, chapter_number, task_type, agent_id, status, started_at) "
                "VALUES (?, ?, ?, ?, 'running', datetime('now','+8 hours'))",
                (project_id, chapter_number, task_type, agent_id),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def complete_task(
        self,
        task_id: int,
        success: bool = True,
        error: str | None = None,
    ) -> bool:
        """Complete a task.

        Returns:
            True if the task was found and updated, False otherwise.
        """
        conn = self._conn()
        try:
            status = "completed" if success else "failed"
            cursor = conn.execute(
                "UPDATE task_status SET status=?, completed_at=datetime('now','+8 hours'), "
                "error_message=? WHERE id=?",
                (status, error, task_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def increment_retry(self, task_id: int) -> int:
        """Increment retry count for a task. Returns new retry count."""
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE task_status SET retry_count=retry_count+1 WHERE id=?",
                (task_id,),
            )
            row = conn.execute(
                "SELECT retry_count FROM task_status WHERE id=?", (task_id,)
            ).fetchone()
            conn.commit()
            return row["retry_count"] if row else 0
        finally:
            conn.close()

    def get_chapter_retry_count(self, project_id: str, chapter_number: int) -> int:
        """Get revision attempts since the last manual reset for a chapter."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM task_status "
                "WHERE project_id=? AND chapter_number=? AND task_type='revise' "
                "AND id > COALESCE(( "
                "  SELECT MAX(id) FROM task_status "
                "  WHERE project_id=? AND chapter_number=? AND task_type='reset' "
                "), 0)",
                (project_id, chapter_number, project_id, chapter_number),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_chapter_total_retry_count(self, project_id: str, chapter_number: int) -> int:
        """Get all historical revision attempts for a chapter."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM task_status "
                "WHERE project_id=? AND chapter_number=? AND task_type='revise'",
                (project_id, chapter_number),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def mark_timed_out_tasks(self, project_id: str, timeout_minutes: int) -> int:
        """Mark running tasks that have exceeded the timeout threshold.

        Sets status to 'timeout' for tasks that are still 'running' and
        whose started_at is older than timeout_minutes ago.

        Does not auto-retry or auto-wake any Agent.

        Args:
            project_id: Project identifier.
            timeout_minutes: Number of minutes after which a running task
                             is considered timed out.

        Returns:
            Number of tasks marked as timed out.
        """
        from ...utils.time import timeout_threshold

        cutoff = timeout_threshold(timeout_minutes)
        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE task_status SET status='timeout', "
                "completed_at=datetime('now','+8 hours'), "
                "error_message='Task timed out' "
                "WHERE project_id=? AND status='running' AND started_at < ?",
                (project_id, cutoff),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # ── Agent messages ────────────────────────────────────────

    def send_message(
        self,
        project_id: str,
        from_agent: str,
        to_agent: str,
        msg_type: str,
        content: dict,
        priority: str = "normal",
        chapter_number: int | None = None,
    ) -> int:
        """Send an async message between agents."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO agent_messages "
                "(project_id, from_agent, to_agent, type, priority, content, chapter_number) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id, from_agent, to_agent, msg_type, priority,
                    json.dumps(content, ensure_ascii=False), chapter_number,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_pending_messages(
        self, project_id: str, to_agent: str | None = None
    ) -> list[dict]:
        """Get pending messages for an agent."""
        conn = self._conn()
        try:
            query = "SELECT * FROM agent_messages WHERE project_id=? AND status='pending'"
            params: list[Any] = [project_id]
            if to_agent:
                query += " AND to_agent=?"
                params.append(to_agent)
            query += " ORDER BY priority DESC, created_at ASC"
            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Artifacts ─────────────────────────────────────────────
