"""Style Bible repository mixin for v4.0."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict


class StyleBibleRepositoryMixin:
    """Repository methods for Style Bible CRUD."""

    def save_style_bible(
        self,
        project_id: str,
        bible_dict: dict[str, Any],
    ) -> str:
        """Save a new Style Bible for a project.

        Returns the bible ID on success.

        Raises:
            ValueError: If a bible already exists for this project.
        """
        conn = self._conn()
        try:
            # Check existing
            existing = conn.execute(
                "SELECT id FROM style_bibles WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if existing:
                raise ValueError(f"Style Bible already exists for project '{project_id}'. Use update_style_bible instead.")

            bible_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            name = bible_dict.get("name", "Default Style Bible")
            genre = bible_dict.get("genre", "")
            target_platform = bible_dict.get("target_platform", "")
            target_audience = bible_dict.get("target_audience", "")
            version = bible_dict.get("version", "1.0.0")

            cursor = conn.execute(
                "INSERT INTO style_bibles "
                "(id, project_id, name, genre, target_platform, target_audience, "
                "bible_json, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    bible_id,
                    project_id,
                    name,
                    genre,
                    target_platform,
                    target_audience,
                    json.dumps(bible_dict, ensure_ascii=False),
                    version,
                    now,
                    now,
                ),
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise RuntimeError(f"Failed to insert Style Bible for project '{project_id}'")
            return bible_id
        finally:
            conn.close()

    def get_style_bible(self, project_id: str) -> dict[str, Any] | None:
        """Get Style Bible for a project.

        Returns the full record dict, or None if not found.
        The `bible_json` field is parsed into a `bible` dict.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM style_bibles WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if not row:
                return None
            result = row_to_dict(row)
            result["bible"] = json.loads(result.get("bible_json", "{}"))
            return result
        finally:
            conn.close()

    def update_style_bible(
        self,
        project_id: str,
        bible_dict: dict[str, Any],
    ) -> bool:
        """Update an existing Style Bible.

        Returns True if the record was updated, False if no matching project.
        """
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            name = bible_dict.get("name", "Default Style Bible")
            genre = bible_dict.get("genre", "")
            target_platform = bible_dict.get("target_platform", "")
            target_audience = bible_dict.get("target_audience", "")
            version = bible_dict.get("version", "1.0.0")

            cursor = conn.execute(
                "UPDATE style_bibles SET name=?, genre=?, target_platform=?, "
                "target_audience=?, bible_json=?, version=?, updated_at=? "
                "WHERE project_id=?",
                (
                    name,
                    genre,
                    target_platform,
                    target_audience,
                    json.dumps(bible_dict, ensure_ascii=False),
                    version,
                    now,
                    project_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_style_bible(self, project_id: str) -> bool:
        """Delete Style Bible for a project.

        Returns True if a record was deleted, False otherwise.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM style_bibles WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_style_bibles(self) -> list[dict[str, Any]]:
        """List all Style Bibles.

        Returns a list of record dicts (bible_json is NOT parsed for performance).
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, project_id, name, genre, target_platform, "
                "target_audience, version, created_at, updated_at "
                "FROM style_bibles ORDER BY updated_at DESC"
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()
