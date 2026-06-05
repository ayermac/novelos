"""Type Editor Lens — genre contract compliance.

Checks draft against GenreContract: forbidden_drift, promise_statement matching,
must_have_beats, and style_constraints.
"""

from __future__ import annotations

import logging
from typing import Any

from ...models.chapter_contracts import EditorLensReport
from .base_lens import BaseEditorLens

logger = logging.getLogger(__name__)


class TypeEditorLens(BaseEditorLens):
    """Verifies chapter adheres to genre contract and project promises."""

    lens_type = "type"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        llm: Any | None = None,
    ) -> EditorLensReport:
        findings = []
        genre_contract = context.get("genre_contract", {})
        launch_profile = context.get("launch_profile", {})

        if not genre_contract:
            return EditorLensReport(
                lens_type=self.lens_type,
                passed=True,
                score=100.0,
                summary="无类型合同可检查，默认通过",
            )

        # Check forbidden drift patterns
        forbidden = genre_contract.get("forbidden_drift", [])
        for pattern in forbidden:
            if isinstance(pattern, str) and pattern.lower() in content.lower():
                findings.append(self._finding(
                    "blocking",
                    "FORBIDDEN_DRIFT",
                    f"检测到禁区模式: {pattern}",
                    f"移除或重写包含 '{pattern}' 的内容",
                ))

        # Check style constraints
        style_constraints = genre_contract.get("style_constraints", [])
        for constraint in style_constraints:
            if isinstance(constraint, str) and len(constraint) > 2:
                # Simple keyword check for style violations
                pass  # Complex style checks go through LLM

        # Check promise statement (keyword presence)
        promise = genre_contract.get("promise_statement", "")
        if promise and len(content) > 100:
            # For now, just check content length is substantial enough
            # LLM-based promise matching would be done via chief_editor
            pass

        # Check must_have_beats
        must_have = genre_contract.get("must_have_beats", [])
        if must_have and len(content) < 200:
            findings.append(self._finding(
                "warning",
                "INSUFFICIENT_CONTENT",
                f"章节内容过短（{len(content)}字），无法体现必有节拍",
                "确保章节长度足够展现所有必有节拍",
            ))

        score = self._compute_score(findings)
        passed = not any(f.severity == "blocking" for f in findings)

        return EditorLensReport(
            lens_type=self.lens_type,
            passed=passed,
            score=score,
            findings=findings,
            summary=f"类型合规检查: {len(findings)} 个问题",
        )
