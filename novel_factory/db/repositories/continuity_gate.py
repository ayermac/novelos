"""Batch continuity gate results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..connection import row_to_dict

class ContinuityGateRepositoryMixin:
    def save_batch_continuity_gate(
        self,
        run_id: str,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
        continuity_report_id: str | None,
        status: str,
        issue_count: int = 0,
        warning_count: int = 0,
        blocking_issues_json: str = "[]",
        summary: str | None = None,
    ) -> str:
        """Save a batch continuity gate result.

        Args:
            run_id: Production run ID.
            project_id: Project identifier.
            from_chapter: Start chapter number.
            to_chapter: End chapter number.
            continuity_report_id: ID from continuity_reports table.
            status: Gate status (passed, warning, failed, error).
            issue_count: Total error+warning issue count.
            warning_count: Warning issue count.
            blocking_issues_json: JSON string of blocking issues.
            summary: Gate summary text.

        Returns:
            Gate ID.
        """
        gate_id = f"bcgate_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO batch_continuity_gates "
                "(id, run_id, project_id, from_chapter, to_chapter, "
                "continuity_report_id, status, issue_count, warning_count, "
                "blocking_issues_json, summary, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    gate_id, run_id, project_id, from_chapter, to_chapter,
                    continuity_report_id, status, issue_count, warning_count,
                    blocking_issues_json, summary, now, now,
                ),
            )
            conn.commit()
            return gate_id
        finally:
            conn.close()

    def get_latest_batch_continuity_gate(self, run_id: str) -> dict | None:
        """Get the latest batch continuity gate for a run.

        Args:
            run_id: Production run ID.

        Returns:
            Gate dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM batch_continuity_gates "
                "WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_batch_continuity_gates(self, run_id: str, limit: int = 10) -> list[dict]:
        """Get batch continuity gates for a run, most recent first.

        Args:
            run_id: Production run ID.
            limit: Maximum number of gates to return.

        Returns:
            List of gate dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM batch_continuity_gates "
                "WHERE run_id = ? ORDER BY created_at DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
            return [row_to_dict(row) for row in rows]
        finally:
            conn.close()

    # ── Production Queue (v3.4) ─────────────────────────────────────
