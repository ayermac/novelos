"""Remove editorial/diagnostic meta text from generated chapter prose."""

from __future__ import annotations

import re


_STRONG_META_MARKERS = (
    "章末钩子强度不足",
    "钩子强度不足",
    "当前钩子仅为",
    "质量诊断建议",
    "诊断建议",
    "修改建议",
    "审核建议",
    "润色建议",
    "此处未扩写",
    "保持原样",
)

_CONTEXT_META_MARKERS = (
    "章末钩子",
    "当前钩子",
    "钩子",
    "危机感",
    "评分",
    "质量",
    "诊断",
    "审核",
    "润色",
    "返修",
    "扩写",
    "正文",
    "原样",
)


def _strip_outer_parentheses(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    if len(stripped) >= 2 and (
        (stripped.startswith("（") and stripped.endswith("）"))
        or (stripped.startswith("(") and stripped.endswith(")"))
    ):
        return stripped[1:-1].strip(), True
    return stripped, False


def is_editorial_meta_paragraph(paragraph: str) -> bool:
    """Return True when a paragraph is an editorial note, not story prose."""
    text = re.sub(r"\s+", "", str(paragraph or ""))
    if not text:
        return False
    if len(text) > 900:
        return False

    bracketed_note = bool(re.match(r"^【?(质量诊断建议|诊断建议|修改建议|审核建议|润色建议)】?", text))
    if bracketed_note:
        return True

    inner, parenthesized = _strip_outer_parentheses(str(paragraph or ""))
    compact_inner = re.sub(r"\s+", "", inner)
    if not parenthesized:
        return False

    if any(marker in compact_inner for marker in _STRONG_META_MARKERS):
        return True

    has_suggestion = "建议：" in compact_inner or "建议:" in compact_inner or compact_inner.startswith("建议")
    has_context = any(marker in compact_inner for marker in _CONTEXT_META_MARKERS)
    return has_suggestion and has_context


def strip_editorial_meta_blocks(content: str) -> tuple[str, list[str]]:
    """Strip whole paragraphs that are clearly editorial diagnostics.

    The filter is deliberately conservative: it only removes standalone
    bracketed/parenthesized advisory paragraphs or explicit diagnostic notes,
    so normal in-story uses like “系统建议忽略” are preserved.
    """
    if not content:
        return content, []

    content_text = str(content)
    inline_removed: list[str] = []

    def _remove_inline_parenthesized(match: re.Match[str]) -> str:
        candidate = match.group(0)
        if is_editorial_meta_paragraph(candidate):
            inline_removed.append(candidate.strip())
            return ""
        return candidate

    content_text = re.sub(r"（[^（）]{1,900}）|\([^()]{1,900}\)", _remove_inline_parenthesized, content_text)

    paragraphs = re.split(r"\n\s*\n", content_text)
    kept: list[str] = []
    removed: list[str] = list(inline_removed)
    for paragraph in paragraphs:
        if is_editorial_meta_paragraph(paragraph):
            removed.append(paragraph.strip())
        else:
            kept.append(paragraph.strip())

    if not removed:
        return content, []

    cleaned = "\n\n".join(part for part in kept if part).strip()
    return cleaned, removed
