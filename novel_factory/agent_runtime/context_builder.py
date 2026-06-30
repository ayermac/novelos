"""Unified context builder for v6.6.2 Agent Context Inheritance Foundation.

Provides structured context assembly across Planner / Screenwriter / Author /
Polisher / Editor with trusted-memory filtering, timeline-constraint extraction,
and budget-aware formatting.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ..validators.chapter_checker import derive_word_target
from ..quality.numeric_state import (
    numeric_state_constraint_from_text,
    numeric_state_constraints_from_facts,
)
from ..context.aging import build_aging_warnings
from ..context.recall_channel import build_pull_context

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────

_TRUSTED_MEMORY_MIN_CONFIDENCE = 0.75
_UNTRUSTED_MEMORY_MAX_CONFIDENCE = 0.45
_MAX_CONTEXT_CHARS = 14000

# v6.10.14 S7: Adaptive budget thresholds based on project chapter count.
# When a project exceeds _ADAPTIVE_BUDGET_CHAPTER_THRESHOLD chapters, the
# default budget is raised to _ADAPTIVE_BUDGET_LONGFORM_CHARS.
_ADAPTIVE_BUDGET_CHAPTER_THRESHOLD = 100
_ADAPTIVE_BUDGET_LONGFORM_CHARS = 20000

# v6.10.14 S1: Buckets that must never be dropped by budget truncation.
# Even when total prompt length exceeds max_chars, these are force-included
# so critical constraints (numeric state, timeline, hard constraints) survive.
_MANDATORY_BUCKETS: frozenset[str] = frozenset({
    "hard_constraints",
    "numeric_state_constraints",
    "timeline_constraints",
})

# v6.10.14 S2/S4: Aging threshold — facts not updated for this many chapters
# are considered "aged" and force-included in relevance filtering.
_AGING_THRESHOLD_CHAPTERS = 20

_TIMELINE_KEYWORDS = re.compile(
    r"(?:三天后|三日后|72小时|72h|四天后|五天后|六天后|七天后|"
    r"一周后|两周后|一个月后|"
    r"明天|今晚|今夜|次日|翌日|第二天|后天|"
    r".*小时后|.*分钟后|"
    r"截止时间|截止日期|期限| deadline |"
    r"约定地点|约定时间|下次见面|再次见面|准时赴约|"
    r"期限类威胁|倒计时|时间不多|没时间了)",
    re.IGNORECASE,
)
_CLOCK_PATTERN = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?!\d)")
_COUNTDOWN_CONTEXT_PATTERN = re.compile(
    r"(?:倒计时|计时|左眼|数字|猩红|暴跌|猛跌|预支|利息|锁链|崩断|搏动|心脏|剩余)"
)

# ── Data classes ─────────────────────────────────────────────────

@dataclass
class ContextItem:
    """A single piece of context with provenance and trust metadata."""

    kind: str
    text: str
    source: str = ""
    confidence: float = 1.0
    chapter_number: int | None = None
    priority: int = 5
    trusted: bool = True


@dataclass
class AgentContextBundle:
    """Structured bundle of all context categories for an agent."""

    project_context: list[ContextItem] = field(default_factory=list)
    chapter_inheritance: list[ContextItem] = field(default_factory=list)
    trusted_memory: list[ContextItem] = field(default_factory=list)
    story_facts: list[ContextItem] = field(default_factory=list)
    plot_obligations: list[ContextItem] = field(default_factory=list)
    timeline_constraints: list[ContextItem] = field(default_factory=list)
    numeric_state_constraints: list[ContextItem] = field(default_factory=list)
    character_states: list[ContextItem] = field(default_factory=list)
    revision_feedback: list[ContextItem] = field(default_factory=list)
    hard_constraints: list[ContextItem] = field(default_factory=list)
    advisory_context: list[ContextItem] = field(default_factory=list)
    diagnostics: list[ContextItem] = field(default_factory=list)
    # v6.10.4: style bible context
    style_context: list[ContextItem] = field(default_factory=list)
    # v6.10.5: story contract context
    story_contract_context: list[ContextItem] = field(default_factory=list)
    # v6.6.14: memory context annotation
    memory_context_degraded: bool = False
    trusted_memory_batch_id: str | None = None
    # v6.10.9: scene beats for editor beat-design routing
    scene_beats: list[ContextItem] = field(default_factory=list)
    # v6.10.9: chapter brief core_loop / fact_locks for editor
    core_loop_context: list[ContextItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for trace / artifact metadata (no API keys)."""
        return {
            "trusted_memory_count": len(self.trusted_memory),
            "timeline_constraints_count": len(self.timeline_constraints),
            "numeric_state_constraints_count": len(self.numeric_state_constraints),
            "plot_obligations_count": len(self.plot_obligations),
            "hard_constraints_count": len(self.hard_constraints),
            "advisory_count": len(self.advisory_context),
            "revision_feedback_count": len(self.revision_feedback),
            "story_facts_count": len(self.story_facts),
            "character_states_count": len(self.character_states),
            "style_context_count": len(self.style_context),
            "story_contract_context_count": len(self.story_contract_context),
            "memory_context_degraded": self.memory_context_degraded,
            "trusted_memory_batch_id": self.trusted_memory_batch_id,
        }


# ── Trusted memory helpers ───────────────────────────────────────

def _is_trusted_memory_item(item: dict[str, Any]) -> bool:
    """Return True if a memory item qualifies as trusted.

    Trusted conditions:
    - confidence >= 0.75
    - has evidence_text
    - not fallback / degraded / no-op
    """
    confidence = float(item.get("confidence") or 0)
    if confidence < _TRUSTED_MEMORY_MIN_CONFIDENCE:
        return False
    evidence = str(item.get("evidence_text") or "").strip()
    if not evidence:
        return False
    rationale = str(item.get("rationale") or "").lower()
    if "状态卡兜底" in rationale or "fallback" in rationale or "degraded" in rationale:
        return False
    if "no-op" in rationale or " degraded " in rationale:
        return False
    return True


def _is_untrusted_memory_item(item: dict[str, Any]) -> bool:
    """Return True if a memory item is explicitly untrusted."""
    confidence = float(item.get("confidence") or 0)
    if confidence <= _UNTRUSTED_MEMORY_MAX_CONFIDENCE:
        return True
    evidence = str(item.get("evidence_text") or "").strip()
    if not evidence:
        return True
    rationale = str(item.get("rationale") or "").lower()
    if "状态卡兜底" in rationale or "fallback" in rationale or "degraded" in rationale:
        return True
    if "no-op" in rationale:
        return True
    return False


def _select_trusted_memory_batch(
    repo: Any, project_id: str, chapter_number: int
) -> tuple[dict | None, list[dict]]:
    """Select the best non-fallback memory batch for a chapter."""
    try:
        batches = [
            batch
            for batch in repo.list_memory_batches(project_id)
            if int(batch.get("chapter_number") or 0) == int(chapter_number)
            and str(batch.get("status") or "") != "ignored"
            and "状态卡兜底" not in str(batch.get("summary") or "")
            and "fallback" not in str(batch.get("summary") or "").lower()
            and "degraded" not in str(batch.get("summary") or "").lower()
        ]
    except Exception:
        return None, []

    candidates: list[tuple[float, str, dict, list[dict]]] = []
    for batch in batches:
        try:
            items = [
                item
                for item in repo.list_memory_items(batch["id"])
                if str(item.get("status") or "") != "ignored"
            ]
        except Exception:
            continue
        if not items:
            continue
        if any("状态卡兜底候选" in str(item.get("rationale") or "") for item in items):
            continue
        if any("fallback_created" in str(item.get("rationale") or "").lower() for item in items):
            continue
        avg_confidence = sum(float(item.get("confidence") or 0) for item in items) / max(
            1, len(items)
        )
        if avg_confidence < _TRUSTED_MEMORY_MIN_CONFIDENCE:
            continue
        candidates.append(
            (avg_confidence, str(batch.get("created_at") or ""), batch, items)
        )

    if not candidates:
        return None, []
    _confidence, _created_at, batch, items = max(candidates, key=lambda row: (row[0], row[1]))
    return batch, items


def _select_recent_memory_items(
    repo: Any, project_id: str, chapter_number: int
) -> list[tuple[dict, dict]]:
    """Return recent non-ignored memory items for advisory classification."""
    try:
        batches = [
            batch
            for batch in repo.list_memory_batches(project_id)
            if int(batch.get("chapter_number") or 0) == int(chapter_number)
            and str(batch.get("status") or "") != "ignored"
        ]
    except Exception:
        return []

    pairs: list[tuple[dict, dict]] = []
    for batch in batches:
        try:
            items = [
                item
                for item in repo.list_memory_items(batch["id"])
                if str(item.get("status") or "") != "ignored"
            ]
        except Exception:
            continue
        pairs.extend((batch, item) for item in items)
    return pairs


# ── Timeline extraction ──────────────────────────────────────────

def extract_timeline_constraints(
    project_id: str,
    chapter_number: int,
    repo: Any,
) -> list[ContextItem]:
    """Extract timeline constraints from story_facts, plot_holes, and prev state.

    Does NOT require a new DB table.
    """
    items: list[ContextItem] = []
    if chapter_number <= 1:
        return items

    prev_ch = chapter_number - 1

    # 1. story_facts with timeline-related fact_type or content
    try:
        facts = repo.list_story_facts(project_id, status="active")
    except Exception:
        facts = []
    for fact in facts:
        fact_type = str(fact.get("fact_type") or "").lower()
        value = str(fact.get("value_json") or "")
        subject = str(fact.get("subject") or "")
        attribute = str(fact.get("attribute") or "")
        text = f"{subject}.{attribute}: {value}" if subject or attribute else value
        source_chapter = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
        if fact_type in ("timeline_event", "time_constraint", "deadline", "appointment") and _is_current_timeline_constraint(
            fact_type,
            text,
            source_chapter=source_chapter,
            current_chapter=chapter_number,
        ):
            items.append(
                ContextItem(
                    kind="timeline_constraint",
                    text=text,
                    source=f"story_fact:{fact.get('fact_key')}",
                    confidence=float(fact.get("confidence") or 1.0),
                    chapter_number=source_chapter,
                    priority=1,
                    trusted=True,
                )
            )
        elif _TIMELINE_KEYWORDS.search(text) and _is_current_timeline_constraint(
            fact_type,
            text,
            source_chapter=source_chapter,
            current_chapter=chapter_number,
            inferred=True,
        ):
            items.append(
                ContextItem(
                    kind="timeline_constraint",
                    text=text,
                    source=f"story_fact:{fact.get('fact_key')}",
                    confidence=float(fact.get("confidence") or 1.0),
                    chapter_number=source_chapter,
                    priority=2,
                    trusted=True,
                )
            )

    # 2. plot_holes with timeline keywords in title/description
    try:
        plots = repo.list_plot_holes(project_id)
    except Exception:
        plots = []
    for plot in plots:
        text = f"{plot.get('title', '')}: {plot.get('description', '')}"
        if _TIMELINE_KEYWORDS.search(text):
            items.append(
                ContextItem(
                    kind="timeline_constraint",
                    text=text,
                    source=f"plot_hole:{plot.get('code')}",
                    confidence=0.85,
                    chapter_number=int(plot.get("planted_chapter") or 0),
                    priority=2,
                    trusted=True,
                )
            )

    # 3. Previous chapter state card suspense hooks
    try:
        prev_state = repo.get_chapter_state(project_id, prev_ch)
    except Exception:
        prev_state = None
    if prev_state:
        state_data = prev_state.get("state_data")
        if isinstance(state_data, str):
            try:
                state_data = json.loads(state_data)
            except Exception:
                state_data = {}
        if isinstance(state_data, dict):
            for key in ("suspense_hooks", "悬念", "未处理悬念"):
                hooks = state_data.get(key)
                if isinstance(hooks, list):
                    for hook in hooks:
                        hook_text = str(hook)
                        if _TIMELINE_KEYWORDS.search(hook_text):
                            items.append(
                                ContextItem(
                                    kind="timeline_constraint",
                                    text=hook_text,
                                    source="prev_state_card:suspense",
                                    confidence=0.9,
                                    chapter_number=prev_ch,
                                    priority=1,
                                    trusted=True,
                                )
                            )

    # 4. Previous chapter precise countdown / timer state.
    try:
        prev_chapter = repo.get_chapter(project_id, prev_ch)
    except Exception:
        prev_chapter = None
    prev_tail = str((prev_chapter or {}).get("content") or "")[-900:]
    precise_timer = _extract_precise_timer_constraint(prev_tail)
    if precise_timer:
        items.append(
            ContextItem(
                kind="timeline_constraint",
                text=precise_timer,
                source="prev_chapter_tail:precise_timer",
                confidence=1.0,
                chapter_number=prev_ch,
                priority=1,
                trusted=True,
            )
        )

    # Deduplicate by text
    seen: set[str] = set()
    deduped: list[ContextItem] = []
    for it in items:
        key = it.text.strip()[:120]
        if key and key not in seen:
            seen.add(key)
            deduped.append(it)
    return deduped


def _extract_precise_timer_constraint(text: str) -> str:
    source = str(text or "")
    clocks = _CLOCK_PATTERN.findall(source)
    if len(clocks) < 2 or not _COUNTDOWN_CONTEXT_PATTERN.search(source):
        return ""
    last_clock = clocks[-1]
    sequence = " → ".join(clocks[-5:])
    return (
        f"上一章结尾精确倒计时/计数器已推进至 {last_clock}；"
        f"尾部序列：{sequence}。"
        "本章开头必须从该状态之后继续，禁止回退到更大的倒计时或重复已完成序列，除非明确标注闪回/回放。"
    )


def extract_numeric_state_constraints(
    project_id: str,
    chapter_number: int,
    repo: Any,
) -> list[ContextItem]:
    """Extract numeric state constraints from applied facts and previous tail."""
    items: list[ContextItem] = []
    if chapter_number <= 1:
        return items

    try:
        facts = [
            fact for fact in repo.list_story_facts(project_id, status="active")
            if int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0) <= chapter_number
        ]
    except Exception:
        facts = []

    fact_lines = numeric_state_constraints_from_facts(facts)[:20]  # v6.10.14 F14: relaxed from 10 to 20
    if fact_lines:
        items.append(
            ContextItem(
                kind="numeric_state_constraint",
                text=(
                    "已确认数值状态：\n"
                    + "\n".join(f"- {line}" for line in fact_lines)
                    + "\n必须继承；如发生变化，正文必须明确写出触发事件和变化过程。"
                ),
                source="story_facts:numeric_state",
                confidence=1.0,
                priority=1,
                trusted=True,
            )
        )

    prev_ch = chapter_number - 1
    try:
        prev_chapter = repo.get_chapter(project_id, prev_ch)
    except Exception:
        prev_chapter = None
    prev_tail = str((prev_chapter or {}).get("content") or "")[-1200:]
    tail_constraint = numeric_state_constraint_from_text(prev_tail, prefix="上一章结尾")
    if tail_constraint and not any(tail_constraint == item.text for item in items):
        items.append(
            ContextItem(
                kind="numeric_state_constraint",
                text=tail_constraint,
                source="prev_chapter_tail:numeric_state",
                confidence=0.95,
                chapter_number=prev_ch,
                priority=1,
                trusted=True,
            )
        )

    return items


_FULFILLED_TIMELINE_MARKERS = (
    "完成",
    "离开",
    "出门",
    "前往",
    "抵达",
    "到达",
    "进入",
    "进去",
    "踏进",
    "坐下",
    "落座",
    "待命",
    "接到指令",
    "已",
)

_STALE_RELATIVE_TIME_MARKERS = ("今晚", "今夜", "当晚", "十分钟前")


def _is_current_timeline_constraint(
    fact_type: str,
    text: str,
    *,
    source_chapter: int,
    current_chapter: int,
    inferred: bool = False,
) -> bool:
    """Return whether a timeline-like fact should constrain this chapter.

    Historical timestamps are still valuable story facts, but they must not be
    promoted to current hard constraints after the story has moved past them.
    Otherwise an old "left the office at 22:05" fact can overpower the latest
    chapter seam and make a revision jump backward in time.
    """
    fact_type = str(fact_type or "").lower()
    text = str(text or "")

    if source_chapter and source_chapter < max(1, current_chapter - 1):
        if any(marker in text for marker in _STALE_RELATIVE_TIME_MARKERS):
            return False
        if any(marker in text for marker in _FULFILLED_TIMELINE_MARKERS):
            return False

    if fact_type in {"deadline", "appointment", "time_constraint"}:
        return True

    if source_chapter and source_chapter < max(1, current_chapter - 1):
        return False

    if fact_type == "timeline_event" or inferred:
        if any(marker in text for marker in _FULFILLED_TIMELINE_MARKERS):
            return False
        return True

    return True


# ── Builder ──────────────────────────────────────────────────────

class AgentContextBuilder:
    """Builds AgentContextBundle for each agent in the workflow."""

    def __init__(self, repo: Any) -> None:
        self.repo = repo
        # v6.10.14 S2: Cache for chapter briefs to avoid repeated DB lookups
        self._brief_cache: dict[str, dict[str, Any] | None] = {}

    def _latest_approved_genesis_at(self, project_id: str) -> str | None:
        """Return the latest approved genesis timestamp, if any."""
        try:
            runs = self.repo.list_genesis_runs(project_id)
        except Exception:
            return None
        approved = [
            str(run.get("updated_at") or run.get("created_at") or "")
            for run in runs
            if str(run.get("status") or "") == "approved"
        ]
        return max(approved) if approved else None

    # ── Shared helpers ───────────────────────────────────────────

    def _project_context(self, project_id: str) -> list[ContextItem]:
        """High-level project info (genre, description)."""
        items: list[ContextItem] = []
        try:
            project = self.repo.get_project(project_id)
        except Exception:
            project = None
        if project:
            description = project.get('description') or ""
            text = f"项目: {project.get('name', '')}\n类型: {project.get('genre', '')}\n简介: {description[:200]}"
            items.append(
                ContextItem(
                    kind="project_info", text=text, source="project", priority=1, trusted=True
                )
            )
        return items

    def _instruction_context(self, project_id: str, chapter_number: int) -> list[ContextItem]:
        items: list[ContextItem] = []
        instruction = self.repo.get_instruction(project_id, chapter_number)
        if instruction:
            project = self.repo.get_project(project_id) or {}
            word_target = derive_word_target(instruction, project)
            text = (
                f"目标: {instruction.get('objective', '')}\n"
                f"关键事件: {instruction.get('key_events', '')}\n"
                f"情绪基调: {instruction.get('emotion_tone', '')}\n"
                f"章末钩子: {instruction.get('ending_hook', '')}\n"
                f"字数目标: {word_target}"
            )
            items.append(
                ContextItem(
                    kind="instruction",
                    text=text,
                    source="instruction",
                    priority=1,
                    trusted=True,
                )
            )
            # Plot obligations from instruction
            for field_name, label in (
                ("plots_to_plant", "埋设伏笔"),
                ("plots_to_resolve", "兑现伏笔"),
            ):
                val = instruction.get(field_name)
                if val:
                    items.append(
                        ContextItem(
                            kind="plot_obligation",
                            text=f"{label}: {val}",
                            source="instruction",
                            priority=1,
                            trusted=True,
                        )
                    )
        return items

    def _previous_chapter_context(
        self, project_id: str, chapter_number: int
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        if chapter_number <= 1:
            return items
        prev_ch = chapter_number - 1
        genesis_cutoff = self._latest_approved_genesis_at(project_id)

        # Previous state card
        prev_state = self.repo.get_chapter_state(project_id, prev_ch)
        if prev_state:
            if genesis_cutoff and str(prev_state.get("created_at") or "") <= genesis_cutoff:
                prev_state = None
        if prev_state:
            state_data = prev_state.get("state_data")
            if isinstance(state_data, str):
                try:
                    state_data = json.loads(state_data)
                except Exception:
                    state_data = {}
            state_text = json.dumps(state_data, ensure_ascii=False, indent=2) if state_data else ""
            if state_text:
                items.append(
                    ContextItem(
                        kind="prev_state_card",
                        text=f"【上一章状态卡】\n{state_text}",
                        source="chapter_state",
                        chapter_number=prev_ch,
                        priority=1,
                        trusted=True,
                    )
                )

        # Previous chapter ending
        prev_chapter = self.repo.get_chapter(project_id, prev_ch)
        if prev_chapter and prev_chapter.get("content"):
            if genesis_cutoff and str(prev_chapter.get("updated_at") or prev_chapter.get("created_at") or "") <= genesis_cutoff:
                prev_chapter = None
        if prev_chapter and prev_chapter.get("content"):
            tail = str(prev_chapter["content"])[-700:]
            items.append(
                ContextItem(
                    kind="prev_chapter_tail",
                    text=f"【上一章结尾摘录】\n{tail}",
                    source="chapter_content",
                    chapter_number=prev_ch,
                    priority=1,
                    trusted=True,
                )
            )

        # Suspense hooks from previous state
        if prev_state:
            state_data = prev_state.get("state_data")
            if isinstance(state_data, str):
                try:
                    state_data = json.loads(state_data)
                except Exception:
                    state_data = {}
            if isinstance(state_data, dict):
                for key in ("suspense_hooks", "悬念", "未处理悬念"):
                    hooks = state_data.get(key)
                    if isinstance(hooks, list):
                        for hook in hooks:
                            items.append(
                                ContextItem(
                                    kind="suspense_hook",
                                    text=f"上一章悬念: {hook}",
                                    source="prev_state_card",
                                    chapter_number=prev_ch,
                                    priority=1,
                                    trusted=True,
                                )
                            )

        return items

    def _trusted_memory_context(
        self, project_id: str, chapter_number: int,
        _bundle: "AgentContextBundle | None" = None,
    ) -> list[ContextItem]:
        """Return trusted memory items from the best batch for prev chapter."""
        items: list[ContextItem] = []
        if chapter_number <= 1:
            return items
        prev_ch = chapter_number - 1

        batch, memory_items = _select_trusted_memory_batch(self.repo, project_id, prev_ch)
        if not batch or not memory_items:
            # v6.6.14: annotate bundle with degraded flag when no trusted batch
            if _bundle is not None:
                _bundle.memory_context_degraded = True
                _bundle.trusted_memory_batch_id = None
            return items

        # v6.6.14: record which batch was used
        if _bundle is not None:
            _bundle.memory_context_degraded = False
            _bundle.trusted_memory_batch_id = str(batch.get("id") or "")

        for item in memory_items:
            if _is_trusted_memory_item(item):
                payload = item.get("after_json") or item.get("before_json") or "{}"
                try:
                    parsed = json.loads(payload) if isinstance(payload, str) else payload
                except Exception:
                    parsed = {}
                code = str(parsed.get("code") or "").strip()
                label = (
                    parsed.get("name")
                    or parsed.get("title")
                    or parsed.get("fact_key")
                    or item.get("target_table")
                )
                target = f"[{code}] {label}" if code else label
                evidence = str(item.get("evidence_text") or "").strip()
                text = f"[{item.get('target_table')}/{item.get('operation')}] {target}"
                if evidence:
                    text += f"\n  证据: {evidence}"
                items.append(
                    ContextItem(
                        kind="trusted_memory",
                        text=text,
                        source=f"memory_batch:{batch.get('id')}",
                        confidence=float(item.get("confidence") or 0),
                        chapter_number=prev_ch,
                        priority=2,
                        trusted=True,
                    )
                )
            elif not _is_untrusted_memory_item(item):
                # Low-confidence but not explicitly untrusted -> advisory
                payload = item.get("after_json") or item.get("before_json") or "{}"
                try:
                    parsed = json.loads(payload) if isinstance(payload, str) else payload
                except Exception:
                    parsed = {}
                label = (
                    parsed.get("name")
                    or parsed.get("title")
                    or parsed.get("fact_key")
                    or item.get("target_table")
                )
                items.append(
                    ContextItem(
                        kind="advisory_memory",
                        text=f"[{item.get('target_table')}/{item.get('operation')}] {label} (confidence={float(item.get('confidence') or 0):.2f})",
                        source=f"memory_batch:{batch.get('id')}",
                        confidence=float(item.get("confidence") or 0),
                        chapter_number=prev_ch,
                        priority=6,
                        trusted=False,
                    )
                )

        return items

    def _advisory_memory_context(self, project_id: str, chapter_number: int) -> list[ContextItem]:
        """Return medium-confidence memory as advisory, even without a trusted batch."""
        items: list[ContextItem] = []
        if chapter_number <= 1:
            return items
        prev_ch = chapter_number - 1
        for batch, item in _select_recent_memory_items(self.repo, project_id, prev_ch):
            if _is_trusted_memory_item(item) or _is_untrusted_memory_item(item):
                continue
            payload = item.get("after_json") or item.get("before_json") or "{}"
            try:
                parsed = json.loads(payload) if isinstance(payload, str) else payload
            except Exception:
                parsed = {}
            label = (
                parsed.get("name")
                or parsed.get("title")
                or parsed.get("fact_key")
                or item.get("target_table")
            )
            items.append(
                ContextItem(
                    kind="advisory_memory",
                    text=f"[{item.get('target_table')}/{item.get('operation')}] {label} (confidence={float(item.get('confidence') or 0):.2f})",
                    source=f"memory_batch:{batch.get('id')}",
                    confidence=float(item.get("confidence") or 0),
                    chapter_number=prev_ch,
                    priority=6,
                    trusted=False,
                )
            )
        return items

    def _story_facts_context(
        self,
        project_id: str,
        chapter_number: int,
        brief: dict[str, Any] | None = None,
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            facts = self.repo.list_story_facts(project_id, status="active")
        except Exception:
            facts = []
        
        # v6.10.11: Deduplicate by subject.attribute, keeping only the latest source_chapter
        # This prevents contradictory facts from being passed to the Author
        latest_facts: dict[str, tuple[dict, int]] = {}
        for fact in facts:
            subject = fact.get("subject") or ""
            attribute = fact.get("attribute") or ""
            key = f"{subject}.{attribute}" if subject and attribute else (subject or attribute or fact.get("fact_key", ""))
            src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
            if src_ch > chapter_number:
                continue
            if key not in latest_facts or src_ch > latest_facts[key][1]:
                latest_facts[key] = (fact, src_ch)

        # v6.10.14 S2: Relevance filtering — reduce noise in long-form projects
        deduped = [fact for fact, _src in latest_facts.values()]
        relevant_facts = self._filter_relevant_facts(deduped, brief, chapter_number)
        
        for fact, src_ch in ((f, int(f.get("source_chapter") or f.get("last_changed_chapter") or 0)) for f in relevant_facts):
            subject = fact.get("subject", "")
            attribute = fact.get("attribute", "")
            value = str(fact.get("value_json") or "")
            fact_type = str(fact.get("fact_type") or "").lower()
            # v6.10.14 F8: numeric_state facts are exempt from truncation —
            # truncating a numeric value mid-string would corrupt the constraint.
            if fact_type != "numeric_state" and len(value) > 200:
                value = value[:200] + "..."
            text = f"{subject}.{attribute} = {value}" if subject or attribute else value
            items.append(
                ContextItem(
                    kind="story_fact",
                    text=text,
                    source=f"story_fact:{fact.get('fact_key')}",
                    confidence=float(fact.get("confidence") or 1.0),
                    chapter_number=src_ch,
                    priority=3 if src_ch == chapter_number - 1 else 4,
                    trusted=True,
                )
            )
        return items

    def _filter_relevant_facts(
        self,
        facts: list[dict[str, Any]],
        brief: dict[str, Any] | None,
        chapter_number: int,
    ) -> list[dict[str, Any]]:
        """v6.10.14 S2: Filter story facts by relevance to the current chapter.

        Rules:
        - ``numeric_state`` facts are always kept (critical values must not be lost).
        - Facts whose ``subject`` matches a brief entity are kept.
        - Facts exceeding the aging threshold (``_AGING_THRESHOLD_CHAPTERS``)
          are kept so long-forgotten foreshadowing is surfaced.
        - When ``brief`` is ``None``, falls back to returning all facts
          (no regression for callers that don't pass a brief).
        """
        if brief is None:
            return facts

        entities = self._extract_entities(brief)
        result: list[dict[str, Any]] = []
        for fact in facts:
            fact_type = str(fact.get("fact_type") or "").lower()
            if fact_type == "numeric_state":
                result.append(fact)
                continue
            subject = str(fact.get("subject") or "")
            if subject and subject in entities:
                result.append(fact)
                continue
            # Aging fallback: keep facts not updated for too many chapters
            src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
            age = chapter_number - src_ch
            if age >= _AGING_THRESHOLD_CHAPTERS:
                result.append(fact)
        return result

    def _extract_entities(self, brief: dict[str, Any]) -> set[str]:
        """v6.10.14 S2: Extract entity names from a chapter brief.

        Sources (in priority order):
        1. ``key_events`` / ``required_events`` from the instruction
        2. Character names from the project (full-name boundary match)
        """
        entities: set[str] = set()

        # 1. Pull entity-like tokens from brief event fields
        for field_name in ("key_events", "required_events", "objective"):
            raw = brief.get(field_name)
            if not raw:
                continue
            if isinstance(raw, (list, tuple)):
                text = " ".join(str(item) for item in raw)
            else:
                text = str(raw)
            # Split on common CJK connectors/particles before extracting name tokens
            text = re.sub(r"[的和与在是把被让给对为有于从到向以以及]", " ", text)
            # Extract CJK name-like tokens (2-6 chars)
            for match in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
                token = match.group()
                entities.add(token)
                # Also add 2-3 char substrings of longer tokens so short name
                # subjects (e.g. "张三" from "张三修炼") can match.
                if len(token) > 3:
                    for i in range(len(token) - 1):
                        entities.add(token[i : i + 2])
                    for i in range(len(token) - 2):
                        entities.add(token[i : i + 3])

        # 2. Add all character names from the project
        try:
            characters = self.repo.get_characters(brief.get("project_id") or "")
            for char in characters:
                name = str(char.get("name") or "").strip()
                if name:
                    entities.add(name)
        except Exception:
            pass

        return entities

    def _load_brief(self, project_id: str, chapter_number: int) -> dict[str, Any] | None:
        """v6.10.14 S2: Load and cache the chapter brief (writing instruction).

        Returns ``None`` if no instruction exists, causing
        :meth:`_story_facts_context` to fall back to full-load (no regression).
        """
        cache_key = f"{project_id}:{chapter_number}"
        if cache_key in self._brief_cache:
            return self._brief_cache[cache_key]
        try:
            instruction = self.repo.get_instruction(project_id, chapter_number)
        except Exception:
            instruction = None
        if instruction:
            instruction["project_id"] = project_id
        self._brief_cache[cache_key] = instruction
        return instruction

    def _character_states_context(self, project_id: str, chapter_number: int) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            characters = self.repo.get_characters(project_id)
        except Exception:
            characters = []
        for c in characters:
            text = f"- {c.get('name')}({c.get('role')}): {c.get('description', '')}"
            items.append(
                ContextItem(
                    kind="character",
                    text=text,
                    source="characters",
                    priority=4,
                    trusted=True,
                )
            )
        # Previous chapter character status from state card
        genesis_cutoff = self._latest_approved_genesis_at(project_id)
        if chapter_number > 1:
            prev_state = self.repo.get_chapter_state(project_id, chapter_number - 1)
            if prev_state and genesis_cutoff and str(prev_state.get("created_at") or "") <= genesis_cutoff:
                prev_state = None
            if prev_state:
                state_data = prev_state.get("state_data")
                if isinstance(state_data, str):
                    try:
                        state_data = json.loads(state_data)
                    except Exception:
                        state_data = {}
                if isinstance(state_data, dict):
                    char_status = state_data.get("character_status")
                    if isinstance(char_status, dict):
                        for name, status in char_status.items():
                            items.append(
                                ContextItem(
                                    kind="character_state",
                                    text=f"- {name}: {status}",
                                    source="prev_state_card:character_status",
                                    chapter_number=chapter_number - 1,
                                    priority=2,
                                    trusted=True,
                                )
                            )
        return items

    def _revision_feedback_context(
        self, project_id: str, chapter_number: int, state: dict[str, Any] | None = None
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        from .revision_context import normalize_revision_review, revision_feedback_block

        review = None
        if state:
            review = state.get("_revision_review")
        if not review:
            chapter = self.repo.get_chapter(project_id, chapter_number)
            if chapter:
                try:
                    review = self.repo.get_latest_review(project_id, chapter.get("id"))
                except Exception:
                    review = None
        normalized = normalize_revision_review(review)
        if normalized:
            issues = normalized.get("issues") or []
            suggestions = normalized.get("suggestions") or []
            text_parts = []
            score = normalized.get("score")
            target = normalized.get("revision_target") or "unknown"
            if score is not None:
                text_parts.append(f"审核评分: {score}; 退回目标: {target}")
            if issues:
                text_parts.append("退回问题:\n" + "\n".join(f"- {i}" for i in issues))
            if suggestions:
                text_parts.append("修改建议:\n" + "\n".join(f"- {s}" for s in suggestions))
            if text_parts:
                items.append(
                    ContextItem(
                        kind="revision_feedback",
                        text="\n\n".join(text_parts),
                        source=f"review:{normalized.get('review_id')}",
                        priority=1,
                        trusted=True,
                    )
                )
        return items

    def _scene_beats_context(self, project_id: str, chapter_number: int) -> list[ContextItem]:
        items: list[ContextItem] = []
        beats = self.repo.get_scene_beats(project_id, chapter_number)
        if beats:
            lines = []
            for b in beats:
                line = (
                    f"  {b.get('sequence')}. 目标: {b.get('scene_goal', '')} | "
                    f"冲突: {b.get('conflict', '')} | 转折: {b.get('turn', '')} | 钩子: {b.get('hook', '')}"
                )
                # v6.10.9: inject reward beat marker
                if b.get("is_reward_beat"):
                    line += " | 【核心爽点 beat】"
                # v6.10.9: inject character states (defensive: may be JSON string)
                char_states = b.get("character_states", {})
                if isinstance(char_states, str):
                    try:
                        char_states = json.loads(char_states)
                    except Exception:
                        char_states = {}
                if char_states and isinstance(char_states, dict):
                    states_str = ", ".join(f"{k}:{v}" for k, v in char_states.items())
                    line += f" | 角色状态: {states_str}"
                lines.append(line)
                # v6.10.9: inject dialogue slots (defensive: may be JSON string)
                dialogue_slots = b.get("dialogue_slots", [])
                if isinstance(dialogue_slots, str):
                    try:
                        dialogue_slots = json.loads(dialogue_slots)
                    except Exception:
                        dialogue_slots = []
                if dialogue_slots and isinstance(dialogue_slots, list):
                    for idx, slot in enumerate(dialogue_slots, 1):
                        if not isinstance(slot, dict):
                            continue
                        speakers = slot.get("speakers", [])
                        conflict_type = slot.get("conflict_type", "")
                        must_convey = slot.get("must_convey", "")
                        slot_line = f"    对白槽位{idx}: {'↔'.join(speakers)}"
                        if conflict_type:
                            slot_line += f" | 冲突: {conflict_type}"
                        if must_convey:
                            slot_line += f" | 传达: {must_convey}"
                        lines.append(slot_line)
            items.append(
                ContextItem(
                    kind="scene_beats",
                    text="【场景 Beat】\n" + "\n".join(lines),
                    source="scene_beats",
                    priority=2,
                    trusted=True,
                )
            )
        return items

    def _core_loop_context(self, project_id: str, chapter_number: int) -> list[ContextItem]:
        """v6.10.9: Inject core_loop design and fact_locks from chapter_brief."""
        items: list[ContextItem] = []
        try:
            instruction = self.repo.get_instruction(project_id, chapter_number)
            if not instruction:
                return items
            # chapter_brief may be nested or flat depending on storage
            brief = instruction.get("chapter_brief") or instruction
            core_loop = brief.get("core_loop", {})
            fact_locks = brief.get("fact_locks", [])
            dialogue_ratio = brief.get("dialogue_target_ratio", 0.15)
            lines = []
            if core_loop:
                lines.append("【核心循环设计】")
                lines.append(f"  爽点事件序号: {core_loop.get('reward_event_index', '?')}")
                lines.append(f"  爽点类型: {core_loop.get('reward_type', '?')}")
                ev = core_loop.get("reward_evidence", "")
                if ev:
                    lines.append(f"  爽点证据: {ev}")
                pd = core_loop.get("protagonist_decision", "")
                if pd:
                    lines.append(f"  主角决策: {pd}")
            if fact_locks:
                lines.append("【事实锁 — 角色物理状态】")
                for fl in fact_locks:
                    lines.append(f"  - {fl}")
            if lines:
                lines.append(f"  目标对白占比: {dialogue_ratio * 100:.0f}%")
                items.append(
                    ContextItem(
                        kind="core_loop",
                        text="\n".join(lines),
                        source="chapter_brief",
                        priority=2,
                        trusted=True,
                    )
                )
        except Exception:
            pass
        return items

    def _pending_plots_context(self, project_id: str) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            plots = self.repo.get_pending_plots(project_id)
        except Exception:
            plots = []
        for p in plots:
            text = (
                f"- [{p.get('code')}] {p.get('title')} "
                f"(埋设:第{p.get('planted_chapter','?')}章, 计划兑现:第{p.get('planned_resolve_chapter','?')}章)"
            )
            items.append(
                ContextItem(
                    kind="pending_plot",
                    text=text,
                    source="plot_holes",
                    priority=3,
                    trusted=True,
                )
            )
        return items

    def _continuity_warnings_context(
        self, project_id: str, chapter_number: int
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            reports = self.repo.get_continuity_reports(project_id, limit=3)
        except Exception:
            reports = []
        if not reports:
            return items
        relevant = [
            r
            for r in reports
            if r.get("from_chapter", 0) <= chapter_number <= r.get("to_chapter", 999)
        ]
        issues: list[str] = []
        for report in relevant:
            content = report.get("content_json", {})
            report_issues = content.get("issues", [])
            for issue in report_issues[:5]:
                if isinstance(issue, dict) and issue.get("severity") in ("error", "warning"):
                    issues.append(f"- [{issue.get('severity')}] {issue.get('description', '')[:100]}")
        if issues:
            items.append(
                ContextItem(
                    kind="continuity_warning",
                    text="【连续性警告】\n" + "\n".join(issues),
                    source="continuity_checker",
                    priority=2,
                    trusted=True,
                )
            )
        return items

    def _inject_recall_extras(
        self,
        project_id: str,
        chapter_number: int,
        bundle: AgentContextBundle,
        brief: dict[str, Any] | None,
    ) -> None:
        """v6.10.14 S4+S5: Inject aging warnings and pull-recall into advisory_context.

        Mutates ``bundle.advisory_context`` in place by appending:
        - Aging warnings for stale numeric_state facts and overdue plots (S4)
        - Proactively pulled entity fact chains (S5)
        """
        # S4: Aging warnings
        try:
            all_facts = self.repo.list_story_facts(project_id, status="active")
        except Exception:
            all_facts = []
        try:
            pending_plots = self.repo.get_pending_plots(project_id)
        except Exception:
            pending_plots = []

        aging_items = build_aging_warnings(all_facts, pending_plots, chapter_number)
        if aging_items:
            bundle.advisory_context.extend(aging_items)

        # S5: Pull recall — proactively retrieve entity fact chains
        pull_items = build_pull_context(all_facts, brief, chapter_number)
        if pull_items:
            bundle.advisory_context.extend(pull_items)

    def _world_rules_context(self, project_id: str) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            settings = self.repo.get_world_settings(project_id)
        except Exception:
            settings = []
        if settings:
            lines = [
                f"- [{s.get('category', '')}] {s.get('title', '')}: {str(s.get('content', ''))[:200]}"
                for s in settings[:5]
            ]
            items.append(
                ContextItem(
                    kind="world_rules",
                    text="【世界观关键规则】\n" + "\n".join(lines),
                    source="world_settings",
                    priority=5,
                    trusted=True,
                )
            )
        return items

    def _style_bible_context(self, project_id: str, agent_id: str) -> list[ContextItem]:
        """Load Style Bible and generate agent-specific style context."""
        items: list[ContextItem] = []
        try:
            from ..style_bible.loader import load_style_bible_for_project

            bible = load_style_bible_for_project(project_id, self.repo)
        except Exception:
            bible = None
        if not bible:
            return items

        try:
            rules_text = bible.rules_for_agent(agent_id)
        except Exception:
            rules_text = ""
        if rules_text:
            items.append(
                ContextItem(
                    kind="style_bible",
                    text=rules_text,
                    source="style_bible",
                    priority=3,
                    trusted=True,
                )
            )
        return items

    def _load_story_contract(self, project_id: str) -> "StoryContract | None":
        """Load StoryContract from DB or derive fallback."""
        try:
            from ..models.creative_contracts import StoryContract
            from ..quality.core_loop_checker import derive_fallback_story_contract

            # Try to load from project_creative_contracts
            row = self.repo.get_creative_contract(project_id, "story_contract")
            if row:
                data_str = row.get("contract_data", "{}")
                if isinstance(data_str, str):
                    data = json.loads(data_str)
                else:
                    data = data_str
                if isinstance(data, dict) and data.get("core_promise"):
                    return StoryContract(**data)

            # Fallback: derive from launch_profile + genre_contract
            lp_row = self.repo.get_creative_contract(project_id, "launch_profile")
            gc_row = self.repo.get_creative_contract(project_id, "genre_contract")
            lp_data = None
            gc_data = None
            if lp_row:
                lp_str = lp_row.get("contract_data", "{}")
                lp_data = json.loads(lp_str) if isinstance(lp_str, str) else lp_str
            if gc_row:
                gc_str = gc_row.get("contract_data", "{}")
                gc_data = json.loads(gc_str) if isinstance(gc_str, str) else gc_str

            if lp_data or gc_data:
                return derive_fallback_story_contract(
                    project_id, lp_data, gc_data
                )
        except Exception as e:
            logger.debug("Failed to load story contract for %s: %s", project_id, e)
        return None

    def _story_contract_context(
        self, project_id: str, agent_id: str, chapter_number: int = 0
    ) -> list[ContextItem]:
        """v6.10.5: Build Story Contract context for agents.

        Each agent receives a tailored view:
        - Planner: core promise, core loop, drift rules, recent trend
        - Screenwriter: core_loop_target, scene beat mapping
        - Author: what to deliver, evidence plan, allowed mechanisms
        - Editor: contract checklist, compliance check guidance
        """
        items: list[ContextItem] = []
        contract = self._load_story_contract(project_id)
        if not contract:
            return items

        status_note = ""
        if contract.status in ("draft", "needs_review", "fallback"):
            status_note = f"\n[注意] 当前合同状态为 '{contract.status}'，仅供参考，不作硬阻断。"

        if agent_id == "planner":
            text = self._format_contract_for_planner(contract, status_note)
        elif agent_id == "screenwriter":
            text = self._format_contract_for_screenwriter(contract, status_note)
        elif agent_id == "author":
            text = self._format_contract_for_author(contract, status_note)
        elif agent_id == "editor":
            text = self._format_contract_for_editor(contract, status_note)
        else:
            text = self._format_contract_generic(contract, status_note)

        if text:
            items.append(ContextItem(
                kind="story_contract",
                text=text,
                source="story_contract",
                priority=2,
                trusted=True,
            ))

        # Recent contract trend for planner/editor
        if agent_id in ("planner", "editor") and chapter_number > 1:
            trend_text = self._recent_contract_trend(project_id, chapter_number)
            if trend_text:
                items.append(ContextItem(
                    kind="contract_trend",
                    text=trend_text,
                    source="contract_metrics",
                    priority=3,
                    trusted=True,
                ))

        return items

    def _format_contract_for_planner(self, contract: Any, status_note: str) -> str:
        lines = ["【Story Contract — Planner 指引】"]
        lines.append(f"核心承诺: {contract.core_promise}")
        if contract.core_loop:
            loop_steps = " → ".join(
                f"{s.label}({s.id})" for s in contract.core_loop
            )
            lines.append(f"核心循环: {loop_steps}")
        if contract.drift_rules:
            lines.append("漂移规则:")
            for r in contract.drift_rules:
                lines.append(f"  - {r.description} (severity={r.severity}, window={r.window_chapters}章)")
        if contract.cadence:
            lines.append(f"回报节奏: {json.dumps(contract.cadence, ensure_ascii=False)}")
        if status_note:
            lines.append(status_note)
        lines.append("生成 ChapterBrief 时必须声明 core_loop_target 和 primary_payoff。")
        return "\n".join(lines)

    def _format_contract_for_screenwriter(self, contract: Any, status_note: str) -> str:
        lines = ["【Story Contract — Screenwriter 指引】"]
        if contract.core_loop:
            lines.append("核心循环步骤（scene beat 必须映射）:")
            for s in contract.core_loop:
                req = "必需" if s.required else "可选"
                lines.append(f"  - [{s.id}] {s.label} ({req})")
        lines.append("每个 scene beat 必须说明服务哪个 core_loop_step。")
        lines.append("禁止把辅助机制写成 scene 唯一主线。")
        if contract.supporting_mechanisms:
            mech_labels = [m.label for m in contract.supporting_mechanisms]
            lines.append(f"辅助机制: {', '.join(mech_labels)}")
        if status_note:
            lines.append(status_note)
        return "\n".join(lines)

    def _format_contract_for_author(self, contract: Any, status_note: str) -> str:
        lines = ["【Story Contract — Author 指引】"]
        lines.append(f"核心承诺: {contract.core_promise}")
        lines.append("本章写作要求:")
        lines.append("  1. 必须完成核心兑现（参考 ChapterBrief.core_loop_target）")
        lines.append("  2. 兑现证据必须在正文可见场景中写出")
        lines.append("  3. 辅助机制必须服务于核心循环，不能喧宾夺主")
        if contract.supporting_mechanisms:
            mech_labels = [m.label for m in contract.supporting_mechanisms]
            lines.append(f"允许的辅助机制: {', '.join(mech_labels)}")
        if status_note:
            lines.append(status_note)
        return "\n".join(lines)

    def _format_contract_for_editor(self, contract: Any, status_note: str) -> str:
        lines = ["【Story Contract — Editor 审核指引】"]
        lines.append("审核清单:")
        lines.append("  1. 本章是否完成核心兑现？(core_payoff_present)")
        lines.append("  2. 辅助机制是否喧宾夺主？(supporting_mechanism_dominance)")
        lines.append("  3. 是否新增机制过载？(new_mechanism_count)")
        lines.append("  4. 主角是否展现主动性？(protagonist_agency)")
        if contract.drift_rules:
            lines.append("漂移规则:")
            for r in contract.drift_rules:
                lines.append(f"  - {r.description}")
        if status_note:
            lines.append(status_note)
        return "\n".join(lines)

    def _format_contract_generic(self, contract: Any, status_note: str) -> str:
        lines = ["【Story Contract】"]
        lines.append(f"核心承诺: {contract.core_promise}")
        if contract.core_loop:
            loop_steps = " → ".join(s.label for s in contract.core_loop)
            lines.append(f"核心循环: {loop_steps}")
        if status_note:
            lines.append(status_note)
        return "\n".join(lines)

    def _recent_contract_trend(self, project_id: str, chapter_number: int) -> str:
        """Load recent contract metrics and summarize trend."""
        try:
            from ..models.creative_ledgers import ChapterContractMetrics
            # Try to get from creative ledger metadata
            metrics_raw = self.repo.get_chapter_contract_metrics(project_id, limit=3)
            if not metrics_raw:
                return ""
            metrics = []
            for m in metrics_raw:
                if isinstance(m, dict):
                    metrics.append(ChapterContractMetrics(**m))

            if not metrics:
                return ""

            lines = ["【最近合同合规趋势】"]
            for m in metrics:
                payoff_mark = "✓" if m.core_payoff_present else "✗"
                lines.append(
                    f"  第{m.chapter_number}章: 核心兑现={payoff_mark}, "
                    f"得分={m.contract_score:.0f}, "
                    f"主导机制={m.dominant_mechanism or 'core_loop'}"
                )
            # Trend summary
            no_payoff_streak = 0
            for m in reversed(metrics):
                if not m.core_payoff_present:
                    no_payoff_streak += 1
                else:
                    break
            if no_payoff_streak >= 2:
                lines.append(f"⚠ 连续{no_payoff_streak}章未完成核心兑现，下一章必须补回。")
            return "\n".join(lines)
        except Exception:
            return ""

    @staticmethod
    def _apply_memory_degraded_hard_constraint(bundle: AgentContextBundle) -> None:
        """Promote no-trusted-memory guidance into hard constraints."""
        if not bundle.memory_context_degraded:
            return
        if any(it.kind == "memory_degraded_warning" for it in bundle.hard_constraints):
            return
        bundle.hard_constraints.insert(
            0,
            ContextItem(
                kind="memory_degraded_warning",
                text=(
                    "当前章节暂无可信记忆批次，必须严格以 story_facts 中已确认 "
                    "(confirmed=True) 的事实和硬约束为准；禁止脑补未在项目资料中"
                    "出现的人物状态、剧情发展或世界设定细节。"
                ),
                source="context_builder",
                priority=0,
                trusted=True,
            ),
        )

    # ── Per-agent build methods ──────────────────────────────────

    def build_for_planner(
        self, project_id: str, chapter_number: int, state: dict[str, Any] | None = None
    ) -> AgentContextBundle:
        bundle = AgentContextBundle()
        brief = self._load_brief(project_id, chapter_number)
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number, brief)
        bundle.plot_obligations = self._pending_plots_context(project_id)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.numeric_state_constraints = extract_numeric_state_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.style_context = self._style_bible_context(project_id, "planner")
        bundle.story_contract_context = self._story_contract_context(project_id, "planner", chapter_number)

        # Hard constraints for planner: suspense hooks + timeline + revision
        hard: list[ContextItem] = []
        for it in bundle.chapter_inheritance:
            if it.kind == "suspense_hook":
                hard.append(it)
        hard.extend(bundle.timeline_constraints)
        hard.extend(bundle.numeric_state_constraints)
        hard.extend(bundle.revision_feedback)
        bundle.hard_constraints = hard
        self._apply_memory_degraded_hard_constraint(bundle)

        # Advisory: low-confidence memory + world rules
        bundle.advisory_context = self._advisory_memory_context(project_id, chapter_number)
        bundle.advisory_context.extend(self._world_rules_context(project_id))

        return bundle

    def build_for_screenwriter(
        self, project_id: str, chapter_number: int, state: dict[str, Any] | None = None
    ) -> AgentContextBundle:
        bundle = AgentContextBundle()
        brief = self._load_brief(project_id, chapter_number)
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number, brief)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.numeric_state_constraints = extract_numeric_state_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.style_context = self._style_bible_context(project_id, "screenwriter")
        bundle.story_contract_context = self._story_contract_context(project_id, "screenwriter", chapter_number)

        bundle.hard_constraints = (
            [it for it in bundle.chapter_inheritance if it.kind == "suspense_hook"]
            + bundle.timeline_constraints
            + bundle.numeric_state_constraints
            + bundle.revision_feedback
        )
        self._apply_memory_degraded_hard_constraint(bundle)
        bundle.advisory_context = self._advisory_memory_context(project_id, chapter_number)
        bundle.advisory_context.extend(self._world_rules_context(project_id))
        bundle.advisory_context.extend(self._continuity_warnings_context(project_id, chapter_number))
        return bundle

    def build_for_author(
        self, project_id: str, chapter_number: int, state: dict[str, Any] | None = None
    ) -> AgentContextBundle:
        bundle = AgentContextBundle()
        brief = self._load_brief(project_id, chapter_number)
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number, brief)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.numeric_state_constraints = extract_numeric_state_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.style_context = self._style_bible_context(project_id, "author")
        bundle.story_contract_context = self._story_contract_context(project_id, "author", chapter_number)

        bundle.hard_constraints = (
            [it for it in bundle.chapter_inheritance if it.kind == "suspense_hook"]
            + bundle.timeline_constraints
            + bundle.numeric_state_constraints
            + bundle.revision_feedback
        )
        self._apply_memory_degraded_hard_constraint(bundle)
        bundle.advisory_context = self._advisory_memory_context(project_id, chapter_number)
        bundle.advisory_context.extend(self._world_rules_context(project_id))
        bundle.advisory_context.extend(self._continuity_warnings_context(project_id, chapter_number))
        # v6.10.14 S4+S5: Inject aging warnings and pull-recall for Author
        self._inject_recall_extras(project_id, chapter_number, bundle, brief)
        return bundle

    def build_for_polisher(
        self, project_id: str, chapter_number: int, state: dict[str, Any] | None = None
    ) -> AgentContextBundle:
        bundle = AgentContextBundle()
        brief = self._load_brief(project_id, chapter_number)
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number, brief)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.numeric_state_constraints = extract_numeric_state_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.style_context = self._style_bible_context(project_id, "polisher")
        bundle.story_contract_context = self._story_contract_context(project_id, "polisher", chapter_number)

        # Polisher hard constraints: fact lock items (instruction events + plots)
        hard: list[ContextItem] = []
        for it in bundle.plot_obligations:
            if it.kind == "plot_obligation":
                hard.append(it)
        hard.extend(bundle.numeric_state_constraints)
        hard.extend(bundle.revision_feedback)
        bundle.hard_constraints = hard
        self._apply_memory_degraded_hard_constraint(bundle)
        bundle.advisory_context = self._advisory_memory_context(project_id, chapter_number)
        bundle.advisory_context.extend(self._world_rules_context(project_id))
        return bundle

    def build_for_editor(
        self, project_id: str, chapter_number: int, state: dict[str, Any] | None = None
    ) -> AgentContextBundle:
        bundle = AgentContextBundle()
        brief = self._load_brief(project_id, chapter_number)
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number, brief)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.numeric_state_constraints = extract_numeric_state_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.style_context = self._style_bible_context(project_id, "editor")
        bundle.story_contract_context = self._story_contract_context(project_id, "editor", chapter_number)

        # v6.10.9: Inject scene_beats so Editor can determine beat-design vs author-execution
        bundle.scene_beats = self._scene_beats_context(project_id, chapter_number)

        # v6.10.9: Inject core_loop / fact_locks from chapter_brief
        bundle.core_loop_context = self._core_loop_context(project_id, chapter_number)

        bundle.hard_constraints = (
            [it for it in bundle.chapter_inheritance if it.kind == "suspense_hook"]
            + bundle.timeline_constraints
            + bundle.numeric_state_constraints
            + bundle.revision_feedback
        )
        self._apply_memory_degraded_hard_constraint(bundle)
        bundle.advisory_context = self._advisory_memory_context(project_id, chapter_number)
        bundle.advisory_context.extend(self._world_rules_context(project_id))
        bundle.advisory_context.extend(self._continuity_warnings_context(project_id, chapter_number))
        # v6.10.14 S4+S5: Inject aging warnings and pull-recall for Editor
        self._inject_recall_extras(project_id, chapter_number, bundle, brief)
        return bundle


# ── Formatting ───────────────────────────────────────────────────

def compute_adaptive_budget(
    total_chapters: int,
    base_budget: int = _MAX_CONTEXT_CHARS,
) -> int:
    """v6.10.14 S7: Return an adaptive context budget based on chapter count.

    For long-form projects (``total_chapters`` > threshold), the budget is
    raised so more facts can fit without triggering truncation.  Callers
    should pass the result as the ``max_chars`` argument to
    :func:`format_context_bundle_for_prompt`.
    """
    if total_chapters > _ADAPTIVE_BUDGET_CHAPTER_THRESHOLD:
        return _ADAPTIVE_BUDGET_LONGFORM_CHARS
    return base_budget


def format_context_bundle_for_prompt(
    bundle: AgentContextBundle,
    agent_name: str,
    max_chars: int = _MAX_CONTEXT_CHARS,
) -> str:
    """Format a bundle into a single prompt string with priority-based truncation.

    Priority order (matches ``ordered_buckets`` below):
    1. hard_constraints
    2. revision_feedback
    3. timeline_constraints
    4. story_facts
    5. numeric_state_constraints
    6. plot_obligations
    7. trusted_memory
    8. character_states
    9. story_contract_context
    10. core_loop_context
    11. scene_beats
    12. style_context
    13. advisory_context
    14. chapter_inheritance
    15. project_context

    v6.10.14: Buckets in :data:`_MANDATORY_BUCKETS` are never dropped — even
    when the total exceeds ``max_chars`` they are force-included so that
    critical constraints (hard / numeric_state / timeline) survive budget
    pressure.  Non-mandatory buckets that overflow are truncated in place and
    the loop *continues* (instead of ``break``) so subsequent mandatory
    buckets are still processed.
    """
    ordered_buckets: list[tuple[str, list[ContextItem]]] = [
        ("【不可违背事实 / Hard Constraints】", bundle.hard_constraints),
        ("【返修反馈 / Revision Feedback】", bundle.revision_feedback),
        ("【时间线约束 / Timeline Constraints】", bundle.timeline_constraints),
        ("【事实账本 / Story Facts】", bundle.story_facts),
        ("【数值状态约束 / Numeric State Constraints】", bundle.numeric_state_constraints),
        ("【伏笔债务 / Plot Obligations】", bundle.plot_obligations),
        ("【可信记忆 / Trusted Memory】", bundle.trusted_memory),
        ("【角色状态 / Character States】", bundle.character_states),
        ("【故事合同 / Story Contract】", bundle.story_contract_context),
        ("【核心循环与事实锁 / Core Loop & Fact Locks】", bundle.core_loop_context),
        ("【场景 Beat / Scene Beats】", bundle.scene_beats),
        ("【风格规范 / Style Bible】", bundle.style_context),
        ("【建议参考 / Advisory Context】", bundle.advisory_context),
        ("【章节继承 / Chapter Inheritance】", bundle.chapter_inheritance),
        ("【项目背景 / Project Context】", bundle.project_context),
    ]

    # v6.10.14: Machine-friendly keys aligned 1:1 with ordered_buckets by index
    bucket_keys: list[str] = [
        "hard_constraints",
        "revision_feedback",
        "timeline_constraints",
        "story_facts",
        "numeric_state_constraints",
        "plot_obligations",
        "trusted_memory",
        "character_states",
        "story_contract_context",
        "core_loop_context",
        "scene_beats",
        "style_context",
        "advisory_context",
        "chapter_inheritance",
        "project_context",
    ]

    parts: list[str] = []
    total_len = 0
    truncated = False
    overflow_logged = False

    # v6.6.14: prepend degraded notice when no trusted memory batch is available
    if bundle.memory_context_degraded:
        degraded_notice = (
            "【记忆上下文降级 / Memory Context Degraded】\n"
            "当前章节暂无可信记忆批次。"
            "请严格以 story_facts 中已确认 (confirmed=True) 的事实和硬约束为准，"
            "禁止脑补未在项目资料中出现的人物状态、剧情发展或世界设定细节。"
        )
        parts.append(degraded_notice)
        total_len += len(degraded_notice)

    for idx, (header, items) in enumerate(ordered_buckets):
        if not items:
            continue
        bucket_name = bucket_keys[idx]
        # v6.10.10: Sort items by priority (lower number = higher priority)
        sorted_items = sorted(items, key=lambda it: it.priority)
        block_lines: list[str] = [header]
        for it in sorted_items:
            confidence_tag = f" [置信度:{it.confidence:.2f}]" if it.confidence < 1.0 else ""
            source_tag = f" [来源:{it.source}]" if it.source else ""
            line = f"- {it.text}{confidence_tag}{source_tag}"
            block_lines.append(line)
        block = "\n".join(block_lines)
        block_len = len(block)

        if total_len + block_len > max_chars:
            if bucket_name in _MANDATORY_BUCKETS:
                # v6.10.14 S1: mandatory bucket — force-include even over budget
                parts.append(block)
                total_len += block_len
                if not overflow_logged:
                    logger.warning(
                        "context_budget_overflow: bucket=%s agent=%s "
                        "total_len=%d max_chars=%d (mandatory force-included)",
                        bucket_name, agent_name, total_len, max_chars,
                    )
                    overflow_logged = True
                continue

            # v6.10.14 S3: non-mandatory — truncate in place then *continue*
            # (previously this was a `break`, which skipped later mandatory buckets)
            remaining = max_chars - total_len - len(header) - 50
            if remaining > 100:
                truncated = True
                # Truncate line-by-line to avoid splitting UTF-8 multi-byte chars
                kept: list[str] = [header]
                used = len(header) + 1
                for line in block_lines[1:]:
                    if used + len(line) + 1 > remaining:
                        break
                    kept.append(line)
                    used += len(line) + 1
                kept.append("...(已截断)")
                truncated_block = "\n".join(kept)
                parts.append(truncated_block)
                total_len += len(truncated_block)
            # Do NOT break — continue so mandatory buckets later in the order
            # still get their chance to be force-included.
            continue
        else:
            parts.append(block)
            total_len += block_len

    result = "\n\n".join(parts)
    if truncated:
        result += "\n\n【上下文已截断】部分低优先级资料因长度限制未完全展示。"
    return result


def build_context_summary_for_trace(bundle: AgentContextBundle) -> dict[str, Any]:
    """Return a compact dict for agent decision trace metadata."""
    return {
        "context_categories_included": [
            name
            for name, items in {
                "project_context": bundle.project_context,
                "chapter_inheritance": bundle.chapter_inheritance,
                "trusted_memory": bundle.trusted_memory,
                "story_facts": bundle.story_facts,
                "plot_obligations": bundle.plot_obligations,
                "timeline_constraints": bundle.timeline_constraints,
                "numeric_state_constraints": bundle.numeric_state_constraints,
                "character_states": bundle.character_states,
                "revision_feedback": bundle.revision_feedback,
                "hard_constraints": bundle.hard_constraints,
                "advisory_context": bundle.advisory_context,
                "style_context": bundle.style_context,
                "scene_beats": bundle.scene_beats,
                "core_loop_context": bundle.core_loop_context,
            }.items()
            if items
        ],
        **bundle.to_dict(),
        "context_truncated": None,  # set by formatter if known
    }
