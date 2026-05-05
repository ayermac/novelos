"""Read-only universal Skill import readiness scanner.

OpenClaw is one supported source, not the boundary of the system. This module
also scans local Codex/agent skill roots when present. It never imports,
copies, enables, mounts, or executes external content.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .import_models import build_import_plan, parse_skill_md


SOURCE_LABELS = {
    "openclaw": "OpenClaw legacy workspace",
    "codex": "Codex user skills",
    "agents": "Agent user skills",
}

OPENCLAW_AGENT_TARGETS = {
    "planner": "planner",
    "author": "author",
    "editor": "editor",
    "scout": "scout",
    "architect": "architect",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_roots(openclaw_root: str | Path | None = None) -> dict[str, Path]:
    home = Path.home()
    return {
        "openclaw": Path(openclaw_root).expanduser().resolve() if openclaw_root else _repo_root() / "openclaw-agents",
        "codex": home / ".codex" / "skills",
        "agents": home / ".agents" / "skills",
    }


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
    return normalized or "skill"


def _detect_openclaw_source_agent(skill_dir: Path, root: Path) -> str | None:
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


def _classify_candidate(
    source_type: str,
    source_agent: str | None,
    features: dict[str, bool],
) -> tuple[str, list[str], str | None]:
    blockers: list[str] = []
    target_agent = OPENCLAW_AGENT_TARGETS.get(source_agent or "") if source_type == "openclaw" else None

    if features["has_scripts"]:
        blockers.append("Contains scripts; requires manual safety review")
    if features["uses_tools_db"]:
        blockers.append("References OpenClaw tools/db.py; needs API/repository adapter")
    if features["uses_shared_prompts"]:
        blockers.append("References OpenClaw shared prompts; needs prompt adapter")
    if features["mentions_python"]:
        blockers.append("Mentions shell/python commands; verify no runtime command dependency")

    if blockers:
        return "needs_adapter", blockers, target_agent
    if target_agent:
        return "import_ready", blockers, target_agent
    return "manual_ready", blockers, target_agent


def _iter_skill_dirs(source_type: str, root: Path) -> list[Path]:
    if not root.exists():
        return []
    if source_type == "openclaw":
        return [path.parent for path in sorted(root.glob("*/workspace/skills/*/SKILL.md"))]
    return [path.parent for path in sorted(root.glob("*/SKILL.md"))]


def scan_import_readiness(openclaw_root: str | Path | None = None) -> dict[str, Any]:
    """Scan local universal Skill sources and classify import readiness."""
    roots = _default_roots(openclaw_root)
    candidates: list[dict[str, Any]] = []
    summary = {
        "import_ready": 0,
        "needs_adapter": 0,
        "manual_ready": 0,
        "already_registered": 0,
        "invalid": 0,
    }
    sources: list[dict[str, Any]] = []

    for source_type, root in roots.items():
        root_exists = root.exists()
        skill_dirs = _iter_skill_dirs(source_type, root)
        sources.append({
            "type": source_type,
            "label": SOURCE_LABELS[source_type],
            "root": str(root),
            "root_exists": root_exists,
            "count": len(skill_dirs),
        })

        for skill_dir in skill_dirs:
            rel_path = skill_dir.relative_to(root)
            source_agent = _detect_openclaw_source_agent(skill_dir, root) if source_type == "openclaw" else None

            try:
                frontmatter, body = parse_skill_md(skill_dir / "SKILL.md")
                name = str(frontmatter.get("name") or skill_dir.name)
                description = str(frontmatter.get("description") or "")
                features = _detect_features(skill_dir, body)
                status, blockers, target_agent = _classify_candidate(source_type, source_agent, features)
                candidate_id = f"{source_type}-{_slug(source_agent or 'manual')}-{_slug(name)}"
                error = None
            except Exception as exc:  # pragma: no cover - exact parse errors vary
                name = skill_dir.name
                description = ""
                features = {}
                status = "invalid"
                blockers = [str(exc)]
                target_agent = None
                candidate_id = f"{source_type}-{_slug(source_agent or 'manual')}-{_slug(skill_dir.name)}"
                error = str(exc)

            summary[status] += 1
            candidates.append({
                "id": candidate_id,
                "name": name,
                "description": description,
                "source_type": source_type,
                "source_label": SOURCE_LABELS[source_type],
                "source_agent": source_agent,
                "target_agent": target_agent,
                "source_path": str(rel_path),
                "status": status,
                "features": features,
                "blockers": blockers,
                "error": error,
            })

    missing = [source["label"] for source in sources if not source["root_exists"]]
    warnings = [f"Skill source not found: {label}" for label in missing]

    return {
        "sources": sources,
        "total": len(candidates),
        "summary": summary,
        "candidates": candidates,
        "warnings": warnings,
    }


def scan_openclaw_readiness(root: str | Path | None = None) -> dict[str, Any]:
    """Backward-compatible OpenClaw-only readiness view."""
    all_data = scan_import_readiness(openclaw_root=root)
    openclaw_source = next(source for source in all_data["sources"] if source["type"] == "openclaw")
    candidates = [candidate for candidate in all_data["candidates"] if candidate["source_type"] == "openclaw"]
    summary = {
        "import_ready": 0,
        "needs_adapter": 0,
        "manual_ready": 0,
        "invalid": 0,
    }
    for candidate in candidates:
        summary[candidate["status"]] += 1

    return {
        "root": openclaw_source["root"],
        "root_exists": openclaw_source["root_exists"],
        "total": len(candidates),
        "summary": summary,
        "candidates": candidates,
        "warnings": [] if openclaw_source["root_exists"] else ["OpenClaw legacy workspace not found"],
    }


def build_import_plan_preview(
    source_type: str,
    source_path: str,
    openclaw_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build a read-only import plan for any scanned Skill candidate."""
    roots = _default_roots(openclaw_root)
    if source_type not in roots:
        return {"ok": False, "error": f"Unknown skill source type: {source_type}", "data": {}}

    root = roots[source_type]
    if not root.exists():
        return {"ok": False, "error": f"Skill source not found: {SOURCE_LABELS[source_type]}", "data": {}}

    candidate_path = (root / source_path).resolve()
    try:
        candidate_path.relative_to(root.resolve())
    except ValueError:
        return {"ok": False, "error": "source_path escapes skill source root", "data": {}}

    if not candidate_path.is_dir():
        return {"ok": False, "error": f"Skill directory not found: {source_path}", "data": {}}
    if not (candidate_path / "SKILL.md").exists():
        return {"ok": False, "error": f"Skill missing SKILL.md: {source_path}", "data": {}}

    plan = build_import_plan(candidate_path)
    if plan.get("ok") and isinstance(plan.get("data"), dict):
        plan["data"]["source_type"] = source_type
        plan["data"]["source_label"] = SOURCE_LABELS[source_type]
        plan["data"]["source_path"] = source_path
        plan["data"]["root"] = str(root)
        plan["data"]["read_only"] = True
    return plan


def build_openclaw_import_plan(source_path: str, root: str | Path | None = None) -> dict[str, Any]:
    """Backward-compatible OpenClaw import plan preview."""
    return build_import_plan_preview("openclaw", source_path, root)
