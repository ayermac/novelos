"""Chapter checker validator — word count and basic format validation.

v1 implements:
- Unified word count function (count_words)
- Word count range check (min/max)
- Non-empty content check
"""

from __future__ import annotations

from ..config.settings import Settings


# Default thresholds (can be overridden via config)
DEFAULT_MIN_WORDS = 500
DEFAULT_MAX_WORDS = 8000


def count_words(text: str) -> int:
    """Count words in text. For Chinese, uses character count as approximation.

    This is the single canonical word count function for the entire factory.
    All modules must use this function instead of len(content).
    """
    return len(text)


def check_word_count(
    content: str,
    min_words: int = DEFAULT_MIN_WORDS,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[str]:
    """Check if content word count is within acceptable range.

    Args:
        content: Chapter text content.
        min_words: Minimum acceptable word count.
        max_words: Maximum acceptable word count.

    Returns:
        List of violation messages. Empty list means no violations.
    """
    violations: list[str] = []
    word_count = count_words(content)

    if word_count == 0:
        violations.append("内容为空")
    elif word_count < min_words:
        violations.append(f"字数不足: {word_count} < {min_words}")
    elif word_count > max_words:
        violations.append(f"字数超标: {word_count} > {max_words}")

    return violations


def validate_chapter_output(output: dict) -> list[str]:
    """Validate Author/Polisher output for chapter-level constraints.

    Checks:
    - content is non-empty
    - word_count matches actual content length (if provided)
    - word count within range

    Returns:
        List of violation messages.
    """
    violations: list[str] = []

    content = output.get("content", "")
    if not content:
        violations.append("content 为空")
        return violations

    # Check actual word count matches declared word_count (Author only)
    declared_wc = output.get("word_count")
    if declared_wc is not None:
        actual_wc = count_words(content)
        # Allow 10% tolerance
        if abs(actual_wc - declared_wc) > declared_wc * 0.1:
            violations.append(
                f"word_count 不匹配: 声明 {declared_wc}, 实际 {actual_wc}"
            )

    # Word count range check
    violations.extend(check_word_count(content))

    return violations
