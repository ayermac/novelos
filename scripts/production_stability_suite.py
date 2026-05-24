#!/usr/bin/env python3
"""Production stability gate for v6.6.22-v6.7.0 readiness.

Default mode is safe: no real LLM calls. Real soak requires --real-soak.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from novel_factory.db.repository import Repository  # noqa: E402
from novel_factory.ops import (  # noqa: E402
    audit_project_memory,
    evaluate_chapter_quality,
    inspect_chapter_recovery,
)
from novel_factory.version import get_version  # noqa: E402


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def _run_command(name: str, command: list[str], *, timeout: int = 180, required: bool = True) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return {
            "name": name,
            "required": required,
            "ok": False,
            "message": f"{type(exc).__name__}: {exc}",
        }
    parsed: Any = None
    if result.stdout.strip().startswith("{"):
        try:
            parsed = json.loads(result.stdout)
        except Exception:
            parsed = None
    return {
        "name": name,
        "required": required,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "message": (result.stdout or result.stderr)[-1200:],
        "data": parsed,
    }


def _quality_gate(repo: Repository, project_id: str, chapters: int) -> dict[str, Any]:
    results = []
    for chapter_number in range(1, chapters + 1):
        chapter = repo.get_chapter(project_id, chapter_number)
        beats = repo.get_scene_beats(project_id, chapter_number)
        result = evaluate_chapter_quality(chapter, beats)
        result["chapter_number"] = chapter_number
        results.append(result)
    failed = [item for item in results if not item["ok"]]
    return {
        "name": "quality_acceptance",
        "required": True,
        "ok": not failed,
        "chapters": results,
        "message": "quality acceptance passed" if not failed else f"{len(failed)} chapter(s) failed quality acceptance",
    }


def _recovery_gate(repo: Repository, project_id: str, chapters: int) -> dict[str, Any]:
    results = []
    blocking_states = {"failed", "blocked", "stale_running", "terminal_with_running_run"}
    for chapter_number in range(1, chapters + 1):
        result = inspect_chapter_recovery(repo, project_id, chapter_number)
        results.append(result)
    blocked = [item for item in results if item["state"] in blocking_states]
    return {
        "name": "recovery_drill",
        "required": True,
        "ok": not blocked,
        "chapters": results,
        "message": "recovery drill passed" if not blocked else f"{len(blocked)} chapter(s) need recovery action",
    }


def _memory_gate(repo: Repository, project_id: str) -> dict[str, Any]:
    result = audit_project_memory(repo, project_id)
    return {
        "name": "memory_governance",
        "required": False,
        "ok": result["ok"],
        "message": "memory governance passed" if result["ok"] else ", ".join(result["warnings"]),
        "data": result,
    }


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    if args.release_smoke:
        gates.append(_run_command(
            "release_smoke",
            [sys.executable, "scripts/release_smoke.py", "--skip-api", "--json"],
            timeout=90,
            required=True,
        ))
    else:
        gates.append({
            "name": "release_smoke",
            "required": False,
            "ok": True,
            "skipped": True,
            "message": "skipped by --no-release-smoke",
        })

    soak_cmd = [
        sys.executable,
        "scripts/soak_real_llm_long_chapter.py",
        "--llm-mode",
        "real" if args.real_soak else "stub",
        "--json",
    ]
    if args.config:
        soak_cmd.extend(["--config", args.config])
    if args.real_soak:
        gates.append(_run_command("real_llm_soak", soak_cmd, timeout=args.soak_timeout, required=True))
    elif args.soak:
        gates.append(_run_command("stub_soak", soak_cmd, timeout=args.soak_timeout, required=True))
    else:
        gates.append({
            "name": "stub_soak",
            "required": False,
            "ok": True,
            "skipped": True,
            "message": "skipped by --no-soak",
        })

    if args.db_path and args.project_id:
        repo = Repository(args.db_path)
        gates.append(_quality_gate(repo, args.project_id, args.chapters))
        gates.append(_recovery_gate(repo, args.project_id, args.chapters))
        gates.append(_memory_gate(repo, args.project_id))
    else:
        gates.append({
            "name": "project_gates",
            "required": False,
            "ok": True,
            "skipped": True,
            "message": "provide --db-path and --project-id to run quality/recovery/memory gates",
        })

    required_failed = [gate for gate in gates if gate.get("required") and not gate.get("ok")]
    optional_failed = [gate for gate in gates if not gate.get("required") and not gate.get("ok")]
    return {
        "ok": not required_failed,
        "version": get_version(),
        "real_soak": bool(args.real_soak),
        "required_failed": len(required_failed),
        "optional_failed": len(optional_failed),
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Novelos production stability gates")
    parser.add_argument("--db-path", help="SQLite DB path for project gates")
    parser.add_argument("--project-id", help="Project id for project gates")
    parser.add_argument("--chapters", type=_positive_int, default=1)
    parser.add_argument("--config", help="Config YAML for real LLM mode")
    parser.add_argument("--real-soak", action="store_true", help="Run real LLM soak; may incur provider cost")
    parser.add_argument("--no-soak", dest="soak", action="store_false", default=True)
    parser.add_argument("--no-release-smoke", dest="release_smoke", action="store_false", default=True)
    parser.add_argument("--soak-timeout", type=int, default=300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_suite(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Novelos Production Stability Suite")
        print(f"Version: {result['version']}")
        for gate in result["gates"]:
            status = "PASS" if gate["ok"] else "FAIL"
            required = "required" if gate.get("required") else "optional"
            print(f"[{status}] {gate['name']} ({required}) - {gate.get('message', '')}")
        print("Result:", "PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
