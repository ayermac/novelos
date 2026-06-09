"""Publish-time title validation guard."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_BAD_ENDINGS = ("的", "了", "和", "与", "及", "之", "在", "将", "把", "被", "对", "向", "中", "上", "下", "无")
_OPEN_TO_CLOSE = {"「": "」", "『": "』", "“": "”", "《": "》", "（": "）", "(": ")"}
_GENERIC_KEYWORDS = {"第一章", "第二章", "第三章", "第四章", "第五章", "第章"}
_CHAPTER_PREFIX_RE = re.compile(r"^\s*第[\d一二三四五六七八九十百千万]+章[\s:：、.\-—_]*")
_CONNECTOR_SPLIT_RE = re.compile(r"[和与及]")
_SUSPICIOUS_POSSESSIVE_TAIL_RE = re.compile(r"^(.{2,8})[的之][\u4e00-\u9fffA-Za-z0-9]$")


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


@dataclass
class TitleRepairResult:
    """Deterministic metadata repair result for publish-time titles."""

    repaired: bool
    title: str | None = None
    content: str | None = None
    reason: str = ""
    guard: TitleGuardResult | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repaired": self.repaired,
            "title": self.title,
            "reason": self.reason,
            "guard": self.guard.to_dict() if self.guard else None,
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


def _first_content_line(content: str) -> str:
    return next((line.strip() for line in str(content or "").splitlines() if line.strip()), "")


def _is_chapter_heading(line: str, chapter_number: int) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    delimiter = r"(?:\s|$|[：:、.\-—（(【《])"
    return bool(
        re.match(rf"^第\s*{chapter_number}\s*章{delimiter}", text)
        or re.match(rf"^第[一二三四五六七八九十百千零〇两]+\s*章{delimiter}", text)
    )


def _clean_repair_suffix(value: str) -> str:
    text = semantic_title_text(str(value or "").strip())
    text = re.sub(r"^[\"'“”‘’《》【】\s]+|[\"'“”‘’《》【】\s]+$", "", text)
    text = re.split(r"[。！？!?；;，,\n\r]", text, maxsplit=1)[0].strip()
    text = re.sub(r"\s+", "", text)
    while text.endswith(_BAD_ENDINGS):
        text = text[:-1].strip()
    if len(text) < 2:
        return ""
    return text[:14]


def _is_bare_or_placeholder_title(title: str | None) -> bool:
    text = re.sub(r"\s+", "", str(title or "").strip())
    if not text:
        return True
    if any(marker in text for marker in ("待命名", "未命名", "占位")):
        return True
    return bool(re.fullmatch(r"第[\d一二三四五六七八九十百千万零〇两]+章节?", text))


def _format_candidate_title(suffix: str, chapter_number: int) -> str | None:
    cleaned = _clean_repair_suffix(suffix)
    if not cleaned:
        return None
    return f"第{chapter_number}章 {cleaned}"


def _replace_bad_heading(content: str, old_title: str | None, repaired_title: str, chapter_number: int) -> str:
    text = str(content or "")
    if not text.strip():
        return text

    lines = text.splitlines()
    first_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_index is None:
        return text

    first_line = lines[first_index].strip()
    old_normalized = str(old_title or "").strip()
    should_replace = first_line == old_normalized
    if not should_replace and _is_chapter_heading(first_line, chapter_number):
        should_replace = not validate_publish_title(first_line, text).passed
    if not should_replace:
        return text

    lines[first_index] = repaired_title
    return "\n".join(lines).strip()


def _repair_candidates(title: str | None, content: str | None, chapter_number: int) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(candidate: str | None, reason: str) -> None:
        if not candidate:
            return
        text = candidate.strip()
        if not text or text in seen:
            return
        seen.add(text)
        candidates.append((text, reason))

    first_line = _first_content_line(content or "")
    if _is_chapter_heading(first_line, chapter_number):
        add(first_line, "content_heading")

    semantic = semantic_title_text(str(title or "").strip())
    if _is_bare_or_placeholder_title(title):
        add(_format_candidate_title(first_line, chapter_number), "content_opening_for_bare_title")

    if semantic:
        add(_format_candidate_title(semantic, chapter_number), "cleaned_existing_title")

        possessive_tail = _SUSPICIOUS_POSSESSIVE_TAIL_RE.match(semantic)
        if possessive_tail:
            add(_format_candidate_title(possessive_tail.group(1), chapter_number), "possessive_tail_fragment")

        for part in _CONNECTOR_SPLIT_RE.split(semantic):
            add(_format_candidate_title(part, chapter_number), "connector_fragment")

        left_fragment = _CONNECTOR_SPLIT_RE.split(semantic, maxsplit=1)[0]
        if left_fragment != semantic:
            add(_format_candidate_title(left_fragment, chapter_number), "left_connector_fragment")

    return candidates


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


def repair_publish_title(
    title: str | None,
    content: str | None,
    chapter_number: int,
) -> TitleRepairResult:
    """Repair a publish title only when a deterministic safe candidate passes.

    This intentionally does not invent a new title. It only tries local metadata
    repairs that can be verified against the same publish guard: content heading,
    cleaned existing suffix, and connector fragments such as "倒计时与钾" →
    "倒计时". Arbitrary title/body mismatches continue to block publication.
    """
    original_guard = validate_publish_title(title, content)
    if original_guard.passed:
        return TitleRepairResult(
            repaired=False,
            title=str(title or "").strip(),
            content=content,
            reason="already_valid",
            guard=original_guard,
            evidence={"candidate_count": 0},
        )

    candidates = _repair_candidates(title, content, chapter_number)
    rejected: list[dict[str, Any]] = []
    for candidate, reason in candidates:
        guard = validate_publish_title(candidate, content)
        if guard.passed:
            return TitleRepairResult(
                repaired=True,
                title=candidate,
                content=_replace_bad_heading(content or "", title, candidate, chapter_number),
                reason=reason,
                guard=guard,
                evidence={
                    "original_title": str(title or "").strip(),
                    "original_issues": original_guard.issues,
                    "candidate_count": len(candidates),
                },
            )
        rejected.append({
            "title": candidate,
            "reason": reason,
            "issues": guard.issues,
        })

    return TitleRepairResult(
        repaired=False,
        title=None,
        content=content,
        reason="no_safe_candidate",
        guard=original_guard,
        evidence={
            "original_title": str(title or "").strip(),
            "candidate_count": len(candidates),
            "rejected_candidates": rejected[:5],
        },
    )
