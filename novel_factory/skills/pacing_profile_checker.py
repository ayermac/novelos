"""PacingProfileChecker: 检测节奏配置。

检测维度：
- 段落长短分布
- 高潮位置
- 场景多样性
- 压力/奖励节奏

规则层：统计段落长度方差、对话/描写比例、场景切换次数。
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from .base import ValidatorSkill


class PacingProfileChecker(ValidatorSkill):
    """检查章节的节奏配置。"""

    skill_id = "pacing-profile-check"
    skill_type = "validator"
    version = "1.0.0"

    # 场景切换标记
    SCENE_BREAK_MARKERS = (
        "——", "****", "***", "---", "***",
        "转场", "镜头切换", "场景切换",
        "时间流逝", "数小时后", "几天后",
    )

    # 对话片段（兼容直引号、中文弯引号和书名号式引号）
    DIALOGUE_PATTERN = re.compile(r'["“「『]([^"“”「」『』]+)["”」』]')

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or "")

        if not content:
            return {
                "ok": False,
                "error": "缺少 content 字段",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "EMPTY_CONTENT", "message": "正文为空", "suggestion": "请提供章节正文"}],
                    "summary": "正文为空，无法进行节奏检查",
                },
            }

        findings = []
        score = 100

        # 1. 段落长度分布检查
        para_score, para_findings = self._check_paragraph_distribution(content)
        findings.extend(para_findings)
        score = min(score, para_score)

        # 2. 高潮位置检查
        climax_score, climax_findings = self._check_climax_position(content)
        findings.extend(climax_findings)
        score = min(score, climax_score)

        # 3. 场景多样性检查
        scene_score, scene_findings = self._check_scene_diversity(content)
        findings.extend(scene_findings)
        score = min(score, scene_score)

        # 4. 对话/描写比例检查
        dialogue_score, dialogue_findings = self._check_dialogue_ratio(content)
        findings.extend(dialogue_findings)
        score = min(score, dialogue_score)

        passed = score >= 70
        summary = f"节奏检查{'通过' if passed else '未通过'}，得分: {score}"

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

    def _check_paragraph_distribution(self, content: str) -> tuple[int, list[dict]]:
        """检查段落长度分布。"""
        findings = []

        # 分割段落
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) < 3:
            return 100, findings

        # 计算段落长度
        lengths = [len(p) for p in paragraphs]

        # 计算变异系数（标准差/均值）
        if statistics.mean(lengths) > 0:
            cv = statistics.stdev(lengths) / statistics.mean(lengths)
        else:
            cv = 0

        # 变异系数过低表示段落长度过于均匀
        if cv < 0.3:
            findings.append({
                "severity": "warning",
                "code": "UNIFORM_PARAGRAPHS",
                "message": f"段落长度过于均匀（变异系数: {cv:.2f}）",
                "suggestion": "适当变化段落长短，创造节奏感",
            })
            return 75, findings

        # 变异系数过高表示段落长度差异过大
        if cv > 1.5:
            findings.append({
                "severity": "info",
                "code": "HIGH_VARIANCE_PARAGRAPHS",
                "message": f"段落长度差异较大（变异系数: {cv:.2f}）",
                "suggestion": "确保长短段落的分布是有意为之",
            })
            return 90, findings

        return 100, findings

    def _check_climax_position(self, content: str) -> tuple[int, list[dict]]:
        """检查高潮位置。"""
        findings = []

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) < 5:
            return 100, findings

        # 检测高潮关键词
        climax_keywords = ("震惊", "惊骇", "不敢相信", "瞳孔一缩", "猛地", "突然", "危机", "生死")
        
        # 找出包含高潮关键词的段落位置
        climax_positions = []
        for i, para in enumerate(paragraphs):
            if any(kw in para for kw in climax_keywords):
                climax_positions.append(i / len(paragraphs))

        if not climax_positions:
            findings.append({
                "severity": "info",
                "code": "NO_CLIMAX_DETECTED",
                "message": "未检测到明显高潮",
                "suggestion": "考虑在章节中设置高潮点",
            })
            return 90, findings

        # 检查高潮是否在后半段
        avg_climax_pos = statistics.mean(climax_positions)
        if avg_climax_pos < 0.4:
            findings.append({
                "severity": "warning",
                "code": "EARLY_CLIMAX",
                "message": f"高潮位置偏前（平均位置: {avg_climax_pos:.0%}）",
                "suggestion": "考虑将高潮移至章节后半段以保持张力",
            })
            return 75, findings

        return 100, findings

    def _check_scene_diversity(self, content: str) -> tuple[int, list[dict]]:
        """检查场景多样性。"""
        findings = []

        # 统计场景切换次数
        scene_breaks = sum(1 for marker in self.SCENE_BREAK_MARKERS if marker in content)

        # 根据章节长度评估场景切换频率
        word_count = len(content)
        if word_count < 1000:
            expected_breaks = 0
        elif word_count < 3000:
            expected_breaks = 1
        else:
            expected_breaks = max(1, word_count // 2000)

        if scene_breaks < expected_breaks:
            findings.append({
                "severity": "info",
                "code": "LOW_SCENE_DIVERSITY",
                "message": f"场景切换较少（{scene_breaks}次，预期约{expected_breaks}次）",
                "suggestion": "考虑增加场景变化以丰富叙事层次",
            })
            return 85, findings

        return 100, findings

    def _check_dialogue_ratio(self, content: str) -> tuple[int, list[dict]]:
        """检查对话/描写比例。"""
        findings = []

        # 统计对话字符数
        dialogue_chars = sum(
            len(match.group(1)) for match in self.DIALOGUE_PATTERN.finditer(content)
        )

        total_chars = len(content)
        if total_chars == 0:
            return 100, findings

        dialogue_ratio = dialogue_chars / total_chars

        # 对话比例过低
        if dialogue_ratio < 0.15:
            findings.append({
                "severity": "warning",
                "code": "LOW_DIALOGUE_RATIO",
                "message": f"对话比例较低（{dialogue_ratio:.0%}）",
                "suggestion": "增加对话可以提升节奏感和角色互动",
            })
            return 75, findings

        # 对话比例过高
        if dialogue_ratio > 0.6:
            findings.append({
                "severity": "info",
                "code": "HIGH_DIALOGUE_RATIO",
                "message": f"对话比例较高（{dialogue_ratio:.0%}）",
                "suggestion": "确保有足够的描写和叙述支撑对话",
            })
            return 85, findings

        return 100, findings
