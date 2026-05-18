"""Genesis draft quality gate for detecting template-like and low-quality outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class GenesisQualityIssue:
    """A single quality issue found in a genesis draft."""

    code: str
    severity: Literal["blocker", "warning", "advisory"]
    message: str
    section: str
    item_ref: str = ""
    suggestion: str = ""


@dataclass
class GenesisQualityReport:
    """Quality evaluation result for a genesis draft."""

    passed: bool
    score: float
    quality_status: Literal["pass", "warning", "blocked", "scaffold_fallback"]
    issues: list[GenesisQualityIssue] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


# Generic template patterns that indicate low-quality output
GENERIC_OBJECTIVE_PATTERNS = [
    r"第\s*\d+\s*章写作指令",
    r"完成.*章节.*目标",
    r"推进.*剧情发展",
    r"继续.*故事",
]

GENERIC_KEY_EVENTS_PATTERNS = [
    r"关键事件\s*\d+",
    r"主角.*登场",
    r"故事.*展开",
    r"剧情.*推进",
    r"冲突.*升级",
]

GENERIC_HOOK_PATTERNS = [
    r"更大.*危机.*浮出水面",
    r"新.*威胁.*出现",
    r"真相.*逐渐.*显现",
    r"谜团.*加深",
]

GENERIC_CHARACTER_NAMES = [
    "主角",
    "男主",
    "女主",
    "反派",
    "反派首领",
    "反派boss",
    "反派BOSS",
    "核心盟友",
    "重要配角",
    "神秘观察者",
    "神秘人",
    "神秘势力",
    "阶段反派",
    "主要反派",
]

GENERIC_FACTION_NAMES = [
    "主角阵营",
    "主角所属势力",
    "敌对势力",
    "既有权力方",
    "隐秘组织",
    "神秘组织",
    "中立资源方",
]

GENERIC_PLOT_TITLES = [
    "主角关键能力来源",
    "主角能力来源",
    "隐秘组织为何关注主角",
    "核心盟友隐藏立场",
    "主角身世之谜",
    "主角真实身份",
    "神秘信物",
]


def _normalize_text(text: str | None) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""
    return " ".join(str(text).split()).strip().lower()


def _is_generic_pattern(text: str, patterns: list[str]) -> bool:
    """Check if text matches any generic pattern."""
    normalized = _normalize_text(text)
    if not normalized:
        return False
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True
    return False


def _count_repeated_values(items: list[dict], key: str) -> dict[str, list[int]]:
    """Count occurrences of values and return chapters with duplicates."""
    value_to_chapters: dict[str, list[int]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        value = _normalize_text(item.get(key, ""))
        if not value:
            continue
        chapter = item.get("chapter_number", 0)
        if value not in value_to_chapters:
            value_to_chapters[value] = []
        value_to_chapters[value].append(chapter)
    return value_to_chapters


def _check_instruction_repetition(
    instructions: list[dict],
) -> list[GenesisQualityIssue]:
    """Check for repeated objectives, key_events, and ending_hooks."""
    issues: list[GenesisQualityIssue] = []

    if not instructions or len(instructions) < 2:
        return issues

    # Filter to only dict items
    dict_instructions = [i for i in instructions if isinstance(i, dict)]
    if len(dict_instructions) < 2:
        return issues

    # Check objective repetition
    obj_to_chapters = _count_repeated_values(dict_instructions, "objective")
    for obj, chapters in obj_to_chapters.items():
        if len(chapters) >= 3:
            issues.append(
                GenesisQualityIssue(
                    code="REPETITIVE_OBJECTIVE",
                    severity="blocker",
                    message=f"第 {', '.join(map(str, chapters[:5]))} 章 objective 完全相同",
                    section="instructions",
                    item_ref=f"chapters: {chapters[:5]}",
                    suggestion="为每章设计独立、具体的写作目标，避免重复使用相同指令",
                )
            )
        elif len(chapters) == 2:
            # Check if consecutive
            if abs(chapters[0] - chapters[1]) == 1:
                issues.append(
                    GenesisQualityIssue(
                        code="CONSECUTIVE_OBJECTIVE",
                        severity="warning",
                        message=f"第 {chapters[0]}、{chapters[1]} 章 objective 完全相同",
                        section="instructions",
                        item_ref=f"chapters: {chapters}",
                        suggestion="连续章节应有不同的写作目标，体现剧情推进",
                    )
                )

    # Check key_events repetition
    events_to_chapters = _count_repeated_values(instructions, "key_events")
    for events, chapters in events_to_chapters.items():
        if len(chapters) >= 3:
            issues.append(
                GenesisQualityIssue(
                    code="REPETITIVE_KEY_EVENTS",
                    severity="blocker",
                    message=f"第 {', '.join(map(str, chapters[:5]))} 章 key_events 完全相同",
                    section="instructions",
                    item_ref=f"chapters: {chapters[:5]}",
                    suggestion="每章应有独特的关键事件，避免模板化",
                )
            )

    # Check ending_hook repetition
    hook_to_chapters = _count_repeated_values(instructions, "ending_hook")
    for hook, chapters in hook_to_chapters.items():
        if len(chapters) >= 3:
            issues.append(
                GenesisQualityIssue(
                    code="REPETITIVE_HOOK",
                    severity="warning",
                    message=f"第 {', '.join(map(str, chapters[:5]))} 章 ending_hook 完全相同",
                    section="instructions",
                    item_ref=f"chapters: {chapters[:5]}",
                    suggestion="每章结尾应有独特的悬念或钩子",
                )
            )

    return issues


def _check_instruction_specificity(
    instructions: list[dict],
    title: str,
    genre: str,
    premise: str,
) -> list[GenesisQualityIssue]:
    """Check if instructions have sufficient specificity."""
    issues: list[GenesisQualityIssue] = []

    if not instructions:
        return issues

    # Filter to only dict items
    dict_instructions = [i for i in instructions if isinstance(i, dict)]
    if not dict_instructions:
        return issues

    # Genre/premise keywords that should trigger specific content
    supernatural_keywords = [
        "异常",
        "灵异",
        "超自然",
        "鬼怪",
        "系统",
        "修正",
        "异能",
        "超能力",
        "魔法",
        "修仙",
        "玄幻",
        "仙侠",
    ]
    urban_keywords = ["都市", "现代", "科技", "机甲", "商业", "职场"]
    fantasy_keywords = ["玄幻", "仙侠", "修仙", "奇幻", "魔法", "异界"]

    combined_text = f"{title} {genre} {premise}".lower()
    has_supernatural = any(kw in combined_text for kw in supernatural_keywords)
    has_urban = any(kw in combined_text for kw in urban_keywords)
    has_fantasy = any(kw in combined_text for kw in fantasy_keywords)

    generic_count = 0
    for inst in dict_instructions:
        objective = _normalize_text(inst.get("objective", ""))
        key_events = _normalize_text(inst.get("key_events", ""))

        # Check for generic patterns
        if _is_generic_pattern(objective, GENERIC_OBJECTIVE_PATTERNS):
            generic_count += 1

        if _is_generic_pattern(key_events, GENERIC_KEY_EVENTS_PATTERNS):
            generic_count += 1

        # Check for specific elements
        has_character = bool(re.search(r"[^\x00-\xff]{2,4}", objective + key_events))
        has_location = bool(
            re.search(
                r"(地点|场所|场景|城市|学院|公司|宗门|家族|组织|基地|实验室)",
                objective + key_events,
            )
        )

        if not has_character and not has_location:
            # Very generic instruction
            pass

    if generic_count >= len(dict_instructions) * 0.5:
        issues.append(
            GenesisQualityIssue(
                code="GENERIC_INSTRUCTIONS",
                severity="warning",
                message=f"{generic_count} 条章节指令使用了通用模板化表述",
                section="instructions",
                suggestion="章节指令应包含具体人物、地点、事件和冲突，避免空泛描述",
            )
        )

    return issues


def _check_outline_quality(
    outlines: list[dict],
    target_chapters: int,
    title: str,
    premise: str,
) -> list[GenesisQualityIssue]:
    """Check outline quality and coverage."""
    issues: list[GenesisQualityIssue] = []

    if not outlines:
        issues.append(
            GenesisQualityIssue(
                code="MISSING_OUTLINES",
                severity="blocker",
                message="大纲缺失",
                section="outlines",
                suggestion="生成覆盖首批章节的大纲",
            )
        )
        return issues

    # Filter to only dict items
    dict_outlines = [o for o in outlines if isinstance(o, dict)]
    if not dict_outlines:
        return issues

    # Check coverage
    covered_chapters = set()
    for outline in dict_outlines:
        chapters_range = str(outline.get("chapters_range", ""))
        # Parse range like "1-3" or "1"
        match = re.match(r"(\d+)\s*[-–]\s*(\d+)", chapters_range)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            covered_chapters.update(range(start, end + 1))
        else:
            single = re.match(r"(\d+)", chapters_range)
            if single:
                covered_chapters.add(int(single.group(1)))

    expected = set(range(1, target_chapters + 1))
    missing_chapters = expected - covered_chapters
    if missing_chapters and len(missing_chapters) > target_chapters * 0.3:
        issues.append(
            GenesisQualityIssue(
                code="INCOMPLETE_OUTLINE_COVERAGE",
                severity="warning",
                message=f"大纲未覆盖第 {sorted(list(missing_chapters))[:10]} 章",
                section="outlines",
                suggestion="大纲应覆盖首批所有章节",
            )
        )

    # Check for stage-label-only outlines
    stage_only_count = 0
    for outline in dict_outlines:
        content = _normalize_text(outline.get("content", ""))
        title_text = _normalize_text(outline.get("title", ""))

        # Check if it's just a stage label without specific plot
        stage_patterns = [
            r"开篇",
            r"开局",
            r"启程",
            r"高潮",
            r"收束",
            r"结局",
        ]
        if (
            _is_generic_pattern(title_text, stage_patterns)
            and len(content) < 50
        ):
            stage_only_count += 1

    if stage_only_count == len(dict_outlines) and len(dict_outlines) > 0:
        issues.append(
            GenesisQualityIssue(
                code="STAGE_LABEL_ONLY_OUTLINES",
                severity="warning",
                message="大纲仅有阶段标签，缺少具体剧情推进",
                section="outlines",
                suggestion="大纲应包含具体剧情发展、转折和冲突，而非仅阶段标签",
            )
        )

    # Check if outlines reflect title/premise
    combined = f"{title} {premise}".lower()
    if combined and len(dict_outlines) > 0:
        # Check if any outline content mentions key elements from title/premise
        outline_text = " ".join(
            o.get("content", "") + " " + o.get("title", "") for o in dict_outlines
        ).lower()
        # Extract significant words from title/premise (Chinese characters, 2+ length)
        key_words = re.findall(r"[^\x00-\xff]{2,}", combined)
        key_words = [w for w in key_words if len(w) >= 2 and w not in ["故事", "小说", "主角"]]
        if key_words:
            mentioned = sum(1 for w in key_words[:5] if w in outline_text)
            if mentioned == 0 and len(key_words) >= 2:
                issues.append(
                    GenesisQualityIssue(
                        code="OUTLINE_NOT_REFLECTING_PREMISE",
                        severity="advisory",
                        message="大纲未体现标题/创意中的核心卖点",
                        section="outlines",
                        suggestion="大纲应围绕标题和创意中的核心元素展开",
                    )
                )

    return issues


def _check_plot_hole_quality(plot_holes: list[dict]) -> list[GenesisQualityIssue]:
    """Check plot hole / foreshadowing quality."""
    issues: list[GenesisQualityIssue] = []

    if not plot_holes:
        return issues

    # Filter to only dict items
    dict_plot_holes = [p for p in plot_holes if isinstance(p, dict)]
    if not dict_plot_holes:
        return issues

    generic_count = 0
    for ph in dict_plot_holes:
        title = _normalize_text(ph.get("title", ""))
        description = _normalize_text(ph.get("description", ""))

        # Check for generic titles
        for generic_title in GENERIC_PLOT_TITLES:
            if generic_title.lower() in title:
                generic_count += 1
                break

        # Check for missing specifics
        has_specific_object = bool(
            re.search(r"[^\x00-\xff]{2,8}(的|之)", title + description)
        )
        has_trigger = bool(
            re.search(
                r"(当|在|如果|一旦|触发|激活|出现|发现)",
                title + description,
            )
        )

        if not has_specific_object and not has_trigger:
            if len(description) < 30:
                issues.append(
                    GenesisQualityIssue(
                        code="GENERIC_PLOT_HOLE",
                        severity="advisory",
                        message=f"伏笔「{ph.get('title', '')}」过于空泛",
                        section="plot_holes",
                        item_ref=ph.get("code", ""),
                        suggestion="伏笔应包含具体对象、触发条件和预期影响",
                    )
                )

    if generic_count >= len(dict_plot_holes) * 0.7 and len(dict_plot_holes) > 0:
        issues.append(
            GenesisQualityIssue(
                code="ALL_GENERIC_PLOT_HOLES",
                severity="warning",
                message="大部分伏笔使用了通用模板",
                section="plot_holes",
                suggestion="伏笔应针对具体故事设计，避免通用模板",
            )
        )

    return issues


def _check_character_quality(characters: list[dict]) -> list[GenesisQualityIssue]:
    """Check character quality."""
    issues: list[GenesisQualityIssue] = []

    if not characters:
        return issues

    # Filter to only dict items
    dict_characters = [c for c in characters if isinstance(c, dict)]
    if not dict_characters:
        return issues

    generic_name_count = 0
    for char in dict_characters:
        name = _normalize_text(char.get("name", ""))
        description = _normalize_text(char.get("description", ""))

        # Check for generic names
        for generic_name in GENERIC_CHARACTER_NAMES:
            if generic_name.lower() == name or generic_name.lower() in name:
                generic_name_count += 1
                issues.append(
                    GenesisQualityIssue(
                        code="GENERIC_CHARACTER_NAME",
                        severity="warning",
                        message=f"角色名「{char.get('name', '')}」使用了通用模板",
                        section="characters",
                        item_ref=char.get("name", ""),
                        suggestion="角色应有具体姓名，而非通用称呼",
                    )
                )
                break

        # Check for missing motivation/conflict
        has_motivation = bool(
            re.search(
                r"(动机|目的|目标|渴望|追求|想要)",
                description,
            )
        )
        has_conflict = bool(
            re.search(
                r"(矛盾|冲突|困境|压力|对立|敌对|秘密)",
                description,
            )
        )

        if not has_motivation and not has_conflict and len(description) < 50:
            issues.append(
                GenesisQualityIssue(
                    code="SHALLOW_CHARACTER",
                    severity="advisory",
                    message=f"角色「{char.get('name', '')}」缺少具体动机或矛盾",
                    section="characters",
                    item_ref=char.get("name", ""),
                    suggestion="角色应有具体动机、矛盾和资源/秘密",
                )
            )

    if generic_name_count >= len(dict_characters) * 0.5 and len(dict_characters) > 0:
        issues.append(
            GenesisQualityIssue(
                code="MOST_GENERIC_CHARACTERS",
                severity="blocker",
                message="大部分角色使用了通用模板名",
                section="characters",
                suggestion="角色应有具体姓名和设定，避免通用称呼",
            )
        )

    return issues


def _check_faction_quality(factions: list[dict]) -> list[GenesisQualityIssue]:
    """Check faction quality."""
    issues: list[GenesisQualityIssue] = []

    if not factions:
        return issues

    # Filter to only dict items
    dict_factions = [f for f in factions if isinstance(f, dict)]
    if not dict_factions:
        return issues

    generic_name_count = 0
    for fac in dict_factions:
        name = _normalize_text(fac.get("name", ""))
        description = _normalize_text(fac.get("description", ""))
        relationship = _normalize_text(
            fac.get("relationship_with_protagonist", "")
        )

        # Check for generic names
        for generic_name in GENERIC_FACTION_NAMES:
            if generic_name.lower() == name or generic_name.lower() in name:
                generic_name_count += 1
                issues.append(
                    GenesisQualityIssue(
                        code="GENERIC_FACTION_NAME",
                        severity="warning",
                        message=f"势力名「{fac.get('name', '')}」使用了通用模板",
                        section="factions",
                        item_ref=fac.get("name", ""),
                        suggestion="势力应有具体名称，而非通用称呼",
                    )
                )
                break

        # Check for missing conflict/relationship
        has_conflict = bool(
            re.search(
                r"(冲突|对立|敌对|竞争|合作|利用|试探)",
                description + relationship,
            )
        )

        if not has_conflict and len(description) < 30:
            issues.append(
                GenesisQualityIssue(
                    code="SHALLOW_FACTION",
                    severity="advisory",
                    message=f"势力「{fac.get('name', '')}」缺少与主角的明确关系",
                    section="factions",
                    item_ref=fac.get("name", ""),
                    suggestion="势力应有与主角的明确冲突或合作关系",
                )
            )

    if generic_name_count >= len(dict_factions) * 0.5 and len(dict_factions) > 0:
        issues.append(
            GenesisQualityIssue(
                code="MOST_GENERIC_FACTIONS",
                severity="blocker",
                message="大部分势力使用了通用模板名",
                section="factions",
                suggestion="势力应有具体名称和设定",
            )
        )

    return issues


def _check_scaffold_metadata(draft: dict) -> GenesisQualityIssue | None:
    """Check if draft is scaffold fallback."""
    meta = draft.get("_meta", {})
    if isinstance(meta, dict):
        source = meta.get("source", "")
        quality_status = meta.get("quality_status", "")
        if source == "scaffold_fallback" or quality_status == "scaffold_fallback":
            return GenesisQualityIssue(
                code="SCAFFOLD_FALLBACK",
                severity="blocker",
                message="当前草案包含兜底模板内容，不建议批准",
                section="meta",
                suggestion="请重新生成或人工补全草案内容",
            )
    return None


def evaluate_genesis_draft(
    draft: dict,
    *,
    title: str,
    genre: str,
    premise: str,
    target_chapters: int,
) -> GenesisQualityReport:
    """Evaluate a genesis draft for quality issues.

    Args:
        draft: The genesis draft JSON object
        title: Project title
        genre: Project genre
        premise: Project premise/creative intent
        target_chapters: Number of chapters to generate instructions for

    Returns:
        GenesisQualityReport with pass/fail status and issues
    """
    issues: list[GenesisQualityIssue] = []

    if not isinstance(draft, dict):
        return GenesisQualityReport(
            passed=False,
            score=0.0,
            quality_status="blocked",
            issues=[
                GenesisQualityIssue(
                    code="INVALID_DRAFT",
                    severity="blocker",
                    message="草案数据格式错误",
                    section="root",
                    suggestion="请重新生成草案",
                )
            ],
        )

    # Check for scaffold fallback
    scaffold_issue = _check_scaffold_metadata(draft)
    if scaffold_issue:
        issues.append(scaffold_issue)

    # Check instructions
    instructions = draft.get("instructions", [])
    if isinstance(instructions, list):
        issues.extend(_check_instruction_repetition(instructions))
        issues.extend(
            _check_instruction_specificity(instructions, title, genre, premise)
        )

    # Check outlines
    outlines = draft.get("outlines", [])
    if isinstance(outlines, list):
        issues.extend(_check_outline_quality(outlines, target_chapters, title, premise))

    # Check plot holes
    plot_holes = draft.get("plot_holes", [])
    if isinstance(plot_holes, list):
        issues.extend(_check_plot_hole_quality(plot_holes))

    # Check characters
    characters = draft.get("characters", [])
    if isinstance(characters, list):
        issues.extend(_check_character_quality(characters))

    # Check factions
    factions = draft.get("factions", [])
    if isinstance(factions, list):
        issues.extend(_check_faction_quality(factions))

    # Calculate score and determine status
    blocker_count = sum(1 for i in issues if i.severity == "blocker")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    advisory_count = sum(1 for i in issues if i.severity == "advisory")

    # Base score starts at 100, deduct for issues
    score = 100.0
    score -= blocker_count * 25
    score -= warning_count * 10
    score -= advisory_count * 3
    score = max(0.0, min(100.0, score))

    # Determine quality status
    if scaffold_issue:
        quality_status = "scaffold_fallback"
        passed = False
    elif blocker_count > 0:
        quality_status = "blocked"
        passed = False
    elif warning_count >= 3:
        quality_status = "warning"
        passed = True  # Warnings don't block by default
    else:
        quality_status = "pass"
        passed = True

    # Metrics
    metrics = {
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "advisory_count": advisory_count,
        "instruction_count": len(instructions) if isinstance(instructions, list) else 0,
        "outline_count": len(outlines) if isinstance(outlines, list) else 0,
        "character_count": len(characters) if isinstance(characters, list) else 0,
        "faction_count": len(factions) if isinstance(factions, list) else 0,
        "plot_hole_count": len(plot_holes) if isinstance(plot_holes, list) else 0,
    }

    return GenesisQualityReport(
        passed=passed,
        score=score,
        quality_status=quality_status,
        issues=issues,
        metrics=metrics,
    )
