"""Secretary Agent — generates reports and exports.

Secretary is a sidecar agent that generates daily reports, chapter exports,
and run summaries without modifying chapter content or status.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from ..db.repository import Repository
from ..models.sidecar import ChapterExport, DailyReport, SecretaryOutput

logger = logging.getLogger(__name__)


class SecretaryAgent:
    """Secretary: generates reports and exports."""

    agent_id = "secretary"

    def __init__(self, repo: Repository, llm=None):
        """Initialize Secretary agent.
        
        Args:
            repo: Repository instance.
            llm: Optional LLM provider (for consistency with other agents).
        """
        self.repo = repo
        self.llm = llm  # Not used, but kept for consistency

    def generate_daily_report(self, project_id: str, date: str | None = None) -> dict[str, Any]:
        """Generate daily workflow report.

        Args:
            project_id: Project identifier.
            date: Optional date string (YYYY-MM-DD). Defaults to today.

        Returns:
            Dict with success, report, error.
        """
        try:
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")

            # Get workflow runs for the date
            conn = self.repo._conn()
            try:
                # Get all runs for project
                all_runs = conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=? ORDER BY started_at DESC",
                    (project_id,),
                ).fetchall()

                # Filter by date (SQLite datetime format: YYYY-MM-DD HH:MM:SS)
                today_runs = [
                    r for r in all_runs
                    if r["started_at"] and r["started_at"].startswith(date)
                ]
            finally:
                conn.close()

            # Calculate statistics
            total_runs = len(today_runs)
            successful_runs = sum(1 for r in today_runs if r["status"] == "completed")
            failed_runs = sum(1 for r in today_runs if r["status"] in ("failed", "blocked"))

            # Get chapter status distribution
            chapters = self.repo.get_chapters(project_id)
            status_dist: dict[str, int] = {}
            for ch in chapters:
                status = ch.get("status", "unknown")
                status_dist[status] = status_dist.get(status, 0) + 1

            # Get recent errors
            recent_errors = [
                r["error_message"]
                for r in today_runs
                if r.get("error_message")
            ][:5]

            # Build report
            report = DailyReport(
                date=date,
                project_id=project_id,
                total_runs=total_runs,
                successful_runs=successful_runs,
                failed_runs=failed_runs,
                chapter_status_distribution=status_dist,
                recent_errors=recent_errors,
                summary=f"今日运行 {total_runs} 次，成功 {successful_runs} 次，失败 {failed_runs} 次",
            )

            # Save to database
            report_id = self.repo.save_report(
                project_id=project_id,
                report_type="daily",
                content_json=report.model_dump(),
                summary=report.summary,
                report_date=date,
            )

            logger.info(f"Secretary generated daily report {report_id} for project {project_id}")

            return {
                "ok": True,
                "error": None,
                "data": {
                    "report_id": report_id,
                    "report": report.model_dump(),
                }
            }

        except Exception as e:
            logger.error(f"Secretary daily report failed: {e}")
            return {"ok": False, "error": str(e), "data": {}}

    def export_chapter(
        self,
        project_id: str,
        chapter_number: int,
        export_format: str = "markdown",
    ) -> dict[str, Any]:
        """Export chapter content and metadata.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            export_format: Export format (json, markdown).

        Returns:
            Dict with success, export_data, error.
        """
        try:
            # Get chapter
            chapter = self.repo.get_chapter(project_id, chapter_number)
            if not chapter:
                return {"ok": False, "error": f"Chapter not found: {chapter_number}", "data": {}}

            # Get version count
            conn = self.repo._conn()
            try:
                version_count = conn.execute(
                    "SELECT COUNT(*) as count FROM chapter_versions WHERE project_id=? AND chapter=?",
                    (project_id, chapter_number),
                ).fetchone()["count"]
            finally:
                conn.close()

            # Get review count and latest score
            # First, get chapter id
            chapter_id = chapter.get("id")
            if chapter_id:
                latest_review = self.repo.get_latest_review(project_id, chapter_id)
                review_count = 1 if latest_review else 0
                latest_score = latest_review["score"] if latest_review else None
            else:
                review_count = 0
                latest_score = None

            # Build export
            # Handle None content (章节未写正文)
            content = chapter.get("content") or ""
            
            export = ChapterExport(
                project_id=project_id,
                chapter_number=chapter_number,
                title=chapter.get("title", "Untitled"),
                content=content,
                word_count=chapter.get("word_count", 0),
                version_count=version_count,
                review_count=review_count,
                latest_score=latest_score,
                export_format=export_format,
                exported_at=datetime.now().isoformat(),
            )

            # Format output
            if export_format == "markdown":
                output = self._format_markdown(export)
            else:
                output = export.model_dump()

            # Save export record
            report_id = self.repo.save_report(
                project_id=project_id,
                report_type="chapter_export",
                content_json=export.model_dump(),
                summary=f"Exported chapter {chapter_number}",
                export_format=export_format,
                chapter_number=chapter_number,
            )

            logger.info(f"Secretary exported chapter {chapter_number} for project {project_id}")

            return {
                "ok": True,
                "error": None,
                "data": {
                    "report_id": report_id,
                    "export": export.model_dump(),
                    "output": output,
                }
            }

        except Exception as e:
            logger.error(f"Secretary chapter export failed: {e}")
            return {"ok": False, "error": str(e), "data": {}}

    def _format_markdown(self, export: ChapterExport) -> str:
        """Format chapter export as Markdown."""
        lines = [
            f"# {export.title}",
            "",
            f"**章节**: 第 {export.chapter_number} 章",
            f"**字数**: {export.word_count}",
            f"**版本数**: {export.version_count}",
            f"**审核次数**: {export.review_count}",
        ]
        
        if export.latest_score:
            lines.append(f"**最新评分**: {export.latest_score}")
        
        lines.extend([
            "",
            "---",
            "",
            export.content,
        ])
        
        return "\n".join(lines)
