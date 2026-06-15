"""Character CRUD operations."""

from __future__ import annotations

from ..connection import row_to_dict


# v6.10.7: Valid character roles for data integrity.
_VALID_CHARACTER_ROLES = {
    "protagonist", "supporting", "antagonist", "neutral",
    "antagonist/neutral", "unclear", "main", "lead",
}


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

    def get_protagonist(self, project_id: str) -> dict | None:
        """Get the protagonist for a project.

        Returns:
            The protagonist character dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM characters WHERE project_id=? AND role='protagonist' AND status='active'",
                (project_id,),
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

        Raises:
            ValueError: If attempting to create a second protagonist or
                        if role/name values are invalid.
        """
        # v6.10.7: Validate role before write
        role = str(role or "").strip().lower()
        if role not in _VALID_CHARACTER_ROLES:
            role = "supporting"

        # v6.10.7: Protagonist uniqueness guard (check all statuses, not just active)
        if role == "protagonist":
            all_chars = self.list_characters(project_id, include_inactive=True)
            existing_protagonists = [c for c in all_chars if c.get("role") == "protagonist"]
            if existing_protagonists:
                first = existing_protagonists[0]
                raise ValueError(
                    f"Project already has protagonist '{first['name']}' (id={first['id']}, status={first.get('status')}). "
                    "Cannot create a second protagonist."
                )

        # v6.10.7: Name sanity check
        name = str(name or "").strip()
        if not name or len(name) > 16:
            raise ValueError(f"Character name must be 1-16 characters, got: {name!r}")

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

        Raises:
            ValueError: If attempting to demote protagonist or corrupt name/role.
        """
        # v6.10.7: Protagonist write-protection — load current record before update
        current = self.get_character(project_id, char_id)
        if not current:
            return None

        is_protagonist = current.get("role") == "protagonist"

        # v6.10.7: Guard name corruption
        if "name" in data:
            new_name = str(data["name"] or "").strip()
            if not new_name or len(new_name) > 16:
                raise ValueError(
                    f"Refusing to corrupt character name: {new_name!r} (must be 1-16 chars)"
                )
            # v6.10.7: Extra guard for protagonist — do not silently rename protagonist
            if is_protagonist and new_name != current.get("name"):
                raise ValueError(
                    f"Refusing to rename protagonist '{current.get('name')}' -> '{new_name}'. "
                    "Use explicit project-level rename if intended."
                )

        # v6.10.7: Guard role corruption
        if "role" in data:
            new_role = str(data["role"] or "").strip().lower()
            if new_role not in _VALID_CHARACTER_ROLES:
                raise ValueError(
                    f"Refusing to set invalid role {new_role!r} for character {char_id}."
                )
            # v6.10.7: Prevent protagonist demotion via memory patches
            if is_protagonist and new_role != "protagonist":
                raise ValueError(
                    f"Refusing to demote protagonist (id={char_id}) to role {new_role!r}."
                )
            # v6.10.7: Prevent promoting another character to protagonist without
            # first handling the existing one (handled by caller or explicit path)
            if not is_protagonist and new_role == "protagonist":
                existing_protagonist = self.get_protagonist(project_id)
                if existing_protagonist and existing_protagonist["id"] != char_id:
                    raise ValueError(
                        f"Cannot promote character {char_id} to protagonist: "
                        f"project already has protagonist '{existing_protagonist['name']}' (id={existing_protagonist['id']})."
                    )

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

        Raises:
            ValueError: If attempting to delete the protagonist.
        """
        # v6.10.7: Protagonist deletion guard
        char = self.get_character(project_id, char_id)
        if char and char.get("role") == "protagonist":
            raise ValueError(
                f"Cannot delete protagonist '{char['name']}' (id={char_id}). "
                "Delete or reassign role first."
            )

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
