"""Deterministic chapter quality acceptance gates.

These checks do not claim literary judgment. They provide release-grade
operational signals for long-form production: terminal status, enough content,
scene-beat payload health, and an observable ending hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..validators.chapter_checker import count_words


TERMINAL_STATUSES = {"reviewed", "awaiting_publish", "published"}
HOOK_MARKERS = ("？", "?", "！", "!", "。", "……", "——", "：", ":")


@dataclass(frozen=True)
class AcceptanceThresholds:
    min_word_count: int = 2500
    min_chars_per_beat: int = 250
    min_scene_beats: int = 1


def _check(name: str, passed: bool, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "message": message,
        "details": details or {},
    }


def _status(chapter: dict[str, Any]) -> str:
    return str(chapter.get("status") or "unknown")


def _content(chapter: dict[str, Any]) -> str:
    return str(chapter.get("content") or "")


def _beat_complete(beat: dict[str, Any]) -> bool:
    return all(str(beat.get(field) or "").strip() for field in ("scene_goal", "conflict", "turn", "hook"))


def evaluate_chapter_quality(
    chapter: dict[str, Any] | None,
    scene_beats: list[dict[str, Any]] | None = None,
    *,
    thresholds: AcceptanceThresholds | None = None,
) -> dict[str, Any]:
    """Return deterministic quality acceptance for one chapter.

    The result is intentionally JSON-serializable and stable for scripts/CI.
    """
    thresholds = thresholds or AcceptanceThresholds()
    chapter = chapter or {}
    scene_beats = scene_beats or []
    content = _content(chapter)
    word_count = int(chapter.get("word_count") or count_words(content))
    status = _status(chapter)

    checks: list[dict[str, Any]] = []
    checks.append(_check(
        "terminal_status",
        status in TERMINAL_STATUSES,
        f"chapter status is {status}",
        {"status": status, "accepted": sorted(TERMINAL_STATUSES)},
    ))
    checks.append(_check(
        "word_count",
        word_count >= thresholds.min_word_count,
        f"word_count {word_count} >= {thresholds.min_word_count}",
        {"word_count": word_count, "minimum": thresholds.min_word_count},
    ))

    beat_count = len(scene_beats)
    complete_beats = sum(1 for beat in scene_beats if _beat_complete(beat))
    checks.append(_check(
        "scene_beats_present",
        beat_count >= thresholds.min_scene_beats,
        f"scene_beats {beat_count} >= {thresholds.min_scene_beats}",
        {"scene_beats": beat_count, "minimum": thresholds.min_scene_beats},
    ))
    if beat_count:
        checks.append(_check(
            "scene_beats_complete",
            complete_beats == beat_count,
            f"{complete_beats}/{beat_count} scene beats include goal/conflict/turn/hook",
            {"complete": complete_beats, "total": beat_count},
        ))
        checks.append(_check(
            "content_per_beat",
            word_count >= beat_count * thresholds.min_chars_per_beat,
            f"word_count {word_count} >= {beat_count * thresholds.min_chars_per_beat} for {beat_count} beats",
            {
                "word_count": word_count,
                "scene_beats": beat_count,
                "min_chars_per_beat": thresholds.min_chars_per_beat,
            },
        ))

    tail = content[-240:].strip()
    checks.append(_check(
        "ending_hook_observable",
        bool(tail) and any(marker in tail for marker in HOOK_MARKERS),
        "chapter ending has observable punctuation/hook marker",
        {"tail_preview": tail[-120:]},
    ))

    failed = [check for check in checks if not check["passed"]]
    score = round(100 * (len(checks) - len(failed)) / max(1, len(checks)), 1)
    next_actions = []
    for check in failed:
        if check["name"] == "terminal_status":
            next_actions.append("continue workflow until reviewed/awaiting_publish/published")
        elif check["name"] == "word_count":
            next_actions.append("expand author output or lower chapter target intentionally")
        elif check["name"].startswith("scene_beats"):
            next_actions.append("rerun or repair screenwriter scene beats")
        elif check["name"] == "content_per_beat":
            next_actions.append("rerun author with per-beat expansion")
        elif check["name"] == "ending_hook_observable":
            next_actions.append("repair final paragraph hook")

    return {
        "ok": not failed,
        "score": score,
        "status": status,
        "word_count": word_count,
        "scene_beat_count": beat_count,
        "failed_count": len(failed),
        "checks": checks,
        "next_actions": next_actions,
    }
