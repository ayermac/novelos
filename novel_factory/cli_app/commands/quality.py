"""Quality CLI commands: check, report."""

from __future__ import annotations

import json
import sys

from ..common import (
    _get_settings,
    init_db,
    Repository,
)


def cmd_quality_check(args) -> None:
    """Run quality check on a chapter."""
    from ...quality.hub import QualityHub
    from ...skills.registry import SkillRegistry

    settings = _get_settings(args)
    init_db(settings.db_path)

    project_id = getattr(args, "project_id", "")
    chapter = getattr(args, "chapter", 1)
    stage = getattr(args, "stage", "draft")

    try:
        repo = Repository(settings.db_path)
        skill_registry = SkillRegistry()  # Use default config path
        hub = QualityHub(repo, skill_registry)

        # Get chapter content
        chapter_data = repo.get_chapter(project_id, chapter)
        if not chapter_data:
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "error": f"Chapter not found: {project_id}/{chapter}", "data": {}}, ensure_ascii=False))
            else:
                print(f"Error: Chapter not found: {project_id}/{chapter}")
            sys.exit(1)

        content = chapter_data.get("content")

        # R1: Handle empty content or planned chapters
        if content is None:
            content = ""

        # Run quality check based on stage
        if stage == "draft":
            result = hub.check_draft(project_id, chapter, content)
        elif stage == "polished":
            # Get original draft for comparison
            versions = repo.get_chapter_versions(project_id, chapter)
            original = versions[0].get("content") if versions else content
            if original is None:
                original = ""
            result = hub.check_polished(project_id, chapter, original, content)
        else:  # final
            result = hub.final_gate(project_id, chapter)

        # Save quality report
        if result.get("ok"):
            data = result.get("data", {})
            repo.save_quality_report(
                project_id=project_id,
                chapter_number=chapter,
                stage=stage,
                overall_score=data.get("overall_score", 0),
                pass_=data.get("pass", False),
                revision_target=data.get("revision_target"),
                blocking_issues=data.get("blocking_issues", []),
                warnings=data.get("warnings", []),
                skill_results=data.get("skill_results", []),
                quality_dimensions=data.get("quality_dimensions", {}),
            )

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result.get("ok"):
                data = result.get("data", {})
                status = "PASSED" if data.get("pass") else "FAILED"
                print(f"Quality Check ({stage}): {status}")
                print(f"  Overall Score: {data.get('overall_score', 0):.2f}")
                print(f"  Revision Target: {data.get('revision_target', 'N/A')}")

                if data.get("blocking_issues"):
                    print("\n  Blocking Issues:")
                    for issue in data.get("blocking_issues", []):
                        print(f"    - {issue.get('type')}: {issue.get('message')}")

                if data.get("warnings"):
                    print("\n  Warnings:")
                    for warning in data.get("warnings", []):
                        print(f"    - {warning}")
            else:
                print(f"Error: {result.get('error')}")
                sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_quality_report(args) -> None:
    """Show quality reports for a chapter."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    project_id = getattr(args, "project_id", "")
    chapter = getattr(args, "chapter", 1)
    limit = getattr(args, "limit", 5)

    try:
        repo = Repository(settings.db_path)
        reports = repo.get_quality_reports(project_id, chapter, limit=limit)

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"reports": reports}}, ensure_ascii=False, indent=2))
        else:
            print(f"Quality Reports for {project_id}/{chapter}:")
            if not reports:
                print("  No reports found.")
            else:
                for i, report in enumerate(reports, 1):
                    status = "PASSED" if report.get("pass") else "FAILED"
                    print(f"\n  Report {i}:")
                    print(f"    Stage: {report.get('stage', 'N/A')}")
                    print(f"    Status: {status}")
                    print(f"    Score: {report.get('overall_score', 0):.2f}")
                    print(f"    Created: {report.get('created_at', 'N/A')}")

                    if report.get("blocking_issues"):
                        print(f"    Blocking Issues: {len(report.get('blocking_issues', []))}")
                    if report.get("warnings"):
                        print(f"    Warnings: {len(report.get('warnings', []))}")
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)
