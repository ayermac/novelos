"""Skills CLI commands: list, run, show, validate, test."""

from __future__ import annotations

import json
import sys

from ..common import (
    _get_settings,
    init_db,
)


def cmd_skill_list(args) -> None:
    """List available skills."""
    from ...skills.registry import SkillRegistry

    settings = _get_settings(args)

    try:
        registry = SkillRegistry()  # Use default config path
        skills = registry.list_skills()

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"skills": skills}}, ensure_ascii=False, indent=2))
        else:
            print("Available Skills:")
            for skill in skills:
                status = "enabled" if skill.get("enabled") else "disabled"
                print(f"  - {skill.get('id')}: {skill.get('type')} ({status})")
                print(f"      Class: {skill.get('class')}")
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_skill_run(args) -> None:
    """Run a skill."""
    from ...skills.registry import SkillRegistry

    settings = _get_settings(args)
    init_db(settings.db_path)

    skill_id = getattr(args, "skill_id", "")
    text = getattr(args, "text", None)
    project_id = getattr(args, "project_id", None)
    chapter = getattr(args, "chapter", None)
    input_json_str = getattr(args, "input_json", None)

    # Build payload
    payload = {}

    # Priority: --input-json > --text
    if input_json_str:
        try:
            payload = json.loads(input_json_str)
        except json.JSONDecodeError as e:
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "error": f"Invalid JSON input: {e}", "data": {}}, ensure_ascii=False))
            else:
                print(f"Error: Invalid JSON input: {e}")
            sys.exit(1)
    elif text:
        payload["text"] = text

    # Add project_id and chapter to payload if provided
    if project_id:
        payload["project_id"] = project_id
    if chapter:
        payload["chapter_number"] = chapter

    try:
        registry = SkillRegistry()  # Use default config path
        # v2.2: Use run_skill with agent="manual" and stage="manual"
        result = registry.run_skill(skill_id, payload, agent="manual", stage="manual")

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result.get("ok"):
                print(f"Skill '{skill_id}' executed successfully.")
                data = result.get("data", {})
                print(json.dumps(data, ensure_ascii=False, indent=2))
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


def cmd_skill_show(args) -> None:
    """Show skill manifest details (v2.2)."""
    from ...skills.registry import SkillRegistry

    settings = _get_settings(args)

    skill_id = getattr(args, "skill_id", "")

    try:
        registry = SkillRegistry()
        manifest = registry.get_manifest(skill_id)

        if not manifest:
            # No manifest, show v2.1 compatibility info
            skill_config = registry.skills_config.get(skill_id)
            if not skill_config:
                use_json = getattr(args, "json", False)
                if use_json:
                    print(json.dumps({"ok": False, "error": f"Skill not found: {skill_id}", "data": {}}, ensure_ascii=False))
                else:
                    print(f"Error: Skill not found: {skill_id}")
                sys.exit(1)

            # Show v2.1 info
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({
                    "ok": True,
                    "error": None,
                    "data": {
                        "id": skill_id,
                        "type": skill_config.get("type"),
                        "enabled": skill_config.get("enabled", True),
                        "class": skill_config.get("class"),
                        "description": skill_config.get("description", ""),
                        "manifest": None,
                    }
                }, ensure_ascii=False, indent=2))
            else:
                print(f"Skill: {skill_id}")
                print(f"  Type: {skill_config.get('type')}")
                print(f"  Enabled: {skill_config.get('enabled', True)}")
                print(f"  Class: {skill_config.get('class')}")
                print(f"  Description: {skill_config.get('description', '')}")
                print("  Manifest: None (v2.1 compatibility)")
            return

        # Show manifest info
        use_json = getattr(args, "json", False)
        if use_json:
            # Get skill config for package info
            skill_config = registry.skills_config.get(skill_id, {})
            manifest_dict = manifest.model_dump()

            # Add package field from skills.yaml
            if skill_config.get("package"):
                manifest_dict["package"] = skill_config["package"]

            print(json.dumps({
                "ok": True,
                "error": None,
                "data": manifest_dict
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Skill: {manifest.id}")
            print(f"  Name: {manifest.name}")
            print(f"  Version: {manifest.version}")
            print(f"  Kind: {manifest.kind}")
            print(f"  Description: {manifest.description}")
            print(f"  Enabled: {manifest.enabled}")
            print(f"  Builtin: {manifest.builtin}")
            print(f"  Class: {manifest.class_name}")
            print(f"  Allowed Agents: {', '.join(manifest.allowed_agents)}")
            print(f"  Allowed Stages: {', '.join(manifest.allowed_stages)}")
            print(f"  Permissions:")
            print(f"    transform_text: {manifest.permissions.transform_text}")
            print(f"    validate_text: {manifest.permissions.validate_text}")
            print(f"    write_skill_run: {manifest.permissions.write_skill_run}")
            print(f"  Failure Policy:")
            print(f"    on_error: {manifest.failure_policy.on_error}")
            print(f"    max_retries: {manifest.failure_policy.max_retries}")
            if manifest.package:
                print(f"  Package:")
                print(f"    name: {manifest.package.name}")
                print(f"    handler: {manifest.package.handler}")
                print(f"    entry_class: {manifest.package.entry_class}")
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_skill_validate(args) -> None:
    """Validate all skill manifests (v2.2)."""
    from ...skills.registry import SkillRegistry

    settings = _get_settings(args)

    try:
        registry = SkillRegistry()
        result = registry.validate_all()

        use_json = getattr(args, "json", False)
        if use_json:
            # Wrap in envelope format
            envelope = {
                "ok": result.get("ok", False),
                "error": None if result.get("ok") else "; ".join(result.get("errors", [])),
                "data": {
                    "errors": result.get("errors", []),
                    "warnings": result.get("warnings", [])
                }
            }
            print(json.dumps(envelope, ensure_ascii=False, indent=2))
        else:
            if result["ok"]:
                print("All skill manifests are valid.")
                if result["warnings"]:
                    print("\nWarnings:")
                    for warning in result["warnings"]:
                        print(f"  - {warning}")
            else:
                print("Skill manifest validation failed.")
                print("\nErrors:")
                for error in result["errors"]:
                    print(f"  - {error}")
                if result["warnings"]:
                    print("\nWarnings:")
                    for warning in result["warnings"]:
                        print(f"  - {warning}")
                sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_skill_test(args) -> None:
    """Run skill fixtures test (v2.3)."""
    from ...skills.registry import SkillRegistry

    settings = _get_settings(args)

    skill_id = getattr(args, "skill_id", None)
    test_all = getattr(args, "all", False)

    try:
        registry = SkillRegistry()

        if test_all:
            # Test all skills with packages
            skills = registry.list_skills()
            package_skills = [s for s in skills if s.get("package")]

            if not package_skills:
                print("No skills with packages found.")
                return

            all_results = {}
            total_passed = 0
            total_failed = 0

            for skill_info in package_skills:
                skill_id = skill_info["id"]
                result = registry.test_skill(skill_id)
                all_results[skill_id] = result

                if result.get("ok"):
                    total_passed += 1
                else:
                    total_failed += 1

            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({
                    "ok": total_failed == 0,
                    "error": None if total_failed == 0 else f"{total_failed}/{len(package_skills)} skills failed",
                    "data": {
                        "passed": total_passed,
                        "failed": total_failed,
                        "total": len(package_skills),
                        "results": all_results,
                    }
                }, ensure_ascii=False, indent=2))
            else:
                print(f"Test Results: {total_passed}/{len(package_skills)} passed")
                print()
                for skill_id, result in all_results.items():
                    data = result.get("data", {})
                    passed = data.get("passed", 0)
                    total = data.get("total", 0)
                    status = "✓" if result.get("ok") else "✗"
                    print(f"  {status} {skill_id}: {passed}/{total} cases passed")

                if total_failed > 0:
                    sys.exit(1)
        else:
            # Test single skill
            if not skill_id:
                use_json = getattr(args, "json", False)
                if use_json:
                    print(json.dumps({
                        "ok": False,
                        "error": "skill_id is required (or use --all)",
                        "data": {}
                    }, ensure_ascii=False))
                else:
                    print("Error: skill_id is required (or use --all)")
                sys.exit(1)

            result = registry.test_skill(skill_id)

            use_json = getattr(args, "json", False)
            if use_json:
                # Ensure envelope format: {ok, error, data}
                # Ensure data is always a dict, never null
                data = result.get("data")
                if data is None:
                    data = {}

                envelope = {
                    "ok": result.get("ok", False),
                    "error": result.get("error") if not result.get("ok") else None,
                    "data": data
                }
                print(json.dumps(envelope, ensure_ascii=False, indent=2))
            else:
                data = result.get("data", {})
                passed = data.get("passed", 0)
                failed = data.get("failed", 0)
                total = data.get("total", 0)

                if result.get("ok"):
                    print(f"✓ All {total} test cases passed for skill '{skill_id}'")
                else:
                    print(f"✗ {failed}/{total} test cases failed for skill '{skill_id}'")
                    print()
                    print("Failed cases:")
                    for case in data.get("cases", []):
                        if not case.get("passed"):
                            print(f"  - {case.get('name')}")
                            if case.get("result", {}).get("error"):
                                print(f"    Error: {case['result']['error']}")
                    sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)
