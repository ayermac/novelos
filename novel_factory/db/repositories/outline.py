"""Outline CRUD operations."""

from __future__ import annotations

from ..connection import row_to_dict


class OutlineRepositoryMixin:
    """Repository mixin for outlines table CRUD operations."""

    def list_outlines(self, project_id: str) -> list[dict]:
        """List all outlines for a project.

        Args:
            project_id: Project identifier.

        Returns:
            List of outline dicts sorted by level and sequence.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM outlines WHERE project_id=? ORDER BY level, sequence",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_outline(self, project_id: str, outline_id: int) -> dict | None:
        """Get a specific outline.

        Args:
            project_id: Project identifier.
            outline_id: Outline ID.

        Returns:
            Outline dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM outlines WHERE project_id=? AND id=?",
                (project_id, outline_id),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_outlines_by_level(self, project_id: str, level: str) -> list[dict]:
        """Get outlines by level.

        Args:
            project_id: Project identifier.
            level: Outline level (e.g., "volume", "arc", "chapter").

        Returns:
            List of outline dicts for the level.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM outlines WHERE project_id=? AND level=? ORDER BY sequence",
                (project_id, level),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def create_outline(
        self,
        project_id: str,
        level: str,
        sequence: int,
        title: str,
        content: str = "",
        chapters_range: str = "",
    ) -> dict:
        """Create a new outline.

        Args:
            project_id: Project identifier.
            level: Outline level (e.g., "volume", "arc", "chapter").
            sequence: Sequence number within level.
            title: Outline title.
            content: Outline content/summary.
            chapters_range: Chapter range (e.g., "1-10").

        Returns:
            Created outline dict with id.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO outlines "
                "(project_id, level, sequence, title, content, chapters_range) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, level, sequence, title, content, chapters_range),
            )
            outline_id = cursor.lastrowid
            conn.commit()
            return {
                "id": outline_id,
                "project_id": project_id,
                "level": level,
                "sequence": sequence,
                "title": title,
                "content": content,
                "chapters_range": chapters_range,
            }
        finally:
            conn.close()

    def update_outline(
        self,
        project_id: str,
        outline_id: int,
        data: dict,
    ) -> dict | None:
        """Update an outline.

        Args:
            project_id: Project identifier.
            outline_id: Outline ID.
            data: Dict with fields to update.

        Returns:
            Updated outline dict or None if not found.
        """
        conn = self._conn()
        try:
            # Build update clause
            fields = []
            values = []
            for key in ("level", "sequence", "title", "content", "chapters_range"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_outline(project_id, outline_id)

            values.extend([project_id, outline_id])
            cursor = conn.execute(
                f"UPDATE outlines SET {', '.join(fields)}, "
                "updated_at=datetime('now','+8 hours') "
                "WHERE project_id=? AND id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_outline(project_id, outline_id)
        finally:
            conn.close()

    def delete_outline(self, project_id: str, outline_id: int) -> bool:
        """Delete an outline.

        Args:
            project_id: Project identifier.
            outline_id: Outline ID.

        Returns:
            True if deleted, False if not found.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM outlines WHERE project_id=? AND id=?",
                (project_id, outline_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_outlines_by_project(self, project_id: str) -> int:
        """Delete all outlines for a project (used in cascade delete).

        Args:
            project_id: Project identifier.

        Returns:
            Number of rows deleted.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM outlines WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
