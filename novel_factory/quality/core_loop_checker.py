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


# ── Deterministic checks ─────────────────────────────────────────

def _check_core_payoff_present(
    content: str,
    brief: ChapterBrief | None,
    contract: StoryContract,
) -> tuple[bool, str]:
    """Check if the chapter contains evidence of core payoff delivery.

    Returns (present, evidence).
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
    window: int = 2,
) -> DriftSignal | None:
    """Check if recent chapters have a payoff gap (no core payoff in window)."""
    if len(recent_metrics) < window:
        return None

    recent = recent_metrics[-window:]
    gap_count = sum(1 for m in recent if not m.core_payoff_present)
    if gap_count >= window:
        return DriftSignal(
            drift_type="payoff_gap",
            severity="warning",
            description=f"连续{window}章没有核心兑现",
            evidence=f"最近{window}章 core_payoff_present 均为 False",
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
            signal = _check_payoff_gap_trend(recent_metrics, window)
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
    recent = recent_contract_metrics or []
    result = CoreLoopCheckResult()

    # 1. Core payoff presence
    payoff_present, payoff_evidence = _check_core_payoff_present(content, chapter_brief, story_contract)
    result.core_payoff_present = payoff_present
    if not payoff_present:
        result.drift_signals.append(DriftSignal(
            drift_type="core_payoff_missing",
            severity="warning",
            description="本章未检测到核心兑现证据",
            chapter_number=chapter_number,
        ))
        result.warnings.append("本章未检测到核心兑现证据")

    # 2. Core loop steps
    result.core_loop_steps_completed = _check_core_loop_steps(content, chapter_brief, story_contract)

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
    drift_signals = _evaluate_drift_rules(story_contract, recent, result)
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
