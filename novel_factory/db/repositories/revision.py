"""Batch revision runs, items, and chapter review notes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..connection import row_to_dict

class RevisionRepositoryMixin:
    def create_batch_revision_run(
        self,
        source_run_id: str,
        project_id: str,
        decision_session_id: str,
        plan_json: str,
        affected_chapters_json: str,
    ) -> str:
        """Create a batch revision run.

        Args:
            source_run_id: Source production run ID.
            project_id: Project identifier.
            decision_session_id: Human review session ID.
            plan_json: JSON string of the revision plan.
            affected_chapters_json: JSON string of affected chapters list.

        Returns:
            Revision run ID.
        """
        revision_run_id = f"batchrev_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO batch_revision_runs "
                "(id, source_run_id, project_id, status, decision_session_id, "
                "plan_json, affected_chapters_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    revision_run_id,
                    source_run_id,
                    project_id,
                    "pending",
                    decision_session_id,
                    plan_json,
                    affected_chapters_json,
                    now,
                    now,
                ),
            )
            conn.commit()
            return revision_run_id
        finally:
            conn.close()

    def update_batch_revision_run(
        self,
        revision_run_id: str,
        status: str | None = None,
        error: str | None = None,
        completed_at: str | None = None,
    ) -> bool:
        """Update a batch revision run.

        Args:
            revision_run_id: Revision run identifier.
            status: New status (optional).
            error: Error message (optional).
            completed_at: Completion timestamp (optional).

        Returns:
            True if row was updated, False otherwise.
        """
        conn = self._conn()
        try:
            updates = ["updated_at = ?"]
            params = [datetime.now().isoformat()]

            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if error is not None:
                updates.append("error = ?")
                params.append(error)
            if completed_at is not None:
                updates.append("completed_at = ?")
                params.append(completed_at)

            params.append(revision_run_id)

            cursor = conn.execute(
                f"UPDATE batch_revision_runs SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_batch_revision_run(self, revision_run_id: str) -> dict | None:
        """Get a batch revision run by ID.

        Args:
            revision_run_id: Revision run identifier.

        Returns:
            Revision run dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM batch_revision_runs WHERE id = ?",
                (revision_run_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_batch_revision_item(
        self,
        revision_run_id: str,
        chapter_number: int,
        action: str,
        target_status: str | None = None,
        notes: str | None = None,
    ) -> str:
        """Create a batch revision item.

        Args:
            revision_run_id: Revision run identifier.
            chapter_number: Chapter number.
            action: Action type (rerun_chapter, resume_to_status, rerun_tail).
            target_status: Target status for resume_to_status.
            notes: Review notes for this chapter.

        Returns:
            Revision item ID.
        """
        item_id = f"revitem_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO batch_revision_items "
                "(id, revision_run_id, chapter_number, action, target_status, notes, "
                "status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id,
                    revision_run_id,
                    chapter_number,
                    action,
                    target_status,
                    notes,
                    "pending",
                    now,
                    now,
                ),
            )
            conn.commit()
            return item_id
        finally:
            conn.close()

    def update_batch_revision_item(
        self,
        item_id: str,
        status: str | None = None,
        workflow_run_id: str | None = None,
        error: str | None = None,
        completed_at: str | None = None,
    ) -> bool:
        """Update a batch revision item.

        Args:
            item_id: Revision item identifier.
            status: New status (optional).
            workflow_run_id: Workflow run ID (optional).
            error: Error message (optional).
            completed_at: Completion timestamp (optional).

        Returns:
            True if row was updated, False otherwise.
        """
        conn = self._conn()
        try:
            updates = ["updated_at = ?"]
            params = [datetime.now().isoformat()]

            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if workflow_run_id is not None:
                updates.append("workflow_run_id = ?")
                params.append(workflow_run_id)
            if error is not None:
                updates.append("error = ?")
                params.append(error)
            if completed_at is not None:
                updates.append("completed_at = ?")
                params.append(completed_at)

            params.append(item_id)

            cursor = conn.execute(
                f"UPDATE batch_revision_items SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_batch_revision_items(self, revision_run_id: str) -> list[dict]:
        """Get all batch revision items for a revision run.

        Args:
            revision_run_id: Revision run identifier.

        Returns:
            List of revision item dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM batch_revision_items WHERE revision_run_id = ? "
                "ORDER BY chapter_number",
                (revision_run_id,),
            ).fetchall()
            return [row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def save_chapter_review_note(
        self,
        project_id: str,
        chapter_number: int,
        source_run_id: str,
        revision_run_id: str,
        notes: str,
    ) -> str:
        """Save a chapter review note.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            source_run_id: Source production run ID.
            revision_run_id: Revision run ID.
            notes: Review notes.

        Returns:
            Note ID.
        """
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO chapter_review_notes "
                "(id, project_id, chapter_number, source_run_id, revision_run_id, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (note_id, project_id, chapter_number, source_run_id, revision_run_id, notes, now),
            )
            conn.commit()
            return note_id
        finally:
            conn.close()

    def get_chapter_review_notes(
        self,
        project_id: str,
        chapter_number: int,
        source_run_id: str | None = None,
    ) -> list[dict]:
        """Get chapter review notes.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            source_run_id: Optional source run ID filter.

        Returns:
            List of review note dicts.
        """
        conn = self._conn()
        try:
            if source_run_id:
                rows = conn.execute(
                    "SELECT * FROM chapter_review_notes "
                    "WHERE project_id = ? AND chapter_number = ? AND source_run_id = ? "
                    "ORDER BY created_at DESC",
                    (project_id, chapter_number, source_run_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chapter_review_notes "
                    "WHERE project_id = ? AND chapter_number = ? "
                    "ORDER BY created_at DESC",
                    (project_id, chapter_number),
                ).fetchall()
            return [row_to_dict(row) for row in rows]
        finally:
            conn.close()

    # ── Batch Continuity Gate (v3.3) ─────────────────────────────
