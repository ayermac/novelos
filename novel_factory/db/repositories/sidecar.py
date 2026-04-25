"""Scout, Secretary, ContinuityChecker, Architect agent data."""

from __future__ import annotations

import json

from ..connection import row_to_dict

class SidecarRepositoryMixin:
    def save_market_report(
        self,
        project_id: str,
        report_type: str,
        content_json: dict,
        summary: str,
        topic: str | None = None,
        keywords: list[str] | None = None,
        chapter_number: int | None = None,
    ) -> int:
        """Save a market report from Scout agent."""
        import json

        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO scout_reports "
                "(project_id, chapter_number, report_type, content_json, summary, topic, keywords) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    chapter_number,
                    report_type,
                    json.dumps(content_json, ensure_ascii=False),
                    summary,
                    topic,
                    json.dumps(keywords or [], ensure_ascii=False),
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_market_reports(
        self,
        project_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent market reports for a project."""
        import json

        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM scout_reports "
                "WHERE project_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            results = []
            for row in rows:
                r = row_to_dict(row)
                r["content_json"] = json.loads(r["content_json"])
                r["keywords"] = json.loads(r.get("keywords", "[]"))
                results.append(r)
            return results
        finally:
            conn.close()

    # Secretary Agent methods

    def save_report(
        self,
        project_id: str,
        report_type: str,
        content_json: dict,
        summary: str,
        report_date: str | None = None,
        export_format: str = "json",
        chapter_number: int | None = None,
    ) -> int:
        """Save a report from Secretary agent."""
        import json

        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO reports "
                "(project_id, chapter_number, report_type, content_json, summary, report_date, export_format) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    chapter_number,
                    report_type,
                    json.dumps(content_json, ensure_ascii=False),
                    summary,
                    report_date,
                    export_format,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_reports(
        self,
        project_id: str,
        report_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get reports for a project."""
        import json

        conn = self._conn()
        try:
            if report_type:
                rows = conn.execute(
                    "SELECT * FROM reports "
                    "WHERE project_id=? AND report_type=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (project_id, report_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM reports "
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
        import json

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
        import json

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

    # Architect Agent methods

    def save_architecture_proposal(
        self,
        project_id: str,
        proposal_type: str,
        scope: str,
        title: str,
        description: str,
        recommendation: str,
        risk_level: str = "medium",
        affected_area: list[str] | None = None,
        rationale: str | None = None,
        implementation_notes: str | None = None,
        status: str = "pending",
    ) -> int:
        """Save an architecture proposal from Architect agent."""
        import json

        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO architecture_proposals "
                "(project_id, proposal_type, scope, title, description, recommendation, "
                "risk_level, affected_area, rationale, implementation_notes, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    proposal_type,
                    scope,
                    title,
                    description,
                    recommendation,
                    risk_level,
                    json.dumps(affected_area or [], ensure_ascii=False),
                    rationale,
                    implementation_notes,
                    status,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_architecture_proposals(
        self,
        project_id: str,
        status: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get architecture proposals for a project."""
        import json

        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM architecture_proposals "
                    "WHERE project_id=? AND status=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (project_id, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM architecture_proposals "
                    "WHERE project_id=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            results = []
            for row in rows:
                r = row_to_dict(row)
                r["affected_area"] = json.loads(r.get("affected_area", "[]"))
                results.append(r)
            return results
        finally:
            conn.close()

    # ── v2.1 QualityHub and Skill ────────────────────────────────────────

    # Quality reports methods
