"""Serial plan operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..connection import row_to_dict

class SerialRepositoryMixin:
    def create_serial_plan(
        self,
        project_id: str,
        name: str,
        start_chapter: int,
        target_chapter: int,
        batch_size: int,
    ) -> str:
        """Create a new serial plan.

        Args:
            project_id: Project identifier.
            name: Human-readable name for the plan.
            start_chapter: Starting chapter number.
            target_chapter: Target chapter number to reach.
            batch_size: Number of chapters per batch.

        Returns:
            Serial plan ID.
        """
        import uuid
        from datetime import datetime

        serial_plan_id = f"serial_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        total_planned = target_chapter - start_chapter + 1

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO serial_plans "
                "(id, project_id, name, start_chapter, target_chapter, batch_size, "
                "current_chapter, status, total_planned_chapters, completed_chapters, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    serial_plan_id,
                    project_id,
                    name,
                    start_chapter,
                    target_chapter,
                    batch_size,
                    start_chapter,
                    "active",
                    total_planned,
                    0,
                    now,
                    now,
                ),
            )
            conn.commit()
            return serial_plan_id
        finally:
            conn.close()

    def get_serial_plan(self, serial_plan_id: str) -> dict | None:
        """Get a serial plan by ID.

        Args:
            serial_plan_id: Serial plan identifier.

        Returns:
            Serial plan dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM serial_plans WHERE id = ?",
                (serial_plan_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def update_serial_plan(
        self,
        serial_plan_id: str,
        **kwargs,
    ) -> bool:
        """Update a serial plan.

        Args:
            serial_plan_id: Serial plan identifier.
            **kwargs: Fields to update.

        Returns:
            True if update succeeded, False otherwise.
        """
        from datetime import datetime

        if not kwargs:
            return False

        # Build SET clause
        set_parts = []
        params = []
        for key, value in kwargs.items():
            if key in (
                "name",
                "status",
                "current_chapter",
                "current_queue_id",
                "current_production_run_id",
                "completed_chapters",
                "last_error",
                "completed_at",
            ):
                set_parts.append(f"{key} = ?")
                params.append(value)

        if not set_parts:
            return False

        # Always update updated_at
        set_parts.append("updated_at = ?")
        params.append(datetime.now().isoformat())

        params.append(serial_plan_id)

        conn = self._conn()
        try:
            cursor = conn.execute(
                f"UPDATE serial_plans SET {', '.join(set_parts)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_serial_plans(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List serial plans.

        Args:
            project_id: Filter by project (optional).
            status: Filter by status (optional).
            limit: Maximum number of results.

        Returns:
            List of serial plan dicts.
        """
        conn = self._conn()
        try:
            query = "SELECT * FROM serial_plans WHERE 1=1"
            params = []

            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def record_serial_plan_event(
        self,
        serial_plan_id: str,
        event_type: str,
        from_status: str | None = None,
        to_status: str | None = None,
        message: str | None = None,
        metadata_json: str | None = None,
    ) -> str | None:
        """Record a serial plan event.

        Args:
            serial_plan_id: Serial plan identifier.
            event_type: Type of event.
            from_status: Previous status (optional).
            to_status: New status (optional).
            message: Event message (optional).
            metadata_json: JSON metadata string (optional).

        Returns:
            Event ID or None if recording failed.
        """
        import uuid
        from datetime import datetime

        event_id = f"sevent_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO serial_plan_events "
                "(id, serial_plan_id, event_type, from_status, to_status, message, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    serial_plan_id,
                    event_type,
                    from_status,
                    to_status,
                    message,
                    metadata_json or "{}",
                    now,
                ),
            )
            conn.commit()
            return event_id
        except Exception:
            return None
        finally:
            conn.close()

    def get_serial_plan_events(self, serial_plan_id: str) -> list[dict]:
        """Get all events for a serial plan.

        Args:
            serial_plan_id: Serial plan identifier.

        Returns:
            List of event dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM serial_plan_events WHERE serial_plan_id = ? "
                "ORDER BY created_at ASC",
                (serial_plan_id,),
            ).fetchall()
            return [row_to_dict(row) for row in rows]
        finally:
            conn.close()

    # ── v3.7 Review Workbench Read-Only Queries ─────────────────────────────
