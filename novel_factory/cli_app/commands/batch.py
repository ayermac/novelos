"""Batch CLI commands: run, status, review, revise, continuity, and all queue subcommands."""

from __future__ import annotations

import json
import sys

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


# ── Batch Production commands (v3.0) ───────────────────────────────


def cmd_batch_run(args) -> None:
    """Run batch production for multiple chapters."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    llm_mode = _get_effective_llm_mode(args)

    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    try:
        result = dispatcher.run_batch(
            project_id=args.project_id,
            from_chapter=args.from_chapter,
            to_chapter=args.to_chapter,
        )
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    use_json = getattr(args, "json", False)

    # v3.1: run_batch already returns {ok, error, data} format
    # Check for LLM configuration errors (distinguished by ok=false and specific error messages)
    # Business logic errors (blocked chapter) should NOT cause exit(1)
    error_msg = result.get("error") or ""
    is_llm_config_error = not result.get("ok") and (
        "LLM configuration error" in error_msg or
        "API key" in error_msg or
        "base_url" in error_msg
    )

    if is_llm_config_error:
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            _print_output(result, use_json)
        sys.exit(1)
    else:
        # Normal result (may include business errors like blocked chapter)
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            _print_output(result, use_json)


def cmd_batch_status(args) -> None:
    """Get batch production run status."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    # batch-status does NOT run Agents, so we use a stub LLM
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_batch_status(args.run_id)

    use_json = getattr(args, "json", False)
    _print_output(result, use_json)


def cmd_batch_review(args) -> None:
    """Record human review decision for a batch production run."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    # batch-review does NOT run Agents, so we use a stub LLM
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.review_batch(
        run_id=args.run_id,
        decision=args.decision,
        notes=getattr(args, "notes", None),
    )

    use_json = getattr(args, "json", False)
    _print_output(result, use_json)


def cmd_batch_revise(args) -> None:
    """Create and execute a batch revision plan (v3.2)."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    llm_mode = _get_effective_llm_mode(args)

    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    # Create revision plan
    try:
        plan_result = dispatcher.create_batch_revision_plan(
            run_id=args.run_id,
            plan_json=args.plan_json,
        )
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    if not plan_result.get("ok"):
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(plan_result, ensure_ascii=False))
        else:
            print(f"Error: {plan_result.get('error')}")
        sys.exit(1)

    # Execute revision
    revision_run_id = plan_result["data"]["revision_run_id"]
    try:
        run_result = dispatcher.run_batch_revision(revision_run_id)
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    use_json = getattr(args, "json", False)
    if use_json:
        # Merge results
        result = {
            "ok": run_result.get("ok", True),
            "error": run_result.get("error"),
            "data": {
                "run_id": args.run_id,
                "revision_run_id": revision_run_id,
                "affected_chapters": plan_result["data"]["affected_chapters"],
                "status": run_result["data"]["status"],
            }
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"Revision Run ID: {revision_run_id}")
        print(f"Affected Chapters: {plan_result['data']['affected_chapters']}")
        print(f"Status: {run_result['data']['status']}")
        if run_result.get("error"):
            print(f"Error: {run_result['error']}")


def cmd_batch_revision_status(args) -> None:
    """Get batch revision run status (v3.2)."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    # revision-status does NOT run Agents, so we use a stub LLM
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_batch_revision_status(args.revision_run_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Revision Run ID: {data['revision_run_id']}")
            print(f"Source Run ID: {data['source_run_id']}")
            print(f"Status: {data['status']}")
            print(f"Affected Chapters: {data['affected_chapters']}")
            print("\nItems:")
            for item in data["items"]:
                status_str = f"  Chapter {item['chapter_number']}: {item['status']}"
                if item.get("error"):
                    status_str += f" (Error: {item['error']})"
                print(status_str)
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_continuity(args) -> None:
    """Run batch continuity gate for a production run (v3.3)."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    llm_mode = _get_effective_llm_mode(args)

    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    result = dispatcher.run_batch_continuity_gate(args.run_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Continuity Gate (ID: {data['gate_id']})")
            print(f"  Status: {data['status']}")
            print(f"  Issue Count: {data['issue_count']}")
            print(f"  Summary: {data['summary']}")
            if data.get("blocking_issues"):
                print(f"  Blocking Issues:")
                for issue in data["blocking_issues"]:
                    print(f"    [{issue.get('severity', '').upper()}] {issue.get('issue_type')}: {issue.get('description')}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_continuity_status(args) -> None:
    """Get batch continuity gate status (v3.3)."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_batch_continuity_gate_status(args.run_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            gate = data.get("gate")
            if gate:
                print(f"Continuity Gate (ID: {gate['id']})")
                print(f"  Status: {gate['status']}")
                print(f"  Issue Count: {gate.get('issue_count', 0)}")
                print(f"  Summary: {gate.get('summary', 'N/A')}")
                if gate.get("blocking_issues"):
                    print(f"  Blocking Issues:")
                    for issue in gate["blocking_issues"]:
                        print(f"    [{issue.get('severity', '').upper()}] {issue.get('issue_type')}: {issue.get('description')}")
            else:
                print(f"Continuity Gate: not_run")
        else:
            print(f"Error: {result.get('error')}")


# ── v3.4 Production Queue commands ────────────────────────────────


def cmd_batch_enqueue(args) -> None:
    """Enqueue a batch production request."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    max_chapters = getattr(args, "max_chapters", 50)

    result = dispatcher.enqueue_batch(
        project_id=args.project_id,
        from_chapter=args.from_chapter,
        to_chapter=args.to_chapter,
        priority=getattr(args, "priority", 100),
        max_attempts=getattr(args, "max_attempts", 3),
        timeout_minutes=getattr(args, "timeout_minutes", 120),
        max_chapters=max_chapters,
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item created: {data['queue_id']} (status: {data['status']})")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_run(args) -> None:
    """Execute the next pending queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    llm_mode = _get_effective_llm_mode(args)

    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    result = dispatcher.run_queue_once()

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            if data.get("status") == "idle":
                print(data.get("message", "No pending queue items"))
            else:
                print(f"Queue item completed: {data.get('queue_id')}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_status(args) -> None:
    """Get production queue status."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_queue_status(
        project_id=getattr(args, "project_id", None),
        status=getattr(args, "status", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            items = result["data"].get("items", [])
            if not items:
                print("No queue items found.")
            else:
                for item in items:
                    print(
                        f"  [{item['status']}] {item['queue_id']} "
                        f"project={item['project_id']} "
                        f"ch={item['from_chapter']}-{item['to_chapter']} "
                        f"priority={item['priority']} "
                        f"attempts={item['attempt_count']}/{item['max_attempts']}"
                    )
                    if item.get("last_error"):
                        print(f"    error: {item['last_error']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_pause(args) -> None:
    """Pause a production queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.pause_queue_item(args.queue_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item paused: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_resume(args) -> None:
    """Resume a paused queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.resume_queue_item(args.queue_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item resumed: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_retry(args) -> None:
    """Retry a failed or timed-out queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.retry_queue_item(args.queue_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item retried: {data['queue_id']} (attempt {data['attempt_count']})")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_timeouts(args) -> None:
    """Mark timed-out queue items."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.mark_queue_timeouts()

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            count = result["data"].get("timed_out_count", 0)
            print(f"Timed-out items marked: {count}")
        else:
            print(f"Error: {result.get('error')}")


# ── v3.5 Queue Runtime Hardening commands ───────────────────────────


def cmd_batch_queue_events(args) -> None:
    """View queue item audit events."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_queue_events(args.queue_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item: {data['queue_id']}")
            print(f"Events ({len(data['events'])}):")
            for event in data["events"]:
                print(f"  [{event['event_type']}] {event['from_status'] or '-'} → {event['to_status'] or '-'}")
                if event.get("message"):
                    print(f"    {event['message']}")
                print(f"    at {event['created_at']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_cancel(args) -> None:
    """Cancel a queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.cancel_queue_item(
        queue_id=args.queue_id,
        reason=getattr(args, "reason", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item cancelled: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_recover(args) -> None:
    """Recover a stuck running queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.recover_queue_item(
        queue_id=args.queue_id,
        force=getattr(args, "force", False),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item recovered: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_doctor(args) -> None:
    """Diagnose a queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.doctor_queue_item(args.queue_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item: {data['queue_id']}")
            print(f"Status: {data['status']}")
            print(f"Production run: {data.get('production_run_id') or 'N/A'}")
            print(f"\nChecks:")
            for check in data["checks"]:
                status = "✓" if check["pass"] else "✗"
                msg = check.get("message", "")
                print(f"  {status} {check['name']}: {msg or ('pass' if check['pass'] else 'fail')}")
            if data.get("recent_error"):
                print(f"\nRecent error: {data['recent_error']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_run_limit(args) -> None:
    """Execute multiple queue items."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    llm_mode = _get_effective_llm_mode(args)

    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    # Handle --once as --limit 1
    limit = getattr(args, "limit", 1)
    if getattr(args, "once", False):
        limit = 1

    result = dispatcher.run_queue(limit=limit)

    use_json = getattr(args, "json", False)

    # v3.4 backward compatibility: when limit=1 and stopped_reason=idle,
    # return the old format {"status": "idle"} instead of the new format
    is_v34_compat = (
        limit == 1
        and result.get("ok")
        and result.get("data", {}).get("stopped_reason") == "idle"
    )
    if is_v34_compat:
        runs = result.get("data", {}).get("runs", [])
        if runs and runs[0].get("ok"):
            v34_result = runs[0]  # The original run_queue_once result
        else:
            v34_result = result

    if use_json:
        if is_v34_compat:
            print(json.dumps(v34_result, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            if data.get("stopped_reason") == "idle" and data.get("executed", 0) == 0:
                print("No pending queue items")
            else:
                print(f"Executed {data['executed']}/{data['limit']} queue items")
                if data.get("stopped_reason"):
                    print(f"Stopped: {data['stopped_reason']}")
                for i, run in enumerate(data.get("runs", []), 1):
                    if run.get("ok"):
                        run_data = run.get("data", {})
                        if run_data.get("status") == "idle":
                            print(f"  Run {i}: idle")
                        else:
                            print(f"  Run {i}: {run_data.get('queue_id')} → {run_data.get('status')}")
                    else:
                        print(f"  Run {i}: failed - {run.get('error')}")
        else:
            print(f"Error: {result.get('error')}")
