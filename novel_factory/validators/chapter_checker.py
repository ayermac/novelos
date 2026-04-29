"""Chapter checker validator — word count and basic format validation.

v1 implements:
- Unified word count function (count_words)
- Word count range check (min/max)
- Non-empty content check

v5.3.0 adds:
- Quality gate word count enforcement (Author/Polisher < 0.85 = fail, Editor < 0.9 = no pass)
- word_target derivation from instruction or project settings
"""

from __future__ import annotations

from ..config.settings import Settings


# Default thresholds (can be overridden via config)
DEFAULT_MIN_WORDS = 500
DEFAULT_MAX_WORDS = 8000

# v5.3.0: Quality gate thresholds
QUALITY_GATE_AUTHOR_THRESHOLD = 0.85  # Author/Polisher: content < word_target * 0.85 = fail
QUALITY_GATE_EDITOR_THRESHOLD = 0.90  # Editor: content < word_target * 0.9 = no pass


def count_words(text: str | None) -> int:
    """Count words in text. For Chinese, uses character count as approximation.

    This is the single canonical word count function for the entire factory.
    All modules must use this function instead of len(content).

    Returns 0 for None or empty content to avoid TypeError in error-path tests.
    """
    if text is None:
        return 0
    return len(text)


def normalize_declared_word_count(output: dict) -> dict:
    """Return output with word_count recomputed from content.

    Real LLMs often return a guessed ``word_count`` that is far from the
    actual generated text length. The system should treat the text as the
    source of truth and keep the mismatch validator for external/raw payloads.
    """
    normalized = dict(output)
    content = normalized.get("content")
    if content is not None:
        normalized["word_count"] = count_words(content)
    return normalized


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


def check_word_count_quality_gate(
    content: str,
    word_target: int,
    agent_type: str,
) -> tuple[bool, str]:
    """Check word count against quality gate threshold.

    v5.3.0: Implements strict word count quality gates.

    Args:
        content: Chapter text content.
        word_target: Target word count for this chapter.
        agent_type: Agent type ("author", "polisher", or "editor").

    Returns:
        Tuple of (passed, message).
        - passed: True if word count meets threshold.
        - message: Description of the result.
    """
    word_count = count_words(content)

    if word_count == 0:
        return False, "内容为空"

    # Determine threshold based on agent type
    if agent_type in ("author", "polisher"):
        threshold = QUALITY_GATE_AUTHOR_THRESHOLD
    elif agent_type == "editor":
        threshold = QUALITY_GATE_EDITOR_THRESHOLD
    else:
        # Unknown agent type, use strict threshold
        threshold = QUALITY_GATE_EDITOR_THRESHOLD

    minimum_required = int(word_target * threshold)

    if word_count < minimum_required:
        shortfall = minimum_required - word_count
        return False, f"字数未达标: {word_count} < {minimum_required} (目标 {word_target} × {threshold:.0%})，差 {shortfall} 字"

    return True, f"字数达标: {word_count} >= {minimum_required}"


def derive_word_target(
    instruction: dict | None,
    project: dict,
) -> int:
    """Derive word_target from instruction or project settings.

    v5.3.0: Provides word_target for quality gate checks.

    Args:
        instruction: Instruction dict for the chapter, or None.
        project: Project dict with target_words and total_chapters_planned.

    Returns:
        Derived word_target, minimum 2000.
    """
    # First check if instruction has explicit word_target
    if instruction and instruction.get("word_target"):
        return max(instruction["word_target"], 2000)

    # Derive from project settings
    target_words = project.get("target_words", 0)
    total_chapters = project.get("total_chapters_planned", 0)

    if target_words and total_chapters:
        derived = target_words // total_chapters
        return max(derived, 2000)

    # Default fallback
    return 2500


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
