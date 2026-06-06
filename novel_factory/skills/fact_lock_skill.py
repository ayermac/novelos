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
        from ..validators.fact_lock import check_fact_integrity, extract_fact_lock

        original = str(payload.get("original_text") or "")
        polished = str(payload.get("polished_text") or payload.get("text") or "")
        fact_items = payload.get("fact_lock_items") or []

        if not polished:
            return {
                "ok": True,
                "error": None,
                "data": {"passed": True, "risk_level": "none", "changed_facts": [], "issues": []},
            }

        # If no explicit fact items, try to extract from original
        if not fact_items and original:
            try:
                fact_items = extract_fact_lock(original)
            except Exception:
                fact_items = []

        if not fact_items:
            return {
                "ok": True,
                "error": None,
                "data": {"passed": True, "risk_level": "none", "changed_facts": [], "issues": []},
            }

        try:
            result = check_fact_integrity(polished, fact_items)
            risk = getattr(result, "risk_level", "none")
            changed = getattr(result, "changed_facts", [])
            passed = risk == "none"
            issues = [f"事实变更: {f}" for f in changed] if changed else []
            return {
                "ok": passed,
                "error": "; ".join(issues) if not passed else None,
                "data": {
                    "passed": passed,
                    "risk_level": risk,
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
