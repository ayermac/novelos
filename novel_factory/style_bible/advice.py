"""v4.1 Style Revision Advice generator.

Builds structured revision advice from Style Bible check results.
Does NOT call LLM. Does NOT auto-rewrite text.
"""

from __future__ import annotations

from typing import Any

from ..models.style_bible import StyleBible, StyleCheckReport, StyleCheckIssue
from ..models.style_gate import StyleRevisionAdvice, StyleGateStage


def build_style_revision_advice(
    style_check_report: dict[str, Any] | StyleCheckReport,
    style_bible: dict[str, Any] | StyleBible,
    stage: str = "polished",
) -> dict[str, Any]:
    """Build structured style revision advice from check results.

    Args:
        style_check_report: The StyleBibleChecker output (dict or model).
        style_bible: The Style Bible data (dict or model).
        stage: The production stage (draft/polished/final_gate).

    Returns:
        Envelope with StyleRevisionAdvice data.
    """
    # Normalize inputs
    if isinstance(style_check_report, dict):
        report = StyleCheckReport(**style_check_report)
    else:
        report = style_check_report

    if isinstance(style_bible, dict):
        try:
            bible = StyleBible.from_storage_dict(style_bible)
        except Exception:
            return {"ok": False, "error": "Invalid Style Bible data", "data": {}}
    elif isinstance(style_bible, StyleBible):
        bible = style_bible
    else:
        return {"ok": False, "error": "Invalid Style Bible data", "data": {}}

    # Build advice
    advice = StyleRevisionAdvice()

    # Determine revision target based on issue types
    has_content_issues = False
    has_style_issues = False

    for issue in report.issues:
        if issue.rule_type in ("forbidden_expression", "ai_trace"):
            has_style_issues = True
        elif issue.rule_type in ("rule_violation", "tone_deviation"):
            has_content_issues = True

    # Determine priority
    if report.blocking_issues > 0:
        advice.priority = "high"
    elif report.warning_issues > 3:
        advice.priority = "medium"
    else:
        advice.priority = "low"

    # Determine revision target
    if stage in ("draft",):
        advice.revision_target = "author"
    elif has_content_issues and not has_style_issues:
        advice.revision_target = "author"
    else:
        advice.revision_target = "polisher"

    # Collect issues
    advice.issues = [issue.description for issue in report.issues[:20]]

    # Build rewrite guidance
    guidance_parts = []
    if report.blocking_issues > 0:
        guidance_parts.append(f"发现 {report.blocking_issues} 个严重风格违规，必须修复。")
    if report.warning_issues > 0:
        guidance_parts.append(f"发现 {report.warning_issues} 个风格警告，建议关注。")
    if report.score < 50:
        guidance_parts.append("风格合规评分过低，建议全面检查。")
    advice.rewrite_guidance = " ".join(guidance_parts) if guidance_parts else "风格合规良好。"

    # Forbidden expression fixes
    for issue in report.issues:
        if issue.rule_type == "forbidden_expression" and issue.suggestion:
            advice.forbidden_expression_fixes.append({
                "issue": issue.description,
                "fix": issue.suggestion,
                "location": issue.location,
            })

    # Preferred expression suggestions
    for pe in bible.preferred_expressions[:5]:
        advice.preferred_expression_suggestions.append({
            "pattern": pe.pattern,
            "context": pe.context,
        })

    # Sentence suggestions
    for issue in report.issues:
        if issue.rule_type == "rule_violation" and "超长句" in issue.description:
            advice.sentence_suggestions.append(issue.suggestion or "拆分为短句")

    # Paragraph suggestions
    for issue in report.issues:
        if issue.rule_type == "rule_violation" and "超长段落" in issue.description:
            advice.paragraph_suggestions.append(issue.suggestion or "拆分为更短段落")

    return {
        "ok": True,
        "error": None,
        "data": advice.model_dump(),
    }
