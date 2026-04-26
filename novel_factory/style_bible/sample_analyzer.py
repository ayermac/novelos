"""v4.2 Style Sample Analyzer — pure rule-based text analysis.

Extracts structural style features from sample text without LLM calls.
Does NOT save full source text. Does NOT call external APIs.
Does NOT imitate any author.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# ── Internal word lists (small, not exhaustive) ────────────────

_ACTION_WORDS = frozenset({
    "冲", "跑", "跳", "打", "踢", "推", "拉", "抓", "砍", "刺",
    "闪", "退", "追", "逃", "挡", "挥", "砸", "扔", "拍", "握",
    "跃", "翻", "撞", "劈", "扫", "射", "击", "扑", "撕", "夺",
})

_PSYCHOLOGY_WORDS = frozenset({
    "想", "觉得", "怀疑", "害怕", "担心", "犹豫", "恐惧", "愤怒",
    "悲伤", "焦虑", "绝望", "希望", "期待", "怀念", "愧疚", "嫉妒",
    "震惊", "困惑", "无奈", "释然", "心动", "紧张", "不安", "忐忑",
})

_DESCRIPTION_WORDS = frozenset({
    "如同", "仿佛", "宛如", "像是", "映入", "只见", "放眼",
    "笼罩", "弥漫", "闪烁", "照耀", "倒映", "铺展", "绵延",
    "苍翠", "辽阔", "空旷", "幽暗", "阴沉", "明亮", "寂静",
})

_TONE_KEYWORDS_POOL = {
    "紧张": ["紧张", "紧迫", "急促", "危机", "险境", "对峙"],
    "克制": ["克制", "冷静", "沉默", "隐忍", "压抑", "收敛"],
    "悬疑": ["悬疑", "谜团", "诡异", "线索", "真相", "暗藏"],
    "热血": ["热血", "激昂", "怒吼", "冲锋", "燃烧", "爆发"],
    "温情": ["温情", "温暖", "微笑", "柔和", "守护", "珍惜"],
    "沉重": ["沉重", "压抑", "苍凉", "悲壮", "惨烈", "沉重"],
    "轻快": ["轻快", "活泼", "俏皮", "灵动", "欢脱", "爽朗"],
    "冷峻": ["冷峻", "冰冷", "漠然", "锐利", "审视", "冷酷"],
}

# AI-trace indicator patterns (simplified, no LLM)
_AI_TRACE_PATTERNS = [
    r"不禁(?![得])", r"竟然", r"居然", r"缓缓地", r"轻轻地",
    r"深深地", r"默默地", r"微微一笑", r"嘴角上扬", r"眼中闪过",
    r"心中暗想", r"不由得", r"恍然大悟", r"若有所思", r"心生一计",
]


def analyze_style_sample_text(text: str) -> dict[str, Any]:
    """Analyze a text sample and return metrics + analysis.

    Returns:
        Envelope with 'metrics' and 'analysis' dicts.
        Returns ok=False for empty/invalid input.
    """
    if not text or not text.strip():
        return {
            "ok": False,
            "error": "Empty text provided for analysis",
            "data": {},
        }

    text = text.strip()

    # Basic counts
    char_count = len(text)
    paragraphs = _split_paragraphs(text)
    paragraph_count = len(paragraphs)
    sentences = _split_sentences(text)
    sentence_count = max(len(sentences), 1)

    # Sentence length stats
    sentence_lengths = [len(s) for s in sentences if s.strip()]
    avg_sentence_length = (
        sum(sentence_lengths) / len(sentence_lengths)
        if sentence_lengths else 0.0
    )
    avg_paragraph_length = char_count / max(paragraph_count, 1)

    # Ratios
    dialogue_ratio = estimate_dialogue_ratio(text)
    ratios = estimate_action_description_psychology_ratio(text)
    action_ratio = ratios["action_ratio"]
    description_ratio = ratios["description_ratio"]
    psychology_ratio = ratios["psychology_ratio"]

    # Punctuation density
    punct_count = sum(1 for c in text if c in "。，！？、；：""''《》—……")
    punctuation_density = punct_count / max(char_count, 1)

    # Sentence length distribution
    short_sentences = sum(1 for sl in sentence_lengths if 0 < sl <= 15)
    long_sentences = sum(1 for sl in sentence_lengths if sl > 60)
    short_sentence_ratio = short_sentences / max(len(sentence_lengths), 1)
    long_sentence_ratio = long_sentences / max(len(sentence_lengths), 1)

    # AI trace risk
    ai_trace_risk = _estimate_ai_trace_risk(text)

    # Tone keywords
    tone_keywords = extract_tone_keywords(text)

    # Rhythm notes
    rhythm_notes = _build_rhythm_notes(
        avg_sentence_length, dialogue_ratio, action_ratio,
        short_sentence_ratio, long_sentence_ratio,
    )

    metrics = {
        "char_count": char_count,
        "paragraph_count": paragraph_count,
        "sentence_count": sentence_count,
        "avg_sentence_length": round(avg_sentence_length, 1),
        "avg_paragraph_length": round(avg_paragraph_length, 1),
        "dialogue_ratio": round(dialogue_ratio, 3),
        "action_ratio": round(action_ratio, 3),
        "description_ratio": round(description_ratio, 3),
        "psychology_ratio": round(psychology_ratio, 3),
        "punctuation_density": round(punctuation_density, 3),
        "short_sentence_ratio": round(short_sentence_ratio, 3),
        "long_sentence_ratio": round(long_sentence_ratio, 3),
        "ai_trace_risk": ai_trace_risk,
        "tone_keywords": tone_keywords,
        "rhythm_notes": rhythm_notes,
    }

    analysis = build_sample_analysis_summary(metrics)

    return {
        "ok": True,
        "error": None,
        "data": {
            "metrics": metrics,
            "analysis": analysis,
        },
    }


def extract_tone_keywords(text: str) -> list[str]:
    """Extract tone/氛围 keywords from text based on word frequency.

    Does NOT extract author names or work titles.
    """
    found_scores: dict[str, int] = {}
    for tone, keywords in _TONE_KEYWORDS_POOL.items():
        for kw in keywords:
            count = text.count(kw)
            if count > 0:
                found_scores[tone] = found_scores.get(tone, 0) + count

    # Return top 3 tones by frequency
    sorted_tones = sorted(found_scores.items(), key=lambda x: x[1], reverse=True)
    return [tone for tone, _ in sorted_tones[:3]]


def estimate_dialogue_ratio(text: str) -> float:
    """Estimate dialogue proportion by counting quoted segments.

    Uses Chinese and English quotation marks.
    """
    # Chinese dialogue: 「...」or "..." or "..."
    # Also count colon-led dialogue: 他道："..."
    dialogue_chars = 0
    # Match Chinese quotes
    for m in re.finditer(r"[「\"].*?[」\"]", text, re.DOTALL):
        dialogue_chars += len(m.group())
    # Match "..." style
    for m in re.finditer(r"\u201c.*?\u201d", text, re.DOTALL):
        dialogue_chars += len(m.group())

    total = max(len(text), 1)
    return min(dialogue_chars / total, 1.0)


def estimate_action_description_psychology_ratio(text: str) -> dict[str, float]:
    """Estimate action/description/psychology ratios using word lists.

    Returns dict with action_ratio, description_ratio, psychology_ratio.
    Ratios are approximate (0.0-1.0) and may not sum to 1.0.
    """
    action_hits = sum(text.count(w) for w in _ACTION_WORDS)
    desc_hits = sum(text.count(w) for w in _DESCRIPTION_WORDS)
    psych_hits = sum(text.count(w) for w in _PSYCHOLOGY_WORDS)
    total_hits = action_hits + desc_hits + psych_hits

    if total_hits == 0:
        return {
            "action_ratio": 0.0,
            "description_ratio": 0.0,
            "psychology_ratio": 0.0,
        }

    return {
        "action_ratio": action_hits / total_hits,
        "description_ratio": desc_hits / total_hits,
        "psychology_ratio": psych_hits / total_hits,
    }


def build_sample_analysis_summary(metrics: dict) -> dict[str, Any]:
    """Build a human-readable analysis summary from metrics.

    No LLM calls. Pure rule-based.
    """
    style_suggestions = []
    avg_sent = metrics.get("avg_sentence_length", 0)
    dialogue = metrics.get("dialogue_ratio", 0)
    action = metrics.get("action_ratio", 0)
    long_ratio = metrics.get("long_sentence_ratio", 0)

    if avg_sent > 40:
        style_suggestions.append("句式偏长，可适当缩短以提升节奏感")
    elif avg_sent < 15:
        style_suggestions.append("句式偏短，适合快节奏场景")
    else:
        style_suggestions.append("句长中等，节奏平稳")

    if dialogue > 0.3:
        style_suggestions.append("对话比例较高，适合推进情节")
    elif dialogue < 0.1:
        style_suggestions.append("对话比例低，偏叙述风格")

    if action > 0.5:
        style_suggestions.append("动作描写突出，适合战斗/冲突场景")
    elif action < 0.2:
        style_suggestions.append("动作描写较少，可加强行动推动")

    if long_ratio > 0.25:
        style_suggestions.append("超长句偏多，建议拆分长句")

    return {
        "rhythm_notes": metrics.get("rhythm_notes", []),
        "style_suggestions": style_suggestions,
        "tone_keywords": metrics.get("tone_keywords", []),
    }


# ── Internal helpers ───────────────────────────────────────────


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences by Chinese/English sentence-end punctuation."""
    parts = re.split(r"[。！？!?]+", text)
    return [p.strip() for p in parts if p.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs by blank lines or newlines."""
    if "\n\n" in text:
        parts = text.split("\n\n")
    else:
        parts = text.split("\n")
    return [p.strip() for p in parts if p.strip()]


def _estimate_ai_trace_risk(text: str) -> str:
    """Estimate AI trace risk level based on pattern matching.

    Returns 'low', 'medium', or 'high'.
    No LLM calls.
    """
    match_count = 0
    for pattern in _AI_TRACE_PATTERNS:
        matches = re.findall(pattern, text)
        match_count += len(matches)

    # Normalize by text length (per 1000 chars)
    char_count = max(len(text), 1)
    density = match_count / (char_count / 1000)

    if density > 8:
        return "high"
    elif density > 3:
        return "medium"
    else:
        return "low"


def _build_rhythm_notes(
    avg_sentence_length: float,
    dialogue_ratio: float,
    action_ratio: float,
    short_sentence_ratio: float,
    long_sentence_ratio: float,
) -> list[str]:
    """Build rhythm description notes from metrics."""
    notes = []

    if avg_sentence_length > 35:
        notes.append("句长偏长")
    elif avg_sentence_length > 20:
        notes.append("句长中等")
    else:
        notes.append("句长偏短")

    if dialogue_ratio > 0.25:
        notes.append("对话比例较高")
    elif dialogue_ratio < 0.08:
        notes.append("对话比例较低")

    if action_ratio > 0.45:
        notes.append("动作描写密集")
    elif action_ratio < 0.15:
        notes.append("动作描写稀少")

    if short_sentence_ratio > 0.4:
        notes.append("短句密集，节奏快")
    if long_sentence_ratio > 0.2:
        notes.append("长句偏多，节奏缓")

    return notes
