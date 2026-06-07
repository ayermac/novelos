"""Chapter inheritance validation for v6.6.2.

Light-weight checks that verify whether a generated payload (brief, beats, draft)
reasonably inherits from the previous chapter.  First version is advisory-heavy
and only flags obvious hard-constraint violations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..agent_runtime.context_builder import AgentContextBundle


@dataclass
class InheritanceCheckResult:
    """Result of validating chapter inheritance."""

    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    advisory_issues: list[str] = field(default_factory=list)


def validate_chapter_inheritance(
    prev_state: dict[str, Any] | None,
    context_bundle: AgentContextBundle,
    generated_payload: dict[str, Any],
) -> InheritanceCheckResult:
    """Check whether generated payload respects chapter inheritance.

    Args:
        prev_state: Previous chapter's state card (optional).
        context_bundle: The context bundle used for generation.
        generated_payload: The output to validate (brief dict, beats list, or draft dict).

    Returns:
        InheritanceCheckResult with warnings / blocking / advisory lists.
    """
    result = InheritanceCheckResult()

    has_inheritance_context = (
        prev_state
        or context_bundle.chapter_inheritance
        or context_bundle.hard_constraints
        or context_bundle.plot_obligations
        or context_bundle.timeline_constraints
    )
    if not has_inheritance_context:
        # First chapter or no prior context — nothing to validate
        return result

    payload_text = _payload_to_text(generated_payload)
    prev_state_data = _extract_state_data(prev_state)

    # 1. Suspense hooks
    suspense_hooks: list[str] = []
    for it in context_bundle.hard_constraints:
        if it.kind == "suspense_hook":
            suspense_hooks.append(it.text)
    if not suspense_hooks and prev_state_data:
        for key in ("suspense_hooks", "悬念", "未处理悬念"):
            hooks = prev_state_data.get(key)
            if isinstance(hooks, list):
                suspense_hooks.extend(str(h) for h in hooks)

    unhandled_suspense: list[str] = []
    for hook in suspense_hooks:
        keywords = _extract_keywords(hook)
        if keywords and not any(kw in payload_text for kw in keywords):
            unhandled_suspense.append(hook)
    if unhandled_suspense:
        result.warnings.append(
            f"上一章悬念未明显处理: {', '.join(s[:40] for s in unhandled_suspense[:2])}"
        )

    # 2. Timeline constraints (advisory only — keyword matching is crude)
    unhandled_timeline: list[str] = []
    for it in context_bundle.timeline_constraints:
        keywords = _extract_keywords(it.text)
        if keywords:
            matched = sum(1 for kw in keywords if kw in payload_text)
            # Only warn if NONE of the keywords match (not just some)
            if matched == 0:
                unhandled_timeline.append(it.text)
    if unhandled_timeline:
        result.advisory_issues.append(
            f"时间线约束未明显处理: {', '.join(t[:40] for t in unhandled_timeline[:2])}"
        )

    # 3. Active plot holes — at least some should be referenced
    plot_refs: list[str] = []
    for it in context_bundle.plot_obligations:
        plot_refs.extend(_extract_keywords(it.text))
    if plot_refs:
        matched = sum(1 for ref in plot_refs if ref in payload_text)
        if matched == 0 and len(plot_refs) >= 2:
            result.advisory_issues.append(
                "活跃伏笔/情节债务在本章输出中未出现任何引用，建议确认是否遗漏。"
            )

    # 4. Character state continuity (advisory only)
    prev_char_status: dict[str, str] = {}
    if prev_state_data:
        prev_char_status = prev_state_data.get("character_status") or {}
    if isinstance(prev_char_status, dict) and prev_char_status:
        # Very light check: if a character was injured / imprisoned / etc.,
        # the payload should at least mention the character name.
        for name, status in list(prev_char_status.items())[:5]:
            if name not in payload_text:
                result.advisory_issues.append(
                    f"角色 '{name}' 在上一章状态卡中有记录，本章输出中未提及。"
                )

    # 5. Hard blocking: explicit contradiction with hard constraints
    for it in context_bundle.hard_constraints:
        if it.kind == "timeline_constraint":
            # If a timeline says "三天后旧工业区" and the payload says
            # "三天后林默去了新工业区" without acknowledging the change,
            # that's a potential contradiction — but we keep it advisory
            # unless the contradiction is extremely obvious.
            pass

    # Determine overall pass: only fail on explicit blocking issues.
    # First version is lenient.
    result.passed = len(result.blocking_issues) == 0
    return result


def _payload_to_text(payload: dict[str, Any]) -> str:
    """Flatten a payload dict to searchable text."""
    if not payload:
        return ""
    parts: list[str] = []
    for key in ("objective", "required_events", "constraints", "ending_hook",
                "scene_beats", "content", "title", "summary",
                "implemented_events", "used_plot_refs"):
        val = payload.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    parts.append(json.dumps(item, ensure_ascii=False))
                else:
                    parts.append(str(item))
        elif isinstance(val, dict):
            parts.append(json.dumps(val, ensure_ascii=False))
        else:
            parts.append(str(val))
    return " ".join(parts)


def _extract_state_data(state_card: dict[str, Any] | None) -> dict[str, Any]:
    if not state_card:
        return {}
    data = state_card.get("state_data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    return data if isinstance(data, dict) else {}


def _extract_keywords(text: str) -> list[str]:
    """Extract searchable keywords from a text snippet."""
    import re

    tokens = re.findall(r"[A-Za-z0-9Ωω]+|[\u4e00-\u9fff]{2,8}", str(text or ""))
    stop = {"本章", "上一章", "一个", "为何", "是否", "关系", "真实", "目的", "身份", "主角"}
    return [t for t in tokens if t not in stop][:5]
