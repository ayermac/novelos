"""Auto-run session and step persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..connection import row_to_dict


class AutoRunRepositoryMixin:
    """CRUD for auto-run sessions and steps."""

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def create_auto_run_session(
        self,
        project_id: str,
        chapter_start: int | None,
        chapter_end: int | None,
        max_steps: int,
        dry_run: bool,
        stop_on_review: bool,
    ) -> dict:
        """Create a new auto-run session and return it."""
        session_id = uuid.uuid4().hex[:12]
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO auto_run_sessions
                (id, project_id, chapter_start, chapter_end, max_steps, dry_run, stop_on_review, status, current_step)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'running', 0)
                """,
                (
                    session_id,
                    project_id,
                    chapter_start,
                    chapter_end,
                    max_steps,
                    1 if dry_run else 0,
                    1 if stop_on_review else 0,
                ),
            )
            conn.commit()
            return self.get_auto_run_session(session_id)
        finally:
            conn.close()

    def get_auto_run_session(self, session_id: str) -> dict | None:
        """Get session by id."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM auto_run_sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def list_auto_run_sessions(self, project_id: str, limit: int = 20) -> list[dict]:
        """List sessions for a project, newest first."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM auto_run_sessions WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def update_auto_run_session_status(
        self,
        session_id: str,
        status: str,
        stop_reason: str | None = None,
        current_step: int | None = None,
    ) -> bool:
        """Update session status and optional fields."""
        conn = self._conn()
        try:
            sets = ["status = ?", "updated_at = datetime('now','+8 hours')"]
            params: list = [status]

            if stop_reason is not None:
                sets.append("stop_reason = ?")
                params.append(stop_reason)
            if current_step is not None:
                sets.append("current_step = ?")
                params.append(current_step)
            if status in ("stopped", "completed", "failed", "cancelled"):
                sets.append("ended_at = datetime('now','+8 hours')")

            params.append(session_id)
            sql = f"UPDATE auto_run_sessions SET {', '.join(sets)} WHERE id=?"
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Step CRUD
    # ------------------------------------------------------------------

    def create_auto_run_step(
        self,
        session_id: str,
        step_number: int,
        action: str,
        label: str,
        target_chapter: int | None,
    ) -> dict:
        """Record that a step has started."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO auto_run_steps
                (session_id, step_number, action, label, target_chapter, started_at)
                VALUES (?, ?, ?, ?, ?, datetime('now','+8 hours'))
                """,
                (session_id, step_number, action, label, target_chapter),
            )
            conn.commit()
            return self._get_auto_run_step(session_id, step_number)
        finally:
            conn.close()

    def _get_auto_run_step(self, session_id: str, step_number: int) -> dict:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM auto_run_steps WHERE session_id=? AND step_number=?",
                (session_id, step_number),
            ).fetchone()
            return row_to_dict(row) or {}
        finally:
            conn.close()

    def complete_auto_run_step(
        self,
        session_id: str,
        step_number: int,
        result: str,
        warnings: list[str] | None = None,
        error: str | None = None,
    ) -> bool:
        """Update step with completion info."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                """
                UPDATE auto_run_steps
                SET result=?, warnings=?, error=?, completed_at=datetime('now','+8 hours')
                WHERE session_id=? AND step_number=?
                """,
                (
                    result,
                    json.dumps(warnings or [], ensure_ascii=False),
                    error,
                    session_id,
                    step_number,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_auto_run_steps(self, session_id: str) -> list[dict]:
        """List all steps for a session in order."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM auto_run_steps WHERE session_id=? ORDER BY step_number",
                (session_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = row_to_dict(r)
                if d.get("warnings"):
                    try:
                        d["warnings"] = json.loads(d["warnings"])
                    except Exception:
                        d["warnings"] = []
                else:
                    d["warnings"] = []
                result.append(d)
            return result
        finally:
            conn.close()

    def get_last_auto_run_step(self, session_id: str) -> dict | None:
        """Get the most recent step for a session."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM auto_run_steps WHERE session_id=? ORDER BY step_number DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()
