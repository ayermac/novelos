"""Publish-time title validation guard."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_BAD_ENDINGS = ("的", "了", "和", "与", "及", "之", "在", "将", "把", "被", "对", "向", "中", "上", "下", "无")
_OPEN_TO_CLOSE = {"「": "」", "『": "』", "“": "”", "《": "》", "（": "）", "(": ")"}
_GENERIC_KEYWORDS = {"第一章", "第二章", "第三章", "第四章", "第五章", "第章"}
_CHAPTER_PREFIX_RE = re.compile(r"^\s*第[\d一二三四五六七八九十百千万]+章[\s:：、.\-—_]*")


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


def semantic_title_text(title: str) -> str:
    """Return title text without a leading chapter number prefix."""
    return _CHAPTER_PREFIX_RE.sub("", title or "").strip()


def _bigrams(text: str) -> list[str]:
    return [text[index:index + 2] for index in range(max(0, len(text) - 1))]


def title_keyword_covered(keyword: str, content_body: str) -> tuple[bool, dict[str, Any]]:
    """Return whether a title keyword is represented in the chapter body.

    Titles are often compact promises ("喂养倒计时") while the body realizes
    them with nearby but non-contiguous terms ("喂养" + "倒计时").  Exact
    phrase matching is still preferred, but publish should not be blocked
    when the meaningful bigrams are substantially covered.
    """
    if keyword in content_body:
        return True, {"keyword": keyword, "match_type": "exact", "coverage": 1.0}

    if len(keyword) < 4:
        return False, {"keyword": keyword, "match_type": "none", "coverage": 0.0}

    grams = _bigrams(keyword)
    if not grams:
        return False, {"keyword": keyword, "match_type": "none", "coverage": 0.0}

    matched = [gram for gram in grams if gram in content_body]
    coverage = len(matched) / len(grams)
    covered = coverage >= 0.6 and len(matched) >= 2
    return covered, {
        "keyword": keyword,
        "match_type": "bigram_coverage" if covered else "none",
        "coverage": round(coverage, 3),
        "matched_bigrams": matched,
    }


def validate_publish_title(title: str | None, content: str | None = None) -> TitleGuardResult:
    """Validate a chapter title before publication.

    This guard is intentionally stricter than advisory continuity diagnosis:
    malformed, truncated, or body-detached titles are publication defects.
    """
    normalized = str(title or "").strip()
    semantic_title = semantic_title_text(normalized)
    content_body = _strip_heading(content or "")
    issues: list[str] = []
    suggestions: list[str] = []
    evidence: dict[str, Any] = {
        "title": normalized,
        "semantic_title": semantic_title,
        "title_length": len(normalized),
        "keyword_match": True,
        "keyword_evidence": [],
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

    if normalized and not semantic_title:
        issues.append("标题只有章节编号，缺少核心事件或卖点。")
        suggestions.append("在章节编号后补充本章核心事件、冲突或爽点。")

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

    keywords = re.findall(r"[\u4e00-\u9fff]{2,8}", semantic_title)
    mismatches: list[str] = []
    if content_body:
        for keyword in keywords[:4]:
            if keyword in _GENERIC_KEYWORDS:
                continue
            covered, keyword_evidence = title_keyword_covered(keyword, content_body)
            evidence["keyword_evidence"].append(keyword_evidence)
            if not covered:
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
