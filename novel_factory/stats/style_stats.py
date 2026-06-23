"""StyleStats — pure code style statistics.

v6.10.13: Inspired by ainovel-cli's StyleStats design.
Computes deterministic style statistics without LLM calls.
Statistics are facts; interpretation is left to LLM.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StyleStatsResult:
    """Style statistics result."""

    # AI tic counts
    ai_tic_counts: dict[str, dict[str, Any]] = field(default_factory=dict)

    # High frequency phrases
    high_freq_phrases: list[dict[str, Any]] = field(default_factory=list)

    # Repeated sentences across chapters
    repeated_sentences: list[dict[str, Any]] = field(default_factory=list)

    # Ending patterns
    ending_patterns: dict[str, Any] = field(default_factory=dict)

    # Opening time word rate
    opening_time_words: dict[str, Any] = field(default_factory=dict)

    # Title format consistency
    title_format: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ai_tic_counts": self.ai_tic_counts,
            "high_freq_phrases": self.high_freq_phrases,
            "repeated_sentences": self.repeated_sentences,
            "ending_patterns": self.ending_patterns,
            "opening_time_words": self.opening_time_words,
            "title_format": self.title_format,
        }


# ── AI Tic Patterns ──

AI_TIC_PATTERNS = {
    "correction": {
        "pattern": r"不是.{1,10}而是",
        "description": "矫正句（不是...而是...）",
    },
    "time_quantifier": {
        "pattern": r"[一二三四五六七八九十百千]+[息瞬刻]",
        "description": "计时量词（X息/X瞬/X刻）",
    },
    "simile": {
        "pattern": r"像[一这][样种]",
        "description": "明喻（像一样/像这种）",
    },
    "silence_beat": {
        "pattern": r"沉默[了着]",
        "description": "沉默节拍（沉默了/沉默着）",
    },
    "breath_held": {
        "pattern": r"屏[住着]呼吸",
        "description": "屏息（屏住呼吸/屏着呼吸）",
    },
    "eye_firm": {
        "pattern": r"目光.{0,2}[坚沉凝]",
        "description": "目光坚定/深沉/凝重",
    },
}

# ── Time Words ──

OPENING_TIME_WORDS = [
    "夜", "清晨", "黎明", "傍晚", "黄昏", "午后", "凌晨",
    "深夜", "拂晓", "破晓", "日出", "日落",
]


def compute_style_stats(
    chapters: list[str],
    titles: list[str] | None = None,
    min_chapters: int = 5,
) -> Optional[StyleStatsResult]:
    """Compute style statistics for a novel.

    Args:
        chapters: List of chapter texts.
        titles: List of chapter titles.
        min_chapters: Minimum chapters required for statistics.

    Returns:
        StyleStatsResult or None if too few chapters.
    """
    if len(chapters) < min_chapters:
        return None

    result = StyleStatsResult()

    # AI tic counts
    result.ai_tic_counts = _count_ai_tics(chapters)

    # High frequency phrases
    result.high_freq_phrases = _find_high_freq_phrases(chapters)

    # Repeated sentences
    result.repeated_sentences = _find_repeated_sentences(chapters)

    # Ending patterns
    result.ending_patterns = _analyze_ending_patterns(chapters)

    # Opening time words
    result.opening_time_words = _count_opening_time_words(chapters)

    # Title format
    if titles:
        result.title_format = _check_title_format(titles)

    return result


def _count_ai_tics(chapters: list[str]) -> dict[str, dict[str, Any]]:
    """Count AI style tics across all chapters."""
    counts = {}
    total_chapters = len(chapters)

    for name, config in AI_TIC_PATTERNS.items():
        pattern = config["pattern"]
        description = config["description"]

        total = 0
        for ch in chapters:
            total += len(re.findall(pattern, ch))

        counts[name] = {
            "description": description,
            "total": total,
            "per_chapter": round(total / total_chapters, 2) if total_chapters > 0 else 0,
        }

    return counts


def _find_high_freq_phrases(
    chapters: list[str],
    window: int = 20,
    min_length: int = 3,
    max_length: int = 6,
) -> list[dict[str, Any]]:
    """Find high frequency phrases (n-gram mining)."""
    # Use recent chapters window
    recent = chapters[-window:] if len(chapters) > window else chapters
    ngrams: Counter[str] = Counter()

    for ch in recent:
        # Extract n-grams
        for n in range(min_length, max_length + 1):
            for i in range(len(ch) - n + 1):
                phrase = ch[i:i + n]

                # Filter invalid phrases
                if not _is_valid_phrase(phrase):
                    continue

                ngrams[phrase] += 1

    # Calculate threshold: max(8, chapter_count / 2)
    threshold = max(8, len(recent) // 2)

    # Filter and sort
    results = []
    for phrase, count in ngrams.most_common():
        if count < threshold:
            break
        results.append({
            "phrase": phrase,
            "count": count,
            "threshold": threshold,
        })

    return results[:20]  # Limit to top 20


def _is_valid_phrase(phrase: str) -> bool:
    """Check if phrase is valid for n-gram mining."""
    # Must contain at least one Chinese character
    if not re.search(r"[\u4e00-\u9fff]", phrase):
        return False

    # Must not be all punctuation
    if re.match(r"^[\s\W]+$", phrase):
        return False

    # Must not contain common stopwords
    stopwords = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你"}
    if phrase in stopwords:
        return False

    return True


def _find_repeated_sentences(
    chapters: list[str],
    min_length: int = 12,
    min_occurrences: int = 3,
) -> list[dict[str, Any]]:
    """Find sentences repeated across multiple chapters."""
    # Extract sentences from each chapter
    chapter_sentences: list[set[str]] = []
    for ch in chapters:
        sentences = set()
        # Split by common sentence endings
        for sent in re.split(r"[。！？]", ch):
            sent = sent.strip()
            if len(sent) >= min_length:
                sentences.add(sent)
        chapter_sentences.append(sentences)

    # Find sentences appearing in multiple chapters
    sentence_chapters: dict[str, list[int]] = {}
    for i, sentences in enumerate(chapter_sentences):
        for sent in sentences:
            if sent not in sentence_chapters:
                sentence_chapters[sent] = []
            sentence_chapters[sent].append(i + 1)  # 1-based chapter numbers

    # Filter by minimum occurrences
    repeated = []
    for sent, chapter_list in sentence_chapters.items():
        if len(chapter_list) >= min_occurrences:
            repeated.append({
                "sentence": sent[:100] + ("..." if len(sent) > 100 else ""),
                "occurrences": len(chapter_list),
                "chapters": chapter_list[:10],  # Limit to first 10
            })

    # Sort by occurrences
    repeated.sort(key=lambda x: x["occurrences"], reverse=True)

    return repeated[:5]  # Limit to top 5


def _analyze_ending_patterns(chapters: list[str]) -> dict[str, Any]:
    """Analyze chapter ending patterns."""
    short_endings = 0
    ending_lengths = []

    for ch in chapters:
        # Get last paragraph
        paragraphs = ch.strip().split("\n")
        if not paragraphs:
            continue

        last_para = paragraphs[-1].strip()
        if not last_para:
            # Try second to last
            if len(paragraphs) > 1:
                last_para = paragraphs[-2].strip()

        if last_para:
            ending_lengths.append(len(last_para))
            # Short ending: less than 50 characters
            if len(last_para) < 50:
                short_endings += 1

    total = len(chapters)
    short_ratio = short_endings / total if total > 0 else 0

    # Calculate median ending length
    if ending_lengths:
        ending_lengths.sort()
        median_idx = len(ending_lengths) // 2
        median_length = ending_lengths[median_idx]
    else:
        median_length = 0

    return {
        "short_ending_count": short_endings,
        "short_ending_ratio": round(short_ratio, 3),
        "median_ending_length": median_length,
        "total_chapters": total,
    }


def _count_opening_time_words(chapters: list[str]) -> dict[str, Any]:
    """Count chapters starting with time words."""
    time_word_count = 0
    total = len(chapters)

    for ch in chapters:
        # Get first non-empty line
        lines = ch.strip().split("\n")
        first_line = ""
        for line in lines:
            first_line = line.strip()
            if first_line:
                break

        if first_line:
            # Remove markdown headers
            first_line = re.sub(r"^#+\s*", "", first_line)

            # Check if starts with time word
            for tw in OPENING_TIME_WORDS:
                if first_line.startswith(tw):
                    time_word_count += 1
                    break

    ratio = time_word_count / total if total > 0 else 0

    return {
        "time_word_count": time_word_count,
        "time_word_ratio": round(ratio, 3),
        "total_chapters": total,
    }


def _check_title_format(titles: list[str]) -> dict[str, Any]:
    """Check title format consistency."""
    # Check for "第N章" prefix pattern
    chapter_prefix_pattern = r"^第[一二三四五六七八九十百千\d]+[章回节卷幕]"
    has_prefix = 0
    no_prefix = 0
    mixed_formats = False

    for title in titles:
        if re.match(chapter_prefix_pattern, title):
            has_prefix += 1
        else:
            no_prefix += 1

    # Mixed format: both with and without prefix
    if has_prefix > 0 and no_prefix > 0:
        mixed_formats = True

    return {
        "has_prefix_count": has_prefix,
        "no_prefix_count": no_prefix,
        "mixed_formats": mixed_formats,
        "total_titles": len(titles),
    }


# ── Convenience function ──

class StyleStats:
    """Style statistics calculator."""

    def __init__(self, min_chapters: int = 5):
        self.min_chapters = min_chapters

    def compute(
        self,
        chapters: list[str],
        titles: list[str] | None = None,
    ) -> Optional[StyleStatsResult]:
        """Compute style statistics."""
        return compute_style_stats(chapters, titles, self.min_chapters)

    def compute_dict(
        self,
        chapters: list[str],
        titles: list[str] | None = None,
    ) -> Optional[dict[str, Any]]:
        """Compute style statistics as dictionary."""
        result = self.compute(chapters, titles)
        if result:
            return result.to_dict()
        return None
