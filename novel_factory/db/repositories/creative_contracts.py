"""v6.9.0: Repository for creative contracts, chapter briefs, creative ledgers, editor lens reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..connection import row_to_dict


class CreativeContractsRepositoryMixin:
    """CRUD operations for creative contracts, chapter briefs, creative ledgers, editor lens reports."""

    # ── Project Creative Contracts ──────────────────────────────────

    def get_creative_contract(self, project_id: str, contract_type: str) -> dict | None:
        """Get a creative contract by project_id and type."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM project_creative_contracts WHERE project_id=? AND contract_type=?",
                (project_id, contract_type),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def upsert_creative_contract(
        self,
        project_id: str,
        contract_type: str,
        contract_data: dict,
    ) -> dict:
        """Insert or update a creative contract."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO project_creative_contracts (project_id, contract_type, contract_data, version, created_at, updated_at)
                   VALUES (?, ?, ?, 1, ?, ?)
                   ON CONFLICT(project_id, contract_type) DO UPDATE SET
                   contract_data=excluded.contract_data,
                   version=version+1,
                   updated_at=excluded.updated_at""",
                (project_id, contract_type, json.dumps(contract_data, ensure_ascii=False), now, now),
            )
            conn.commit()
            return self.get_creative_contract(project_id, contract_type)
        finally:
            conn.close()

    def list_creative_contracts(self, project_id: str) -> list[dict]:
        """List all creative contracts for a project."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM project_creative_contracts WHERE project_id=? ORDER BY contract_type",
                (project_id,),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Chapter Briefs ──────────────────────────────────────────────

    def get_chapter_brief(self, project_id: str, chapter_number: int) -> dict | None:
        """Get a chapter brief by project_id and chapter_number."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM chapter_briefs WHERE project_id=? AND chapter_number=?",
                (project_id, chapter_number),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def upsert_chapter_brief(
        self,
        project_id: str,
        chapter_number: int,
        brief_data: dict,
        workflow_run_id: str | None = None,
    ) -> dict:
        """Insert or update a chapter brief."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO chapter_briefs (project_id, chapter_number, brief_data, workflow_run_id, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, chapter_number) DO UPDATE SET
                   brief_data=excluded.brief_data,
                   workflow_run_id=excluded.workflow_run_id""",
                (project_id, chapter_number, json.dumps(brief_data, ensure_ascii=False), workflow_run_id, now),
            )
            conn.commit()
            return self.get_chapter_brief(project_id, chapter_number)
        finally:
            conn.close()

    # ── Creative Ledger Snapshots ───────────────────────────────────

    def get_creative_ledger(
        self,
        project_id: str,
        chapter_number: int,
        ledger_type: str,
        workflow_run_id: str | None = None,
    ) -> dict | None:
        """Get a creative ledger snapshot."""
        conn = self._conn()
        try:
            if workflow_run_id:
                row = conn.execute(
                    "SELECT * FROM creative_ledger_snapshots WHERE project_id=? AND chapter_number=? AND ledger_type=? AND workflow_run_id=?",
                    (project_id, chapter_number, ledger_type, workflow_run_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM creative_ledger_snapshots WHERE project_id=? AND chapter_number=? AND ledger_type=? ORDER BY created_at DESC LIMIT 1",
                    (project_id, chapter_number, ledger_type),
                ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def upsert_creative_ledger(
        self,
        project_id: str,
        chapter_number: int,
        ledger_type: str,
        ledger_data: dict,
        patch_from_previous: dict | None = None,
        workflow_run_id: str | None = None,
    ) -> dict:
        """Insert or update a creative ledger snapshot."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO creative_ledger_snapshots
                   (project_id, chapter_number, ledger_type, ledger_data, patch_from_previous, workflow_run_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, chapter_number, ledger_type, workflow_run_id) DO UPDATE SET
                   ledger_data=excluded.ledger_data,
                   patch_from_previous=excluded.patch_from_previous""",
                (
                    project_id,
                    chapter_number,
                    ledger_type,
                    json.dumps(ledger_data, ensure_ascii=False),
                    json.dumps(patch_from_previous, ensure_ascii=False) if patch_from_previous else None,
                    workflow_run_id,
                    now,
                ),
            )
            conn.commit()
            return self.get_creative_ledger(project_id, chapter_number, ledger_type, workflow_run_id)
        finally:
            conn.close()

    def list_creative_ledgers(
        self,
        project_id: str,
        chapter_number: int | None = None,
    ) -> list[dict]:
        """List creative ledger snapshots for a project."""
        conn = self._conn()
        try:
            if chapter_number is not None:
                rows = conn.execute(
                    "SELECT * FROM creative_ledger_snapshots WHERE project_id=? AND chapter_number=? ORDER BY ledger_type",
                    (project_id, chapter_number),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM creative_ledger_snapshots WHERE project_id=? ORDER BY chapter_number, ledger_type",
                    (project_id,),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_latest_creative_ledger(
        self,
        project_id: str,
        ledger_type: str,
    ) -> dict | None:
        """Get the most recent ledger snapshot for a given ledger type (any chapter).

        Returns the snapshot with the highest chapter_number, breaking ties
        by created_at DESC. Used when current chapter has no snapshot and we
        need to fall back to the most recent prior snapshot.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT * FROM creative_ledger_snapshots
                   WHERE project_id=? AND ledger_type=?
                   ORDER BY chapter_number DESC, created_at DESC
                   LIMIT 1""",
                (project_id, ledger_type),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def get_creative_ledger_history(
        self,
        project_id: str,
        ledger_type: str,
    ) -> list[dict]:
        """Get all snapshots for a given ledger type, ordered by chapter ASC."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM creative_ledger_snapshots
                   WHERE project_id=? AND ledger_type=?
                   ORDER BY chapter_number ASC, created_at ASC""",
                (project_id, ledger_type),
            ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── Chapter Contract Metrics (v6.10.5) ───────────────────────────

    def get_chapter_contract_metrics(
        self,
        project_id: str,
        limit: int = 5,
        before_chapter: int | None = None,
    ) -> list[dict]:
        """Load recent ChapterContractMetrics from ledger snapshots (ledger_type='contract_metrics')."""
        conn = self._conn()
        try:
            if before_chapter is not None:
                rows = conn.execute(
                    """SELECT * FROM creative_ledger_snapshots
                       WHERE project_id=? AND ledger_type='contract_metrics' AND chapter_number < ?
                       ORDER BY chapter_number DESC, created_at DESC
                       LIMIT ?""",
                    (project_id, before_chapter, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM creative_ledger_snapshots
                       WHERE project_id=? AND ledger_type='contract_metrics'
                       ORDER BY chapter_number DESC, created_at DESC
                       LIMIT ?""",
                    (project_id, limit),
                ).fetchall()
            results = []
            for r in rows:
                d = row_to_dict(r)
                if d and isinstance(d.get("ledger_data"), str):
                    import json as _json
                    try:
                        metrics = _json.loads(d["ledger_data"])
                        metrics["chapter_number"] = d.get("chapter_number", 0)
                        results.append(metrics)
                    except (ValueError, TypeError):
                        pass
                elif d and isinstance(d.get("ledger_data"), dict):
                    metrics = d["ledger_data"]
                    metrics["chapter_number"] = d.get("chapter_number", 0)
                    results.append(metrics)
            return results
        finally:
            conn.close()

    # ── Editor Lens Reports ─────────────────────────────────────────

    def upsert_editor_lens_report(
        self,
        project_id: str,
        chapter_number: int,
        lens_type: str,
        report_data: dict,
        workflow_run_id: str | None = None,
    ) -> dict:
        """Insert or update an editor lens report."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO editor_lens_reports
                   (project_id, chapter_number, lens_type, report_data, workflow_run_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, chapter_number, lens_type, workflow_run_id) DO UPDATE SET
                   report_data=excluded.report_data""",
                (
                    project_id,
                    chapter_number,
                    lens_type,
                    json.dumps(report_data, ensure_ascii=False),
                    workflow_run_id,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM editor_lens_reports WHERE project_id=? AND chapter_number=? AND lens_type=? ORDER BY created_at DESC LIMIT 1",
                (project_id, chapter_number, lens_type),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def list_recent_lens_reports(
        self,
        project_id: str,
        lens_type: str,
        before_chapter: int | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """List recent editor lens reports for a project, optionally before a chapter."""
        conn = self._conn()
        try:
            if before_chapter is not None:
                rows = conn.execute(
                    """SELECT * FROM editor_lens_reports
                       WHERE project_id=? AND lens_type=? AND chapter_number < ?
                       ORDER BY chapter_number DESC, created_at DESC
                       LIMIT ?""",
                    (project_id, lens_type, before_chapter, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM editor_lens_reports
                       WHERE project_id=? AND lens_type=?
                       ORDER BY chapter_number DESC, created_at DESC
                       LIMIT ?""",
                    (project_id, lens_type, limit),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

