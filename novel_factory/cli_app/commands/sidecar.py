"""Sidecar CLI commands for optional diagnostic agents."""

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
