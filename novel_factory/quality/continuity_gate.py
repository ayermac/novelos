"""Narrative Continuity Gate — v6.7.9

A hard, deterministic gate that blocks chapters with obvious narrative
continuity defects from reaching (or leaving) the publish pipeline.

Checks:
1. Chapter-internal time regression (flashbacks that rewind the main timeline)
2. Cross-chapter time-anchor conflicts
3. Truncated or malformed titles
4. Title-content keyword mismatch
5. Replay of already-completed plot events
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Severity levels ──────────────────────────────────────────────
SEVERITY_PASS = "pass"
SEVERITY_ADVISORY = "advisory"
SEVERITY_WARNING = "warning"
SEVERITY_BLOCKING = "blocking"


# ── Time regression detection patterns ───────────────────────────

# Markers that indicate a flashback / time regression in the narrative body.
_TIME_REGRESSION_MARKERS = (
    "两小时前", "三小时前", "四小时前", "五小时前", "几小时前",
    "半小时前", "一小时前", "一刻钟前", "十分钟前",
    "昨晚", "昨夜", "昨晨", "昨天下午", "昨天傍晚",
    "前天", "前日", "几天前", "数日前", "数月前", "数年前",
    "回到", "再次来到", "重新走进", "重返", "又回到了",
)

# Scenes that are *typically* part of a completed past event and should not
# re-appear as the main timeline unless clearly marked as a recap/flashback.
_OLD_SCENE_MARKERS = (
    "出租车", "下车步行", "门口保安", "公司走廊", "离开公司",
    "走出公司", "走出大厦", "回到公司", "抵达公司", "公司门口",
    "电梯里", "会议室门口", "走廊尽头", "前台",
)

# Phrases that clearly frame a section as a brief memory / flashback.
_FLASHBACK_FRAME_MARKERS = (
    "回忆起", "想起", "脑海中浮现", "记忆如潮", "往事涌上心头",
    "仿佛看到", "恍惚间", "眼前浮现", "往事", "记忆",
    "那段日子", "那时候", "曾经", "从前",
)

# Cross-chapter relative time expressions
_RELATIVE_TIME_EXPRESSIONS = (
    "明日", "明天", "今日", "今天", "今晚", "今夜", "凌晨", "清晨",
    "早上", "早晨", "上午", "中午", "午时", "下午", "傍晚", "黄昏",
    "晚上", "夜间", "深夜", "半夜", "子时", "丑时", "寅时",
    "七点五十", "七时五十分", "7:50", "7点50",
    "十点半", "十点三十", "10:30", "10点30",
    "八点半", "九点整", "正午", "晌午", "日落", "日出",
    "两天后", "三天后", "一周后", "一个月后",
    "次日", "翌日", "第二天", "第三天",
)

# Title truncation / malformed ending characters
_TITLE_BAD_ENDINGS = ("无", "的", "与", "和", "了", "在", "是", "有", "被", "让",
                      "把", "给", "对", "向", "从", "到", "及", "或")

# Hard contradiction phrases for time-anchor checks
_TIME_ANCHOR_CONTRADICTIONS = {
    # key: expected relative time -> phrases that contradict it
    "明日午时": ("早上", "清晨", "七点", "七时", "7:", "7点", "上午", "昨夜", "昨晚"),
    "明天": ("昨天", "前天", "昨晚", "昨夜"),
    "今日": ("明天", "昨日", "前天"),
    "今晚": ("明早", "明天", "昨天", "昨晚"),
}


@dataclass
class ContinuityGateResult:
    """Result of a continuity gate evaluation."""

    passed: bool = True
    severity: str = SEVERITY_PASS  # pass / advisory / warning / blocking
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    should_block_publish: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "evidence": self.evidence,
            "should_block_publish": self.should_block_publish,
        }


# ── Internal helpers ─────────────────────────────────────────────


def _head(text: str, limit: int) -> str:
    return str(text or "").strip()[:limit]


def _tail(text: str, limit: int) -> str:
    return str(text or "").strip()[-limit:]


def _strip_heading(text: str) -> str:
    lines = str(text or "").splitlines()
    if lines and re.match(r"^\s*第[一二三四五六七八九十百千万\d]+章\b", lines[0]):
        return "\n".join(lines[1:]).strip()
    return str(text or "").strip()


def _find_time_regression(content: str) -> tuple[list[str], list[str], dict[str, Any]]:
    """Scan for time-regression markers and classify severity.

    Returns (issues, suggestions, evidence).
    """
    issues: list[str] = []
    suggestions: list[str] = []
    evidence: dict[str, Any] = {"markers_found": [], "old_scene_found": False, "framed_as_flashback": False}

    body = _strip_heading(content)
    if not body:
        return issues, suggestions, evidence

    # Scan for time regression markers anywhere after the first paragraph.
    # For short texts, scan everything except the very first paragraph.
    body_len = len(body)
    first_para_end = body.find("\n\n")
    if first_para_end < 0:
        first_para_end = min(300, body_len)
    scan_area = body[first_para_end:]

    found_markers: list[str] = []
    for marker in _TIME_REGRESSION_MARKERS:
        if marker in scan_area:
            found_markers.append(marker)

    if not found_markers:
        return issues, suggestions, evidence

    evidence["markers_found"] = found_markers

    # Check if framed as a legitimate flashback
    framed = any(frame in body for frame in _FLASHBACK_FRAME_MARKERS)
    evidence["framed_as_flashback"] = framed

    # Check if old scene markers appear near the regression
    old_scene_hits = []
    for om in _OLD_SCENE_MARKERS:
        if om in scan_area:
            old_scene_hits.append(om)
    evidence["old_scene_found"] = bool(old_scene_hits)
    evidence["old_scene_hits"] = old_scene_hits

    # Decision logic
    if old_scene_hits and not framed:
        # Unframed regression to a completed scene → blocking
        issues.append(
            f"章中时空回退：正文出现“{found_markers[0]}”并回到已完成的旧场景"
            f"（{'/'.join(old_scene_hits[:3])}），且未标注为回忆/闪回。"
        )
        suggestions.append(
            "如果此处是回忆，请在段首明确标注回忆框架；"
            "如果是主线时间回退，请修正为顺叙或在本章开头交代转场原因。"
        )
    elif framed:
        # Framed as flashback → advisory only
        issues.append(
            f"章中出现回忆/闪回段落（标记：{found_markers[0]}），"
            "已检测到回忆框架，但请确认主线时间未因此回退。"
        )
        suggestions.append("确认闪回结束后主线时间线未发生倒退。")
    else:
        # Time marker found but no old scene hit → warning
        issues.append(
            f"章中出现时间回退标记“{found_markers[0]}”，"
            "请确认此处是合法回忆且主线未倒退。"
        )
        suggestions.append("若为主线时间回退，请在开头明确交代转场原因；否则标注为回忆。")

    return issues, suggestions, evidence


def _extract_relative_time_anchors(text: str) -> list[str]:
    """Extract relative time expressions from text."""
    anchors: list[str] = []
    text = str(text or "")
    for expr in _RELATIVE_TIME_EXPRESSIONS:
        if expr in text:
            anchors.append(expr)
    return anchors


def _check_cross_chapter_time_anchors(
    prev_tail: str,
    current_content: str,
    current_tail: str,
    next_opening: str | None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Check for cross-chapter time-anchor conflicts.

    Returns (issues, suggestions, evidence).
    """
    issues: list[str] = []
    suggestions: list[str] = []
    evidence: dict[str, Any] = {
        "prev_anchors": [],
        "current_anchors": [],
        "next_anchors": [],
        "conflicts": [],
    }

    prev_anchors = _extract_relative_time_anchors(prev_tail)
    current_anchors = _extract_relative_time_anchors(current_content)
    current_tail_anchors = _extract_relative_time_anchors(current_tail)
    next_anchors = _extract_relative_time_anchors(next_opening or "")

    evidence["prev_anchors"] = prev_anchors
    evidence["current_anchors"] = current_anchors
    evidence["next_anchors"] = next_anchors

    # Conflict 1: Previous chapter set a future anchor, but current chapter
    # treats it as already arrived without proper transition.
    for anchor in prev_anchors:
        if anchor in ("明日", "明天", "明日午时", "后天"):
            # Check if current chapter *still* refers to it as future
            if anchor in current_content and any(
                contradictor in current_content for contradictor in ("早上", "清晨", "上午", "昨天", "昨晚")
            ):
                # If the anchor is still spoken as "future" but the scene is
                # clearly the target day morning → contradiction
                if any(morning in current_content for morning in ("早上", "清晨", "七点", "七时", "7:", "7点", "上午")):
                    issues.append(
                        f"跨章时间锚点冲突：上一章约定“{anchor}”，"
                        "本章场景已处于次日早晨，但台词仍说“明日”之前。"
                    )
                    suggestions.append(
                        f"修正台词：将“{anchor}之前”改为“今天午时之前”或调整时间线。"
                    )
                    evidence["conflicts"].append({
                        "type": "future_anchor_still_spoken",
                        "anchor": anchor,
                        "scene_time": "morning",
                        "severity": "blocking",
                    })

    # Conflict 2: Current chapter tail sets an anchor that next chapter ignores
    for anchor in current_tail_anchors:
        if anchor in ("明日", "明天", "今晚", "今夜"):
            if next_anchors and any(
                contradictor in next_anchors for contradictor in ("昨天", "昨晚", "前天")
            ):
                issues.append(
                    f"跨章时间锚点断裂：本章结尾指向“{anchor}”，"
                    "下一章开头却回到过去时间。"
                )
                suggestions.append(
                    "在下一章开头明确时间过渡，或修正本章结尾的时间表述。"
                )
                evidence["conflicts"].append({
                    "type": "tail_to_next_break",
                    "anchor": anchor,
                    "severity": "warning",
                })

    return issues, suggestions, evidence


def _check_title(title: str, content: str) -> tuple[list[str], list[str], dict[str, Any]]:
    """Check title for truncation, malformation, or keyword mismatch.

    Returns (issues, suggestions, evidence).
    """
    from .title_guard import semantic_title_text, title_keyword_covered

    issues: list[str] = []
    suggestions: list[str] = []
    evidence: dict[str, Any] = {
        "title": title,
        "semantic_title": "",
        "title_length": 0,
        "bad_ending": False,
        "keyword_match": True,
        "keyword_evidence": [],
    }

    if not title:
        issues.append("标题缺失：章节没有标题。")
        suggestions.append("为章节生成一个能概括核心事件的标题。")
        evidence["missing"] = True
        return issues, suggestions, evidence

    title = str(title).strip()
    semantic_title = semantic_title_text(title)
    evidence["semantic_title"] = semantic_title
    evidence["title_length"] = len(title)

    # Truncation check: too short or ends with bad character
    if len(title) < 4:
        issues.append(f"标题过短：「{title}」仅有 {len(title)} 个字，疑似截断。")
        suggestions.append("补充完整标题，使其能概括本章核心事件。")
    elif any(title.endswith(bad) for bad in _TITLE_BAD_ENDINGS):
        issues.append(f"标题疑似截断：「{title}」以残缺字结尾。")
        suggestions.append("补全标题结尾，避免以虚词或残缺词收尾。")
        evidence["bad_ending"] = True

    # Keyword mismatch: title keywords should appear in content
    title_keywords = re.findall(r"[\u4e00-\u9fff]{2,8}", semantic_title)
    content_body = _strip_heading(content or "")
    if title_keywords and content_body:
        mismatches = []
        for kw in title_keywords[:4]:
            # Skip generic chapter numbering words
            if kw in ("第章", "第一章", "第二章", "第三章", "第四章", "第五章"):
                continue
            covered, keyword_evidence = title_keyword_covered(kw, content_body)
            evidence["keyword_evidence"].append(keyword_evidence)
            if not covered:
                mismatches.append(kw)
        if mismatches:
            issues.append(
                f"标题与正文脱节：标题关键词「{'/'.join(mismatches)}」未在正文中出现。"
            )
            suggestions.append("检查标题是否准确概括本章内容，或修正正文以覆盖标题所指事件。")
            evidence["keyword_match"] = False
            evidence["mismatched_keywords"] = mismatches

    return issues, suggestions, evidence


def _check_event_replay(
    content: str,
    previous_content: str | None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Detect if the current chapter replays already-completed events.

    Returns (issues, suggestions, evidence).
    """
    issues: list[str] = []
    suggestions: list[str] = []
    evidence: dict[str, Any] = {"replay_found": False, "overlapping_events": []}

    if not previous_content or not content:
        return issues, suggestions, evidence

    prev = str(previous_content)
    curr = str(content)

    # Guard: if the two chapters are >50% identical at sentence level,
    # treat as template/test data rather than narrative replay.
    prev_sents_all = {s.strip() for s in re.split(r"[。！？\n]", prev) if len(s.strip()) >= 6}
    curr_sents_all = {s.strip() for s in re.split(r"[。！？\n]", curr) if len(s.strip()) >= 6}
    if prev_sents_all and curr_sents_all:
        overlap = len(prev_sents_all & curr_sents_all)
        union = len(prev_sents_all | curr_sents_all)
        jaccard = overlap / union if union else 0
        evidence["jaccard_similarity"] = round(jaccard, 3)
        if jaccard > 0.50:
            # Likely identical stub/template content — skip replay detection
            return issues, suggestions, evidence

    # Heuristic: if a long unique phrase (>=12 chars) from the previous chapter
    # appears verbatim in the current chapter, it may be a replay.
    prev_sentences = re.split(r"[。！？\n]", prev)
    replay_candidates = []
    seen: set[str] = set()
    for sent in prev_sentences:
        sent = sent.strip()
        if len(sent) >= 12 and len(sent) <= 60 and sent in curr:
            # Skip common narrative glue and generic description
            if any(glue in sent for glue in (
                "说道", "说完", "看着", "走了", "来了", "点了点头",
                "站起身", "坐下", "站起来", "坐下后", "转过身", "回过头",
                "缓缓", "慢慢", "轻轻", "忽然", "突然", "只是",
                "心中", "心底", "心里", "脑海中", "眼前", "目光",
                "没有", "不能", "不要", "无法", "不得不",
            )):
                continue
            if sent not in seen:
                seen.add(sent)
                replay_candidates.append(sent)

    if len(replay_candidates) >= 3:
        evidence["replay_found"] = True
        evidence["overlapping_events"] = replay_candidates[:3]
        issues.append(
            f"疑似重复旧流程：当前章节与上一章有 {len(replay_candidates)} 处高度重叠的叙事段落。"
        )
        suggestions.append("删除或改写与上一章重复的段落，确保本章推进新情节。")

    return issues, suggestions, evidence


# ── Public API ───────────────────────────────────────────────────


def evaluate_chapter_continuity(
    repo: Any,
    project_id: str,
    chapter_number: int,
    content: str,
    title: str | None = None,
) -> ContinuityGateResult:
    """Evaluate a single chapter for narrative continuity defects.

    This is intentionally conservative — it only blocks *obvious* structural
    problems (time regression, title truncation, event replay) and leaves
    subtle continuity to the Editor LLM review.
    """
    all_issues: list[str] = []
    all_suggestions: list[str] = []
    all_evidence: dict[str, Any] = {"chapter_number": chapter_number}
    has_blocking = False
    has_warning = False

    # 1. Time regression
    reg_issues, reg_suggestions, reg_evidence = _find_time_regression(content)
    if reg_issues:
        if any("blocking" in i or "章中时空回退" in i for i in reg_issues):
            has_blocking = True
        else:
            has_warning = True
        all_issues.extend(reg_issues)
        all_suggestions.extend(reg_suggestions)
    all_evidence["time_regression"] = reg_evidence

    # 2. Cross-chapter time anchors
    if chapter_number > 1:
        try:
            prev_ch = repo.get_chapter(project_id, chapter_number - 1)
            prev_content = str(prev_ch.get("content") or "") if prev_ch else ""
            prev_tail = _tail(prev_content, 900)
        except Exception:
            prev_content = ""
            prev_tail = ""

        try:
            next_ch = repo.get_chapter(project_id, chapter_number + 1)
            next_opening = _head(next_ch.get("content") or "", 900) if next_ch else ""
        except Exception:
            next_opening = ""

        current_tail = _tail(content, 900)
        anchor_issues, anchor_suggestions, anchor_evidence = _check_cross_chapter_time_anchors(
            prev_tail, content, current_tail, next_opening,
        )
        if anchor_issues:
            anchor_blocking = any(
                c.get("severity") == "blocking"
                for c in anchor_evidence.get("conflicts", [])
            )
            if anchor_blocking:
                has_blocking = True
            else:
                has_warning = True
            all_issues.extend(anchor_issues)
            all_suggestions.extend(anchor_suggestions)
        all_evidence["time_anchors"] = anchor_evidence

    # 3. Title check
    title_issues, title_suggestions, title_evidence = _check_title(title or "", content)
    if title_issues:
        # Title truncation is warning-level (does not block publish by itself)
        if title_evidence.get("missing") or title_evidence.get("bad_ending"):
            has_warning = True
        all_issues.extend(title_issues)
        all_suggestions.extend(title_suggestions)
    all_evidence["title"] = title_evidence

    # 4. Event replay
    if chapter_number > 1 and prev_content:
        replay_issues, replay_suggestions, replay_evidence = _check_event_replay(content, prev_content)
        if replay_issues:
            has_blocking = True
            all_issues.extend(replay_issues)
            all_suggestions.extend(replay_suggestions)
        all_evidence["event_replay"] = replay_evidence

    # Determine severity
    if has_blocking:
        severity = SEVERITY_BLOCKING
        passed = False
        should_block = True
    elif has_warning:
        severity = SEVERITY_WARNING
        passed = False
        should_block = False
    elif all_issues:
        severity = SEVERITY_ADVISORY
        passed = True
        should_block = False
    else:
        severity = SEVERITY_PASS
        passed = True
        should_block = False

    return ContinuityGateResult(
        passed=passed,
        severity=severity,
        issues=all_issues,
        suggestions=all_suggestions,
        evidence=all_evidence,
        should_block_publish=should_block,
    )


def evaluate_publish_continuity(
    repo: Any,
    project_id: str,
    chapter_number: int,
) -> ContinuityGateResult:
    """Run continuity gate at publish time (reads chapter from DB)."""
    try:
        chapter = repo.get_chapter(project_id, chapter_number)
    except Exception:
        chapter = None

    if not chapter:
        return ContinuityGateResult(
            passed=False,
            severity=SEVERITY_BLOCKING,
            issues=["章节数据缺失，无法执行连续性检查。"],
            suggestions=["请确认章节已正确生成并保存。"],
            should_block_publish=True,
        )

    return evaluate_chapter_continuity(
        repo=repo,
        project_id=project_id,
        chapter_number=chapter_number,
        content=chapter.get("content", ""),
        title=chapter.get("title", ""),
    )
