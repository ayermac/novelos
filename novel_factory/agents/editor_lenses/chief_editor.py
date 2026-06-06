"""Chief Editor — aggregates lens reports into final pass/fail decision.

Takes all EditorLensReports from specialized lenses, applies genre-specific
editor weights, and produces a unified verdict.
"""

from __future__ import annotations

import logging
from typing import Any

from ...models.chapter_contracts import EditorLensReport, EditorLensFinding

logger = logging.getLogger(__name__)

# Default editor weights for lens aggregation
DEFAULT_WEIGHTS = {
    "type": 1.2,
    "continuity": 1.0,
    "commercial": 1.3,
    "pacing": 0.9,
    "character": 1.1,
    "mystery": 0.8,
    "style": 1.4,
}


class ChiefEditor:
    """Aggregates lens reports into a final pass/fail decision."""

    def aggregate(
        self,
        lens_reports: list[EditorLensReport],
        genre_weights: dict[str, float] | None = None,
        chapter_brief: dict | None = None,
    ) -> dict[str, Any]:
        """Aggregate lens reports into final decision.

        Args:
            lens_reports: List of EditorLensReport from all lenses.
            genre_weights: Optional genre-specific weights override.
            chapter_brief: Optional chapter brief for context.

        Returns:
            Dict with pass, score, revision_target, findings, summary.
        """
        weights = dict(DEFAULT_WEIGHTS)
        if genre_weights:
            weights.update(genre_weights)

        total_weighted_score = 0.0
        total_weight = 0.0
        all_findings = []
        blocking_count = 0
        warning_count = 0

        lens_details = []

        for report in lens_reports:
            w = weights.get(report.lens_type, 1.0)
            total_weighted_score += report.score * w
            total_weight += w

            for finding in report.findings:
                all_findings.append({
                    "lens": report.lens_type,
                    "severity": finding.severity,
                    "code": finding.code,
                    "message": finding.message,
                    "suggestion": finding.suggestion,
                })
                if finding.severity == "blocking":
                    blocking_count += 1
                elif finding.severity == "warning":
                    warning_count += 1

            lens_details.append({
                "lens_type": report.lens_type,
                "passed": report.passed,
                "score": report.score,
                "weight": w,
                "weighted_score": report.score * w,
                "finding_count": len(report.findings),
                "summary": report.summary,
            })

        # Compute final score
        final_score = total_weighted_score / total_weight if total_weight > 0 else 0.0

        # Count info-level findings for cap logic
        info_count = sum(
            1 for f in all_findings if f.get("severity") == "info"
        )

        # Determine pass/fail
        # Blocking findings always fail
        has_blocking = blocking_count > 0
        # Score threshold: 70 for pass
        score_pass = final_score >= 70.0

        passed = not has_blocking and score_pass

        # v6.9.0-fix: Cap passing scores to avoid meaningless 100 from
        # rule-only lenses that found zero issues. Purely rule-based
        # review cannot claim perfection.
        if passed and final_score >= 95.0:
            if warning_count > 0:
                final_score = min(final_score, 88.0)
            elif info_count > 0:
                final_score = min(final_score, 92.0)
            else:
                final_score = min(final_score, 92.0)
        # Ensure floor for passed chapters
        if passed:
            final_score = max(final_score, 75.0)

        # Determine revision target if failed
        revision_target = None
        if not passed:
            revision_target = self._determine_revision_target(lens_reports)

        # Build summary
        summary_parts = []
        for detail in lens_details:
            status = "PASS" if detail["passed"] else "FAIL"
            summary_parts.append(f"{detail['lens_type']}:{status}({detail['score']:.0f})")

        return {
            "passed": passed,
            "score": round(final_score, 1),
            "blocking_count": blocking_count,
            "warning_count": warning_count,
            "revision_target": revision_target,
            "findings": all_findings,
            "lens_details": lens_details,
            "summary": f"主编综合评审: {'通过' if passed else '未通过'} | 分数: {final_score:.1f} | " + " ".join(summary_parts),
        }

    @staticmethod
    def _determine_revision_target(lens_reports: list[EditorLensReport]) -> str:
        """Determine which agent should handle revision based on failing lenses.

        Mapping:
        - type, continuity issues → planner (fundamental mismatch)
        - character, mystery issues → author (content rewrite)
        - style, pacing issues → polisher (prose refinement)
        - commercial issues → author (engagement rewrite)
        """
        # Priority: planner-blocking > author > polisher
        planner_lenses = {"type", "continuity"}
        author_lenses = {"character", "mystery", "commercial"}
        polisher_lenses = {"style", "pacing"}

        has_planner_issue = False
        has_author_issue = False
        has_polisher_issue = False

        for report in lens_reports:
            if not report.passed:
                if report.lens_type in planner_lenses:
                    has_planner_issue = True
                elif report.lens_type in author_lenses:
                    has_author_issue = True
                elif report.lens_type in polisher_lenses:
                    has_polisher_issue = True

        if has_planner_issue:
            return "planner"
        if has_author_issue:
            return "author"
        if has_polisher_issue:
            return "polisher"
        return "author"  # default
