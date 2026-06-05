"""Base class for specialized editor lenses."""

from __future__ import annotations

import logging
from typing import Any

from ...models.chapter_contracts import EditorLensReport, EditorLensFinding

logger = logging.getLogger(__name__)


class BaseEditorLens:
    """Base class for all editor lenses.

    Each lens evaluates one dimension of chapter quality and produces
    an EditorLensReport. Subclasses implement evaluate().
    """

    lens_type: str = "base"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        llm: Any | None = None,
    ) -> EditorLensReport:
        """Evaluate chapter content from this lens's perspective.

        Args:
            content: Chapter text content.
            context: Context dict with project_id, chapter_number, instruction, etc.
            llm: Optional LLM provider for complex checks.

        Returns:
            EditorLensReport with findings and verdict.
        """
        raise NotImplementedError

    @staticmethod
    def _finding(
        severity: str,
        code: str,
        message: str,
        suggestion: str = "",
    ) -> EditorLensFinding:
        """Helper to create a finding."""
        return EditorLensFinding(
            severity=severity,
            code=code,
            message=message,
            suggestion=suggestion,
        )

    @staticmethod
    def _compute_score(findings: list[EditorLensFinding], max_score: float = 100.0) -> float:
        """Compute a score from 0-100 based on findings severity."""
        score = max_score
        for f in findings:
            if f.severity == "blocking":
                score -= 20
            elif f.severity == "warning":
                score -= 10
            elif f.severity == "info":
                score -= 3
        return max(0.0, min(max_score, score))
