"""Scene Conflict Checker — v2.0.0 package handler."""

from __future__ import annotations

from typing import Any

from novel_factory.skills.base import ValidatorSkill


class SceneConflictCheckerSkill(ValidatorSkill):
    """Validate Screenwriter scene beats for goal/conflict/turn/hook."""

    skill_id = "scene-conflict-checker"
    skill_type = "validator"
    version = "2.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        beats = payload.get("scene_beats", [])
        issues: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not isinstance(beats, list) or not beats:
            issues.append(_issue("missing_scene_beats", "缺少 scene_beats", "至少拆解 1 个场景 beat。"))
            beats = []

        required_fields = ("scene_goal", "conflict", "turn", "hook")
        for index, beat in enumerate(beats, start=1):
            if not isinstance(beat, dict):
                issues.append(_issue("invalid_scene_beat", f"第 {index} 个 scene beat 不是对象", "使用结构化 scene beat。"))
                continue
            for field in required_fields:
                if not str(beat.get(field) or "").strip():
                    issues.append(_issue(f"missing_{field}", f"第 {index} 场缺少 {field}", "补齐场景目标、冲突、转折和钩子。", sequence=index))
            if not beat.get("plot_refs"):
                warnings.append(f"第 {index} 场未声明 plot_refs。")

        return {
            "ok": not issues,
            "error": "; ".join(issue["message"] for issue in issues[:3]) if issues else None,
            "data": {
                "scene_count": len(beats),
                "issues": issues,
                "warnings": warnings,
                "blocking": bool(issues),
            },
        }


def _issue(code: str, message: str, suggestion: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "suggestion": suggestion, **extra}
