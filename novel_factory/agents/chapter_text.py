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
