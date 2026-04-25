"""Sidecar CLI commands: scout, report daily, export chapter, continuity-check, architect suggest."""

from __future__ import annotations

import json
import sys

from ..common import (
    _get_settings,
    _get_effective_llm_mode,
    _build_dispatcher,
    init_db,
    Repository,
)
from ..output import _print_output, print_llm_runtime_error


def cmd_scout(args) -> None:
    """Generate market report using Scout agent."""
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
        result = dispatcher.run_scout(
            project_id=args.project_id,
            topic=getattr(args, "topic", None),
            genre=getattr(args, "genre", None),
            platform=getattr(args, "platform", None),
            audience=getattr(args, "audience", None),
        )
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = result.get("market_report", {})
        print(f"Market Report (ID: {result.get('report_id')})")
        print(f"Genre: {report.get('genre', 'N/A')}")
        print(f"\nSummary: {report.get('summary', 'N/A')}")
        print(f"\nTrends:")
        for trend in report.get("trends", []):
            print(f"  - {trend}")
        print(f"\nOpportunities:")
        for opp in report.get("opportunities", []):
            print(f"  - {opp}")
        print(f"\nRecommendations:")
        for rec in report.get("recommendations", []):
            print(f"  - {rec}")


def cmd_report_daily(args) -> None:
    """Generate daily report using Secretary agent."""
    from ...agents.secretary import SecretaryAgent

    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    secretary = SecretaryAgent(repo)

    result = secretary.generate_daily_report(
        project_id=args.project_id,
        date=getattr(args, "date", None),
    )

    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = result.get("report", {})
        print(f"Daily Report - {report.get('date', 'N/A')}")
        print(f"Project: {report.get('project_id', 'N/A')}")
        print(f"\nTotal runs: {report.get('total_runs', 0)}")
        print(f"Successful: {report.get('successful_runs', 0)}")
        print(f"Failed: {report.get('failed_runs', 0)}")
        print(f"\nChapter Status Distribution:")
        for status, count in sorted(report.get("chapter_status_distribution", {}).items()):
            print(f"  - {status}: {count}")
        if report.get("recent_errors"):
            print(f"\nRecent Errors:")
            for error in report["recent_errors"][:5]:
                print(f"  - {error[:100]}")


def cmd_export_chapter(args) -> None:
    """Export chapter using Secretary agent."""
    from ...agents.secretary import SecretaryAgent

    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    secretary = SecretaryAgent(repo)

    result = secretary.export_chapter(
        project_id=args.project_id,
        chapter_number=args.chapter,
        export_format=getattr(args, "format", "markdown"),
    )

    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Print the formatted output
        data = result.get("data", {})
        output = data.get("output", "")
        print(output)


def cmd_continuity_check(args) -> None:
    """Check cross-chapter continuity using ContinuityChecker agent."""
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
        result = dispatcher.run_continuity_check(
            project_id=args.project_id,
            from_chapter=args.from_chapter,
            to_chapter=args.to_chapter,
        )
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = result.get("report", {})
        print(f"Continuity Report (ID: {result.get('report_id')})")
        print(f"Chapters: {report.get('from_chapter')}-{report.get('to_chapter')}")
        print(f"\nSummary: {report.get('summary', 'N/A')}")
        print(f"\nConsistency Checks:")
        print(f"  State Card: {'✓' if report.get('state_card_consistency') else '✗'}")
        print(f"  Character: {'✓' if report.get('character_consistency') else '✗'}")
        print(f"  Plot: {'✓' if report.get('plot_consistency') else '✗'}")

        issues = report.get("issues", [])
        if issues:
            print(f"\nIssues ({len(issues)}):")
            for issue in issues[:10]:
                print(f"  [{issue.get('severity', 'info').upper()}] {issue.get('issue_type')}: {issue.get('description')}")


def cmd_architect_suggest(args) -> None:
    """Generate architecture improvement proposals."""
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
        result = dispatcher.run_architect_suggest(
            project_id=args.project_id,
            scope=getattr(args, "scope", "quality"),
        )
    except Exception as e:
        print_llm_runtime_error(e, getattr(args, "json", False))

    use_json = getattr(args, "json", False)

    # v3.1: run_architect_suggest already returns {ok, error, data} format
    # Check for LLM configuration errors (distinguished by ok=false and specific error messages)
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
            print(f"Error: {error_msg}")
        sys.exit(1)
    else:
        # Normal result
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            data = result.get("data", {})
            print(f"Architecture Proposals for {args.project_id}:")
            print(f"  Scope: {data.get('scope', 'N/A')}")
            print(f"  Proposals: {len(data.get('proposals', []))}")
            for i, proposal in enumerate(data.get("proposals", [])[:5], 1):
                print(f"\n  Proposal {i}:")
                print(f"    Title: {proposal.get('title', 'N/A')}")
                print(f"    Risk: {proposal.get('risk_level', 'N/A')}")
                print(f"    Recommendation: {proposal.get('recommendation', 'N/A')[:100]}...")
