"""Sidecar agent dispatch — scout, secretary, continuity check, architect."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

class SidecarDispatchMixin:
    """Sidecar agent dispatch — scout, secretary, continuity check, architect."""

    def run_scout(
        self,
        project_id: str,
        topic: str | None = None,
        genre: str | None = None,
        platform: str | None = None,
        audience: str | None = None,
    ) -> dict[str, Any]:
        """Run Scout agent to generate market report.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            topic: Optional topic to analyze.
            genre: Optional target genre.
            platform: Optional target platform.
            audience: Optional target audience.

        Returns:
            Dict with success, report_id, market_report, error.
        """
        from ..agents.scout import ScoutAgent

        # v3.1: Use agent-specific LLM with error handling
        try:
            llm = self._llm_for_agent("scout")
        except ValueError as e:
            logger.error(f"LLM configuration error for scout: {e}")
            return {"ok": False, "error": f"LLM configuration error: {e}", "data": {}}

        scout = ScoutAgent(self.repo, llm)
        return scout.run(
            project_id=project_id,
            topic=topic,
            genre=genre,
            platform=platform,
            audience=audience,
        )

    def run_secretary_report(
        self,
        project_id: str,
        report_type: str = "daily",
        date: str | None = None,
    ) -> dict[str, Any]:
        """Run Secretary agent to generate report.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            report_type: Type of report (daily, weekly, etc.).
            date: Optional date string.

        Returns:
            Dict with success, report, error.
        """
        from ..agents.secretary import SecretaryAgent

        secretary = SecretaryAgent(self.repo)

        if report_type == "daily":
            return secretary.generate_daily_report(project_id, date)
        else:
            return {"success": False, "error": f"Unsupported report type: {report_type}"}

    def run_secretary_export(
        self,
        project_id: str,
        chapter_number: int,
        export_format: str = "markdown",
    ) -> dict[str, Any]:
        """Run Secretary agent to export chapter.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number to export.
            export_format: Export format (json, markdown).

        Returns:
            Dict with success, export, error.
        """
        from ..agents.secretary import SecretaryAgent

        secretary = SecretaryAgent(self.repo)
        return secretary.export_chapter(project_id, chapter_number, export_format)

    def run_continuity_check(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
    ) -> dict[str, Any]:
        """Run ContinuityChecker agent for cross-chapter consistency.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            from_chapter: Start chapter number.
            to_chapter: End chapter number.

        Returns:
            Dict with success, report, issues, error.
        """
        from ..agents.continuity_checker import ContinuityCheckerAgent

        # v3.1: Use agent-specific LLM with error handling
        try:
            llm = self._llm_for_agent("continuity_checker")
        except ValueError as e:
            logger.error(f"LLM configuration error for continuity_checker: {e}")
            return {"ok": False, "error": f"LLM configuration error: {e}", "data": {}}

        checker = ContinuityCheckerAgent(self.repo, llm)
        return checker.run(project_id, from_chapter, to_chapter)

    def run_architect_suggest(
        self,
        project_id: str,
        scope: str = "quality",
    ) -> dict[str, Any]:
        """Run Architect agent to generate improvement proposals.

        Note: This is a sidecar method that does NOT change chapter status
        or automatically apply any changes.

        Args:
            project_id: Project identifier.
            scope: Scope of analysis (quality, workflow, agent, system).

        Returns:
            Dict with success, proposals, error.
        """
        from ..agents.architect import ArchitectAgent

        # v3.1: Use agent-specific LLM with error handling
        try:
            llm = self._llm_for_agent("architect")
        except ValueError as e:
            logger.error(f"LLM configuration error for architect: {e}")
            return {"ok": False, "error": f"LLM configuration error: {e}", "data": {}}

        architect = ArchitectAgent(self.repo, llm)
        return architect.run(project_id, scope)
