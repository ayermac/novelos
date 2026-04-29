"""Chapter instruction CRUD operations."""

from __future__ import annotations

from ..connection import row_to_dict


class InstructionRepositoryMixin:
    """Repository mixin for instructions table CRUD operations."""

    def list_instructions(self, project_id: str) -> list[dict]:
        """List all instructions for a project.

        Args:
            project_id: Project identifier.

        Returns:
            List of instruction dicts ordered by chapter number.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM instructions WHERE project_id=? ORDER BY chapter_number",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_instruction_by_id(self, project_id: str, instruction_id: int) -> dict | None:
        """Get a specific instruction by ID.

        Args:
            project_id: Project identifier.
            instruction_id: Instruction ID.

        Returns:
            Instruction dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM instructions WHERE project_id=? AND id=?",
                (project_id, instruction_id),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_instruction_by_chapter(self, project_id: str, chapter_number: int) -> dict | None:
        """Get instruction for a specific chapter.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.

        Returns:
            Instruction dict or None if not found.
        """
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
        objective: str = "",
        key_events: str = "",
        plots_to_resolve: str = "",
        plots_to_plant: str = "",
        emotion_tone: str = "",
        ending_hook: str = "",
        word_target: int | None = None,
        status: str = "pending",
    ) -> int:
        """Create a new instruction.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number this instruction targets.
            objective: Chapter objective.
            key_events: Key events in this chapter.
            plots_to_resolve: Plots to resolve.
            plots_to_plant: Plots to plant.
            emotion_tone: Emotional tone.
            ending_hook: Ending hook.
            word_target: Target word count.
            status: Instruction status.

        Returns:
            Created instruction ID.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT OR REPLACE INTO instructions "
                "(project_id, chapter_number, objective, key_events, plots_to_resolve, "
                "plots_to_plant, emotion_tone, ending_hook, word_target, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, chapter_number, objective, key_events, plots_to_resolve,
                 plots_to_plant, emotion_tone, ending_hook, word_target, status),
            )
            instruction_id = cursor.lastrowid
            conn.commit()
            return instruction_id
        finally:
            conn.close()

    def update_instruction(
        self,
        project_id: str,
        instruction_id: int,
        data: dict,
    ) -> dict | None:
        """Update an instruction.

        Args:
            project_id: Project identifier.
            instruction_id: Instruction ID.
            data: Dict with fields to update.

        Returns:
            Updated instruction dict or None if not found.
        """
        conn = self._conn()
        try:
            fields = []
            values = []
            for key in ("chapter_number", "objective", "key_events", "plots_to_resolve",
                        "plots_to_plant", "emotion_tone", "ending_hook", "word_target", "status"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_instruction_by_id(project_id, instruction_id)

            values.extend([project_id, instruction_id])
            cursor = conn.execute(
                f"UPDATE instructions SET {', '.join(fields)} "
                "WHERE project_id=? AND id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_instruction_by_id(project_id, instruction_id)
        finally:
            conn.close()

    def delete_instruction(self, project_id: str, instruction_id: int) -> bool:
        """Delete an instruction.

        Args:
            project_id: Project identifier.
            instruction_id: Instruction ID.

        Returns:
            True if deleted, False if not found.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM instructions WHERE project_id=? AND id=?",
                (project_id, instruction_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_instructions_by_project(self, project_id: str) -> int:
        """Delete all instructions for a project (used in cascade delete).

        Args:
            project_id: Project identifier.

        Returns:
            Number of rows deleted.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM instructions WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
