"""Deterministic Agent capability validator Skills."""

from __future__ import annotations

import json
from typing import Any

from .base import ValidatorSkill


class ChapterObjectiveCheckerSkill(ValidatorSkill):
    """Validate Planner chapter objectives and required events."""

    skill_id = "chapter-objective-checker"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = payload.get("chapter_brief") if isinstance(payload.get("chapter_brief"), dict) else payload
        objective = str(brief.get("objective") or "").strip()
        events = _as_list(brief.get("required_events") or brief.get("key_events"))
        constraints = _as_list(brief.get("constraints"))
        issues: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not objective:
            issues.append(_issue("missing_objective", "章节目标为空", "为本章补充具体目标。"))
        elif len(objective) < 8:
            issues.append(_issue("vague_objective", "章节目标过短，缺少可执行信息", "写清主角状态、行动和结果。"))

        vague_terms = ("成长", "变强", "推进剧情", "继续冒险", "发生变化")
        if objective and any(term in objective for term in vague_terms) and not events:
            issues.append(_issue("abstract_objective", "章节目标偏抽象且未列出关键事件", "补充可落地的事件或约束。"))

        if not events:
            issues.append(_issue("missing_required_events", "缺少 required_events/key_events", "至少列出 1 个本章必须发生的事件。"))
        elif len([event for event in events if str(event).strip()]) < len(events):
            warnings.append("required_events 中存在空事件。")

        if not constraints:
            warnings.append("未提供 constraints，建议列出事实、视角或节奏约束。")

        return {
            "ok": not issues,
            "error": "; ".join(issue["message"] for issue in issues) if issues else None,
            "data": {
                "score": max(0, 100 - len(issues) * 35 - len(warnings) * 10),
                "issues": issues,
                "warnings": warnings,
                "blocking": bool(issues),
            },
        }


class SceneConflictCheckerSkill(ValidatorSkill):
    """Validate Screenwriter scene beats for goal/conflict/turn/hook."""

    skill_id = "scene-conflict-checker"
    skill_type = "validator"
    version = "1.0.0"

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


class EventCoverageCheckerSkill(ValidatorSkill):
    """Validate Author output against required events."""

    skill_id = "event-coverage-checker"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or payload.get("text") or "")
        required_events = _as_list(payload.get("required_events") or payload.get("key_events"))
        implemented_events = _as_list(payload.get("implemented_events"))
        issues: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not content.strip():
            issues.append(_issue("missing_content", "正文为空", "生成正文后再进入保存。"))

        missing: list[str] = []
        for event in required_events:
            event_text = str(event).strip()
            if not event_text:
                continue
            covered_by_declared = any(_loosely_matches(event_text, str(done)) for done in implemented_events)
            covered_by_content = event_text in content
            if not covered_by_declared and not covered_by_content:
                missing.append(event_text)

        if required_events and not implemented_events:
            warnings.append("Author 输出未声明 implemented_events。")
        if missing:
            issues.append(_issue("missing_required_events", f"正文可能遗漏 {len(missing)} 个必需事件", "检查正文或 implemented_events 是否覆盖写作指令。", missing_events=missing))

        coverage = 1.0
        if required_events:
            coverage = max(0.0, (len(required_events) - len(missing)) / len(required_events))

        return {
            "ok": not issues,
            "error": "; ".join(issue["message"] for issue in issues) if issues else None,
            "data": {
                "coverage": coverage,
                "missing_events": missing,
                "issues": issues,
                "warnings": warnings,
                "blocking": bool(issues),
            },
        }


class MemoryPatchValidatorSkill(ValidatorSkill):
    """Validate MemoryCurator patches before batch creation."""

    skill_id = "memory-patch-validator"
    skill_type = "validator"
    version = "1.0.0"

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


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [part.strip() for part in text.replace("，", ",").split(",") if part.strip()]
    return [value]


def _issue(code: str, message: str, suggestion: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "suggestion": suggestion, **extra}


def _loosely_matches(required: str, implemented: str) -> bool:
    if not required or not implemented:
        return False
    if required in implemented or implemented in required:
        return True
    required_tokens = {token for token in required.replace("，", ",").replace("、", ",").split(",") if token}
    return any(token and token in implemented for token in required_tokens)
