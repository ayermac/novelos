"""Mystery Editor Lens — clue threading and mystery management.

Checks mystery/clue debt, reveal pacing, and terminology overload.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...models.chapter_contracts import EditorLensReport
from .base_lens import BaseEditorLens

logger = logging.getLogger(__name__)


class MysteryEditorLens(BaseEditorLens):
    """Checks mystery management: clue debt, reveal pacing, terminology."""

    lens_type = "mystery"

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
                summary="内容过短，跳过悬疑检查",
            )

        # Check mystery ledger context
        ledger_context = context.get("ledger_context", {})
        mystery_ledger = ledger_context.get("mystery_reveal", {})
        
        if mystery_ledger:
            entries = mystery_ledger.get("entries", [])
            active_mysteries = [e for e in entries if e.get("status") in ("introduced", "deepening")]
            
            # Warn if too many active mysteries
            if len(active_mysteries) > 5:
                findings.append(self._finding(
                    "warning",
                    "MYSTERY_OVERLOAD",
                    f"当前有 {len(active_mysteries)} 条未解悬疑，读者可能感到疲惫",
                    "在后续章节中解决部分悬疑线索",
                ))

        # Check for new mystery introduction without resolution
        mystery_introduce = ["谜", "疑问", "不解", "困惑", "不知道为什么"]
        mystery_resolve = ["真相", "答案", "原来", "揭示", "解开"]
        
        introduce_count = sum(content.count(w) for w in mystery_introduce)
        resolve_count = sum(content.count(w) for w in mystery_resolve)
        
        if introduce_count > 3 and resolve_count == 0:
            findings.append(self._finding(
                "info",
                "MYSTERY_IMBALANCE",
                "本章引入较多悬疑但未解决任何",
                "平衡悬疑引入与揭示节奏",
            ))

        # Check for terminology/jargon overload
        # Count technical terms that might confuse readers
        jargon_patterns = re.findall(r"[A-Z]{2,}|[a-z]+(?:术|法|功|诀|经|典)", content)
        if len(jargon_patterns) > 10 and len(content) < 3000:
            findings.append(self._finding(
                "warning",
                "JARGON_OVERLOAD",
                f"检测到 {len(jargon_patterns)} 个术语/专有名词，可能造成阅读障碍",
                "减少术语密度，确保新术语有解释上下文",
            ))

        # Check chapter brief mystery actions
        chapter_brief = context.get("chapter_brief", {})
        if chapter_brief:
            tier2 = chapter_brief.get("tier2", {})
            mystery_actions = tier2.get("mystery_actions", [])
            if mystery_actions:
                # Check if brief mystery actions are addressed in content
                addressed = 0
                for action in mystery_actions:
                    if isinstance(action, str) and len(action) > 2:
                        if any(keyword in content for keyword in action.split()[:2]):
                            addressed += 1
                if addressed < len(mystery_actions) * 0.5 and len(mystery_actions) > 1:
                    findings.append(self._finding(
                        "info",
                        "BRIEF_MYSTERY_PARTIAL",
                        f"章节brief要求的悬疑动作仅部分体现 ({addressed}/{len(mystery_actions)})",
                        "确保brief中的悬疑动作在正文中有体现",
                    ))

        score = self._compute_score(findings)
        passed = not any(f.severity == "blocking" for f in findings)

        return EditorLensReport(
            lens_type=self.lens_type,
            passed=passed,
            score=score,
            findings=findings,
            summary=f"悬疑检查: {len(findings)} 个问题",
        )
