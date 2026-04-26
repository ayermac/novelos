"""v3.8 Skill Import Models — parsing, validation, and plan building.

Pure read-only functions for analyzing external skill directories.
No filesystem writes in this module.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────

SKILL_MD = "SKILL.md"
VALID_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*[a-z0-9]$")
LARGE_FILE_THRESHOLD = 1_000_000  # 1 MB


# ── SKILL.md Parsing ───────────────────────────────────────────

def parse_skill_md(skill_md_path: Path) -> tuple[dict[str, str], str]:
    """Parse SKILL.md frontmatter and body.

    Args:
        skill_md_path: Path to SKILL.md file.

    Returns:
        Tuple of (frontmatter_dict, body_text).

    Raises:
        ValueError: If frontmatter is missing or invalid.
    """
    content = skill_md_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter (---)")

    # Extract frontmatter
    end_idx = content.find("---", 3)
    if end_idx == -1:
        raise ValueError("SKILL.md frontmatter not closed (missing ---)")

    fm_text = content[3:end_idx].strip()
    body = content[end_idx + 3:].strip()

    try:
        frontmatter = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}")

    if not isinstance(frontmatter, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")

    if "name" not in frontmatter:
        raise ValueError("SKILL.md frontmatter missing required field: name")

    if "description" not in frontmatter:
        raise ValueError("SKILL.md frontmatter missing required field: description")

    return frontmatter, body


# ── Source Validation ───────────────────────────────────────────

def validate_source_skill(source: str | Path) -> dict[str, Any]:
    """Validate a source skill directory.

    Args:
        source: Path to source skill directory.

    Returns:
        Envelope: {ok, error, data} where data contains validation result.
    """
    source_path = Path(source).resolve()

    # Must exist
    if not source_path.exists():
        return {"ok": False, "error": f"Source does not exist: {source}", "data": {}}

    # Must be a directory
    if not source_path.is_dir():
        return {"ok": False, "error": f"Source is not a directory: {source}", "data": {}}

    # Must have SKILL.md
    skill_md = source_path / SKILL_MD
    if not skill_md.exists():
        return {"ok": False, "error": f"Source missing SKILL.md: {source}", "data": {}}

    # Must have valid frontmatter
    try:
        frontmatter, body = parse_skill_md(skill_md)
    except ValueError as e:
        return {"ok": False, "error": str(e), "data": {}}

    # Check for symlink escapes
    warnings = []
    for item in source_path.rglob("*"):
        if item.is_symlink():
            target = item.resolve()
            try:
                target.relative_to(source_path)
            except ValueError:
                return {
                    "ok": False,
                    "error": f"Symlink escape detected: {item} -> {target}",
                    "data": {},
                }

    # Detect features
    has_scripts = (source_path / "scripts").is_dir()
    has_references = (source_path / "references").is_dir()
    has_assets = (source_path / "assets").is_dir()
    has_rules = (source_path / "rules").is_dir()
    has_prompts = (source_path / "prompts").is_dir()
    has_examples = (source_path / "examples").is_dir()

    # Warnings
    if has_scripts:
        warnings.append("Source contains scripts. Scripts will be copied but disabled.")
    if has_assets:
        for f in (source_path / "assets").rglob("*"):
            if f.is_file() and _is_binary(f):
                warnings.append(f"Source contains binary asset: {f.name}")
                break
    for f in source_path.rglob("*"):
        if f.is_file() and f.stat().st_size > LARGE_FILE_THRESHOLD:
            warnings.append(f"Source contains large file: {f.name} ({f.stat().st_size} bytes)")
    if len(frontmatter.get("description", "")) > 500:
        warnings.append("Source description is very long (> 500 chars)")

    return {
        "ok": True,
        "error": None,
        "data": {
            "source": str(source_path),
            "frontmatter": frontmatter,
            "body": body,
            "detected": {
                "name": frontmatter["name"],
                "description": frontmatter["description"],
                "has_scripts": has_scripts,
                "has_references": has_references,
                "has_assets": has_assets,
                "has_rules": has_rules,
                "has_prompts": has_prompts,
                "has_examples": has_examples,
            },
            "warnings": warnings,
        },
    }


def _is_binary(path: Path) -> bool:
    """Check if a file appears to be binary."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except Exception:
        return True


# ── Import Mode Detection ──────────────────────────────────────

def detect_import_mode(detected: dict[str, bool]) -> str:
    """Detect the import mode based on source features.

    Args:
        detected: Dict with has_scripts, has_references, has_assets, etc.

    Returns:
        Import mode string: "instruction-only", "prompt-pack", "rule-pack", or "script-pack".
    """
    if detected.get("has_scripts"):
        return "script-pack"
    if detected.get("has_rules"):
        return "rule-pack"
    if detected.get("has_prompts") or detected.get("has_references"):
        return "prompt-pack"
    return "instruction-only"


# ── Skill ID Validation ────────────────────────────────────────

def validate_skill_id(skill_id: str) -> str | None:
    """Validate a skill_id string.

    Args:
        skill_id: Proposed skill identifier.

    Returns:
        None if valid, error message if invalid.
    """
    if not skill_id:
        return "skill_id is required"
    if not VALID_ID_PATTERN.match(skill_id):
        return f"skill_id '{skill_id}' is invalid (must match {VALID_ID_PATTERN.pattern})"
    if ".." in skill_id:
        return f"skill_id contains path traversal: {skill_id}"
    return None


# ── Import Plan ─────────────────────────────────────────────────

def build_import_plan(source: str | Path) -> dict[str, Any]:
    """Build an import plan for a source skill directory.

    Read-only: does not write any files.

    Args:
        source: Path to source skill directory.

    Returns:
        Envelope: {ok, error, data} with import plan.
    """
    validation = validate_source_skill(source)
    if not validation["ok"]:
        return validation

    data = validation["data"]
    detected = data["detected"]
    frontmatter = data["frontmatter"]
    warnings = data["warnings"]

    import_mode = detect_import_mode(detected)
    source_name = frontmatter["name"]
    skill_id = f"imported-{source_name}"

    # Validate skill_id format
    if not VALID_ID_PATTERN.match(skill_id):
        return {
            "ok": False,
            "error": f"Generated skill_id '{skill_id}' is invalid (must match {VALID_ID_PATTERN.pattern})",
            "data": {},
        }

    kind = "imported_instruction"

    return {
        "ok": True,
        "error": None,
        "data": {
            "source": data["source"],
            "detected": detected,
            "target": {
                "skill_id": skill_id,
                "kind": kind,
                "import_mode": import_mode,
            },
            "warnings": warnings,
        },
    }
