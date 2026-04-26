"""v4.2 Style Sample repository mixin.

Provides CRUD for style_samples table.
All write methods check rowcount; failures are never silent.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..connection import row_to_dict


class StyleSampleRepositoryMixin:
    """Repository methods for v4.2 Style Sample Analyzer."""

    def save_style_sample(
        self,
        project_id: str,
        name: str,
        source_type: str,
        content_hash: str,
        content_preview: str = "",
        metrics_json: str = "{}",
        analysis_json: str = "{}",
        status: str = "imported",
    ) -> str:
        """Save a new style sample record.

        Args:
            status: Sample status, defaults to 'imported'. Pass 'analyzed'
                    to save directly in analyzed state (used by sample-import
                    which analyzes on import).

        Returns the sample ID on success.

        Raises:
            ValueError: If a sample with the same content_hash already exists
                        for this project (among non-deleted samples).
            RuntimeError: If the INSERT fails.
        """
        import sqlite3

        conn = self._conn()
        try:
            # Check duplicate content_hash for same project (application-level)
            existing = conn.execute(
                "SELECT id FROM style_samples "
                "WHERE project_id=? AND content_hash=? AND status != 'deleted'",
                (project_id, content_hash),
            ).fetchone()
            if existing:
                raise ValueError(
                    f"A sample with this content hash already exists "
                    f"for project '{project_id}' (id={existing['id']})"
                )

            sample_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            analyzed_at = now if status == "analyzed" else None

            cursor = conn.execute(
                "INSERT INTO style_samples "
                "(id, project_id, name, source_type, content_hash, "
                "content_preview, metrics_json, analysis_json, status, "
                "created_at, analyzed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sample_id,
                    project_id,
                    name,
                    source_type,
                    content_hash,
                    content_preview[:500],  # Hard limit
                    metrics_json,
                    analysis_json,
                    status,
                    now,
                    analyzed_at,
                ),
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise RuntimeError(
                    f"Failed to insert style_sample for project '{project_id}'"
                )
            return sample_id
        except ValueError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as e:
            conn.rollback()
            # DB-level unique constraint violation → consistent ValueError
            raise ValueError(
                f"A sample with this content hash already exists "
                f"for project '{project_id}'"
            ) from e
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_style_sample(self, sample_id: str) -> dict[str, Any] | None:
        """Get a style sample by ID.

        Returns the record dict with metrics and analysis parsed,
        or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM style_samples WHERE id=?",
                (sample_id,),
            ).fetchone()
            if not row:
                return None
            result = row_to_dict(row)
            result["metrics"] = json.loads(result.get("metrics_json", "{}"))
            result["analysis"] = json.loads(result.get("analysis_json", "{}"))
            return result
        finally:
            conn.close()

    def list_style_samples(
        self,
        project_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List style samples for a project, newest first.

        Optionally filter by status.
        Deleted samples are excluded unless status='deleted' is explicitly passed.
        """
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM style_samples "
                    "WHERE project_id=? AND status=? ORDER BY created_at DESC",
                    (project_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM style_samples "
                    "WHERE project_id=? AND status != 'deleted' "
                    "ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            results = []
            for r in rows:
                d = row_to_dict(r)
                d["metrics"] = json.loads(d.get("metrics_json", "{}"))
                d["analysis"] = json.loads(d.get("analysis_json", "{}"))
                results.append(d)
            return results
        finally:
            conn.close()

    def update_style_sample_analysis(
        self,
        sample_id: str,
        metrics_json: str,
        analysis_json: str,
        status: str = "analyzed",
    ) -> bool:
        """Update a sample's analysis results and status.

        Returns True if updated, False if not found.
        """
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.execute(
                "UPDATE style_samples SET metrics_json=?, analysis_json=?, "
                "status=?, analyzed_at=? WHERE id=?",
                (metrics_json, analysis_json, status, now, sample_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_style_sample(self, sample_id: str) -> bool:
        """Soft-delete a style sample (sets status='deleted').

        Returns True if updated, False if not found.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE style_samples SET status='deleted' WHERE id=? "
                "AND status != 'deleted'",
                (sample_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_style_samples_by_ids(
        self,
        project_id: str,
        sample_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Get multiple style samples by IDs, filtered by project.

        Only returns non-deleted samples.
        """
        if not sample_ids:
            return []
        conn = self._conn()
        try:
            placeholders = ",".join("?" for _ in sample_ids)
            rows = conn.execute(
                f"SELECT * FROM style_samples "
                f"WHERE project_id=? AND id IN ({placeholders}) "
                f"AND status != 'deleted' ORDER BY created_at DESC",
                (project_id, *sample_ids),
            ).fetchall()
            results = []
            for r in rows:
                d = row_to_dict(r)
                d["metrics"] = json.loads(d.get("metrics_json", "{}"))
                d["analysis"] = json.loads(d.get("analysis_json", "{}"))
                results.append(d)
            return results
        finally:
            conn.close()
