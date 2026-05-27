"""Preflight diagnostics for chapter generation.

v6.7.2: Lightweight checks that expose memory pressure and duplicates
before chapter generation starts. Unlike hard guards, preflight checks
emit warnings and diagnostics without blocking the workflow.

These checks complement memory_governance.audit_project_memory by being
integrated into the run guard flow, making issues visible at the exact
moment a user tries to start chapter generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PreflightWarning:
    """A single preflight warning.

    Attributes:
        code: Warning code (e.g., "duplicate_characters").
        message: Human-readable warning message.
        severity: "warning" or "info".
        details: Additional structured details.
    """

    code: str
    message: str
    severity: str = "warning"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreflightResult:
    """Result of preflight checks.

    Attributes:
        ok: True if no blocking issues (preflight never blocks).
        warnings: List of preflight warnings.
        diagnostics: Detailed diagnostic data.
    """

    ok: bool = True  # Preflight never blocks, so ok is always True
    warnings: list[PreflightWarning] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ok": self.ok,
            "warnings": [
                {
                    "code": w.code,
                    "message": w.message,
                    "severity": w.severity,
                    "details": w.details,
                }
                for w in self.warnings
            ],
            "diagnostics": self.diagnostics,
        }


def check_preflight_diagnostics(
    repo: Any,
    project_id: str,
    *,
    limits: dict[str, int] | None = None,
) -> PreflightResult:
    """Run lightweight preflight checks before chapter generation.

    This function checks for:
    1. Duplicate characters (same name)
    2. Duplicate world_settings (same title)
    3. Story facts pressure (count exceeds threshold)
    4. Memory items pressure (count exceeds threshold)
    5. Context character pressure (total chars exceeds threshold)

    Unlike run guards, preflight checks do NOT block generation.
    They only emit warnings to make issues visible.

    Args:
        repo: Repository instance.
        project_id: Project ID to check.
        limits: Optional custom limits for pressure thresholds.

    Returns:
        PreflightResult with warnings and diagnostics.
    """
    from .memory_governance import audit_project_memory, DEFAULT_LIMITS

    limits = {**DEFAULT_LIMITS, **(limits or {})}
    warnings: list[PreflightWarning] = []

    # Run memory governance audit
    governance_result = audit_project_memory(repo, project_id, limits=limits)

    # Extract duplicates
    duplicates = governance_result.get("duplicates", {})
    duplicate_groups = governance_result.get("duplicate_groups", {})

    # Check for duplicate characters
    duplicate_characters = duplicates.get("characters", [])
    if duplicate_characters:
        char_groups = duplicate_groups.get("characters", [])
        warnings.append(
            PreflightWarning(
                code="duplicate_characters",
                message=f"发现 {len(duplicate_characters)} 个重复角色名，可能导致上下文膨胀",
                severity="warning",
                details={
                    "count": len(duplicate_characters),
                    "examples": [d["value"] for d in duplicate_characters[:5]],
                    "groups": char_groups[:5] if char_groups else [],
                    "recommended_actions": [
                        {
                            "code": "review_duplicate_characters",
                            "label": "查看重复角色",
                            "severity": "warning",
                        },
                    ],
                },
            )
        )

    # Check for duplicate world_settings
    duplicate_world_settings = duplicates.get("world_settings", [])
    if duplicate_world_settings:
        world_groups = duplicate_groups.get("world_settings", [])
        warnings.append(
            PreflightWarning(
                code="duplicate_world_settings",
                message=f"发现 {len(duplicate_world_settings)} 个重复世界观设定标题，可能导致上下文膨胀",
                severity="warning",
                details={
                    "count": len(duplicate_world_settings),
                    "examples": [d["value"] for d in duplicate_world_settings[:5]],
                    "groups": world_groups[:5] if world_groups else [],
                    "recommended_actions": [
                        {
                            "code": "review_duplicate_world_settings",
                            "label": "查看重复世界观",
                            "severity": "warning",
                        },
                    ],
                },
            )
        )

    # Check for story_facts pressure
    counts = governance_result.get("counts", {})
    story_facts_count = counts.get("story_facts", 0)
    story_facts_limit = limits.get("story_facts", 160)
    if story_facts_count > story_facts_limit:
        warnings.append(
            PreflightWarning(
                code="story_facts_pressure",
                message=f"故事事实数量 ({story_facts_count}) 超过阈值 ({story_facts_limit})，可能影响上下文质量",
                severity="warning",
                details={
                    "count": story_facts_count,
                    "limit": story_facts_limit,
                    "recommended_actions": [
                        {
                            "code": "review_story_facts",
                            "label": "查看故事事实",
                            "severity": "warning",
                        },
                        {
                            "code": "summarize_low_relevance_facts",
                            "label": "整理低相关事实",
                            "severity": "info",
                        },
                    ],
                },
            )
        )

    # Check for memory_items pressure
    memory_items_count = counts.get("memory_items", 0)
    memory_items_limit = limits.get("memory_items", 240)
    if memory_items_count > memory_items_limit:
        warnings.append(
            PreflightWarning(
                code="memory_items_pressure",
                message=f"记忆项数量 ({memory_items_count}) 超过阈值 ({memory_items_limit})，可能影响上下文质量",
                severity="warning",
                details={
                    "count": memory_items_count,
                    "limit": memory_items_limit,
                    "recommended_actions": [
                        {
                            "code": "review_memory_items",
                            "label": "查看记忆项",
                            "severity": "warning",
                        },
                        {
                            "code": "summarize_low_relevance_memory",
                            "label": "整理低相关记忆",
                            "severity": "info",
                        },
                    ],
                },
            )
        )

    # Check for context character pressure
    context_chars = counts.get("context_chars", 0)
    context_chars_limit = limits.get("context_chars", 48000)
    if context_chars > context_chars_limit:
        warnings.append(
            PreflightWarning(
                code="context_pressure",
                message=f"上下文字符总量 ({context_chars}) 超过阈值 ({context_chars_limit})，建议清理低相关性记忆",
                severity="warning",
                details={
                    "count": context_chars,
                    "limit": context_chars_limit,
                    "recommended_actions": [
                        {
                            "code": "review_context_pressure",
                            "label": "查看上下文压力",
                            "severity": "warning",
                        },
                        {
                            "code": "prune_low_relevance_memory",
                            "label": "清理低相关记忆",
                            "severity": "info",
                        },
                    ],
                },
            )
        )

    # Build diagnostics
    diagnostics = {
        "counts": counts,
        "duplicate_count": governance_result.get("duplicate_group_count", 0),
        "pressure_count": len(governance_result.get("pressures", [])),
    }

    return PreflightResult(
        ok=True,  # Preflight never blocks
        warnings=warnings,
        diagnostics=diagnostics,
    )
