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

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────

_TRUSTED_MEMORY_MIN_CONFIDENCE = 0.75
_UNTRUSTED_MEMORY_MAX_CONFIDENCE = 0.45
_MAX_CONTEXT_CHARS = 14000

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
    character_states: list[ContextItem] = field(default_factory=list)
    revision_feedback: list[ContextItem] = field(default_factory=list)
    hard_constraints: list[ContextItem] = field(default_factory=list)
    advisory_context: list[ContextItem] = field(default_factory=list)
    diagnostics: list[ContextItem] = field(default_factory=list)
    # v6.6.14: memory context annotation
    memory_context_degraded: bool = False
    trusted_memory_batch_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for trace / artifact metadata (no API keys)."""
        return {
            "trusted_memory_count": len(self.trusted_memory),
            "timeline_constraints_count": len(self.timeline_constraints),
            "plot_obligations_count": len(self.plot_obligations),
            "hard_constraints_count": len(self.hard_constraints),
            "advisory_count": len(self.advisory_context),
            "revision_feedback_count": len(self.revision_feedback),
            "story_facts_count": len(self.story_facts),
            "character_states_count": len(self.character_states),
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

    # Deduplicate by text
    seen: set[str] = set()
    deduped: list[ContextItem] = []
    for it in items:
        key = it.text.strip()[:120]
        if key and key not in seen:
            seen.add(key)
            deduped.append(it)
    return deduped


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

    def _story_facts_context(self, project_id: str, chapter_number: int) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            facts = self.repo.list_story_facts(project_id, status="active")
        except Exception:
            facts = []
        for fact in facts:
            src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
            if src_ch > chapter_number:
                continue
            subject = fact.get("subject", "")
            attribute = fact.get("attribute", "")
            value = str(fact.get("value_json") or "")
            if len(value) > 120:
                value = value[:120] + "..."
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
                lines.append(
                    f"  {b.get('sequence')}. 目标: {b.get('scene_goal', '')} | "
                    f"冲突: {b.get('conflict', '')} | 转折: {b.get('turn', '')} | 钩子: {b.get('hook', '')}"
                )
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
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number)
        bundle.plot_obligations = self._pending_plots_context(project_id)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )

        # Hard constraints for planner: suspense hooks + timeline + revision
        hard: list[ContextItem] = []
        for it in bundle.chapter_inheritance:
            if it.kind == "suspense_hook":
                hard.append(it)
        hard.extend(bundle.timeline_constraints)
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
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.hard_constraints = (
            [it for it in bundle.chapter_inheritance if it.kind == "suspense_hook"]
            + bundle.timeline_constraints
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
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.hard_constraints = (
            [it for it in bundle.chapter_inheritance if it.kind == "suspense_hook"]
            + bundle.timeline_constraints
            + bundle.revision_feedback
        )
        self._apply_memory_degraded_hard_constraint(bundle)
        bundle.advisory_context = self._advisory_memory_context(project_id, chapter_number)
        bundle.advisory_context.extend(self._world_rules_context(project_id))
        bundle.advisory_context.extend(self._continuity_warnings_context(project_id, chapter_number))
        return bundle

    def build_for_polisher(
        self, project_id: str, chapter_number: int, state: dict[str, Any] | None = None
    ) -> AgentContextBundle:
        bundle = AgentContextBundle()
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        # Polisher hard constraints: fact lock items (instruction events + plots)
        hard: list[ContextItem] = []
        for it in bundle.plot_obligations:
            if it.kind == "plot_obligation":
                hard.append(it)
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
        bundle.project_context = self._project_context(project_id)
        bundle.chapter_inheritance = self._previous_chapter_context(project_id, chapter_number)
        bundle.trusted_memory = self._trusted_memory_context(project_id, chapter_number, bundle)
        bundle.story_facts = self._story_facts_context(project_id, chapter_number)
        bundle.plot_obligations = self._instruction_context(project_id, chapter_number)
        bundle.timeline_constraints = extract_timeline_constraints(
            project_id, chapter_number, self.repo
        )
        bundle.character_states = self._character_states_context(project_id, chapter_number)
        bundle.revision_feedback = self._revision_feedback_context(
            project_id, chapter_number, state
        )
        bundle.hard_constraints = (
            [it for it in bundle.chapter_inheritance if it.kind == "suspense_hook"]
            + bundle.timeline_constraints
            + bundle.revision_feedback
        )
        self._apply_memory_degraded_hard_constraint(bundle)
        bundle.advisory_context = self._advisory_memory_context(project_id, chapter_number)
        bundle.advisory_context.extend(self._world_rules_context(project_id))
        bundle.advisory_context.extend(self._continuity_warnings_context(project_id, chapter_number))
        return bundle


# ── Formatting ───────────────────────────────────────────────────

def format_context_bundle_for_prompt(
    bundle: AgentContextBundle,
    agent_name: str,
    max_chars: int = _MAX_CONTEXT_CHARS,
) -> str:
    """Format a bundle into a single prompt string with priority-based truncation.

    Priority order:
    1. hard_constraints
    2. revision_feedback
    3. timeline_constraints
    4. plot_obligations
    5. trusted_memory
    6. story_facts
    7. character_states
    8. advisory_context
    9. chapter_inheritance (state cards, tails — lower priority for some agents)
    10. project_context
    """
    ordered_buckets: list[tuple[str, list[ContextItem]]] = [
        ("【不可违背事实 / Hard Constraints】", bundle.hard_constraints),
        ("【返修反馈 / Revision Feedback】", bundle.revision_feedback),
        ("【时间线约束 / Timeline Constraints】", bundle.timeline_constraints),
        ("【伏笔债务 / Plot Obligations】", bundle.plot_obligations),
        ("【可信记忆 / Trusted Memory】", bundle.trusted_memory),
        ("【事实账本 / Story Facts】", bundle.story_facts),
        ("【角色状态 / Character States】", bundle.character_states),
        ("【建议参考 / Advisory Context】", bundle.advisory_context),
        ("【章节继承 / Chapter Inheritance】", bundle.chapter_inheritance),
        ("【项目背景 / Project Context】", bundle.project_context),
    ]

    parts: list[str] = []
    total_len = 0
    truncated = False

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

    for header, items in ordered_buckets:
        if not items:
            continue
        block_lines: list[str] = [header]
        for it in items:
            confidence_tag = f" [置信度:{it.confidence:.2f}]" if it.confidence < 1.0 else ""
            source_tag = f" [来源:{it.source}]" if it.source else ""
            line = f"- {it.text}{confidence_tag}{source_tag}"
            block_lines.append(line)
        block = "\n".join(block_lines)
        block_len = len(block)
        if total_len + block_len > max_chars:
            # Try to include a truncated version
            remaining = max_chars - total_len - len(header) - 50
            if remaining > 100:
                truncated = True
                truncated_block = header + "\n" + block[len(header) + 1 : len(header) + 1 + remaining] + "\n...(已截断)"
                parts.append(truncated_block)
                total_len += len(truncated_block)
            break
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
                "character_states": bundle.character_states,
                "revision_feedback": bundle.revision_feedback,
                "hard_constraints": bundle.hard_constraints,
                "advisory_context": bundle.advisory_context,
            }.items()
            if items
        ],
        **bundle.to_dict(),
        "context_truncated": None,  # set by formatter if known
    }
