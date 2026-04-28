"""World Setting CRUD operations."""

from __future__ import annotations

from ..connection import row_to_dict


class WorldSettingRepositoryMixin:
    """Repository mixin for world_settings table CRUD operations."""

    def list_world_settings(self, project_id: str) -> list[dict]:
        """List all world settings for a project.

        Args:
            project_id: Project identifier.

        Returns:
            List of world setting dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM world_settings WHERE project_id=? ORDER BY category, id",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_world_setting(self, project_id: str, ws_id: int) -> dict | None:
        """Get a specific world setting.

        Args:
            project_id: Project identifier.
            ws_id: World setting ID.

        Returns:
            World setting dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM world_settings WHERE project_id=? AND id=?",
                (project_id, ws_id),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_world_setting(
        self,
        project_id: str,
        category: str,
        title: str,
        content: str = "",
    ) -> dict:
        """Create a new world setting.

        Args:
            project_id: Project identifier.
            category: Setting category (e.g., "力量体系", "地理设定").
            title: Setting title.
            content: Setting content.

        Returns:
            Created world setting dict with id.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO world_settings (project_id, category, title, content) "
                "VALUES (?, ?, ?, ?)",
                (project_id, category, title, content),
            )
            ws_id = cursor.lastrowid
            conn.commit()
            return {
                "id": ws_id,
                "project_id": project_id,
                "category": category,
                "title": title,
                "content": content,
            }
        finally:
            conn.close()

    def update_world_setting(
        self,
        project_id: str,
        ws_id: int,
        data: dict,
    ) -> dict | None:
        """Update a world setting.

        Args:
            project_id: Project identifier.
            ws_id: World setting ID.
            data: Dict with fields to update (category, title, content).

        Returns:
            Updated world setting dict or None if not found.
        """
        conn = self._conn()
        try:
            # Build update clause
            fields = []
            values = []
            for key in ("category", "title", "content"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_world_setting(project_id, ws_id)

            values.extend([project_id, ws_id])
            cursor = conn.execute(
                f"UPDATE world_settings SET {', '.join(fields)} "
                "WHERE project_id=? AND id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_world_setting(project_id, ws_id)
        finally:
            conn.close()

    def delete_world_setting(self, project_id: str, ws_id: int) -> bool:
        """Delete a world setting.

        Args:
            project_id: Project identifier.
            ws_id: World setting ID.

        Returns:
            True if deleted, False if not found.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM world_settings WHERE project_id=? AND id=?",
                (project_id, ws_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_world_settings_by_project(self, project_id: str) -> int:
        """Delete all world settings for a project (used in cascade delete).

        Args:
            project_id: Project identifier.

        Returns:
            Number of rows deleted.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM world_settings WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
