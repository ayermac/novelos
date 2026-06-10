"""Helpers for passing review feedback into revision agents."""

from __future__ import annotations

import json
from typing import Any


def normalize_review_items(value: Any) -> list[str]:
    """Normalize review issues/suggestions from DB JSON or in-memory lists."""
    if value is None:
        return []
    parsed = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            return [text]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def normalize_revision_review(review: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a stable revision review payload for prompts, events, and artifacts."""
    if not review:
        return None
    return {
        "review_id": review.get("review_id") or review.get("id"),
        "score": review.get("score"),
        "revision_target": review.get("revision_target"),
        "issues": normalize_review_items(review.get("issues")),
        "suggestions": normalize_review_items(review.get("suggestions")),
    }


def revision_review_from_quality_gate(
    gate: dict[str, Any] | None,
    *,
    workflow_run_id: str | None = None,
) -> dict[str, Any] | None:
    """Build revision feedback from a failed deterministic QualityGate result.

    QualityGate can route directly to revision without an Editor review row.
    Revision agents still need the same review-like contract so they can repair
    the specific deterministic blocking issues instead of failing fast.
    """
    gate = gate or {}
    if gate.get("passed") is not False and gate.get("pass") is not False:
        return None

    blocking = [str(i).strip() for i in gate.get("blocking_issues", []) if str(i).strip()]
    priority = [str(i).strip() for i in gate.get("priority_issues", []) if str(i).strip()]
    advisory = [str(i).strip() for i in gate.get("advisory_issues", []) if str(i).strip()]
    if not (blocking or priority or advisory):
        return None

    issues = blocking + priority
    suggestions: list[str] = []
    diagnostics = gate.get("diagnostics") or {}
    for check_name in ("chapter_seam", "continuity_gate", "quality_diagnosis"):
        check_diag = diagnostics.get(check_name) or {}
        raw_suggestions = check_diag.get("suggestions") or check_diag.get("advisory_issues") or []
        if isinstance(raw_suggestions, list):
            suggestions.extend(str(item).strip() for item in raw_suggestions if str(item).strip())

    suggestions.extend(advisory[:4])
    if blocking:
        suggestions.insert(
            0,
            "必须逐条消解 QualityGate 阻断项；返修后不得保留同名阻断、不得只做语言润色。",
        )
    if any("章间衔接" in item or "时间" in item for item in blocking):
        suggestions.append("章首必须明确承接上一章时间/地点/行动钩子，避免突然跳场或无标注回退。")
    if any("标题与正文脱节" in item or "标题关键词" in item for item in blocking):
        suggestions.append("标题关键词必须以原词或自然对白形式出现在正文关键场景中；否则改标题。")

    return {
        "review_id": gate.get("review_id") or f"quality_gate:{workflow_run_id or 'current'}",
        "score": gate.get("score"),
        "revision_target": gate.get("revision_target") or "author",
        "issues": issues[:12],
        "suggestions": suggestions[:12],
        "source": "quality_gate",
        "blocking_issue_count": len(blocking),
    }


def revision_feedback_block(review: dict[str, Any] | None) -> str:
    """Format review feedback for LLM prompt context."""
    normalized = normalize_revision_review(review)
    if not normalized:
        return ""
    parts = []
    score = normalized.get("score")
    target = normalized.get("revision_target") or "unknown"
    if score is not None:
        parts.append(f"【返修来源】审核评分: {score}; 退回目标: {target}")
    issues = normalized.get("issues") or []
    suggestions = normalized.get("suggestions") or []
    if issues:
        parts.append("【退回问题】\n" + "\n".join(f"- {item}" for item in issues))
    if suggestions:
        parts.append("【修改建议】\n" + "\n".join(f"- {item}" for item in suggestions))
    return "\n\n".join(parts)


def build_revision_feedback_context(
    state: dict[str, Any] | None = None,
    repo: Any = None,
    chapter: dict[str, Any] | None = None,
) -> str:
    """通用返修反馈上下文构建器。

    优先使用 state["_revision_review"]，fallback 到 repo.get_latest_review。
    输出结构化文本块，包含【返修来源】【退回问题】【修改建议】【返修边界】。
    适用于 Author/Polisher 等所有真实 LLM 路径。
    """
    review = None
    if state and isinstance(state, dict):
        review = state.get("_revision_review")
        if not review:
            review = revision_review_from_quality_gate(
                state.get("quality_gate"),
                workflow_run_id=state.get("workflow_run_id"),
            )
    if not review and repo and chapter:
        project_id = chapter.get("project_id") or (state or {}).get("project_id")
        chapter_id = chapter.get("id") or chapter.get("chapter_id")
        if project_id and chapter_id:
            try:
                review = repo.get_latest_review(project_id, chapter_id)
            except Exception:
                review = None
    if not review:
        return ""

    normalized = normalize_revision_review(review)
    if not normalized:
        return ""

    parts = []
    score = normalized.get("score")
    target = normalized.get("revision_target") or "unknown"
    if score is not None:
        parts.append(f"【返修来源】审核评分: {score}; 退回目标: {target}")

    issues = normalized.get("issues") or []
    suggestions = normalized.get("suggestions") or []
    if issues:
        parts.append("【退回问题】\n" + "\n".join(f"- {item}" for item in issues))
    if suggestions:
        parts.append("【修改建议】\n" + "\n".join(f"- {item}" for item in suggestions))

    # 返修边界（通用提示）
    parts.append(
        "【返修边界】\n"
        "- 只修复指出的具体问题，不要重写无关段落\n"
        "- 保留原章节标题和核心事件\n"
        "- 满足字数硬门（≥85% 目标字数）\n"
        "- 避免引入新 death-penalty 违规"
    )
    return "\n\n".join(parts)
