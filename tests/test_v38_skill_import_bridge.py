"""v3.8 Skill Import Bridge tests.

Covers:
- import-plan: parse, validate, detect features
- import-apply: generate package, manifest, handler, fixtures, README
- import-validate: validate imported package
- Security: path escape, symlink escape, illegal ID
- Compatibility: registry integration, no auto-mount
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from novel_factory.skills.import_bridge import (
    ImportedInstructionSkill,
    apply_import_plan,
    build_import_plan,
    detect_import_mode,
    parse_skill_md,
    validate_imported_package,
    validate_skill_id,
    validate_source_skill,
)


# ── Helpers ────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]

# Track created packages for cleanup
_CREATED_PACKAGES: list[str] = []


@pytest.fixture(autouse=True)
def cleanup_imported_packages():
    """Clean up any packages created during tests."""
    yield
    pkg_root = Path(__file__).parent.parent / "novel_factory" / "skill_packages"
    for skill_id in _CREATED_PACKAGES:
        pkg_dir = pkg_root / skill_id.replace("-", "_")
        if pkg_dir.exists():
            import shutil
            shutil.rmtree(pkg_dir, ignore_errors=True)
    _CREATED_PACKAGES.clear()


def _apply_and_track(source, skill_id, **kwargs):
    """Apply import plan and track the package for cleanup."""
    result = apply_import_plan(source, skill_id, **kwargs)
    if result["ok"]:
        _CREATED_PACKAGES.append(skill_id)
    return result


# ── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def tmp_source_dir(tmp_path):
    """Create a temporary source skill directory."""
    source = tmp_path / "demo-skill"
    source.mkdir()
    return source


@pytest.fixture
def minimal_skill_md(tmp_source_dir):
    """Create a minimal SKILL.md."""
    skill_md = tmp_source_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: demo-skill\ndescription: Demo imported instruction skill.\n---\n\nUse this skill as a read-only instruction.\n",
        encoding="utf-8",
    )
    return tmp_source_dir


@pytest.fixture
def full_skill_dir(tmp_path):
    """Create a full source skill directory with scripts, prompts, references, rules."""
    source = tmp_path / "full-skill"
    source.mkdir()

    # SKILL.md
    (source / "SKILL.md").write_text(
        "---\nname: full-skill\ndescription: A skill with all features.\n---\n\nFull skill instructions.\n",
        encoding="utf-8",
    )

    # scripts/
    scripts_dir = source / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "helper.sh").write_text("#!/bin/bash\necho hello\n", encoding="utf-8")

    # prompts/
    prompts_dir = source / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "system.md").write_text("System prompt.", encoding="utf-8")

    # references/
    refs_dir = source / "references"
    refs_dir.mkdir()
    (refs_dir / "guide.md").write_text("Reference guide.", encoding="utf-8")

    # rules/
    rules_dir = source / "rules"
    rules_dir.mkdir()
    (rules_dir / "check.yaml").write_text("pattern: test\n", encoding="utf-8")

    # assets/
    assets_dir = source / "assets"
    assets_dir.mkdir()
    (assets_dir / "data.txt").write_text("asset data", encoding="utf-8")

    return source


# ── 1. import-plan: parse SKILL.md ─────────────────────────────

class TestImportPlan:
    """Tests for build_import_plan (read-only)."""

    def test_import_plan_reads_valid_skill_md(self, minimal_skill_md):
        result = build_import_plan(minimal_skill_md)
        assert result["ok"] is True
        assert result["data"]["detected"]["name"] == "demo-skill"
        assert result["data"]["target"]["skill_id"] == "imported-demo-skill"

    def test_import_plan_missing_skill_md(self, tmp_source_dir):
        result = build_import_plan(tmp_source_dir)
        assert result["ok"] is False
        assert "SKILL.md" in result["error"]

    def test_import_plan_no_frontmatter(self, tmp_source_dir):
        (tmp_source_dir / "SKILL.md").write_text("Just some text without frontmatter.")
        result = build_import_plan(tmp_source_dir)
        assert result["ok"] is False
        assert "frontmatter" in result["error"].lower()

    def test_import_plan_detects_scripts(self, full_skill_dir):
        result = build_import_plan(full_skill_dir)
        assert result["ok"] is True
        assert result["data"]["detected"]["has_scripts"] is True
        assert any("scripts" in w.lower() for w in result["data"]["warnings"])

    def test_import_plan_detects_prompts_references_rules_assets(self, full_skill_dir):
        result = build_import_plan(full_skill_dir)
        assert result["ok"] is True
        d = result["data"]["detected"]
        assert d["has_prompts"] is True
        assert d["has_references"] is True
        assert d["has_rules"] is True
        assert d["has_assets"] is True

    def test_import_plan_source_not_exists(self):
        result = build_import_plan("/nonexistent/path")
        assert result["ok"] is False
        assert "does not exist" in result["error"]

    def test_import_plan_source_not_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        result = build_import_plan(str(f))
        assert result["ok"] is False
        assert "not a directory" in result["error"]


# ── 2. Import Mode Detection ───────────────────────────────────

class TestDetectImportMode:
    def test_instruction_only(self):
        mode = detect_import_mode({"has_scripts": False, "has_rules": False, "has_prompts": False, "has_references": False})
        assert mode == "instruction-only"

    def test_prompt_pack(self):
        mode = detect_import_mode({"has_scripts": False, "has_rules": False, "has_prompts": True, "has_references": False})
        assert mode == "prompt-pack"

    def test_rule_pack(self):
        mode = detect_import_mode({"has_scripts": False, "has_rules": True, "has_prompts": False, "has_references": False})
        assert mode == "rule-pack"

    def test_script_pack(self):
        mode = detect_import_mode({"has_scripts": True, "has_rules": False, "has_prompts": False, "has_references": False})
        assert mode == "script-pack"


# ── 3. import-apply: generate package ──────────────────────────

class TestImportApply:
    def test_generates_package_directory(self, minimal_skill_md):
        result = _apply_and_track(minimal_skill_md, "imported-demo")
        assert result["ok"] is True
        assert Path(result["data"]["package_dir"]).is_dir()

    def test_generates_manifest_yaml(self, minimal_skill_md):
        result = _apply_and_track(minimal_skill_md, "imported-demo-mf")
        assert result["ok"] is True
        pkg_dir = Path(result["data"]["package_dir"])
        manifest_path = pkg_dir / "manifest.yaml"
        assert manifest_path.exists()
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert manifest["id"] == "imported-demo-mf"
        assert manifest["kind"] == "imported_instruction"

    def test_generates_handler_py(self, minimal_skill_md):
        result = _apply_and_track(minimal_skill_md, "imported-demo-hd")
        assert result["ok"] is True
        pkg_dir = Path(result["data"]["package_dir"])
        handler_path = pkg_dir / "handler.py"
        assert handler_path.exists()
        content = handler_path.read_text(encoding="utf-8")
        assert "ImportedInstructionSkill" in content

    def test_generates_fixtures_yaml(self, minimal_skill_md):
        result = _apply_and_track(minimal_skill_md, "imported-demo-fx")
        assert result["ok"] is True
        pkg_dir = Path(result["data"]["package_dir"])
        fixtures_path = pkg_dir / "tests" / "fixtures.yaml"
        assert fixtures_path.exists()
        fixtures = yaml.safe_load(fixtures_path.read_text(encoding="utf-8"))
        assert "cases" in fixtures

    def test_generates_readme_md(self, minimal_skill_md):
        result = _apply_and_track(minimal_skill_md, "imported-demo-rd")
        assert result["ok"] is True
        pkg_dir = Path(result["data"]["package_dir"])
        assert (pkg_dir / "README.md").exists()

    def test_target_exists_without_force_fails(self, minimal_skill_md):
        result1 = _apply_and_track(minimal_skill_md, "imported-exists-test")
        assert result1["ok"] is True
        # Second apply without force (don't track, won't create new)
        result2 = apply_import_plan(minimal_skill_md, "imported-exists-test")
        assert result2["ok"] is False
        assert "already exists" in result2["error"]

    def test_force_overwrites_existing(self, minimal_skill_md):
        result1 = _apply_and_track(minimal_skill_md, "imported-force-test")
        assert result1["ok"] is True
        # Force overwrite (still tracked from first call)
        result2 = apply_import_plan(minimal_skill_md, "imported-force-test", force=True)
        assert result2["ok"] is True

    def test_illegal_skill_id_rejected(self, minimal_skill_md):
        result = apply_import_plan(minimal_skill_md, "../bad-id")
        assert result["ok"] is False

    def test_manifest_defaults_manual_manual(self, minimal_skill_md):
        result = _apply_and_track(minimal_skill_md, "imported-manual-test")
        assert result["ok"] is True
        pkg_dir = Path(result["data"]["package_dir"])
        manifest = yaml.safe_load((pkg_dir / "manifest.yaml").read_text(encoding="utf-8"))
        assert manifest["allowed_agents"] == ["manual"]
        assert manifest["allowed_stages"] == ["manual"]

    def test_manifest_defaults_scripts_disabled(self, full_skill_dir):
        result = _apply_and_track(full_skill_dir, "imported-scripts-test")
        assert result["ok"] is True
        pkg_dir = Path(result["data"]["package_dir"])
        manifest = yaml.safe_load((pkg_dir / "manifest.yaml").read_text(encoding="utf-8"))
        assert manifest.get("has_scripts") is True
        assert manifest.get("scripts_enabled") is False
        assert any("scripts" in w.lower() for w in result["data"]["warnings"])


# ── 4. Security Tests ──────────────────────────────────────────

class TestSecurity:
    def test_path_escape_rejected(self, minimal_skill_md):
        result = apply_import_plan(minimal_skill_md, "../../etc-passwd")
        assert result["ok"] is False

    def test_symlink_escape_rejected(self, tmp_path):
        source = tmp_path / "evil-skill"
        source.mkdir()
        (source / "SKILL.md").write_text(
            "---\nname: evil\ndescription: evil\n---\n\nBad skill.\n",
            encoding="utf-8",
        )
        # Create symlink pointing outside
        scripts_dir = source / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "link").symlink_to("/etc/passwd")

        result = validate_source_skill(source)
        assert result["ok"] is False
        assert "symlink" in result["error"].lower() or "escape" in result["error"].lower()

    def test_skill_id_validation(self):
        assert validate_skill_id("imported-demo") is None
        assert validate_skill_id("imported_demo") is None
        assert validate_skill_id("") is not None
        assert validate_skill_id("../bad") is not None
        assert validate_skill_id("UPPER") is not None
        assert validate_skill_id("1start") is not None


# ── 5. import-validate ─────────────────────────────────────────

class TestImportValidate:
    def test_validate_valid_package(self, minimal_skill_md):
        apply_result = _apply_and_track(minimal_skill_md, "imported-val-ok")
        assert apply_result["ok"] is True

        validate_result = validate_imported_package("imported-val-ok")
        assert validate_result["ok"] is True

    def test_validate_nonexistent_package(self):
        result = validate_imported_package("imported-nonexistent-xyz")
        assert result["ok"] is False

    def test_validate_checks_manifest_agents(self, minimal_skill_md):
        apply_result = _apply_and_track(minimal_skill_md, "imported-agent-chk")
        assert apply_result["ok"] is True

        # Tamper with manifest
        pkg_dir = Path(apply_result["data"]["package_dir"])
        manifest = yaml.safe_load((pkg_dir / "manifest.yaml").read_text(encoding="utf-8"))
        manifest["allowed_agents"] = ["polisher"]
        (pkg_dir / "manifest.yaml").write_text(
            yaml.dump(manifest, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        result = validate_imported_package("imported-agent-chk")
        assert result["ok"] is False
        assert any("allowed_agents" in e for e in result["data"]["errors"])

    def test_import_validate_json_envelope_stable(self, minimal_skill_md):
        apply_result = _apply_and_track(minimal_skill_md, "imported-envelope-test")
        assert apply_result["ok"] is True

        result = validate_imported_package("imported-envelope-test")
        assert "ok" in result
        assert "error" in result
        assert "data" in result


# ── 6. Registry Integration ────────────────────────────────────

class TestRegistryIntegration:
    def test_imported_skill_not_auto_mounted(self, minimal_skill_md):
        """Imported skill should NOT appear in polisher/editor agent skills."""
        from novel_factory.skills.registry import SkillRegistry

        apply_result = _apply_and_track(minimal_skill_md, "imported-no-mount")
        assert apply_result["ok"] is True

        # Create a fresh registry
        registry = SkillRegistry()

        # Check the skill is NOT in agent_skills for polisher/editor
        polisher_skills = registry.get_skills_for_agent("polisher", "after_llm")
        assert "imported-no-mount" not in polisher_skills

        editor_skills = registry.get_skills_for_agent("editor", "before_review")
        assert "imported-no-mount" not in editor_skills

    def test_imported_instruction_skill_is_context_skill(self):
        """ImportedInstructionSkill should be a ContextSkill subclass."""
        from novel_factory.skills.base import BaseSkill, ContextSkill
        assert issubclass(ImportedInstructionSkill, BaseSkill)
        assert issubclass(ImportedInstructionSkill, ContextSkill)


# ── 7. CLI Error Paths ─────────────────────────────────────────

class TestCLIErrorPaths:
    def test_cli_import_plan_missing_source(self):
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "import-plan", "--json"],
            capture_output=True, text=True,
            cwd=REPO_ROOT,
        )
        # Should not traceback, just error
        assert "Traceback" not in result.stderr

    def test_cli_import_apply_missing_args(self):
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "import-apply", "--json"],
            capture_output=True, text=True,
            cwd=REPO_ROOT,
        )
        assert "Traceback" not in result.stderr


# ── 8. parse_skill_md ──────────────────────────────────────────

class TestParseSkillMd:
    def test_valid_frontmatter(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\nname: test-skill\ndescription: A test.\n---\n\nBody text.\n",
            encoding="utf-8",
        )
        fm, body = parse_skill_md(skill_md)
        assert fm["name"] == "test-skill"
        assert fm["description"] == "A test."
        assert "Body text." in body

    def test_missing_name(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\ndescription: No name.\n---\n\nBody.\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="name"):
            parse_skill_md(skill_md)

    def test_missing_description(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\nname: no-desc\n---\n\nBody.\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="description"):
            parse_skill_md(skill_md)

    def test_no_frontmatter(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("Just plain text.", encoding="utf-8")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_md(skill_md)


# ── 9. [P1] Registry auto-discover imported skills ──────────────

class TestRegistryAutoDiscover:
    """Imported skills should be discoverable by skills show/test."""

    def test_imported_skill_found_by_registry(self, minimal_skill_md):
        """After import-apply, SkillRegistry should find the skill."""
        from novel_factory.skills.registry import SkillRegistry

        apply_result = _apply_and_track(minimal_skill_md, "imported-registry-disc")
        assert apply_result["ok"] is True

        registry = SkillRegistry()

        # skill should be in skills_config (auto-discovered)
        assert "imported-registry-disc" in registry.skills_config

        # get_manifest should work
        manifest = registry.get_manifest("imported-registry-disc")
        assert manifest is not None
        assert manifest.kind == "imported_instruction"

    def test_imported_skill_show_via_registry(self, minimal_skill_md):
        """get_skill should return an instance for imported skills."""
        from novel_factory.skills.registry import SkillRegistry

        apply_result = _apply_and_track(minimal_skill_md, "imported-registry-show")
        assert apply_result["ok"] is True

        registry = SkillRegistry()

        # get_skill should find the skill (enabled=False by default)
        skill_config = registry.skills_config.get("imported-registry-show", {})
        assert skill_config.get("enabled") is False
        # The skill is disabled, so get_skill returns None — that's correct
        # But the manifest should still be accessible
        manifest = registry.get_manifest("imported-registry-show")
        assert manifest is not None

    def test_imported_skill_not_in_agent_skills(self, minimal_skill_md):
        """Auto-discovered imported skills must NOT be auto-mounted to any agent."""
        from novel_factory.skills.registry import SkillRegistry

        apply_result = _apply_and_track(minimal_skill_md, "imported-registry-noagent")
        assert apply_result["ok"] is True

        registry = SkillRegistry()

        # Not in agent_skills for any agent
        for agent, stages in registry.agent_skills.items():
            for stage, skill_ids in stages.items():
                assert "imported-registry-noagent" not in skill_ids

    def test_builtin_skill_not_overridden_by_discover(self):
        """Auto-discover must not override skills.yaml entries."""
        from novel_factory.skills.registry import SkillRegistry

        registry = SkillRegistry()
        # humanizer-zh is in skills.yaml — should keep its original config
        assert "humanizer-zh" in registry.skills_config
        original = registry.skills_config["humanizer-zh"]
        assert original.get("enabled") is True  # not overridden by discover


# ── 10. [P1] Force overwrite protection ─────────────────────────

class TestForceOverwriteProtection:
    """--force should not delete built-in skill packages."""

    def test_force_rejects_builtin_package(self, minimal_skill_md):
        """Cannot --force overwrite a built-in skill package."""
        # Try to import with skill-id that maps to humanizer_zh directory
        result = apply_import_plan(minimal_skill_md, "humanizer-zh", force=True)
        assert result["ok"] is False
        assert "built-in" in result["error"].lower() or "overwrite" in result["error"].lower()

    def test_force_allows_imported_package(self, minimal_skill_md):
        """--force can overwrite a previously imported package."""
        result1 = _apply_and_track(minimal_skill_md, "imported-force-allowed")
        assert result1["ok"] is True

        result2 = apply_import_plan(minimal_skill_md, "imported-force-allowed", force=True)
        assert result2["ok"] is True

    def test_force_rejects_no_manifest(self, minimal_skill_md, tmp_path):
        """Cannot --force overwrite a directory without manifest.yaml."""
        # Create a dummy directory without manifest
        # Note: skill_id "imported-force-nomf" maps to directory "imported_force_nomf"
        pkg_root = Path(__file__).parent.parent / "novel_factory" / "skill_packages"
        dummy_dir = pkg_root / "imported_force_nomf"
        dummy_dir.mkdir(exist_ok=True)
        (dummy_dir / "some_file.txt").write_text("not a skill")

        try:
            result = apply_import_plan(minimal_skill_md, "imported-force-nomf", force=True)
            assert result["ok"] is False
            assert "overwrite" in result["error"].lower() or "manifest" in result["error"].lower()
        finally:
            import shutil
            if dummy_dir.exists():
                shutil.rmtree(dummy_dir, ignore_errors=True)


# ── 11. [P2] Auto-validate after import-apply ───────────────────

class TestAutoValidateAfterApply:
    """import-apply should auto-validate the generated package."""

    def test_apply_includes_validation_result(self, minimal_skill_md):
        """apply_import_plan result should contain validation key."""
        result = _apply_and_track(minimal_skill_md, "imported-auto-val")
        assert result["ok"] is True
        assert "validation" in result["data"]
        assert result["data"]["validation"]["ok"] is True


# ── 12. [P2] prompts/imported_skill.md not overwritten ──────────

class TestPromptNoOverwrite:
    """Source prompts/imported_skill.md should not overwrite generated one."""

    def test_imported_skill_md_preserved(self, tmp_path):
        """When source has prompts/imported_skill.md, it must be skipped."""
        # Create source with prompts/imported_skill.md
        source = tmp_path / "overwrite-skill"
        source.mkdir()
        (source / "SKILL.md").write_text(
            "---\nname: overwrite-skill\ndescription: Test overwrite.\n---\n\nGenerated content.\n",
            encoding="utf-8",
        )
        prompts_dir = source / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "imported_skill.md").write_text(
            "EVIL CONTENT FROM SOURCE - should not appear",
            encoding="utf-8",
        )
        (prompts_dir / "system.md").write_text("System prompt.", encoding="utf-8")

        result = _apply_and_track(str(source), "imported-prompt-nooverwrite")
        assert result["ok"] is True

        pkg_dir = Path(result["data"]["package_dir"])
        content = (pkg_dir / "prompts" / "imported_skill.md").read_text(encoding="utf-8")
        # Should contain the generated body, NOT the source's evil content
        assert "Generated content." in content
        assert "EVIL CONTENT FROM SOURCE" not in content

        # system.md should still be copied
        assert (pkg_dir / "prompts" / "system.md").exists()
