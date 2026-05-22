"""Core CLI commands: init-db, run-chapter, status, runs, artifacts, human-resume."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..common import (
    _get_settings,
    _get_effective_llm_mode,
    _StubLLM,
    init_db,
    Repository,
    Dispatcher,
)
from ..output import _print_output, print_llm_runtime_error
from ...workflow.runner import run_with_graph


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
        result = run_with_graph(
            project_id=args.project_id,
            chapter_number=args.chapter,
            settings=settings,
            repo=repo,
            llm_mode=llm_mode,
            max_steps=args.max_steps,
        )
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    use_json = getattr(args, "json", False)

    # v6.6.16: Build domain_result for CLI output (mirrors API run.py behavior)
    domain_result = _build_cli_domain_result(result, repo, args.project_id, args.chapter)
    result_with_domain = dict(result)
    result_with_domain["domain_result"] = domain_result

    # v5.2 P1 fix: Distinguish between LLM config errors and business errors
    # - LLM config errors: exit(1), ok=false
    # - GraphRecursionError: exit(1), ok=false
    # - Business blocking (requires_human): exit(0) by default, but ok=false if error present
    # - Success: exit(0), ok=true
    error_msg = result.get("error") or ""
    is_llm_config_error = "LLM configuration error" in error_msg or "API key" in error_msg or "base_url" in error_msg
    is_graph_recursion_error = "GraphRecursionError" in error_msg or "recursion limit" in error_msg.lower()
    has_error = bool(error_msg)
    requires_human = result.get("requires_human", False)

    # Determine if this is a failure that should return non-zero exit code
    is_failure = is_llm_config_error or is_graph_recursion_error or (has_error and not requires_human)

    if is_failure:
        if use_json:
            envelope = {"ok": False, "error": error_msg or None, "data": result_with_domain}
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            _print_output(result_with_domain, use_json)
        sys.exit(1)
    elif has_error and requires_human:
        # Business blocking with error - ok=false but exit(0) for recoverable blocks
        if use_json:
            envelope = {"ok": False, "error": error_msg, "data": result_with_domain}
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            _print_output(result_with_domain, use_json)
    else:
        # Normal result (success)
        if use_json:
            envelope = {"ok": True, "error": None, "data": result_with_domain}
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            _print_output(result_with_domain, use_json)

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


# ---------------------------------------------------------------------------
# v6.6.16: CLI domain_result builder (mirrors api/routes/run.py helpers)
# ---------------------------------------------------------------------------


def _build_cli_domain_result(
    result: dict,
    repo,
    project_id: str,
    chapter_number: int,
) -> dict:
    """Build domain_result for CLI run-chapter output.

    Mirrors the domain_result logic in api/routes/run.py's
    _build_run_chapter_domain_result().
    """
    from novel_factory.api.routes._memory_curator_gate import has_trusted_memory_batch

    chapter_status = result.get("chapter_status")
    error = result.get("error")
    requires_human = result.get("requires_human", False)
    awaiting_publish = result.get("awaiting_publish", False)
    run_id = result.get("run_id", "")
    has_trusted_memory = has_trusted_memory_batch(repo, project_id, chapter_number)

    if error:
        from novel_factory.api.contracts import failed
        return failed(
            error,
            user_message="章节生成失败，可重试或查看详情",
            retryable=True,
            next_action="retry_workflow",
            action_label="重试工作流",
            details={
                "chapter_status": chapter_status,
                "run_id": run_id,
            },
            flags={"workflow_failed": True},
        ).to_dict()

    if requires_human or chapter_status == "blocking":
        if chapter_status == "revision":
            from novel_factory.api.contracts import needs_human
            return needs_human(
                "章节需要返修",
                user_message="审核未通过，需要返修处理",
                next_action="retry_node",
                action_label="重试失败节点",
                details={
                    "chapter_status": chapter_status,
                    "run_id": run_id,
                },
                flags={"workflow_blocked": True, "revision_needed": True},
            ).to_dict()
        from novel_factory.api.contracts import blocked as _blocked
        return _blocked(
            "章节生成被阻塞",
            user_message="章节生成被阻塞，需要人工处理",
            next_action="reset_chapter",
            action_label="重置章节",
            details={
                "chapter_status": chapter_status,
                "run_id": run_id,
            },
            flags={"workflow_blocked": True},
        ).to_dict()

    # Completed / awaiting_publish / published
    if awaiting_publish or chapter_status in ("reviewed", "published"):
        if not has_trusted_memory:
            from novel_factory.api.contracts import partial_success
            return partial_success(
                "章节已到待发布状态，但记忆提取未成功",
                user_message="章节正文已通过审核，但记忆提取为降级/兜底状态，建议补跑记忆",
                next_action="backfill_memory",
                action_label="补跑记忆",
                details={
                    "chapter_status": chapter_status,
                    "run_id": run_id,
                },
                flags={
                    "workflow_completed": True,
                    "awaiting_publish": awaiting_publish,
                    "memory_degraded": True,
                },
            ).to_dict()

        from novel_factory.api.contracts import success
        return success(
            "章节生成完成" if chapter_status == "published" else "AI 审核通过，等待人工确认发布",
            user_message="章节生成完成",
            details={
                "chapter_status": chapter_status,
                "run_id": run_id,
            },
            flags={
                "workflow_completed": True,
                "memory_trusted": True,
            },
        ).to_dict()

    # Default: pending/unknown
    from novel_factory.api.contracts import OperationResult
    return OperationResult(
        ok=True,
        domain_status="pending",
        message="工作流完成",
        details={
            "chapter_status": chapter_status,
            "run_id": run_id,
        },
        flags={"workflow_completed": True},
    ).to_dict()
