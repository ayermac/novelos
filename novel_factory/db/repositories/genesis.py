"""Genesis runs CRUD operations."""

from __future__ import annotations

import uuid

from ..connection import row_to_dict


class GenesisRepositoryMixin:
    """Repository mixin for genesis_runs table CRUD operations."""

    def list_genesis_runs(self, project_id: str) -> list[dict]:
        """List all genesis runs for a project."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM genesis_runs WHERE project_id=? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_genesis_run(self, genesis_id: str) -> dict | None:
        """Get a genesis run by ID."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM genesis_runs WHERE id=?",
                (genesis_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_latest_genesis_run(self, project_id: str) -> dict | None:
        """Get the most recent genesis run for a project."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM genesis_runs WHERE project_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_genesis_run(
        self,
        project_id: str,
        input_json: str,
        status: str = "pending",
    ) -> dict:
        """Create a new genesis run."""
        genesis_id = uuid.uuid4().hex
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO genesis_runs (id, project_id, status, input_json) "
                "VALUES (?, ?, ?, ?)",
                (genesis_id, project_id, status, input_json),
            )
            conn.commit()
            return self.get_genesis_run(genesis_id)  # type: ignore[return-value]
        finally:
            conn.close()

    def update_genesis_run(
        self,
        genesis_id: str,
        data: dict,
    ) -> dict | None:
        """Update a genesis run."""
        conn = self._conn()
        try:
            fields = []
            values = []
            for key in ("status", "draft_json", "error_message"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return self.get_genesis_run(genesis_id)

            fields.append("updated_at=datetime('now', '+8 hours')")
            values.append(genesis_id)
            cursor = conn.execute(
                f"UPDATE genesis_runs SET {', '.join(fields)} WHERE id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_genesis_run(genesis_id)
        finally:
            conn.close()

    def delete_genesis_runs_by_project(self, project_id: str) -> int:
        """Delete all genesis runs for a project."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM genesis_runs WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
