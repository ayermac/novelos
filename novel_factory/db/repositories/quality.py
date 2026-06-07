"""Quality reports, reviews, skill runs, learned patterns, best practices, polish reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict

class QualityRepositoryMixin:
    def save_review(
        self,
        project_id: str,
        chapter_id: int,
        passed: bool,
        score: int,
        setting_score: int = 0,
        logic_score: int = 0,
        poison_score: int = 0,
        text_score: int = 0,
        pacing_score: int = 0,
        issues: list[str] | None = None,
        suggestions: list[str] | None = None,
        revision_target: str | None = None,
    ) -> int:
        """Save a review record. Returns review id."""
        conn = self._conn()
        try:
            # Delete previous review for this chapter (one-to-one)
            conn.execute("DELETE FROM reviews WHERE chapter_id=?", (chapter_id,))
            
            # Build summary without revision_target prefix
            summary_parts = []
            if issues:
                summary_parts.append(f"issues={len(issues)}")
            if suggestions:
                summary_parts.append(f"suggestions={len(suggestions)}")
            summary = ", ".join(summary_parts) if summary_parts else None
            
            cursor = conn.execute(
                "INSERT INTO reviews "
                "(project_id, chapter_id, pass, score, setting_score, "
                "logic_score, poison_score, text_score, pacing_score, "
                "issues, suggestions, summary, revision_target) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id, chapter_id, 1 if passed else 0, score,
                    setting_score, logic_score, poison_score, text_score,
                    pacing_score,
                    json.dumps(issues or [], ensure_ascii=False),
                    json.dumps(suggestions or [], ensure_ascii=False),
                    summary,
                    revision_target,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_latest_review(self, project_id: str, chapter_id: int) -> dict | None:
        """Get latest review for a chapter."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM reviews WHERE project_id=? AND chapter_id=? "
                "ORDER BY reviewed_at DESC LIMIT 1",
                (project_id, chapter_id),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    # ── Chapter state (state card) ────────────────────────────

    def save_quality_report(
        self,
        project_id: str,
        chapter_number: int,
        stage: str,
        overall_score: float,
        pass_: bool,
        revision_target: str | None = None,
        blocking_issues: list | None = None,
        warnings: list | None = None,
        skill_results: list | None = None,
        quality_dimensions: dict | None = None,
    ) -> int:
        """Save a quality report from QualityHub.
        
        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            stage: Quality check stage (draft, polished, final).
            overall_score: Overall quality score (0-100).
            pass_: Whether the quality check passed.
            revision_target: Target agent for revision (if failed).
            blocking_issues: List of blocking issues.
            warnings: List of warnings.
            skill_results: List of skill execution results.
            quality_dimensions: Dict of quality dimension scores.
        
        Returns:
            Report ID.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO quality_reports "
                "(project_id, chapter_number, stage, overall_score, pass, revision_target, "
                "blocking_issues_json, warnings_json, skill_results_json, quality_dimensions_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    chapter_number,
                    stage,
                    overall_score,
                    1 if pass_ else 0,
                    revision_target,
                    json.dumps(blocking_issues or [], ensure_ascii=False),
                    json.dumps(warnings or [], ensure_ascii=False),
                    json.dumps(skill_results or [], ensure_ascii=False),
                    json.dumps(quality_dimensions or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_quality_reports(
        self,
        project_id: str,
        chapter_number: int | None = None,
        stage: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get quality reports for a project.
        
        Args:
            project_id: Project identifier.
            chapter_number: Optional chapter number filter.
            stage: Optional stage filter.
            limit: Maximum number of reports to return.
        
        Returns:
            List of quality reports.
        """
        conn = self._conn()
        try:
            query = "SELECT * FROM quality_reports WHERE project_id=?"
            params: list[Any] = [project_id]
            
            if chapter_number is not None:
                query += " AND chapter_number=?"
                params.append(chapter_number)
            
            if stage:
                query += " AND stage=?"
                params.append(stage)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                r = row_to_dict(row)
                r["pass"] = bool(r.get("pass", 0))
                r["blocking_issues"] = json.loads(r.get("blocking_issues_json", "[]"))
                r["warnings"] = json.loads(r.get("warnings_json", "[]"))
                r["skill_results"] = json.loads(r.get("skill_results_json", "[]"))
                r["quality_dimensions"] = json.loads(r.get("quality_dimensions_json", "{}"))
                results.append(r)
            return results
        finally:
            conn.close()

    def get_latest_quality_report(
        self,
        project_id: str,
        chapter_number: int,
        stage: str,
    ) -> dict | None:
        """Get the latest quality report for a specific chapter and stage.
        
        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            stage: Quality check stage.
        
        Returns:
            Latest quality report or None.
        """
        reports = self.get_quality_reports(project_id, chapter_number, stage, limit=1)
        return reports[0] if reports else None

    # Skill runs methods

    def save_skill_run(
        self,
        project_id: str,
        skill_id: str,
        skill_type: str,
        ok: bool,
        error: str | None = None,
        input_json: dict | None = None,
        output_json: dict | None = None,
        duration_ms: int | None = None,
        chapter_number: int | None = None,
        agent_id: str | None = None,
        stage: str | None = None,
    ) -> int:
        """Save a skill execution record.
        
        Args:
            project_id: Project identifier.
            skill_id: Skill identifier.
            skill_type: Skill type (transform, validator, context, report).
            ok: Whether the skill execution succeeded.
            error: Error message (if failed).
            input_json: Input payload.
            output_json: Output result.
            duration_ms: Execution duration in milliseconds.
            chapter_number: Optional chapter number.
            agent_id: Optional agent that triggered the skill.
            stage: Optional execution stage.
        
        Returns:
            Run ID.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO skill_runs "
                "(project_id, chapter_number, skill_id, skill_type, agent_id, stage, "
                "ok, error, input_json, output_json, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    chapter_number,
                    skill_id,
                    skill_type,
                    agent_id,
                    stage,
                    1 if ok else 0,
                    error,
                    json.dumps(input_json or {}, ensure_ascii=False),
                    json.dumps(output_json or {}, ensure_ascii=False),
                    duration_ms,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_skill_runs(
        self,
        project_id: str,
        skill_id: str | None = None,
        agent_id: str | None = None,
        chapter_number: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get skill execution records.
        
        Args:
            project_id: Project identifier.
            skill_id: Optional skill ID filter.
            agent_id: Optional agent ID filter.
            chapter_number: Optional chapter number filter.
            limit: Maximum number of records to return.
        
        Returns:
            List of skill run records.
        """
        conn = self._conn()
        try:
            query = "SELECT * FROM skill_runs WHERE project_id=?"
            params: list[Any] = [project_id]
            
            if skill_id:
                query += " AND skill_id=?"
                params.append(skill_id)
            
            if agent_id:
                query += " AND agent_id=?"
                params.append(agent_id)
            
            if chapter_number is not None:
                query += " AND chapter_number=?"
                params.append(chapter_number)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                r = row_to_dict(row)
                r["ok"] = bool(r.get("ok", 0))
                r["input"] = json.loads(r.get("input_json", "{}"))
                r["output"] = json.loads(r.get("output_json", "{}"))
                results.append(r)
            return results
        finally:
            conn.close()

    # ── Batch Production Methods (v3.0) ─────────────────────────────

    def save_learned_pattern(
        self,
        project_id: str,
        category: str,
        pattern: str,
        chapter_number: int | None = None,
    ) -> int:
        """Save or update a learned pattern.

        If a pattern with the same project_id + category + pattern already exists,
        increment its frequency and update last_seen.

        Returns:
            Pattern id.
        """
        conn = self._conn()
        try:
            existing = conn.execute(
                "SELECT id, frequency FROM learned_patterns "
                "WHERE project_id=? AND category=? AND pattern=?",
                (project_id, category, pattern),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE learned_patterns SET frequency=?, last_seen=datetime('now','+8 hours') "
                    "WHERE id=?",
                    (existing["frequency"] + 1, existing["id"]),
                )
                conn.commit()
                return existing["id"]
            cursor = conn.execute(
                "INSERT INTO learned_patterns (project_id, chapter_number, category, pattern) "
                "VALUES (?, ?, ?, ?)",
                (project_id, chapter_number, category, pattern),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_learned_patterns(
        self,
        project_id: str,
        category: str | None = None,
        enabled_only: bool = True,
        min_frequency: int = 1,
        limit: int = 20,
    ) -> list[dict]:
        """Get learned patterns for a project, sorted by frequency descending.

        Args:
            project_id: Project identifier.
            category: Optional category filter.
            enabled_only: Only return enabled patterns.
            min_frequency: Minimum frequency threshold.
            limit: Maximum number of patterns to return.

        Returns:
            List of pattern dicts.
        """
        conn = self._conn()
        try:
            query = (
                "SELECT * FROM learned_patterns "
                "WHERE project_id=? AND frequency >= ?"
            )
            params: list[Any] = [project_id, min_frequency]

            if category:
                query += " AND category=?"
                params.append(category)
            if enabled_only:
                query += " AND enabled=1"

            query += " ORDER BY frequency DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def disable_learned_pattern(self, pattern_id: int) -> bool:
        """Disable a learned pattern. Returns True if found and updated."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE learned_patterns SET enabled=0 WHERE id=?", (pattern_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Best practices (Q6) ────────────────────────────────────

    def get_best_practices(
        self,
        project_id: str | None = None,
        category: str | None = None,
        min_score: float = 80.0,
        limit: int = 10,
    ) -> list[dict]:
        """Get best practices, optionally filtered.

        Args:
            project_id: Optional project filter.
            category: Optional category filter.
            min_score: Minimum average score threshold.
            limit: Maximum number of practices to return.

        Returns:
            List of practice dicts sorted by avg_score descending.
        """
        conn = self._conn()
        try:
            query = "SELECT * FROM best_practices WHERE avg_score >= ?"
            params: list[Any] = [min_score]

            if project_id:
                query += " AND project_id=?"
                params.append(project_id)
            if category:
                query += " AND category=?"
                params.append(category)

            query += " ORDER BY avg_score DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Anti-patterns (Q2 — read from DB) ──────────────────────

    def get_anti_patterns(
        self,
        category: str | None = None,
        enabled_only: bool = True,
        severity: str | None = None,
    ) -> list[dict]:
        """Get anti-patterns from the database.

        Args:
            category: Optional category filter.
            enabled_only: Only return enabled patterns.
            severity: Optional severity filter.

        Returns:
            List of anti-pattern dicts.
        """
        conn = self._conn()
        try:
            query = "SELECT * FROM anti_patterns WHERE 1=1"
            params: list[Any] = []

            if category:
                query += " AND category=?"
                params.append(category)
            if enabled_only:
                query += " AND enabled=1"
            if severity:
                query += " AND severity=?"
                params.append(severity)

            query += " ORDER BY severity, frequency DESC"

            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Review issue categories (Q7) ──────────────────────────

    def save_polish_report(
        self,
        project_id: str,
        chapter_number: int,
        fact_change_risk: str,
        style_changes: list | None = None,
        rhythm_changes: list | None = None,
        dialogue_changes: list | None = None,
        ai_trace_fixes: list | None = None,
        summary: str | None = None,
        source_version: int | None = None,
        target_version: int | None = None,
    ) -> int:
        """Save a polish report."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO polish_reports "
                "(project_id, chapter_number, source_version, target_version, "
                "style_changes, rhythm_changes, dialogue_changes, "
                "ai_trace_fixes, fact_change_risk, summary) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id, chapter_number, source_version, target_version,
                    json.dumps(style_changes or [], ensure_ascii=False),
                    json.dumps(rhythm_changes or [], ensure_ascii=False),
                    json.dumps(dialogue_changes or [], ensure_ascii=False),
                    json.dumps(ai_trace_fixes or [], ensure_ascii=False),
                    fact_change_risk, summary,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # ── Tasks ─────────────────────────────────────────────────

    def save_review_categories(
        self,
        review_id: int,
        categories: list[dict],
    ) -> bool:
        """Save issue categories for a review.

        Args:
            review_id: The review id.
            categories: List of categorized issue dicts.

        Returns:
            True if the review was found and updated.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE reviews SET issue_categories=? WHERE id=?",
                (json.dumps(categories, ensure_ascii=False), review_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Workflow run queries (D4 CLI) ────────────────────────────
