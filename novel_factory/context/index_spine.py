"""v6.10.15 S10: Index spine — lightweight fact directory for megafiction.

For projects with 1000+ chapters, loading full fact payloads into context
is infeasible.  The index spine provides a compact directory of all active
facts (fact_key / fact_type / subject / source_chapter only, ~15 chars/row)
so agents know "what lines exist" and can pull details on demand.

Design:
- Pure code, no LLM dependency.
- Index rows are deduplicated by subject.attribute (keeping latest source_chapter).
- Compact formatting: one line per fact, grouped by fact_type.
- Hard cap of MAX_INDEX_ROWS to stay within budget even at extreme scale.
- Intended for injection into advisory_context.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent_runtime.context_builder import ContextItem

MAX_INDEX_ROWS = 200
MAX_INDEX_CHARS = 4000

# Fact types that are always shown in full elsewhere; exclude from index to
# avoid redundancy with numeric_state_constraints and timeline_constraints buckets.
_INDEX_EXCLUDED_TYPES = frozenset({"numeric_state"})


def build_index_spine(
    facts: list[dict[str, Any]],
    current_chapter: int,
) -> list["ContextItem"]:
    """Build a compact index spine ContextItem from a list of facts.

    Expects raw facts (full dicts) or index rows (fact_key/type/subject/
    attribute/source_chapter only).  Produces at most one ContextItem
    containing the formatted directory.
    """
    # Deduplicate by subject.attribute, keeping latest source_chapter
    latest: dict[str, tuple[dict, int]] = {}
    for fact in facts:
        fact_type = str(fact.get("fact_type") or "").lower()
        if fact_type in _INDEX_EXCLUDED_TYPES:
            continue
        subject = str(fact.get("subject") or "")
        attribute = str(fact.get("attribute") or "")
        key = (
            f"{subject}.{attribute}"
            if subject and attribute
            else (subject or attribute or fact.get("fact_key", ""))
        )
        src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
        if key not in latest or src_ch > latest[key][1]:
            latest[key] = (fact, src_ch)

    if not latest:
        return []

    # Sort by source_chapter descending (most recent first)
    sorted_facts = sorted(latest.values(), key=lambda x: x[1], reverse=True)

    # Group by fact_type for readability
    by_type: dict[str, list[tuple[dict, int]]] = {}
    for fact, src_ch in sorted_facts:
        ft = str(fact.get("fact_type") or "other").lower()
        by_type.setdefault(ft, []).append((fact, src_ch))

    lines: list[str] = ["【事实索引脊柱 / Fact Index Spine】"]
    lines.append("以下为全部活跃事实的目录（仅元数据，详情见各分片或 Pull 通道）：")
    lines.append("")

    row_count = 0
    total_chars = 0
    type_labels = {
        "event": "事件",
        "relationship": "关系",
        "item": "道具",
        "location": "地点",
        "setting": "设定",
        "character": "角色",
        "plot": "伏笔",
    }

    for ft, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        label = type_labels.get(ft, ft)
        lines.append(f"[{label}]")
        for fact, src_ch in items:
            if row_count >= MAX_INDEX_ROWS:
                lines.append(f"  ...（还有 {len(sorted_facts) - row_count} 条未列出）")
                break
            subject = str(fact.get("subject") or "")
            attribute = str(fact.get("attribute") or "")
            name = f"{subject}.{attribute}" if subject and attribute else (subject or attribute or fact.get("fact_key", ""))
            age = current_chapter - src_ch if src_ch > 0 else 0
            age_tag = f"({age}章前)" if age > 0 else "(本章)"
            line = f"  - {name} {age_tag}"
            line_chars = len(line)
            if total_chars + line_chars > MAX_INDEX_CHARS:
                lines.append(f"  ...（索引已达字符上限，剩余未列出）")
                break
            lines.append(line)
            row_count += 1
            total_chars += line_chars
        else:
            continue
        break

    if row_count == 0:
        return []

    # Deferred import to avoid circular dependency
    from ..agent_runtime.context_builder import ContextItem

    return [
        ContextItem(
            kind="index_spine",
            text="\n".join(lines),
            source="index_spine",
            confidence=1.0,
            chapter_number=current_chapter,
            priority=6,
            trusted=True,
        )
    ]
