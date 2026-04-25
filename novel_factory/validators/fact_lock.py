"""Fact lock validator — verifies that Polisher didn't remove or change key facts.

Q8: Before polishing, key facts are extracted from instruction and state card.
After polishing, the output is checked against the fact lock list.
If critical facts are missing or changed, the Polisher must fail.
"""

from __future__ import annotations

import re
from typing import Any

from ..models.quality import FactLockItem, FactLockResult


def extract_fact_lock(
    instruction: dict[str, Any] | None,
    state_card: dict[str, Any] | None,
) -> list[FactLockItem]:
    """Extract facts to lock before polishing.

    Args:
        instruction: The chapter instruction dict.
        state_card: The previous chapter's state card data.

    Returns:
        List of FactLockItem to check after polishing.
    """
    items: list[FactLockItem] = []

    # Key events from instruction
    if instruction:
        key_events = instruction.get("key_events", "")
        if key_events:
            try:
                import json
                events = json.loads(key_events) if isinstance(key_events, str) else key_events
                for event in events[:5]:
                    items.append(FactLockItem(
                        fact_type="event",
                        content=str(event),
                        source="instruction",
                    ))
            except (json.JSONDecodeError, TypeError):
                if key_events:
                    items.append(FactLockItem(
                        fact_type="event",
                        content=str(key_events)[:200],
                        source="instruction",
                    ))

        # Plot references
        for field in ("plots_to_plant", "plots_to_resolve"):
            refs = instruction.get(field, "")
            if refs:
                try:
                    import json
                    ref_list = json.loads(refs) if isinstance(refs, str) else refs
                    for ref in ref_list[:5]:
                        items.append(FactLockItem(
                            fact_type="plot_ref",
                            content=str(ref),
                            source="instruction",
                        ))
                except (json.JSONDecodeError, TypeError):
                    pass

    # State card values
    if state_card:
        state_data = state_card.get("state_data", state_card) if isinstance(state_card, dict) else {}

        # Level/numeric values
        for key in ("level", "等级", "lv", "Lv", "级别"):
            val = state_data.get(key)
            if val is not None:
                items.append(FactLockItem(
                    fact_type="state_value",
                    content=f"{key}={val}",
                    source="state_card",
                ))
                break

        # Relations
        relations = state_data.get("relations", {})
        if isinstance(relations, dict):
            for name, relation in list(relations.items())[:5]:
                items.append(FactLockItem(
                    fact_type="relation",
                    content=f"{name}:{relation}",
                    source="state_card",
                ))

    return items


def check_fact_integrity(
    original_content: str,
    polished_content: str,
    fact_lock: list[FactLockItem],
) -> FactLockResult:
    """Check that polished content preserves all locked facts.

    Args:
        original_content: The original chapter content before polishing.
        polished_content: The polished chapter content.
        fact_lock: List of facts to verify.

    Returns:
        FactLockResult with missing/changed facts and risk level.
    """
    result = FactLockResult()
    
    # R1: Defensive handling for None content
    if original_content is None:
        original_content = ""
    if polished_content is None:
        polished_content = ""

    for item in fact_lock:
        if item.fact_type == "event":
            # Check if key event text appears in polished content
            if _is_content_removed(original_content, polished_content, item.content):
                result.missing_facts.append(item)

        elif item.fact_type == "plot_ref":
            # Check if plot reference code appears in polished content
            if item.content not in polished_content and item.content in original_content:
                result.missing_facts.append(item)

        elif item.fact_type == "state_value":
            # Check if numeric value still appears
            if item.content.split("=")[1] if "=" in item.content else item.content:
                # For state values, just check if a similar value exists
                val = item.content.split("=")[-1] if "=" in item.content else item.content
                if val not in polished_content and val in original_content:
                    result.changed_facts.append(item)

        elif item.fact_type == "relation":
            # Check if character name still appears
            name = item.content.split(":")[0] if ":" in item.content else item.content
            if name not in polished_content and name in original_content:
                result.missing_facts.append(item)

    # Determine risk level
    if result.missing_facts or result.changed_facts:
        critical_types = {item.fact_type for item in result.missing_facts + result.changed_facts}
        if "event" in critical_types or "plot_ref" in critical_types:
            result.risk = "high"
        else:
            result.risk = "low"
    else:
        result.risk = "none"

    return result


def _is_content_removed(original: str, polished: str, content: str) -> bool:
    """Check if a meaningful piece of content was removed during polishing.

    Uses a simple heuristic: if the content appears in the original
    but not in the polished version, it was removed.
    """
    # R1: Defensive handling for None content
    if original is None:
        original = ""
    if polished is None:
        polished = ""
    
    # For short content (event names), check substring
    if len(content) <= 50:
        return content in original and content not in polished

    # For longer content, check key phrases
    # Split into segments and check if most are preserved
    phrases = re.split(r"[，。！？；]", content)
    phrases = [p.strip() for p in phrases if len(p.strip()) > 3]

    if not phrases:
        return False

    missing_count = sum(1 for p in phrases if p in original and p not in polished)
    return missing_count > len(phrases) * 0.5
