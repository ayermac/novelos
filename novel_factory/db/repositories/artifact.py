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
        workflow_run_id: str | None = None,
    ) -> str:
        """Save an agent artifact with content hash and idempotency.

        If an artifact with the same project_id + chapter_number + agent_id +
        artifact_type + content_hash + workflow_run_id already exists,
        returns the existing id without inserting a duplicate.

        Args:
            workflow_run_id: Optional workflow run id for run-level isolation.

        Returns:
            Artifact id (UUID string).
        """
        conn = self._conn()
        try:
            content_str = json.dumps(content_json, ensure_ascii=False) if content_json else None
            content_hash = stable_json_hash(content_json) if content_json else ""

            # Check for existing artifact with same idempotency key (including run_id)
            if workflow_run_id:
                existing = conn.execute(
                    "SELECT id FROM agent_artifacts "
                    "WHERE project_id=? AND chapter_number=? AND agent_id=? "
                    "AND artifact_type=? AND content_hash=? AND workflow_run_id=?",
                    (project_id, chapter_number, agent_id, artifact_type, content_hash, workflow_run_id),
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM agent_artifacts "
                    "WHERE project_id=? AND chapter_number=? AND agent_id=? "
                    "AND artifact_type=? AND content_hash=? AND workflow_run_id IS NULL",
                    (project_id, chapter_number, agent_id, artifact_type, content_hash),
                ).fetchone()
            if existing:
                return existing["id"]

            artifact_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO agent_artifacts "
                "(id, project_id, chapter_number, agent_id, artifact_type, "
                "content_json, content_hash, workflow_run_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, project_id, chapter_number, agent_id, artifact_type,
                 content_str, content_hash, workflow_run_id),
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
        workflow_run_id: str | None = None,
    ) -> list[dict]:
        """Get artifacts for a chapter.

        Args:
            workflow_run_id: If provided, filter to this run only.
                             If None, returns all artifacts for the chapter (legacy behavior).
        """
        conn = self._conn()
        try:
            if workflow_run_id:
                rows = conn.execute(
                    "SELECT id, agent_id, artifact_type, created_at, workflow_run_id "
                    "FROM agent_artifacts "
                    "WHERE project_id=? AND chapter_number=? AND workflow_run_id=? "
                    "ORDER BY created_at DESC",
                    (project_id, chapter_number, workflow_run_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, agent_id, artifact_type, created_at, workflow_run_id "
                    "FROM agent_artifacts "
                    "WHERE project_id=? AND chapter_number=? "
                    "ORDER BY created_at DESC",
                    (project_id, chapter_number),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_artifacts_for_run(
        self,
        workflow_run_id: str,
    ) -> list[dict]:
        """Get all artifacts belonging to a specific workflow run.

        Args:
            workflow_run_id: Workflow run identifier.

        Returns:
            List of artifact metadata dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, project_id, chapter_number, agent_id, artifact_type, "
                "created_at, workflow_run_id "
                "FROM agent_artifacts "
                "WHERE workflow_run_id=? "
                "ORDER BY created_at DESC",
                (workflow_run_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_artifacts(
        self, project_id: str, limit: int = 50
    ) -> list[dict]:
        """List all artifacts for a project.

        Args:
            project_id: Project identifier.
            limit: Maximum number of artifacts to return.

        Returns:
            List of artifact metadata dicts.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, chapter_number, agent_id, artifact_type, created_at "
                "FROM agent_artifacts "
                "WHERE project_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Recent chapter summaries (Q1 context) ──────────────────
