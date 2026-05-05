"""Project-specific skill overrides repository mixin."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict


class ProjectSkillOverrideRepositoryMixin:
    """Repository methods for per-project skill override documents."""

    def get_project_skill_overrides(self, project_id: str) -> dict[str, Any]:
        """Get the override document for a project.

        Returns a normalized dict with ``skills`` and ``agent_skills`` keys.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM project_skill_overrides WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if not row:
                return {
                    "project_id": project_id,
                    "skills": {},
                    "agent_skills": {},
                    "overrides": {},
                    "created_at": "",
                    "updated_at": "",
                }

            record = row_to_dict(row) or {}
            overrides = json.loads(record.get("overrides_json", "{}"))
            if not isinstance(overrides, dict):
                overrides = {}

            skills = overrides.get("skills", {})
            if not isinstance(skills, dict):
                skills = {}

            agent_skills = overrides.get("agent_skills", {})
            if not isinstance(agent_skills, dict):
                agent_skills = {}

            return {
                "project_id": project_id,
                "skills": skills,
                "agent_skills": agent_skills,
                "overrides": overrides,
                "created_at": record.get("created_at", ""),
                "updated_at": record.get("updated_at", ""),
            }
        finally:
            conn.close()

    def save_project_skill_overrides(
        self,
        project_id: str,
        overrides: dict[str, Any],
    ) -> bool:
        """Save or replace a project's skill override document."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            payload = json.dumps(overrides or {}, ensure_ascii=False)

            existing = conn.execute(
                "SELECT id FROM project_skill_overrides WHERE project_id=?",
                (project_id,),
            ).fetchone()

            if existing:
                cursor = conn.execute(
                    "UPDATE project_skill_overrides "
                    "SET overrides_json=?, updated_at=? "
                    "WHERE project_id=?",
                    (payload, now, project_id),
                )
            else:
                cursor = conn.execute(
                    "INSERT INTO project_skill_overrides "
                    "(project_id, overrides_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (project_id, payload, now, now),
                )

            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
