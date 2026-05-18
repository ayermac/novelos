"""Event Coverage Checker — v2.0.0 package handler."""

from __future__ import annotations

import json
from typing import Any

from novel_factory.skills.base import ValidatorSkill


class EventCoverageCheckerSkill(ValidatorSkill):
    """Validate Author output against required events."""

    skill_id = "event-coverage-checker"
    skill_type = "validator"
    version = "2.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or payload.get("text") or "")
        required_events = _as_list(payload.get("required_events") or payload.get("key_events"))
        implemented_events = _as_list(payload.get("implemented_events"))
        issues: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not content.strip():
            issues.append(_issue("missing_content", "正文为空", "生成正文后再进入保存。"))

        missing: list[str] = []
        for event in required_events:
            event_text = str(event).strip()
            if not event_text:
                continue
            covered_by_declared = any(_loosely_matches(event_text, str(done)) for done in implemented_events)
            covered_by_content = event_text in content
            if not covered_by_declared and not covered_by_content:
                missing.append(event_text)

        if required_events and not implemented_events:
            warnings.append("Author 输出未声明 implemented_events。")
        if missing:
            issues.append(_issue("missing_required_events", f"正文可能遗漏 {len(missing)} 个必需事件", "检查正文或 implemented_events 是否覆盖写作指令。", missing_events=missing))

        coverage = 1.0
        if required_events:
            coverage = max(0.0, (len(required_events) - len(missing)) / len(required_events))

        return {
            "ok": not issues,
            "error": "; ".join(issue["message"] for issue in issues) if issues else None,
            "data": {
                "coverage": coverage,
                "missing_events": missing,
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


def _loosely_matches(required: str, implemented: str) -> bool:
    if not required or not implemented:
        return False
    if required in implemented or implemented in required:
        return True
    required_tokens = {token for token in required.replace("，", ",").replace("、", ",").split(",") if token}
    return any(token and token in implemented for token in required_tokens)


def _issue(code: str, message: str, suggestion: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "suggestion": suggestion, **extra}
