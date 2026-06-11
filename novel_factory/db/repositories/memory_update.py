"""Memory update batches and items CRUD operations."""

from __future__ import annotations

import uuid

from ..connection import row_to_dict

_MEMORY_CURATOR_LOCK_STALE_MINUTES = 120


class MemoryUpdateRepositoryMixin:
    """Repository mixin for memory_update_batches/items CRUD operations."""

    # --- MemoryCurator extraction locks ---

    def _delete_stale_memory_curator_lock(
        self,
        conn,
        project_id: str,
        chapter_number: int,
    ) -> int:
        """Delete expired MemoryCurator locks for a project/chapter."""
        cursor = conn.execute(
            "DELETE FROM memory_curator_locks "
            "WHERE project_id=? AND chapter_number=? "
            "AND status='running' "
            "AND locked_at <= datetime('now', '+8 hours', ?)",
            (
                project_id,
                chapter_number,
                f"-{_MEMORY_CURATOR_LOCK_STALE_MINUTES} minutes",
            ),
        )
        return int(cursor.rowcount or 0)

    def acquire_memory_curator_lock(
        self,
        project_id: str,
        chapter_number: int,
        run_id: str | None = None,
    ) -> dict:
        """Acquire the per-project/chapter MemoryCurator lock.

        Returns {"acquired": True, "lock": row} when the caller owns the lock.
        Returns {"acquired": False, "lock": existing_row} when another active
        extraction already holds it.
        """
        conn = self._conn()
        try:
            try:
                conn.execute(
                    "INSERT INTO memory_curator_locks "
                    "(project_id, chapter_number, run_id, status) "
                    "VALUES (?, ?, ?, 'running')",
                    (project_id, chapter_number, run_id),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM memory_curator_locks "
                    "WHERE project_id=? AND chapter_number=?",
                    (project_id, chapter_number),
                ).fetchone()
                return {"acquired": True, "lock": row_to_dict(row)}
            except Exception:
                conn.rollback()
                self._delete_stale_memory_curator_lock(conn, project_id, chapter_number)
                conn.commit()
                try:
                    conn.execute(
                        "INSERT INTO memory_curator_locks "
                        "(project_id, chapter_number, run_id, status) "
                        "VALUES (?, ?, ?, 'running')",
                        (project_id, chapter_number, run_id),
                    )
                    conn.commit()
                    row = conn.execute(
                        "SELECT * FROM memory_curator_locks "
                        "WHERE project_id=? AND chapter_number=?",
                        (project_id, chapter_number),
                    ).fetchone()
                    return {"acquired": True, "lock": row_to_dict(row)}
                except Exception:
                    conn.rollback()
                row = conn.execute(
                    "SELECT * FROM memory_curator_locks "
                    "WHERE project_id=? AND chapter_number=?",
                    (project_id, chapter_number),
                ).fetchone()
                return {"acquired": False, "lock": row_to_dict(row)}
        finally:
            conn.close()

    def get_memory_curator_lock(
        self,
        project_id: str,
        chapter_number: int,
    ) -> dict | None:
        """Return the active MemoryCurator lock for a project/chapter, if any."""
        conn = self._conn()
        try:
            deleted = self._delete_stale_memory_curator_lock(conn, project_id, chapter_number)
            if deleted:
                conn.commit()
            row = conn.execute(
                "SELECT * FROM memory_curator_locks "
                "WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def release_memory_curator_lock(
        self,
        project_id: str,
        chapter_number: int,
        run_id: str | None = None,
    ) -> bool:
        """Release the MemoryCurator lock held by run_id for this chapter."""
        conn = self._conn()
        try:
            query = (
                "DELETE FROM memory_curator_locks "
                "WHERE project_id=? AND chapter_number=?"
            )
            params: list = [project_id, chapter_number]
            if run_id is not None:
                query += " AND (run_id=? OR run_id IS NULL)"
                params.append(run_id)
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # --- Batches ---

    def list_memory_batches(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[dict]:
        """List memory update batches for a project."""
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM memory_update_batches "
                    "WHERE project_id=? AND status=? ORDER BY created_at DESC",
                    (project_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_update_batches "
                    "WHERE project_id=? ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_memory_batch(self, batch_id: str) -> dict | None:
        """Get a memory update batch by ID."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM memory_update_batches WHERE id=?",
                (batch_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_memory_batch(
        self,
        project_id: str,
        chapter_number: int | None = None,
        run_id: str | None = None,
        summary: str | None = None,
    ) -> dict:
        """Create a new memory update batch."""
        batch_id = uuid.uuid4().hex
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO memory_update_batches "
                "(id, project_id, chapter_number, run_id, summary) "
                "VALUES (?, ?, ?, ?, ?)",
                (batch_id, project_id, chapter_number, run_id, summary),
            )
            conn.commit()
            return self.get_memory_batch(batch_id)  # type: ignore[return-value]
        finally:
            conn.close()

    def update_memory_batch(
        self,
        batch_id: str,
        data: dict,
    ) -> dict | None:
        """Update a memory update batch."""
        conn = self._conn()
        try:
            fields = []
            values = []
            for key in ("status", "summary"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_memory_batch(batch_id)

            fields.append("updated_at=datetime('now', '+8 hours')")
            values.append(batch_id)
            cursor = conn.execute(
                f"UPDATE memory_update_batches SET {', '.join(fields)} WHERE id=?",
                values,
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
            return self.get_memory_batch(batch_id)
        finally:
            conn.close()

    # --- Items ---

    def list_memory_items(
        self,
        batch_id: str,
        status: str | None = None,
    ) -> list[dict]:
        """List memory update items for a batch."""
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM memory_update_items "
                    "WHERE batch_id=? AND status=? ORDER BY created_at",
                    (batch_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_update_items "
                    "WHERE batch_id=? ORDER BY created_at",
                    (batch_id,),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_memory_items_by_project(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[dict]:
        """List all memory update items for a project."""
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM memory_update_items "
                    "WHERE project_id=? AND status=? ORDER BY created_at DESC",
                    (project_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_update_items "
                    "WHERE project_id=? ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_memory_item(self, item_id: str) -> dict | None:
        """Get a memory update item by ID."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM memory_update_items WHERE id=?",
                (item_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_memory_item(
        self,
        batch_id: str,
        project_id: str,
        target_table: str,
        operation: str,
        after_json: str,
        target_id: str | None = None,
        before_json: str | None = None,
        confidence: float = 0.8,
        evidence_text: str | None = None,
        rationale: str | None = None,
    ) -> dict:
        """Create a new memory update item."""
        item_id = uuid.uuid4().hex
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO memory_update_items "
                "(id, batch_id, project_id, target_table, target_id, operation, "
                "before_json, after_json, confidence, evidence_text, rationale) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id, batch_id, project_id, target_table, target_id,
                    operation, before_json, after_json, confidence,
                    evidence_text, rationale,
                ),
            )
            conn.commit()
            return self.get_memory_item(item_id)  # type: ignore[return-value]
        finally:
            conn.close()

    def update_memory_item(
        self,
        item_id: str,
        data: dict,
    ) -> dict | None:
        """Update a memory update item."""
        conn = self._conn()
        try:
            fields = []
            values = []
            for key in (
                "status",
                "target_table",
                "target_id",
                "operation",
                "before_json",
                "after_json",
                "confidence",
                "rationale",
                "evidence_text",
                "error_message",
            ):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_memory_item(item_id)

            if "status" in data and data["status"] in ("applied", "ignored"):
                fields.append("applied_at=datetime('now', '+8 hours')")

            values.append(item_id)
            cursor = conn.execute(
                f"UPDATE memory_update_items SET {', '.join(fields)} WHERE id=?",
                values,
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
            return self.get_memory_item(item_id)
        finally:
            conn.close()

    def delete_memory_items_by_project(self, project_id: str) -> int:
        """Delete all memory update items for a project."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM memory_update_items WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def delete_memory_batches_by_project(self, project_id: str) -> int:
        """Delete all memory update batches for a project."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM memory_update_batches WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
