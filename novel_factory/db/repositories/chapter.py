"""Chapter CRUD, status, content, versions, scene beats, state card, instructions, plot holes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..connection import row_to_dict
from ...validators.chapter_checker import count_words
from ...utils.hash import stable_json_hash

class ChapterRepositoryMixin:
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
