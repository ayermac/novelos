"""Character Editor Lens — character motivation, agency, and relationship progression.

Checks character consistency, motivation clarity, agency, and relationship movement.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...models.chapter_contracts import EditorLensReport
from .base_lens import BaseEditorLens

logger = logging.getLogger(__name__)

# Tool-person patterns (characters used as plot devices without agency)
_TOOL_PERSON_PATTERNS = [
    (r"只是为了.{2,10}(存在|出场|出现)", "角色工具化"),
    (r"他的唯一作用就是", "角色工具化"),
]


class CharacterEditorLens(BaseEditorLens):
    """Checks character quality: motivation, agency, relationships."""

    lens_type = "character"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        llm: Any | None = None,
    ) -> EditorLensReport:
        findings = []

        if not content or len(content) < 200:
            return EditorLensReport(
                lens_type=self.lens_type,
                passed=True,
                score=100.0,
                summary="内容过短，跳过角色检查",
            )

        # Check for tool-person patterns
        for pattern, desc in _TOOL_PERSON_PATTERNS:
            if re.search(pattern, content):
                findings.append(self._finding(
                    "warning",
                    "CHARACTER_TOOLING",
                    f"疑似角色工具化: {desc}",
                    "赋予角色独立动机和能动性",
                ))

        # Check protagonist agency
        protagonist_name = context.get("protagonist_name", "")
        chapter_brief = context.get("chapter_brief", {})
        
        if chapter_brief:
            tier1 = chapter_brief.get("tier1", {})
            agency_requirement = tier1.get("protagonist_agency", "")
            if agency_requirement:
                # Simple check: does the protagonist appear in action context?
                if protagonist_name and protagonist_name in content:
                    action_context = re.findall(
                        rf"{protagonist_name}.{{0,20}}[决定选择冲跑说喊]",
                        content
                    )
                    if not action_context and len(content) > 500:
                        findings.append(self._finding(
                            "warning",
                            "LOW_AGENCY",
                            f"主角'{protagonist_name}'能动性不足，未体现brief要求: {agency_requirement}",
                            "增加主角主动决策和行动的场景",
                        ))

        # Check for character relationship movement
        # If chapter has romantic/social content, check for relationship progression
        romance_indicators = ["喜欢", "心动", "脸红", "牵手", "拥抱", "亲吻"]
        has_romance = any(ind in content for ind in romance_indicators)
        if has_romance:
            # Check if there's actual movement (not just status quo)
            movement_verbs = ["靠近", "离开", "表白", "拒绝", "接受", "误会", "和好"]
            has_movement = any(verb in content for verb in movement_verbs)
            if not has_movement:
                findings.append(self._finding(
                    "info",
                    "STATIC_RELATIONSHIP",
                    "检测到感情线但缺少关系推进",
                    "在感情场景中加入关系状态变化",
                ))

        score = self._compute_score(findings)
        passed = not any(f.severity == "blocking" for f in findings)

        return EditorLensReport(
            lens_type=self.lens_type,
            passed=passed,
            score=score,
            findings=findings,
            summary=f"角色检查: {len(findings)} 个问题",
        )
