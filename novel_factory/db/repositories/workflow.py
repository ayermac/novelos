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
                    "ORDER BY started_at DESC, rowid DESC LIMIT ?",
                    (project_id, chapter_number, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=? "
                    "ORDER BY started_at DESC, rowid DESC LIMIT ?",
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

    def invalidate_running_workflow_runs_for_chapter(
        self,
        project_id: str,
        chapter_number: int,
        error_message: str,
        run_id: str | None = None,
    ) -> int:
        """Mark active running workflow runs for a chapter as blocked.

        Used when a chapter is reset or otherwise invalidated while an older
        workflow is still in flight. This prevents stale runs from lingering in
        ``running`` state after the source chapter has been reset.
        """
        conn = self._conn()
        try:
            query = (
                "UPDATE workflow_runs SET status='blocked', "
                "current_node='human_review', "
                "error_message=?, "
                "completed_at=datetime('now','+8 hours') "
                "WHERE project_id=? AND chapter_number=? AND status='running'"
            )
            params: list[Any] = [error_message, project_id, chapter_number]
            if run_id:
                query += " AND id=?"
                params.append(run_id)
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def mark_blocked_workflow_runs_recovered_for_chapter(
        self,
        project_id: str,
        chapter_number: int,
        run_id: str | None = None,
    ) -> int:
        """Mark blocked workflow runs as recovered after a chapter reset.

        Resetting a chapter moves the chapter back to ``planned``. If the latest
        blocked run remains blocked, health reconciliation will correctly infer
        that the chapter is still blocked and move it back to ``blocking``. Mark
        the recovered blocked run complete so old failure bookkeeping cannot
        re-block a freshly reset chapter.
        """
        conn = self._conn()
        try:
            query = (
                "UPDATE workflow_runs SET status='completed', "
                "current_node='reset_recovery', "
                "error_message=NULL, "
                "completed_at=datetime('now','+8 hours') "
                "WHERE project_id=? AND chapter_number=? AND status='blocked'"
            )
            params: list[Any] = [project_id, chapter_number]
            if run_id:
                query += " AND id=?"
                params.append(run_id)
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def reconcile_terminal_chapter_running_workflows(
        self,
        project_id: str | None = None,
        chapter_number: int | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Close running workflow rows when the chapter is already terminal.

        Chapter state is the source of truth for terminal statuses. If a
        workflow_run remains ``running`` after the chapter reached reviewed,
        awaiting_publish, or published, the run is stale bookkeeping rather
        than active work.
        """
        terminal_statuses = ("reviewed", "awaiting_publish", "published")
        conn = self._conn()
        try:
            query = (
                "SELECT wr.id, wr.project_id, wr.chapter_number, wr.graph_name, c.status AS chapter_status "
                "FROM workflow_runs wr "
                "JOIN chapters c ON c.project_id = wr.project_id "
                "AND c.chapter_number = wr.chapter_number "
                "WHERE wr.status='running' "
                "AND wr.graph_name='chapter_production' "
                "AND c.status IN (?, ?, ?)"
            )
            params: list[Any] = list(terminal_statuses)
            if project_id is not None:
                query += " AND wr.project_id=?"
                params.append(project_id)
            if chapter_number is not None:
                query += " AND wr.chapter_number=?"
                params.append(chapter_number)
            if run_id is not None:
                query += " AND wr.id=?"
                params.append(run_id)

            rows = conn.execute(query, params).fetchall()
            run_ids: list[str] = []
            task_count = 0
            for row in rows:
                resolved_node = (
                    "publish"
                    if row["chapter_status"] == "published"
                    else "awaiting_publish"
                )
                cursor = conn.execute(
                    "UPDATE workflow_runs SET status='completed', current_node=?, "
                    "error_message=NULL, completed_at=datetime('now','+8 hours') "
                    "WHERE id=? AND status='running'",
                    (resolved_node, row["id"]),
                )
                if cursor.rowcount:
                    run_ids.append(row["id"])
                    task_cursor = conn.execute(
                        "UPDATE task_status SET status='completed', "
                        "completed_at=COALESCE(completed_at, datetime('now','+8 hours')), "
                        "error_message=NULL "
                        "WHERE workflow_run_id=? AND status='running'",
                        (row["id"],),
                    )
                    task_count += task_cursor.rowcount
            conn.commit()
            return {
                "runs": len(run_ids),
                "tasks": task_count,
                "run_ids": run_ids,
            }
        finally:
            conn.close()

    def reconcile_latest_blocked_runs_with_chapters(
        self,
        project_id: str | None = None,
        chapter_number: int | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Move chapters to blocking when their latest workflow run is blocked.

        Older blocked runs must not poison a chapter that was already reset or
        successfully completed later. For that reason this only considers the
        latest run for each chapter, and never rewrites terminal/recovery
        chapter states.
        """
        protected_statuses = ("blocking", "revision", "reviewed", "awaiting_publish", "published")
        conn = self._conn()
        try:
            query = (
                "SELECT wr.id, wr.project_id, wr.chapter_number, c.status AS chapter_status "
                "FROM workflow_runs wr "
                "JOIN chapters c ON c.project_id = wr.project_id "
                "AND c.chapter_number = wr.chapter_number "
                "WHERE wr.status='blocked' "
                "AND c.status NOT IN (?, ?, ?, ?, ?) "
                "AND wr.id = ("
                "  SELECT wr2.id FROM workflow_runs wr2 "
                "  WHERE wr2.project_id = wr.project_id "
                "  AND wr2.chapter_number = wr.chapter_number "
                "  ORDER BY datetime(wr2.started_at) DESC, wr2.id DESC "
                "  LIMIT 1"
                ")"
            )
            params: list[Any] = list(protected_statuses)
            if project_id is not None:
                query += " AND wr.project_id=?"
                params.append(project_id)
            if chapter_number is not None:
                query += " AND wr.chapter_number=?"
                params.append(chapter_number)
            if run_id is not None:
                query += " AND wr.id=?"
                params.append(run_id)

            rows = conn.execute(query, params).fetchall()
            run_ids: list[str] = []
            chapter_keys: list[dict[str, Any]] = []
            for row in rows:
                cursor = conn.execute(
                    "UPDATE chapters SET status='blocking', updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=? "
                    "AND status NOT IN (?, ?, ?, ?, ?)",
                    (
                        row["project_id"],
                        row["chapter_number"],
                        *protected_statuses,
                    ),
                )
                if cursor.rowcount:
                    run_ids.append(row["id"])
                    chapter_keys.append({
                        "project_id": row["project_id"],
                        "chapter_number": row["chapter_number"],
                        "previous_status": row["chapter_status"],
                        "new_status": "blocking",
                    })
            conn.commit()
            return {
                "chapters": len(chapter_keys),
                "run_ids": run_ids,
                "chapter_keys": chapter_keys,
            }
        finally:
            conn.close()

    def get_project_workflow_token_total(self, project_id: str) -> int:
        """Return total workflow tokens already recorded for a project."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(total_tokens), 0) AS total FROM workflow_runs WHERE project_id=?",
                (project_id,),
            ).fetchone()
            return int(row["total"] or 0) if row else 0
        finally:
            conn.close()

    def start_task(
        self,
        project_id: str,
        chapter_number: int,
        task_type: str,
        agent_id: str,
        workflow_run_id: str | None = None,
    ) -> int:
        """Start a new task. Returns task id."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO task_status "
                "(project_id, chapter_number, task_type, agent_id, status, started_at, workflow_run_id) "
                "VALUES (?, ?, ?, ?, 'running', datetime('now','+8 hours'), ?)",
                (project_id, chapter_number, task_type, agent_id, workflow_run_id),
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

    def get_latest_chapter_reset_marker(
        self,
        project_id: str,
        chapter_number: int,
    ) -> str | None:
        """Return the latest explicit human recovery marker for a chapter.

        Manual reset is the user's confirmation that old workflow failures
        should no longer poison the next attempt. Both task_status reset rows
        and reset_recovery workflow runs count as recovery markers because
        older API paths recorded one or the other.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT MAX(marker_at) AS marker_at FROM ("
                "  SELECT COALESCE(completed_at, started_at, created_at) AS marker_at "
                "  FROM task_status "
                "  WHERE project_id=? AND chapter_number=? AND task_type='reset' "
                "  UNION ALL "
                "  SELECT COALESCE(completed_at, started_at) AS marker_at "
                "  FROM workflow_runs "
                "  WHERE project_id=? AND chapter_number=? "
                "  AND current_node='reset_recovery' AND status='completed'"
                ")",
                (project_id, chapter_number, project_id, chapter_number),
            ).fetchone()
            return row["marker_at"] if row and row["marker_at"] else None
        finally:
            conn.close()

    def count_recent_failed_workflow_runs(
        self,
        project_id: str,
        chapter_number: int,
        since: str | None = None,
        limit: int = 20,
    ) -> int:
        """Count failed workflow runs in the current recovery window.

        Without ``since`` this preserves the historical "recent 20 runs"
        behavior. With ``since`` it counts only failures after the latest manual
        reset/confirmation so old deadloops do not permanently block a chapter.
        """
        conn = self._conn()
        try:
            if since:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM workflow_runs "
                    "WHERE project_id=? AND chapter_number=? "
                    "AND status='failed' AND started_at>?",
                    (project_id, chapter_number, since),
                ).fetchone()
                return int(row["cnt"] if row else 0)

            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM ("
                "  SELECT status FROM workflow_runs "
                "  WHERE project_id=? AND chapter_number=? "
                "  ORDER BY started_at DESC, rowid DESC LIMIT ?"
                ") WHERE status='failed'",
                (project_id, chapter_number, limit),
            ).fetchone()
            return int(row["cnt"] if row else 0)
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

    # ── Workflow Node Events (v5.8) ──────────────────────────

    def create_workflow_node_event(
        self,
        run_id: str,
        project_id: str,
        chapter_number: int,
        node_name: str,
        event_type: str,
        status: str | None = None,
        message: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        artifact_refs_json: str | None = None,
        token_count: int | None = None,
        latency_ms: int | None = None,
        cost_estimate: float | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        metadata_json: str | None = None,
    ) -> int:
        """Create a workflow node event. Returns event id."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO workflow_node_events "
                "(run_id, project_id, chapter_number, node_name, event_type, status, "
                "message, input_summary, output_summary, artifact_refs_json, "
                "token_count, latency_ms, cost_estimate, error_code, error_message, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, project_id, chapter_number, node_name, event_type, status,
                    message, input_summary, output_summary, artifact_refs_json,
                    token_count, latency_ms, cost_estimate, error_code, error_message, metadata_json,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_workflow_node_events(
        self,
        run_id: str,
        node_name: str | None = None,
    ) -> list[dict]:
        """Get node events for a workflow run, ordered by creation time."""
        conn = self._conn()
        try:
            query = (
                "SELECT * FROM workflow_node_events WHERE run_id=? "
                "ORDER BY created_at ASC, id ASC"
            )
            params: list[Any] = [run_id]
            if node_name:
                query = (
                    "SELECT * FROM workflow_node_events WHERE run_id=? AND node_name=? "
                    "ORDER BY created_at ASC, id ASC"
                )
                params = [run_id, node_name]
            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_workflow_node_events_for_chapter(
        self,
        project_id: str,
        chapter_number: int,
        run_id: str | None = None,
    ) -> list[dict]:
        """Get node events for a chapter, optionally filtered by run_id."""
        conn = self._conn()
        try:
            if run_id:
                rows = conn.execute(
                    "SELECT * FROM workflow_node_events "
                    "WHERE project_id=? AND chapter_number=? AND run_id=? "
                    "ORDER BY created_at ASC, id ASC",
                    (project_id, chapter_number, run_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_node_events "
                    "WHERE project_id=? AND chapter_number=? "
                    "ORDER BY created_at ASC, id ASC",
                    (project_id, chapter_number),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Artifacts ─────────────────────────────────────────────
