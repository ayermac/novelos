"""v6.10.14 S4: Aging detector for long-form story facts and plot holes.

Detects facts/plots that have not been updated for too many chapters and
produces :class:`~novel_factory.agent_runtime.context_builder.ContextItem`
warnings so the Writer is forced to see them.

Design principles:
- Pure code derivation (no LLM dependency).
- Numeric-state facts: warn after ``NUMERIC_STATE_AGING_THRESHOLD`` chapters.
- Plot holes (foreshadowing): warn after ``PLOT_AGING_THRESHOLD`` chapters,
  or when ``planned_resolve_chapter`` has passed without resolution.
- Maximum ``MAX_AGING_WARNINGS`` items, sorted by "most stale first".
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent_runtime.context_builder import ContextItem

# Thresholds (in chapters)
NUMERIC_STATE_AGING_THRESHOLD = 15
PLOT_AGING_THRESHOLD = 20
MAX_AGING_WARNINGS = 5


def detect_aging_facts(
    facts: list[dict[str, Any]],
    current_chapter: int,
    *,
    threshold: int = NUMERIC_STATE_AGING_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return numeric_state facts that haven't been updated for ``threshold`` chapters.

    Each returned dict is the original fact dict augmented with an ``_age``
    field for downstream formatting.
    """
    aged: list[dict[str, Any]] = []
    for fact in facts:
        fact_type = str(fact.get("fact_type") or "").lower()
        if fact_type != "numeric_state":
            continue
        src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
        age = current_chapter - src_ch
        if age >= threshold:
            enriched = dict(fact)
            enriched["_age"] = age
            aged.append(enriched)
    # Sort by most stale first
    aged.sort(key=lambda f: f["_age"], reverse=True)
    return aged


def detect_aging_plots(
    plots: list[dict[str, Any]],
    current_chapter: int,
    *,
    threshold: int = PLOT_AGING_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return pending plot holes that are aged or overdue.

    A plot hole is "aged" when:
    - It has no ``planned_resolve_chapter`` and has been pending for
      ``threshold`` chapters since planting.
    - OR its ``planned_resolve_chapter`` has passed but status is still
      ``pending`` / ``planted``.
    """
    aged: list[dict[str, Any]] = []
    for plot in plots:
        status = str(plot.get("status") or "").lower()
        if status in ("resolved", "cancelled", "ignored"):
            continue
        planted_ch = int(plot.get("planted_chapter") or 0)
        planned_resolve = plot.get("planned_resolve_chapter")
        age = current_chapter - planted_ch

        is_overdue = False
        if planned_resolve is not None:
            try:
                resolve_ch = int(planned_resolve)
                if resolve_ch <= current_chapter:
                    is_overdue = True
            except (TypeError, ValueError):
                pass

        if is_overdue or age >= threshold:
            enriched = dict(plot)
            enriched["_age"] = age
            enriched["_overdue"] = is_overdue
            aged.append(enriched)

    # Overdue first, then by most stale
    aged.sort(key=lambda p: (not p["_overdue"], -p["_age"]))
    return aged


def build_aging_warnings(
    facts: list[dict[str, Any]],
    plots: list[dict[str, Any]],
    current_chapter: int,
) -> list["ContextItem"]:
    """Build ContextItem warnings for aged facts and plots.

    Returns at most :data:`MAX_AGING_WARNINGS` items, prioritising
    overdue plots and most-stale numeric states.
    """
    # Deferred import to avoid circular dependency
    from ..agent_runtime.context_builder import ContextItem

    items: list[ContextItem] = []

    aged_plots = detect_aging_plots(plots, current_chapter)
    for plot in aged_plots[:MAX_AGING_WARNINGS]:
        code = plot.get("code") or plot.get("id") or "?"
        title = plot.get("title") or ""
        age = plot.get("_age", 0)
        overdue = plot.get("_overdue", False)
        planted = plot.get("planted_chapter", "?")
        planned = plot.get("planned_resolve_chapter", "未定")
        tag = "已逾期未兑现" if overdue else f"已挂起{age}章"
        text = (
            f"[{code}] {title}（埋设于第{planted}章，计划兑现：{planned}）— {tag}，"
            f"请评估是否在本章推进或兑现。"
        )
        items.append(
            ContextItem(
                kind="aging_warning",
                text=text,
                source=f"aging:plot:{code}",
                confidence=1.0,
                chapter_number=planted,
                priority=2,
                trusted=True,
            )
        )

    remaining = MAX_AGING_WARNINGS - len(items)
    if remaining > 0:
        aged_facts = detect_aging_facts(facts, current_chapter)
        for fact in aged_facts[:remaining]:
            subject = fact.get("subject") or fact.get("attribute") or "数值状态"
            age = fact.get("_age", 0)
            src_ch = fact.get("source_chapter") or fact.get("last_changed_chapter") or "?"
            text = (
                f"{subject}（第{src_ch}章确认，已{age}章未更新）— "
                f"请确认该数值状态是否仍有效，如已变化须在本章明确写出。"
            )
            items.append(
                ContextItem(
                    kind="aging_warning",
                    text=text,
                    source=f"aging:fact:{fact.get('fact_key', '')}",
                    confidence=1.0,
                    chapter_number=int(src_ch) if isinstance(src_ch, (int, float)) else 0,
                    priority=3,
                    trusted=True,
                )
            )

    return items
