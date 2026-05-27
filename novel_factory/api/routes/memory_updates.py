"""Memory update batches and items API endpoints."""

from __future__ import annotations

import json
import re
import hashlib

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ..contracts import success, partial_success, failed, blocked as blocked_result, ignored

router = APIRouter()


class MemoryItemUpdateRequest(BaseModel):
    """Request to update a memory update item."""

    status: str | None = None
    after_json: str | None = None
    rationale: str | None = None
    evidence_text: str | None = None


class MemoryApplyRequest(BaseModel):
    """Canonical body for memory apply action."""

    project_id: str
    batch_id: str
    allow_fallback: bool = False


class MemoryIgnoreRequest(BaseModel):
    """Canonical body for memory ignore action."""

    project_id: str
    item_id: str


class MemoryRetryRequest(BaseModel):
    """Canonical body for memory retry-failed action."""

    project_id: str
    batch_id: str


def _json_text(value) -> str:
    """Normalize structured memory values for text columns."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _normalize_text_fields(data: dict, fields: tuple[str, ...]) -> dict:
    """Return a copy with structured fields serialized for DB text columns."""
    normalized = dict(data)
    for field in fields:
        if field in normalized:
            normalized[field] = _json_text(normalized[field])
    return normalized


def _normalize_character_memory_data(data: dict) -> dict:
    """Normalize character patch fields without corrupting lifecycle status.

    Memory patches often use "status" to mean the character's story state. In
    the characters table, status is only an active/inactive lifecycle flag.
    """
    normalized = _normalize_text_fields(
        data, ("traits", "description", "alias", "role", "status")
    )
    if "status" in normalized:
        lifecycle_status = str(normalized.get("status") or "").strip().lower()
        if lifecycle_status not in {"active", "inactive"}:
            normalized.pop("status", None)
    return normalized


def _canonical_instruction_value(value) -> str:
    """Canonicalize instruction text so JSON-list and string forms compare."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed = value
    else:
        parsed = value

    if isinstance(parsed, list):
        text = "\n".join(_canonical_instruction_value(item) for item in parsed)
    elif isinstance(parsed, dict):
        text = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    else:
        text = str(parsed or "")
    return re.sub(r"\s+", "", text).strip()


def _instruction_signature(data: dict) -> tuple[str, str]:
    return (
        _canonical_instruction_value(data.get("objective")),
        _canonical_instruction_value(data.get("key_events")),
    )


def _find_recent_duplicate_instruction(
    repo,
    project_id: str,
    instruction_data: dict,
    *,
    lookback: int = 5,
) -> dict | None:
    """Find an identical instruction in the target or recent previous chapters."""
    chapter_number = _coerce_int(instruction_data.get("chapter_number"))
    if chapter_number <= 0:
        return None
    incoming_objective, incoming_events = _instruction_signature(instruction_data)
    if not incoming_objective or not incoming_events:
        return None

    for ch_num in range(max(1, chapter_number - lookback), chapter_number + 1):
        existing = repo.get_instruction_by_chapter(project_id, ch_num)
        if not existing:
            continue
        if _instruction_signature(existing) == (incoming_objective, incoming_events):
            return existing
    return None


def _parse_json_object(value) -> dict:
    """Parse a JSON object string safely."""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _infer_faction_name(repo, project_id: str, item: dict, after_data: dict) -> str:
    """Infer a faction name for memory patches missing target_id.

    LLM-generated memory patches sometimes classify an item as `update` but omit
    both target_id and name. Prefer existing faction names mentioned in the
    evidence/rationale, then fall back to a conservative Chinese faction-name
    pattern.
    """
    before_data = _parse_json_object(item.get("before_json"))
    for candidate in (after_data.get("name"), before_data.get("name")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    text = "\n".join(
        str(part or "")
        for part in (item.get("rationale"), item.get("evidence_text"), json.dumps(after_data, ensure_ascii=False))
    )
    for faction in repo.list_factions(project_id):
        name = str(faction.get("name") or "").strip()
        if name and name in text:
            return name

    ignored = {"拍卖会", "地下拍卖会", "豪门", "顶级豪门"}
    matches = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{1,12}(?:集团|公司|世家|家|宗|门|派|会|阁|楼|盟|帮|宫|族)", text)
    for match in sorted(set(matches), key=len):
        candidate = match
        for sep in ("了", "在"):
            if sep in candidate:
                candidate = candidate.rsplit(sep, 1)[-1]
        if candidate.endswith("家家"):
            candidate = candidate[:-1]
        if candidate and candidate not in ignored:
            return candidate
    return ""


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _find_outline_for_memory_update(repo, project_id: str, after_data: dict) -> dict | None:
    """Find an outline target for update patches that omitted target_id."""
    title = str(after_data.get("title") or "").strip()
    chapters_range = str(after_data.get("chapters_range") or "").strip()
    level = str(after_data.get("level") or "").strip()
    outlines = repo.list_outlines(project_id)

    if title:
        exact_title = next((outline for outline in outlines if str(outline.get("title") or "").strip() == title), None)
        if exact_title:
            return exact_title

    if chapters_range:
        same_range = [
            outline
            for outline in outlines
            if str(outline.get("chapters_range") or "").strip() == chapters_range
        ]
        if level:
            same_level_range = [
                outline
                for outline in same_range
                if str(outline.get("level") or "").strip() == level
            ]
            if same_level_range:
                return same_level_range[0]
        if same_range:
            return same_range[0]

    return None


def _find_world_setting_for_memory_update(repo, project_id: str, item: dict, after_data: dict) -> dict | None:
    """Find a world setting target for update patches that omitted target_id."""
    before_data = _parse_json_object(item.get("before_json"))
    titles = [
        str(candidate or "").strip()
        for candidate in (after_data.get("title"), before_data.get("title"))
        if str(candidate or "").strip()
    ]
    categories = {
        str(candidate or "").strip()
        for candidate in (after_data.get("category"), before_data.get("category"))
        if str(candidate or "").strip()
    }
    settings = repo.list_world_settings(project_id)

    for title in titles:
        title_matches = [
            setting
            for setting in settings
            if str(setting.get("title") or "").strip() == title
        ]
        if categories:
            category_match = next(
                (
                    setting
                    for setting in title_matches
                    if str(setting.get("category") or "").strip() in categories
                ),
                None,
            )
            if category_match:
                return category_match
        if len(title_matches) == 1:
            return title_matches[0]

    if categories:
        category_matches = [
            setting
            for setting in settings
            if str(setting.get("category") or "").strip() in categories
        ]
        if len(category_matches) == 1:
            return category_matches[0]

    return None


def _find_character_for_memory_update(repo, project_id: str, item: dict, after_data: dict) -> dict | None:
    """Find a character target for update patches that omitted target_id."""
    before_data = _parse_json_object(item.get("before_json"))
    names = [
        str(candidate or "").strip()
        for candidate in (
            after_data.get("name"),
            item.get("target_name"),
            before_data.get("name"),
        )
        if str(candidate or "").strip()
    ]
    characters = repo.list_characters(project_id, include_inactive=True)
    exact = next(
        (
            character
            for character in characters
            if str(character.get("name") or "").strip() in names
        ),
        None,
    )
    if exact:
        return exact

    inferred_name = _infer_character_name_for_memory_update(item, after_data)
    if not inferred_name:
        return None
    return next(
        (
            character
            for character in characters
            if str(character.get("name") or "").strip() == inferred_name
        ),
        None,
    )


def _derive_story_fact_key(item: dict, after_data: dict) -> str:
    """Derive a stable fact key when an LLM omits fact_key."""
    subject = str(after_data.get("subject") or "").strip()
    attribute = str(after_data.get("attribute") or "").strip()
    if subject and attribute:
        return f"{subject}.{attribute}"
    for candidate in (after_data.get("fact_key"), after_data.get("code"), after_data.get("title")):
        text = str(candidate or "").strip()
        if text:
            return text
    anchor = str(after_data.get("value") or item.get("evidence_text") or item.get("rationale") or "").strip()
    if anchor:
        compact = _compact_match_text(anchor)
        if compact:
            fact_type = str(after_data.get("fact_type") or "fact").strip() or "fact"
            return f"{fact_type}.{compact[:24]}"
    return ""


def _infer_character_name_for_memory_update(item: dict, after_data: dict) -> str:
    """Infer a concise character/group name from prose-only character patches."""
    before_data = _parse_json_object(item.get("before_json"))
    for candidate in (
        after_data.get("name"),
        item.get("target_name"),
        before_data.get("name"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text

    parts = [
        str(part or "")
        for part in (
            item.get("rationale"),
            item.get("evidence_text"),
            json.dumps(after_data, ensure_ascii=False),
        )
    ]
    patterns = (
        r"^([\u4e00-\u9fffA-Za-z0-9]{2,12}?)(?:的|行动|追踪|忽然|提前|没继续|继续|已经|正在|用)",
    )
    ignored = {
        "角色状态", "状态更新", "证据", "他们", "身后", "这里", "今天", "晨会",
        "主角", "有人", "外部", "内部",
    }
    ignored_prefixes = ("因为", "以及", "但是", "如果", "这里", "今天", "上方", "身后")
    for part in parts:
        for segment in re.split(r"[，。；;:：\n\"'“”‘’——,]", part):
            segment = segment.strip()
            if not segment or segment.startswith(ignored_prefixes):
                continue
            for pattern in patterns:
                match = re.search(pattern, segment)
                if not match:
                    continue
                candidate = str(match.group(1) or "").strip("，。；：:、 　")
                if candidate and candidate not in ignored:
                    return candidate
    return ""


def _compact_match_text(value) -> str:
    """Normalize Chinese/English text for fuzzy memory target matching."""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "")).lower()


def _longest_common_substring_len(left: str, right: str) -> int:
    """Return longest common substring length for short normalized labels."""
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for left_char in left:
        current = [0] * (len(right) + 1)
        for index, right_char in enumerate(right, start=1):
            if left_char == right_char:
                current[index] = previous[index - 1] + 1
                if current[index] > best:
                    best = current[index]
        previous = current
    return best


def _plot_update_anchors(item: dict, after_data: dict) -> list[str]:
    """Extract short subject anchors from a plot-hole update patch."""
    raw_parts = [
        after_data.get("code"),
        after_data.get("title"),
        after_data.get("description"),
        after_data.get("notes"),
        item.get("rationale"),
        item.get("evidence_text"),
    ]
    anchors: list[str] = []
    for part in raw_parts:
        text = str(part or "").strip()
        if not text:
            continue
        for segment in re.split(r"[，。；;:：\n]|从|升级|需要|疑似|再次|仍|并", text):
            compact = _compact_match_text(segment)
            if len(compact) >= 4 and compact not in anchors:
                anchors.append(compact[:18])
                break
    return anchors


def _infer_plot_hole_title(item: dict, after_data: dict) -> str:
    """Infer a concise plot-hole title from an update patch."""
    for candidate in (after_data.get("title"), after_data.get("code")):
        text = str(candidate or "").strip()
        if text:
            return text[:40]
    anchors = _plot_update_anchors(item, after_data)
    if anchors:
        return anchors[0][:24]
    for candidate in (after_data.get("description"), item.get("rationale"), item.get("evidence_text")):
        text = str(candidate or "").strip()
        if text:
            return re.split(r"[，。；;:：\n]", text, maxsplit=1)[0][:24]
    return "未命名伏笔"


def _create_plot_hole_from_memory_update(repo, project_id: str, item: dict, after_data: dict, chapter_number: int) -> dict | None:
    """Create a plot hole when an update patch describes a new/unmatched suspense thread."""
    title = _infer_plot_hole_title(item, after_data)
    description = str(
        after_data.get("description")
        or item.get("rationale")
        or item.get("evidence_text")
        or title
    ).strip()
    code = str(after_data.get("code") or "").strip()
    if not code:
        digest_source = f"{project_id}:{title}:{description}"
        code = f"PH-MEM-{hashlib.sha1(digest_source.encode('utf-8')).hexdigest()[:8].upper()}"
    return repo.create_plot_hole(
        project_id,
        code=code,
        type=after_data.get("type") or "悬念",
        title=title,
        description=description,
        planted_chapter=after_data.get("planted_chapter") or chapter_number or None,
        planned_resolve_chapter=after_data.get("planned_resolve_chapter"),
        status=after_data.get("status", "planted"),
        notes=after_data.get("notes", ""),
    )


def _plot_hole_match_score(plot: dict, text_norm: str, anchors: list[str]) -> int:
    """Score how likely a memory update refers to an existing plot hole."""
    score = 0
    fields = (
        ("code", 110),
        ("title", 80),
        ("description", 62),
        ("notes", 54),
    )
    for field, base_score in fields:
        value_norm = _compact_match_text(plot.get(field))
        if len(value_norm) < 4:
            continue
        if value_norm in text_norm:
            score = max(score, base_score + min(len(value_norm), 20))
        common_len = _longest_common_substring_len(value_norm, text_norm)
        if common_len >= 4:
            score = max(score, base_score - 24 + min(common_len * 3, 24))
        for anchor in anchors:
            if len(anchor) < 4:
                continue
            if anchor in value_norm or value_norm in anchor:
                score = max(score, base_score + min(len(anchor), 16))
                continue
            anchor_common_len = _longest_common_substring_len(anchor, value_norm)
            if anchor_common_len >= 4:
                score = max(score, base_score - 18 + min(anchor_common_len * 4, 28))
    return score


def _find_plot_hole_for_memory_update(repo, project_id: str, item: dict, after_data: dict, target_id=None) -> dict | None:
    """Resolve a plot_holes memory update to an existing伏笔 row."""
    if target_id:
        plot = repo.get_plot_hole(project_id, _coerce_int(target_id))
        if plot:
            return plot

    before_data = _parse_json_object(item.get("before_json"))
    plots = repo.list_plot_holes(project_id)

    code_candidates = [
        str(value).strip()
        for value in (after_data.get("code"), before_data.get("code"))
        if str(value or "").strip()
    ]
    title_candidates = [
        str(value).strip()
        for value in (after_data.get("title"), before_data.get("title"))
        if str(value or "").strip()
    ]

    for code in code_candidates:
        for plot in plots:
            if str(plot.get("code") or "").strip() == code:
                return plot

    for title in title_candidates:
        for plot in plots:
            if str(plot.get("title") or "").strip() == title:
                return plot

    text = "\n".join(
        str(part or "")
        for part in (
            item.get("rationale"),
            item.get("evidence_text"),
            json.dumps(after_data, ensure_ascii=False),
        )
    )

    for plot in plots:
        code = str(plot.get("code") or "").strip()
        if code and code in text:
            return plot

    titled_plots = sorted(
        (plot for plot in plots if str(plot.get("title") or "").strip()),
        key=lambda plot: len(str(plot.get("title") or "")),
        reverse=True,
    )
    for plot in titled_plots:
        title = str(plot.get("title") or "").strip()
        if len(title) >= 4 and title in text:
            return plot

    text_norm = _compact_match_text(text)
    anchors = _plot_update_anchors(item, after_data)
    scored = [
        (_plot_hole_match_score(plot, text_norm, anchors), plot)
        for plot in plots
    ]
    scored = [(score, plot) for score, plot in scored if score >= 58]
    scored.sort(key=lambda entry: entry[0], reverse=True)
    if scored:
        if len(scored) == 1 or scored[0][0] >= scored[1][0] + 8:
            return scored[0][1]

    return None


def _next_outline_sequence(repo, project_id: str, level: str) -> int:
    sequences = [
        _coerce_int(outline.get("sequence"), 0)
        for outline in repo.list_outlines(project_id)
        if str(outline.get("level") or "") == level
    ]
    return max(sequences, default=0) + 1


def _apply_memory_item(
    repo,
    project_id: str,
    item: dict,
    chapter_number: int = 0,
    batch_id: str | None = None,
) -> dict:
    """Apply a single memory update item to its target table.

    Returns a result dict with operation details.
    """
    target_table = item.get("target_table", "")
    operation = item.get("operation", "")
    target_id = item.get("target_id")
    after_data = {}
    result = {"target_table": target_table, "operation": operation, "success": False}

    try:
        after_data = json.loads(item.get("after_json", "{}"))
    except (json.JSONDecodeError, TypeError) as e:
        result["error"] = f"after_json 解析失败: {str(e)[:100]}"
        return result

    try:
        if target_table == "world_settings":
            if operation == "create":
                existing_setting = _find_world_setting_for_memory_update(
                    repo, project_id, item, after_data
                )
                if existing_setting:
                    updated = repo.update_world_setting(
                        project_id,
                        existing_setting["id"],
                        after_data,
                    )
                    result["operation"] = "update"
                    result["success"] = updated is not None
                    result["created_id"] = existing_setting["id"]
                    if not updated:
                        result["error"] = f"世界观设定 {existing_setting['id']} 不存在，无法更新"
                else:
                    ws = repo.create_world_setting(
                        project_id,
                        category=after_data.get("category", ""),
                        title=after_data.get("title", ""),
                        content=after_data.get("content", ""),
                    )
                    result["success"] = True
                    result["created_id"] = ws["id"] if ws else None
            elif operation == "update":
                setting = repo.get_world_setting(project_id, _coerce_int(target_id)) if target_id else None
                if not setting:
                    setting = _find_world_setting_for_memory_update(repo, project_id, item, after_data)

                if setting:
                    updated = repo.update_world_setting(project_id, setting["id"], after_data)
                    result["success"] = updated is not None
                    result["created_id"] = setting["id"]
                    if not updated:
                        result["error"] = f"世界观设定 {setting['id']} 不存在，无法更新"
                else:
                    title = str(after_data.get("title") or "").strip()
                    content = str(after_data.get("content") or "").strip()
                    if not title and not content:
                        result["error"] = "世界观更新缺少 target_id，且没有可创建的标题或内容"
                    else:
                        ws = repo.create_world_setting(
                            project_id,
                            category=str(after_data.get("category") or "未分类"),
                            title=title or f"第{chapter_number}章世界观补充",
                            content=content,
                        )
                        result["operation"] = "create"
                        result["success"] = True
                        result["created_id"] = ws["id"] if ws else None

        elif target_table == "characters":
            character_data = _normalize_character_memory_data(after_data)
            if operation == "create":
                existing_character = _find_character_for_memory_update(
                    repo, project_id, item, after_data
                )
                if existing_character:
                    updated = repo.update_character(
                        project_id,
                        existing_character["id"],
                        character_data,
                    )
                    result["operation"] = "update"
                    result["success"] = updated is not None
                    result["created_id"] = existing_character["id"]
                    if not updated:
                        result["error"] = f"角色 {existing_character['id']} 不存在，无法更新"
                else:
                    ch = repo.create_character(
                        project_id,
                        name=character_data.get("name", ""),
                        role=character_data.get("role", "supporting"),
                        description=character_data.get("description", ""),
                        traits=character_data.get("traits", ""),
                    )
                    result["success"] = True
                    result["created_id"] = ch["id"] if ch else None
            elif operation == "update":
                character = (
                    repo.get_character(project_id, _coerce_int(target_id))
                    if target_id
                    else None
                )
                if not character:
                    character = _find_character_for_memory_update(
                        repo, project_id, item, after_data
                    )
                if character:
                    updated = repo.update_character(
                        project_id, character["id"], character_data
                    )
                    result["success"] = updated is not None
                    result["created_id"] = character["id"]
                    if not updated:
                        result["error"] = f"角色 {character['id']} 不存在，无法更新"
                else:
                    inferred_name = _infer_character_name_for_memory_update(item, after_data)
                    if inferred_name:
                        created = repo.create_character(
                            project_id,
                            name=inferred_name,
                            role=character_data.get("role", "supporting"),
                            description=(
                                character_data.get("description")
                                or item.get("rationale", "")
                                or item.get("evidence_text", "")
                            ),
                            traits=character_data.get("traits", ""),
                        )
                        result["operation"] = "create"
                        result["success"] = True
                        result["created_id"] = created["id"] if created else None
                    else:
                        result["error"] = "角色更新缺少 target_id，且无法根据角色名匹配现有角色"

        elif target_table == "factions":
            if operation == "create":
                f = repo.create_faction(
                    project_id,
                    name=after_data.get("name", ""),
                    type=after_data.get("type", ""),
                    description=after_data.get("description", ""),
                    relationship_with_protagonist=after_data.get(
                        "relationship_with_protagonist", ""
                    ),
                )
                result["success"] = True
                result["created_id"] = f["id"] if f else None
            elif operation == "update":
                if target_id:
                    updated = repo.update_faction(project_id, target_id, after_data)
                    result["success"] = updated is not None
                    if updated:
                        result["created_id"] = updated["id"]
                    else:
                        result["error"] = f"势力 {target_id} 不存在，无法更新"
                else:
                    inferred_name = _infer_faction_name(repo, project_id, item, after_data)
                    if not inferred_name:
                        result["error"] = "势力更新缺少 target_id，且无法从证据中推断势力名称"
                    else:
                        existing = next(
                            (
                                faction
                                for faction in repo.list_factions(project_id)
                                if faction.get("name") == inferred_name
                            ),
                            None,
                        )
                        faction_data = dict(after_data)
                        faction_data["name"] = inferred_name
                        if existing:
                            updated = repo.update_faction(project_id, existing["id"], faction_data)
                            result["success"] = updated is not None
                            result["created_id"] = existing["id"]
                        else:
                            created = repo.create_faction(
                                project_id,
                                name=inferred_name,
                                type=faction_data.get("type") or ("家族势力" if inferred_name.endswith("家") else "势力"),
                                description=faction_data.get("description") or item.get("rationale", ""),
                                relationship_with_protagonist=faction_data.get("relationship_with_protagonist", ""),
                            )
                            result["operation"] = "create"
                            result["success"] = True
                            result["created_id"] = created["id"] if created else None

        elif target_table == "outlines":
            if operation == "create":
                o = repo.create_outline(
                    project_id,
                    level=after_data.get("level", "arc"),
                    sequence=_coerce_int(after_data.get("sequence"), 1),
                    title=after_data.get("title", ""),
                    content=after_data.get("content", ""),
                    chapters_range=after_data.get("chapters_range", ""),
                )
                result["success"] = True
                result["created_id"] = o["id"] if o else None
            elif operation == "update":
                outline = repo.get_outline(project_id, _coerce_int(target_id)) if target_id else None
                if not outline:
                    outline = _find_outline_for_memory_update(repo, project_id, after_data)

                if outline:
                    updated = repo.update_outline(project_id, outline["id"], after_data)
                    result["success"] = updated is not None
                    result["created_id"] = outline["id"]
                    if not updated:
                        result["error"] = f"大纲 {outline['id']} 不存在，无法更新"
                else:
                    title = str(after_data.get("title") or "").strip()
                    content = str(after_data.get("content") or "").strip()
                    if not title and not content:
                        result["error"] = "大纲更新缺少 target_id，且没有可创建的大纲标题或内容"
                    else:
                        level = str(after_data.get("level") or "arc").strip() or "arc"
                        sequence = _coerce_int(
                            after_data.get("sequence"),
                            _next_outline_sequence(repo, project_id, level),
                        )
                        created = repo.create_outline(
                            project_id,
                            level=level,
                            sequence=sequence,
                            title=title or f"第{chapter_number}章记忆大纲",
                            content=content,
                            chapters_range=str(after_data.get("chapters_range") or ""),
                        )
                        result["operation"] = "create"
                        result["success"] = True
                        result["created_id"] = created["id"] if created else None

        elif target_table == "plot_holes":
            if operation == "create":
                code = after_data.get("code", "")
                existing = next(
                    (
                        plot
                        for plot in repo.list_plot_holes(project_id)
                        if plot.get("code") == code
                    ),
                    None,
                )
                if existing:
                    ph = repo.update_plot_hole(project_id, existing["id"], after_data)
                    result["operation"] = "update"
                    result["success"] = ph is not None
                    result["created_id"] = existing["id"]
                else:
                    ph = repo.create_plot_hole(
                        project_id,
                        code=code,
                        type=after_data.get("type", ""),
                        title=after_data.get("title", ""),
                        description=after_data.get("description", ""),
                        planted_chapter=after_data.get("planted_chapter"),
                        planned_resolve_chapter=after_data.get("planned_resolve_chapter"),
                        status=after_data.get("status", "planted"),
                    )
                    result["success"] = True
                    result["created_id"] = ph["id"] if ph else None
            elif operation in {"update", "resolve", "deprecate"}:
                plot = _find_plot_hole_for_memory_update(
                    repo,
                    project_id,
                    item,
                    after_data,
                    target_id=target_id,
                )
                if plot:
                    plot_data = dict(after_data)
                    if operation == "resolve":
                        plot_data.setdefault("status", "resolved")
                        plot_data.setdefault("resolved_chapter", chapter_number or None)
                    elif operation == "deprecate":
                        plot_data.setdefault("status", "abandoned")
                    updated = repo.update_plot_hole(project_id, plot["id"], plot_data)
                    result["success"] = updated is not None
                    result["created_id"] = plot["id"]
                    if not updated:
                        result["error"] = f"伏笔 {plot['id']} 不存在，无法更新"
                else:
                    if operation == "update":
                        created = _create_plot_hole_from_memory_update(
                            repo,
                            project_id,
                            item,
                            after_data,
                            chapter_number,
                        )
                        result["operation"] = "create"
                        result["success"] = created is not None
                        result["created_id"] = created["id"] if created else None
                    else:
                        result["error"] = "伏笔更新缺少 target_id，且无法根据 code/title/证据匹配现有伏笔"

        elif target_table == "instructions":
            instruction_data = _normalize_text_fields(
                after_data,
                (
                    "key_events",
                    "plots_to_resolve",
                    "plots_to_plant",
                    "emotion_tone",
                    "ending_hook",
                    "objective",
                ),
            )
            if operation == "create":
                duplicate = _find_recent_duplicate_instruction(
                    repo, project_id, instruction_data
                )
                if duplicate:
                    result.update({
                        "success": True,
                        "skipped": True,
                        "reason": "duplicate_recent_instruction",
                        "existing_chapter_number": duplicate.get("chapter_number"),
                        "created_id": duplicate.get("id"),
                    })
                    return result

                inst = repo.create_instruction(
                    project_id,
                    chapter_number=instruction_data.get("chapter_number", 0),
                    objective=instruction_data.get("objective", ""),
                    key_events=instruction_data.get("key_events", ""),
                    plots_to_resolve=instruction_data.get("plots_to_resolve", ""),
                    plots_to_plant=instruction_data.get("plots_to_plant", ""),
                    emotion_tone=instruction_data.get("emotion_tone", ""),
                    ending_hook=instruction_data.get("ending_hook", ""),
                    word_target=instruction_data.get("word_target"),
                )
                result["success"] = True
                result["created_id"] = inst
            elif operation == "update":
                instruction = (
                    repo.get_instruction_by_id(project_id, _coerce_int(target_id))
                    if target_id
                    else None
                )
                if not instruction:
                    chapter_num = _coerce_int(instruction_data.get("chapter_number"))
                    instruction = (
                        repo.get_instruction_by_chapter(project_id, chapter_num)
                        if chapter_num > 0
                        else None
                    )
                if instruction:
                    updated = repo.update_instruction(
                        project_id, instruction["id"], instruction_data
                    )
                    result["success"] = updated is not None
                    result["created_id"] = instruction["id"]
                    if not updated:
                        result["error"] = f"写作指令 {instruction['id']} 不存在，无法更新"
                else:
                    inst = repo.create_instruction(
                        project_id,
                        chapter_number=instruction_data.get("chapter_number", 0),
                        objective=instruction_data.get("objective", ""),
                        key_events=instruction_data.get("key_events", ""),
                        plots_to_resolve=instruction_data.get("plots_to_resolve", ""),
                        plots_to_plant=instruction_data.get("plots_to_plant", ""),
                        emotion_tone=instruction_data.get("emotion_tone", ""),
                        ending_hook=instruction_data.get("ending_hook", ""),
                        word_target=instruction_data.get("word_target"),
                    )
                    result["operation"] = "create"
                    result["success"] = True
                    result["created_id"] = inst

        elif target_table == "story_facts":
            fact_key = str(after_data.get("fact_key") or "").strip()
            if not fact_key:
                fact_key = _derive_story_fact_key(item, after_data)
            if fact_key:
                # Check if fact exists before upsert (for event type)
                existing_fact = repo.get_story_fact_by_key(project_id, fact_key)
                is_update = existing_fact is not None

                fact = repo.upsert_story_fact(
                    project_id,
                    fact_key=fact_key,
                    fact_type=after_data.get("fact_type", "character_state"),
                    value_json=json.dumps(
                        after_data.get("value", {}), ensure_ascii=False
                    ),
                    source_chapter=after_data.get("source_chapter"),
                    source_agent=after_data.get("source_agent"),
                    subject=after_data.get("subject"),
                    attribute=after_data.get("attribute"),
                    unit=after_data.get("unit"),
                )
                result["success"] = True
                result["created_id"] = fact["id"] if fact else None

                # Create fact event for traceability
                if fact:
                    event_type = "updated" if is_update else "created"
                    event_chapter = (
                        after_data.get("source_chapter")
                        or chapter_number
                    )
                    try:
                        repo.create_fact_event(
                            project_id,
                            chapter_number=event_chapter,
                            agent_id="memory_curator",
                            event_type=event_type,
                            fact_id=fact["id"],
                            run_id=batch_id,
                            after_json=json.dumps(
                                after_data, ensure_ascii=False
                            ),
                            rationale=item.get(
                                "rationale",
                                f"Memory patch {event_type}",
                            ),
                            evidence_text=item.get("evidence_text", ""),
                            validation_status="validated",
                        )
                    except Exception:
                        pass  # Event creation is non-blocking

        elif target_table == "project":
            if after_data:
                repo.update_project(project_id, **after_data)
                result["success"] = True

    except Exception as e:
        result["error"] = str(e)[:200]

    if not result["success"] and "error" not in result:
        result["error"] = f"不支持的记忆更新: {target_table}.{operation}"

    return result


def _compute_batch_status(batch_id: str, repo) -> str:
    """Recalculate batch status from all item statuses.

    Rules:
    - partial: any failed items exist
    - pending: has pending items and no failed items
    - applied: all items are applied (no pending/failed/ignored)
    - ignored: all items are ignored (no pending/failed/applied)
    - mixed: has applied + ignored, no pending/failed
    """
    all_items = repo.list_memory_items(batch_id)
    if not all_items:
        return "pending"

    statuses = {item["status"] for item in all_items}

    if "failed" in statuses:
        return "partial"
    if "pending" in statuses:
        return "pending"
    if statuses == {"applied"}:
        return "applied"
    if statuses == {"ignored"}:
        return "ignored"
    # Mixed: applied + ignored only
    return "mixed"


def _is_state_card_fallback_batch(batch: dict, items: list[dict]) -> bool:
    """Return True when a batch is a low-confidence state-card fallback.

    These batches are created only after MemoryCurator's real extraction fails.
    They are useful as hints, but applying them directly pollutes project memory
    because they have not been classified or verified by the memory extractor.
    """
    summary = str(batch.get("summary") or "")
    if "状态卡兜底" in summary:
        return True
    for item in items:
        rationale = str(item.get("rationale") or "")
        confidence = float(item.get("confidence") or 0)
        if "状态卡兜底候选" in rationale or (
            confidence <= 0.45 and "MemoryCurator LLM 复核" in rationale
        ):
            return True
    return False


def _fallback_apply_error() -> EnvelopeResponse:
    return error_response(
        "FALLBACK_MEMORY_REQUIRES_REEXTRACTION",
        "该批次是状态卡兜底候选，不是 MemoryCurator 真实提取结果。请重新补跑记忆提取，或逐条人工复核后再应用。",
        details={
            "domain_result": blocked_result(
                "状态卡兜底记忆不能直接应用",
                user_message="这批记忆来自状态卡兜底，不是可信提取结果。请先补跑记忆提取。",
                next_action="backfill_memory",
                action_label="补跑记忆提取",
                flags={"fallback_memory_blocked": True},
            ).to_dict(),
        },
    )


def _build_memory_apply_domain_result(
    batch_id: str,
    new_status: str,
    results: list[dict],
) -> dict:
    """Build v6.6.12 domain_result for memory batch apply routes."""
    failed_count = sum(1 for r in results if not r.get("success"))
    success_count = len(results) - failed_count
    if new_status == "applied":
        return success(
            f"记忆批次应用成功：{success_count} 条已应用",
            user_message="记忆更新已成功应用到项目",
            details={
                "batch_id": batch_id,
                "items_processed": len(results),
                "success_count": success_count,
            },
            flags={"memory_applied": True},
        ).to_dict()
    if new_status == "partial":
        return partial_success(
            f"记忆批次部分应用：{success_count} 成功，{failed_count} 失败",
            user_message="部分记忆项应用失败，可重试失败项",
            next_action="retry_failed_memory",
            action_label="重试失败项",
            details={
                "batch_id": batch_id,
                "items_processed": len(results),
                "success_count": success_count,
                "failed_count": failed_count,
            },
            flags={"memory_partial": True},
        ).to_dict()
    if new_status == "mixed":
        return success(
            f"记忆批次应用完成：{success_count} 成功，部分已忽略",
            user_message="记忆更新已应用，部分项被忽略",
            details={
                "batch_id": batch_id,
                "items_processed": len(results),
                "success_count": success_count,
            },
            flags={"memory_mixed": True},
        ).to_dict()
    if new_status == "ignored":
        return ignored(
            "记忆批次已全部忽略",
            user_message="所有记忆项已被忽略，未应用到项目",
            details={
                "batch_id": batch_id,
                "items_processed": len(results),
            },
            flags={"memory_ignored": True},
        ).to_dict()
    return success(
        f"记忆批次处理完成：{new_status}",
        details={
            "batch_id": batch_id,
            "status": new_status,
            "items_processed": len(results),
        },
    ).to_dict()


@router.get("/projects/{project_id}/memory-batches")
async def list_memory_batches(
    request: Request, project_id: str, status: str | None = None
) -> EnvelopeResponse:
    """List memory update batches for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        try:
            from ._memory_curator_gate import (
                has_trusted_memory_batch,
                ignore_duplicate_state_card_fallback_batches,
                ignore_state_card_fallback_batches_for_chapter,
            )

            ignore_duplicate_state_card_fallback_batches(repo, project_id)
            for batch in repo.list_memory_batches(project_id):
                chapter_number = batch.get("chapter_number")
                if chapter_number is None:
                    continue
                if has_trusted_memory_batch(repo, project_id, int(chapter_number)):
                    ignore_state_card_fallback_batches_for_chapter(
                        repo,
                        project_id,
                        int(chapter_number),
                    )
        except Exception:
            pass

        batches = repo.list_memory_batches(project_id, status=status)
        return envelope_response(batches)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取记忆批次列表失败: {str(e)}")


@router.get("/projects/{project_id}/memory-batches/{batch_id}")
async def get_memory_batch(
    request: Request, project_id: str, batch_id: str
) -> EnvelopeResponse:
    """Get a memory update batch with its items."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        batch = repo.get_memory_batch(batch_id)
        if not batch:
            return error_response("BATCH_NOT_FOUND", f"批次 {batch_id} 不存在")

        if batch["project_id"] != project_id:
            return error_response("BATCH_NOT_FOUND", "批次不属于该项目")

        items = repo.list_memory_items(batch_id)
        result = {**batch, "items": items}
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取批次详情失败: {str(e)}")


@router.post("/projects/{project_id}/memory-batches/{batch_id}/apply")
async def apply_memory_batch(
    request: Request, project_id: str, batch_id: str
) -> EnvelopeResponse:
    """Apply all pending items in a memory update batch."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        batch = repo.get_memory_batch(batch_id)
        if not batch:
            return error_response("BATCH_NOT_FOUND", f"批次 {batch_id} 不存在")

        if batch["project_id"] != project_id:
            return error_response("BATCH_NOT_FOUND", "批次不属于该项目")

        if batch["status"] not in ("pending", "partial"):
            return error_response(
                "INVALID_BATCH_STATUS",
                f"只能应用待处理的批次，当前状态: {batch['status']}",
            )

        items = repo.list_memory_items(batch_id, status="pending")
        if not items:
            return error_response(
                "NO_PENDING_MEMORY_ITEMS",
                "该批次没有待应用的记忆项，请刷新后查看最新状态",
            )
        if _is_state_card_fallback_batch(batch, items):
            return _fallback_apply_error()
        results = []

        for item in items:
            apply_result = _apply_memory_item(
                repo, project_id, item,
                chapter_number=batch.get("chapter_number", 0),
                batch_id=batch_id,
            )
            update_data = {"status": "applied" if apply_result["success"] else "failed"}
            if not apply_result["success"] and apply_result.get("error"):
                update_data["error_message"] = apply_result["error"]
            repo.update_memory_item(item["id"], update_data)
            results.append({**apply_result, "item_id": item["id"]})

        # Recalculate batch status from all items
        new_status = _compute_batch_status(batch_id, repo)
        repo.update_memory_batch(batch_id, {"status": new_status})
        domain_result = _build_memory_apply_domain_result(batch_id, new_status, results)

        return envelope_response({
            "batch_id": batch_id,
            "status": new_status,
            "items_processed": len(results),
            "results": results,
            "domain_result": domain_result,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"应用批次失败: {str(e)}")


@router.post("/projects/{project_id}/memory-items/{item_id}/ignore")
async def ignore_memory_item(
    request: Request, project_id: str, item_id: str
) -> EnvelopeResponse:
    """Ignore a memory update item."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        item = repo.get_memory_item(item_id)
        if not item:
            return error_response("ITEM_NOT_FOUND", f"项目 {item_id} 不存在")

        if item["project_id"] != project_id:
            return error_response("ITEM_NOT_FOUND", "更新项不属于该项目")

        if item["status"] != "pending":
            return error_response(
                "INVALID_ITEM_STATUS",
                f"只能忽略待处理的项目，当前状态: {item['status']}",
            )

        updated = repo.update_memory_item(item_id, {"status": "ignored"})
        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"忽略更新项失败: {str(e)}")


@router.put("/projects/{project_id}/memory-items/{item_id}")
async def update_memory_item(
    request: Request, project_id: str, item_id: str, body: MemoryItemUpdateRequest
) -> EnvelopeResponse:
    """Update a memory update item (e.g., edit before applying)."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        item = repo.get_memory_item(item_id)
        if not item:
            return error_response("ITEM_NOT_FOUND", f"项目 {item_id} 不存在")

        if item["project_id"] != project_id:
            return error_response("ITEM_NOT_FOUND", "更新项不属于该项目")

        data = {}
        if body.status is not None:
            data["status"] = body.status
        if body.after_json is not None:
            data["after_json"] = body.after_json
        if body.rationale is not None:
            data["rationale"] = body.rationale
        if body.evidence_text is not None:
            data["evidence_text"] = body.evidence_text

        if not data:
            return envelope_response(item)

        updated = repo.update_memory_item(item_id, data)
        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新记忆项失败: {str(e)}")


# ---------------------------------------------------------------------------
# Canonical body-style routes (API Contract §4)
# ---------------------------------------------------------------------------


@router.post("/memory/apply")
async def apply_memory_batch_canonical(
    request: Request, body: MemoryApplyRequest
) -> EnvelopeResponse:
    """Canonical body-style route for memory batch apply."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        batch = repo.get_memory_batch(body.batch_id)
        if not batch:
            return error_response("BATCH_NOT_FOUND", f"批次 {body.batch_id} 不存在")

        if batch["project_id"] != body.project_id:
            return error_response("BATCH_NOT_FOUND", "批次不属于该项目")

        if batch["status"] not in ("pending", "partial"):
            return error_response(
                "INVALID_BATCH_STATUS",
                f"只能应用待处理的批次，当前状态: {batch['status']}",
            )

        items = repo.list_memory_items(body.batch_id, status="pending")
        if not items:
            return error_response(
                "NO_PENDING_MEMORY_ITEMS",
                "该批次没有待应用的记忆项，请刷新后查看最新状态",
            )
        if _is_state_card_fallback_batch(batch, items) and not body.allow_fallback:
            return _fallback_apply_error()
        results = []

        for item in items:
            apply_result = _apply_memory_item(
                repo, body.project_id, item,
                chapter_number=batch.get("chapter_number", 0),
                batch_id=body.batch_id,
            )
            update_data = {"status": "applied" if apply_result["success"] else "failed"}
            if not apply_result["success"] and apply_result.get("error"):
                update_data["error_message"] = apply_result["error"]
            repo.update_memory_item(item["id"], update_data)
            results.append({**apply_result, "item_id": item["id"]})

        new_status = _compute_batch_status(body.batch_id, repo)
        repo.update_memory_batch(body.batch_id, {"status": new_status})

        domain_result = _build_memory_apply_domain_result(body.batch_id, new_status, results)

        return envelope_response({
            "batch_id": body.batch_id,
            "status": new_status,
            "items_processed": len(results),
            "results": results,
            "domain_result": domain_result,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"应用批次失败: {str(e)}")


@router.post("/memory/ignore")
async def ignore_memory_item_canonical(
    request: Request, body: MemoryIgnoreRequest
) -> EnvelopeResponse:
    """Canonical body-style route for memory item ignore."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        item = repo.get_memory_item(body.item_id)
        if not item:
            return error_response("ITEM_NOT_FOUND", f"项目 {body.item_id} 不存在")

        if item["project_id"] != body.project_id:
            return error_response("ITEM_NOT_FOUND", "更新项不属于该项目")

        if item["status"] != "pending":
            return error_response(
                "INVALID_ITEM_STATUS",
                f"只能忽略待处理的项目，当前状态: {item['status']}",
            )

        updated = repo.update_memory_item(body.item_id, {"status": "ignored"})
        return envelope_response(updated)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"忽略更新项失败: {str(e)}")


@router.post("/memory/retry-failed")
async def retry_failed_memory_items(
    request: Request, body: MemoryRetryRequest
) -> EnvelopeResponse:
    """Reset all failed items in a batch to pending so they can be re-applied."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        batch = repo.get_memory_batch(body.batch_id)
        if not batch:
            return error_response("BATCH_NOT_FOUND", f"批次 {body.batch_id} 不存在")

        if batch["project_id"] != body.project_id:
            return error_response("BATCH_NOT_FOUND", "批次不属于该项目")

        if batch["status"] not in ("partial",):
            return error_response(
                "INVALID_BATCH_STATUS",
                f"只能重试 partial 批次，当前状态: {batch['status']}",
            )

        failed_items = repo.list_memory_items(body.batch_id, status="failed")
        if not failed_items:
            return error_response(
                "NO_FAILED_MEMORY_ITEMS",
                "该批次没有失败项",
            )

        reset_count = 0
        for item in failed_items:
            repo.update_memory_item(
                item["id"],
                {"status": "pending", "error_message": ""},
            )
            reset_count += 1

        new_status = _compute_batch_status(body.batch_id, repo)
        repo.update_memory_batch(body.batch_id, {"status": new_status})

        return envelope_response({
            "batch_id": body.batch_id,
            "status": new_status,
            "reset_count": reset_count,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"重试失败项失败: {str(e)}")
