"""Serial CLI commands: create, status, enqueue-next, advance, pause, resume, cancel."""

from __future__ import annotations

import json
import sys

from ..common import (
    _get_settings,
    _StubLLM,
    init_db,
    Repository,
    Dispatcher,
)


def cmd_serial_create(args) -> None:
    """Create a new serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.create_serial_plan(
        project_id=args.project_id,
        name=args.name,
        start_chapter=args.start_chapter,
        target_chapter=args.target_chapter,
        batch_size=args.batch_size,
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Serial plan created: {data['serial_plan_id']}")
            print(f"Status: {data['status']}")
            print(f"Current chapter: {data['current_chapter']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_status(args) -> None:
    """Get serial plan status."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_serial_status(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Serial plan: {data['serial_plan_id']}")
            print(f"Project: {data['project_id']}")
            print(f"Name: {data['name']}")
            print(f"Status: {data['status']}")
            print(f"Progress: {data['current_chapter']}/{data['target_chapter']}")
            print(f"Batch size: {data['batch_size']}")
            print(f"Completed chapters: {data['completed_chapters']}")
            if data.get("current_queue_id"):
                print(f"Current queue: {data['current_queue_id']}")
            if data.get("current_production_run_id"):
                print(f"Current production run: {data['current_production_run_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_enqueue_next(args) -> None:
    """Enqueue next batch for serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.enqueue_serial_next(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Enqueued chapters {data['from_chapter']}-{data['to_chapter']}")
            print(f"Queue ID: {data['queue_id']}")
            print(f"Status: {data['status']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_advance(args) -> None:
    """Advance serial plan with decision."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.advance_serial_plan(
        serial_plan_id=args.serial_plan_id,
        decision=args.decision,
        notes=getattr(args, "notes", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Decision: {args.decision}")
            print(f"Status: {data['status']}")
            if "current_chapter" in data:
                print(f"Current chapter: {data['current_chapter']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_pause(args) -> None:
    """Pause a serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.pause_serial_plan(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Serial plan paused: {args.serial_plan_id}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_resume(args) -> None:
    """Resume a paused serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.resume_serial_plan(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Serial plan resumed: {args.serial_plan_id}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_cancel(args) -> None:
    """Cancel a serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.cancel_serial_plan(
        serial_plan_id=args.serial_plan_id,
        reason=getattr(args, "reason", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Serial plan cancelled: {args.serial_plan_id}")
        else:
            print(f"Error: {result.get('error')}")
