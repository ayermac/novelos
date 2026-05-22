#!/usr/bin/env python3
"""Agent Evaluation Harness for v6.0.

Usage:
    python3 scripts/eval_agents.py planner
    python3 scripts/eval_agents.py all
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from novel_factory.skills.registry import SkillRegistry
from novel_factory.agents.role_profile import RoleProfileRegistry


def load_eval_cases(agent_id: str) -> list[dict[str, Any]]:
    eval_dir = Path(__file__).parent.parent / "evals" / "agents" / agent_id
    if not eval_dir.is_dir():
        return []
    cases = []
    for path in sorted(eval_dir.glob("*.yaml")):
        import yaml
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if "cases" in data:
                cases.extend(data["cases"])
            else:
                cases.append(data)
        except Exception:
            pass
    return cases


def run_eval_for_agent(agent_id: str) -> dict[str, Any]:
    registry = SkillRegistry()
    profile_registry = RoleProfileRegistry()
    profile = profile_registry.get(agent_id)

    cases = load_eval_cases(agent_id)
    if not cases:
        return {
            "agent_id": agent_id,
            "status": "no_cases",
            "passed": 0,
            "failed": 0,
            "total": 0,
        }

    passed = 0
    failed = 0
    results = []

    for case in cases:
        case_id = case.get("id", "unknown")
        case_input = case.get("input_fixture", {})
        expected = case.get("expected_behavior", {})

        # Run relevant capability packs. Cases may either declare explicit
        # capability_packs or rely on expected_behavior.must_pass skill checks.
        skill_results = []
        pack_ids = list(case.get("capability_packs", []))
        for check in expected.get("must_pass", []):
            skill_id = check.get("skill_id")
            if skill_id and skill_id not in pack_ids:
                pack_ids.append(skill_id)

        for pack_id in pack_ids:
            try:
                result = registry.run_skill(pack_id, case_input, agent=agent_id, stage="manual")
                skill_results.append({"pack_id": pack_id, "result": result})
            except Exception as e:
                skill_results.append({"pack_id": pack_id, "error": str(e)})

        # Simple rubric check
        ok = True
        if expected.get("must_pass"):
            for check in expected["must_pass"]:
                if check.get("type") == "skill_ok":
                    skill_id = check["skill_id"]
                    found = next((r for r in skill_results if r["pack_id"] == skill_id), None)
                    if not found or not found.get("result", {}).get("ok"):
                        ok = False
                if check.get("type") == "skill_not_ok":
                    skill_id = check["skill_id"]
                    found = next((r for r in skill_results if r["pack_id"] == skill_id), None)
                    if not found or found.get("result", {}).get("ok"):
                        ok = False

        if ok:
            passed += 1
        else:
            failed += 1

        results.append({
            "case_id": case_id,
            "passed": ok,
            "skill_results": skill_results,
        })

    return {
        "agent_id": agent_id,
        "status": "completed",
        "passed": passed,
        "failed": failed,
        "total": len(cases),
        "has_profile": profile is not None,
        "results": results,
    }


def run_all() -> dict[str, Any]:
    agents = ["planner", "screenwriter", "author", "polisher", "editor", "memory_curator"]
    agent_results = {}
    total_passed = 0
    total_failed = 0
    total_cases = 0

    for agent_id in agents:
        result = run_eval_for_agent(agent_id)
        agent_results[agent_id] = result
        total_passed += result["passed"]
        total_failed += result["failed"]
        total_cases += result["total"]

    # E2E eval placeholder
    e2e_result = {"status": "skipped", "note": "E2E eval requires real project setup"}

    return {
        "overall": {
            "passed": total_passed,
            "failed": total_failed,
            "total": total_cases,
        },
        "agents": agent_results,
        "e2e": e2e_result,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/eval_agents.py <agent_id>|all")
        return 1

    target = sys.argv[1]
    if target == "all":
        result = run_all()
    else:
        result = run_eval_for_agent(target)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("overall", result).get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
