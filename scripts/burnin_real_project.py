#!/usr/bin/env python3
"""v6.6.16 manual burn-in for the Anomaly Corrector fixture.

Default mode is stub and uses a temporary SQLite database. The script exercises
the same real project fixture used by the regression tests:

init DB -> seed fixture -> chapter 1 -> memory status/backfill -> publish check
-> chapter 2 -> run detail audit -> workflow timeline semantics.

Usage:
    python3 scripts/burnin_real_project.py
    python3 scripts/burnin_real_project.py --keep-db
    python3 scripts/burnin_real_project.py --real-mode --config config/local.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from novel_factory.api.routes._memory_curator_gate import (  # noqa: E402
    get_memory_status_for_chapter,
)
from novel_factory.api_app import create_api_app  # noqa: E402
from novel_factory.db.connection import get_connection, init_db  # noqa: E402
from novel_factory.db.repository import Repository  # noqa: E402
from novel_factory.version import get_version  # noqa: E402
from tests.fixtures.burnin_project import (  # noqa: E402
    BURNIN_PROJECT_ID,
    PROJECT_NAME,
    seed_burnin_project,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="v6.6.16 real project burn-in")
    parser.add_argument("--real-mode", action="store_true", help="Use real LLM; incurs API cost.")
    parser.add_argument("--config", default=None, help="Path to config YAML for real mode.")
    parser.add_argument("--project-id", default=BURNIN_PROJECT_ID)
    parser.add_argument("--max-chapters", type=int, default=2)
    parser.add_argument("--keep-db", action="store_true", help="Keep the temporary DB after run.")
    args = parser.parse_args()

    llm_mode = "real" if args.real_mode else "stub"
    if args.real_mode:
        _check_real_mode_ready(args.config)

    temp_dir_obj = None
    if args.keep_db:
        db_dir = Path(tempfile.mkdtemp(prefix="novelos_burnin_", dir=str(REPO_ROOT)))
    else:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="novelos_burnin_")
        db_dir = Path(temp_dir_obj.name)
    db_path = db_dir / "burnin.db"

    print(f"v6.6.16 Burn-in: {PROJECT_NAME} ({args.project_id})")
    print(f"  Version:  {get_version()}")
    print(f"  LLM mode: {llm_mode}")
    print(f"  DB path:  {db_path}")

    results: list[dict[str, Any]] = []
    client: TestClient | None = None
    exit_code = 0

    try:
        repo = _record_step(
            results,
            "init_and_seed_fixture",
            lambda: _init_and_seed(db_path, args.project_id),
        )
        client = TestClient(
            create_api_app(
                db_path=str(db_path),
                config_path=args.config,
                llm_mode=llm_mode,
            )
        )

        _record_step(
            results,
            "context_readiness",
            lambda: _context_readiness(repo, args.project_id),
        )

        chapter1 = _record_step(
            results,
            "chapter_1_run",
            lambda: _run_chapter(db_path, args.config, llm_mode, args.project_id, 1),
        )
        run_id_1 = chapter1["run_id"]

        _record_step(
            results,
            "chapter_1_run_detail",
            lambda: _run_detail(client, run_id_1),
        )
        _record_step(
            results,
            "chapter_1_memory_status",
            lambda: _memory_status(repo, args.project_id, 1),
        )
        _record_step(
            results,
            "memory_backfill_force",
            lambda: _memory_backfill(client, run_id_1),
        )
        _record_step(
            results,
            "publish_readiness",
            lambda: _publish_readiness(client, repo, args.project_id, 1),
        )

        if args.max_chapters >= 2:
            chapter2 = _record_step(
                results,
                "chapter_2_run",
                lambda: _run_chapter(db_path, args.config, llm_mode, args.project_id, 2),
            )
            run_id_2 = chapter2["run_id"]
            _record_step(
                results,
                "chapter_2_memory_context_audit",
                lambda: _memory_context_audit(client, run_id_2),
            )
            _record_step(
                results,
                "chapter_2_timeline",
                lambda: _timeline(client, args.project_id, 2),
            )

    except Exception as exc:
        exit_code = 1
        results.append({
            "step": "fatal",
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        })
    finally:
        if client is not None:
            client.close()

    summary = {
        "version": get_version(),
        "project_id": args.project_id,
        "llm_mode": llm_mode,
        "db_path": str(db_path),
        "steps": results,
        "overall": {
            "total_steps": len(results),
            "ok": sum(1 for step in results if step.get("status") == "ok"),
            "warning": sum(1 for step in results if step.get("status") == "warning"),
            "error": sum(1 for step in results if step.get("status") == "error"),
        },
    }
    if summary["overall"]["error"]:
        exit_code = 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if temp_dir_obj is not None:
        temp_dir_obj.cleanup()
    return exit_code


def _record_step(results: list[dict[str, Any]], name: str, fn):
    print(f"\n[burn-in] {name}")
    try:
        data = fn()
        entry_data = data if isinstance(data, dict) else {}
        entry = {"step": name, "status": "ok", **entry_data}
        results.append(entry)
        print(f"  ok: {json.dumps(entry_data, ensure_ascii=False)[:500]}")
        return data
    except Exception as exc:
        entry = {
            "step": name,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
        results.append(entry)
        print(f"  error: {entry['error']}")
        raise


def _init_and_seed(db_path: Path, project_id: str) -> Repository:
    init_db(db_path)
    repo = Repository(str(db_path))
    seed_burnin_project(repo, project_id=project_id)
    project = repo.get_project(project_id)
    if not project:
        raise RuntimeError("burn-in fixture project was not seeded")
    return repo


def _context_readiness(repo: Repository, project_id: str) -> dict[str, Any]:
    world_settings = repo.list_world_settings(project_id)
    characters = repo.list_characters(project_id, include_inactive=True)
    factions = repo.list_factions(project_id)
    outlines = repo.list_outlines(project_id)
    plot_holes = repo.list_plot_holes(project_id)
    instruction = repo.get_instruction_by_chapter(project_id, 1)
    checks = {
        "world_settings": len(world_settings),
        "characters": len(characters),
        "factions": len(factions),
        "outlines": len(outlines),
        "plot_holes": len(plot_holes),
        "chapter_1_instruction": bool(instruction),
    }
    if (
        checks["world_settings"] < 3
        or checks["characters"] < 4
        or checks["factions"] < 1
        or checks["outlines"] < 3
        or checks["plot_holes"] < 3
        or not checks["chapter_1_instruction"]
    ):
        raise RuntimeError(f"context readiness failed: {checks}")
    return checks


def _run_chapter(
    db_path: Path,
    config_path: str | None,
    llm_mode: str,
    project_id: str,
    chapter_number: int,
) -> dict[str, Any]:
    output = _run_cli_json(
        db_path,
        config_path,
        [
            "--llm-mode", llm_mode,
            "run-chapter",
            "--project-id", project_id,
            "--chapter", str(chapter_number),
        ],
        timeout=180,
    )
    data = output.get("data") or {}
    if output.get("ok") is not True:
        raise RuntimeError(f"run-chapter returned ok=false: {output}")
    if not data.get("run_id"):
        raise RuntimeError(f"run-chapter missing run_id: {output}")
    if data.get("chapter_status") not in {"reviewed", "awaiting_publish", "published"}:
        raise RuntimeError(f"unexpected chapter status: {data.get('chapter_status')}")
    domain = data.get("domain_result") or {}
    if not domain.get("domain_status") or not domain.get("severity"):
        raise RuntimeError(f"run-chapter missing domain_result: {output}")
    return {
        "run_id": data["run_id"],
        "chapter_status": data["chapter_status"],
        "domain_status": domain["domain_status"],
        "severity": domain["severity"],
    }


def _run_detail(client: TestClient, run_id: str) -> dict[str, Any]:
    response = client.get(f"/api/runs/{run_id}")
    payload = response.json()
    if response.status_code != 200 or payload.get("ok") is not True:
        raise RuntimeError(f"run detail failed: {payload}")
    data = payload["data"]
    for key in ("domain_result", "memory_status", "recovery_state"):
        if key not in data:
            raise RuntimeError(f"run detail missing {key}")
    return {
        "workflow_status": data.get("workflow_status"),
        "chapter_status": data.get("chapter_status"),
        "domain_status": data["domain_result"].get("domain_status"),
        "memory_status": data["memory_status"].get("memory_status"),
    }


def _memory_status(repo: Repository, project_id: str, chapter_number: int) -> dict[str, Any]:
    memory = get_memory_status_for_chapter(repo, project_id, chapter_number)
    return {
        "memory_status": memory["memory_status"],
        "trusted_batch_count": memory.get("trusted_batch_count", 0),
        "fallback_batch_count": memory.get("fallback_batch_count", 0),
    }


def _memory_backfill(client: TestClient, run_id: str) -> dict[str, Any]:
    response = client.post(
        f"/api/runs/{run_id}/memory/backfill",
        json={"confirm": True, "force": True},
    )
    payload = response.json()
    if response.status_code != 200:
        raise RuntimeError(f"memory backfill HTTP failed: {payload}")
    if payload.get("ok") is True:
        data = payload["data"]
        domain = data.get("domain_result") or {}
    else:
        details = ((payload.get("error") or {}).get("details") or {})
        domain = details.get("domain_result") or {}
        if not domain:
            raise RuntimeError(f"memory backfill error missing domain_result: {payload}")
        data = details
    if not domain.get("domain_status") or not domain.get("severity"):
        raise RuntimeError(f"memory backfill missing domain_result fields: {payload}")
    return {
        "ok": payload.get("ok"),
        "domain_status": domain["domain_status"],
        "severity": domain["severity"],
        "memory_items_count": data.get("memory_items_count", 0),
    }


def _publish_readiness(
    client: TestClient,
    repo: Repository,
    project_id: str,
    chapter_number: int,
) -> dict[str, Any]:
    chapter = repo.get_chapter(project_id, chapter_number)
    status = (chapter or {}).get("status")
    if status == "published":
        return {"chapter_status": status, "publish_action": "already_published"}
    response = client.post(
        "/api/publish/chapter",
        json={"project_id": project_id, "chapter": chapter_number},
    )
    payload = response.json()
    if payload.get("ok") is True:
        domain = payload["data"].get("domain_result") or {}
    else:
        domain = ((payload.get("error") or {}).get("details") or {}).get("domain_result") or {}
        if not domain:
            raise RuntimeError(f"publish error missing domain_result: {payload}")
    return {
        "chapter_status": status,
        "publish_response_ok": payload.get("ok"),
        "domain_status": domain.get("domain_status"),
        "severity": domain.get("severity"),
    }


def _memory_context_audit(client: TestClient, run_id: str) -> dict[str, Any]:
    response = client.get(f"/api/runs/{run_id}")
    payload = response.json()
    if response.status_code != 200 or payload.get("ok") is not True:
        raise RuntimeError(f"run detail failed: {payload}")
    audit = payload["data"].get("memory_context_audit") or {}
    if audit.get("chapter_number") != 2:
        raise RuntimeError(f"chapter 2 audit missing or wrong chapter: {audit}")
    if audit.get("batch_status") == "not_applicable":
        raise RuntimeError(f"chapter 2 audit incorrectly not_applicable: {audit}")
    return {
        "batch_status": audit.get("batch_status"),
        "memory_context_degraded": audit.get("memory_context_degraded"),
        "memory_items_count": audit.get("memory_items_count"),
    }


def _timeline(client: TestClient, project_id: str, chapter_number: int) -> dict[str, Any]:
    response = client.get(f"/api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline")
    payload = response.json()
    if response.status_code != 200 or payload.get("ok") is not True:
        raise RuntimeError(f"timeline failed: {payload}")
    nodes = payload["data"].get("nodes") or []
    if not nodes:
        raise RuntimeError("timeline returned no nodes")
    memory_nodes = [node for node in nodes if node.get("node_name") == "memory_curator"]
    for node in memory_nodes:
        domain = node.get("domain_status")
        if domain in {"fallback", "degraded", "partial_success"} and node.get("severity") == "success":
            raise RuntimeError(f"memory_curator fake green: {node}")
    return {
        "node_count": len(nodes),
        "memory_node_count": len(memory_nodes),
        "memory_statuses": [node.get("domain_status") for node in memory_nodes],
    }


def _run_cli_json(
    db_path: Path,
    config_path: str | None,
    args: list[str],
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    command = [sys.executable, "-m", "novel_factory.cli", "--db-path", str(db_path)]
    if config_path:
        command.extend(["--config", config_path])
    command.extend(args)
    command.append("--json")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=timeout,
        env={**os.environ, "NOVEL_FACTORY_DISABLE_DOTENV": "1"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"CLI failed ({result.returncode}): {' '.join(command)}\n"
            f"STDOUT={result.stdout[:1000]}\nSTDERR={result.stderr[:1000]}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CLI did not return JSON: {result.stdout[:1000]}") from exc


def _check_real_mode_ready(config_path: str | None) -> None:
    if not config_path and not os.environ.get("OPENAI_API_KEY"):
        print("Real mode requires --config or OPENAI_API_KEY.")
        print("Real mode will incur LLM API costs.")
        sys.exit(1)
    print("REAL MODE active. API calls may incur costs. Press Ctrl+C within 5 seconds to abort.")
    time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
