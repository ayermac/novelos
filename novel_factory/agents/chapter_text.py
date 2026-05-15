"""Chapter text normalization helpers for generated prose."""

from __future__ import annotations

import re


def default_chapter_title(chapter_number: int) -> str:
    """Return the fallback display title for a chapter."""
    return f"第{chapter_number}章"


def first_content_line(content: str) -> str:
    """Return the first non-empty line from chapter content."""
    return next((line.strip() for line in str(content or "").splitlines() if line.strip()), "")


def is_chapter_heading(line: str, chapter_number: int) -> bool:
    """Return True when a line already looks like a chapter heading."""
    text = str(line or "").strip()
    if not text:
        return False
    return bool(
        re.match(rf"^第\s*{chapter_number}\s*章(?:\s|$|[：:、.-])", text)
        or re.match(r"^第[一二三四五六七八九十百千零〇两]+\s*章(?:\s|$|[：:、.-])", text)
    )


def ensure_chapter_heading(content: str, title: str | None, chapter_number: int) -> str:
    """Ensure generated chapter content starts with a chapter title line.

    The title is part of the readable/exportable novel text, not just metadata.
    If the model already wrote a heading, the content is returned unchanged.
    """
    text = str(content or "").strip()
    if not text:
        return text
    if is_chapter_heading(first_content_line(text), chapter_number):
        return text
    heading = str(title or "").strip() or default_chapter_title(chapter_number)
    return f"{heading}\n\n{text}"


def strip_chapter_heading(content: str, chapter_number: int, title: str | None = None) -> str:
    """Return chapter body text without the leading display heading.

    Generated chapter content is stored with a readable heading so exports and
    the editor look like an actual manuscript. Quality gates should evaluate
    only the prose body, otherwise a generated heading can mask short drafts or
    skew retry diagnostics.
    """
    text = str(content or "").strip()
    if not text:
        return text
    lines = text.splitlines()
    first_idx = next((idx for idx, line in enumerate(lines) if line.strip()), None)
    if first_idx is None:
        return ""
    first_line = lines[first_idx].strip()
    explicit_title = str(title or "").strip()
    if not is_chapter_heading(first_line, chapter_number) and first_line != explicit_title:
        return text
    body_lines = lines[:first_idx] + lines[first_idx + 1 :]
    return "\n".join(body_lines).strip()
