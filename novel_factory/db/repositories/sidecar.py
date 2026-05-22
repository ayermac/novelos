"""ContinuityChecker sidecar diagnostic data."""

from __future__ import annotations

import json

from ..connection import row_to_dict

class SidecarRepositoryMixin:
    # ContinuityChecker Agent methods

    def save_continuity_report(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
        content_json: dict,
        summary: str,
        issue_count: int = 0,
        warning_count: int = 0,
    ) -> int:
        """Save a continuity report from ContinuityChecker agent."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO continuity_reports "
                "(project_id, from_chapter, to_chapter, content_json, summary, issue_count, warning_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    from_chapter,
                    to_chapter,
                    json.dumps(content_json, ensure_ascii=False),
                    summary,
                    issue_count,
                    warning_count,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_continuity_reports(
        self,
        project_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get continuity reports for a project."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM continuity_reports "
                "WHERE project_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            results = []
            for row in rows:
                r = row_to_dict(row)
                r["content_json"] = json.loads(r["content_json"])
                results.append(r)
            return results
        finally:
            conn.close()
