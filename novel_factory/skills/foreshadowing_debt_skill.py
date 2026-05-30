"""ForeshadowingDebtSkill: deterministic foreshadowing debt checker.

Checks for:
1. Planted but never resolved plots (debt)
2. Resolved without being planted (invalid)
3. Stale plots beyond planned resolve chapter
4. Instruction-level missing plants/resolves

No LLM calls, no side effects.
"""

from __future__ import annotations

import json
from typing import Any

from .base import ValidatorSkill


class ForeshadowingDebtSkill(ValidatorSkill):
    """Check foreshadowing debt across chapters.

    Input payload:
        plot_holes: list of plot_hole dicts (code, type, status, planted_chapter, planned_resolve_chapter)
        instruction: current chapter instruction dict (plots_to_plant, plots_to_resolve)
        used_plot_refs: list of plot refs the author claims to have used
        chapter_number: current chapter number
        content: chapter content text (optional, for content-level checks)
    """

    skill_id = "foreshadowing-debt"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        plot_holes = payload.get("plot_holes") or []
        instruction = payload.get("instruction") or {}
        used_plot_refs = payload.get("used_plot_refs") or []
        chapter_number = int(payload.get("chapter_number") or 0)
        content = str(payload.get("content") or "")

        issues: list[str] = []
        suggestions: list[str] = []
        debt: list[str] = []
        invalid: list[str] = []
        stale: list[str] = []
        missing_plants: list[str] = []
        missing_resolves: list[str] = []

        # 1. Check plot_holes for debt and stale plots
        for ph in plot_holes:
            if not isinstance(ph, dict):
                continue
            code = str(ph.get("code") or "")
            status = str(ph.get("status") or "")
            planted = ph.get("planted_chapter") or 0
            planned_resolve = ph.get("planned_resolve_chapter") or 0

            if not code:
                continue

            if status == "planted" and planned_resolve and chapter_number > planned_resolve:
                stale.append(code)
                issues.append(f"伏笔 '{code}' 已过期：计划第 {planned_resolve} 章兑现，当前第 {chapter_number} 章仍未兑现")
                suggestions.append(f"在本章或后续章节兑现伏笔 '{code}'，或更新其计划兑现章节。")

            if status == "planted" and chapter_number > 0 and planted and chapter_number > planted + 5:
                if code not in debt:
                    debt.append(code)

        # 2. Check instruction-level plot coverage
        plots_to_plant = _parse_json_list(instruction.get("plots_to_plant", "[]"))
        plots_to_resolve = _parse_json_list(instruction.get("plots_to_resolve", "[]"))

        for ref in plots_to_plant:
            if ref not in used_plot_refs:
                missing_plants.append(ref)
                issues.append(f"指令要求埋设伏笔 '{ref}'，但未在 used_plot_refs 中")

        for ref in plots_to_resolve:
            if ref not in used_plot_refs:
                missing_resolves.append(ref)
                issues.append(f"指令要求兑现伏笔 '{ref}'，但未在 used_plot_refs 中")

        # 3. Content-level check
        if content and plots_to_resolve:
            for ref in plots_to_resolve:
                if ref in used_plot_refs and ref not in content:
                    issues.append(f"伏笔 '{ref}' 声称已兑现但正文中未直接提及")

        has_blocking = bool(debt or stale or missing_resolves)
        return {
            "ok": not has_blocking,
            "error": "; ".join(issues[:3]) if has_blocking else None,
            "data": {
                "debt": debt,
                "invalid": invalid,
                "stale": stale,
                "missing_plants": missing_plants,
                "missing_resolves": missing_resolves,
                "issues": issues,
                "suggestions": suggestions,
                "blocking": has_blocking,
            },
        }


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
