"""Chapter Objective Checker — v2.0.0 package handler."""

from __future__ import annotations

import json
from typing import Any

from novel_factory.skills.base import ValidatorSkill


class ChapterObjectiveCheckerSkill(ValidatorSkill):
    """Validate Planner chapter objectives and required events."""

    skill_id = "chapter-objective-checker"
    skill_type = "validator"
    version = "2.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = payload.get("chapter_brief") if isinstance(payload.get("chapter_brief"), dict) else payload
        objective = str(brief.get("objective") or "").strip()
        events = _as_list(brief.get("required_events") or brief.get("key_events"))
        constraints = _as_list(brief.get("constraints"))
        issues: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not objective:
            issues.append(_issue("missing_objective", "章节目标为空", "为本章补充具体目标。"))
        elif len(objective) < 8:
            issues.append(_issue("vague_objective", "章节目标过短，缺少可执行信息", "写清主角状态、行动和结果。"))

        vague_terms = ("成长", "变强", "推进剧情", "继续冒险", "发生变化")
        if objective and any(term in objective for term in vague_terms) and not events:
            issues.append(_issue("abstract_objective", "章节目标偏抽象且未列出关键事件", "补充可落地的事件或约束。"))

        if not events:
            issues.append(_issue("missing_required_events", "缺少 required_events/key_events", "至少列出 1 个本章必须发生的事件。"))
        elif len([event for event in events if str(event).strip()]) < len(events):
            warnings.append("required_events 中存在空事件。")

        if not constraints:
            warnings.append("未提供 constraints，建议列出事实、视角或节奏约束。")

        return {
            "ok": not issues,
            "error": "; ".join(issue["message"] for issue in issues) if issues else None,
            "data": {
                "score": max(0, 100 - len(issues) * 35 - len(warnings) * 10),
                "issues": issues,
                "warnings": warnings,
                "blocking": bool(issues),
            },
        }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [part.strip() for part in text.replace("，", ",").split(",") if part.strip()]
    return [value]


def _issue(code: str, message: str, suggestion: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "suggestion": suggestion, **extra}
