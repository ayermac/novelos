"""CommercialViabilityChecker: 检测商业可行性指标。

检测维度：
- 首章3000字钩子强度
- 付费点密度
- 追读吸引力
- 主角能动性

规则层实现，可扩展LLM层。
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class CommercialViabilityChecker(ValidatorSkill):
    """检查章节的商业可行性指标。"""

    skill_id = "commercial-viability-check"
    skill_type = "validator"
    version = "1.0.0"

    # 钩子强度关键词
    HOOK_KEYWORDS = (
        "震惊", "惊骇", "不敢相信", "难以置信", "瞳孔一缩", "瞳孔骤缩",
        "猛地", "突然", "骤然", "忽然", "刹那", "瞬间",
        "危机", "危险", "生死", "死亡", "致命",
        "秘密", "真相", "谜团", "悬念",
        "冲突", "对峙", "对抗", "较量",
        "反转", "逆转", "意想不到",
    )

    # 主角能动性关键词
    PROTAGONIST_ACTION_KEYWORDS = (
        "决定", "选择", "计划", "谋划", "布局",
        "行动", "出击", "反击", "反抗", "挑战",
        "发现", "意识到", "察觉", "领悟",
        "主动", "毅然", "果断", "坚决",
    )

    # 被动描写关键词（负面）
    PASSIVE_KEYWORDS = (
        "被", "被逼", "被迫", "被安排", "被选择",
        "无奈", "无助", "只能", "只好", "不得不",
        "等待", "观望", "无能为力",
    )

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or "")
        chapter_number = int(payload.get("chapter_number") or 0)
        genre_contract = payload.get("genre_contract") or {}

        if not content:
            return {
                "ok": False,
                "error": "缺少 content 字段",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "EMPTY_CONTENT", "message": "正文为空", "suggestion": "请提供章节正文"}],
                    "summary": "正文为空，无法进行商业可行性检查",
                },
            }

        findings = []
        score = 100

        # 1. 首章钩子强度检查（仅首章）
        if chapter_number <= 1:
            hook_score, hook_findings = self._check_opening_hook(content)
            findings.extend(hook_findings)
            score = min(score, hook_score)

        # 2. 付费点密度检查（通常在第3-6章）
        if 3 <= chapter_number <= 6:
            payment_score, payment_findings = self._check_payment_point(content)
            findings.extend(payment_findings)
            score = min(score, payment_score)

        # 3. 追读吸引力检查
        retention_score, retention_findings = self._check_retention_hook(content)
        findings.extend(retention_findings)
        score = min(score, retention_score)

        # 4. 主角能动性检查
        agency_score, agency_findings = self._check_protagonist_agency(content)
        findings.extend(agency_findings)
        score = min(score, agency_score)

        passed = score >= 70
        summary = f"商业可行性检查{'通过' if passed else '未通过'}，得分: {score}"

        return {
            "ok": True,
            "error": None,
            "data": {
                "passed": passed,
                "score": score,
                "findings": findings,
                "summary": summary,
            },
        }

    def _check_opening_hook(self, content: str) -> tuple[int, list[dict]]:
        """检查首章钩子强度。"""
        findings = []
        opening = content[:3000]

        # 检查是否有强钩子词
        hook_count = sum(1 for kw in self.HOOK_KEYWORDS if kw in opening)

        if hook_count == 0:
            findings.append({
                "severity": "warning",
                "code": "WEAK_OPENING_HOOK",
                "message": "首章前3000字缺少强钩子词",
                "suggestion": "在开头加入冲突、悬念或危机元素吸引读者",
            })
            return 70, findings
        elif hook_count < 3:
            findings.append({
                "severity": "info",
                "code": "MODERATE_HOOK",
                "message": f"首章钩子强度中等（{hook_count}个钩子词）",
                "suggestion": "可考虑增加更多冲突或悬念元素",
            })
            return 80, findings

        return 100, findings

    def _check_payment_point(self, content: str) -> tuple[int, list[dict]]:
        """检查付费点密度。"""
        findings = []

        # 检查章节末尾是否有悬念/钩子
        ending = content[-500:] if len(content) > 500 else content
        has_hook = any(kw in ending for kw in ("悬念", "钩子", "伏笔", "疑问", "？", "……"))

        if not has_hook:
            findings.append({
                "severity": "warning",
                "code": "WEAK_PAYMENT_HOOK",
                "message": "章节末尾缺少悬念钩子",
                "suggestion": "在章节结尾设置悬念，引导读者继续阅读",
            })
            return 70, findings

        return 100, findings

    def _check_retention_hook(self, content: str) -> tuple[int, list[dict]]:
        """检查追读吸引力。"""
        findings = []

        # 检查是否有持续的冲突或悬念
        paragraphs = content.split("\n\n")
        if len(paragraphs) < 3:
            return 100, findings

        # 检查中间段落是否有推进感
        middle_start = len(paragraphs) // 3
        middle_end = len(paragraphs) * 2 // 3
        middle_text = "\n\n".join(paragraphs[middle_start:middle_end])

        action_keywords = ("发现", "决定", "行动", "变化", "发展", "推进")
        has_progression = any(kw in middle_text for kw in action_keywords)

        if not has_progression and len(middle_text) > 500:
            findings.append({
                "severity": "info",
                "code": "SLOW_MIDDLE",
                "message": "章节中段推进感较弱",
                "suggestion": "在中段加入更多行动或变化保持读者兴趣",
            })
            return 85, findings

        return 100, findings

    def _check_protagonist_agency(self, content: str) -> tuple[int, list[dict]]:
        """检查主角能动性。"""
        findings = []

        # 统计主动和被动关键词
        active_count = sum(1 for kw in self.PROTAGONIST_ACTION_KEYWORDS if kw in content)
        passive_count = sum(1 for kw in self.PASSIVE_KEYWORDS if kw in content)

        # 计算能动性比例
        total = active_count + passive_count
        if total == 0:
            return 100, findings

        agency_ratio = active_count / total

        if agency_ratio < 0.3:
            findings.append({
                "severity": "warning",
                "code": "LOW_PROTAGONIST_AGENCY",
                "message": f"主角能动性较低（主动:被动 = {active_count}:{passive_count}）",
                "suggestion": "增加主角的主动决策和行动，减少被动应对",
            })
            return 65, findings
        elif agency_ratio < 0.5:
            findings.append({
                "severity": "info",
                "code": "MODERATE_AGENCY",
                "message": f"主角能动性中等（主动:被动 = {active_count}:{passive_count}）",
                "suggestion": "可考虑增加更多主角主动推动剧情的情节",
            })
            return 85, findings

        return 100, findings
