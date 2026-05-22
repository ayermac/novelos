"""Utilities for bounded real-LLM segmented generation."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TypeVar

T = TypeVar("T")


def chunk_items(items: list[T], *, size: int) -> Iterator[list[T]]:
    """Yield ordered item chunks with a positive fixed size."""
    chunk_size = max(1, int(size or 1))
    for index in range(0, len(items), chunk_size):
        yield items[index:index + chunk_size]


def chunk_text_by_paragraphs(text: str, *, soft_limit: int) -> Iterator[str]:
    """Chunk text by paragraph without splitting unless a paragraph is oversized."""
    limit = max(1, int(soft_limit or 1))
    paragraphs = [p.strip() for p in str(text or "").split("\n\n") if p.strip()]
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        next_len = len(paragraph) if not current else current_len + 2 + len(paragraph)
        if current and next_len > limit:
            yield "\n\n".join(current)
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len = next_len
    if current:
        yield "\n\n".join(current)
