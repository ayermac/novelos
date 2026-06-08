"""Publish-time title validation guard."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_BAD_ENDINGS = ("的", "了", "和", "与", "及", "之", "在", "将", "把", "被", "对", "向", "中", "上", "下", "无")
_OPEN_TO_CLOSE = {"「": "」", "『": "』", "“": "”", "《": "》", "（": "）", "(": ")"}
_GENERIC_KEYWORDS = {"第一章", "第二章", "第三章", "第四章", "第五章", "第章"}


@dataclass
class TitleGuardResult:
    """Result for publish-time title validation."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "evidence": self.evidence,
        }


def _strip_heading(content: str) -> str:
    lines = [line.strip() for line in (content or "").splitlines()]
    if lines and re.match(r"^第[一二三四五六七八九十百千万\d]+章", lines[0]):
        return "\n".join(lines[1:]).strip()
    return content or ""


def validate_publish_title(title: str | None, content: str | None = None) -> TitleGuardResult:
    """Validate a chapter title before publication.

    This guard is intentionally stricter than advisory continuity diagnosis:
    malformed, truncated, or body-detached titles are publication defects.
    """
    normalized = str(title or "").strip()
    content_body = _strip_heading(content or "")
    issues: list[str] = []
    suggestions: list[str] = []
    evidence: dict[str, Any] = {
        "title": normalized,
        "title_length": len(normalized),
        "keyword_match": True,
        "unclosed_pairs": [],
    }

    if not normalized:
        issues.append("标题缺失：发布前必须有章节标题。")
        suggestions.append("生成一个概括本章核心事件或爽点兑现的标题。")
    elif len(normalized) < 3:
        issues.append(f"标题过短：「{normalized}」疑似截断。")
        suggestions.append("补全标题，使其能概括本章核心事件。")
    elif len(normalized) > 32:
        issues.append(f"标题过长：「{normalized}」超过 32 个字符。")
        suggestions.append("压缩标题，只保留核心事件、冲突或卖点。")

    if "\n" in normalized or "\r" in normalized:
        issues.append("标题包含换行，疑似混入正文片段。")
        suggestions.append("仅保留单行章节标题。")

    if normalized.endswith(_BAD_ENDINGS):
        issues.append(f"标题疑似截断：「{normalized}」以残缺字结尾。")
        suggestions.append("补全标题结尾，避免以虚词或残缺词收尾。")

    unclosed: list[str] = []
    for open_char, close_char in _OPEN_TO_CLOSE.items():
        if normalized.count(open_char) != normalized.count(close_char):
            unclosed.append(open_char + close_char)
    if unclosed:
        evidence["unclosed_pairs"] = unclosed
        issues.append(f"标题括号或引号未闭合：{', '.join(unclosed)}。")
        suggestions.append("修正标题中的括号、书名号或引号。")

    keywords = re.findall(r"[\u4e00-\u9fff]{2,8}", normalized)
    mismatches: list[str] = []
    if content_body:
        for keyword in keywords[:4]:
            if keyword in _GENERIC_KEYWORDS:
                continue
            if keyword not in content_body:
                mismatches.append(keyword)
    if mismatches:
        evidence["keyword_match"] = False
        evidence["mismatched_keywords"] = mismatches
        issues.append(f"标题与正文脱节：标题关键词「{'/'.join(mismatches)}」未在正文中出现。")
        suggestions.append("修正标题或正文，确保标题承诺在正文中兑现。")

    return TitleGuardResult(
        passed=not issues,
        issues=issues,
        suggestions=suggestions,
        evidence=evidence,
    )
