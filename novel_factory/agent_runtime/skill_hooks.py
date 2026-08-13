"""Shared Agent Skill hook execution helpers.

This module keeps Skill runtime behavior consistent across agents:
run configured skills, persist ``skill_runs``, collect structured findings,
and keep non-critical failures from crashing the workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class AgentSkillHookResult:
    """Structured result returned by an Agent Skill hook."""

    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    transforms: list[dict[str, Any]] = field(default_factory=list)
    context_fragments: list[dict[str, Any]] = field(default_factory=list)
    validation_issues: list[dict[str, Any]] = field(default_factory=list)
    skill_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def blocking_error(self) -> str | None:
        """Return a compact blocking error if the hook failed closed."""
        if self.ok or not self.errors:
            return None
        return "; ".join(self.errors)


def run_agent_skills(
    *,
    repo: Any,
    skill_registry: Any | None,
    project_id: str,
    chapter_number: int,
    agent: str,
    stage: str,
    payload: dict[str, Any],
    project_overrides: dict[str, Any] | None = None,
    skill_type_hint: str | None = None,
    fail_closed_ids: set[str] | None = None,
    honor_manifest_failure_policy: bool = False,
) -> AgentSkillHookResult:
    """Run and persist configured Skills for an agent stage.

    Non-critical failures are recorded as warnings. A failed Skill becomes
    blocking only when its id is in ``fail_closed_ids`` or when
    ``honor_manifest_failure_policy`` is enabled and the manifest declares
    ``failure_policy.on_error: block``.
    """

    result = AgentSkillHookResult()
    if skill_registry is None:
        return result

    started = time.perf_counter()
    try:
        raw_results = skill_registry.run_skills_for_agent(
            agent=agent,
            stage=stage,
            payload=payload,
            project_overrides=project_overrides,
        )
    except Exception as exc:
        logger.warning("%s.%s Skill hook failed before execution: %s", agent, stage, exc)
        result.warnings.append(f"{agent}.{stage} Skill hook failed: {exc}")
        return result

    fail_closed = fail_closed_ids or set()
    for item in raw_results or []:
        skill_id = str(item.get("skill_id") or "")
        envelope = item.get("result") or {}
        data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
        ok = bool(envelope.get("ok", False))
        error = envelope.get("error")
        skill_type = skill_type_hint or _skill_type(skill_registry, skill_id) or "validator"
        duration_ms = int((time.perf_counter() - started) * 1000)

        persisted = {
            "skill_id": skill_id,
            "agent": agent,
            "stage": stage,
            "ok": ok,
            "error": error,
            "data": data,
        }
        result.skill_results.append(persisted)

        try:
            repo.save_skill_run(
                project_id=project_id,
                skill_id=skill_id,
                skill_type=skill_type,
                ok=ok,
                error=error,
                input_json=_compact_payload(payload),
                output_json=data,
                duration_ms=duration_ms,
                chapter_number=chapter_number,
                agent_id=agent,
                stage=stage,
            )
        except Exception as exc:
            logger.warning("%s.%s failed to save skill_run for %s: %s", agent, stage, skill_id, exc)
            result.warnings.append(f"failed to save skill_run for {skill_id}: {exc}")

        _collect_data(result, skill_id, data)

        if not ok:
            message = f"{skill_id}: {error or 'Skill failed'}"
            if skill_id in fail_closed or (
                honor_manifest_failure_policy
                and _manifest_blocks_on_error(skill_registry, skill_id)
            ):
                result.ok = False
                result.errors.append(message)
            else:
                result.warnings.append(message)

    return result


def _skill_type(skill_registry: Any, skill_id: str) -> str | None:
    config = getattr(skill_registry, "skills_config", {}).get(skill_id, {})
    manifest = None
    try:
        manifest = skill_registry.get_manifest(skill_id)
    except Exception:
        manifest = None
    if manifest:
        return getattr(manifest, "kind", None)
    return config.get("type")


def _manifest_blocks_on_error(skill_registry: Any, skill_id: str) -> bool:
    try:
        manifest = skill_registry.get_manifest(skill_id)
    except Exception:
        return False
    if not manifest:
        return False
    return getattr(manifest.failure_policy, "on_error", "warn") == "block"


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if key == "_repo":
            continue
        if isinstance(value, str):
            compact[key] = value[:500]
        elif isinstance(value, list):
            compact[key] = value[:20]
        elif isinstance(value, dict):
            compact[key] = value
        else:
            compact[key] = value
    return compact


def _collect_data(result: AgentSkillHookResult, skill_id: str, data: dict[str, Any]) -> None:
    if not data:
        return

    for key in ("issues", "validation_issues"):
        values = data.get(key)
        if isinstance(values, list):
            for issue in values:
                if isinstance(issue, dict):
                    result.validation_issues.append({"skill_id": skill_id, **issue})
                else:
                    result.validation_issues.append({"skill_id": skill_id, "message": str(issue)})

    warnings = data.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            result.warnings.append(f"{skill_id}: {warning}")

    for key in ("humanized_text", "transformed_text"):
        if isinstance(data.get(key), str):
            result.transforms.append({"skill_id": skill_id, "content": data[key], "field": key})

    fragments = data.get("context_fragments")
    if isinstance(fragments, list):
        for fragment in fragments:
            if isinstance(fragment, dict):
                result.context_fragments.append({"skill_id": skill_id, **fragment})
            else:
                result.context_fragments.append({"skill_id": skill_id, "content": str(fragment)})
