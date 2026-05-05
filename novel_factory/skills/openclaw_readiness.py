"""Read-only OpenClaw legacy Skill import readiness scanner.

This module never imports, copies, enables, mounts, or executes external
content. It only inspects local OpenClaw-style ``SKILL.md`` directories and
classifies them for a later manual import decision.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .import_models import parse_skill_md


OPENCLAW_AGENT_TARGETS = {
    "planner": "planner",
    "author": "author",
    "editor": "editor",
    "scout": "scout",
    "architect": "architect",
}

UNSUPPORTED_OPENCLAW_AGENTS = {"dispatcher", "secretary"}


def _default_openclaw_root() -> Path:
    return Path(__file__).resolve().parents[2] / "openclaw-agents"


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
    return normalized or "skill"


def _detect_source_agent(skill_dir: Path, root: Path) -> str | None:
    try:
        rel = skill_dir.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) >= 4 and parts[1] == "workspace" and parts[2] == "skills":
        return parts[0]
    return None


def _detect_features(skill_dir: Path, body: str) -> dict[str, bool]:
    body_lower = body.lower()
    return {
        "has_scripts": (skill_dir / "scripts").is_dir(),
        "has_references": (skill_dir / "references").is_dir(),
        "has_assets": (skill_dir / "assets").is_dir(),
        "has_rules": (skill_dir / "rules").is_dir(),
        "has_prompts": (skill_dir / "prompts").is_dir(),
        "uses_tools_db": "tools/db.py" in body_lower,
        "uses_shared_prompts": "shared.prompts" in body_lower,
        "mentions_python": "python3 " in body_lower or "python " in body_lower,
    }


def _classify_candidate(source_agent: str | None, features: dict[str, bool]) -> tuple[str, list[str], str | None]:
    blockers: list[str] = []
    target_agent = OPENCLAW_AGENT_TARGETS.get(source_agent or "")

    if source_agent in UNSUPPORTED_OPENCLAW_AGENTS or not target_agent:
        blockers.append("OpenClaw agent has no direct Novelos workflow target")

    if features["has_scripts"]:
        blockers.append("Contains scripts; requires manual safety review")
    if features["uses_tools_db"]:
        blockers.append("References OpenClaw tools/db.py; needs API/repository adapter")
    if features["uses_shared_prompts"]:
        blockers.append("References OpenClaw shared prompts; needs prompt adapter")
    if features["mentions_python"]:
        blockers.append("Mentions shell/python commands; verify no runtime command dependency")

    if source_agent in UNSUPPORTED_OPENCLAW_AGENTS or not target_agent:
        return "not_recommended", blockers, target_agent
    if blockers:
        return "needs_adapter", blockers, target_agent
    return "import_ready", blockers, target_agent


def scan_openclaw_readiness(root: str | Path | None = None) -> dict[str, Any]:
    """Scan local OpenClaw skills and classify import readiness.

    Args:
        root: Optional OpenClaw root. Defaults to repo-local ``openclaw-agents``.

    Returns:
        Dict suitable for API envelope data.
    """
    root_path = Path(root).expanduser().resolve() if root else _default_openclaw_root()
    if not root_path.exists():
        return {
            "root": str(root_path),
            "root_exists": False,
            "total": 0,
            "summary": {"import_ready": 0, "needs_adapter": 0, "not_recommended": 0, "invalid": 0},
            "candidates": [],
            "warnings": ["OpenClaw legacy workspace not found"],
        }

    candidates: list[dict[str, Any]] = []
    summary = {"import_ready": 0, "needs_adapter": 0, "not_recommended": 0, "invalid": 0}

    for skill_md in sorted(root_path.glob("*/workspace/skills/*/SKILL.md")):
        skill_dir = skill_md.parent
        source_agent = _detect_source_agent(skill_dir, root_path)
        rel_path = skill_dir.relative_to(root_path)

        try:
            frontmatter, body = parse_skill_md(skill_md)
            name = str(frontmatter.get("name") or skill_dir.name)
            description = str(frontmatter.get("description") or "")
            features = _detect_features(skill_dir, body)
            status, blockers, target_agent = _classify_candidate(source_agent, features)
            candidate_id = f"openclaw-{_slug(source_agent or 'unknown')}-{_slug(name)}"
            error = None
        except Exception as exc:  # pragma: no cover - exact parse errors vary
            name = skill_dir.name
            description = ""
            features = {}
            status = "invalid"
            blockers = [str(exc)]
            target_agent = None
            candidate_id = f"openclaw-{_slug(source_agent or 'unknown')}-{_slug(skill_dir.name)}"
            error = str(exc)

        summary[status] += 1
        candidates.append({
            "id": candidate_id,
            "name": name,
            "description": description,
            "source_agent": source_agent,
            "target_agent": target_agent,
            "source_path": str(rel_path),
            "status": status,
            "features": features,
            "blockers": blockers,
            "error": error,
        })

    return {
        "root": str(root_path),
        "root_exists": True,
        "total": len(candidates),
        "summary": summary,
        "candidates": candidates,
        "warnings": [],
    }
