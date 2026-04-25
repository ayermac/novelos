"""Plot verifier — validates that required plot points are addressed.

v1.2 extends from soft check to structured result with:
- missing_plants: plots required to plant but not referenced in content
- missing_resolves: plots required to resolve but not referenced in content
- invalid_refs: plot refs that don't exist in plot_holes table
- warnings: soft issues

Also checks plot_holes table for existence and resolvability.
"""

from __future__ import annotations

import json
from typing import Any

from ..db.repository import Repository
from ..models.quality import PlotVerifyResult


def check_plot_coverage(
    instruction: dict[str, Any] | None,
    used_plot_refs: list[str],
) -> list[str]:
    """Legacy soft check — returns warnings only.

    Args:
        instruction: The chapter instruction dict (may be None).
        used_plot_refs: Plot refs that the author claims to have used.

    Returns:
        List of warning messages for missing plot coverage.
    """
    result = check_plot_coverage_structured(instruction, used_plot_refs)
    return result.warnings + [
        f"未埋设伏笔: {ref}" for ref in result.missing_plants
    ] + [
        f"未兑现伏笔: {ref}" for ref in result.missing_resolves
    ]


def check_plot_coverage_structured(
    instruction: dict[str, Any] | None,
    used_plot_refs: list[str],
    repo: Repository | None = None,
    project_id: str | None = None,
) -> PlotVerifyResult:
    """Check plot coverage with structured result.

    Args:
        instruction: The chapter instruction dict (may be None).
        used_plot_refs: Plot refs that the author claims to have used.
        repo: Optional Repository for plot_holes validation.
        project_id: Required if repo is provided.

    Returns:
        PlotVerifyResult with missing_plants, missing_resolves, invalid_refs, warnings.
    """
    result = PlotVerifyResult()

    if not instruction:
        result.warnings.append("无写作指令，跳过伏笔检查")
        return result

    # Parse plots_to_plant and plots_to_resolve from instruction
    plots_to_plant = _parse_json_list(instruction.get("plots_to_plant", "[]"))
    plots_to_resolve = _parse_json_list(instruction.get("plots_to_resolve", "[]"))

    # Check required plots are addressed
    for plot_ref in plots_to_plant:
        if plot_ref not in used_plot_refs:
            result.missing_plants.append(plot_ref)

    for plot_ref in plots_to_resolve:
        if plot_ref not in used_plot_refs:
            result.missing_resolves.append(plot_ref)

    # Validate refs against plot_holes table
    if repo and project_id:
        _validate_against_plot_holes(
            plots_to_plant + plots_to_resolve, repo, project_id, result,
        )

    return result


def check_plot_in_content(
    instruction: dict[str, Any] | None,
    content: str,
    used_plot_refs: list[str],
) -> PlotVerifyResult:
    """Check that plot requirements are actually present in the content text.

    This goes beyond used_plot_refs and checks if the content text
    contains mentions related to the required plot codes.

    Args:
        instruction: The chapter instruction dict.
        content: The actual chapter content text.
        used_plot_refs: Plot refs that the author claims to have used.

    Returns:
        PlotVerifyResult including content-level checks.
    """
    # R1: Defensive handling for None content
    if content is None:
        content = ""
    
    result = check_plot_coverage_structured(instruction, used_plot_refs)

    if not instruction or not content:
        return result

    # For refs that are in used_plot_refs, also verify they appear in content
    plots_to_plant = _parse_json_list(instruction.get("plots_to_plant", "[]"))
    plots_to_resolve = _parse_json_list(instruction.get("plots_to_resolve", "[]"))

    all_required = set(plots_to_plant + plots_to_resolve)
    for ref in all_required:
        if ref in used_plot_refs and ref not in content:
            result.warnings.append(
                f"伏笔 '{ref}' 在 used_plot_refs 中但未在正文中直接提及"
            )

    return result


def _validate_against_plot_holes(
    refs: list[str],
    repo: Repository,
    project_id: str,
    result: PlotVerifyResult,
) -> None:
    """Validate that plot refs exist in the plot_holes table and are in valid state."""
    try:
        pending_plots = repo.get_pending_plots(project_id)
    except Exception:
        result.warnings.append("无法读取伏笔库，跳过引用验证")
        return

    # Build set of valid plot codes
    valid_codes = {p.get("code", "") for p in pending_plots}

    # Also get all plots (not just pending) for code existence check
    all_codes = valid_codes.copy()
    try:
        conn = repo._conn()
        rows = conn.execute(
            "SELECT code, status FROM plot_holes WHERE project_id=?", (project_id,)
        ).fetchall()
        conn.close()
        for row in rows:
            code = row["code"]
            all_codes.add(code)
            # Check if a resolved plot is being referenced for resolution
            status = row["status"]
            if status == "resolved" and code in refs:
                result.warnings.append(
                    f"伏笔 '{code}' 已兑现（状态: {status}），不应再次兑现"
                )
    except Exception:
        pass

    # Check for invalid refs
    for ref in refs:
        if ref not in all_codes:
            result.invalid_refs.append(ref)


def _parse_json_list(value: str | list) -> list[str]:
    """Parse a JSON string or list into a list of strings."""
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
