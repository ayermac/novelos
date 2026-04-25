"""Agent artifact storage and queries."""

from __future__ import annotations

import json
import uuid

from ..connection import row_to_dict
from ...utils.hash import stable_json_hash

class ArtifactRepositoryMixin:
    def save_artifact(
        self,
        project_id: str,
        chapter_number: int,
        agent_id: str,
        artifact_type: str,
        content_json: dict | None = None,
    ) -> str:
        """Save an agent artifact with content hash and idempotency.

        If an artifact with the same project_id + chapter_number + agent_id +
        artifact_type + content_hash already exists, returns the existing id
        without inserting a duplicate.

        Returns:
            Artifact id (UUID string).
        """
        conn = self._conn()
        try:
            content_str = json.dumps(content_json, ensure_ascii=False) if content_json else None
            content_hash = stable_json_hash(content_json) if content_json else ""

            # Check for existing artifact with same idempotency key
            existing = conn.execute(
                "SELECT id FROM agent_artifacts "
                "WHERE project_id=? AND chapter_number=? AND agent_id=? "
                "AND artifact_type=? AND content_hash=?",
                (project_id, chapter_number, agent_id, artifact_type, content_hash),
            ).fetchone()
            if existing:
                return existing["id"]

            artifact_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO agent_artifacts "
                "(id, project_id, chapter_number, agent_id, artifact_type, "
                "content_json, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, project_id, chapter_number, agent_id, artifact_type,
                 content_str, content_hash),
            )
            conn.commit()
            return artifact_id
        finally:
            conn.close()

    # ── Workflow runs ─────────────────────────────────────────

    def get_artifacts_for_chapter(
        self,
        project_id: str,
        chapter_number: int,
    ) -> list[dict]:
        """Get all artifacts for a chapter."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, agent_id, artifact_type, created_at "
                "FROM agent_artifacts "
                "WHERE project_id=? AND chapter_number=? "
                "ORDER BY created_at DESC",
                (project_id, chapter_number),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Recent chapter summaries (Q1 context) ──────────────────
