"""Skill manifest loader for v2.2.

Handles loading and validating skill manifests from YAML files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ..models.skill_manifest import SkillManifest
from .base import BUILTIN_SKILLS

logger = logging.getLogger(__name__)


class SkillManifestError(Exception):
    """Error loading or validating skill manifest."""

    pass


def load_manifest(manifest_path: str) -> SkillManifest:
    """Load a skill manifest from a YAML file.

    Args:
        manifest_path: Path to the manifest YAML file (relative to package root)

    Returns:
        SkillManifest instance

    Raises:
        SkillManifestError: If manifest cannot be loaded or is invalid
    """
    try:
        # Resolve path relative to package root
        if not Path(manifest_path).is_absolute():
            # Try to load from package resources
            try:
                from importlib.resources import files

                package_root = files("novel_factory")
                manifest_file = package_root.joinpath(manifest_path)
                manifest_data = yaml.safe_load(manifest_file.read_text())
            except Exception:
                # Fallback to file system
                from importlib.resources import files

                package_root = files("novel_factory")
                base_path = Path(str(package_root))
                full_path = base_path / manifest_path
                if not full_path.exists():
                    raise SkillManifestError(f"Manifest file not found: {manifest_path}")
                with open(full_path, "r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f)
        else:
            # Absolute path
            full_path = Path(manifest_path)
            if not full_path.exists():
                raise SkillManifestError(f"Manifest file not found: {manifest_path}")
            with open(full_path, "r", encoding="utf-8") as f:
                manifest_data = yaml.safe_load(f)

        if not isinstance(manifest_data, dict):
            raise SkillManifestError(f"Manifest must be a YAML mapping: {manifest_path}")

        # Validate required fields
        required_fields = [
            "id",
            "name",
            "version",
            "kind",
            "class_name",
            "allowed_agents",
            "allowed_stages",
            "permissions",
            "input_schema",
            "output_schema",
        ]
        for field in required_fields:
            if field not in manifest_data:
                raise SkillManifestError(f"Missing required field '{field}' in manifest: {manifest_path}")

        # Validate class_name is in whitelist
        class_name = manifest_data["class_name"]
        if class_name not in BUILTIN_SKILLS:
            raise SkillManifestError(
                f"Invalid class_name '{class_name}' in manifest {manifest_path}. "
                f"Must be one of: {list(BUILTIN_SKILLS.keys())}"
            )

        # Validate skill id matches manifest id
        # This will be done by the caller who knows the skill_id

        # Parse manifest
        manifest = SkillManifest(**manifest_data)

        # Validate permissions don't violate v2.2 constraints
        _validate_permissions(manifest)

        return manifest

    except yaml.YAMLError as e:
        raise SkillManifestError(f"Invalid YAML in manifest {manifest_path}: {e}")
    except Exception as e:
        if isinstance(e, SkillManifestError):
            raise
        raise SkillManifestError(f"Error loading manifest {manifest_path}: {e}")


def _validate_permissions(manifest: SkillManifest) -> None:
    """Validate that manifest permissions don't violate v2.2 constraints.

    v2.2 must enforce that skills cannot:
    - write_chapter_content (unless explicitly allowed by spec)
    - update_chapter_status (unless explicitly allowed by spec)
    - call_network (forbidden in v2.2)
    - call_llm (forbidden in v2.2)

    Args:
        manifest: SkillManifest to validate

    Raises:
        SkillManifestError: If permissions violate constraints
    """
    # v2.2 forbids call_network and call_llm for all skills
    if manifest.permissions.call_network:
        raise SkillManifestError(
            f"Skill '{manifest.id}' declares call_network=true, "
            "which is forbidden in v2.2"
        )

    if manifest.permissions.call_llm:
        raise SkillManifestError(
            f"Skill '{manifest.id}' declares call_llm=true, "
            "which is forbidden in v2.2"
        )

    # v2.2 forbids write_chapter_content and update_chapter_status for most skills
    # Only transform skills can potentially write_chapter_content,
    # but v2.2 spec doesn't allow any skill to do this yet
    if manifest.permissions.write_chapter_content:
        raise SkillManifestError(
            f"Skill '{manifest.id}' declares write_chapter_content=true, "
            "which is forbidden in v2.2"
        )

    if manifest.permissions.update_chapter_status:
        raise SkillManifestError(
            f"Skill '{manifest.id}' declares update_chapter_status=true, "
            "which is forbidden in v2.2"
        )


def validate_manifest_for_agent(
    manifest: SkillManifest,
    agent: str,
    stage: str,
) -> tuple[bool, str]:
    """Validate that a manifest allows execution for given agent and stage.

    Args:
        manifest: SkillManifest to validate
        agent: Agent name (e.g., "polisher", "editor", "qualityhub")
        stage: Stage name (e.g., "after_llm", "before_save", "final_gate")

    Returns:
        Tuple of (is_allowed, error_message)
    """
    if not manifest.enabled:
        return False, f"Skill '{manifest.id}' is disabled"

    if agent not in manifest.allowed_agents:
        return (
            False,
            f"Skill '{manifest.id}' is not allowed for agent '{agent}'. "
            f"Allowed agents: {manifest.allowed_agents}",
        )

    if stage not in manifest.allowed_stages:
        return (
            False,
            f"Skill '{manifest.id}' is not allowed for stage '{stage}'. "
            f"Allowed stages: {manifest.allowed_stages}",
        )

    return True, ""
