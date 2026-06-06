"""MysteryIntegrityChecker: 检测悬疑/推理/惊悚类型小说的完整性。

检测维度：
- 伏笔债务
- 揭示节奏
- 误导合理性
- 术语过载

仅在 genre_contract.genre ∈ (悬疑, 推理, 惊悚) 时由项目 override 启用。
failure_policy: warn
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class MysteryIntegrityChecker(ValidatorSkill):
    """检查悬疑/推理/惊悚类型小说的完整性。"""

    skill_id = "mystery-integrity-check"
    skill_type = "validator"
    version = "1.0.0"

    # 悬疑相关关键词
    MYSTERY_KEYWORDS = (
        "谜团", "悬念", "伏笔", "线索", "暗示",
        "真相", "秘密", "阴谋", "诡计", "陷阱",
        "误导", "假象", "伪装", "隐藏", "隐瞒",
        "推理", "推断", "分析", "调查", "追踪",
    )

    # 术语过载标记
    TERMINOLOGY_MARKERS = (
        "专业术语", "技术名词", "行业黑话",
        "缩写", "代号", "暗语",
    )

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or "")
        genre_contract = payload.get("genre_contract") or {}
        foreshadowing = payload.get("foreshadowing") or []

        # 检查是否为悬疑类型
        genre = genre_contract.get("genre", "")
        if genre not in ("悬疑", "推理", "惊悚", "mystery", "thriller"):
            return {
                "ok": True,
                "error": None,
                "data": {
                    "passed": True,
                    "score": 100,
                    "findings": [],
                    "summary": f"跳过悬疑完整性检查（当前类型: {genre}）",
                },
            }

        if not content:
            return {
                "ok": False,
                "error": "缺少 content 字段",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "EMPTY_CONTENT", "message": "正文为空", "suggestion": "请提供章节正文"}],
                    "summary": "正文为空，无法进行悬疑完整性检查",
                },
            }

        findings = []
        score = 100

        # 1. 伏笔债务检查
        debt_score, debt_findings = self._check_foreshadowing_debt(content, foreshadowing)
        findings.extend(debt_findings)
        score = min(score, debt_score)

        # 2. 揭示节奏检查
        reveal_score, reveal_findings = self._check_reveal_pacing(content)
        findings.extend(reveal_findings)
        score = min(score, reveal_score)

        # 3. 误导合理性检查
        mislead_score, mislead_findings = self._check_misdirection(content)
        findings.extend(mislead_findings)
        score = min(score, mislead_score)

        # 4. 术语过载检查
        term_score, term_findings = self._check_terminology_overload(content)
        findings.extend(term_findings)
        score = min(score, term_score)

        passed = score >= 70
        summary = f"悬疑完整性检查{'通过' if passed else '未通过'}，得分: {score}"

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

    def _check_foreshadowing_debt(self, content: str, foreshadowing: list[dict]) -> tuple[int, list[dict]]:
        """检查伏笔债务。"""
        findings = []

        if not foreshadowing:
            return 100, findings

        # 检查已埋伏笔是否在本章有进展
        unresolved_count = 0
        for foreshadow in foreshadowing:
            foreshadow_id = foreshadow.get("id", "")
            foreshadow_desc = foreshadow.get("description", "")
            status = foreshadow.get("status", "")

            # 如果伏笔状态为"已埋"但本章未提及
            if status == "planted" and foreshadow_desc:
                # 简单检查：伏笔描述中的关键词是否在内容中出现
                keywords = foreshadow_desc[:20].split()
                if not any(kw in content for kw in keywords if len(kw) > 1):
                    unresolved_count += 1

        if unresolved_count > 3:
            findings.append({
                "severity": "warning",
                "code": "HIGH_FORESHADOWING_DEBT",
                "message": f"有{unresolved_count}个伏笔未在本章推进",
                "suggestion": "考虑推进或提及部分伏笔以保持读者兴趣",
            })
            return 70, findings
        elif unresolved_count > 0:
            findings.append({
                "severity": "info",
                "code": "FORESHADOWING_DEBT",
                "message": f"有{unresolved_count}个伏笔未在本章推进",
                "suggestion": "可选择性推进重要伏笔",
            })
            return 90, findings

        return 100, findings

    def _check_reveal_pacing(self, content: str) -> tuple[int, list[dict]]:
        """检查揭示节奏。"""
        findings = []

        # 检查是否有过多揭示
        reveal_keywords = ("真相是", "原来", "实际上", "其实", "事实上", "揭秘", "揭晓")
        reveal_count = sum(1 for kw in reveal_keywords if kw in content)

        if reveal_count > 3:
            findings.append({
                "severity": "warning",
                "code": "TOO_MANY_REVEALS",
                "message": f"本章揭示过多（{reveal_count}次）",
                "suggestion": "控制揭示节奏，避免信息过载",
            })
            return 70, findings

        # 检查是否有悬念维持
        suspense_keywords = ("悬念", "疑问", "未解之谜", "？", "……")
        has_suspense = any(kw in content for kw in suspense_keywords)

        if not has_suspense and len(content) > 2000:
            findings.append({
                "severity": "info",
                "code": "NO_SUSPENSE_MAINTAINED",
                "message": "章节未维持悬念",
                "suggestion": "在章节结尾留下悬念以保持读者兴趣",
            })
            return 85, findings

        return 100, findings

    def _check_misdirection(self, content: str) -> tuple[int, list[dict]]:
        """检查误导合理性。"""
        findings = []

        # 检查是否有误导性描述
        misdirection_keywords = ("似乎", "好像", "仿佛", "感觉", "以为", "误以为")
        misdirection_count = sum(1 for kw in misdirection_keywords if kw in content)

        # 误导过多可能让读者困惑
        if misdirection_count > 5:
            findings.append({
                "severity": "warning",
                "code": "EXCESSIVE_MISDIRECTION",
                "message": f"误导性描述过多（{misdirection_count}次）",
                "suggestion": "适度使用误导，避免读者失去信任",
            })
            return 75, findings

        return 100, findings

    def _check_terminology_overload(self, content: str) -> tuple[int, list[dict]]:
        """检查术语过载。"""
        findings = []

        # 检测可能的术语（连续的专业词汇）
        # 简化版：检测括号内的解释
        explanation_pattern = re.compile(r'（[^）]{10,}）')
        explanations = explanation_pattern.findall(content)

        if len(explanations) > 5:
            findings.append({
                "severity": "info",
                "code": "TERMINOLOGY_OVERLOAD",
                "message": f"术语解释较多（{len(explanations)}处）",
                "suggestion": "考虑简化术语或分散解释",
            })
            return 85, findings

        return 100, findings
