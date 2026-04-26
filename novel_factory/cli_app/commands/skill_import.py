"""v3.8 Skill Import CLI commands: import-plan, import-apply, import-validate."""

from __future__ import annotations

import json
import sys


def cmd_skill_import_plan(args) -> None:
    """Generate an import plan for an external skill directory."""
    from ...skills.import_bridge import build_import_plan

    source = getattr(args, "source", None)
    if not source:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": "--source is required", "data": {}}, ensure_ascii=False))
        else:
            print("Error: --source is required")
            sys.exit(1)
        return

    try:
        result = build_import_plan(source)

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result["ok"]:
                data = result["data"]
                detected = data.get("detected", {})
                target = data.get("target", {})
                warnings = data.get("warnings", [])
                print(f"Import Plan for: {data.get('source')}")
                print(f"  Name: {detected.get('name')}")
                print(f"  Description: {detected.get('description')}")
                print(f"  Mode: {target.get('import_mode')}")
                print(f"  Target ID: {target.get('skill_id')}")
                print(f"  Kind: {target.get('kind')}")
                print(f"  Has scripts: {detected.get('has_scripts')}")
                print(f"  Has prompts: {detected.get('has_prompts')}")
                print(f"  Has references: {detected.get('has_references')}")
                print(f"  Has rules: {detected.get('has_rules')}")
                if warnings:
                    print("  Warnings:")
                    for w in warnings:
                        print(f"    - {w}")
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


def cmd_skill_import_apply(args) -> None:
    """Apply an import plan, generating the skill package."""
    from ...skills.import_bridge import apply_import_plan

    source = getattr(args, "source", None)
    skill_id = getattr(args, "skill_id", None)
    force = getattr(args, "force", False)

    if not source:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": "--source is required", "data": {}}, ensure_ascii=False))
        else:
            print("Error: --source is required")
            sys.exit(1)
        return

    if not skill_id:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": "--skill-id is required", "data": {}}, ensure_ascii=False))
        else:
            print("Error: --skill-id is required")
            sys.exit(1)
        return

    try:
        result = apply_import_plan(source, skill_id, force=force)

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result["ok"]:
                data = result["data"]
                print(f"Imported skill: {data.get('skill_id')}")
                print(f"  Package dir: {data.get('package_dir')}")
                print(f"  Generated files:")
                for f in data.get("generated_files", []):
                    print(f"    - {f}")
                for w in data.get("warnings", []):
                    print(f"  WARNING: {w}")
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


def cmd_skill_import_validate(args) -> None:
    """Validate an imported skill package."""
    from ...skills.import_bridge import validate_imported_package

    skill_id = getattr(args, "skill_id", None)
    if not skill_id:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": "--skill-id is required", "data": {}}, ensure_ascii=False))
        else:
            print("Error: --skill-id is required")
            sys.exit(1)
        return

    try:
        result = validate_imported_package(skill_id)

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result["ok"]:
                data = result["data"]
                print(f"Validation passed for: {data.get('skill_id')}")
                for w in data.get("warnings", []):
                    print(f"  WARNING: {w}")
            else:
                data = result["data"]
                print(f"Validation failed for: {data.get('skill_id')}")
                for e in data.get("errors", []):
                    print(f"  ERROR: {e}")
                for w in data.get("warnings", []):
                    print(f"  WARNING: {w}")
                sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)
