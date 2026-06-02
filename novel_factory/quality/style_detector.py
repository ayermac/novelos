"""Webnovel Style Detector — v6.8.1

Deterministic style detection from project metadata.
No LLM dependencies, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Style Keywords ───────────────────────────────────────────────

_WEBNOVEL_KEYWORDS = (
    "逆袭", "打脸", "金手指", "升级", "碾压", "爽文", "开局",
    "系统", "签到", "抽奖", "重生", "穿越", "赘婿", "退婚",
    "龙王", "战神", "医神", "神豪", "装逼", "装弱", "扮猪吃虎",
)

_SUSPENSE_KEYWORDS = (
    "悬疑", "推理", "烧脑", "反转", "暗黑", "悬疑推理",
    "密室", "谋杀", "侦探", "真相", "线索", "阴谋",
)

_ROMANCE_KEYWORDS = (
    "爱情", "恋爱", "甜宠", "虐恋", "言情", "总裁",
    "豪门", "宠文", "腹黑", "霸道总裁", "先婚后爱",
    "破镜重圆", "暗恋", "双向奔赴",
)


# ── Style Profile ────────────────────────────────────────────────

@dataclass
class StyleProfile:
    """Detected style profile from project metadata."""

    primary_style: str = "general"  # webnovel_excitement | serious_literature | suspense | romance | general
    excitement_level: str = "low"  # high | medium | low
    opening_hook_required: bool = False
    excitement_density_target: str = "chapter_end_only"  # every_500_chars | every_1000_chars | chapter_end_only
    pacing_preference: str = "moderate"  # fast | moderate | slow
    keywords_detected: list[str] = field(default_factory=list)


# ── Prompt Templates ─────────────────────────────────────────────

_WEBNOVEL_PROMPTS = {
    "planner": (
        '\n\n【风格指令 — 爽文】\n'
        '- 开局必须在前 200 字内建立"逆袭预期"：让读者看到主角的潜力、资源或机遇\n'
        '- 压抑阶段不超过全章 30%，必须穿插"小爽点"（被认可、小胜利、技能展示）\n'
        '- 章末钩子必须指向"即将翻盘"而非"更多压抑"\n'
        '- 每章至少一个"打脸"或"逆袭"爽点\n'
    ),
    "screenwriter": (
        '\n\n【风格指令 — 爽文节奏】\n'
        '- 第一个 beat 必须包含"钩子"或"逆袭预期"\n'
        '- 每 2 个 beat 至少有一个"爽点 beat"（打脸/认可/胜利/技能展示）\n'
        '- 压抑 beat 和爽点 beat 交替，避免连续 3 个压抑 beat\n'
    ),
    "author": (
        '\n\n【风格指令 — 爽文写作】\n'
        '- 开局 200 字必须有"钩子"：悬念、冲突、或暗示即将发生的事\n'
        '- 压抑段落必须穿插"微爽点"：角色的小机智、小胜利、被认可\n'
        '- 避免连续 500 字以上的纯压抑叙述\n'
        '- 打脸场景要写得"爽"：对比鲜明、反应夸张、旁观者震惊\n'
    ),
    "editor": (
        '\n\n【风格指令 — 爽文审核】\n'
        '- 爽点权重提升：pacing 维度权重从 15 提升到 30\n'
        '- 重点检查：开局钩子、爽点密度、压抑/爽点交替节奏\n'
        '- 爽文模式下，连续压抑超过 500 字应标记为 warning\n'
    ),
}

_SUSPENSE_PROMPTS = {
    "planner": (
        "\n\n【风格指令 — 悬疑】\n"
        "- 每章至少埋下一个悬念或线索\n"
        "- 真相揭示节奏：前期铺垫 → 中期加深 → 后期反转\n"
        '- 章末钩子必须指向"即将揭晓的秘密"\n'
    ),
    "screenwriter": (
        "\n\n【风格指令 — 悬疑节奏】\n"
        "- 第一个 beat 建立悬念或异常\n"
        "- 中间 beat 逐步揭示线索，每 3 个 beat 一个小反转\n"
        "- 最后 beat 留下更大悬念或部分揭晓\n"
    ),
    "author": (
        "\n\n【风格指令 — 悬疑写作】\n"
        "- 氛围营造：环境描写要暗示不安、异常、隐藏的秘密\n"
        "- 线索埋伏：重要线索要自然融入对话或场景，不要刻意\n"
        "- 节奏控制：紧张段落用短句，揭示段落用长句\n"
    ),
    "editor": (
        "\n\n【风格指令 — 悬疑审核】\n"
        "- 重点检查：悬念连贯性、线索逻辑性、反转合理性\n"
        "- pacing 维度权重保持默认\n"
    ),
}

_ROMANCE_PROMPTS = {
    "planner": (
        "\n\n【风格指令 — 言情】\n"
        "- 每章至少一个情感互动场景\n"
        "- 感情线推进：初遇 → 心动 → 误会 → 和好 → 深入\n"
        '- 章末钩子指向"情感进展"或"关系变化"\n'
    ),
    "screenwriter": (
        "\n\n【风格指令 — 言情节奏】\n"
        "- 第一个 beat 建立情感张力或冲突\n"
        "- 每 2 个 beat 至少一个情感互动 beat\n"
        "- 避免连续 3 个纯剧情 beat（无情感元素）\n"
    ),
    "author": (
        "\n\n【风格指令 — 言情写作】\n"
        "- 情感描写细腻：心理活动、微表情、肢体语言\n"
        '- 对话要有"暧昧感"：双关、暗示、欲言又止\n'
        "- 场景氛围烘托：天气、环境、音乐与情感呼应\n"
    ),
    "editor": (
        "\n\n【风格指令 — 言情审核】\n"
        "- 重点检查：情感线连贯性、角色互动质量、氛围营造\n"
        "- pacing 维度权重保持默认\n"
    ),
}


# ── Public API ───────────────────────────────────────────────────

def detect_style_from_text(text: str) -> StyleProfile:
    """Detect style profile from project metadata text.

    Pure deterministic detection — no LLM dependencies.
    Input: concatenated name + genre + description text from projects table.
    """
    text_lower = text.lower()

    # Check for webnovel excitement keywords
    webnovel_hits = [kw for kw in _WEBNOVEL_KEYWORDS if kw in text_lower]
    suspense_hits = [kw for kw in _SUSPENSE_KEYWORDS if kw in text_lower]
    romance_hits = [kw for kw in _ROMANCE_KEYWORDS if kw in text_lower]

    all_hits = webnovel_hits + suspense_hits + romance_hits

    # Determine primary style based on keyword count
    if webnovel_hits and len(webnovel_hits) >= max(len(suspense_hits), len(romance_hits)):
        return StyleProfile(
            primary_style="webnovel_excitement",
            excitement_level="high",
            opening_hook_required=True,
            excitement_density_target="every_500_chars",
            pacing_preference="fast",
            keywords_detected=all_hits,
        )
    elif suspense_hits and len(suspense_hits) >= max(len(webnovel_hits), len(romance_hits)):
        return StyleProfile(
            primary_style="suspense",
            excitement_level="medium",
            opening_hook_required=True,
            excitement_density_target="every_1000_chars",
            pacing_preference="moderate",
            keywords_detected=all_hits,
        )
    elif romance_hits and len(romance_hits) >= max(len(webnovel_hits), len(suspense_hits)):
        return StyleProfile(
            primary_style="romance",
            excitement_level="medium",
            opening_hook_required=True,
            excitement_density_target="every_1000_chars",
            pacing_preference="moderate",
            keywords_detected=all_hits,
        )
    else:
        return StyleProfile(
            primary_style="general",
            excitement_level="low",
            opening_hook_required=False,
            excitement_density_target="chapter_end_only",
            pacing_preference="moderate",
            keywords_detected=all_hits,
        )


def get_style_prompt_injection(profile: StyleProfile, agent: str) -> str:
    """Return style-specific prompt injection for the given agent type.

    Returns empty string if no style-specific instructions apply.
    """
    if profile.primary_style == "webnovel_excitement":
        return _WEBNOVEL_PROMPTS.get(agent, "")
    elif profile.primary_style == "suspense":
        return _SUSPENSE_PROMPTS.get(agent, "")
    elif profile.primary_style == "romance":
        return _ROMANCE_PROMPTS.get(agent, "")
    return ""


def get_editor_weight_multiplier(profile: StyleProfile) -> dict[str, float]:
    """Return scoring weight multipliers for the Editor based on style.

    Default weights: setting=25, logic=25, poison=20, text=15, pacing=15
    Webnovel excitement: setting=20, logic=20, poison=15, text=15, pacing=30
    """
    if profile.excitement_level == "high":
        return {
            "setting": 20 / 25,  # 0.8
            "logic": 20 / 25,    # 0.8
            "poison": 15 / 20,   # 0.75
            "text": 15 / 15,     # 1.0
            "pacing": 30 / 15,   # 2.0
        }
    else:
        return {
            "setting": 1.0,
            "logic": 1.0,
            "poison": 1.0,
            "text": 1.0,
            "pacing": 1.0,
        }
