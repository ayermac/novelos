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
