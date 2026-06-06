"""Commercial Editor Lens — reader engagement and retention.

Checks hooks, payoffs, protagonist agency, and reading motivation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...models.chapter_contracts import EditorLensReport
from .base_lens import BaseEditorLens

logger = logging.getLogger(__name__)

# Anti-patterns that kill reader engagement
_ENGAGEMENT_KILLERS = [
    (r"简单来说", "说教式info dump"),
    (r"所谓.{2,10}就是", "旁白式解释"),
    (r"这个世界是", "世界观info dump"),
    (r"他感到一阵.{2,6}(欣慰|感动|温暖)", "直白情绪描写"),
]


class CommercialEditorLens(BaseEditorLens):
    """Checks commercial viability: hooks, payoffs, reader pull."""

    lens_type = "commercial"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        llm: Any | None = None,
    ) -> EditorLensReport:
        findings = []

        if not content or len(content) < 100:
            return EditorLensReport(
                lens_type=self.lens_type,
                passed=True,
                score=100.0,
                summary="内容过短，跳过商业性检查",
            )

        # Check for engagement killers
        for pattern, desc in _ENGAGEMENT_KILLERS:
            matches = re.findall(pattern, content)
            if matches:
                findings.append(self._finding(
                    "warning",
                    "ENGAGEMENT_KILLER",
                    f"{desc}: 检测到 {len(matches)} 处",
                    f"移除 '{pattern}' 类句式，用动作/对话展现",
                ))

        # Check for chapter ending hook
        last_200 = content[-200:].strip() if len(content) > 200 else content
        hook_indicators = ["？", "但", "却", "然而", "突然", "居然", "没想到"]
        has_hook = any(ind in last_200 for ind in hook_indicators)
        if not has_hook and len(content) > 500:
            findings.append(self._finding(
                "warning",
                "MISSING_HOOK",
                "章末缺少悬念钩子",
                "在章节结尾添加悬念、反转或问题，吸引读者继续阅读",
            ))

        # Check for protagonist agency (simplified)
        protagonist_name = context.get("protagonist_name", "")
        if protagonist_name and len(content) > 500:
            # Count protagonist action verbs vs passive descriptions
            action_verbs = ["决定", "选择", "冲", "跑", "说", "喊", "打", "踢", "握"]
            action_count = sum(content.count(v) for v in action_verbs)
            if action_count < 3:
                findings.append(self._finding(
                    "info",
                    "LOW_PROTAGONIST_AGENCY",
                    "主角能动性较低，多为被动描述",
                    "增加主角主动行动和决策的描写",
                ))

        # Check brief constraints
        chapter_brief = context.get("chapter_brief", {})
        if chapter_brief:
            tier1 = chapter_brief.get("tier1", {})
            forbidden = tier1.get("forbidden_moves", [])
            for move in forbidden:
                if isinstance(move, str) and len(move) > 2 and move in content:
                    findings.append(self._finding(
                        "blocking",
                        "BRIEF_FORBIDDEN_MOVE",
                        f"违反章节brief禁止动作: {move}",
                        f"移除或重写包含 '{move}' 的内容",
                    ))

        score = self._compute_score(findings)
        passed = not any(f.severity == "blocking" for f in findings)

        return EditorLensReport(
            lens_type=self.lens_type,
            passed=passed,
            score=score,
            findings=findings,
            summary=f"商业性检查: {len(findings)} 个问题",
        )
