"""Sidecar agent dispatch for optional diagnostic agents."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

class SidecarDispatchMixin:
    """Sidecar agent dispatch for optional diagnostics."""

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
