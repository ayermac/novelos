"""InfoDumpDetector: detect lore dumps, exposition paragraphs, and info-dump patterns.

Deterministic validator — no LLM calls.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class InfoDumpDetector(ValidatorSkill):
    """Detect info-dump patterns: lore exposition, setting narration, consecutive explanation."""

    skill_id = "info-dump-detector"
    version = "1.0.0"

    # Explicit lore-dump opening patterns
    LORE_PATTERNS: list[str] = [
        r"这个世界(是|有|存在)[^。！？]{10,80}",
        r"在这个(世界|时代|地方)[^。！？]{10,80}",
        r"所谓[^。！？]{10,60}(是|指)",
        r"简单来说[^。！？]{10,60}",
        r"说白了[^。！？]{10,60}",
    ]

    # Phrases that signal author explaining instead of showing
    EXPLAIN_PHRASES: list[str] = [
        "也就是说",
        "换句话说",
        "换言之",
        "这意味着",
        "这说明",
        "这表明",
    ]

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text") or payload.get("content", "")
        if not text:
            return {"ok": True, "error": None, "data": {"score": 100, "findings": []}}

        total_chars = max(len(text), 1)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        findings: list[dict[str, Any]] = []
        lore_count = 0
        explain_count = 0
        dump_paragraphs = 0

        # 1. Lore-dump patterns
        for pattern in self.LORE_PATTERNS:
            matches = re.findall(pattern, text)
            lore_count += len(matches)

        # 2. Explanation phrases
        for phrase in self.EXPLAIN_PHRASES:
            explain_count += text.count(phrase)

        # 3. Consecutive pure-exposition paragraphs
        # A paragraph is info-dump-like if it has no dialogue and >80% declarative sentences
        for para in paragraphs:
            if not para:
                continue
            has_dialogue = bool(re.search(r'["\u201c\u300c\u300e].*?["\u201d\u300d\u300f]', para))
            if has_dialogue:
                continue
            sentences = [s.strip() for s in re.split(r'[。！？]', para) if s.strip()]
            if len(sentences) >= 3:
                # Heuristic: 3+ consecutive sentences without dialogue or action verbs
                action_verbs = [
                    "走", "跑", "站", "坐", "看", "听", "说", "拿", "推", "拉", "打", "踢", "跳", "爬",
                    "击", "撞", "错", "绕", "靠", "玩", "翻", "抬", "扫", "问", "开", "回答",
                    "移动", "后退", "前进", "转身", "侧头", "攥紧", "逼近", "弥漫", "回荡",
                ]
                action_count = sum(1 for s in sentences for v in action_verbs if v in s)
                if action_count < len(sentences) * 0.3:
                    dump_paragraphs += 1

        total_dumps = lore_count + explain_count + dump_paragraphs

        # Score: 100 = none, 0 = heavy
        score = max(0, 100 - total_dumps * 15)

        if lore_count > 0:
            findings.append({
                "code": "LORE_DUMP",
                "severity": "medium" if lore_count >= 2 else "info",
                "message": f"检测到 {lore_count} 处设定旁白式解释",
                "evidence": {"count": lore_count},
                "suggestion": "通过角色动作或对话展现设定，减少旁白解释",
            })

        if explain_count > 0:
            findings.append({
                "code": "EXPLAIN_PHRASE",
                "severity": "info",
                "message": f"检测到 {explain_count} 处解释性短语",
                "evidence": {"count": explain_count},
                "suggestion": "删除'也就是说/换句话说'等解释性插入语",
            })

        if dump_paragraphs > 0:
            findings.append({
                "code": "EXPOSITION_PARAGRAPH",
                "severity": "info",
                "message": f"检测到 {dump_paragraphs} 处纯说明段落（无动作/对白）",
                "evidence": {"count": dump_paragraphs},
                "suggestion": "在连续说明中插入角色动作或环境反馈",
            })

        return {
            "ok": True,
            "error": None,
            "data": {
                "score": round(score, 1),
                "lore_count": lore_count,
                "explain_count": explain_count,
                "dump_paragraphs": dump_paragraphs,
                "findings": findings,
            },
        }
