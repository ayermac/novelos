"""Project CRUD operations."""

from __future__ import annotations

from datetime import datetime, timezone

from ..connection import row_to_dict

class ProjectRepositoryMixin:
    def list_projects(self) -> list[dict]:
        """List all projects, newest first."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY created_at DESC, project_id"
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

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
