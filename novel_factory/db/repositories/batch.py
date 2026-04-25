"""Batch production runs, items, and human review sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict

class BatchRepositoryMixin:
    def create_production_run(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
    ) -> str:
        """Create a new production run.

        Args:
            project_id: Project identifier.
            from_chapter: Starting chapter number.
            to_chapter: Ending chapter number.

        Returns:
            Run ID.
        """
        import uuid
        from datetime import datetime, timezone

        run_id = f"batch_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        total_chapters = to_chapter - from_chapter + 1

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO production_runs "
                "(id, project_id, from_chapter, to_chapter, status, total_chapters, "
                "completed_chapters, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, project_id, from_chapter, to_chapter, "running", total_chapters, 0, now, now),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()

    def update_production_run(
        self,
        run_id: str,
        status: str | None = None,
        completed_chapters: int | None = None,
        blocked_chapter: int | None = None,
        error: str | None = None,
        completed_at: str | None = None,
    ) -> bool:
        """Update a production run.

        Args:
            run_id: Run identifier.
            status: New status (optional).
            completed_chapters: Number of completed chapters (optional).
            blocked_chapter: Chapter that caused block (optional).
            error: Error message (optional).
            completed_at: Completion timestamp (optional).

        Returns:
            True if update succeeded.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        
        conn = self._conn()
        try:
            updates = ["updated_at = ?"]
            params: list[Any] = [now]
            
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            
            if completed_chapters is not None:
                updates.append("completed_chapters = ?")
                params.append(completed_chapters)
            
            if blocked_chapter is not None:
                updates.append("blocked_chapter = ?")
                params.append(blocked_chapter)
            
            if error is not None:
                updates.append("error = ?")
                params.append(error)
            
            if completed_at is not None:
                updates.append("completed_at = ?")
                params.append(completed_at)
            
            params.append(run_id)
            
            cursor = conn.execute(
                f"UPDATE production_runs SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            return False
        finally:
            conn.close()

    def get_production_run(self, run_id: str) -> dict | None:
        """Get a production run by ID.

        Args:
            run_id: Run identifier.

        Returns:
            Production run dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM production_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def list_production_runs(
        self,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List production runs.

        Args:
            project_id: Optional project ID filter.
            limit: Maximum number of runs to return.

        Returns:
            List of production run dicts.
        """
        conn = self._conn()
        try:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM production_runs WHERE project_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM production_runs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def create_production_run_item(
        self,
        run_id: str,
        project_id: str,
        chapter_number: int,
    ) -> str:
        """Create a production run item.

        Args:
            run_id: Run identifier.
            project_id: Project identifier.
            chapter_number: Chapter number.

        Returns:
            Item ID.
        """
        import uuid
        from datetime import datetime, timezone

        item_id = f"item_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO production_run_items "
                "(id, run_id, project_id, chapter_number, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item_id, run_id, project_id, chapter_number, "pending", now, now),
            )
            conn.commit()
            return item_id
        finally:
            conn.close()

    def update_production_run_item(
        self,
        item_id: str,
        status: str | None = None,
        workflow_run_id: str | None = None,
        chapter_status: str | None = None,
        quality_pass: bool | None = None,
        error: str | None = None,
        requires_human: bool | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> bool:
        """Update a production run item.

        Args:
            item_id: Item identifier.
            status: New status (optional).
            workflow_run_id: Workflow run ID (optional).
            chapter_status: Chapter status (optional).
            quality_pass: Quality pass flag (optional).
            error: Error message (optional).
            requires_human: Requires human flag (optional).
            started_at: Start timestamp (optional).
            completed_at: Completion timestamp (optional).

        Returns:
            True if update succeeded.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        
        conn = self._conn()
        try:
            updates = ["updated_at = ?"]
            params: list[Any] = [now]
            
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            
            if workflow_run_id is not None:
                updates.append("workflow_run_id = ?")
                params.append(workflow_run_id)
            
            if chapter_status is not None:
                updates.append("chapter_status = ?")
                params.append(chapter_status)
            
            if quality_pass is not None:
                updates.append("quality_pass = ?")
                params.append(1 if quality_pass else 0)
            
            if error is not None:
                updates.append("error = ?")
                params.append(error)
            
            if requires_human is not None:
                updates.append("requires_human = ?")
                params.append(1 if requires_human else 0)
            
            if started_at is not None:
                updates.append("started_at = ?")
                params.append(started_at)
            
            if completed_at is not None:
                updates.append("completed_at = ?")
                params.append(completed_at)
            
            params.append(item_id)
            
            cursor = conn.execute(
                f"UPDATE production_run_items SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            return False
        finally:
            conn.close()

    def get_production_run_items(self, run_id: str) -> list[dict]:
        """Get all items for a production run.

        Args:
            run_id: Run identifier.

        Returns:
            List of production run item dicts, sorted by chapter_number.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM production_run_items WHERE run_id = ? "
                "ORDER BY chapter_number",
                (run_id,),
            ).fetchall()
            results = []
            for row in rows:
                r = row_to_dict(row)
                # Convert SQLite 0/1 to bool
                if "quality_pass" in r and r["quality_pass"] is not None:
                    r["quality_pass"] = bool(r["quality_pass"])
                if "requires_human" in r:
                    r["requires_human"] = bool(r.get("requires_human", 0))
                results.append(r)
            return results
        finally:
            conn.close()

    def get_production_run_item_by_chapter(
        self,
        run_id: str,
        chapter_number: int,
    ) -> dict | None:
        """Get a production run item by run and chapter.

        Args:
            run_id: Run identifier.
            chapter_number: Chapter number.

        Returns:
            Production run item dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM production_run_items WHERE run_id = ? AND chapter_number = ?",
                (run_id, chapter_number),
            ).fetchone()
            if not row:
                return None
            r = row_to_dict(row)
            # Convert SQLite 0/1 to bool
            if "quality_pass" in r and r["quality_pass"] is not None:
                r["quality_pass"] = bool(r["quality_pass"])
            if "requires_human" in r:
                r["requires_human"] = bool(r.get("requires_human", 0))
            return r
        finally:
            conn.close()

    def save_human_review_session(
        self,
        run_id: str,
        project_id: str,
        decision: str,
        notes: str | None = None,
    ) -> str:
        """Save a human review session.

        Args:
            run_id: Run identifier.
            project_id: Project identifier.
            decision: Review decision (approve, request_changes, reject).
            notes: Optional review notes.

        Returns:
            Session ID.
        """
        import uuid
        from datetime import datetime, timezone

        session_id = f"review_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO human_review_sessions "
                "(id, run_id, project_id, decision, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, run_id, project_id, decision, notes, now),
            )
            conn.commit()
            return session_id
        finally:
            conn.close()

    def get_human_review_sessions(self, run_id: str) -> list[dict]:
        """Get all human review sessions for a production run.

        Args:
            run_id: Run identifier.

        Returns:
            List of human review session dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM human_review_sessions WHERE run_id = ? "
                "ORDER BY created_at DESC",
                (run_id,),
            ).fetchall()
            return [row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def get_latest_human_review_session(self, run_id: str) -> dict | None:
        """Get the latest human review session for a production run.

        Args:
            run_id: Run identifier.

        Returns:
            Latest human review session dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM human_review_sessions WHERE run_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    # ── Batch Revision (v3.2) ─────────────────────────────────────
