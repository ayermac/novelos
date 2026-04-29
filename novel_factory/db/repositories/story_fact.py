"""Story facts and events CRUD operations."""

from __future__ import annotations

import uuid

from ..connection import row_to_dict


class StoryFactRepositoryMixin:
    """Repository mixin for story_facts and story_fact_events CRUD operations."""

    # --- Story Facts ---

    def list_story_facts(
        self,
        project_id: str,
        fact_type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """List story facts for a project with optional filters."""
        conn = self._conn()
        try:
            conditions = ["project_id=?"]
            params: list[str | int | float] = [project_id]
            if fact_type:
                conditions.append("fact_type=?")
                params.append(fact_type)
            if status:
                conditions.append("status=?")
                params.append(status)
            where = " AND ".join(conditions)
            rows = conn.execute(
                f"SELECT * FROM story_facts WHERE {where} "
                "ORDER BY updated_at DESC",
                params,
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_story_fact(self, fact_id: str) -> dict | None:
        """Get a story fact by ID."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM story_facts WHERE id=?",
                (fact_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_story_fact_by_key(
        self,
        project_id: str,
        fact_key: str,
    ) -> dict | None:
        """Get a story fact by project and key."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM story_facts WHERE project_id=? AND fact_key=?",
                (project_id, fact_key),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_story_fact(
        self,
        project_id: str,
        fact_key: str,
        fact_type: str,
        value_json: str,
        subject: str | None = None,
        attribute: str | None = None,
        unit: str | None = None,
        scope: str = "global",
        status: str = "active",
        confidence: float = 1.0,
        source_chapter: int | None = None,
        source_agent: str | None = None,
    ) -> dict:
        """Create a new story fact."""
        fact_id = uuid.uuid4().hex
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO story_facts "
                "(id, project_id, fact_key, fact_type, subject, attribute, "
                "value_json, unit, scope, status, confidence, "
                "source_chapter, source_agent, last_changed_chapter) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact_id, project_id, fact_key, fact_type, subject,
                    attribute, value_json, unit, scope, status, confidence,
                    source_chapter, source_agent, source_chapter,
                ),
            )
            conn.commit()
            return self.get_story_fact(fact_id)  # type: ignore[return-value]
        finally:
            conn.close()

    def update_story_fact(
        self,
        fact_id: str,
        data: dict,
    ) -> dict | None:
        """Update a story fact."""
        conn = self._conn()
        try:
            fields = []
            values: list[str | int | float | None] = []
            for key in (
                "value_json", "status", "confidence", "subject",
                "attribute", "unit", "scope", "last_changed_chapter",
            ):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_story_fact(fact_id)

            fields.append("updated_at=datetime('now', '+8 hours')")
            values.append(fact_id)
            cursor = conn.execute(
                f"UPDATE story_facts SET {', '.join(fields)} WHERE id=?",
                values,
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
            return self.get_story_fact(fact_id)
        finally:
            conn.close()

    def upsert_story_fact(
        self,
        project_id: str,
        fact_key: str,
        fact_type: str,
        value_json: str,
        source_chapter: int | None = None,
        source_agent: str | None = None,
        subject: str | None = None,
        attribute: str | None = None,
        unit: str | None = None,
    ) -> dict:
        """Create or update a story fact by key."""
        existing = self.get_story_fact_by_key(project_id, fact_key)
        if existing:
            update_data: dict = {"value_json": value_json}
            if source_chapter is not None:
                update_data["last_changed_chapter"] = source_chapter
            if subject is not None:
                update_data["subject"] = subject
            if attribute is not None:
                update_data["attribute"] = attribute
            if unit is not None:
                update_data["unit"] = unit
            return self.update_story_fact(existing["id"], update_data)  # type: ignore[return-value]
        return self.create_story_fact(
            project_id, fact_key, fact_type, value_json,
            subject=subject, attribute=attribute, unit=unit,
            source_chapter=source_chapter, source_agent=source_agent,
        )

    def delete_story_facts_by_project(self, project_id: str) -> int:
        """Delete all story facts for a project."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM story_facts WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # --- Story Fact Events ---

    def list_fact_events(
        self,
        project_id: str,
        fact_id: str | None = None,
        chapter_number: int | None = None,
    ) -> list[dict]:
        """List story fact events with optional filters."""
        conn = self._conn()
        try:
            conditions = ["project_id=?"]
            params: list[str | int] = [project_id]
            if fact_id:
                conditions.append("fact_id=?")
                params.append(fact_id)
            if chapter_number is not None:
                conditions.append("chapter_number=?")
                params.append(chapter_number)
            where = " AND ".join(conditions)
            rows = conn.execute(
                f"SELECT * FROM story_fact_events WHERE {where} "
                "ORDER BY created_at DESC",
                params,
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_fact_event(self, event_id: str) -> dict | None:
        """Get a story fact event by ID."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM story_fact_events WHERE id=?",
                (event_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_fact_event(
        self,
        project_id: str,
        chapter_number: int,
        agent_id: str,
        event_type: str,
        fact_id: str | None = None,
        run_id: str | None = None,
        before_json: str | None = None,
        after_json: str | None = None,
        rationale: str | None = None,
        evidence_text: str | None = None,
        validation_status: str = "pending",
    ) -> dict:
        """Create a new story fact event."""
        event_id = uuid.uuid4().hex
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO story_fact_events "
                "(id, fact_id, project_id, chapter_number, run_id, agent_id, "
                "event_type, before_json, after_json, rationale, "
                "evidence_text, validation_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id, fact_id, project_id, chapter_number, run_id,
                    agent_id, event_type, before_json, after_json,
                    rationale, evidence_text, validation_status,
                ),
            )
            conn.commit()
            return self.get_fact_event(event_id)  # type: ignore[return-value]
        finally:
            conn.close()

    def delete_fact_events_by_project(self, project_id: str) -> int:
        """Delete all story fact events for a project."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM story_fact_events WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
