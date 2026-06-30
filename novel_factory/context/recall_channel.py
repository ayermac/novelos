"""v6.10.14 S5: Pull recall channel for proactive entity-based fact retrieval.

Instead of waiting for the Writer to discover missing context, this module
proactively retrieves the full fact chain for entities mentioned in the
chapter brief.  This turns the context pipeline from pure "push" into
"push + pull".

Design:
- No LLM dependency — pure code entity extraction + DB lookup.
- Hard upper limit of :data:`MAX_PULL_ITEMS` to avoid noise.
- Returns :class:`ContextItem` list ready for injection into advisory_context.
"""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent_runtime.context_builder import ContextItem

MAX_PULL_ITEMS = 10


def extract_pull_entities(brief: dict[str, Any] | None) -> set[str]:
    """Extract entity names from a chapter brief for pull retrieval.

    Extracts CJK name-like tokens (2-6 chars) from ``key_events``,
    ``required_events``, and ``objective`` fields.
    """
    if brief is None:
        return set()

    entities: set[str] = set()
    for field_name in ("key_events", "required_events", "objective", "ending_hook"):
        raw = brief.get(field_name)
        if not raw:
            continue
        if isinstance(raw, (list, tuple)):
            text = " ".join(str(item) for item in raw)
        else:
            text = str(raw)
        # Split on common CJK connectors/particles before extracting name tokens
        text = re.sub(r"[的和与在是把被让给对为有于从到向以以及]", " ", text)
        for match in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
            token = match.group()
            entities.add(token)
            # Also add 2-3 char substrings of longer tokens
            if len(token) > 3:
                for i in range(len(token) - 1):
                    entities.add(token[i : i + 2])
                for i in range(len(token) - 2):
                    entities.add(token[i : i + 3])
    return entities


def pull_facts_for_entities(
    facts: list[dict[str, Any]],
    entities: set[str],
    current_chapter: int,
) -> list[dict[str, Any]]:
    """Retrieve the full fact chain for the given entities.

    Returns facts whose ``subject`` or ``value_json`` mentions any entity,
    capped at :data:`MAX_PULL_ITEMS`.
    """
    if not entities:
        return []

    result: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for fact in facts:
        if len(result) >= MAX_PULL_ITEMS:
            break
        fact_key = str(fact.get("fact_key") or "")
        if fact_key in seen_keys:
            continue

        subject = str(fact.get("subject") or "")
        value_json = str(fact.get("value_json") or "")
        attribute = str(fact.get("attribute") or "")

        # Check if any entity is mentioned in the fact
        matched = False
        for entity in entities:
            if entity and (entity in subject or entity in value_json or entity in attribute):
                matched = True
                break

        if matched:
            # Only include facts from chapters up to current
            src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
            if src_ch <= current_chapter:
                result.append(fact)
                seen_keys.add(fact_key)

    return result


def build_pull_context(
    facts: list[dict[str, Any]],
    brief: dict[str, Any] | None,
    current_chapter: int,
) -> list["ContextItem"]:
    """Build ContextItem list for proactively pulled entity facts.

    This is the main entry point.  Callers pass the full active story_facts
    list and the chapter brief; the function returns at most
    :data:`MAX_PULL_ITEMS` ContextItems for injection into advisory_context.
    """
    # Deferred import to avoid circular dependency
    from ..agent_runtime.context_builder import ContextItem

    entities = extract_pull_entities(brief)
    if not entities:
        return []

    pulled = pull_facts_for_entities(facts, entities, current_chapter)
    items: list[ContextItem] = []
    for fact in pulled:
        subject = fact.get("subject") or ""
        attribute = fact.get("attribute") or ""
        value = str(fact.get("value_json") or "")
        fact_type = str(fact.get("fact_type") or "").lower()
        # Exempt numeric_state from truncation (same as S2/F8)
        if fact_type != "numeric_state" and len(value) > 200:
            value = value[:200] + "..."
        text = f"[主动召回] {subject}.{attribute} = {value}" if subject or attribute else f"[主动召回] {value}"
        src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
        items.append(
            ContextItem(
                kind="pull_recall",
                text=text,
                source=f"pull:story_fact:{fact.get('fact_key', '')}",
                confidence=float(fact.get("confidence") or 1.0),
                chapter_number=src_ch,
                priority=5,
                trusted=True,
            )
        )
    return items
