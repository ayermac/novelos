"""Quality Feedback Bridge (v6.6.1)

将 QualityHub.diagnose() 的 findings + dimensions 转换为适合注入
Agent prompt 的 compact feedback。不传递正文，只传 count/ratio/instruction。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Mapping from dimension key → polisher instruction template
_DIMENSION_INSTRUCTION_MAP: dict[str, str] = {
    "hook_strength": "章末增加推进感/悬念/未解问题，但不得新增重大事实",
    "character_motivation": "用动作、选择、对话补足角色动机，不写直白解释",
    "dialogue_naturalness": "对白增加打断、反问、省略、语气差异，避免功能性问答",
    "info_dump": "把连续说明拆入动作或环境反馈，减少旁白式 exposition",
    "show_dont_tell": "将直白心理词（感到/觉得/意识到）改为动作/神态/对白",
    "scene_immersion": "优先强化已有场景线索（光影/声音/气味/温度），不强塞设定",
    "pacing_control": "打破均匀段落，紧张处用短句，避免连续段落长度相近",
    "ai_trace": "删减模板句式、直白情绪词和宏大空泛判断",
    "narrative_quality": "增强叙事张力，让冲突和选择驱动情节推进",
}

# Severity ordering for sorting
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "warning": 3, "info": 4}

# Dimensions that are "polisher-fixable" (style/surface issues)
_POLISHER_DIMENSIONS = {
    "hook_strength",
    "dialogue_naturalness",
    "info_dump",
    "show_dont_tell",
    "scene_immersion",
    "pacing_control",
    "ai_trace",
}

# Dimensions that are "author-level" (structural/plot issues)
_AUTHOR_DIMENSIONS = {
    "character_motivation",
    "narrative_quality",
    "conflict_intensity",
}

# Score thresholds
_PRIORITY_THRESHOLD = 55   # below this → priority finding
_ADVISORY_THRESHOLD = 70   # below this → advisory finding


class QualityFeedback:
    """Compact feedback for agent consumption."""

    def __init__(
        self,
        priority_findings: list[dict[str, Any]],
        advisory_findings: list[dict[str, Any]],
        polisher_instructions: list[str],
        editor_notes: list[str],
        deferred_findings: list[dict[str, Any]],
        quality_risk_note: str | None = None,
    ):
        self.priority_findings = priority_findings
        self.advisory_findings = advisory_findings
        self.polisher_instructions = polisher_instructions
        self.editor_notes = editor_notes
        self.deferred_findings = deferred_findings
        self.quality_risk_note = quality_risk_note

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority_findings": self.priority_findings,
            "advisory_findings": self.advisory_findings,
            "polisher_instructions": self.polisher_instructions,
            "editor_notes": self.editor_notes,
            "deferred_findings": self.deferred_findings,
            "quality_risk_note": self.quality_risk_note,
        }

    def is_empty(self) -> bool:
        return (
            not self.priority_findings
            and not self.advisory_findings
            and not self.polisher_instructions
            and not self.editor_notes
        )


def build_compact_feedback(
    diagnose_result: dict[str, Any],
    max_priority: int = 5,
    max_advisory: int = 5,
    max_polisher_instructions: int = 5,
) -> QualityFeedback:
    """Convert QualityHub.diagnose() output to compact agent feedback.

    Args:
        diagnose_result: Output from QualityHub.diagnose()
        max_priority: Max priority findings to include
        max_advisory: Max advisory findings to include
        max_polisher_instructions: Max instructions for polisher

    Returns:
        QualityFeedback with categorized, limited findings.
    """
    dimensions: dict[str, float] = diagnose_result.get("dimensions", {})
    findings: list[dict[str, Any]] = diagnose_result.get("findings", [])
    metrics: dict[str, Any] = diagnose_result.get("metrics", {})

    priority_findings: list[dict[str, Any]] = []
    advisory_findings: list[dict[str, Any]] = []
    deferred_findings: list[dict[str, Any]] = []
    polisher_instructions: list[str] = []
    editor_notes: list[str] = []

    # --- 1. Classify findings by severity ---
    for finding in findings:
        severity = finding.get("severity", "info")
        code = finding.get("code", "")
        message = finding.get("message", "")
        evidence = finding.get("evidence")
        suggestion = finding.get("suggestion")

        compact = {
            "code": code,
            "message": _truncate(message, 120),
            "evidence": _compact_evidence(evidence),
            "suggestion": _truncate(suggestion, 120) if suggestion else None,
        }

        if severity in ("critical", "high"):
            priority_findings.append(compact)
        elif severity == "medium":
            advisory_findings.append(compact)
        else:
            deferred_findings.append(compact)

    # --- 2. Derive instructions from low dimensions ---
    for dim_key, score in dimensions.items():
        if dim_key in ("death_penalty",):
            continue  # Already covered by findings

        instruction = _DIMENSION_INSTRUCTION_MAP.get(dim_key)
        if not instruction:
            continue

        note = f"{dim_key}={score:.0f}"
        if score < _PRIORITY_THRESHOLD:
            if dim_key in _POLISHER_DIMENSIONS:
                polisher_instructions.append(f"【{note}】{instruction}")
            elif dim_key in _AUTHOR_DIMENSIONS:
                editor_notes.append(f"结构问题：{note} — {instruction}")
        elif score < _ADVISORY_THRESHOLD:
            if dim_key in _POLISHER_DIMENSIONS:
                polisher_instructions.append(f"【{note}，建议优化】{instruction}")
            elif dim_key in _AUTHOR_DIMENSIONS:
                editor_notes.append(f"结构建议：{note} — {instruction}")

    # --- 3. Add metric-based advisory notes ---
    dialogue_ratio = metrics.get("dialogue_ratio", 0)
    if isinstance(dialogue_ratio, (int, float)) and dialogue_ratio < 0.05:
        advisory_findings.append({
            "code": "LOW_DIALOGUE_RATIO",
            "message": "对白占比过低，章节可能以叙述为主",
            "evidence": f"ratio={dialogue_ratio:.3f}",
            "suggestion": "适当增加角色对话，让情节通过对话推进",
        })

    avg_sent_len = metrics.get("avg_sentence_length", 0)
    if isinstance(avg_sent_len, (int, float)) and avg_sent_len > 45:
        advisory_findings.append({
            "code": "LONG_SENTENCES",
            "message": "平均句长过长，可能影响阅读节奏",
            "evidence": f"avg={avg_sent_len:.1f} chars",
            "suggestion": "适当拆分长句，增加短句和断句",
        })

    # --- 4. Cap and deduplicate ---
    priority_findings = _deduplicate_findings(priority_findings)[:max_priority]
    advisory_findings = _deduplicate_findings(advisory_findings)[:max_advisory]
    polisher_instructions = _deduplicate_strings(polisher_instructions)[:max_polisher_instructions]
    editor_notes = _deduplicate_strings(editor_notes)

    # --- 5. Build risk note ---
    risk_parts: list[str] = []
    if priority_findings:
        risk_parts.append(f"{len(priority_findings)} 项高优先级问题")
    if polisher_instructions:
        risk_parts.append(f"{len(polisher_instructions)} 项润色修复重点")
    quality_risk_note = "；".join(risk_parts) if risk_parts else None

    return QualityFeedback(
        priority_findings=priority_findings,
        advisory_findings=advisory_findings,
        polisher_instructions=polisher_instructions,
        editor_notes=editor_notes,
        deferred_findings=deferred_findings,
        quality_risk_note=quality_risk_note,
    )


def format_polisher_context(feedback: QualityFeedback) -> str:
    """Format feedback as a prompt section for Polisher."""
    if feedback.is_empty():
        return ""

    lines: list[str] = ["【本轮质量诊断修复重点】"]
    lines.append("以下诊断结果来自 deterministic quality check，优先按顺序修复，但不得为改分数而改剧情事实。")

    if feedback.polisher_instructions:
        lines.append("\n修复重点（按优先级）：")
        for i, instr in enumerate(feedback.polisher_instructions, 1):
            lines.append(f"{i}. {instr}")

    if feedback.priority_findings:
        lines.append("\n高优先级问题：")
        for f in feedback.priority_findings:
            lines.append(f"  - [{f['code']}] {f['message']}")

    if feedback.advisory_findings:
        lines.append("\n参考建议：")
        for f in feedback.advisory_findings[:3]:
            lines.append(f"  - [{f['code']}] {f['message']}")

    lines.append(
        "\n注意："
        "1. 优先修复诊断重点；"
        "2. 不得为修分数改剧情事实；"
        "3. 无法安全修复的问题保留原样，不强行修改；"
        "4. 修复后请在 summary 中说明处理了哪些诊断项。"
    )

    return "\n".join(lines)


def format_editor_context(feedback: QualityFeedback) -> str:
    """Format feedback as a prompt section for Editor."""
    if feedback.is_empty():
        return ""

    lines: list[str] = ["【辅助质量诊断参考】"]
    lines.append("以下 deterministic 诊断结果供审核参考，不替代五层审校评分。")

    if feedback.editor_notes:
        lines.append("\n结构层注意：")
        for note in feedback.editor_notes:
            lines.append(f"  - {note}")

    if feedback.priority_findings:
        lines.append("\n高优先级问题（已纳入 issues）：")
        for f in feedback.priority_findings:
            ev = f" 证据: {f['evidence']}" if f.get("evidence") else ""
            lines.append(f"  - [{f['code']}] {f['message']}{ev}")

    if feedback.advisory_findings:
        lines.append("\n中低优先级建议（advisory only，不单独推翻 85+ 分）：")
        for f in feedback.advisory_findings[:3]:
            lines.append(f"  - [{f['code']}] {f['message']}")

    return "\n".join(lines)


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    text = str(text).replace("\n", " ")
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _compact_evidence(evidence: Any) -> str | None:
    """Keep evidence compact: counts, ratios, or very short snippets."""
    if evidence is None:
        return None
    if isinstance(evidence, (int, float)):
        return str(evidence)
    text = str(evidence).replace("\n", " ")
    if len(text) <= 40:
        return text
    # For longer text, keep first 30 chars + count info
    return f"len={len(text)}"


def _deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for f in findings:
        key = f"{f.get('code')}:{f.get('message', '')[:40]}"
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def _deduplicate_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item[:60]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
