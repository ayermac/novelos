"""Character CRUD operations."""

from __future__ import annotations

from ..connection import row_to_dict


class CharacterRepositoryMixin:
    """Repository mixin for characters table CRUD operations."""

    def list_characters(self, project_id: str, include_inactive: bool = False) -> list[dict]:
        """List all characters for a project.

        Args:
            project_id: Project identifier.
            include_inactive: If True, include inactive characters.

        Returns:
            List of character dicts.
        """
        conn = self._conn()
        try:
            if include_inactive:
                rows = conn.execute(
                    "SELECT * FROM characters WHERE project_id=? ORDER BY role, name",
                    (project_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM characters WHERE project_id=? AND status='active' ORDER BY role, name",
                    (project_id,),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_character(self, project_id: str, char_id: int) -> dict | None:
        """Get a specific character.

        Args:
            project_id: Project identifier.
            char_id: Character ID.

        Returns:
            Character dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM characters WHERE project_id=? AND id=?",
                (project_id, char_id),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_character(
        self,
        project_id: str,
        name: str,
        role: str = "supporting",
        description: str = "",
        alias: str = "",
        traits: str = "",
        first_appearance: int | None = None,
    ) -> dict:
        """Create a new character.

        Args:
            project_id: Project identifier.
            name: Character name.
            role: Character role (protagonist, antagonist, supporting).
            description: Character description.
            alias: Character alias.
            traits: Character traits (comma-separated).
            first_appearance: First appearance chapter number.

        Returns:
            Created character dict with id.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO characters "
                "(project_id, name, alias, role, description, traits, first_appearance, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
                (project_id, name, alias, role, description, traits, first_appearance),
            )
            char_id = cursor.lastrowid
            conn.commit()
            return {
                "id": char_id,
                "project_id": project_id,
                "name": name,
                "alias": alias,
                "role": role,
                "description": description,
                "traits": traits,
                "first_appearance": first_appearance,
                "status": "active",
            }
        finally:
            conn.close()

    def update_character(
        self,
        project_id: str,
        char_id: int,
        data: dict,
    ) -> dict | None:
        """Update a character.

        Args:
            project_id: Project identifier.
            char_id: Character ID.
            data: Dict with fields to update.

        Returns:
            Updated character dict or None if not found.
        """
        conn = self._conn()
        try:
            # Build update clause
            fields = []
            values = []
            for key in ("name", "alias", "role", "description", "traits", "first_appearance", "status"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_character(project_id, char_id)

            values.extend([project_id, char_id])
            cursor = conn.execute(
                f"UPDATE characters SET {', '.join(fields)} "
                "WHERE project_id=? AND id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_character(project_id, char_id)
        finally:
            conn.close()

    def delete_character(self, project_id: str, char_id: int) -> bool:
        """Delete a character.

        Args:
            project_id: Project identifier.
            char_id: Character ID.

        Returns:
            True if deleted, False if not found.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM characters WHERE project_id=? AND id=?",
                (project_id, char_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_characters_by_project(self, project_id: str) -> int:
        """Delete all characters for a project (used in cascade delete).

        Args:
            project_id: Project identifier.

        Returns:
            Number of rows deleted.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM characters WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
