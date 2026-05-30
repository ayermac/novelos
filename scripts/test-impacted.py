#!/usr/bin/env python3
"""test-impacted.py — Run only tests impacted by current changes.

Usage:
    python3 scripts/test-impacted.py              # auto-detect from git diff
    python3 scripts/test-impacted.py --staged      # only staged changes
    python3 scripts/test-impacted.py --dry-run     # show tests without running
    python3 scripts/test-impacted.py --verbose      # show mapping decisions
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ── Source → Test mapping ────────────────────────────────────────
# Each entry: (source_pattern, [test_files])
# First match wins for a given source file.

SOURCE_TEST_MAP: list[tuple[str, list[str]]] = [
    # ── Agents ──
    ("novel_factory/agents/editor.py", [
        "tests/test_agents.py::TestEditorAgent",
        "tests/test_v64_editor_quality_gates.py",
        "tests/test_v679_continuity_gate.py",
    ]),
    ("novel_factory/agents/author.py", [
        "tests/test_agents.py::TestAuthorAgent",
        "tests/test_v61_acceptance_fixes.py",
    ]),
    ("novel_factory/agents/polisher.py", [
        "tests/test_agents.py::TestPolisherAgent",
    ]),
    ("novel_factory/agents/planner.py", [
        "tests/test_agents.py::TestPlannerAgent",
    ]),
    ("novel_factory/agents/screenwriter.py", [
        "tests/test_agents.py::TestScreenwriterAgent",
    ]),
    ("novel_factory/agents/memory_curator.py", [
        "tests/test_agents.py::TestMemoryCuratorAgent",
        "tests/test_v6617_memory_curator_fallback.py",
        "tests/test_v6619_memory_curator_lock.py",
    ]),
    ("novel_factory/agents/autonomous_planner.py", [
        "tests/test_v555_autonomous_production_runner.py",
    ]),
    ("novel_factory/agents/continuity_checker.py", [
        "tests/test_agents.py",
    ]),

    # ── Agent Runtime ──
    ("novel_factory/agent_runtime/context_builder.py", [
        "tests/test_v662_context_inheritance.py",
    ]),
    ("novel_factory/agent_runtime/skill_hooks.py", [
        "tests/test_v680_skillized_quality_gates.py",
        "tests/test_skill_package.py",
    ]),
    ("novel_factory/agent_runtime/revision_context.py", [
        "tests/test_v611_revision_evidence.py",
    ]),

    # ── Quality ──
    ("novel_factory/quality/continuity_gate.py", [
        "tests/test_v679_continuity_gate.py",
        "tests/test_v680_skillized_quality_gates.py",
    ]),
    ("novel_factory/quality/chapter_seam.py", [
        "tests/test_v680_skillized_quality_gates.py",
    ]),
    ("novel_factory/quality/editor_strategy.py", [
        "tests/test_v64_editor_quality_gates.py",
    ]),
    ("novel_factory/quality/genesis_quality_gate.py", [
        "tests/test_v532_project_genesis.py",
    ]),
    ("novel_factory/quality/version_regression_guard.py", [
        "tests/test_v55_run_recovery.py",
    ]),
    ("novel_factory/quality/deadloop_detector.py", [
        "tests/test_v536_workflow_trace_isolation.py",
    ]),
    ("novel_factory/quality/chapter_inheritance.py", [
        "tests/test_v662_context_inheritance.py",
    ]),

    # ── Skills ──
    ("novel_factory/skills/", [
        "tests/test_v680_skillized_quality_gates.py",
        "tests/test_skill_package.py",
    ]),
    ("novel_factory/skill_packages/", [
        "tests/test_skill_package.py",
        "tests/test_skills_api.py",
    ]),

    # ── Validators ──
    ("novel_factory/validators/death_penalty.py", [
        "tests/test_v680_skillized_quality_gates.py",
        "tests/test_agents.py",
    ]),
    ("novel_factory/validators/fact_lock.py", [
        "tests/test_v680_skillized_quality_gates.py",
    ]),
    ("novel_factory/validators/chapter_checker.py", [
        "tests/test_v680_skillized_quality_gates.py",
    ]),
    ("novel_factory/validators/revision_classifier.py", [
        "tests/test_v678_revision_retry_accounting.py",
    ]),
    ("novel_factory/validators/plot_verifier.py", [
        "tests/test_quality.py",
    ]),
    ("novel_factory/validators/state_verifier.py", [
        "tests/test_quality.py",
    ]),

    # ── Workflow ──
    ("novel_factory/workflow/graph.py", [
        "tests/test_workflow.py",
    ]),
    ("novel_factory/workflow/nodes.py", [
        "tests/test_workflow.py",
        "tests/test_agents.py",
        "tests/test_v679_continuity_gate.py",
    ]),
    ("novel_factory/workflow/conditions.py", [
        "tests/test_workflow.py",
    ]),
    ("novel_factory/workflow/runner.py", [
        "tests/test_workflow.py",
        "tests/test_v55_run_recovery.py",
    ]),
    ("novel_factory/workflow/execution_events.py", [
        "tests/test_v6618_segmented_agent_payloads.py",
    ]),

    # ── LLM ──
    ("novel_factory/llm/openai_compatible.py", [
        "tests/test_v5512_llm_runtime_reliability.py",
        "tests/test_json_resilience.py",
    ]),
    ("novel_factory/llm/stub_provider.py", [
        "tests/test_agents.py",
    ]),
    ("novel_factory/llm/router.py", [
        "tests/test_llm_router.py",
    ]),
    ("novel_factory/llm/profiles.py", [
        "tests/test_llm_profiles.py",
    ]),

    # ── API Routes ──
    ("novel_factory/api/routes/run.py", [
        "tests/test_v51_api_e2e_smoke.py",
        "tests/test_v679_continuity_gate.py",
    ]),
    ("novel_factory/api/routes/production.py", [
        "tests/test_v555_autonomous_production_runner.py",
        "tests/test_v557_realtime_production_monitor.py",
    ]),
    ("novel_factory/api/routes/workflow_timeline.py", [
        "tests/test_v6618_segmented_agent_payloads.py",
    ]),
    ("novel_factory/api/routes/skills.py", [
        "tests/test_skills_api.py",
    ]),
    ("novel_factory/api/routes/world_settings.py", [
        "tests/test_v51_api_e2e_smoke.py",
    ]),

    # ── DB ──
    ("novel_factory/db/repository.py", [
        "tests/test_repository.py",
    ]),
    ("novel_factory/db/connection.py", [
        "tests/test_init_db_idempotency.py",
    ]),
    ("novel_factory/db/migrations/", [
        "tests/test_repository.py",
    ]),

    # ── Config ──
    ("novel_factory/config/skills.yaml", [
        "tests/test_v680_skillized_quality_gates.py",
        "tests/test_skill_package.py",
    ]),
    ("novel_factory/config/", [
        "tests/test_config_cli.py",
    ]),

    # ── Version ──
    ("novel_factory/version.py", [
        "tests/test_v678_revision_retry_accounting.py::TestVersionAlignment",
        "tests/test_version_alignment.py",
    ]),

    # ── Frontend ──
    ("frontend/src/", [
        "tests/test_v51_frontend_build.py",
        "tests/test_v51_frontend_quality.py",
    ]),
    ("frontend/package.json", [
        "tests/test_v678_revision_retry_accounting.py::TestVersionAlignment",
        "tests/test_version_alignment.py",
    ]),

    # ── Desktop ──
    ("desktop/package.json", [
        "tests/test_v678_revision_retry_accounting.py::TestVersionAlignment",
        "tests/test_version_alignment.py",
    ]),
]

# ── Smoke tests (always safe to run) ────────────────────────────

SMOKE_TESTS = [
    "tests/test_agents.py",
    "tests/test_workflow.py",
    "tests/test_v64_editor_quality_gates.py",
    "tests/test_v61_acceptance_fixes.py",
    "tests/test_v662_context_inheritance.py",
    "tests/test_v5512_llm_runtime_reliability.py",
]

REPO_ROOT = str(Path(__file__).parent.parent)


def get_changed_files(staged: bool = False) -> list[str]:
    """Get list of changed files from git."""
    cmd = ["git", "diff", "--name-only"]
    if staged:
        cmd.append("--cached")
    else:
        cmd.append("HEAD")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        cmd = ["git", "diff", "--name-only", "main...HEAD"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]


def map_files_to_tests(changed_files: list[str], verbose: bool = False) -> list[str]:
    """Map changed source files to their impacted test files."""
    test_set: set[str] = set()

    for changed in changed_files:
        matched = False
        for pattern, tests in SOURCE_TEST_MAP:
            if changed.startswith(pattern) or changed == pattern.rstrip("/"):
                for t in tests:
                    test_set.add(t)
                if verbose:
                    print(f"  {changed} -> {tests}", file=sys.stderr)
                matched = True
                break
        if not matched and verbose:
            print(f"  {changed} -> (no mapping)", file=sys.stderr)

    if not test_set:
        print("No test mapping found for changes. Running smoke tests.", file=sys.stderr)
        test_set.update(SMOKE_TESTS)

    return sorted(test_set)


def main():
    parser = argparse.ArgumentParser(description="Run tests impacted by current changes")
    parser.add_argument("--staged", action="store_true", help="Only consider staged changes")
    parser.add_argument("--dry-run", action="store_true", help="Show tests without running")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show mapping decisions")
    parser.add_argument("--smoke", action="store_true", help="Run smoke tests only")
    args = parser.parse_args()

    if args.smoke:
        tests = SMOKE_TESTS
        print(f"Smoke tests: {len(tests)} files", file=sys.stderr)
    else:
        changed = get_changed_files(staged=args.staged)
        if not changed:
            print("No changes detected. Nothing to test.", file=sys.stderr)
            sys.exit(0)

        print(f"Changed files: {len(changed)}", file=sys.stderr)
        if args.verbose:
            for f in changed:
                print(f"  {f}", file=sys.stderr)

        tests = map_files_to_tests(changed, verbose=args.verbose)
        print(f"Impacted tests: {len(tests)} files", file=sys.stderr)

    for t in tests:
        print(t)

    if args.dry_run:
        print(f"\nWould run {len(tests)} test files (dry run)", file=sys.stderr)
        sys.exit(0)

    if not tests:
        print("No impacted tests.", file=sys.stderr)
        sys.exit(0)

    print(f"\nRunning {len(tests)} test files...", file=sys.stderr)
    pytest_cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"] + tests
    result = subprocess.run(pytest_cmd, cwd=REPO_ROOT)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
