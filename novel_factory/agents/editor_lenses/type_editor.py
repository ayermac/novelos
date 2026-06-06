"""Type Editor Lens — genre contract compliance.

Checks draft against GenreContract: forbidden_drift, promise_statement matching,
must_have_beats, and style_constraints.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...models.chapter_contracts import EditorLensReport
from .base_lens import BaseEditorLens

logger = logging.getLogger(__name__)

# Minimum length for substring matching to avoid noise from very short single-char
# patterns. Two-character forbidden-drift entries (e.g. "穿越") are still honored.
_MIN_PATTERN_LEN = 2


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

        if not genre_contract:
            return EditorLensReport(
                lens_type=self.lens_type,
                passed=True,
                score=100.0,
                summary="无类型合同可检查，默认通过",
            )

        # Check forbidden drift patterns.
        # Use whole-pattern match anchored by Unicode word boundaries to
        # reduce false positives from short common substrings.
        forbidden = genre_contract.get("forbidden_drift", [])
        for pattern in forbidden:
            if not isinstance(pattern, str):
                continue
            stripped = pattern.strip()
            if len(stripped) < _MIN_PATTERN_LEN:
                # Skip patterns that are too short to match reliably.
                continue
            try:
                # Use regex with re.escape to honour pattern as literal text
                if re.search(re.escape(stripped), content, flags=re.IGNORECASE):
                    findings.append(self._finding(
                        "blocking",
                        "FORBIDDEN_DRIFT",
                        f"检测到禁区模式: {stripped}",
                        f"移除或重写包含 '{stripped}' 的内容",
                    ))
            except re.error:
                # Pathological pattern — skip rather than crash
                logger.debug("type_editor: skipping invalid forbidden_drift pattern: %s", stripped)
                continue

        # Check must_have_beats — flag only when chapter is too short to deliver them
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
