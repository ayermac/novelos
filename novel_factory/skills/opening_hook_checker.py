"""Opening Hook Checker — v6.8.1

Deterministic validator that checks whether the opening 200 characters
of a chapter contain a narrative hook (suspense, conflict, reversal,
cheat-hint, or reversal-expectation).

No LLM calls — pure regex + keyword heuristics.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class OpeningHookChecker(ValidatorSkill):
    """Check whether the chapter opening has a narrative hook.

    Input payload:
      - text or content: chapter text
      - style_profile (optional): StyleProfile dict for style-aware thresholds

    Output data:
      - passed: bool
      - hook_type: str | None
      - hook_strength: int (0-100)
      - opening_text: first 200 chars
      - findings: list of issues
    """

    skill_id = "opening-hook-checker"
    version = "1.0.0"

    # ── Hook pattern categories ─────────────────────────────────────

    # Suspense / mystery hooks
    _SUSPENSE_PATTERNS: list[str] = [
        r"忽然",
        r"突然",
        r"意外",
        r"没想到",
        r"竟然",
        r"居然",
        r"不可思议",
        r"诡异",
        r"异常",
        r"蹊跷",
        r"神秘",
        r"秘密",
        r"暗中",
        r"偷偷",
        r"悄悄",
    ]

    # Conflict / tension hooks
    _CONFLICT_PATTERNS: list[str] = [
        r"冲突",
        r"争执",
        r"争吵",
        r"怒",
        r"吼",
        r"咆哮",
        r"威胁",
        r"逼迫",
        r"绝境",
        r"危机",
        r"危险",
        r"生死",
        r"命悬一线",
        r"千钧一发",
    ]

    # Reversal / twist hooks
    _REVERSAL_PATTERNS: list[str] = [
        r"反转",
        r"逆转",
        r"翻盘",
        r"逆袭",
        r"打脸",
        r"碾压",
        r"震惊",
        r"惊呆",
        r"目瞪口呆",
        r"难以置信",
        r"万万没想到",
    ]

    # Cheat / golden-finger hints
    _CHEAT_PATTERNS: list[str] = [
        r"金手指",
        r"系统",
        r"签到",
        r"抽奖",
        r"觉醒",
        r"获得.*能力",
        r"解锁",
        r"激活",
        r"绑定",
        r"传承",
        r"宝物",
        r"神器",
    ]

    # Reversal-expectation (reader expects the MC to rise)
    _EXPECTATION_PATTERNS: list[str] = [
        r"潜力",
        r"天赋",
        r"血脉",
        r"前世",
        r"重生",
        r"穿越",
        r"回到.*前",
        r"记忆",
        r"经验",
        r"机遇",
        r"奇遇",
        r"机缘",
    ]

    # Opening-excitement keywords (webnovel style)
    _EXCITEMENT_KEYWORDS: list[str] = [
        "逆袭", "打脸", "金手指", "系统", "开局", "重生", "穿越",
        "赘婿", "退婚", "龙王", "战神", "医神", "神豪",
    ]

    # Depression markers (negative if dominant in opening)
    _DEPRESSION_MARKERS: list[str] = [
        "嘲笑", "羞辱", "欺辱", "欺负", "蔑视", "鄙视", "看不起",
        "废物", "垃圾", "无能", "窝囊", "懦弱", "失败",
        "绝望", "痛苦", "悲伤", "凄惨", "悲惨", "落魄",
    ]

    @staticmethod
    def _count_pattern_hits(text: str, patterns: list[str]) -> int:
        """Count how many patterns match in the text."""
        count = 0
        for pattern in patterns:
            if re.search(pattern, text):
                count += 1
        return count

    @staticmethod
    def _find_hook_type(text: str) -> tuple[str | None, int]:
        """Detect the primary hook type and its strength (0-100)."""
        checks = [
            ("suspense", OpeningHookChecker._SUSPENSE_PATTERNS),
            ("conflict", OpeningHookChecker._CONFLICT_PATTERNS),
            ("reversal", OpeningHookChecker._REVERSAL_PATTERNS),
            ("cheat_hint", OpeningHookChecker._CHEAT_PATTERNS),
            ("reversal_expectation", OpeningHookChecker._EXPECTATION_PATTERNS),
        ]

        best_type: str | None = None
        best_hits = 0

        for hook_type, patterns in checks:
            hits = OpeningHookChecker._count_pattern_hits(text, patterns)
            if hits > best_hits:
                best_hits = hits
                best_type = hook_type

        # Also check excitement keywords
        excitement_hits = sum(1 for kw in OpeningHookChecker._EXCITEMENT_KEYWORDS if kw in text)
        if excitement_hits > best_hits:
            best_hits = excitement_hits
            best_type = "webnovel_excitement"

        # Calculate strength: 1 hit = 40, 2 = 60, 3 = 80, 4+ = 100
        if best_hits == 0:
            return None, 0
        strength = min(100, 20 + best_hits * 20)

        return best_type, strength

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text") or payload.get("content", "")
        if not text:
            return {
                "ok": True,
                "error": None,
                "data": {
                    "passed": False,
                    "hook_type": None,
                    "hook_strength": 0,
                    "opening_text": "",
                    "findings": [{"code": "EMPTY_TEXT", "message": "正文为空", "severity": "blocking"}],
                },
            }

        # Extract opening 200 characters (skip whitespace/newlines at start)
        cleaned = text.strip()
        opening = cleaned[:200]

        # Detect hook
        hook_type, hook_strength = self._find_hook_type(opening)

        # Check for depression dominance
        depression_count = self._count_pattern_hits(opening, self._DEPRESSION_MARKERS)
        has_hook = hook_type is not None and hook_strength >= 40

        findings: list[dict[str, Any]] = []

        if not has_hook:
            findings.append({
                "code": "NO_OPENING_HOOK",
                "message": "开局 200 字未检测到钩子（悬念/冲突/反转/金手指暗示/逆袭预期）",
                "severity": "warning",
                "suggestion": "在章节开头 200 字内加入悬念、冲突或逆袭预期",
            })

        if depression_count >= 3 and not has_hook:
            findings.append({
                "code": "DEPRESSION_DOMINANT_OPENING",
                "message": f"开局以压抑内容为主（检测到 {depression_count} 个压抑标记），缺乏钩子",
                "severity": "blocking",
                "suggestion": "开局不应以纯压抑铺陈开始，需在前 200 字建立逆袭预期或悬念",
            })

        passed = has_hook and depression_count < 3

        return {
            "ok": True,
            "error": None,
            "data": {
                "passed": passed,
                "hook_type": hook_type,
                "hook_strength": hook_strength,
                "opening_text": opening,
                "depression_count": depression_count,
                "findings": findings,
            },
        }
