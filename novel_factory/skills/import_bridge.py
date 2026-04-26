"""v3.8 Skill Import Bridge — safe external skill import.

Reads local external Skill directories, generates import plans,
creates novel_factory skill package drafts with safe defaults.

Security:
- Never executes external scripts
- Never auto-enables imported skills
- Never auto-modifies skills.yaml
- All dangerous permissions default to false
- Allowed agents/stages default to manual/manual
"""

from __future__ import annotations

import logging
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Re-export from import_models for backward compatibility
from .import_models import (  # noqa: F401
    SKILL_MD,
    LARGE_FILE_THRESHOLD,
    VALID_ID_PATTERN,
    build_import_plan,
    detect_import_mode,
    parse_skill_md,
    validate_skill_id,
    validate_source_skill,
)
from .import_models import _is_binary  # noqa: F401
from .base import ContextSkill

logger = logging.getLogger(__name__)


# ── Safe Copy ───────────────────────────────────────────────────

def safe_copy_tree(
    src_dir: Path,
    dst_dir: Path,
    subdir: str,
    skip_names: set[str] | None = None,
) -> list[str]:
    """Safely copy a subdirectory from source to destination.

    Validates no path escapes or symlink escapes.

    Args:
        src_dir: Source base directory.
        dst_dir: Destination base directory.
        subdir: Subdirectory name to copy.
        skip_names: Set of file names to skip (e.g., {"imported_skill.md"}).

    Returns:
        List of copied relative file paths.

    Raises:
        ValueError: If path escape or symlink escape detected.
    """
    src_subdir = src_dir / subdir
    if not src_subdir.is_dir():
        return []

    if ".." in subdir:
        raise ValueError(f"Path traversal in subdir: {subdir}")

    dst_subdir = dst_dir / subdir
    dst_subdir.mkdir(parents=True, exist_ok=True)

    if skip_names is None:
        skip_names = set()

    copied = []
    for item in src_subdir.rglob("*"):
        if not item.is_file():
            continue

        # Skip files by name
        if item.name in skip_names:
            continue

        # Check symlink escape
        if item.is_symlink():
            target = item.resolve()
            try:
                target.relative_to(src_subdir.resolve())
            except ValueError:
                raise ValueError(f"Symlink escape: {item} -> {target}")

        # Compute relative path
        rel_path = item.relative_to(src_subdir)

        # Check path escape in relative path
        if ".." in str(rel_path):
            raise ValueError(f"Path traversal in: {rel_path}")

        dst_file = dst_subdir / rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)

        # Verify destination is within package
        try:
            dst_file.resolve().relative_to(dst_dir.resolve())
        except ValueError:
            raise ValueError(f"Destination path escape: {dst_file}")

        shutil.copy2(item, dst_file)
        # Remove execute permission for safety
        current = dst_file.stat().st_mode
        dst_file.chmod(current & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        copied.append(f"{subdir}/{rel_path}")

    return copied


# ── Manifest Generation ─────────────────────────────────────────

def _generate_manifest(
    skill_id: str,
    name: str,
    description: str,
    source_path: str,
    has_scripts: bool,
    has_prompts: bool,
    has_references: bool,
    has_rules: bool,
) -> dict[str, Any]:
    """Generate manifest data for an imported skill."""
    # Derive package dir name from skill_id (replace - with _)
    package_name = skill_id.replace("-", "_")

    manifest = {
        "id": skill_id,
        "name": f"Imported {name}",
        "version": "0.1.0",
        "kind": "imported_instruction",
        "class_name": "ImportedInstructionSkill",
        "description": description,
        "enabled": False,
        "builtin": False,
        "package": {
            "name": package_name,
            "handler": "handler.py",
            "entry_class": "ImportedInstructionSkill",
            "prompts_dir": "prompts" if has_prompts else None,
            "rules_dir": "rules" if has_rules else None,
            "fixtures": "tests/fixtures.yaml",
        },
        "allowed_agents": ["manual"],
        "allowed_stages": ["manual"],
        "permissions": {
            "transform_text": False,
            "validate_text": False,
            "read_context": True,
            "write_files": False,
            "read_chapter": False,
            "write_quality_report": False,
            "write_skill_run": True,
            "write_chapter_content": False,
            "update_chapter_status": False,
            "send_agent_message": False,
            "call_llm": False,
            "call_network": False,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Input text for the skill"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "instructions": {"type": "string"},
                "prompt_fragments": {"type": "array"},
                "references": {"type": "array"},
            },
        },
        "failure_policy": {
            "on_error": "warn",
            "max_retries": 0,
        },
        "import": {
            "source_type": "local_directory",
            "source_path": source_path,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "importer_version": "v3.8",
        },
    }

    if has_scripts:
        manifest["has_scripts"] = True
        manifest["scripts_enabled"] = False

    return manifest


# ── Handler Generation ──────────────────────────────────────────

def _generate_handler(skill_id: str) -> str:
    """Generate handler.py content for an imported skill."""
    return f'''"""Imported skill handler for {skill_id}."""

from novel_factory.skills.import_bridge import ImportedInstructionSkill

__all__ = ["ImportedInstructionSkill"]
'''


# ── Fixtures Generation ────────────────────────────────────────

def _generate_fixtures(skill_id: str) -> str:
    """Generate smoke test fixtures for an imported skill."""
    return f"""# Smoke test fixtures for {skill_id}

cases:
  - name: smoke_test
    description: "Basic smoke test for imported skill"
    input:
      text: "Hello world"
    expect:
      ok: true
      contains:
        - instructions
"""


# ── README Generation ──────────────────────────────────────────

def _generate_readme(
    skill_id: str,
    name: str,
    description: str,
    source_path: str,
    import_mode: str,
    has_rules: bool,
) -> str:
    """Generate README.md for an imported skill."""
    parts = [
        f"# Imported Skill: {name}",
        "",
        f"**Skill ID:** `{skill_id}`",
        f"**Description:** {description}",
        f"**Import Mode:** {import_mode}",
        f"**Source:** `{source_path}`",
        "",
        "## Safety",
        "",
        "- This skill was imported from an external source.",
        "- Default permissions: read-only (no transform, no write).",
        "- Allowed agents: `manual` only.",
        "- Allowed stages: `manual` only.",
        "- **Not auto-mounted** to any production agent.",
    ]

    if has_rules:
        parts.extend([
            "",
            "## TODO: Rule Implementation",
            "",
            "This skill contains rules that need manual implementation.",
            "The handler stub does not automatically interpret rules.",
            "Please review `rules/` and update `handler.py` accordingly.",
        ])

    parts.extend([
        "",
        "## Activation",
        "",
        "To enable this skill, manually edit `novel_factory/config/skills.yaml`:",
        "",
        "```yaml",
        "skills:",
        f"  {skill_id}:",
        "    enabled: true",
        f"    package: skill_packages/{skill_id.replace('-', '_')}",
        "```",
        "",
        "Then add to the desired agent/stage in `agent_skills` section.",
    ])

    return "\n".join(parts) + "\n"


# ── Force Overwrite Protection ───────────────────────────────────

def _check_force_overwrite_safe(package_dir: Path, skill_id: str) -> str | None:
    """Check that force-overwriting a package directory is safe.

    Only imported packages (kind=imported_instruction with import metadata)
    may be overwritten. Built-in or manually created packages are protected.

    Args:
        package_dir: Target package directory.
        skill_id: Skill ID being imported.

    Returns:
        Error message if overwrite is unsafe, None if safe.
    """
    manifest_path = package_dir / "manifest.yaml"
    if not manifest_path.exists():
        return (
            f"Cannot overwrite {package_dir}: no manifest.yaml found. "
            f"Only imported packages can be overwritten with --force."
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = yaml.safe_load(f)
    except Exception:
        return (
            f"Cannot overwrite {package_dir}: failed to read manifest.yaml. "
            f"Only imported packages can be overwritten with --force."
        )

    if not isinstance(manifest_data, dict):
        return f"Cannot overwrite {package_dir}: invalid manifest.yaml."

    # Must be an imported package
    if manifest_data.get("kind") != "imported_instruction":
        return (
            f"Cannot overwrite {package_dir}: it is a built-in skill "
            f"(kind={manifest_data.get('kind')!r}). "
            f"--force can only overwrite imported_instruction packages."
        )

    # Must have import metadata
    if "import" not in manifest_data:
        return (
            f"Cannot overwrite {package_dir}: missing import metadata. "
            f"--force can only overwrite previously imported packages."
        )

    return None


# ── Apply Import Plan ───────────────────────────────────────────

def apply_import_plan(
    source: str | Path,
    skill_id: str,
    force: bool = False,
) -> dict[str, Any]:
    """Apply an import plan, generating the skill package.

    Args:
        source: Path to source skill directory.
        skill_id: Target skill ID (must match VALID_ID_PATTERN).
        force: If True, overwrite existing package directory.

    Returns:
        Envelope: {ok, error, data} with generated file list.
    """
    # Validate skill_id
    id_error = validate_skill_id(skill_id)
    if id_error:
        return {"ok": False, "error": id_error, "data": {}}

    # Validate source
    validation = validate_source_skill(source)
    if not validation["ok"]:
        return validation

    data = validation["data"]
    detected = data["detected"]
    frontmatter = data["frontmatter"]
    body = data["body"]
    source_path = data["source"]

    # Resolve package directory
    package_root = Path(__file__).parent.parent / "skill_packages"
    package_dir_name = skill_id.replace("-", "_")
    package_dir = package_root / package_dir_name

    # Check path escape
    try:
        package_dir.resolve().relative_to(package_root.resolve())
    except ValueError:
        return {"ok": False, "error": f"Package path escape: {package_dir}", "data": {}}

    # Check existing directory
    if package_dir.exists() and not force:
        return {
            "ok": False,
            "error": f"Target directory already exists: {package_dir}. Use --force to overwrite.",
            "data": {},
        }

    # Remove existing if force — but only if it's an imported package
    if package_dir.exists() and force:
        protect_error = _check_force_overwrite_safe(package_dir, skill_id)
        if protect_error:
            return {"ok": False, "error": protect_error, "data": {}}
        shutil.rmtree(package_dir)

    # Create package directory
    package_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []
    warnings = list(data["warnings"])

    try:
        # Generate manifest.yaml
        manifest_data = _generate_manifest(
            skill_id=skill_id,
            name=frontmatter["name"],
            description=frontmatter["description"],
            source_path=source_path,
            has_scripts=detected["has_scripts"],
            has_prompts=detected["has_prompts"],
            has_references=detected["has_references"],
            has_rules=detected["has_rules"],
        )
        manifest_path = package_dir / "manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest_data, default_flow_style=False, allow_unicode=True, sort_keys=False), encoding="utf-8")
        generated_files.append("manifest.yaml")

        # Generate handler.py
        handler_content = _generate_handler(skill_id)
        handler_path = package_dir / "handler.py"
        handler_path.write_text(handler_content, encoding="utf-8")
        generated_files.append("handler.py")

        # Generate prompts/imported_skill.md
        prompts_dir = package_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        prompt_path = prompts_dir / "imported_skill.md"
        prompt_path.write_text(body, encoding="utf-8")
        generated_files.append("prompts/imported_skill.md")

        # Copy source prompts if present (skip imported_skill.md to preserve generated one)
        if detected["has_prompts"]:
            src_prompts = Path(source_path) / "prompts"
            copied = safe_copy_tree(
                Path(source_path), package_dir, "prompts",
                skip_names={"imported_skill.md"},
            )
            generated_files.extend(copied)

        # Copy references
        if detected["has_references"]:
            copied = safe_copy_tree(Path(source_path), package_dir, "references")
            generated_files.extend(copied)

        # Copy rules
        if detected["has_rules"]:
            copied = safe_copy_tree(Path(source_path), package_dir, "rules")
            generated_files.extend(copied)

        # Copy scripts (but disabled)
        if detected["has_scripts"]:
            copied = safe_copy_tree(Path(source_path), package_dir, "scripts")
            generated_files.extend(copied)
            warnings.append("Imported skill contains scripts. Scripts are copied but disabled.")

        # Copy assets
        if detected["has_assets"]:
            copied = safe_copy_tree(Path(source_path), package_dir, "assets")
            generated_files.extend(copied)

        # Generate tests/fixtures.yaml
        tests_dir = package_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        fixtures_path = tests_dir / "fixtures.yaml"
        fixtures_path.write_text(_generate_fixtures(skill_id), encoding="utf-8")
        generated_files.append("tests/fixtures.yaml")

        # Generate README.md
        import_mode = detect_import_mode(detected)
        readme_content = _generate_readme(
            skill_id=skill_id,
            name=frontmatter["name"],
            description=frontmatter["description"],
            source_path=source_path,
            import_mode=import_mode,
            has_rules=detected["has_rules"],
        )
        readme_path = package_dir / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        generated_files.append("README.md")

    except Exception as e:
        # Cleanup on failure
        if package_dir.exists():
            shutil.rmtree(package_dir)
        return {"ok": False, "error": f"Import failed: {e}", "data": {}}

    # v3.8: Auto-validate the generated package
    validation_result = validate_imported_package(skill_id)

    return {
        "ok": True,
        "error": None,
        "data": {
            "skill_id": skill_id,
            "package_dir": str(package_dir),
            "generated_files": generated_files,
            "warnings": warnings,
            "validation": validation_result,
        },
    }


# ── Validate Imported Package ──────────────────────────────────

def validate_imported_package(skill_id: str) -> dict[str, Any]:
    """Validate an imported skill package.

    Args:
        skill_id: Skill identifier to validate.

    Returns:
        Envelope: {ok, error, data} with validation results.
    """
    # Validate skill_id format
    id_error = validate_skill_id(skill_id)
    if id_error:
        return {"ok": False, "error": id_error, "data": {}}

    package_root = Path(__file__).parent.parent / "skill_packages"
    package_dir_name = skill_id.replace("-", "_")
    package_dir = package_root / package_dir_name

    errors = []
    warnings = []

    # Check package directory exists
    if not package_dir.is_dir():
        return {"ok": False, "error": f"Package directory not found: {package_dir}", "data": {}}

    # Check manifest
    manifest_path = package_dir / "manifest.yaml"
    if not manifest_path.exists():
        errors.append("manifest.yaml not found")
    else:
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest_data = yaml.safe_load(f)

            # Validate manifest fields
            if manifest_data.get("id") != skill_id:
                errors.append(f"manifest id '{manifest_data.get('id')}' != '{skill_id}'")

            if manifest_data.get("kind") != "imported_instruction":
                errors.append(f"manifest kind should be 'imported_instruction', got '{manifest_data.get('kind')}'")

            # Security checks
            if manifest_data.get("allowed_agents") != ["manual"]:
                errors.append("allowed_agents must be ['manual']")

            if manifest_data.get("allowed_stages") != ["manual"]:
                errors.append("allowed_stages must be ['manual']")

            perms = manifest_data.get("permissions", {})
            if perms.get("transform_text"):
                errors.append("transform_text must be false")
            if perms.get("write_files") or perms.get("write_chapter_content"):
                errors.append("write permissions must be false")
            if perms.get("call_llm"):
                errors.append("call_llm must be false")
            if perms.get("call_network"):
                errors.append("call_network must be false")

            # Scripts check
            if manifest_data.get("has_scripts") and manifest_data.get("scripts_enabled"):
                errors.append("scripts_enabled must be false for imported skills")

        except Exception as e:
            errors.append(f"Failed to load manifest: {e}")

    # Check handler
    handler_path = package_dir / "handler.py"
    if not handler_path.exists():
        errors.append("handler.py not found")
    else:
        try:
            # Try to import and check it's a BaseSkill subclass
            import importlib
            module_path = f"novel_factory.skill_packages.{package_dir_name}.handler"
            module = importlib.import_module(module_path)

            if not hasattr(module, "ImportedInstructionSkill"):
                errors.append("handler.py does not export ImportedInstructionSkill")
            else:
                from .base import BaseSkill
                skill_class = getattr(module, "ImportedInstructionSkill")
                if not issubclass(skill_class, BaseSkill):
                    errors.append("ImportedInstructionSkill is not a BaseSkill subclass")

        except ImportError as e:
            errors.append(f"Failed to import handler: {e}")
        except Exception as e:
            errors.append(f"Handler validation error: {e}")

    # Check fixtures
    fixtures_path = package_dir / "tests" / "fixtures.yaml"
    if not fixtures_path.exists():
        warnings.append("tests/fixtures.yaml not found")
    else:
        try:
            with open(fixtures_path, encoding="utf-8") as f:
                fixtures = yaml.safe_load(f)
            if not fixtures.get("cases"):
                warnings.append("fixtures.yaml has no test cases")
        except Exception as e:
            errors.append(f"Failed to load fixtures: {e}")

    # Check for path escapes
    for item in package_dir.rglob("*"):
        if item.is_symlink():
            target = item.resolve()
            try:
                target.relative_to(package_dir.resolve())
            except ValueError:
                errors.append(f"Symlink escape: {item} -> {target}")

    return {
        "ok": len(errors) == 0,
        "error": "; ".join(errors) if errors else None,
        "data": {
            "skill_id": skill_id,
            "package_dir": str(package_dir),
            "errors": errors,
            "warnings": warnings,
        },
    }


# ── ImportedInstructionSkill ────────────────────────────────────

class ImportedInstructionSkill(ContextSkill):
    """Default handler for imported instruction-only skills.

    Returns the imported instructions and prompt fragments as context.
    Does NOT execute external scripts or modify content.
    """

    skill_id = "imported-instruction"
    skill_type = "context"
    version = "0.1.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return imported skill instructions as context.

        Args:
            payload: Input data (expects 'text' field).

        Returns:
            Envelope with instructions, prompt_fragments, and references.
        """
        instructions = self._load_instructions()
        prompt_fragments = self._load_prompt_fragments()
        references = self._load_references()

        return {
            "ok": True,
            "error": None,
            "data": {
                "fragment_name": "imported_instruction",
                "content": instructions,
                "priority": 10,
                "mandatory": False,
                "instructions": instructions,
                "prompt_fragments": prompt_fragments,
                "references": references,
            },
        }

    def _load_instructions(self) -> str:
        """Load the main instruction prompt."""
        try:
            # Try to load from package prompts directory
            from importlib.resources import files
            package_root = files("novel_factory")
            prompt_path = package_root / "skill_packages" / self._package_name() / "prompts" / "imported_skill.md"
            if hasattr(prompt_path, 'read_text'):
                return prompt_path.read_text(encoding="utf-8")
            return Path(str(prompt_path)).read_text(encoding="utf-8")
        except Exception:
            return ""

    def _load_prompt_fragments(self) -> list[str]:
        """Load additional prompt fragments from prompts/ directory."""
        fragments = []
        try:
            from importlib.resources import files
            package_root = files("novel_factory")
            prompts_dir = package_root / "skill_packages" / self._package_name() / "prompts"
            prompts_path = Path(str(prompts_dir))
            if prompts_path.is_dir():
                for f in sorted(prompts_path.glob("*.md")):
                    if f.name != "imported_skill.md":
                        fragments.append(f.read_text(encoding="utf-8"))
        except Exception:
            pass
        return fragments

    def _load_references(self) -> list[str]:
        """Load reference documents from references/ directory."""
        references = []
        try:
            from importlib.resources import files
            package_root = files("novel_factory")
            refs_dir = package_root / "skill_packages" / self._package_name() / "references"
            refs_path = Path(str(refs_dir))
            if refs_path.is_dir():
                for f in sorted(refs_path.glob("*")):
                    if f.is_file() and not _is_binary(f):
                        references.append(f.read_text(encoding="utf-8"))
        except Exception:
            pass
        return references

    def _package_name(self) -> str:
        """Derive package directory name from skill config."""
        # Use config to find the package name
        pkg = self.config.get("package", "")
        if pkg:
            return Path(pkg).name
        return "unknown"
