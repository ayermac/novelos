"""v6.9.0: Editor Lens Scheduler — fast-path skip logic.

Implements should_skip_lens() to skip LLM-heavy lens evaluations
when a lens has been consistently passing for recent chapters.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Number of consecutive passing chapters before a lens can be skipped
SKIP_THRESHOLD = 3


def should_skip_lens(
    lens_type: str,
    project_id: str,
    chapter_number: int,
    repo: Any,
) -> bool:
    """Check if a lens can be skipped based on recent history.

    A lens can be skipped if it has passed for the last SKIP_THRESHOLD chapters
    without any blocking findings.

    Args:
        lens_type: The lens type to check.
        project_id: Project identifier.
        chapter_number: Current chapter number.
        repo: Repository instance for DB access.

    Returns:
        True if the lens can be safely skipped.
    """
    if chapter_number <= SKIP_THRESHOLD:
        return False  # Not enough history to skip

    try:
        conn = repo._conn()
        try:
            # Check recent lens reports
            rows = conn.execute(
                """SELECT report_data FROM editor_lens_reports
                   WHERE project_id = ? AND lens_type = ?
                   AND chapter_number > ?
                   ORDER BY chapter_number DESC LIMIT ?""",
                (project_id, lens_type, chapter_number - SKIP_THRESHOLD - 1, SKIP_THRESHOLD),
            ).fetchall()

            if len(rows) < SKIP_THRESHOLD:
                return False  # Not enough reports

            # All recent reports must be passing with no blocking findings
            import json
            for row in rows:
                report = json.loads(row["report_data"]) if row["report_data"] else {}
                if not report.get("passed", False):
                    return False
                findings = report.get("findings", [])
                if any(f.get("severity") == "blocking" for f in findings):
                    return False

            return True
        finally:
            conn.close()
    except Exception:
        logger.debug("should_skip_lens failed for %s/%s lens=%s", project_id, chapter_number, lens_type)
        return False


def persist_lens_report(
    project_id: str,
    chapter_number: int,
    lens_type: str,
    report: Any,
    repo: Any,
    workflow_run_id: str | None = None,
) -> None:
    """Persist a lens report to the database for future skip decisions.

    Args:
        project_id: Project identifier.
        chapter_number: Chapter number.
        lens_type: Lens type string.
        report: EditorLensReport instance.
        repo: Repository instance.
        workflow_run_id: Optional workflow run ID.
    """
    try:
        import json
        report_data = report.model_dump() if hasattr(report, "model_dump") else {
            "passed": report.passed,
            "score": report.score,
            "findings": [f.model_dump() if hasattr(f, "model_dump") else f for f in report.findings],
            "summary": report.summary,
        }
        conn = repo._conn()
        try:
            conn.execute(
                """INSERT INTO editor_lens_reports
                   (project_id, chapter_number, lens_type, report_data, workflow_run_id, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(project_id, chapter_number, lens_type, workflow_run_id)
                   DO UPDATE SET report_data=excluded.report_data""",
                (
                    project_id,
                    chapter_number,
                    lens_type,
                    json.dumps(report_data, ensure_ascii=False),
                    workflow_run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.warning(
            "Failed to persist lens report %s/%s/%s",
            project_id, chapter_number, lens_type,
            exc_info=True,
        )
