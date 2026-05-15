"""Memory Patch Validator — v2.0.0 package handler."""

from __future__ import annotations

from typing import Any

from novel_factory.skills.base import ValidatorSkill


class MemoryPatchValidatorSkill(ValidatorSkill):
    """Validate MemoryCurator patches before batch creation."""

    skill_id = "memory-patch-validator"
    skill_type = "validator"
    version = "2.0.0"

    _allowed_tables = {
        "characters",
        "world_settings",
        "factions",
        "outlines",
        "plot_holes",
        "instructions",
        "story_facts",
    }
    _allowed_operations = {"create", "update", "resolve", "deprecate"}

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        patches = payload.get("patches", [])
        issues: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not isinstance(patches, list):
            issues.append(_issue("invalid_patches", "patches 必须是列表", "返回 patches: [] 或 patch 对象列表。"))
            patches = []

        for index, patch in enumerate(patches, start=1):
            if not isinstance(patch, dict):
                issues.append(_issue("invalid_patch", f"第 {index} 个 patch 不是对象", "使用结构化 patch。", index=index))
                continue

            target_table = patch.get("target_table")
            operation = patch.get("operation")
            data = patch.get("data")
            confidence = patch.get("confidence")
            evidence = str(patch.get("evidence_text") or "").strip()

            if target_table not in self._allowed_tables:
                issues.append(_issue("invalid_target_table", f"第 {index} 个 patch target_table 无效: {target_table}", "使用允许的项目资料表。", index=index))
            if operation not in self._allowed_operations:
                issues.append(_issue("invalid_operation", f"第 {index} 个 patch operation 无效: {operation}", "使用 create/update/resolve/deprecate。", index=index))
            if not isinstance(data, dict) or not data:
                issues.append(_issue("invalid_data", f"第 {index} 个 patch 缺少 data", "提供目标表字段数据。", index=index))
            if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                issues.append(_issue("invalid_confidence", f"第 {index} 个 patch confidence 必须在 0-1", "提供 0.0 到 1.0 的置信度。", index=index))
            elif float(confidence) < 0.5:
                warnings.append(f"第 {index} 个 patch 置信度偏低。")
            if not evidence:
                issues.append(_issue("missing_evidence", f"第 {index} 个 patch 缺少 evidence_text", "提供原文证据片段。", index=index))

        return {
            "ok": not issues,
            "error": "; ".join(issue["message"] for issue in issues[:3]) if issues else None,
            "data": {
                "patch_count": len(patches),
                "issues": issues,
                "warnings": warnings,
                "blocking": bool(issues),
            },
        }


def _issue(code: str, message: str, suggestion: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "suggestion": suggestion, **extra}
