"""v6.10.5: Core Loop Checker — project contract compliance checker.

Checks whether a chapter fulfills the project's Story Contract:
- Core payoff present in chapter
- Core loop steps completed
- Supporting mechanism dominance detection
- New mechanism budget
- Protagonist agency
- Drift rule violations

This is NOT a general literary quality scorer. It checks contract compliance
specific to each project's StoryContract.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from ..models.creative_contracts import StoryContract, CoreLoopStep, SupportingMechanism, DriftRule
from ..models.chapter_contracts import ChapterBrief
from ..models.creative_ledgers import ChapterContractMetrics

logger = logging.getLogger(__name__)


# ── Drift types ──────────────────────────────────────────────────

DriftType = Literal[
    "pressure_mechanism_dominance",
    "core_payoff_missing",
    "new_mechanism_overload",
    "payoff_gap",
    "protagonist_agency_gap",
    "promise_drift",
]


@dataclass
class DriftSignal:
    """A single drift signal detected by the checker."""

    drift_type: DriftType
    severity: Literal["warning", "blocking"]
    description: str
    evidence: str = ""
    chapter_number: int = 0


@dataclass
class CoreLoopCheckResult:
    """Result of checking a chapter against its Story Contract."""

    passed: bool = True
    score: float = 100.0
    core_payoff_present: bool = False
    core_loop_steps_completed: list[str] = field(default_factory=list)
    supporting_mechanism_dominance: bool = False
    new_mechanism_count: int = 0
    protagonist_agency_present: bool = True
    warnings: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    drift_signals: list[DriftSignal] = field(default_factory=list)
    contract_metrics: ChapterContractMetrics | None = None
    reward_acquired: bool = False
    reward_used: bool = False
    enemy_consequence: bool = False
    required_payoff_present: bool = True
    missing_evidence: list[str] = field(default_factory=list)
    evidence_spans: dict[str, list[str]] = field(default_factory=dict)
    tracked_states: dict[str, str] = field(default_factory=dict)
    state_deltas: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API / artifact storage."""
        return {
            "passed": self.passed,
            "score": self.score,
            "core_payoff_present": self.core_payoff_present,
            "core_loop_steps_completed": self.core_loop_steps_completed,
            "supporting_mechanism_dominance": self.supporting_mechanism_dominance,
            "new_mechanism_count": self.new_mechanism_count,
            "protagonist_agency_present": self.protagonist_agency_present,
            "warnings": self.warnings,
            "blocking_issues": self.blocking_issues,
            "reward_acquired": self.reward_acquired,
            "reward_used": self.reward_used,
            "enemy_consequence": self.enemy_consequence,
            "required_payoff_present": self.required_payoff_present,
            "missing_evidence": self.missing_evidence,
            "evidence_spans": self.evidence_spans,
            "tracked_states": self.tracked_states,
            "state_deltas": self.state_deltas,
            "drift_signals": [
                {
                    "drift_type": s.drift_type,
                    "severity": s.severity,
                    "description": s.description,
                    "evidence": s.evidence,
                }
                for s in self.drift_signals
            ],
        }


# ── Keyword banks for deterministic detection ────────────────────

_PAYOFF_KEYWORDS = [
    "获得", "得到", "收获", "奖励", "提升", "突破", "升级", "兑现",
    "反杀", "碾压", "打脸", "逆转", "胜利", "成功", "掌控", "拿捏",
    "击败", "解决", "达成", "实现", "完成", "觉醒", "激活",
]

_PRESSURE_KEYWORDS = [
    "危机", "威胁", "追杀", "倒计时", "压迫", "困境", "危险",
    "被迫", "陷入", "绝境", "崩溃", "失败", "挫折", "压制",
    "债务", "命债", "诅咒", "束缚", "枷锁", "代价",
]

_PASSIVE_KEYWORDS = [
    "被动", "被迫", "无奈", "无力", "无助", "只能", "不得不",
    "任由", "听凭", "被控制", "被支配", "被安排", "被摆布",
]

_ACTIVE_KEYWORDS = [
    "主动", "决定", "选择", "出手", "反击", "行动", "计划",
    "布局", "设局", "主导", "掌控", "操控", "推动", "引导",
]

_NEW_MECHANISM_KEYWORDS = [
    "新规则", "新设定", "新机制", "新能力", "新系统", "新势力",
    "新限制", "新约束", "新条件", "新代价", "新境界", "新领域",
]

_STATE_KEYS = [
    "魂源", "统帅值", "积分", "余额", "等级", "权限", "倒计时",
    "次数", "进度", "生命", "能量", "经验", "战力", "境界",
]

_RESOURCE_CHANGE_ACTIONS = [
    "获得", "得到", "收获", "奖励", "吞噬", "抽干", "消耗",
    "兑换", "扣除", "提升", "补充", "吸收", "转化",
]


@dataclass
class CoreLoopEvidence:
    """Concrete textual evidence for core-loop delivery."""

    reward_acquired: bool = False
    reward_used: bool = False
    enemy_consequence: bool = False
    army_payoff: bool = False
    required_payoff_present: bool = True
    missing_evidence: list[str] = field(default_factory=list)
    evidence_spans: dict[str, list[str]] = field(default_factory=dict)
    tracked_states: dict[str, str] = field(default_factory=dict)
    state_deltas: list[dict] = field(default_factory=list)


def _contract_text(contract: StoryContract, brief: ChapterBrief | None) -> str:
    parts: list[str] = [contract.core_promise or ""]
    parts.extend(contract.payoff_types or [])
    parts.extend(step.id for step in contract.core_loop)
    parts.extend(step.label for step in contract.core_loop)
    parts.extend(step.description for step in contract.core_loop)
    if brief:
        parts.extend([
            brief.tier1.reader_payoff,
            brief.tier1.core_loop_target,
            brief.tier1.primary_payoff,
            brief.tier1.payoff_evidence_plan,
            brief.tier2.upgrade_or_skill_use,
        ])
    return "\n".join(str(p) for p in parts if p)


def _requires_summon_or_army_payoff(contract: StoryContract, brief: ChapterBrief | None) -> bool:
    text = _contract_text(contract, brief)
    return any(token in text for token in ("召唤", "兵俑", "军团", "战灵", "神军", "傀儡", "统帅"))


def _segments(content: str) -> list[str]:
    compact = content.replace("\r\n", "\n")
    raw = re.split(r"(?<=[。！？!?；;])|\n+", compact)
    return [s.strip() for s in raw if s and s.strip()]


def _find_segments(content: str, patterns: list[str], limit: int = 5) -> list[str]:
    hits: list[str] = []
    for segment in _segments(content):
        for pattern in patterns:
            if re.search(pattern, segment):
                hits.append(segment[:160])
                break
        if len(hits) >= limit:
            break
    return hits


def _drop_hypothetical_spans(spans: list[str]) -> list[str]:
    """Remove plan/preview text that is not actual chapter payoff evidence."""
    filtered: list[str] = []
    for span in spans:
        if any(token in span for token in ("预期", "获取后", "可解锁", "可直接", "若拿到", "足以")):
            if not any(token in span for token in ("已解锁", "已获得", "已到账", "已完成")):
                continue
        filtered.append(span)
    return filtered


def _extract_tracked_states(content: str) -> dict[str, str]:
    states: dict[str, str] = {}
    number = r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?"
    for key in _STATE_KEYS:
        delta = re.findall(
            rf"{re.escape(key)}[^。\n，,；;]{{0,30}}从\s*({number})\s*(?:变为|变成|提升到|降至|增加到)\s*({number})",
            content,
        )
        if delta:
            states[key] = delta[-1][1].replace(" ", "")
            continue
        arrow_delta = re.findall(
            rf"{re.escape(key)}\s*[：:]?\s*({number})\s*(?:→|->|—>|=>)\s*({number})",
            content,
        )
        if arrow_delta:
            states[key] = arrow_delta[-1][1].replace(" ", "")
            continue
        direct = re.findall(rf"{re.escape(key)}\s*[：:]\s*({number})", content)
        if direct:
            states[key] = direct[-1].replace(" ", "")
    return states


def _extract_state_deltas(content: str, previous_states: dict[str, str], current_states: dict[str, str]) -> list[dict]:
    deltas: list[dict] = []
    number = r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?"
    seen: set[tuple[str, str, str]] = set()
    for key in _STATE_KEYS:
        for old, new in re.findall(
            rf"{re.escape(key)}[^。\n，,；;]{{0,30}}从\s*({number})\s*(?:变为|变成|提升到|降至|增加到)\s*({number})",
            content,
        ):
            item = (key, old.replace(" ", ""), new.replace(" ", ""))
            if item not in seen:
                deltas.append({"state": item[0], "from": item[1], "to": item[2], "source": "text_delta"})
                seen.add(item)
        for old, new in re.findall(
            rf"{re.escape(key)}\s*[：:]?\s*({number})\s*(?:→|->|—>|=>)\s*({number})",
            content,
        ):
            item = (key, old.replace(" ", ""), new.replace(" ", ""))
            if item not in seen:
                deltas.append({"state": item[0], "from": item[1], "to": item[2], "source": "text_delta"})
                seen.add(item)
    for key, current in current_states.items():
        previous = previous_states.get(key)
        if previous and previous != current:
            item = (key, previous, current)
            if item not in seen:
                deltas.append({"state": key, "from": previous, "to": current, "source": "state_snapshot"})
                seen.add(item)
    return deltas


def _latest_tracked_states(recent_metrics: list[ChapterContractMetrics]) -> dict[str, str]:
    states: dict[str, str] = {}
    for metric in sorted(recent_metrics, key=lambda m: m.chapter_number):
        metric_states = getattr(metric, "tracked_states", {}) or {}
        for key, value in metric_states.items():
            if value not in (None, ""):
                states[key] = str(value)
    return states


def _changed_tracked_resources(content: str, previous_states: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for key in previous_states:
        if key not in content:
            continue
        window_hit = False
        for match in re.finditer(re.escape(key), content):
            start = max(0, match.start() - 24)
            end = min(len(content), match.end() + 36)
            window = content[start:end]
            if any(action in window for action in _RESOURCE_CHANGE_ACTIONS):
                window_hit = True
                break
        if window_hit:
            changed.append(key)
    return changed


def _build_contract_patterns(contract: StoryContract, brief: ChapterBrief | None) -> tuple[list[str], list[str], list[str]]:
    """Build dynamic regex patterns from contract payoff_types, core_loop steps, and brief.

    Returns (reward_acquired_extra, reward_used_extra, enemy_extra) pattern lists.
    """
    reward_extra: list[str] = []
    used_extra: list[str] = []
    enemy_extra: list[str] = []

    # Extract meaningful keywords from contract (skip very short or generic ones)
    payoff_keywords: list[str] = []
    for pt in (contract.payoff_types or []):
        if pt and len(pt) >= 2:
            payoff_keywords.append(re.escape(pt))

    for step in (contract.core_loop or []):
        for text in (step.label, step.description):
            if text and len(text) >= 2:
                payoff_keywords.append(re.escape(text))

    if brief:
        for text in [
            brief.tier1.reader_payoff,
            brief.tier1.core_loop_target,
            brief.tier1.primary_payoff,
            brief.tier1.payoff_evidence_plan,
        ]:
            if text and len(text) >= 2:
                payoff_keywords.append(re.escape(text))

    if payoff_keywords:
        # Group keywords into OR pattern
        kw_group = "|".join(payoff_keywords[:20])  # cap to avoid regex explosion
        reward_extra.append(rf"(获得|得到|收获|兑现|实现|达成|完成|触发|激活).{{0,24}}({kw_group})")
        reward_extra.append(rf"({kw_group}).{{0,24}}(生效|爆发|释放|显现|兑现|成功|完成)")
        used_extra.append(rf"(使用|动用|催动|发动|施展|兑现|消耗|牺牲|撕裂).{{0,24}}({kw_group})")
        used_extra.append(rf"({kw_group}).{{0,24}}(出手|生效|爆发|释放|冲击|对抗|反击)")

    return reward_extra, used_extra, enemy_extra


def _analyze_core_loop_evidence(
    content: str,
    brief: ChapterBrief | None,
    contract: StoryContract,
    recent_metrics: list[ChapterContractMetrics],
) -> CoreLoopEvidence:
    """Build evidence diagnostics from actual chapter text.

    This intentionally does not treat ChapterBrief declarations as proof. Briefs
    are plans; the checker must find matching evidence in the final prose.

    v6.10.9: Augments hardcoded patterns with contract-derived dynamic patterns
    so project-specific vocabulary (e.g. 浊嗅, 血裔印, 压制波) is detected.
    """
    evidence = CoreLoopEvidence()

    # Build contract-derived dynamic patterns
    contract_reward_extra, contract_used_extra, contract_enemy_extra = _build_contract_patterns(contract, brief)

    reward_acquired_spans = _find_segments(content, [
        r"(获得|得到|收获|奖励|到账|入账|夺得|拿到).{0,18}(奖励|魂源|积分|能力|权限|装备|资源|魔晶|晶核)",
        r"(解锁|激活|觉醒).{0,18}(能力|指令|序列|技能|权限|天赋|形态)",
        r"【[^】]*(获得|解锁|激活|奖励|指令|初始魂源)[^】]*】",
        r"(吞噬|吸收|抽干|转化).{0,18}(魂源|能量|晶核|魂源石|积分)",
        # v6.10.9: broader outcome patterns
        r"(撕裂|牺牲|消耗|献祭|燃烧).{0,24}(记忆|感官|生命力|血|魂|代价).{0,24}(激活|触发|释放|打开|启动|兑现)",
        r"(代价|牺牲|消耗).{0,18}(换来|换来|得到|获得|开启|激活)",
        *contract_reward_extra,
    ])
    reward_used_spans = _find_segments(content, [
        r"(使用|动用|催动|发动|施展|兑现).{0,24}(奖励|能力|指令|魂源|积分|权限|技能|力量)",
        r"(召唤|具现|指挥|命令|调动).{0,24}(兵俑|军团|战灵|召唤物|神军|傀儡)",
        r"(兵俑|军团|战灵|神军|召唤物).{0,24}(出手|斩|杀|挡|冲|列阵|围|压|碾)",
        r"(噬源|指令).{0,24}(发动|生效|抽干|吞噬|吸收)",
        r"(抽干|吞噬|吸收).{0,18}(魂源石|魂源|能量|晶核)",
        r"(魂源石|魂源|能量|晶核).{0,18}(抽干|吞噬|吸收|转化)",
        r"实力.{0,12}(提升|突破|大幅提升|暴涨)",
        # v6.10.9: broader use/action patterns
        r"(撕裂|消耗|牺牲|献祭).{0,24}(记忆|感官|生命力|血|魂).{0,24}(引信|钥匙|代价|催化)",
        r"(感知|感应|触碰|连接|同步).{0,24}(裂纹|断裂|变化|波动|反馈|回应)",
        *contract_used_extra,
    ])
    enemy_consequence_spans = _find_segments(content, [
        r"(敌人|对手|顾家|顾长歌|反派|暗卫|追踪|罗盘|鱼钩|锯齿鼠|老蝎|马三).{0,32}(失败|崩断|炸开|受创|震惊|僵住|反噬|退|损失|倒飞|死)",
        r"(打脸|反杀|碾压|击败|杀死).{0,24}(敌人|对手|顾家|反派|暗卫|锯齿鼠)",
        # v6.10.9: broader antagonist consequence patterns
        r"(封锁|压制|控制|束缚).{0,24}(破裂|崩断|撕裂|失效|瓦解|动摇)",
        r"(回收者|压制波|封锁线|屏障).{0,24}(阻滞|破裂|撕裂|失效|崩断|动摇)",
        *contract_enemy_extra,
    ])
    army_payoff_spans = _find_segments(content, [
        r"(兵俑|军团|战灵|神军|召唤物).{0,32}(出手|斩|杀|挡|冲|列阵|围|压|碾|救|破)",
        r"(召唤|具现|指挥|命令|统帅).{0,32}(兵俑|军团|战灵|神军|召唤物)",
    ])

    reward_acquired_spans = _drop_hypothetical_spans(reward_acquired_spans)
    reward_used_spans = _drop_hypothetical_spans(reward_used_spans)

    evidence.reward_acquired = bool(reward_acquired_spans)
    evidence.reward_used = bool(reward_used_spans)
    evidence.enemy_consequence = bool(enemy_consequence_spans)
    evidence.army_payoff = bool(army_payoff_spans)
    evidence.evidence_spans = {
        "reward_acquired": reward_acquired_spans,
        "reward_used": reward_used_spans,
        "enemy_consequence": enemy_consequence_spans,
        "army_payoff": army_payoff_spans,
    }

    previous_states = _latest_tracked_states(recent_metrics)
    current_states = _extract_tracked_states(content)
    changed_resources = _changed_tracked_resources(content, previous_states)
    evidence.tracked_states = {**previous_states, **current_states}
    evidence.state_deltas = _extract_state_deltas(content, previous_states, current_states)
    for delta in evidence.state_deltas:
        state_name = str(delta.get("state") or "")
        new_value = str(delta.get("to") or "")
        if state_name and new_value:
            evidence.tracked_states[state_name] = new_value

    if evidence.reward_acquired and not evidence.reward_used:
        evidence.missing_evidence.append("reward_used")
    if _requires_summon_or_army_payoff(contract, brief) and (evidence.reward_acquired or evidence.reward_used) and not evidence.army_payoff:
        evidence.missing_evidence.append("contract_required_payoff")
    for key in changed_resources:
        if key not in current_states and not any(delta.get("state") == key for delta in evidence.state_deltas):
            evidence.missing_evidence.append(f"state_delta:{key}")

    evidence.required_payoff_present = not evidence.missing_evidence
    return evidence


# ── Deterministic checks ─────────────────────────────────────────

def _check_core_payoff_present(
    content: str,
    brief: ChapterBrief | None,
    contract: StoryContract,
) -> tuple[bool, str]:
    """Check if the chapter contains evidence of core payoff delivery.

    Returns (present, evidence).

    v6.10.9: Also checks contract core_loop step labels/descriptions as keywords,
    and uses broader outcome patterns for project-specific vocabulary.
    """
    content_lower = content.lower()

    # Check brief first — most reliable signal
    if brief:
        tier1 = brief.tier1
        if tier1.reader_payoff and len(tier1.reader_payoff.strip()) > 5:
            return True, f"brief.reader_payoff: {tier1.reader_payoff[:80]}"
        if tier1.primary_payoff and len(tier1.primary_payoff.strip()) > 5:
            return True, f"brief.primary_payoff: {tier1.primary_payoff[:80]}"

    # Check content for payoff keywords
    payoff_hits = [kw for kw in _PAYOFF_KEYWORDS if kw in content_lower]
    if len(payoff_hits) >= 2:
        return True, f"payoff_keywords: {', '.join(payoff_hits[:5])}"

    # Check contract payoff_types
    for ptype in contract.payoff_types:
        if ptype and ptype.lower() in content_lower:
            return True, f"payoff_type_match: {ptype}"

    # v6.10.9: Check contract core_loop step labels/descriptions
    for step in contract.core_loop:
        for text in (step.label, step.description):
            if text and len(text) >= 2 and text.lower() in content_lower:
                return True, f"core_loop_step_match: {step.id}:{text[:60]}"

    # v6.10.9: Broader outcome pattern — sacrifice/consumption leading to result
    outcome_patterns = [
        r"(撕裂|牺牲|消耗|献祭|燃烧).{0,30}(记忆|感官|生命力|血|魂|代价).{0,30}(激活|触发|释放|打开|启动|兑现|换来|得到)",
        r"(代价|牺牲|消耗).{0,18}(换来|得到|获得|开启|激活)",
        r"(感知|感应|触碰|连接|同步).{0,24}(裂纹|断裂|变化|波动|反馈|回应|突破)",
        r"(封锁|压制|控制|束缚).{0,24}(破裂|崩断|撕裂|失效|瓦解)",
    ]
    for pat in outcome_patterns:
        if re.search(pat, content):
            return True, f"outcome_pattern_match: {pat[:60]}"

    return False, ""


def _check_core_loop_steps(
    content: str,
    brief: ChapterBrief | None,
    contract: StoryContract,
) -> list[str]:
    """Identify which core loop steps appear completed in the chapter."""
    content_lower = content.lower()
    completed: list[str] = []

    # From brief
    if brief and brief.tier1.core_loop_target:
        target = brief.tier1.core_loop_target.strip()
        if target:
            # Map target to core loop step IDs
            for step in contract.core_loop:
                if step.label.lower() in target.lower() or step.id.lower() in target.lower():
                    completed.append(step.id)
                    break
            else:
                # If no match to contract steps, record the target itself
                completed.append(target)

    # From content — check each step's label
    for step in contract.core_loop:
        if step.id in completed:
            continue
        label_lower = step.label.lower()
        if label_lower and label_lower in content_lower:
            completed.append(step.id)

    return completed


def _check_supporting_mechanism_dominance(
    content: str,
    brief: ChapterBrief | None,
    contract: StoryContract,
) -> tuple[bool, str]:
    """Check if supporting mechanisms dominate the chapter instead of serving core loop.

    Returns (dominant, evidence).
    """
    content_lower = content.lower()

    # Count pressure keyword hits
    pressure_hits = sum(1 for kw in _PRESSURE_KEYWORDS if kw in content_lower)
    payoff_hits = sum(1 for kw in _PAYOFF_KEYWORDS if kw in content_lower)

    # Check if brief explicitly lists supporting mechanisms
    if brief and brief.tier2.supporting_mechanisms_used:
        mech_count = len(brief.tier2.supporting_mechanisms_used)
        if mech_count >= 3 and not brief.tier1.core_loop_target:
            return True, f"brief has {mech_count} supporting mechanisms but no core_loop_target"

    # Heuristic: pressure keywords significantly outnumber payoff keywords
    if pressure_hits >= 4 and payoff_hits == 0:
        return True, f"pressure_keywords({pressure_hits}) >> payoff_keywords({payoff_hits})"

    # Check if contract drift rules flag this
    for rule in contract.drift_rules:
        if rule.id == "pressure_not_primary" and pressure_hits >= 3 and payoff_hits == 0:
            return True, f"drift_rule triggered: {rule.description}"

    return False, ""


def _count_new_mechanisms(
    content: str,
    brief: ChapterBrief | None,
) -> int:
    """Count new mechanisms introduced in this chapter."""
    content_lower = content.lower()
    count = 0

    # From brief
    if brief and brief.tier2.new_mechanisms_allowed:
        count = len(brief.tier2.new_mechanisms_allowed)

    # From content keywords
    keyword_hits = sum(1 for kw in _NEW_MECHANISM_KEYWORDS if kw in content_lower)
    # Only count if brief didn't already specify
    if count == 0 and keyword_hits >= 2:
        count = keyword_hits

    return count


def _check_protagonist_agency(
    content: str,
    brief: ChapterBrief | None,
) -> tuple[bool, str]:
    """Check if the protagonist shows agency (not purely passive).

    Returns (has_agency, evidence).
    """
    content_lower = content.lower()

    # From brief
    if brief and brief.tier1.protagonist_agency:
        if len(brief.tier1.protagonist_agency.strip()) > 5:
            return True, f"brief.protagonist_agency: {brief.tier1.protagonist_agency[:80]}"

    active_hits = sum(1 for kw in _ACTIVE_KEYWORDS if kw in content_lower)
    passive_hits = sum(1 for kw in _PASSIVE_KEYWORDS if kw in content_lower)

    if active_hits >= 2:
        return True, f"active_keywords({active_hits})"
    if passive_hits >= 3 and active_hits == 0:
        return False, f"passive_keywords({passive_hits}) >> active_keywords({active_hits})"

    # Default: assume agency present unless clear evidence otherwise
    return True, "default"


# ── Trend checks ─────────────────────────────────────────────────

def _check_payoff_gap_trend(
    recent_metrics: list[ChapterContractMetrics],
    current_result: CoreLoopCheckResult,
    chapter_number: int,
    window: int = 2,
) -> DriftSignal | None:
    """Check if recent chapters have a payoff gap (no core payoff in window)."""
    current_metric = ChapterContractMetrics(
        chapter_number=chapter_number,
        core_payoff_present=current_result.core_payoff_present,
    )
    metrics = [*recent_metrics, current_metric]
    if len(metrics) < window:
        return None

    recent = metrics[-window:]
    gap_count = sum(1 for m in recent if not m.core_payoff_present)
    if gap_count >= window:
        return DriftSignal(
            drift_type="payoff_gap",
            severity="warning",
            description=f"连续{window}章没有核心兑现",
            evidence=f"最近{window}章（含当前章）core_payoff_present 均为 False",
        )
    return None


def _check_pressure_dominance_streak(
    recent_metrics: list[ChapterContractMetrics],
    window: int = 2,
) -> DriftSignal | None:
    """Check if recent chapters show supporting mechanism dominance streak."""
    if len(recent_metrics) < window:
        return None

    recent = recent_metrics[-window:]
    dominance_count = sum(1 for m in recent if m.dominant_mechanism and m.dominant_mechanism != "core_loop")
    if dominance_count >= window:
        return DriftSignal(
            drift_type="pressure_mechanism_dominance",
            severity="warning",
            description=f"连续{window}章辅助机制主导",
            evidence=f"最近{window}章 dominant_mechanism 非 core_loop",
        )
    return None


def _evaluate_drift_rules(
    contract: StoryContract,
    recent_metrics: list[ChapterContractMetrics],
    current_result: CoreLoopCheckResult,
    chapter_number: int,
) -> list[DriftSignal]:
    """Evaluate contract drift rules against current and recent data."""
    signals: list[DriftSignal] = []

    for rule in contract.drift_rules:
        window = rule.window_chapters
        threshold = rule.threshold

        if rule.id == "pressure_not_primary":
            if current_result.supporting_mechanism_dominance:
                signals.append(DriftSignal(
                    drift_type="pressure_mechanism_dominance",
                    severity=rule.severity,
                    description=rule.description,
                    evidence="current chapter supporting mechanism dominance detected",
                ))

        elif rule.id == "payoff_within_window":
            signal = _check_payoff_gap_trend(recent_metrics, current_result, chapter_number, window)
            if signal:
                signal.severity = rule.severity
                signals.append(signal)

        elif rule.id == "new_mechanism_budget":
            if current_result.new_mechanism_count > threshold:
                signals.append(DriftSignal(
                    drift_type="new_mechanism_overload",
                    severity=rule.severity,
                    description=rule.description,
                    evidence=f"new_mechanism_count={current_result.new_mechanism_count} > threshold={threshold}",
                ))

    return signals


# ── Main checker ─────────────────────────────────────────────────

def check_core_loop_compliance(
    *,
    project_id: str,
    chapter_number: int,
    content: str,
    story_contract: StoryContract,
    chapter_brief: ChapterBrief | None = None,
    recent_contract_metrics: list[ChapterContractMetrics] | None = None,
) -> CoreLoopCheckResult:
    """Check a chapter against its Story Contract.

    Deterministic checks run first. LLM-assisted checks are a future enhancement.

    Args:
        project_id: Project identifier
        chapter_number: Chapter number being checked
        content: Chapter text content
        story_contract: The project's StoryContract
        chapter_brief: Optional ChapterBrief for richer signals
        recent_contract_metrics: Optional list of recent chapter metrics for trend checks

    Returns:
        CoreLoopCheckResult with compliance status and signals
    """
    recent = sorted(recent_contract_metrics or [], key=lambda m: m.chapter_number)
    result = CoreLoopCheckResult()

    # 1. Evidence-grounded core payoff presence
    evidence = _analyze_core_loop_evidence(content, chapter_brief, story_contract, recent)
    result.reward_acquired = evidence.reward_acquired
    result.reward_used = evidence.reward_used
    result.enemy_consequence = evidence.enemy_consequence
    result.required_payoff_present = evidence.required_payoff_present
    result.missing_evidence = evidence.missing_evidence
    result.evidence_spans = evidence.evidence_spans
    result.tracked_states = evidence.tracked_states
    result.state_deltas = evidence.state_deltas

    payoff_evidence = ""
    if evidence.evidence_spans.get("army_payoff"):
        payoff_evidence = "army_payoff"
    elif evidence.evidence_spans.get("reward_used"):
        payoff_evidence = "reward_used"
    elif evidence.evidence_spans.get("enemy_consequence"):
        payoff_evidence = "enemy_consequence"

    result.core_payoff_present = bool(
        evidence.required_payoff_present
        and evidence.reward_acquired
        and (evidence.reward_used or evidence.enemy_consequence or evidence.army_payoff)
    )
    if not result.core_payoff_present:
        result.drift_signals.append(DriftSignal(
            drift_type="core_payoff_missing",
            severity="warning",
            description="本章未检测到核心兑现证据",
            chapter_number=chapter_number,
        ))
        result.warnings.append("本章未检测到核心兑现证据")

    if evidence.missing_evidence:
        missing_text = "、".join(evidence.missing_evidence)
        severity = (
            "blocking"
            if story_contract.status in {"active", "confirmed"}
            and any(item.startswith(("reward_used", "contract_required_payoff", "state_delta:")) for item in evidence.missing_evidence)
            else "warning"
        )
        result.drift_signals.append(DriftSignal(
            drift_type="core_payoff_missing",
            severity=severity,
            description=f"核心循环缺少正文证据：{missing_text}",
            evidence=missing_text,
            chapter_number=chapter_number,
        ))
        result.warnings.append(f"核心循环缺少正文证据：{missing_text}")

    # 2. Core loop steps
    result.core_loop_steps_completed = _check_core_loop_steps(content, chapter_brief, story_contract)
    if evidence.reward_acquired and "reward" not in result.core_loop_steps_completed:
        result.core_loop_steps_completed.append("reward")
    if evidence.reward_used and "payoff" not in result.core_loop_steps_completed:
        result.core_loop_steps_completed.append("payoff")
    if evidence.enemy_consequence and "reaction" not in result.core_loop_steps_completed:
        result.core_loop_steps_completed.append("reaction")

    # 3. Supporting mechanism dominance
    dominant, dominance_evidence = _check_supporting_mechanism_dominance(content, chapter_brief, story_contract)
    result.supporting_mechanism_dominance = dominant
    if dominant:
        result.warnings.append(f"辅助机制可能喧宾夺主: {dominance_evidence}")

    # 4. New mechanism count
    result.new_mechanism_count = _count_new_mechanisms(content, chapter_brief)

    # 5. Protagonist agency
    agency, agency_evidence = _check_protagonist_agency(content, chapter_brief)
    result.protagonist_agency_present = agency
    if not agency:
        result.drift_signals.append(DriftSignal(
            drift_type="protagonist_agency_gap",
            severity="warning",
            description="主角在本章中缺乏主动性",
            evidence=agency_evidence,
            chapter_number=chapter_number,
        ))
        result.warnings.append("主角在本章中缺乏主动性")

    # 6. Drift rule evaluation (contract + trend)
    drift_signals = _evaluate_drift_rules(story_contract, recent, result, chapter_number)
    result.drift_signals.extend(drift_signals)

    # 7. Calculate score
    score = 100.0
    for signal in result.drift_signals:
        if signal.severity == "blocking":
            score -= 25
        elif signal.severity == "warning":
            score -= 10
    result.score = max(0.0, min(100.0, score))

    # 8. Determine pass/fail
    blocking_signals = [s for s in result.drift_signals if s.severity == "blocking"]
    if blocking_signals:
        result.passed = False
        result.blocking_issues = [s.description for s in blocking_signals]
    else:
        result.passed = True

    # 9. Build contract metrics for ledger persistence
    dominant_mech = ""
    if result.supporting_mechanism_dominance:
        # Try to identify which mechanism dominated
        if chapter_brief and chapter_brief.tier2.supporting_mechanisms_used:
            dominant_mech = chapter_brief.tier2.supporting_mechanisms_used[0]
        else:
            dominant_mech = "pressure"

    result.contract_metrics = ChapterContractMetrics(
        chapter_number=chapter_number,
        core_payoff_present=result.core_payoff_present,
        payoff_type=payoff_evidence[:80] if payoff_evidence else "",
        core_loop_steps_completed=result.core_loop_steps_completed,
        supporting_mechanisms_used=(
            chapter_brief.tier2.supporting_mechanisms_used if chapter_brief else []
        ),
        dominant_mechanism=dominant_mech,
        new_mechanisms_introduced=(
            chapter_brief.tier2.new_mechanisms_allowed if chapter_brief else []
        ),
        protagonist_agency=result.protagonist_agency_present,
        contract_drift_warnings=[s.description for s in result.drift_signals if s.severity == "warning"],
        contract_score=result.score,
        reward_acquired=result.reward_acquired,
        reward_used=result.reward_used,
        enemy_consequence=result.enemy_consequence,
        required_payoff_present=result.required_payoff_present,
        missing_evidence=result.missing_evidence,
        evidence_spans=result.evidence_spans,
        tracked_states=result.tracked_states,
        state_deltas=result.state_deltas,
    )

    return result


# ── Fallback Story Contract derivation ───────────────────────────

def derive_fallback_story_contract(
    project_id: str,
    launch_profile: dict[str, Any] | None,
    genre_contract: dict[str, Any] | None,
    genre_profile: dict[str, Any] | None = None,
) -> StoryContract:
    """Derive a read-only fallback StoryContract from existing contracts.

    Used when no explicit story_contract exists for a project.
    """
    core_promise = ""
    core_loop_steps: list = []
    supporting_mechs: list = []
    payoff_types: list = []
    drift_rules: list = []
    cadence: dict[str, int] = {}

    # Extract from launch_profile
    if launch_profile:
        core_promise = str(launch_profile.get("primary_payoff_loop", ""))
        if not core_promise:
            core_promise = str(launch_profile.get("core_hook", ""))

    # Extract from genre_contract
    if genre_contract:
        # Derive core loop from payoff cadence
        payoff_cadence = genre_contract.get("payoff_cadence", {})
        if isinstance(payoff_cadence, dict):
            cadence = {
                "minor_payoff": _parse_cadence_number(payoff_cadence.get("minor_payoff", "")),
                "visible_upgrade": _parse_cadence_number(payoff_cadence.get("visible_upgrade", "")),
                "public_reversal": _parse_cadence_number(payoff_cadence.get("public_reversal", "")),
            }

        # Build generic core loop steps from genre beats
        must_have = genre_contract.get("must_have_beats", [])
        if must_have:
            for i, beat in enumerate(must_have[:6]):
                core_loop_steps.append({
                    "id": f"step_{i+1}",
                    "label": str(beat)[:50],
                    "description": str(beat),
                    "payoff_type": "",
                    "required": True,
                })

        # Forbidden drift -> drift rules
        forbidden = genre_contract.get("forbidden_drift", [])
        for i, rule_text in enumerate(forbidden[:5]):
            drift_rules.append({
                "id": f"forbidden_{i+1}",
                "description": str(rule_text),
                "severity": "warning",
                "window_chapters": 2,
                "threshold": 1,
            })

    # Build generic core loop if none derived
    if not core_loop_steps:
        core_loop_steps = [
            {"id": "trigger", "label": "触发核心机会", "required": True},
            {"id": "action", "label": "完成核心动作", "required": True},
            {"id": "reward", "label": "获得明确收益", "required": True},
            {"id": "payoff", "label": "兑现收益", "required": True},
            {"id": "reaction", "label": "外部反馈", "required": False},
            {"id": "hook", "label": "下一章钩子", "required": False},
        ]

    # Default drift rules if none derived
    if not drift_rules:
        drift_rules = [
            DriftRule(
                id="pressure_not_primary",
                description="辅助机制不能替代核心循环",
                severity="warning",
                window_chapters=2,
                threshold=1,
            ),
            DriftRule(
                id="payoff_within_window",
                description=f"连续{_default_window(cadence)}章内必须至少完成一次核心兑现",
                severity="warning",
                window_chapters=_default_window(cadence),
                threshold=1,
            ),
        ]

    return StoryContract(
        project_id=project_id,
        core_promise=core_promise,
        core_loop=[
            CoreLoopStep(**s) if isinstance(s, dict) else s
            for s in core_loop_steps
        ],
        supporting_mechanisms=[
            SupportingMechanism(**m) if isinstance(m, dict) else m
            for m in supporting_mechs
        ],
        payoff_types=payoff_types,
        drift_rules=[
            DriftRule(**r) if isinstance(r, dict) else r
            for r in drift_rules
        ],
        cadence=cadence,
        status="fallback",
        version="1.0.0",
    )


def _parse_cadence_number(text: str) -> int:
    """Extract a number from cadence text like '每3-5章' -> 3."""
    import re
    if not text:
        return 1
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 1


def _default_window(cadence: dict[str, int]) -> int:
    """Default window for payoff_gap drift rule."""
    return max(2, cadence.get("minor_payoff", 1) * 2)
