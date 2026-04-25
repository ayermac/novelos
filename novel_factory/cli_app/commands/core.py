"""Core CLI commands: init-db, run-chapter, status, runs, artifacts, human-resume."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..common import (
    _get_settings,
    _get_effective_llm_mode,
    _build_dispatcher,
    _StubLLM,
    init_db,
    Repository,
    Dispatcher,
)
from ..output import _print_output, print_llm_runtime_error


def cmd_init_db(args) -> None:
    """Initialize the database."""
    settings = _get_settings(args)
    # Ensure parent directory exists
    db_dir = Path(settings.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)
    print(f"Database initialized at: {settings.db_path}")


def cmd_run_chapter(args) -> dict:
    """Run a chapter through the production pipeline.

    Returns:
        Dict with chapter_status, steps, error, requires_human.
    """
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    llm_mode = _get_effective_llm_mode(args)

    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {"error": str(e)}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    try:
        result = dispatcher.run_chapter(
            project_id=args.project_id,
            chapter_number=args.chapter,
            max_steps=args.max_steps,
        )
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    use_json = getattr(args, "json", False)

    # v3.1: Check for LLM configuration errors (distinguished by specific error messages)
    # Business logic errors (max_steps exceeded, requires_human) should NOT cause exit(1)
    error_msg = result.get("error") or ""
    is_llm_config_error = "LLM configuration error" in error_msg or "API key" in error_msg or "base_url" in error_msg

    if is_llm_config_error:
        if use_json:
            # LLM config error: return error envelope
            envelope = {"ok": False, "error": error_msg, "data": result}
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            _print_output(result, use_json)
        sys.exit(1)
    else:
        # Normal result (may include business errors like max_steps exceeded)
        if use_json:
            envelope = {"ok": True, "error": error_msg or None, "data": result}
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            _print_output(result, use_json)

    return result


def cmd_status(args) -> None:
    """Show chapter status."""
    settings = _get_settings(args)
    repo = Repository(settings.db_path)

    chapter = repo.get_chapter(args.project_id, args.chapter)
    use_json = getattr(args, "json", False)

    if not chapter:
        if use_json:
            print(json.dumps({"error": "Chapter not found"}, ensure_ascii=False))
        else:
            print(f"No chapter found: project={args.project_id}, chapter={args.chapter}")
        sys.exit(1)

    # Get latest workflow run for this specific chapter
    runs = repo.get_workflow_runs_for_project(args.project_id, chapter_number=args.chapter, limit=1)
    latest_run = runs[0] if runs else None

    result = {
        "project_id": args.project_id,
        "chapter_number": args.chapter,
        "status": chapter["status"],
        "word_count": chapter.get("word_count", 0),
        "latest_run": latest_run,
    }

    # Add recent error if any
    if latest_run and latest_run.get("error_message"):
        result["recent_error"] = latest_run["error_message"]

    _print_output(result, use_json)


def cmd_runs(args) -> None:
    """Show workflow runs for a project."""
    settings = _get_settings(args)
    repo = Repository(settings.db_path)

    runs = repo.get_workflow_runs_for_project(args.project_id)
    use_json = getattr(args, "json", False)

    if use_json:
        _print_output(runs, use_json)
    else:
        if not runs:
            print(f"No workflow runs found for project={args.project_id}")
            return
        for run in runs:
            print(
                f"  [{run.get('status', '?')}] "
                f"run={run['id'][:8]}... "
                f"ch={run.get('chapter_number', '?')} "
                f"node={run.get('current_node', '-')} "
                f"started={run.get('started_at', '?')}"
            )
            if run.get("error_message"):
                print(f"    error: {run['error_message']}")


def cmd_artifacts(args) -> None:
    """Show artifacts for a chapter."""
    settings = _get_settings(args)
    repo = Repository(settings.db_path)

    artifacts = repo.get_artifacts_for_chapter(args.project_id, args.chapter)
    use_json = getattr(args, "json", False)

    if use_json:
        _print_output(artifacts, use_json)
    else:
        if not artifacts:
            print(f"No artifacts found: project={args.project_id}, chapter={args.chapter}")
            return
        for art in artifacts:
            print(
                f"  [{art.get('agent_id', '?')}] "
                f"type={art.get('artifact_type', '?')} "
                f"id={art.get('id', '?')[:8]}... "
                f"created={art.get('created_at', '?')}"
            )


def cmd_human_resume(args) -> None:
    """Resume a blocked chapter to a new status.

    Note: This command does NOT run Agents, so it does NOT require LLM validation.
    """
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    # human-resume does NOT run Agents, so we use a stub LLM to satisfy Dispatcher requirement
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=settings.quality_gate.max_retries)

    result = dispatcher.resume_blocked(
        project_id=args.project_id,
        chapter_number=args.chapter,
        status=args.status,
    )

    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    _print_output(result, use_json)
