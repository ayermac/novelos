"""Deterministic numeric state extraction and inheritance checks.

Numeric state is any story value that should carry across chapters, such as
countdowns, balances, levels, points, remaining counts, percentages, HP/energy,
or progress. The extractor is intentionally conservative: it only records
numbers that appear near state-like keywords, so generic chapter numbers or
ordinary descriptions are not promoted to hard constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


_CLOCK_PATTERN = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?!\d)")
_NUMBER_BASE = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_NUMBER_UNIT = r"(?:万|亿|%|％|点|级|阶|层|星|次|回|小时|分钟|秒|天|元|块|枚|条|格|滴|年|号|倍)?"
_NUMBER_VALUE = rf"{_NUMBER_BASE}(?:\s*/\s*{_NUMBER_BASE})?\s*{_NUMBER_UNIT}"
_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    + _NUMBER_VALUE +
    r"(?![A-Za-z0-9])"
)

_COUNTDOWN_CONTEXT_PATTERN = re.compile(
    r"(?:倒计时|计时器?|剩余时间|左眼|数字|猩红|暴跌|猛跌|预支|利息|锁链|崩断|搏动|心脏|归零)"
)

_STATE_KEYWORDS = (
    "账户余额",
    "银行卡余额",
    "余额",
    "资产",
    "现金",
    "资金",
    "存款",
    "负债",
    "债务",
    "利息",
    "额度",
    "授信",
    "金币",
    "金钱",
    "灵石",
    "筹码",
    "积分",
    "点数",
    "贡献点",
    "声望",
    "经验值",
    "经验",
    "等级",
    "级别",
    "权限等级",
    "权限",
    "Lv",
    "LV",
    "lv",
    "血量",
    "生命值",
    "体力",
    "法力",
    "灵力",
    "能量",
    "耐久",
    "修为",
    "战力",
    "好感度",
    "忠诚度",
    "同步率",
    "污染度",
    "完成度",
    "进度",
    "冷却",
    "库存",
    "名额",
    "次数",
    "剩余次数",
    "温度",
)

_KEYWORD_CANONICAL = {
    "银行卡余额": "余额",
    "账户余额": "余额",
    "存款": "余额",
    "金钱": "余额",
    "等级": "等级",
    "级别": "等级",
    "权限等级": "权限等级",
    "Lv": "等级",
    "LV": "等级",
    "lv": "等级",
    "经验值": "经验",
    "点数": "积分",
    "剩余次数": "次数",
}

_CHANGE_MARKERS = (
    "从",
    "变成",
    "变为",
    "升至",
    "降至",
    "涨到",
    "跌至",
    "增加",
    "减少",
    "扣除",
    "消耗",
    "获得",
    "奖励",
    "到账",
    "结算",
    "刷新",
    "更新",
    "归零",
    "清零",
)
_REPLAY_MARKERS = ("回忆", "闪回", "倒叙", "回放", "复盘", "画面回到")
_GENERIC_STATE_CONTEXT_MARKERS = (
    "系统",
    "面板",
    "状态栏",
    "属性",
    "参数",
    "数值",
    "指标",
    "读数",
    "计量",
    "监测",
    "仪表",
    "刻度",
    "显示",
    "刷新",
    "更新",
    "当前",
    "剩余",
    "累计",
    "总计",
    "上限",
    "下限",
    "阈值",
    "倍率",
    "序列",
    "密钥",
    "授权",
    "残页",
    "碎片",
    "稳定",
    "污染",
    "同步",
    "浓度",
    "风险",
    "警戒",
)
_GENERIC_STATE_LABEL_HINTS = (
    "率",
    "值",
    "度",
    "量",
    "数",
    "分",
    "级",
    "档",
    "阶",
    "指数",
    "阈值",
    "上限",
    "下限",
    "倍率",
    "序列",
    "编号",
    "密钥",
    "授权",
    "残页",
    "碎片",
    "令牌",
    "额度",
    "进度",
    "冷却",
    "温度",
    "压力",
    "浓度",
    "纯度",
    "稳定",
    "污染",
    "同步",
    "完整",
    "风险",
    "警戒",
)
_GENERIC_LABEL_IGNORED = {
    "第",
    "章",
    "段",
    "页",
    "行",
    "字",
    "他",
    "她",
    "它",
    "他们",
    "她们",
    "这里",
    "那里",
    "今天",
    "明天",
    "昨天",
    "系统",
    "面板",
    "状态栏",
    "屏幕",
    "数字",
    "数据",
}
_GENERIC_LABEL_PREFIXES = (
    "当前",
    "最新",
    "剩余",
    "累计",
    "总计",
    "系统",
    "面板",
    "屏幕",
    "状态栏",
    "数据显示",
    "显示",
    "读数",
    "指标",
    "参数",
)


@dataclass(frozen=True)
class NumericState:
    """A traceable numeric state mention from chapter text."""

    key: str
    label: str
    value: str
    normalized_value: float | None
    kind: str
    evidence: str
    position: int
    unit: str = ""


def extract_numeric_states(text: str, *, max_items: int = 12) -> list[NumericState]:
    """Extract latest numeric states from text.

    For each canonical key, the last occurrence wins because the chapter tail
    represents the latest state that must be inherited by the next chapter.
    """
    source = str(text or "")
    if not source.strip():
        return []

    candidates: list[NumericState] = []
    candidates.extend(_extract_clock_states(source))
    candidates.extend(_extract_explicit_state_syntax(source))
    candidates.extend(_extract_labeled_number_states(source))

    latest_by_key: dict[str, NumericState] = {}
    for state in candidates:
        current = latest_by_key.get(state.key)
        if current is None or state.position >= current.position:
            latest_by_key[state.key] = state

    return sorted(latest_by_key.values(), key=lambda item: item.position)[-max_items:]


def build_numeric_state_fact_patches(
    text: str,
    *,
    chapter_number: int,
    confidence: float = 0.92,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """Build MemoryCurator story_facts patches for extracted numeric states."""
    patches: list[dict[str, Any]] = []
    for state in extract_numeric_states(text, max_items=max_items):
        digest_source = f"{chapter_number}:{state.key}:{state.value}:{state.evidence}"
        digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:10]
        fact_key = f"chapter_{chapter_number}.numeric_state.{_safe_key(state.key)}.{digest}"
        patches.append(
            {
                "target_table": "story_facts",
                "operation": "create",
                "target_name": fact_key,
                "data": {
                    "fact_key": fact_key,
                    "fact_type": "numeric_state",
                    "subject": state.label,
                    "attribute": "最新数值",
                    "value": {
                        "key": state.key,
                        "label": state.label,
                        "value": state.value,
                        "normalized_value": state.normalized_value,
                        "kind": state.kind,
                        "evidence": state.evidence,
                    },
                    "unit": state.unit,
                    "source_chapter": chapter_number,
                    "source_agent": "memory_curator",
                },
                "confidence": confidence,
                "evidence_text": state.evidence[:240],
                "rationale": "确定性数值状态提取：用于下一章继承，防止余额、等级、倒计时等关键数值漂移。",
            }
        )
    return patches


def numeric_state_constraint_from_text(text: str, *, prefix: str = "上一章结尾") -> str:
    """Format extracted numeric states as a prompt hard constraint block."""
    states = extract_numeric_states(text, max_items=8)
    if not states:
        return ""
    lines = [
        f"- {state.label} = {state.value}（证据：{state.evidence[:80]}）"
        for state in states
    ]
    return (
        f"{prefix}数值状态:\n"
        + "\n".join(lines)
        + "\n本章必须继承这些最新数值；如果数值变化，必须写出明确原因和变化过程，禁止无解释回退或重置。"
    )


def numeric_state_constraints_from_facts(facts: list[dict[str, Any]]) -> list[str]:
    """Format active numeric_state story facts for prompt injection."""
    latest: dict[str, tuple[int, str]] = {}
    for fact in facts:
        fact_type = str(fact.get("fact_type") or "").lower()
        if fact_type != "numeric_state" and not _fact_looks_numeric(fact):
            continue
        label = str(fact.get("subject") or fact.get("attribute") or "数值状态").strip()
        raw_value = fact.get("value_json")
        value = _parse_fact_value(raw_value)
        display = (
            value.get("value")
            or value.get("text")
            or value.get("state")
            or raw_value
            or ""
        )
        evidence = value.get("evidence") or fact.get("attribute") or ""
        source = fact.get("source_chapter") or fact.get("last_changed_chapter") or "?"
        if str(display).strip():
            key = str(value.get("key") or label).strip() or label
            try:
                source_num = int(source)
            except (TypeError, ValueError):
                source_num = 0
            line = f"{label} = {display}（第{source}章确认；{str(evidence)[:60]}）"
            if key not in latest or source_num > latest[key][0]:
                latest[key] = (source_num, line)
    return [line for _source_num, line in sorted(latest.values(), key=lambda item: item[0], reverse=True)]


def detect_numeric_state_regressions(prev_tail: str, opening: str) -> list[dict[str, str]]:
    """Detect same-key numeric states that restart without explanation."""
    previous_states = {state.key: state for state in extract_numeric_states(prev_tail, max_items=10)}
    current_states = {state.key: state for state in extract_numeric_states(opening, max_items=10)}
    if not previous_states or not current_states:
        return []
    if any(marker in str(opening or "") for marker in _REPLAY_MARKERS):
        return []

    regressions: list[dict[str, str]] = []
    opening_text = str(opening or "")
    for key, previous in previous_states.items():
        current = current_states.get(key)
        if not current or _same_numeric_value(previous, current):
            continue
        if previous.value and previous.value in opening_text:
            continue
        current_window = current.evidence
        if any(marker in current_window for marker in _CHANGE_MARKERS):
            continue
        regressions.append(
            {
                "issue": (
                    f"章间数值继承断裂：上一章结尾“{previous.label}”为“{previous.value}”，"
                    f"本章开头变成“{current.value}”，但未交代变化原因。"
                ),
                "suggestion": (
                    f"本章开头应先承接“{previous.label}={previous.value}”；"
                    "如需变化，必须写明触发事件、扣除/奖励/结算过程。"
                ),
            }
        )
    return regressions


def _extract_clock_states(source: str) -> list[NumericState]:
    clocks = list(_CLOCK_PATTERN.finditer(source))
    if len(clocks) < 2 or not _COUNTDOWN_CONTEXT_PATTERN.search(source):
        return []
    latest = clocks[-1]
    value = latest.group(0)
    return [
        NumericState(
            key="倒计时",
            label="倒计时",
            value=value,
            normalized_value=_clock_to_seconds(value),
            kind="countdown",
            evidence=_sentence_around(source, latest.start(), latest.end()),
            position=latest.start(),
        )
    ]


def _extract_explicit_state_syntax(source: str) -> list[NumericState]:
    """Extract dashboard/stat-card style values such as ``【魂源：4.5 → 49.5】``."""
    states: list[NumericState] = []
    label_pattern = r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff·/_-]{1,24})"
    boundary = r"(?:^|[【\[\(（\n。！？；;])\s*"
    transition_pattern = re.compile(
        boundary
        + label_pattern
        + rf"\s*[：:=＝]\s*({_NUMBER_VALUE})\s*(?:→|->|—>|=>)\s*({_NUMBER_VALUE})"
    )
    direct_pattern = re.compile(
        boundary
        + label_pattern
        + rf"\s*[：:=＝]\s*({_NUMBER_VALUE})(?!\s*(?:→|->|—>|=>))"
    )

    for match in transition_pattern.finditer(source):
        label = _clean_generic_label(match.group(1))
        if not _explicit_label_allowed(label):
            continue
        value = re.sub(r"\s+", "", match.group(3))
        states.append(_numeric_state_from_explicit_match(source, match, label, value, match.start(3)))

    for match in direct_pattern.finditer(source):
        label = _clean_generic_label(match.group(1))
        if not _explicit_direct_label_allowed(source, match, label):
            continue
        value = re.sub(r"\s+", "", match.group(2))
        states.append(_numeric_state_from_explicit_match(source, match, label, value, match.start(2)))

    return states


def _numeric_state_from_explicit_match(
    source: str,
    match: re.Match,
    label: str,
    value: str,
    position: int,
) -> NumericState:
    return NumericState(
        key=_canonical_key(label),
        label=_canonical_label(label),
        value=value,
        normalized_value=_normalize_numeric_value(value),
        kind="explicit_numeric_state",
        evidence=_sentence_around(source, match.start(), match.end()),
        position=position,
        unit=_extract_unit(value),
    )


def _explicit_label_allowed(label: str) -> bool:
    if not label or len(label) < 2:
        return False
    return label not in _GENERIC_LABEL_IGNORED and not label.startswith(("第", "这", "那"))


def _explicit_direct_label_allowed(source: str, match: re.Match, label: str) -> bool:
    if not _explicit_label_allowed(label):
        return False
    raw = match.group(0).lstrip()
    if raw.startswith(("【", "[", "(", "（")):
        return True
    sentence = _sentence_around(source, match.start(), match.end())
    return bool(
        label in _STATE_KEYWORDS
        or label in _KEYWORD_CANONICAL
        or _generic_label_is_stateful(label, sentence)
    )


def _extract_labeled_number_states(source: str) -> list[NumericState]:
    states: list[NumericState] = []
    for match in _NUMBER_PATTERN.finditer(source):
        if _is_chapter_heading_number(source, match.start(), match.end()):
            continue
        before, after = _local_number_context(source, match.start(), match.end())
        label = _pick_label(before, after)
        kind = "numeric"
        if not label:
            label = _pick_generic_state_label(source, match.start(), match.end(), before, after)
            kind = "generic_numeric"
        if not label:
            continue
        value = re.sub(r"\s+", "", match.group(0))
        states.append(
            NumericState(
                key=_canonical_key(label),
                label=_canonical_label(label),
                value=value,
                normalized_value=_normalize_numeric_value(value),
                kind=kind,
                evidence=_sentence_around(source, match.start(), match.end()),
                position=match.start(),
                unit=_extract_unit(value),
            )
        )
    return states


def _local_number_context(source: str, start: int, end: int) -> tuple[str, str]:
    left = max(source.rfind(mark, 0, start) for mark in ("。", "！", "？", "\n", "；", ";"))
    right_candidates = [
        index for index in (
            source.find(mark, end) for mark in ("。", "！", "？", "\n", "；", ";")
        )
        if index >= 0
    ]
    right = min(right_candidates) if right_candidates else min(len(source), end + 24)
    return source[max(left + 1, start - 24):start], source[end:min(right, end + 24)]


def _pick_label(before: str, after: str) -> str:
    candidates: list[tuple[int, int, str]] = []
    for keyword in _STATE_KEYWORDS:
        before_index = before.rfind(keyword)
        if before_index >= 0:
            candidates.append((len(before) - before_index, -len(keyword), keyword))
        after_index = after.find(keyword)
        if after_index >= 0:
            candidates.append((after_index + len(keyword), -len(keyword), keyword))
    if not candidates:
        return ""
    return min(candidates)[2]


def _pick_generic_state_label(source: str, start: int, end: int, before: str, after: str) -> str:
    """Infer an open-ended numeric-state label from explicit state syntax.

    This intentionally requires either state-like context or a state-like label
    hint so ordinary prose numbers such as ages, room numbers, and chapter
    headings are not promoted to hard constraints.
    """
    sentence = _sentence_around(source, start, end)
    label = _generic_label_before_number(before)
    if not label:
        label = _generic_label_after_number(after)
    if not label:
        return ""
    label = _clean_generic_label(label)
    if not _generic_label_is_stateful(label, sentence):
        return ""
    return label


def _generic_label_before_number(before: str) -> str:
    patterns = (
        r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff·/_-]{1,24})\s*(?:[:：=＝])\s*$",
        r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff·/_-]{1,24})\s*(?:为|是|剩余|只剩|还剩|余下|达到|突破|升至|升到|降至|降到|跌至|涨到|变为|变成|刷新为|更新为|显示为|稳定在|锁定在)\s*$",
        r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff·/_-]{1,24})\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, before)
        if match:
            return match.group(1)
    return ""


def _generic_label_after_number(after: str) -> str:
    match = re.search(
        r"^\s*(?:枚|条|格|层|级|阶|点|次|回|号|倍)?\s*"
        r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff·/_-]{1,24})",
        after,
    )
    return match.group(1) if match else ""


def _clean_generic_label(label: str) -> str:
    cleaned = str(label or "").strip(" \t\r\n，。！？；;：:、,.「」“”《》()（）[]【】")
    for sep in ("，", "。", "；", ";", "、", "\n", " "):
        if sep in cleaned:
            cleaned = cleaned.rsplit(sep, 1)[-1]
    for prefix in _GENERIC_LABEL_PREFIXES:
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix) + 1:
            cleaned = cleaned[len(prefix):]
    return cleaned.strip(" \t\r\n，。！？；;：:、,.「」“”《》()（）[]【】")


def _generic_label_is_stateful(label: str, sentence: str) -> bool:
    if not label or len(label) < 2:
        return False
    if label in _GENERIC_LABEL_IGNORED:
        return False
    if label.startswith(("第", "这", "那")) and not any(hint in label for hint in _GENERIC_STATE_LABEL_HINTS):
        return False
    if any(marker in sentence for marker in _GENERIC_STATE_CONTEXT_MARKERS):
        return True
    return any(hint in label for hint in _GENERIC_STATE_LABEL_HINTS)


def _canonical_label(label: str) -> str:
    return _KEYWORD_CANONICAL.get(label, label)


def _canonical_key(label: str) -> str:
    return _canonical_label(label).lower()


def _safe_key(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value).strip("_")
    return text[:24] or "value"


def _extract_unit(value: str) -> str:
    match = re.search(r"(万|亿|%|％|点|级|阶|层|星|次|回|小时|分钟|秒|天|元|块|枚|条|格|滴|年)$", value)
    return match.group(1) if match else ""


def _normalize_numeric_value(value: str) -> float | None:
    text = str(value or "").replace(",", "").replace(" ", "")
    unit_multiplier = 1.0
    if text.endswith("亿"):
        unit_multiplier = 100000000.0
        text = text[:-1]
    elif text.endswith("万"):
        unit_multiplier = 10000.0
        text = text[:-1]
    elif text.endswith(("％", "%")):
        text = text[:-1]
    else:
        text = re.sub(r"(点|级|阶|层|星|次|回|小时|分钟|秒|天|元|块|枚|条|格|滴|年)$", "", text)
    try:
        return float(text) * unit_multiplier
    except ValueError:
        return None


def _clock_to_seconds(value: str) -> float | None:
    parts = str(value or "").split(":")
    if len(parts) == 2:
        parts.append("0")
    if len(parts) != 3:
        return None
    try:
        hour, minute, second = (int(part) for part in parts)
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return float(hour * 3600 + minute * 60 + second)


def _same_numeric_value(left: NumericState, right: NumericState) -> bool:
    if left.value == right.value:
        return True
    if left.normalized_value is None or right.normalized_value is None:
        return False
    return abs(left.normalized_value - right.normalized_value) < 1e-6


def _sentence_around(source: str, start: int, end: int) -> str:
    left = max(source.rfind(mark, 0, start) for mark in ("。", "！", "？", "\n", "；", ";"))
    right_candidates = [
        index for index in (
            source.find(mark, end) for mark in ("。", "！", "？", "\n", "；", ";")
        )
        if index >= 0
    ]
    right = min(right_candidates) if right_candidates else min(len(source), end + 80)
    snippet = source[left + 1:right + 1].strip()
    return re.sub(r"\s+", "", snippet)[:160]


def _is_chapter_heading_number(source: str, start: int, end: int) -> bool:
    window = source[max(0, start - 3): min(len(source), end + 3)]
    return bool(re.search(r"第\s*" + re.escape(source[start:end].strip()) + r"\s*章", window))


def _fact_looks_numeric(fact: dict[str, Any]) -> bool:
    text = " ".join(
        str(fact.get(key) or "")
        for key in ("fact_key", "fact_type", "subject", "attribute", "value_json", "unit")
    )
    return bool(_NUMBER_PATTERN.search(text) and any(keyword in text for keyword in _STATE_KEYWORDS))


def _parse_fact_value(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except Exception:
            return {"value": raw_value}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {"value": raw_value}
