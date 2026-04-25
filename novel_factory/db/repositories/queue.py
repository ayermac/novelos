"""Production queue operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict

class QueueRepositoryMixin:
    def create_queue_item(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
        priority: int = 100,
        max_attempts: int = 3,
        timeout_minutes: int = 120,
    ) -> str | None:
        """Create a new production queue item.

        Args:
            project_id: Project identifier.
            from_chapter: Starting chapter number (inclusive).
            to_chapter: Ending chapter number (inclusive).
            priority: Queue priority (lower = higher priority).
            max_attempts: Maximum retry attempts.
            timeout_minutes: Timeout in minutes for running items.

        Returns:
            Queue item ID or None if creation failed.
        """
        queue_id = f"queue_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO production_queue "
                "(id, project_id, from_chapter, to_chapter, priority, status, "
                "attempt_count, max_attempts, timeout_minutes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)",
                (queue_id, project_id, from_chapter, to_chapter, priority,
                 max_attempts, timeout_minutes, now, now),
            )
            conn.commit()
            return queue_id
        except Exception:
            return None
        finally:
            conn.close()

    def get_queue_item(self, queue_id: str) -> dict | None:
        """Get a production queue item by ID.

        Args:
            queue_id: Queue item identifier.

        Returns:
            Queue item dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM production_queue WHERE id = ?",
                (queue_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def list_queue_items(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List production queue items, optionally filtered.

        Args:
            project_id: Optional project ID filter.
            status: Optional status filter.
            limit: Maximum number of items to return.

        Returns:
            List of queue item dicts, ordered by priority ASC, created_at ASC.
        """
        conn = self._conn()
        try:
            query = "SELECT * FROM production_queue WHERE 1=1"
            params: list[Any] = []

            if project_id is not None:
                query += " AND project_id = ?"
                params.append(project_id)
            if status is not None:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY priority ASC, created_at ASC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def claim_next_queue_item(self) -> dict | None:
        """Claim the next pending queue item for execution.

        Selects the highest priority (lowest priority number), earliest created
        item with status 'pending' and atomically marks it as 'running'.

        Uses a transaction with conditional UPDATE to ensure only one claim
        can succeed per item.

        Returns:
            Queue item dict if a pending item was claimed, None otherwise.
        """
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Find the next pending item
            row = conn.execute(
                "SELECT * FROM production_queue "
                "WHERE status = 'pending' "
                "ORDER BY priority ASC, created_at ASC LIMIT 1"
            ).fetchone()

            if not row:
                conn.rollback()
                return None

            item = row_to_dict(row)
            queue_id = item["id"]
            now = datetime.now().isoformat()

            # Conditional update: only claim if still pending
            cursor = conn.execute(
                "UPDATE production_queue SET status = 'running', "
                "locked_at = ?, started_at = ?, updated_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (now, now, now, queue_id),
            )

            if cursor.rowcount == 0:
                # Another process claimed it first, or status changed
                conn.rollback()
                return None

            conn.commit()
            # Return the item with updated fields
            item["status"] = "running"
            item["locked_at"] = now
            item["started_at"] = now
            item["updated_at"] = now
            return item
        except Exception:
            conn.rollback()
            return None
        finally:
            conn.close()

    def update_queue_item(
        self,
        queue_id: str,
        status: str | None = None,
        production_run_id: str | None = None,
        attempt_count: int | None = None,
        last_error: str | None = None,
        locked_at: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        *,
        clear_locked_at: bool = False,
        clear_started_at: bool = False,
        clear_completed_at: bool = False,
    ) -> bool:
        """Update a production queue item.

        Args:
            queue_id: Queue item identifier.
            status: New status (optional).
            production_run_id: Associated production run ID (optional).
            attempt_count: New attempt count (optional).
            last_error: Error message (optional, use empty string to clear).
            locked_at: Lock timestamp (optional).
            started_at: Start timestamp (optional).
            completed_at: Completion timestamp (optional).
            clear_locked_at: If True, set locked_at to NULL.
            clear_started_at: If True, set started_at to NULL.
            clear_completed_at: If True, set completed_at to NULL.

        Returns:
            True if update succeeded (rowcount > 0), False otherwise.
        """
        conn = self._conn()
        try:
            updates = ["updated_at = ?"]
            now = datetime.now().isoformat()
            params: list[Any] = [now]

            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if production_run_id is not None:
                updates.append("production_run_id = ?")
                params.append(production_run_id)
            if attempt_count is not None:
                updates.append("attempt_count = ?")
                params.append(attempt_count)
            if last_error is not None:
                updates.append("last_error = ?")
                params.append(last_error)

            # Handle locked_at: explicit value takes precedence, then clear flag
            if locked_at is not None:
                updates.append("locked_at = ?")
                params.append(locked_at)
            elif clear_locked_at:
                updates.append("locked_at = NULL")

            # Handle started_at
            if started_at is not None:
                updates.append("started_at = ?")
                params.append(started_at)
            elif clear_started_at:
                updates.append("started_at = NULL")

            # Handle completed_at
            if completed_at is not None:
                updates.append("completed_at = ?")
                params.append(completed_at)
            elif clear_completed_at:
                updates.append("completed_at = NULL")

            params.append(queue_id)

            cursor = conn.execute(
                f"UPDATE production_queue SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            return False
        finally:
            conn.close()

    def record_queue_event(
        self,
        queue_id: str,
        event_type: str,
        from_status: str | None = None,
        to_status: str | None = None,
        message: str | None = None,
        metadata_json: str | None = None,
    ) -> str | None:
        """Record a production queue event.

        Args:
            queue_id: Queue item identifier.
            event_type: Type of event (enqueued, started, completed, failed, etc.).
            from_status: Previous status (optional).
            to_status: New status (optional).
            message: Event message (optional).
            metadata_json: JSON metadata string (optional).

        Returns:
            Event ID or None if recording failed.
        """
        event_id = f"qevent_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO production_queue_events "
                "(id, queue_id, event_type, from_status, to_status, message, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, queue_id, event_type, from_status, to_status, message,
                 metadata_json or "{}", now),
            )
            conn.commit()
            return event_id
        except Exception:
            return None
        finally:
            conn.close()

    def get_queue_events(self, queue_id: str) -> list[dict]:
        """Get all events for a production queue item.

        Args:
            queue_id: Queue item identifier.

        Returns:
            List of queue event dicts, ordered by created_at ASC.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM production_queue_events WHERE queue_id = ? "
                "ORDER BY created_at ASC",
                (queue_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def mark_timed_out_queue_items(
        self,
        timeout_minutes: int | None = None,
    ) -> list[str]:
        """Mark running queue items as timed out.

        Items with status 'running' whose locked_at is older than
        (now - timeout_minutes) are marked as 'timeout'.
        Uses per-item timeout_minutes if not overridden.

        Args:
            timeout_minutes: Override timeout minutes. If None, uses
                             per-item timeout_minutes from the DB.

        Returns:
            List of queue item IDs that were marked as timed out.
        """
        conn = self._conn()
        try:
            timed_out_ids: list[str] = []

            if timeout_minutes is not None:
                # Use global timeout
                from ...utils.time import timeout_threshold
                cutoff = timeout_threshold(timeout_minutes)

                # First, get the IDs of items to be timed out
                cursor = conn.execute(
                    "SELECT id FROM production_queue "
                    "WHERE status = 'running' AND locked_at < ?",
                    (cutoff,),
                )
                timed_out_ids = [row[0] for row in cursor.fetchall()]

                # Then update them
                conn.execute(
                    "UPDATE production_queue SET status = 'timeout', "
                    "last_error = 'Queue item timed out', "
                    "completed_at = ?, updated_at = ? "
                    "WHERE status = 'running' AND locked_at < ?",
                    (datetime.now().isoformat(), datetime.now().isoformat(), cutoff),
                )
            else:
                # Use per-item timeout_minutes
                # We can't use a simple parameterized query for per-item timeout,
                # so we fetch all running items and check individually
                rows = conn.execute(
                    "SELECT id, locked_at, timeout_minutes FROM production_queue "
                    "WHERE status = 'running' AND locked_at IS NOT NULL"
                ).fetchall()

                now = datetime.now()
                for row in rows:
                    row_dict = row_to_dict(row)
                    locked_str = row_dict.get("locked_at", "")
                    timeout_mins = row_dict.get("timeout_minutes", 120)
                    if locked_str:
                        try:
                            locked_dt = datetime.fromisoformat(locked_str)
                            elapsed = (now - locked_dt).total_seconds() / 60.0
                            if elapsed > timeout_mins:
                                now_iso = now.isoformat()
                                conn.execute(
                                    "UPDATE production_queue SET status = 'timeout', "
                                    "last_error = 'Queue item timed out', "
                                    "completed_at = ?, updated_at = ? "
                                    "WHERE id = ?",
                                    (now_iso, now_iso, row_dict["id"]),
                                )
                                timed_out_ids.append(row_dict["id"])
                        except (ValueError, TypeError):
                            pass

            conn.commit()
            return timed_out_ids
        except Exception:
            return []
        finally:
            conn.close()

    # ── Serial Plans (v3.6) ───────────────────────────────────────────────
