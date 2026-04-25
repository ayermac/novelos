"""Repository pattern for database access in Novel Factory.

All SQL is encapsulated here. Agents must NOT write raw SQL.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from .connection import get_connection, row_to_dict
from ..validators.chapter_checker import count_words
from ..utils.hash import stable_json_hash


class Repository:
    """Lightweight repository wrapping SQLite access for chapter production."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    # ── Chapter status ────────────────────────────────────────

    def get_project(self, project_id: str) -> dict | None:
        """Get project information."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id=?",
                (project_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_chapter_status(self, project_id: str, chapter_number: int) -> str | None:
        """Get the current status of a chapter."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT status FROM chapters WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            return row["status"] if row else None
        finally:
            conn.close()

    def update_chapter_status(
        self,
        project_id: str,
        chapter_number: int,
        status: str,
        expected_status: str | None = None,
    ) -> bool:
        """Update chapter status with optional optimistic lock.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            status: New status to set.
            expected_status: If provided, update only when current status matches.

        Returns:
            True if row was updated, False if no row matched (or status mismatch).
        """
        conn = self._conn()
        try:
            if expected_status is not None:
                cursor = conn.execute(
                    "UPDATE chapters SET status=?, updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=? AND status=?",
                    (status, project_id, chapter_number, expected_status),
                )
            else:
                cursor = conn.execute(
                    "UPDATE chapters SET status=?, updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=?",
                    (status, project_id, chapter_number),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_chapter(self, project_id: str, chapter_number: int) -> dict | None:
        """Get full chapter record."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM chapters WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_chapters(self, project_id: str) -> list[dict]:
        """Get all chapters for a project."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM chapters WHERE project_id=? ORDER BY chapter_number",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def save_chapter(
        self,
        project_id: str,
        chapter_number: int,
        title: str,
        content: str,
        word_count: int,
        status: str,
    ) -> int:
        """Save a chapter with content."""
        conn = self._conn()
        try:
            # Check if chapter exists
            existing = conn.execute(
                "SELECT id FROM chapters WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            
            if existing:
                cursor = conn.execute(
                    "UPDATE chapters SET title=?, content=?, word_count=?, status=?, "
                    "updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=?",
                    (title, content, word_count, status, project_id, chapter_number),
                )
                conn.commit()
                return existing["id"]
            else:
                cursor = conn.execute(
                    "INSERT INTO chapters "
                    "(project_id, chapter_number, title, content, word_count, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (project_id, chapter_number, title, content, word_count, status),
                )
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    def save_chapter_content(
        self,
        project_id: str,
        chapter_number: int,
        content: str,
        title: str | None = None,
    ) -> bool:
        """Save chapter content and update word count.

        Returns:
            True if the chapter was found and updated, False otherwise.
        """
        conn = self._conn()
        try:
            word_count = count_words(content)
            if title:
                cursor = conn.execute(
                    "UPDATE chapters SET content=?, word_count=?, title=?, "
                    "draft_saved_at=datetime('now','+8 hours'), "
                    "updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=?",
                    (content, word_count, title, project_id, chapter_number),
                )
            else:
                cursor = conn.execute(
                    "UPDATE chapters SET content=?, word_count=?, "
                    "draft_saved_at=datetime('now','+8 hours'), "
                    "updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=?",
                    (content, word_count, project_id, chapter_number),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def add_chapter(
        self,
        project_id: str,
        chapter_number: int,
        title: str,
        status: str = "planned",
    ) -> int:
        """Add a new chapter record. Returns the chapter id."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status) "
                "VALUES (?, ?, ?, ?)",
                (project_id, chapter_number, title, status),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # ── Instructions ──────────────────────────────────────────

    def get_instruction(self, project_id: str, chapter_number: int) -> dict | None:
        """Get writing instruction for a chapter."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM instructions WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_instruction(
        self,
        project_id: str,
        chapter_number: int,
        objective: str,
        key_events: str | None = None,
        plots_to_plant: str = "[]",
        plots_to_resolve: str = "[]",
        emotion_tone: str | None = None,
        ending_hook: str | None = None,
        word_target: int = 2500,
    ) -> int:
        """Create a writing instruction. Returns instruction id."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT OR REPLACE INTO instructions "
                "(project_id, chapter_number, objective, key_events, "
                "plots_to_plant, plots_to_resolve, emotion_tone, "
                "ending_hook, word_target, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
                (
                    project_id, chapter_number, objective, key_events,
                    plots_to_plant, plots_to_resolve, emotion_tone,
                    ending_hook, word_target,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # ── Scene beats ───────────────────────────────────────────

    def save_scene_beats(
        self,
        project_id: str,
        chapter_number: int,
        beats: list[dict],
    ) -> int:
        """Save scene beats for a chapter. Clears existing beats first."""
        conn = self._conn()
        try:
            conn.execute(
                "DELETE FROM scene_beats WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            )
            for beat in beats:
                conn.execute(
                    "INSERT INTO scene_beats "
                    "(project_id, chapter_number, sequence, scene_goal, "
                    "location, characters, conflict, turn, revealed_info, "
                    "plot_refs, hook) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        project_id, chapter_number,
                        beat.get("sequence", 0),
                        beat.get("scene_goal", ""),
                        beat.get("location"),
                        json.dumps(beat.get("characters", []), ensure_ascii=False),
                        beat.get("conflict"),
                        beat.get("turn"),
                        beat.get("revealed_info"),
                        json.dumps(beat.get("plot_refs", []), ensure_ascii=False),
                        beat.get("hook"),
                    ),
                )
            conn.commit()
            return len(beats)
        finally:
            conn.close()

    def get_scene_beats(self, project_id: str, chapter_number: int) -> list[dict]:
        """Get scene beats for a chapter."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM scene_beats WHERE project_id=? AND chapter_number=? "
                "ORDER BY sequence",
                (project_id, chapter_number),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Reviews ───────────────────────────────────────────────

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

    def get_chapter_state(self, project_id: str, chapter_number: int) -> dict | None:
        """Get the state card for a chapter."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM chapter_state WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            if row:
                d = row_to_dict(row)
                if d.get("state_data"):
                    d["state_data"] = json.loads(d["state_data"])
                return d
            return None
        finally:
            conn.close()

    def save_chapter_state(
        self,
        project_id: str,
        chapter_number: int,
        state_data: dict,
        summary: str | None = None,
    ) -> bool:
        """Save or update the state card for a chapter.

        Returns:
            True if the operation succeeded.
        """
        conn = self._conn()
        try:
            state_json = json.dumps(state_data, ensure_ascii=False)
            existing = conn.execute(
                "SELECT id FROM chapter_state WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            if existing:
                cursor = conn.execute(
                    "UPDATE chapter_state SET state_data=?, summary=? "
                    "WHERE project_id=? AND chapter_number=?",
                    (state_json, summary, project_id, chapter_number),
                )
            else:
                cursor = conn.execute(
                    "INSERT INTO chapter_state (project_id, chapter_number, state_data, summary) "
                    "VALUES (?, ?, ?, ?)",
                    (project_id, chapter_number, state_json, summary),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Chapter versions ──────────────────────────────────────

    def save_version(
        self,
        project_id: str,
        chapter: int,
        content: str,
        created_by: str = "author",
        notes: str | None = None,
    ) -> int:
        """Save a chapter version with content hash for idempotency.

        If a version with the same project_id + chapter + created_by +
        content_hash already exists, returns the existing version id
        without inserting a duplicate.

        Returns:
            Version id (integer).
        """
        conn = self._conn()
        try:
            content_hash = stable_json_hash({"content": content})

            # Check for existing version with same hash
            existing = conn.execute(
                "SELECT id FROM chapter_versions "
                "WHERE project_id=? AND chapter=? AND created_by=? AND content_hash=?",
                (project_id, chapter, created_by, content_hash),
            ).fetchone()
            if existing:
                return existing["id"]

            max_ver = conn.execute(
                "SELECT MAX(version) as v FROM chapter_versions "
                "WHERE project_id=? AND chapter=?",
                (project_id, chapter),
            ).fetchone()["v"] or 0
            cursor = conn.execute(
                "INSERT INTO chapter_versions "
                "(project_id, chapter, version, content, word_count, created_by, notes, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, chapter, max_ver + 1, content, count_words(content),
                 created_by, notes, content_hash),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # ── Polish reports ────────────────────────────────────────

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

    def start_task(
        self,
        project_id: str,
        chapter_number: int,
        task_type: str,
        agent_id: str,
    ) -> int:
        """Start a new task. Returns task id."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO task_status "
                "(project_id, chapter_number, task_type, agent_id, status, started_at) "
                "VALUES (?, ?, ?, ?, 'running', datetime('now','+8 hours'))",
                (project_id, chapter_number, task_type, agent_id),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def complete_task(
        self,
        task_id: int,
        success: bool = True,
        error: str | None = None,
    ) -> bool:
        """Complete a task.

        Returns:
            True if the task was found and updated, False otherwise.
        """
        conn = self._conn()
        try:
            status = "completed" if success else "failed"
            cursor = conn.execute(
                "UPDATE task_status SET status=?, completed_at=datetime('now','+8 hours'), "
                "error_message=? WHERE id=?",
                (status, error, task_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def increment_retry(self, task_id: int) -> int:
        """Increment retry count for a task. Returns new retry count."""
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE task_status SET retry_count=retry_count+1 WHERE id=?",
                (task_id,),
            )
            row = conn.execute(
                "SELECT retry_count FROM task_status WHERE id=?", (task_id,)
            ).fetchone()
            conn.commit()
            return row["retry_count"] if row else 0
        finally:
            conn.close()

    def get_chapter_retry_count(self, project_id: str, chapter_number: int) -> int:
        """Get the number of revision tasks for a chapter (circuit breaker)."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM task_status "
                "WHERE project_id=? AND chapter_number=? AND task_type='revise'",
                (project_id, chapter_number),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def mark_timed_out_tasks(self, project_id: str, timeout_minutes: int) -> int:
        """Mark running tasks that have exceeded the timeout threshold.

        Sets status to 'timeout' for tasks that are still 'running' and
        whose started_at is older than timeout_minutes ago.

        Does not auto-retry or auto-wake any Agent.

        Args:
            project_id: Project identifier.
            timeout_minutes: Number of minutes after which a running task
                             is considered timed out.

        Returns:
            Number of tasks marked as timed out.
        """
        from ..utils.time import timeout_threshold

        cutoff = timeout_threshold(timeout_minutes)
        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE task_status SET status='timeout', "
                "completed_at=datetime('now','+8 hours'), "
                "error_message='Task timed out' "
                "WHERE project_id=? AND status='running' AND started_at < ?",
                (project_id, cutoff),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # ── Agent messages ────────────────────────────────────────

    def send_message(
        self,
        project_id: str,
        from_agent: str,
        to_agent: str,
        msg_type: str,
        content: dict,
        priority: str = "normal",
        chapter_number: int | None = None,
    ) -> int:
        """Send an async message between agents."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO agent_messages "
                "(project_id, from_agent, to_agent, type, priority, content, chapter_number) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id, from_agent, to_agent, msg_type, priority,
                    json.dumps(content, ensure_ascii=False), chapter_number,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_pending_messages(
        self, project_id: str, to_agent: str | None = None
    ) -> list[dict]:
        """Get pending messages for an agent."""
        conn = self._conn()
        try:
            query = "SELECT * FROM agent_messages WHERE project_id=? AND status='pending'"
            params: list[Any] = [project_id]
            if to_agent:
                query += " AND to_agent=?"
                params.append(to_agent)
            query += " ORDER BY priority DESC, created_at ASC"
            rows = conn.execute(query, params).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Artifacts ─────────────────────────────────────────────

    def save_artifact(
        self,
        project_id: str,
        chapter_number: int,
        agent_id: str,
        artifact_type: str,
        content_json: dict | None = None,
    ) -> str:
        """Save an agent artifact with content hash and idempotency.

        If an artifact with the same project_id + chapter_number + agent_id +
        artifact_type + content_hash already exists, returns the existing id
        without inserting a duplicate.

        Returns:
            Artifact id (UUID string).
        """
        conn = self._conn()
        try:
            content_str = json.dumps(content_json, ensure_ascii=False) if content_json else None
            content_hash = stable_json_hash(content_json) if content_json else ""

            # Check for existing artifact with same idempotency key
            existing = conn.execute(
                "SELECT id FROM agent_artifacts "
                "WHERE project_id=? AND chapter_number=? AND agent_id=? "
                "AND artifact_type=? AND content_hash=?",
                (project_id, chapter_number, agent_id, artifact_type, content_hash),
            ).fetchone()
            if existing:
                return existing["id"]

            artifact_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO agent_artifacts "
                "(id, project_id, chapter_number, agent_id, artifact_type, "
                "content_json, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, project_id, chapter_number, agent_id, artifact_type,
                 content_str, content_hash),
            )
            conn.commit()
            return artifact_id
        finally:
            conn.close()

    # ── Workflow runs ─────────────────────────────────────────

    def create_workflow_run(
        self,
        project_id: str,
        chapter_number: int,
        graph_name: str = "chapter_production",
    ) -> str:
        """Create a workflow run record. Returns run id."""
        conn = self._conn()
        try:
            run_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO workflow_runs (id, project_id, chapter_number, graph_name) "
                "VALUES (?, ?, ?, ?)",
                (run_id, project_id, chapter_number, graph_name),
            )
            conn.commit()
            return run_id
        finally:
            conn.close()

    def update_workflow_run(
        self,
        run_id: str,
        status: str | None = None,
        current_node: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update workflow run status.

        Returns:
            True if the run was found and updated, False otherwise.
        """
        conn = self._conn()
        try:
            parts: list[str] = []
            params: list[Any] = []
            if status:
                parts.append("status=?")
                params.append(status)
            if current_node:
                parts.append("current_node=?")
                params.append(current_node)
            if error_message:
                parts.append("error_message=?")
                params.append(error_message)
            if status in ("completed", "failed", "blocked"):
                parts.append("completed_at=datetime('now','+8 hours')")
            if not parts:
                return False
            params.append(run_id)
            cursor = conn.execute(
                f"UPDATE workflow_runs SET {', '.join(parts)} WHERE id=?", params
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Plots ─────────────────────────────────────────────────

    def get_pending_plots(self, project_id: str) -> list[dict]:
        """Get all unresolved plots for a project."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM plot_holes WHERE project_id=? AND status='planted' "
                "ORDER BY planned_resolve_chapter",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Characters / world ────────────────────────────────────

    def get_characters(self, project_id: str) -> list[dict]:
        """Get all active characters for a project."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM characters WHERE project_id=? AND status='active'",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_world_settings(self, project_id: str) -> list[dict]:
        """Get all world settings for a project."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM world_settings WHERE project_id=? ORDER BY category",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Publish ───────────────────────────────────────────────

    def publish_chapter(
        self,
        project_id: str,
        chapter_number: int,
        expected_status: str | None = "reviewed",
    ) -> bool:
        """Mark a chapter as published.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            expected_status: If provided, only publish when current status matches.
                             Defaults to 'reviewed'.

        Returns:
            True if the chapter was found and updated, False otherwise.
        """
        conn = self._conn()
        try:
            if expected_status is not None:
                cursor = conn.execute(
                    "UPDATE chapters SET status='published', "
                    "published_at=datetime('now','+8 hours'), "
                    "updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=? AND status=?",
                    (project_id, chapter_number, expected_status),
                )
            else:
                cursor = conn.execute(
                    "UPDATE chapters SET status='published', "
                    "published_at=datetime('now','+8 hours'), "
                    "updated_at=datetime('now','+8 hours') "
                    "WHERE project_id=? AND chapter_number=?",
                    (project_id, chapter_number),
                )
            if cursor.rowcount > 0:
                # Also update project current_chapter
                conn.execute(
                    "UPDATE projects SET current_chapter=? WHERE project_id=?",
                    (chapter_number, project_id),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Learned patterns (Q5) ──────────────────────────────────

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

    def get_workflow_runs_for_project(
        self,
        project_id: str,
        chapter_number: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get workflow runs for a project, most recent first.

        Args:
            project_id: Project identifier.
            chapter_number: Optional chapter filter.
            limit: Maximum number of runs to return.
        """
        conn = self._conn()
        try:
            if chapter_number is not None:
                rows = conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=? AND chapter_number=? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (project_id, chapter_number, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_artifacts_for_chapter(
        self,
        project_id: str,
        chapter_number: int,
    ) -> list[dict]:
        """Get all artifacts for a chapter."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, agent_id, artifact_type, created_at "
                "FROM agent_artifacts "
                "WHERE project_id=? AND chapter_number=? "
                "ORDER BY created_at DESC",
                (project_id, chapter_number),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Recent chapter summaries (Q1 context) ──────────────────

    def get_recent_chapter_summaries(
        self,
        project_id: str,
        before_chapter: int,
        limit: int = 3,
    ) -> list[dict]:
        """Get summaries from recent chapters for context.

        Args:
            project_id: Project identifier.
            before_chapter: Get chapters before this number.
            limit: Maximum number of chapters to return.

        Returns:
            List of dicts with chapter_number, title, and state summary.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT c.chapter_number, c.title, cs.summary "
                "FROM chapters c "
                "LEFT JOIN chapter_state cs ON c.project_id = cs.project_id "
                "  AND c.chapter_number = cs.chapter_number "
                "WHERE c.project_id=? AND c.chapter_number < ? "
                "ORDER BY c.chapter_number DESC LIMIT ?",
                (project_id, before_chapter, limit),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── v2 Sidecar Agents ────────────────────────────────────────

    # Scout Agent methods

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
                from ..utils.time import timeout_threshold
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
