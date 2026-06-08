"""Chapter-to-chapter seam context and deterministic continuity checks."""

from __future__ import annotations

import json
import re
import math
from typing import Any


_TIME_PATTERN = re.compile(
    r"(?:[一二两三四五六七八九十\d]+天后|[一二两三四五六七八九十\d]+日后|明天|今晚|今夜|当晚|次日|翌日|第二天|三日后|几天后)"
)
_LOCATION_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9Ωω·]{2,18}(?:区|厂|馆|室|楼|院|校|城|市|街|路|村|山|谷|河|湖|站|场|港|厅|所|部|园|库|宅|实验室|图书馆|工厂)"
)
_QUOTE_PATTERN = re.compile(r"[\"“'‘]([^\"”'’]{2,60})[\"”'’]")


def build_chapter_seam_context(repo: Any, project_id: str, chapter_number: int) -> str:
    """Build prompt context that forces the next chapter to bridge from the previous one."""
    if chapter_number <= 1:
        return ""

    previous = _safe_get_chapter(repo, project_id, chapter_number - 1)
    if not previous:
        return ""

    prev_content = str(previous.get("content") or "")
    prev_state = _state_data(_safe_get_state(repo, project_id, chapter_number - 1))
    prev_instruction = _safe_get_instruction(repo, project_id, chapter_number - 1) or {}

    parts = ["【章间衔接硬约束】"]
    parts.append(
        "本章开头必须承接上一章结尾的时间、地点、人物处境和未处理悬念。"
        "如果暂不处理某个悬念，必须在正文中明确交代延期或转场原因，禁止无解释切到新危机。"
    )

    if prev_content:
        parts.append(f"上一章结尾摘录:\n{_tail(prev_content, 700)}")

    ending_hook = str(prev_instruction.get("ending_hook") or "").strip()
    if ending_hook:
        parts.append(f"上一章指令钩子: {ending_hook}")

    facts = _state_values(prev_state, ("new_facts", "新增事实"))[:5]
    if facts:
        parts.append("上一章新增事实:\n" + "\n".join(f"- {item}" for item in facts))

    character_status = _state_mapping(prev_state, ("character_status", "角色状态"))
    if character_status:
        lines = [f"- {name}: {status}" for name, status in list(character_status.items())[:6]]
        parts.append("上一章人物状态:\n" + "\n".join(lines))

    hooks = _state_values(prev_state, ("suspense_hooks", "悬念"))[:5]
    if hooks:
        parts.append("上一章未处理悬念:\n" + "\n".join(f"- {item}" for item in hooks))

    return "\n".join(parts)


def build_planner_inheritance_context(repo: Any, project_id: str, chapter_number: int) -> str:
    """Build Planner-only inheritance context from applied facts and trusted memory batches."""
    if chapter_number <= 1:
        return ""

    prev_chapter = chapter_number - 1
    parts: list[str] = [
        "【强制继承资料】",
        "Planner 必须优先使用本节资料规划本章；其中“上一章真实记忆候选”按非兜底、高置信、最新批次选择。",
    ]

    facts = _recent_story_facts(repo, project_id, prev_chapter)
    if facts:
        lines = []
        for fact in facts[:12]:
            value = _compact_json_value(fact.get("value_json"))
            source = fact.get("source_chapter") or fact.get("last_changed_chapter") or "?"
            lines.append(
                f"- [{fact.get('fact_type', '')}] {fact.get('subject', '')}.{fact.get('attribute', '')}: {value} (第{source}章)"
            )
        parts.append("已应用事实账本:\n" + "\n".join(lines))

    batch, items = _select_trusted_memory_batch(repo, project_id, prev_chapter)
    if batch and items:
        lines = []
        for item in items[:12]:
            payload = _parse_json(item.get("after_json")) or {}
            code = str(payload.get("code") or "").strip()
            label = payload.get("name") or payload.get("title") or payload.get("fact_key") or item.get("target_table")
            target = f"[{code}] {label}" if code else label
            evidence = str(item.get("evidence_text") or item.get("rationale") or "")[:90]
            lines.append(
                f"- {item.get('target_table')}/{item.get('operation')}: {target} "
                f"(confidence={float(item.get('confidence') or 0):.2f}) {evidence}"
            )
        parts.append(
            f"上一章真实记忆候选: {batch.get('summary') or batch.get('id')}\n"
            + "\n".join(lines)
        )

    if len(parts) <= 2:
        return ""
    return "\n".join(parts)


def enforce_planner_inheritance(
    brief: Any,
    repo: Any,
    project_id: str,
    chapter_number: int,
) -> tuple[bool, list[str]]:
    """Repair a Planner brief so it cannot ignore explicit previous-chapter carryover."""
    obligations = _planner_obligations(repo, project_id, chapter_number)
    if not obligations:
        return False, []

    current_text = " ".join(
        [
            str(getattr(brief, "objective", "") or ""),
            " ".join(str(item) for item in getattr(brief, "required_events", []) or []),
            " ".join(str(item) for item in getattr(brief, "constraints", []) or []),
            str(getattr(brief, "ending_hook", "") or ""),
        ]
    )
    required_events = list(getattr(brief, "required_events", []) or [])
    constraints = list(getattr(brief, "constraints", []) or [])
    issues: list[str] = []

    for obligation in obligations:
        keywords = _keywords(obligation)
        if keywords and any(keyword in current_text for keyword in keywords):
            continue
        event = f"承接上一章悬念/约束：{obligation}"
        if event not in required_events:
            required_events.insert(0, event)
        constraint = f"本章必须回应或明确延期：{obligation}"
        if constraint not in constraints:
            constraints.append(constraint)
        if constraint not in required_events:
            required_events.append(constraint)
        issues.append(f"Planner 指令未承接上一章：{obligation}")

    if issues:
        brief.required_events = required_events[:6]
        brief.constraints = constraints[:8]
        if obligations[0] not in str(brief.objective):
            brief.objective = f"{brief.objective}；承接上一章：{obligations[0]}".strip("；")
    return bool(issues), issues


def evaluate_chapter_seam(
    repo: Any,
    project_id: str,
    chapter_number: int,
    current_content: str,
) -> dict[str, Any]:
    """Evaluate whether the current chapter bridges from the previous ending.

    This is intentionally conservative: it only blocks explicit previous-ending
    obligations such as "three days later, old industrial district" when the
    current opening does not acknowledge them. Softer unresolved hooks remain
    advisory so they do not create endless false-positive loops.
    """
    if chapter_number <= 1:
        return {"pass": True, "blocking_issues": [], "advisory_issues": [], "suggestions": []}

    previous = _safe_get_chapter(repo, project_id, chapter_number - 1)
    if not previous:
        return {"pass": True, "blocking_issues": [], "advisory_issues": [], "suggestions": []}

    prev_content = str(previous.get("content") or "")
    if not prev_content:
        return {"pass": True, "blocking_issues": [], "advisory_issues": [], "suggestions": []}

    opening = _head(_strip_heading(current_content or ""), 1800)
    prev_tail = _tail(prev_content, 900)
    prev_state = _state_data(_safe_get_state(repo, project_id, chapter_number - 1))
    prev_instruction = _safe_get_instruction(repo, project_id, chapter_number - 1) or {}
    source_text = "\n".join(
        [
            prev_tail,
            str(prev_instruction.get("ending_hook") or ""),
            "\n".join(_state_values(prev_state, ("suspense_hooks", "悬念"))[:5]),
        ]
    )

    blocking: list[str] = []
    advisory: list[str] = []
    suggestions: list[str] = []

    time_markers = _unique(_TIME_PATTERN.findall(source_text))
    location_markers = _unique(_LOCATION_PATTERN.findall(source_text))
    salient_locations = [
        loc for loc in location_markers
        if _is_explicit_appointment_location(loc, source_text, has_time_constraint=bool(time_markers))
    ] if location_markers else []
    salient_location_acknowledged = any(
        _location_acknowledged(loc, opening) for loc in salient_locations[:3]
    )
    quoted_hooks = [
        quote
        for quote in _QUOTE_PATTERN.findall(source_text)
        if any(token in quote for token in ("后", "明天", "今晚", "旧", "区", "见", "等", "来", "期待"))
    ][:3]

    time_anchor_acknowledged = _time_anchor_acknowledged(
        time_markers,
        source_text,
        opening,
    )

    if time_markers and not time_anchor_acknowledged and not salient_location_acknowledged:
        marker = time_markers[0]
        blocking.append(f"章间衔接断裂：上一章结尾存在明确时间节点“{marker}”，本章开头未承接。")
        suggestions.append(f"在本章开头交代“{marker}”是否已到、跳过了多久，或为什么暂时不赴约。")

    if salient_locations:
        if not salient_location_acknowledged:
            loc = salient_locations[0]
            blocking.append(f"章间衔接断裂：上一章结尾指向地点“{loc}”，本章开头未交代。")
            suggestions.append(f"在开头补充与“{loc}”相关的行动、转场或延期说明。")

    for quote in quoted_hooks:
        keywords = _keywords(quote)
        if keywords and not any(keyword in opening for keyword in keywords):
            advisory.append(f"上一章对白钩子“{quote[:24]}”在本章开头缺少回应。")
            break

    hooks = _state_values(prev_state, ("suspense_hooks", "悬念"))[:3]
    for hook in hooks:
        keywords = _keywords(str(hook))
        if keywords and not any(keyword in (current_content or "") for keyword in keywords):
            advisory.append(f"上一章悬念“{str(hook)[:28]}”本章未明显处理或延期。")
            break

    return {
        "pass": not blocking,
        "blocking_issues": blocking,
        "advisory_issues": advisory,
        "suggestions": suggestions,
    }


def _planner_obligations(repo: Any, project_id: str, chapter_number: int) -> list[str]:
    if chapter_number <= 1:
        return []
    previous = _safe_get_chapter(repo, project_id, chapter_number - 1)
    prev_content = str((previous or {}).get("content") or "")
    prev_tail = _tail(prev_content, 900)
    prev_state = _state_data(_safe_get_state(repo, project_id, chapter_number - 1))
    prev_instruction = _safe_get_instruction(repo, project_id, chapter_number - 1) or {}
    source_text = "\n".join(
        [
            prev_tail,
            str(prev_instruction.get("ending_hook") or ""),
            "\n".join(_state_values(prev_state, ("suspense_hooks", "悬念"))[:5]),
        ]
    )

    obligations: list[str] = []
    for marker in _unique(_TIME_PATTERN.findall(source_text))[:2]:
        related_locations = _unique(_LOCATION_PATTERN.findall(source_text))
        location = f"、{related_locations[0]}" if related_locations else ""
        obligations.append(f"{marker}{location}")

    hooks = _state_values(prev_state, ("suspense_hooks", "悬念"))
    if hooks:
        needed = max(1, min(2, math.ceil(len(hooks) * 0.5)))
        obligations.extend(str(hook) for hook in hooks[:needed])

    for quote in _QUOTE_PATTERN.findall(source_text):
        if any(token in quote for token in ("后", "明天", "今晚", "旧", "区", "见", "期待")):
            obligations.append(quote)

    return _unique([item for item in obligations if item])


def _recent_story_facts(repo: Any, project_id: str, chapter_number: int) -> list[dict]:
    try:
        facts = repo.list_story_facts(project_id, status="active")
    except Exception:
        return []
    return [
        fact for fact in facts
        if int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0) == int(chapter_number)
    ]


def _select_trusted_memory_batch(repo: Any, project_id: str, chapter_number: int) -> tuple[dict | None, list[dict]]:
    try:
        batches = [
            batch for batch in repo.list_memory_batches(project_id)
            if int(batch.get("chapter_number") or 0) == int(chapter_number)
            and str(batch.get("status") or "") != "ignored"
            and "状态卡兜底" not in str(batch.get("summary") or "")
        ]
    except Exception:
        return None, []

    candidates: list[tuple[float, str, dict, list[dict]]] = []
    for batch in batches:
        try:
            items = [
                item for item in repo.list_memory_items(batch["id"])
                if str(item.get("status") or "") != "ignored"
            ]
        except Exception:
            continue
        if not items:
            continue
        if any("状态卡兜底候选" in str(item.get("rationale") or "") for item in items):
            continue
        avg_confidence = sum(float(item.get("confidence") or 0) for item in items) / max(1, len(items))
        candidates.append((avg_confidence, str(batch.get("created_at") or ""), batch, items))

    if not candidates:
        return None, []
    _confidence, _created_at, batch, items = max(candidates, key=lambda row: (row[0], row[1]))
    return batch, items


def _safe_get_chapter(repo: Any, project_id: str, chapter_number: int) -> dict | None:
    try:
        return repo.get_chapter(project_id, chapter_number)
    except Exception:
        return None


def _safe_get_instruction(repo: Any, project_id: str, chapter_number: int) -> dict | None:
    try:
        return repo.get_instruction(project_id, chapter_number)
    except Exception:
        return None


def _safe_get_state(repo: Any, project_id: str, chapter_number: int) -> dict | None:
    try:
        return repo.get_chapter_state(project_id, chapter_number)
    except Exception:
        return None


def _state_data(state_card: dict | None) -> dict:
    data = (state_card or {}).get("state_data") if isinstance(state_card, dict) else {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    return data if isinstance(data, dict) else {}


def _state_values(state_data: dict, keys: tuple[str, ...]) -> list[str]:
    value: Any = None
    for key in keys:
        if state_data.get(key):
            value = state_data.get(key)
            break
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _state_mapping(state_data: dict, keys: tuple[str, ...]) -> dict[str, str]:
    for key in keys:
        value = state_data.get(key)
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items() if str(k).strip() and str(v).strip()}
    return {}


def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or "{}"))
    except Exception:
        return None


def _compact_json_value(value: Any) -> str:
    parsed = _parse_json(value)
    if parsed is None:
        text = str(value or "")
    else:
        text = json.dumps(parsed, ensure_ascii=False)
    return text[:120]


def _is_explicit_appointment_location(
    location: str,
    source_text: str,
    *,
    has_time_constraint: bool,
) -> bool:
    """Return True only for explicit carryover locations that should block.

    The raw location regex is intentionally broad. Without this guard, ordinary
    narration like "他沿着后巷一路" can be misread as a hard sequel obligation
    and push legacy batch workflows into blocking/revision loops.
    """
    loc = str(location or "").strip()
    if len(loc) < 2:
        return False
    if loc.startswith(("他", "她", "它", "我", "你", "众人", "两人", "三人")):
        return False
    if any(marker in loc for marker in ("着", "在了", "正站", "消失")):
        return False

    if not has_time_constraint:
        return False

    idx = source_text.rfind(loc)
    if idx < 0:
        return False

    window = source_text[max(0, idx - 40): idx + len(loc) + 40]
    appointment_markers = ("三天后", "明天", "今晚", "今夜", "次日", "后天", "等你", "期待", "约定", "赴约", "见面")
    return any(marker in window for marker in appointment_markers)


def _location_acknowledged(location: str, opening: str) -> bool:
    """Return True when the opening plainly continues the same place.

    Previous-ending extraction can capture owner/time qualifiers as part of a
    place, e.g. "赵家今晚在云澜预订的宴厅". The next chapter may naturally write
    "云澜宴会厅" instead; that should count as a bridge, not a hard seam break.
    """
    loc = str(location or "").strip()
    text = str(opening or "").strip()
    if not loc or not text:
        return False
    if loc in text:
        return True

    normalized_loc = _normalize_location_phrase(loc)
    normalized_opening = _normalize_location_phrase(text)
    if normalized_loc and normalized_loc in normalized_opening:
        return True

    venue_tokens = ("会馆", "宴会厅", "宴厅", "主位", "厅")
    if "云澜" in loc and "云澜" in text:
        return any(token in loc for token in venue_tokens) and any(token in text for token in venue_tokens)

    return False


def _time_anchor_acknowledged(
    time_markers: list[str],
    source_text: str,
    opening: str,
) -> bool:
    """Return True when the opening semantically bridges a prior time hook.

    Authors often fix a seam by writing the immediate consequence rather than
    repeating the exact relative-time word. For example, a previous ending says
    "今晚开启第二次签到"; the next opening may write "系统提示尚未消退，车已抵达酒店".
    Requiring the literal word "今晚" creates revision loops even when the
    scene is clearly continuous.
    """
    text = str(opening or "").strip()
    if not text:
        return False
    if any(marker and marker in text for marker in time_markers):
        return True

    transition_markers = (
        "刚才", "方才", "刚刚", "片刻前", "不久前", "尚未", "还未", "仍",
        "仍旧", "依旧", "已经", "随即", "随后", "此刻", "下一秒", "车窗",
        "抵达", "驶入", "滑入", "停在", "入住", "套房", "酒店", "提示",
        "灼热", "余温", "未散", "未退",
    )
    if not any(marker in text for marker in transition_markers):
        return False

    anchors = _anchor_keywords(source_text)
    if not anchors:
        return False
    hits = [anchor for anchor in anchors if anchor in text]
    return len(hits) >= 1


def _normalize_location_phrase(text: str) -> str:
    normalized = str(text or "")
    replacements = {
        "宴厅": "宴会厅",
        "今晚": "",
        "今夜": "",
        "当晚": "",
        "明天": "",
        "赵家": "",
        "苏家": "",
        "林辰": "",
        "预订的": "",
        "预定的": "",
        "订的": "",
        "预约的": "",
        "那间": "",
        "这间": "",
        "那座": "",
        "这座": "",
        "的": "",
        "在": "",
    }
    for before, after in replacements.items():
        normalized = normalized.replace(before, after)
    return re.sub(r"\s+", "", normalized)


def _anchor_keywords(text: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9Ωω]+|[\u4e00-\u9fff]{2,10}", str(text or ""))
    stop = {
        "本章", "上一章", "一个", "为何", "是否", "关系", "真实", "目的", "身份",
        "今晚", "今夜", "当晚", "明天", "次日", "翌日", "第二天", "三日后",
        "必须", "如果", "暂不", "处理", "明确", "交代", "原因", "禁止",
        "开头", "结尾", "悬念", "地方", "时候", "已经", "没有",
    }
    tokens: list[str] = []
    for token in raw_tokens:
        if token in stop or len(token) < 3:
            continue
        tokens.append(token)
        if re.search(r"[\u4e00-\u9fff]", token) and len(token) > 4:
            tokens.append(token[:4])
            tokens.append(token[-4:])
            tokens.extend(token[index:index + 4] for index in range(0, len(token) - 3))
    return _unique(tokens)


def _tail(text: str, limit: int) -> str:
    return str(text or "").strip()[-limit:]


def _head(text: str, limit: int) -> str:
    return str(text or "").strip()[:limit]


def _strip_heading(text: str) -> str:
    lines = str(text or "").splitlines()
    if lines and re.match(r"^\s*第[一二三四五六七八九十百千万\d]+章\b", lines[0]):
        return "\n".join(lines[1:]).strip()
    return str(text or "").strip()


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _keywords(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9Ωω]+|[\u4e00-\u9fff]{2,8}", str(text or ""))
    stop = {"本章", "上一章", "一个", "为何", "是否", "关系", "真实", "目的", "身份"}
    return [token for token in tokens if token not in stop][:5]
