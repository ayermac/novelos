"""Faction CRUD operations."""

from __future__ import annotations

from ..connection import row_to_dict


class FactionRepositoryMixin:
    """Repository mixin for factions table CRUD operations."""

    def list_factions(self, project_id: str) -> list[dict]:
        """List all factions for a project.

        Args:
            project_id: Project identifier.

        Returns:
            List of faction dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM factions WHERE project_id=? ORDER BY name",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_faction(self, project_id: str, faction_id: int) -> dict | None:
        """Get a specific faction.

        Args:
            project_id: Project identifier.
            faction_id: Faction ID.

        Returns:
            Faction dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM factions WHERE project_id=? AND id=?",
                (project_id, faction_id),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_faction(
        self,
        project_id: str,
        name: str,
        type: str = "",
        description: str = "",
        relationship_with_protagonist: str = "",
    ) -> dict:
        """Create a new faction.

        Args:
            project_id: Project identifier.
            name: Faction name.
            type: Faction type.
            description: Faction description.
            relationship_with_protagonist: Relationship with protagonist.

        Returns:
            Created faction dict with id.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO factions "
                "(project_id, name, type, description, relationship_with_protagonist) "
                "VALUES (?, ?, ?, ?, ?)",
                (project_id, name, type, description, relationship_with_protagonist),
            )
            faction_id = cursor.lastrowid
            conn.commit()
            return {
                "id": faction_id,
                "project_id": project_id,
                "name": name,
                "type": type,
                "description": description,
                "relationship_with_protagonist": relationship_with_protagonist,
            }
        finally:
            conn.close()

    def update_faction(
        self,
        project_id: str,
        faction_id: int,
        data: dict,
    ) -> dict | None:
        """Update a faction.

        Args:
            project_id: Project identifier.
            faction_id: Faction ID.
            data: Dict with fields to update.

        Returns:
            Updated faction dict or None if not found.
        """
        conn = self._conn()
        try:
            fields = []
            values = []
            for key in ("name", "type", "description", "relationship_with_protagonist"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_faction(project_id, faction_id)

            values.extend([project_id, faction_id])
            cursor = conn.execute(
                f"UPDATE factions SET {', '.join(fields)} "
                "WHERE project_id=? AND id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_faction(project_id, faction_id)
        finally:
            conn.close()

    def delete_faction(self, project_id: str, faction_id: int) -> bool:
        """Delete a faction.

        Args:
            project_id: Project identifier.
            faction_id: Faction ID.

        Returns:
            True if deleted, False if not found.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM factions WHERE project_id=? AND id=?",
                (project_id, faction_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_factions_by_project(self, project_id: str) -> int:
        """Delete all factions for a project (used in cascade delete).

        Args:
            project_id: Project identifier.

        Returns:
            Number of rows deleted.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM factions WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
