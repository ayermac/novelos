"""Review workbench CLI commands: pack, chapter, timeline, diff, export."""

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


def cmd_review_pack(args) -> None:
    """Build a review pack."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.build_review_pack(
        run_id=getattr(args, "run_id", None),
        serial_plan_id=getattr(args, "serial_plan_id", None),
        project_id=getattr(args, "project_id", None),
        from_chapter=getattr(args, "from_chapter", None),
        to_chapter=getattr(args, "to_chapter", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            scope = data.get("scope", {})
            hint = data.get("decision_hint", {})

            print(f"Review Pack: {scope.get('project_id')} chapters {scope.get('from_chapter')}-{scope.get('to_chapter')}")
            print(f"Can approve: {'yes' if hint.get('can_approve') else 'no'}")

            blocking = hint.get("blocking_reasons", [])
            if blocking:
                print("Blocking reasons:")
                for reason in blocking:
                    print(f"  - {reason}")

            warnings = hint.get("warnings", [])
            if warnings:
                print("Warnings:")
                for warning in warnings:
                    print(f"  - {warning}")

            chapters = data.get("chapters", [])
            if chapters:
                print(f"\nChapters: {len(chapters)}")
                for ch in chapters[:5]:  # Show first 5
                    print(f"  Ch {ch.get('chapter')}: {ch.get('status')} - {ch.get('word_count')} words")
                if len(chapters) > 5:
                    print(f"  ... and {len(chapters) - 5} more")
        else:
            print(f"Error: {result.get('error')}")


def cmd_review_chapter(args) -> None:
    """Get review view for a single chapter."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_review_chapter(
        project_id=args.project_id,
        chapter=args.chapter,
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            chapter = data.get("chapter", {})

            print(f"Chapter {args.chapter} - {chapter.get('status')}")
            print(f"Word count: {data.get('word_count', 0)}")

            if data.get("content_preview"):
                print(f"\nPreview:\n{data['content_preview'][:400]}...")

            if data.get("latest_review"):
                review = data["latest_review"]
                print(f"\nLatest review: score {review.get('score', 0)}, {'passed' if review.get('passed') else 'failed'}")

            if data.get("latest_quality"):
                quality = data["latest_quality"]
                print(f"Latest quality: score {quality.get('score', 0)}, {'pass' if quality.get('pass') else 'fail'}")

            if data.get("notes_count", 0) > 0:
                print(f"Review notes: {data['notes_count']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_review_timeline(args) -> None:
    """Get timeline events."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_review_timeline(
        run_id=getattr(args, "run_id", None),
        serial_plan_id=getattr(args, "serial_plan_id", None),
        queue_id=getattr(args, "queue_id", None),
        project_id=getattr(args, "project_id", None),
        chapter=getattr(args, "chapter", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            events = result["data"].get("events", [])
            print(f"Timeline ({len(events)} events):")
            for event in events:
                time = event.get("time", "?")
                source = event.get("source", "?")
                event_type = event.get("type", "?")
                message = event.get("message", "")
                print(f"  {time} [{source}] {event_type}: {message}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_review_diff(args) -> None:
    """Get diff between chapter versions."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_review_diff(
        project_id=args.project_id,
        chapter=args.chapter,
        from_version=getattr(args, "from_version", None),
        to_version=getattr(args, "to_version", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Diff: version {data.get('from_version_number')} → {data.get('to_version_number')}")
            print(f"Word count delta: {data.get('word_count_delta', 0):+d}")
            print(f"Changed ratio: {data.get('changed_ratio', 0):.1%}")

            if data.get("added_preview"):
                print(f"\nAdded:\n{data['added_preview'][:200]}...")

            if data.get("removed_preview"):
                print(f"\nRemoved:\n{data['removed_preview'][:200]}...")
        else:
            print(f"Error: {result.get('error')}")


def cmd_review_export(args) -> None:
    """Export review pack to file."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.export_review_pack(
        run_id=getattr(args, "run_id", None),
        serial_plan_id=getattr(args, "serial_plan_id", None),
        project_id=getattr(args, "project_id", None),
        from_chapter=getattr(args, "from_chapter", None),
        to_chapter=getattr(args, "to_chapter", None),
        format=getattr(args, "format", "json"),
        output=args.output,
        force=getattr(args, "force", False),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Exported to: {result['data'].get('output')}")
        else:
            print(f"Error: {result.get('error')}")
