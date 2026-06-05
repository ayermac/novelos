"""Genesis draft quality gate for detecting template-like and low-quality outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, Any

from ..models.creative_contracts import (
    GenreProfile,
    ProjectLaunchProfile,
    GenreContract,
    PayoffCadence,
    PressureLimits,
)


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

# v6.6.4: Abstract objective patterns that lack specificity
ABSTRACT_OBJECTIVE_PATTERNS = [
    r"扩大冲突",
    r"推动剧情",
    r"获得主动权",
    r"进入复杂局面",
    r"冲突升级",
    r"主角成长",
    r"势力入场",
    r"故事展开",
    r"局面复杂",
    r"矛盾加深",
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


def _objective_similarity(a: str, b: str) -> float:
    """Jaccard similarity of character sets for detecting paraphrased templates."""
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


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

    # v6.6.4: Check for paraphrased (highly similar but not identical) consecutive objectives
    sorted_insts = sorted(
        [i for i in dict_instructions if i.get("chapter_number") is not None],
        key=lambda x: x["chapter_number"],
    )
    for i in range(len(sorted_insts) - 1):
        a = _normalize_text(sorted_insts[i].get("objective", ""))
        b = _normalize_text(sorted_insts[i + 1].get("objective", ""))
        if a and b and a != b and _objective_similarity(a, b) >= 0.65:
            issues.append(
                GenesisQualityIssue(
                    code="CONSECUTIVE_OBJECTIVE",
                    severity="warning",
                    message=f"第 {sorted_insts[i]['chapter_number']}、{sorted_insts[i + 1]['chapter_number']} 章 objective 高度相似（同义模板）",
                    section="instructions",
                    item_ref=f"chapters: {sorted_insts[i]['chapter_number']}, {sorted_insts[i + 1]['chapter_number']}",
                    suggestion="连续章节应有不同的写作目标，避免换说法复用同一模板",
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

    generic_count = 0
    for inst in dict_instructions:
        objective = _normalize_text(inst.get("objective", ""))
        key_events = _normalize_text(inst.get("key_events", ""))

        # Check for generic patterns
        if _is_generic_pattern(objective, GENERIC_OBJECTIVE_PATTERNS):
            generic_count += 1

        if _is_generic_pattern(key_events, GENERIC_KEY_EVENTS_PATTERNS):
            generic_count += 1

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


def _check_instruction_depth(instructions: list[dict]) -> list[GenesisQualityIssue]:
    """v6.6.4: Check if instructions have depth (specific characters, locations, actions, results)."""
    issues: list[GenesisQualityIssue] = []

    if not instructions:
        return issues

    dict_instructions = [i for i in instructions if isinstance(i, dict)]
    if not dict_instructions:
        return issues

    shallow_count = 0
    abstract_count = 0
    weak_events_count = 0
    missing_hook_count = 0
    missing_seed_count = 0

    for inst in dict_instructions:
        objective = _normalize_text(inst.get("objective", ""))
        key_events = _normalize_text(inst.get("key_events", ""))
        combined = objective + " " + key_events

        # ABSTRACT_OBJECTIVE: check for abstract patterns
        if _is_generic_pattern(objective, ABSTRACT_OBJECTIVE_PATTERNS):
            abstract_count += 1

        # SHALLOW_INSTRUCTION: must have specific character, location, action verb, result change
        has_character = bool(re.search(r"[^\x00-\xff]{2,4}", combined))
        has_location = bool(
            re.search(
                r"(地点|场所|场景|城市|学院|公司|宗门|家族|组织|基地|实验室|学校|街道|家中|办公室|战场|山谷|洞穴|塔|殿|阁|村|镇|城|医院|事务所|公寓|大楼|工厂|仓库|墓地|教堂|车站|码头|酒吧|餐厅|酒店|宫殿|密室|禁地|废墟|森林|沙漠|海岛|地下|天际|荒野|港|湾|堤|坝|站|所|区|域|界|层|网|节点|枢纽|入口)",
                combined,
            )
        )
        has_action = bool(
            re.search(
                r"(发现|找到|击败|逃离|潜入|揭露|保护|摧毁|夺取|谈判|背叛|拯救|追杀|埋伏|破解|触发|遭遇|拒绝|接受|质疑|展示|失控|击碎|试探|出手|相助|暗示|暴露|引发|遭到|监视|被迫|面对|挑战|测试|觉醒|制造|引起|使用|产生|碰撞|交锋|博弈|争夺|反击|投降|逃脱|追击|拦截|封锁|围困|逆转|寻找|进入|离开|取出|隐藏|追查|验证|确认|取得|得到|送出|收到|派出|接触|控制|关闭|打开|启动|停止|删除|复制|转移|改写|修复)",
                combined,
            )
        )
        has_result = bool(
            re.search(
                r"(导致|结果|因此|从而|使得|失去|获得|暴露|隐藏|改变|决定|意识到|明白|确认|否认|牺牲|代价|发现|遭到|面对|封锁|取得|得到|被删|被阻|被迫|被迫|陷入|陷入|曝光|泄露|外泄|逆转|反转|翻盘|落败|获胜|解决|未解|悬而未决)",
                combined,
            )
        )
        if not (has_character and has_location and has_action and has_result):
            shallow_count += 1

        # WEAK_KEY_EVENTS: count distinguishable events (split by common delimiters)
        events_text = str(inst.get("key_events", ""))
        event_parts = re.split(r"[；;。\.\n\r,，]", events_text)
        distinct_events = [p.strip() for p in event_parts if len(p.strip()) >= 4]
        if len(distinct_events) < 2:
            weak_events_count += 1

        # MISSING_CONTINUITY_SEED
        ending_hook = _normalize_text(inst.get("ending_hook", ""))
        continuity_seed = _normalize_text(inst.get("continuity_seed", ""))
        if not ending_hook:
            missing_hook_count += 1
        if not continuity_seed:
            missing_seed_count += 1

    total = len(dict_instructions)
    if abstract_count >= max(1, total // 2):
        issues.append(
            GenesisQualityIssue(
                code="ABSTRACT_OBJECTIVE",
                severity="blocker",
                message=f"{abstract_count} 章的 objective 使用了抽象表达（如\"扩大冲突/推动剧情/获得主动权\"）",
                section="instructions",
                suggestion="每章 objective 必须写出具体的主角目标、阻力和结果变化",
            )
        )

    if shallow_count >= max(1, total // 2):
        issues.append(
            GenesisQualityIssue(
                code="SHALLOW_INSTRUCTION",
                severity="blocker",
                message=f"{shallow_count} 章的指令缺少具体人物、地点、行动或结果变化",
                section="instructions",
                suggestion="章节指令应包含具体人物、地点、行动动词和结果变化",
            )
        )

    if weak_events_count >= max(1, total // 2):
        issues.append(
            GenesisQualityIssue(
                code="WEAK_KEY_EVENTS",
                severity="warning",
                message=f"{weak_events_count} 章的 key_events 少于 2 个可区分事件",
                section="instructions",
                suggestion="每章应至少包含 2-3 个不同的具体事件",
            )
        )

    # MISSING_CONTINUITY_SEED only matters for multi-chapter plans
    if total >= 2:
        if missing_hook_count >= max(1, total // 2):
            issues.append(
                GenesisQualityIssue(
                    code="MISSING_CONTINUITY_SEED",
                    severity="warning",
                    message=f"{missing_hook_count} 章缺少 ending_hook",
                    section="instructions",
                    suggestion="多章规划应为每章设置结尾钩子，支撑悬念延续",
                )
            )
        if missing_seed_count >= max(1, total // 2):
            issues.append(
                GenesisQualityIssue(
                    code="MISSING_CONTINUITY_SEED",
                    severity="warning",
                    message=f"{missing_seed_count} 章缺少 continuity_seed",
                    section="instructions",
                    suggestion="多章规划应设置继承点，确保下一章能衔接悬念",
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
    abstract_count = 0
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
            r"前期",
            r"中期",
            r"后期",
            r"过渡",
            r"铺垫",
        ]
        if (
            _is_generic_pattern(title_text, stage_patterns)
            and len(content) < 50
        ):
            stage_only_count += 1

        # v6.6.4: OUTLINE_TOO_ABSTRACT - check for missing conflict, twist, result
        has_conflict = bool(
            re.search(
                r"(冲突|对抗|争夺|矛盾|斗争|较量|博弈|对立|厮杀|伏击|围杀|背叛|决裂|摩擦|压制|反抗)",
                content,
            )
        )
        has_twist = bool(
            re.search(
                r"(转折|反转|突变|意外|震惊|发现|揭露|识破|中计|落网|逃脱|反杀|翻盘|失衡|破裂)",
                content,
            )
        )
        has_result = bool(
            re.search(
                r"(结果|结局|代价|收获|改变|决定|立场|归属|胜负|生死|覆灭|崛起|退败|妥协|联合)",
                content,
            )
        )
        if not (has_conflict or has_twist or has_result) and len(content) < 60:
            abstract_count += 1

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

    if abstract_count >= max(1, len(dict_outlines) // 2):
        issues.append(
            GenesisQualityIssue(
                code="OUTLINE_TOO_ABSTRACT",
                severity="blocker",
                message=f"{abstract_count} 个大纲缺少阶段冲突、转折或阶段结果",
                section="outlines",
                suggestion="大纲不能只写阶段标签，必须写出阶段冲突、转折和阶段结果",
            )
        )

    # v6.6.18: Check if outlines reflect title/premise using tokenized short keywords
    combined = f"{title} {premise}".lower()
    if combined and len(dict_outlines) > 0:
        outline_text = " ".join(
            o.get("content", "") + " " + o.get("title", "") for o in dict_outlines
        ).lower()
        generic_stopwords = {
            "故事", "小说", "主角", "一个", "关于", "作品", "讲述", "围绕",
            "展开", "发生", "背景", "世界", "时代", "题材", "类型", "风格",
            "设定", "情节", "剧情", "文本", "作者", "读者", "本书", "本章",
            "系列", "篇章", "内容", "主题", "核心", "主要", "重要", "基本",
            "因此", "从而", "使得",
        }
        # Split by non-Chinese delimiters, then extract meaningful tokens
        raw_phrases = re.split(r"[^\u4e00-\u9fff]+", combined)
        key_words: list[str] = []
        for phrase in raw_phrases:
            if not phrase:
                continue
            if 2 <= len(phrase) <= 6 and phrase not in generic_stopwords:
                key_words.append(phrase)
            elif len(phrase) > 6:
                # For long unbroken strings, extract 2-char windows with step 2
                # from the head to capture core nouns/verbs without too much noise
                for i in range(0, min(len(phrase) - 1, 12), 2):
                    sub = phrase[i:i + 2]
                    if sub not in generic_stopwords:
                        key_words.append(sub)
        # Alphanumeric tokens of 2+ chars (names, tech terms)
        for token in re.findall(r"[a-z0-9]+", combined):
            if len(token) >= 2:
                key_words.append(token)
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for w in key_words:
            if w not in seen:
                seen.add(w)
                deduped.append(w)
        key_words = deduped[:10]
        if key_words:
            mentioned = sum(1 for w in key_words[:6] if w in outline_text)
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
    weak_design_count = 0
    for ph in dict_plot_holes:
        title = _normalize_text(ph.get("title", ""))
        description = _normalize_text(ph.get("description", ""))
        combined = title + " " + description

        # Check for generic titles
        for generic_title in GENERIC_PLOT_TITLES:
            if generic_title.lower() in title:
                generic_count += 1
                break

        # Check for missing specifics
        has_specific_object = bool(
            re.search(r"[^\x00-\xff]{2,8}(的|之)", combined)
        )
        has_trigger = bool(
            re.search(
                r"(当|在|如果|一旦|触发|激活|出现|发现|场景|时刻|条件)",
                combined,
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

        # v6.6.4: WEAK_PLOT_HOLE_DESIGN
        has_appearance = bool(
            re.search(
                r"(表象|表面|看似|看起来|读者|发现|注意到|看到|听到|察觉)",
                combined,
            )
        )
        has_truth = bool(
            re.search(
                r"(真相|真实|实际|背后|内幕|实质|谜底|揭秘)",
                combined,
            )
        )
        has_resolve = bool(
            re.search(
                r"(兑现|解决|揭示|揭晓|推进|展开|于第|在.*章|预计|计划)",
                combined,
            )
        ) or ph.get("planned_resolve_chapter")
        if not (has_trigger and has_appearance and has_truth and has_resolve):
            weak_design_count += 1

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

    if weak_design_count >= max(1, len(dict_plot_holes) // 2):
        issues.append(
            GenesisQualityIssue(
                code="WEAK_PLOT_HOLE_DESIGN",
                severity="warning",
                message=f"{weak_design_count} 个伏笔缺少触发场景、表象、真相方向或预计兑现章节",
                section="plot_holes",
                suggestion="伏笔应包含触发场景、读者表象、真相方向和预计兑现计划",
            )
        )

    return issues


# v6.6.18: Expanded semantic vocabularies for high-quality natural-language outputs
_CHARACTER_GOAL_FIELDS = ("goal", "objective", "motivation", "current_goal", "desire")
_CHARACTER_CONFLICT_FIELDS = ("conflict", "secret", "inner_conflict", "contradiction")
_CHARACTER_INTEREST_FIELDS = (
    "relationship_with_protagonist", "interest_relation", "alliance", "hostility"
)
_CHARACTER_RELATIONSHIP_WORDS = [
    "协助", "保护", "牵制", "摇摆", "隐瞒", "补救", "利用价值", "镜像", "旧账",
    "被卷入", "被处理对象", "表面配合", "真实摇摆", "关键证人", "线索提供者",
    "合作", "敌对", "同盟", "依附", "背叛", "监视", "忌惮", "赏识", "排斥",
    "利益", "关系", "利用", "盟友", "同路人", "前搭档", "不完全信任", "帮助",
    "共同处理", "关键参照", "熟悉感", "线索互换", "推动主线",
]
_CHARACTER_GOAL_PATTERNS = [
    r"(动机|目的|目标|渴望|追求|想要|欲望|志向|执念|心愿|野心|理想)",
    r"(希望|想|试图|企图|力图|为了|要|打算|计划|准备).{0,36}"
    r"(查|找|寻找|确认|证明|保护|保住|维持|阻止|保存|揭|追|救|抹除|处理)",
    r"(专门处理|负责.{0,24}(比对|维护|调控|封存|校验)|追查|寻找|查明|确认|保护|保住|"
    r"维持|阻止|保存|揭露|证明|推动|调查)",
]
_CHARACTER_CONFLICT_PATTERNS = [
    r"(矛盾|冲突|困境|压力|对立|敌对|秘密|心结|隐痛|挣扎|纠结|背叛|隐瞒|欺骗)",
    r"(记忆空洞|被.{0,12}(改写|修正|重排|抹去|收编|封存|处理)|曾参与|掩盖事故|"
    r"旧事故|旧案|风险名单|下落不明|身份危机|无法确认|不完全信任|立场.{0,12}摇摆|"
    r"刻意封存|不能公开|悬念|样本|触碰)",
    r"(怀疑自己|发现自己|被迫承认|究竟是|疑似|可能曾|越接近.{0,24}越怀疑)",
]
_CHARACTER_INTEREST_PATTERNS = [
    r"(与|和|对).{0,12}(陆澈|林潮|主角).{0,32}"
    r"(盟友|同路人|信任|帮助|触碰|对抗|压制|协助|保护|利用|参照|摇摆|阻止|"
    r"逼近|共同|处理|熟悉感)",
    r"(陆澈|林潮|主角).{0,32}(越|共同|帮助|关键|记忆|调查|逼近|触碰|参照|信任)",
    r"(盟友|同路人|前搭档|关键参照|线索互换|共同处理|帮助|协助|保护|利益|立场|"
    r"摇摆|对抗|压制|监控|利用|触碰|熟悉感|关键证人|线索提供者|推动主线)",
    r"(自己|自身|自我|身份|记忆完整性|家人|妹妹|亲人|下落).{0,24}"
    r"(保护|保住|风险|危机|完整性|风险名单|空洞|修正|改写)",
]


def _character_has_structured_goal(char: dict) -> bool:
    """Return True if character has a non-empty structured goal field."""
    for field in _CHARACTER_GOAL_FIELDS:
        value = str(char.get(field) or "").strip()
        if value and len(value) >= 4:
            return True
    return False


def _character_has_structured_conflict(char: dict) -> bool:
    """Return True if character has a non-empty structured conflict/secret field."""
    for field in _CHARACTER_CONFLICT_FIELDS:
        value = str(char.get(field) or "").strip()
        if value and len(value) >= 4:
            return True
    return False


def _character_has_structured_interest(char: dict) -> bool:
    """Return True if character has a non-empty structured relationship field."""
    for field in _CHARACTER_INTEREST_FIELDS:
        value = str(char.get(field) or "").strip()
        if value and len(value) >= 4:
            return True
    return False


def _matches_any_pattern(text: str, patterns: list[str]) -> bool:
    """Return True when text matches any semantic regex pattern."""
    return any(re.search(pattern, text) for pattern in patterns)


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
    shallow_motivation_count = 0
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

        # v6.6.18: Structured-field-first check
        has_motivation = _character_has_structured_goal(char)
        has_conflict = _character_has_structured_conflict(char)
        has_interest = _character_has_structured_interest(char)

        # Fallback to description keyword scan if structured fields are absent
        if not has_motivation:
            has_motivation = _matches_any_pattern(description, _CHARACTER_GOAL_PATTERNS)
        if not has_conflict:
            has_conflict = _matches_any_pattern(description, _CHARACTER_CONFLICT_PATTERNS)
        if not has_interest:
            interest_pattern = "|".join(re.escape(w) for w in _CHARACTER_RELATIONSHIP_WORDS)
            has_interest = bool(re.search(interest_pattern, description)) or _matches_any_pattern(
                description, _CHARACTER_INTEREST_PATTERNS
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

        # v6.6.4 / v6.6.18: SHALLOW_CHARACTER_MOTIVATION
        # Protagonist/antagonist require all three; supporting needs at least 2/3
        role = _normalize_text(char.get("role", ""))
        if role in ("protagonist", "antagonist"):
            required = 3
        else:
            required = 2
        score = sum([has_motivation, has_conflict, has_interest])
        if score < required:
            shallow_motivation_count += 1

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

    if shallow_motivation_count >= max(1, len(dict_characters) // 2):
        issues.append(
            GenesisQualityIssue(
                code="SHALLOW_CHARACTER_MOTIVATION",
                severity="warning",
                message=f"{shallow_motivation_count} 个角色缺少目标、矛盾、秘密或利益关系",
                section="characters",
                suggestion="角色应包含具体目标、内在矛盾/秘密、与主角的利益关系",
            )
        )

    return issues


# v6.6.18: Expanded faction semantic vocabularies
_FACTION_RESOURCES_FIELDS = ("resources", "means", "assets", "capabilities")
_FACTION_ACTION_FIELDS = ("current_action", "stage_action", "action", "operations")
_FACTION_ATTITUDE_FIELDS = (
    "relationship_with_protagonist", "attitude_toward_protagonist", "attitude",
)
_FACTION_ACTION_WORDS = [
    "压低", "掩盖", "修补", "收集", "调度", "授权", "接管", "限制", "防范",
    "封锁", "外泄", "抹平", "追索", "传播", "监控", "协助调查", "悄悄修补",
    "行动", "出击", "围剿", "拉拢", "监视", "渗透", "暗杀", "策反", "压制",
    "扶植", "收购", "毁灭", "保护", "驱逐", "结盟", "背叛", "试探", "追捕",
    "救援",
]
_FACTION_RESOURCES_WORDS = [
    "权限", "接口", "记录库", "档案链", "安防网络", "调控接口", "验证协议",
    "私人影像", "证词", "潮汐日志", "控制记录", "系统权限", "资源", "手段",
    "武器", "资金", "技术", "人力", "情报", "网络", "势力", "地盘", "产业",
    "传承", "秘术", "科技", "资本", "人脉", "丹药", "功法", "秘籍",
]


def _faction_has_structured_resources(fac: dict) -> bool:
    """Return True if faction has a non-empty structured resources/means field."""
    for field in _FACTION_RESOURCES_FIELDS:
        value = str(fac.get(field) or "").strip()
        if value and len(value) >= 4:
            return True
    return False


def _faction_has_structured_action(fac: dict) -> bool:
    """Return True if faction has a non-empty structured action field."""
    for field in _FACTION_ACTION_FIELDS:
        value = str(fac.get(field) or "").strip()
        if value and len(value) >= 4:
            return True
    return False


def _faction_has_structured_attitude(fac: dict) -> bool:
    """Return True if faction has a non-empty structured relationship field."""
    for field in _FACTION_ATTITUDE_FIELDS:
        value = str(fac.get(field) or "").strip()
        if value and len(value) >= 4:
            return True
    return False


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
    shallow_action_count = 0
    for fac in dict_factions:
        name = _normalize_text(fac.get("name", ""))
        description = _normalize_text(fac.get("description", ""))
        relationship = _normalize_text(
            fac.get("relationship_with_protagonist", "")
        )
        combined = description + " " + relationship

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
                combined,
            )
        )
        # v6.6.18: attitude from structured fields also counts
        if not has_conflict:
            has_conflict = _faction_has_structured_attitude(fac)

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

        # v6.6.4 / v6.6.18: SHALLOW_FACTION_ACTION
        has_resources = _faction_has_structured_resources(fac)
        has_action = _faction_has_structured_action(fac)

        # Fallback to description keyword scan
        if not has_resources:
            resources_pattern = "|".join(re.escape(w) for w in _FACTION_RESOURCES_WORDS)
            has_resources = bool(re.search(resources_pattern, combined))
        if not has_action:
            action_pattern = "|".join(re.escape(w) for w in _FACTION_ACTION_WORDS)
            has_action = bool(re.search(action_pattern, combined))

        if not (has_resources and has_action):
            shallow_action_count += 1

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

    if shallow_action_count >= max(1, len(dict_factions) // 2):
        issues.append(
            GenesisQualityIssue(
                code="SHALLOW_FACTION_ACTION",
                severity="warning",
                message=f"{shallow_action_count} 个势力缺少资源/手段或阶段行动",
                section="factions",
                suggestion="势力应包含资源/手段和对主角采取的阶段行动",
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
        issues.extend(_check_instruction_depth(instructions))

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
    if scaffold_issue:
        score = 0.0

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


# ── v6.9.0: Creative Contract Generation ──────────────────────────────────


def generate_launch_profile(
    user_idea: str,
    genre_profile: GenreProfile,
    llm_caller: Any = None,
) -> ProjectLaunchProfile:
    """Generate a ProjectLaunchProfile from user idea and genre profile.

    Args:
        user_idea: User's creative idea/premise text
        genre_profile: Genre profile template to use
        llm_caller: Optional LLM caller for real mode (stub mode uses defaults)

    Returns:
        ProjectLaunchProfile with fields populated from genre defaults
    """
    # Stub mode: generate deterministic profile from genre defaults
    if llm_caller is None:
        return _generate_stub_launch_profile(user_idea, genre_profile)

    # Real mode: call LLM to generate profile
    return _generate_llm_launch_profile(user_idea, genre_profile, llm_caller)


def _generate_stub_launch_profile(
    user_idea: str,
    genre_profile: GenreProfile,
) -> ProjectLaunchProfile:
    """Generate a deterministic launch profile for stub mode."""
    # Extract genre family from profile_id
    genre_family = genre_profile.profile_id.split("_")[0] if "_" in genre_profile.profile_id else genre_profile.profile_id

    # Build core hook from user idea (first 100 chars)
    core_hook = user_idea[:100].strip() if user_idea else genre_profile.default_payoff_loop

    return ProjectLaunchProfile(
        target_reader="网络小说读者",
        market_lane=genre_profile.profile_id,
        genre_family=genre_family,
        subgenre="",
        title_promise="",
        core_hook=core_hook,
        primary_payoff_loop=genre_profile.default_payoff_loop,
        secondary_payoff_loops=[],
        protagonist_growth_engine="",
        commercial_comps=[],
        first_30_chapter_strategy="",
        hard_do_not_drift_rules=genre_profile.profile_specific_rules.get("avoid_patterns", []),
    )


def _generate_llm_launch_profile(
    user_idea: str,
    genre_profile: GenreProfile,
    llm_caller: Any,
) -> ProjectLaunchProfile:
    """Generate launch profile using LLM."""
    # Build prompt for LLM
    prompt = f"""根据以下用户创意和类型配置，生成项目启动配置。

用户创意：
{user_idea}

类型配置：
- profile_id: {genre_profile.profile_id}
- 默认读者期望: {', '.join(genre_profile.default_reader_expectations)}
- 默认回报循环: {genre_profile.default_payoff_loop}
- 开篇要求: {', '.join(genre_profile.opening_requirements)}
- 常见毒点: {', '.join(genre_profile.common_poison_points)}

请生成以下JSON格式的项目启动配置：
{{
    "target_reader": "目标读者群体",
    "market_lane": "市场赛道",
    "genre_family": "类型家族",
    "subgenre": "子类型",
    "title_promise": "标题承诺",
    "core_hook": "核心钩子",
    "primary_payoff_loop": "主要回报循环",
    "secondary_payoff_loops": ["次要回报循环1", "次要回报循环2"],
    "protagonist_growth_engine": "主角成长引擎",
    "commercial_comps": ["商业对标1", "商业对标2"],
    "first_30_chapter_strategy": "前30章策略",
    "hard_do_not_drift_rules": ["禁止漂移规则1", "禁止漂移规则2"]
}}

只返回JSON，不要其他文字。"""

    try:
        # Call LLM
        response = llm_caller(prompt)
        # Parse JSON response
        data = json.loads(response)
        return ProjectLaunchProfile(**data)
    except (json.JSONDecodeError, Exception) as e:
        # Fallback to stub mode on error
        return _generate_stub_launch_profile(user_idea, genre_profile)


def generate_genre_contract(
    launch_profile: ProjectLaunchProfile,
    genre_profile: GenreProfile,
    llm_caller: Any = None,
) -> GenreContract:
    """Generate a GenreContract from launch profile and genre profile.

    Args:
        launch_profile: Project launch profile
        genre_profile: Genre profile template
        llm_caller: Optional LLM caller for real mode

    Returns:
        GenreContract with fields populated
    """
    # Stub mode: generate deterministic contract
    if llm_caller is None:
        return _generate_stub_genre_contract(launch_profile, genre_profile)

    # Real mode: call LLM to generate contract
    return _generate_llm_genre_contract(launch_profile, genre_profile, llm_caller)


def _generate_stub_genre_contract(
    launch_profile: ProjectLaunchProfile,
    genre_profile: GenreProfile,
) -> GenreContract:
    """Generate a deterministic genre contract for stub mode."""
    # Build promise statement from launch profile
    promise_statement = f"这是一部{genre_profile.profile_id}类型的小说，核心承诺：{launch_profile.primary_payoff_loop}"

    # Get editor weights from genre profile
    editor_weights = genre_profile.editor_weight_profile

    return GenreContract(
        genre_id=genre_profile.profile_id,
        promise_statement=promise_statement,
        reader_expectations=genre_profile.default_reader_expectations,
        must_have_beats=genre_profile.profile_specific_rules.get("must_have_tropes", []),
        allowed_dark_lines=[],
        forbidden_drift=genre_profile.profile_specific_rules.get("avoid_patterns", []),
        payoff_cadence=PayoffCadence(
            minor_payoff=f"每{genre_profile.chapter_rhythm_defaults.get('minor_payoff_frequency', 1)}章",
            visible_upgrade=f"每{genre_profile.chapter_rhythm_defaults.get('visible_upgrade_frequency', 5)}章",
            public_reversal=f"每{genre_profile.chapter_rhythm_defaults.get('public_reversal_frequency', 8)}章",
        ),
        pressure_limits=PressureLimits(
            max_consecutive_heavy=genre_profile.chapter_rhythm_defaults.get("max_consecutive_pressure", 3),
            max_passive_protagonist=2,
        ),
        upgrade_cadence="",
        relationship_cadence="",
        mystery_reveal_cadence="",
        style_constraints=genre_profile.profile_specific_rules.get("style_constraints", []),
        editor_weights=editor_weights,
    )


def _generate_llm_genre_contract(
    launch_profile: ProjectLaunchProfile,
    genre_profile: GenreProfile,
    llm_caller: Any,
) -> GenreContract:
    """Generate genre contract using LLM."""
    # Build prompt for LLM
    prompt = f"""根据以下项目启动配置和类型配置，生成类型合同。

项目启动配置：
- 目标读者: {launch_profile.target_reader}
- 市场赛道: {launch_profile.market_lane}
- 核心钩子: {launch_profile.core_hook}
- 主要回报循环: {launch_profile.primary_payoff_loop}
- 禁止漂移规则: {', '.join(launch_profile.hard_do_not_drift_rules)}

类型配置：
- profile_id: {genre_profile.profile_id}
- 默认读者期望: {', '.join(genre_profile.default_reader_expectations)}
- 必须包含元素: {', '.join(genre_profile.profile_specific_rules.get('must_have_tropes', []))}
- 常见毒点: {', '.join(genre_profile.common_poison_points)}
- 编辑权重: {genre_profile.editor_weight_profile}

请生成以下JSON格式的类型合同：
{{
    "genre_id": "类型ID",
    "promise_statement": "核心承诺声明",
    "reader_expectations": ["读者期望1", "读者期望2"],
    "must_have_beats": ["必须包含节拍1", "必须包含节拍2"],
    "allowed_dark_lines": ["允许的黑暗元素1", "允许的黑暗元素2"],
    "forbidden_drift": ["禁止漂移1", "禁止漂移2"],
    "payoff_cadence": {{
        "minor_payoff": "每X章",
        "visible_upgrade": "每X章",
        "public_reversal": "每X章"
    }},
    "pressure_limits": {{
        "max_consecutive_heavy": 3,
        "max_passive_protagonist": 2
    }},
    "upgrade_cadence": "升级节奏描述",
    "relationship_cadence": "关系发展节奏描述",
    "mystery_reveal_cadence": "悬念揭示节奏描述",
    "style_constraints": ["风格约束1", "风格约束2"],
    "editor_weights": {{
        "weight1": 30,
        "weight2": 25
    }}
}}

只返回JSON，不要其他文字。"""

    try:
        # Call LLM
        response = llm_caller(prompt)
        # Parse JSON response
        data = json.loads(response)

        # Parse nested objects
        if "payoff_cadence" in data and isinstance(data["payoff_cadence"], dict):
            data["payoff_cadence"] = PayoffCadence(**data["payoff_cadence"])
        if "pressure_limits" in data and isinstance(data["pressure_limits"], dict):
            data["pressure_limits"] = PressureLimits(**data["pressure_limits"])

        return GenreContract(**data)
    except (json.JSONDecodeError, Exception) as e:
        # Fallback to stub mode on error
        return _generate_stub_genre_contract(launch_profile, genre_profile)


def check_project_ready_for_production(
    project_id: str,
    repo: Any,
) -> bool:
    """Check if a project is ready for chapter production.

    A project is ready if it has:
    1. A launch_profile in project_creative_contracts
    2. A genre_contract in project_creative_contracts
    3. The genre_contract has approved=True in its contract_data JSON

    Args:
        project_id: Project identifier
        repo: Repository instance with creative contracts methods

    Returns:
        True if project is ready for production
    """
    try:
        # Check for launch profile
        launch_profile_row = repo.get_creative_contract(project_id, "launch_profile")
        if not launch_profile_row:
            return False

        # Check for genre contract
        genre_contract_row = repo.get_creative_contract(project_id, "genre_contract")
        if not genre_contract_row:
            return False

        # Parse contract_data JSON to check approved field
        contract_data_str = genre_contract_row.get("contract_data", "{}")
        if isinstance(contract_data_str, str):
            contract_data = json.loads(contract_data_str)
        else:
            contract_data = contract_data_str

        # Check if genre contract is approved
        if not contract_data.get("approved", False):
            return False

        return True
    except Exception:
        return False
