"""v6.9.0: Ledger context builder for Planner.

Loads creative ledger snapshots and builds context for Planner agent,
providing visibility into ongoing narrative threads, character arcs,
mystery status, and style patterns.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..db.repository import Repository

logger = logging.getLogger(__name__)


# ── Ledger type descriptions ─────────────────────────────────────────────

LEDGER_DESCRIPTIONS = {
    "reader_promise": "读者承诺台账 - 跟踪对读者的承诺及其兑现状态",
    "power_growth": "力量成长台账 - 跟踪主角能力获取和升级",
    "character_arc": "角色弧线台账 - 跟踪角色成长和转变里程碑",
    "mystery_reveal": "悬疑揭示台账 - 跟踪悬疑线索的引入和揭示",
    "conflict": "冲突台账 - 跟踪冲突的开始、升级和解决",
    "payoff": "回报台账 - 跟踪给读者的回报时刻",
    "style_fatigue": "风格疲劳台账 - 跟踪重复模式和AI痕迹",
}


# ── Context builder ──────────────────────────────────────────────────────


def load_ledgers_for_planner(
    repo: Repository,
    project_id: str,
    chapter_number: int,
) -> dict[str, Any]:
    """Load creative ledger snapshots for Planner context.

    Reads the latest snapshot for each ledger type and builds
    a summary dict for injection into Planner prompt.

    Args:
        repo: Repository instance
        project_id: Project identifier
        chapter_number: Current chapter number (reads up to chapter_number - 1)

    Returns:
        Dict with ledger summaries for Planner context
    """
    ledgers = {}

    for ledger_type, description in LEDGER_DESCRIPTIONS.items():
        try:
            # Get latest snapshot before current chapter
            snapshot = repo.get_creative_ledger(project_id, chapter_number - 1, ledger_type)
            if not snapshot and hasattr(repo, "get_latest_creative_ledger"):
                # Try earlier chapters via the latest-snapshot fallback
                snapshot = repo.get_latest_creative_ledger(project_id, ledger_type)

            if snapshot:
                ledger_data = _parse_ledger_data(snapshot.get("ledger_data", "{}"))
                summary = ledger_data.get("summary", "")
                entries = ledger_data.get("entries", [])

                ledgers[ledger_type] = {
                    "description": description,
                    "summary": summary,
                    "entries_count": len(entries),
                    "recent_entries": _extract_recent_entries(entries, limit=5),
                    "status_counts": _count_entry_statuses(entries),
                }
            else:
                ledgers[ledger_type] = {
                    "description": description,
                    "summary": "无数据",
                    "entries_count": 0,
                    "recent_entries": [],
                    "status_counts": {},
                }
        except Exception as e:
            logger.warning(f"Failed to load {ledger_type} ledger: {e}")
            ledgers[ledger_type] = {
                "description": description,
                "summary": f"加载失败: {str(e)}",
                "entries_count": 0,
                "recent_entries": [],
                "status_counts": {},
            }

    return ledgers


def format_ledger_context_for_prompt(ledgers: dict[str, Any]) -> str:
    """Format ledger context for injection into Planner prompt.

    Creates a concise summary of all ledger statuses for the Planner
    to consider when planning the next chapter.
    """
    if not ledgers:
        return ""

    parts = ["【创作台账摘要】"]

    # Reader promises - most critical for Planner
    reader_promise = ledgers.get("reader_promise", {})
    if reader_promise.get("entries_count", 0) > 0:
        active_count = reader_promise.get("status_counts", {}).get("active", 0)
        fulfilled_count = reader_promise.get("status_counts", {}).get("fulfilled", 0)
        parts.append(f"读者承诺: {active_count}个活跃, {fulfilled_count}个已兑现")
        if reader_promise.get("recent_entries"):
            parts.append("最近承诺:")
            for entry in reader_promise["recent_entries"][:3]:
                parts.append(f"  - {entry.get('promise', '')} [{entry.get('status', '')}]")

    # Power growth - important for progression genres
    power_growth = ledgers.get("power_growth", {})
    if power_growth.get("entries_count", 0) > 0:
        parts.append(f"力量成长: {power_growth['entries_count']}个能力记录")

    # Mystery reveals - important for mystery/suspense
    mystery_reveal = ledgers.get("mystery_reveal", {})
    if mystery_reveal.get("entries_count", 0) > 0:
        active_count = mystery_reveal.get("status_counts", {}).get("introduced", 0) + \
                      mystery_reveal.get("status_counts", {}).get("deepening", 0)
        parts.append(f"悬疑线索: {active_count}个未揭示")

    # Conflicts - track ongoing tensions
    conflict = ledgers.get("conflict", {})
    if conflict.get("entries_count", 0) > 0:
        active_count = conflict.get("status_counts", {}).get("active", 0) + \
                      conflict.get("status_counts", {}).get("escalating", 0)
        parts.append(f"活跃冲突: {active_count}个")

    # Style fatigue - warning for repetitive patterns
    style_fatigue = ledgers.get("style_fatigue", {})
    fatigue_score = 0.0
    if style_fatigue.get("recent_entries"):
        fatigue_score = style_fatigue["recent_entries"][0].get("fatigue_score", 0.0)
    if fatigue_score > 0.6:
        parts.append(f"⚠️ 风格疲劳警告: {fatigue_score:.1%} - 需要变化写作模式")

    return "\n".join(parts)


# ── Helper functions ─────────────────────────────────────────────────────


def _parse_ledger_data(data: str | dict) -> dict:
    """Parse ledger data from string or dict."""
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_recent_entries(entries: list[dict], limit: int = 5) -> list[dict]:
    """Extract most recent entries from ledger.

    Each ledger type uses different field names for the chapter index
    (``chapter``, ``chapter_introduced``, ``chapter_acquired``,
    ``chapter_started``, ``chapter_detected``). We probe a known set of
    keys to find the chapter number; if none is present, the entry is
    sorted with chapter 0 (i.e. treated as oldest).
    """
    if not entries:
        return []

    chapter_keys = (
        "chapter",
        "chapter_introduced",
        "chapter_acquired",
        "chapter_started",
        "chapter_detected",
        "chapter_revealed",
        "chapter_resolved",
        "chapter_upgraded",
    )

    def _chapter_of(entry: dict) -> int:
        for key in chapter_keys:
            val = entry.get(key)
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val.isdigit():
                return int(val)
        return 0

    sorted_entries = sorted(entries, key=_chapter_of, reverse=True)
    return sorted_entries[:limit]


def _count_entry_statuses(entries: list[dict]) -> dict[str, int]:
    """Count entries by status."""
    counts = {}
    for entry in entries:
        status = entry.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts