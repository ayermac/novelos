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

    def create_project(
        self,
        project_id: str,
        name: str,
        genre: str = "",
        description: str = "",
        total_chapters_planned: int = 500,
        target_words: int = 1500000,
        current_chapter: int = 1,
    ) -> None:
        """Create a new project.

        Args:
            project_id: Unique project identifier.
            name: Project name.
            genre: Genre (optional).
            description: Project description (optional).
            total_chapters_planned: Total chapters planned (default 500).
            target_words: Target word count (default 1,500,000).
            current_chapter: Current chapter number (default 1).

        Raises:
            sqlite3.IntegrityError: If project_id already exists.
        """
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO projects "
                "(project_id, name, genre, description, total_chapters_planned, "
                "target_words, current_chapter, status, is_current, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?)",
                (
                    project_id,
                    name,
                    genre,
                    description,
                    total_chapters_planned,
                    target_words,
                    current_chapter,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        genre: str | None = None,
        target_words: int | None = None,
        total_chapters_planned: int | None = None,
    ) -> dict | None:
        """Update project settings (v5.2 Phase C).

        Args:
            project_id: Project identifier.
            name: New project name (optional).
            description: New description (optional).
            genre: New genre (optional).
            target_words: New target word count (optional).
            total_chapters_planned: New total chapters planned (optional).

        Returns:
            Updated project dict or None if not found.
        """
        conn = self._conn()
        try:
            # Build update clause
            fields = []
            values = []
            if name is not None:
                fields.append("name=?")
                values.append(name)
            if description is not None:
                fields.append("description=?")
                values.append(description)
            if genre is not None:
                fields.append("genre=?")
                values.append(genre)
            if target_words is not None:
                fields.append("target_words=?")
                values.append(target_words)
            if total_chapters_planned is not None:
                fields.append("total_chapters_planned=?")
                values.append(total_chapters_planned)

            if not fields:
                return self.get_project(project_id)

            # Always update updated_at
            fields.append("updated_at=datetime('now','+8 hours')")

            values.append(project_id)
            cursor = conn.execute(
                f"UPDATE projects SET {', '.join(fields)} WHERE project_id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_project(project_id)
        finally:
            conn.close()

    def add_world_setting(
        self,
        project_id: str,
        category: str,
        title: str,
        content: str,
    ) -> int:
        """Add a world setting for a project.

        Args:
            project_id: Project identifier.
            category: Setting category.
            title: Setting title.
            content: Setting content.

        Returns:
            The ID of the inserted setting.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO world_settings (project_id, category, title, content) "
                "VALUES (?, ?, ?, ?)",
                (project_id, category, title, content),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def add_character(
        self,
        project_id: str,
        name: str,
        role: str,
        description: str = "",
        alias: str = "",
        first_appearance: int | None = None,
    ) -> int:
        """Add a character for a project.

        Args:
            project_id: Project identifier.
            name: Character name.
            role: Character role (e.g., 'protagonist', 'antagonist', 'supporting').
            description: Character description (optional).
            alias: Character alias (optional).
            first_appearance: First appearance chapter number (optional).

        Returns:
            The ID of the inserted character.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO characters "
                "(project_id, name, alias, role, description, first_appearance, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active')",
                (project_id, name, alias, role, description, first_appearance),
            )
            conn.commit()
            return cursor.lastrowid
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

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all associated data (cascade delete).

        Args:
            project_id: Project identifier.

        Returns:
            True if project was deleted, False if not found.
        """
        conn = self._conn()
        try:
            # Check if project exists
            existing = conn.execute(
                "SELECT project_id FROM projects WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if not existing:
                return False

            # Delete from all related tables in single connection
            # Only include tables that have project_id column
            tables = [
                "chapters",
                "characters",
                "outlines",
                "world_settings",
                "workflow_runs",
                "instructions",
                "scene_beats",
                "chapter_state",
                "chapter_versions",
                "chapter_plots",
                "chapter_review_notes",
                "plot_holes",
                "agent_artifacts",
                "agent_messages",
                "quality_reports",
                "scout_reports",
                "polish_reports",
                "reviews",
                "reports",
                "batch_revision_runs",
                "batch_continuity_gates",
                "production_runs",
                "production_queue",
                "production_queue_events",
                "serial_plans",
                "serial_plan_events",
                "state_history",
                "human_review_sessions",
                "production_run_items",
                "batch_revision_items",
            ]
            for table in tables:
                try:
                    conn.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
                except Exception:
                    # Table may not exist in this schema
                    pass

            # Finally delete the project
            conn.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
            conn.commit()
            return True
        finally:
            conn.close()
