"""Excitement Density Checker — v6.8.1

Deterministic validator that checks whether a chapter has sufficient
excitement/hook density throughout the text (not just at the end).

No LLM calls — pure regex + keyword heuristics.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class ExcitementDensityChecker(ValidatorSkill):
    """Check excitement/hook density across the full chapter text.

    Input payload:
      - text or content: chapter text
      - style_profile (optional): StyleProfile dict for thresholds

    Output data:
      - passed: bool
      - density_score: int (0-100)
      - excitement_map: list of segment scores
      - depression_ratio: float (0-1)
      - findings: list of issues
    """

    skill_id = "excitement-density-checker"
    version = "1.0.0"

    # ── Excitement markers ──────────────────────────────────────────

    # "爽点" markers (satisfaction/victory moments)
    _EXCITEMENT_MARKERS: list[str] = [
        # 打脸 / 逆袭
        "打脸", "逆袭", "碾压", "震惊", "惊呆", "目瞪口呆", "难以置信",
        "万万没想到", "翻盘", "逆转", "反杀",
        # 认可 / 胜利
        "认可", "赞赏", "佩服", "刮目相看", "另眼相看", "竖起大拇指",
        "胜利", "赢了", "成功", "突破", "觉醒",
        # 技能展示
        "一招", "一击", "秒杀", "碾压", "降维打击", "实力碾压",
        "惊艳", "叹为观止", "不可思议",
        # 金手指 / 系统
        "获得", "解锁", "激活", "升级", "进化", "强化",
        "签到", "抽奖", "奖励", "宝箱", "掉落",
        # 情感高潮
        "感动", "热血", "激动", "振奋", "鼓舞",
    ]

    # Depression / suppression markers
    _DEPRESSION_MARKERS: list[str] = [
        "嘲笑", "羞辱", "欺辱", "欺负", "蔑视", "鄙视", "看不起",
        "废物", "垃圾", "无能", "窝囊", "懦弱", "失败",
        "绝望", "痛苦", "悲伤", "凄惨", "悲惨", "落魄",
        "被骂", "被打", "被踩", "被踩在脚下", "被人看不起",
        "低声下气", "忍气吞声", "委曲求全", "逆来顺受",
        "压抑", "沉闷", "郁闷", "憋屈", "窝火",
    ]

    # Hook / suspense markers
    _HOOK_MARKERS: list[str] = [
        "忽然", "突然", "意外", "没想到", "竟然", "居然",
        "悬念", "秘密", "真相", "阴谋", "暗中",
        "但是", "然而", "可是", "不过", "却",
        "下一刻", "紧接着", "随即", "顿时",
    ]

    @staticmethod
    def _count_hits(text: str, markers: list[str]) -> int:
        """Count marker occurrences in text."""
        return sum(text.count(m) for m in markers)

    @staticmethod
    def _segment_text(text: str, segment_size: int = 500) -> list[str]:
        """Split text into segments of approximately segment_size characters."""
        segments = []
        start = 0
        while start < len(text):
            end = min(start + segment_size, len(text))
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end within last 100 chars of segment
                search_start = max(start, end - 100)
                last_period = max(
                    text.rfind("。", search_start, end),
                    text.rfind("！", search_start, end),
                    text.rfind("？", search_start, end),
                    text.rfind("\n", search_start, end),
                )
                if last_period > start:
                    end = last_period + 1
            segments.append(text[start:end])
            start = end
        return segments

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text") or payload.get("content", "")
        if not text:
            return {
                "ok": True,
                "error": None,
                "data": {
                    "passed": False,
                    "density_score": 0,
                    "excitement_map": [],
                    "depression_ratio": 1.0,
                    "findings": [{"code": "EMPTY_TEXT", "message": "正文为空", "severity": "blocking"}],
                },
            }

        cleaned = text.strip()
        total_chars = max(len(cleaned), 1)

        # Count markers across full text
        excitement_count = self._count_hits(cleaned, self._EXCITEMENT_MARKERS)
        depression_count = self._count_hits(cleaned, self._DEPRESSION_MARKERS)
        hook_count = self._count_hits(cleaned, self._HOOK_MARKERS)

        # Calculate depression ratio
        total_markers = excitement_count + depression_count
        depression_ratio = depression_count / max(total_markers, 1)

        # Segment analysis (every 500 chars)
        segments = self._segment_text(cleaned, 500)
        excitement_map: list[dict[str, Any]] = []
        consecutive_depression = 0
        max_consecutive_depression = 0

        for i, seg in enumerate(segments):
            seg_excitement = self._count_hits(seg, self._EXCITEMENT_MARKERS)
            seg_depression = self._count_hits(seg, self._DEPRESSION_MARKERS)
            seg_hook = self._count_hits(seg, self._HOOK_MARKERS)

            is_depressed = seg_depression > seg_excitement and seg_depression >= 2
            if is_depressed:
                consecutive_depression += 1
                max_consecutive_depression = max(max_consecutive_depression, consecutive_depression)
            else:
                consecutive_depression = 0

            excitement_map.append({
                "segment": i + 1,
                "chars": len(seg),
                "excitement_hits": seg_excitement,
                "depression_hits": seg_depression,
                "hook_hits": seg_hook,
                "is_depressed": is_depressed,
            })

        # Calculate density score (0-100)
        # Base: excitement per 1000 chars
        excitement_per_1000 = (excitement_count / total_chars) * 1000

        # Score calculation
        density_score = 0

        # 1. Excitement density (40 points)
        # Target: at least 1 excitement per 1000 chars
        if excitement_per_1000 >= 2:
            density_score += 40
        elif excitement_per_1000 >= 1:
            density_score += 30
        elif excitement_per_1000 >= 0.5:
            density_score += 20
        elif excitement_count > 0:
            density_score += 10

        # 2. Depression ratio (30 points)
        # Target: depression < 50% of total markers
        if depression_ratio < 0.3:
            density_score += 30
        elif depression_ratio < 0.5:
            density_score += 20
        elif depression_ratio < 0.7:
            density_score += 10
        # else: 0 points

        # 3. No long depression runs (20 points)
        # Target: no more than 2 consecutive depressed segments
        if max_consecutive_depression == 0:
            density_score += 20
        elif max_consecutive_depression <= 2:
            density_score += 10
        # else: 0 points

        # 4. Hook distribution (10 points)
        # Target: hooks present (not just at end)
        segments_with_hooks = sum(1 for seg in excitement_map if seg["hook_hits"] > 0)
        if segments_with_hooks >= len(segments) * 0.3:
            density_score += 10
        elif segments_with_hooks >= 1:
            density_score += 5

        density_score = min(100, density_score)

        # Determine pass/fail
        findings: list[dict[str, Any]] = []

        if depression_ratio >= 0.7 and depression_count >= 3:
            findings.append({
                "code": "HIGH_DEPRESSION_RATIO",
                "message": f"压抑内容占比过高（{depression_ratio:.0%}），爽点不足",
                "severity": "blocking",
                "suggestion": "增加爽点（打脸/认可/胜利/技能展示），降低压抑内容占比",
            })

        if max_consecutive_depression >= 3:
            findings.append({
                "code": "CONSECUTIVE_DEPRESSION",
                "message": f"连续压抑段落达 {max_consecutive_depression} 段（每段约 500 字），节奏过于沉闷",
                "severity": "blocking",
                "suggestion": "在压抑段落之间穿插爽点或微爽点，避免连续 3 段以上纯压抑",
            })

        if excitement_count == 0:
            findings.append({
                "code": "NO_EXCITEMENT",
                "message": "全文未检测到爽点标记（打脸/认可/胜利/技能展示等）",
                "severity": "warning",
                "suggestion": "每章至少包含一个爽点场景",
            })

        if excitement_per_1000 < 0.5 and total_chars > 1000:
            findings.append({
                "code": "LOW_EXCITEMENT_DENSITY",
                "message": f"爽点密度过低（每 1000 字仅 {excitement_per_1000:.1f} 个爽点标记）",
                "severity": "warning",
                "suggestion": "增加爽点频率，建议每 500-1000 字至少一个爽点",
            })

        passed = density_score >= 50 and depression_ratio < 0.7 and max_consecutive_depression < 3

        return {
            "ok": True,
            "error": None,
            "data": {
                "passed": passed,
                "density_score": density_score,
                "excitement_map": excitement_map,
                "excitement_count": excitement_count,
                "depression_count": depression_count,
                "depression_ratio": depression_ratio,
                "max_consecutive_depression": max_consecutive_depression,
                "hook_count": hook_count,
                "findings": findings,
            },
        }
