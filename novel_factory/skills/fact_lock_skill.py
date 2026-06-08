"""FactLockSkill: deterministic fact integrity checker.

Wraps validators/fact_lock.py as a ValidatorSkill.
No LLM calls, no side effects.
"""

from __future__ import annotations

from typing import Any

from .base import ValidatorSkill


class FactLockSkill(ValidatorSkill):
    """Check that key facts are preserved after polishing.

    Delegates to validators.fact_lock.check_fact_integrity().
    """

    skill_id = "fact-lock"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..models.quality import FactLockItem
        from ..validators.fact_lock import check_fact_integrity

        original = str(payload.get("original_text") or "")
        polished = str(payload.get("polished_text") or payload.get("text") or "")
        raw_fact_items = payload.get("fact_lock_items") or []

        if not polished:
            return {
                "ok": True,
                "error": None,
                "data": {"passed": True, "risk_level": "none", "changed_facts": [], "issues": []},
            }

        fact_items: list[FactLockItem] = []
        for item in raw_fact_items:
            if isinstance(item, FactLockItem):
                fact_items.append(item)
            elif isinstance(item, dict):
                fact_items.append(FactLockItem(
                    fact_type=str(item.get("fact_type") or "event"),
                    content=str(item.get("content") or ""),
                    source=str(item.get("source") or "skill_payload"),
                ))
            elif str(item).strip():
                fact_items.append(FactLockItem(
                    fact_type="event",
                    content=str(item),
                    source="skill_payload",
                ))

        if not fact_items:
            return {
                "ok": True,
                "error": None,
                "data": {"passed": True, "risk_level": "none", "changed_facts": [], "issues": []},
            }

        try:
            result = check_fact_integrity(original, polished, fact_items)
            risk = getattr(result, "risk", "none")
            missing = [getattr(f, "content", str(f)) for f in getattr(result, "missing_facts", [])]
            changed = [getattr(f, "content", str(f)) for f in getattr(result, "changed_facts", [])]
            passed = risk == "none"
            issues = [f"事实缺失: {f}" for f in missing] + [f"事实变更: {f}" for f in changed]
            return {
                "ok": passed,
                "error": "; ".join(issues) if not passed else None,
                "data": {
                    "passed": passed,
                    "risk_level": risk,
                    "missing_facts": missing,
                    "changed_facts": changed,
                    "issues": issues,
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"事实锁检查异常: {e}",
                "data": {"passed": False, "risk_level": "high", "changed_facts": [], "issues": [str(e)]},
            }
