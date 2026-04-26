"""v4.1 Style Gate & Evolution repository mixin.

Adds repository methods for style_bible_versions and style_evolution_proposals.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict


class StyleGateRepositoryMixin:
    """Repository methods for v4.1 Style Gate & Evolution."""

    # ── Style Bible Versions ────────────────────────────────

    def save_style_bible_version(
        self,
        project_id: str,
        style_bible_id: str,
        bible_dict: dict[str, Any],
        change_summary: str = "",
        created_by: str = "system",
    ) -> str:
        """Save a Style Bible version snapshot.

        Returns the version ID.
        """
        conn = self._conn()
        try:
            version_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            version = bible_dict.get("version", "1.0.0")

            cursor = conn.execute(
                "INSERT INTO style_bible_versions "
                "(id, project_id, style_bible_id, version, bible_json, "
                "change_summary, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    project_id,
                    style_bible_id,
                    version,
                    json.dumps(bible_dict, ensure_ascii=False),
                    change_summary,
                    created_by,
                    now,
                ),
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise RuntimeError(
                    f"Failed to insert style_bible_version for project '{project_id}'"
                )
            return version_id
        finally:
            conn.close()

    def get_style_bible_versions(self, project_id: str) -> list[dict[str, Any]]:
        """List all Style Bible versions for a project, newest first."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, project_id, style_bible_id, version, "
                "change_summary, created_by, created_at "
                "FROM style_bible_versions "
                "WHERE project_id=? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_style_bible_version(self, version_id: str) -> dict[str, Any] | None:
        """Get a specific Style Bible version by ID."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM style_bible_versions WHERE id=?",
                (version_id,),
            ).fetchone()
            if not row:
                return None
            result = row_to_dict(row)
            result["bible"] = json.loads(result.get("bible_json", "{}"))
            return result
        finally:
            conn.close()

    # ── Style Evolution Proposals ───────────────────────────

    def create_style_evolution_proposal(
        self,
        project_id: str,
        proposal_type: str,
        proposal_json: dict[str, Any],
        rationale: str = "",
        source: str = "quality_reports",
    ) -> str:
        """Create a new Style Evolution Proposal.

        Returns the proposal ID.
        """
        conn = self._conn()
        try:
            proposal_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            cursor = conn.execute(
                "INSERT INTO style_evolution_proposals "
                "(id, project_id, proposal_type, source, status, "
                "proposal_json, rationale, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
                (
                    proposal_id,
                    project_id,
                    proposal_type,
                    source,
                    json.dumps(proposal_json, ensure_ascii=False),
                    rationale,
                    now,
                ),
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise RuntimeError(
                    f"Failed to insert style_evolution_proposal for project '{project_id}'"
                )
            return proposal_id
        finally:
            conn.close()

    def list_style_evolution_proposals(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List Style Evolution Proposals for a project."""
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM style_evolution_proposals "
                    "WHERE project_id=? AND status=? ORDER BY created_at DESC",
                    (project_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM style_evolution_proposals "
                    "WHERE project_id=? ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            results = []
            for r in rows:
                d = row_to_dict(r)
                d["proposal"] = json.loads(d.get("proposal_json", "{}"))
                results.append(d)
            return results
        finally:
            conn.close()

    def get_style_evolution_proposal(
        self, proposal_id: str
    ) -> dict[str, Any] | None:
        """Get a specific Style Evolution Proposal by ID."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM style_evolution_proposals WHERE id=?",
                (proposal_id,),
            ).fetchone()
            if not row:
                return None
            result = row_to_dict(row)
            result["proposal"] = json.loads(result.get("proposal_json", "{}"))
            return result
        finally:
            conn.close()

    def decide_style_evolution_proposal(
        self,
        proposal_id: str,
        decision: str,
        notes: str | None = None,
    ) -> bool:
        """Approve or reject a Style Evolution Proposal.

        Args:
            proposal_id: The proposal ID.
            decision: 'approved' or 'rejected'.
            notes: Optional decision notes.

        Returns:
            True if the proposal was updated, False if not found.

        Note:
            v4.1 does NOT auto-apply proposals to Style Bible.
            This only updates the proposal status.
        """
        if decision not in ("approved", "rejected"):
            raise ValueError(f"Invalid decision '{decision}': must be 'approved' or 'rejected'")

        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.execute(
                "UPDATE style_evolution_proposals "
                "SET status=?, decided_at=?, decision_notes=? "
                "WHERE id=? AND status='pending'",
                (decision, now, notes or "", proposal_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Style Gate Config helpers ───────────────────────────

    def get_style_gate_config(self, project_id: str) -> dict[str, Any] | None:
        """Get Style Gate config from the Style Bible's bible_json.

        The gate config is stored inside the style_bibles.bible_json
        under the key 'gate_config'.
        """
        record = self.get_style_bible(project_id)
        if not record:
            return None
        bible = record.get("bible", {})
        return bible.get("gate_config")

    def set_style_gate_config(
        self, project_id: str, gate_config: dict[str, Any]
    ) -> bool:
        """Update the gate_config within the Style Bible's bible_json.

        Returns True if updated, False if no Style Bible found.
        """
        record = self.get_style_bible(project_id)
        if not record:
            return False

        bible = record.get("bible", {})
        bible["gate_config"] = gate_config
        return self.update_style_bible(project_id, bible)
