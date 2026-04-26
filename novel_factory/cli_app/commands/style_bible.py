"""v4.0 Style Bible CLI commands.

Provides:
- style templates: List available style bible templates
- style init: Create a style bible from a template
- style show: Show style bible for a project
- style update: Update style bible fields
- style check: Check chapter text against style bible
- style delete: Delete style bible for a project
"""

from __future__ import annotations

import json
import sys
from typing import Any

from ..output import print_error_and_exit, print_json_envelope


def cmd_style_templates(args) -> None:
    """List available Style Bible templates."""
    from ...style_bible.templates import list_templates

    use_json = getattr(args, "json", False)

    try:
        templates = list_templates()
        data = []
        for tid, tdata in templates.items():
            data.append({
                "id": tid,
                "name": tdata.get("name", ""),
                "description": tdata.get("description", ""),
                "genre": tdata.get("genre", ""),
                "target_platform": tdata.get("target_platform", ""),
            })
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"templates": data, "total": len(data)}}, ensure_ascii=False, indent=2))
        else:
            print(f"Style Bible Templates ({len(data)}):")
            print()
            for t in data:
                print(f"  [{t['id']}] {t['name']}")
                print(f"    {t['description']}")
                print(f"    genre: {t['genre']}, platform: {t['target_platform']}")
                print()
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_init(args) -> None:
    """Initialize a Style Bible from a template."""
    from ...style_bible.templates import create_style_bible_from_template, validate_style_bible
    from ...db.repository import Repository
    from ...db.connection import init_db, get_connection
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")
    template_id = getattr(args, "template", "default_web_serial")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        # Check if already exists
        existing = repo.get_style_bible(project_id)
        if existing:
            print_error_and_exit(
                f"Style Bible already exists for project '{project_id}'. Use 'style update' instead.",
                use_json,
            )
            return

        # Check if project exists; require --create-project for auto-creation
        conn = get_connection(settings.db_path)
        try:
            row = conn.execute(
                "SELECT project_id FROM projects WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if not row:
                create_project = getattr(args, "create_project", False)
                if not create_project:
                    print_error_and_exit(
                        f"Project '{project_id}' does not exist. "
                        "Use --create-project to auto-create it, or run 'seed-demo' first.",
                        use_json,
                    )
                    return
                conn.execute(
                    "INSERT INTO projects (project_id, name) VALUES (?, ?)",
                    (project_id, f"{project_id} Project"),
                )
                conn.commit()
        finally:
            conn.close()

        # Parse overrides from --set
        overrides = _parse_set_args(getattr(args, "set", None))

        bible = create_style_bible_from_template(project_id, template_id, overrides)

        # Validate
        validation = validate_style_bible(bible)
        if not validation["ok"]:
            print_error_and_exit(f"Style Bible validation failed: {validation['error']}", use_json)
            return

        # Save
        bible_id = repo.save_style_bible(project_id, bible.to_storage_dict())

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {
                    "bible_id": bible_id,
                    "project_id": project_id,
                    "template": template_id,
                    "name": bible.name,
                },
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Bible created for project '{project_id}'")
            print(f"  Template: {template_id}")
            print(f"  Name: {bible.name}")
            print(f"  ID: {bible_id}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_show(args) -> None:
    """Show Style Bible for a project."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        record = repo.get_style_bible(project_id)
        if not record:
            print_error_and_exit(f"No Style Bible found for project '{project_id}'", use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": record["bible"],
            }, ensure_ascii=False, indent=2))
        else:
            bible = record["bible"]
            print(f"Style Bible: {bible.get('name', 'N/A')}")
            print(f"  Project: {project_id}")
            print(f"  Genre: {bible.get('genre', 'N/A')}")
            print(f"  Platform: {bible.get('target_platform', 'N/A')}")
            print(f"  Pacing: {bible.get('pacing', 'N/A')}")
            print(f"  POV: {bible.get('pov', 'N/A')}")
            if bible.get("tone_keywords"):
                print(f"  Tone: {', '.join(bible['tone_keywords'])}")
            if bible.get("forbidden_expressions"):
                print(f"  Forbidden: {len(bible['forbidden_expressions'])} patterns")
            if bible.get("preferred_expressions"):
                print(f"  Preferred: {len(bible['preferred_expressions'])} patterns")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_update(args) -> None:
    """Update Style Bible fields."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ...models.style_bible import StyleBible
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        record = repo.get_style_bible(project_id)
        if not record:
            print_error_and_exit(f"No Style Bible found for project '{project_id}'", use_json)
            return

        bible_data = record["bible"]

        # Parse overrides from --set
        overrides = _parse_set_args(getattr(args, "set", None))
        if not overrides:
            print_error_and_exit("No updates provided. Use --set key=value", use_json)
            return

        # Merge
        from ...style_bible.templates import merge_style_bible
        bible_data = merge_style_bible(bible_data, overrides)

        # Validate
        bible = StyleBible.from_storage_dict(bible_data)

        # Save
        ok = repo.update_style_bible(project_id, bible.to_storage_dict())
        if not ok:
            print_error_and_exit(f"Failed to update Style Bible for project '{project_id}'", use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {"project_id": project_id, "updated_fields": list(overrides.keys())},
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Bible updated for project '{project_id}'")
            print(f"  Updated fields: {', '.join(overrides.keys())}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_check(args) -> None:
    """Check chapter text against Style Bible."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ...skills.style_bible_checker import StyleBibleCheckerSkill
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")
    chapter_num = getattr(args, "chapter", None)

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    if chapter_num is None:
        print_error_and_exit("--chapter is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        # Get Style Bible
        record = repo.get_style_bible(project_id)
        if not record:
            print_error_and_exit(f"No Style Bible found for project '{project_id}'", use_json)
            return

        bible_data = record["bible"]

        # Get chapter content
        chapter = repo.get_chapter(project_id, chapter_num)
        if not chapter:
            print_error_and_exit(f"Chapter {chapter_num} not found for project '{project_id}'", use_json)
            return

        content = chapter.get("content") or ""
        if not content:
            print_error_and_exit(f"Chapter {chapter_num} has no content", use_json)
            return

        # Run check
        checker = StyleBibleCheckerSkill()
        result = checker.run({"text": content, "style_bible": bible_data})

        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            data = result.get("data", {})
            print(f"Style Check for {project_id}/ch{chapter_num}:")
            print(f"  Score: {data.get('score', 0):.1f}/100")
            print(f"  Issues: {data.get('total_issues', 0)} ({data.get('blocking_issues', 0)} blocking, {data.get('warning_issues', 0)} warning)")
            for issue in data.get("issues", []):
                severity = issue.get("severity", "warning").upper()
                print(f"    [{severity}] {issue.get('rule_type')}: {issue.get('description')}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_delete(args) -> None:
    """Delete Style Bible for a project."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        ok = repo.delete_style_bible(project_id)
        if not ok:
            print_error_and_exit(f"No Style Bible found for project '{project_id}'", use_json)
            return

        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"project_id": project_id, "deleted": True}}, ensure_ascii=False, indent=2))
        else:
            print(f"Style Bible deleted for project '{project_id}'")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


# ── Helpers ────────────────────────────────────────────────────


def _parse_set_args(set_values: list[str] | str | None) -> dict[str, Any]:
    """Parse --set key=value arguments into a dict."""
    if not set_values:
        return {}

    if isinstance(set_values, str):
        set_values = [set_values]

    result: dict[str, Any] = {}
    for item in set_values:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Try to parse as JSON, fall back to string
        try:
            result[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            # Handle comma-separated lists
            if "," in value:
                result[key] = [v.strip() for v in value.split(",")]
            else:
                result[key] = value

    return result
