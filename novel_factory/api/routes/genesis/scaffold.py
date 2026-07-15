"""Genesis scaffold generation — fallback draft templates.

This module contains all functions related to generating deterministic
fallback Genesis drafts when real LLM output is incomplete or fails.
"""

from __future__ import annotations

import json
import re
import time
from typing import Callable

from .models import GenesisGenerateRequest
from .utils import _as_text
from .normalizer import (
    _normalize_genesis_draft,
    _dedupe_genesis_draft,
)
from .progress import (
    GENESIS_SEGMENT_LABELS,
    GENESIS_INSTRUCTION_CHUNK_SIZE,
)


def _project_description_from_body(body: GenesisGenerateRequest) -> str:
    """Build a project description when the provider omits project_updates."""
    title = body.title.strip() or "未命名项目"
    genre = body.genre.strip() or "小说"
    premise = body.premise.strip()
    if premise:
        return f"《{title}》是一部{genre}题材长篇小说。{premise}"
    return f"《{title}》是一部{genre}题材长篇小说，围绕主角的成长、冲突升级和核心谜团展开。"


def _target_word_count(body: GenesisGenerateRequest) -> int:
    chapters = max(body.target_chapters, 1)
    return max(body.target_words // chapters, 1500)


def _infer_protagonist_name(body: GenesisGenerateRequest) -> str:
    """Infer a concrete protagonist name from user input when possible."""
    source = f"{body.title} {body.premise}"
    patterns = [
        r"([\u4e00-\u9fff]{2,4})作为",
        r"主角[：:，,]?\s*([\u4e00-\u9fff]{2,4})",
    ]
    generic = {
        "故事",
        "异常",
        "系统",
        "现实",
        "修正",
        "修正员",
        "处理局",
        "普通人",
        "政府",
        "地球",
    }
    for pattern in patterns:
        for match in re.finditer(pattern, source):
            name = match.group(1).strip()
            if name and name not in generic and len(name) <= 4:
                return name
    return "林泽" if "异常" in source or "修正" in source else "沈砚"


def _is_anomaly_genesis(body: GenesisGenerateRequest) -> bool:
    source = f"{body.title} {body.genre} {body.premise}"
    return any(token in source for token in ("异常", "修正员", "异常处理局", "超自然", "灵异"))


def _genre_terms(body: GenesisGenerateRequest) -> dict[str, str]:
    """Return lightweight genre-aware labels for deterministic fallback drafts."""
    text = f"{body.genre} {body.title} {body.premise}".lower()
    if any(token in text for token in ("xianxia", "玄幻", "仙侠", "修仙", "仙帝")):
        return {
            "power": "修炼体系",
            "setting": "修行世界与凡俗秩序并存，力量、资源和势力共同决定人物命运。",
            "resource": "灵气、功法、丹药、秘境和传承",
            "conflict": "宗门、家族、隐秘组织与主角成长路线之间的冲突",
            "tone": "热血、逆袭、压迫后的爆发",
        }
    if any(token in text for token in ("urban", "都市", "科技", "机甲")):
        return {
            "power": "都市能力体系",
            "setting": "现代都市表层秩序下隐藏着技术、资本和特殊力量的暗线博弈。",
            "resource": "技术资源、资本、人脉和关键情报",
            "conflict": "校园、财阀、官方机构与地下势力围绕主角能力展开争夺",
            "tone": "爽感、成长、现实压迫下的反击",
        }
    if any(token in text for token in ("sci", "科幻", "未来")):
        return {
            "power": "科技规则体系",
            "setting": "未来科技社会中，资源、算法、组织权力和未知技术共同推动冲突。",
            "resource": "核心技术、数据、能源和实验设施",
            "conflict": "科研机构、企业、官方力量与未知威胁之间的争夺",
            "tone": "探索、危机、理性推演后的震撼",
        }
    return {
        "power": "核心成长体系",
        "setting": "故事世界由日常秩序、隐藏规则和持续升级的外部冲突构成。",
        "resource": "资源、情报、盟友和关键机会",
        "conflict": "主角目标与反派、组织、环境压力之间的持续冲突",
        "tone": "成长、悬念、冲突升级",
    }


def _scaffold_seed_items(seed_draft: dict | None, section: str) -> list[dict]:
    if not isinstance(seed_draft, dict):
        return []
    value = seed_draft.get(section)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _clean_scaffold_entity_name(value: str, fallback: str) -> str:
    name = _as_text(value).strip()
    generic = {
        "",
        "主角",
        "男主",
        "女主",
        "本章主角",
        "角色",
        "反派",
        "配角",
        "未知",
        "无",
    }
    return name if name not in generic and len(name) <= 12 else fallback


def _pick_seed_character(
    characters: list[dict],
    *,
    role_terms: tuple[str, ...],
    fallback: str,
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()
    for item in characters:
        role_text = _as_text(item.get("role", "")).lower()
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if not name or name in exclude:
            continue
        if any(term in role_text for term in role_terms):
            return name
    for item in characters:
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if name and name not in exclude:
            return name
    return fallback


def _pick_seed_faction(
    factions: list[dict],
    *,
    preferred_terms: tuple[str, ...],
    fallback: str,
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()
    for item in factions:
        text = " ".join(
            _as_text(item.get(key, ""))
            for key in ("name", "type", "description", "relationship_with_protagonist")
        )
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if name and name not in exclude and any(term in text for term in preferred_terms):
            return name
    for item in factions:
        name = _clean_scaffold_entity_name(item.get("name", ""), "")
        if name and name not in exclude:
            return name
    return fallback


def _detect_scaffold_story_mode(body: GenesisGenerateRequest, seed_draft: dict | None) -> str:
    seed_text = ""
    if isinstance(seed_draft, dict):
        seed_text = json.dumps(seed_draft, ensure_ascii=False)[:12000]
    text = f"{body.title} {body.genre} {body.premise} {seed_text}"
    if any(term in text for term in ("召唤", "神军", "战灵", "异兽潮", "觉醒者", "职业评级")):
        return "urban_summon"
    if any(term in text for term in ("签到", "打卡", "奖励", "返现", "系统奖励")):
        return "urban_signin"
    if _is_anomaly_genesis(body) or any(term in text for term in ("异常处理", "修正系统", "同化")):
        return "anomaly"
    if any(term in text for term in ("修仙", "宗门", "灵根", "仙帝", "玄幻")):
        return "xianxia"
    return "generic"


def _default_scaffold_entities(
    body: GenesisGenerateRequest,
    seed_draft: dict | None,
) -> dict[str, str]:
    mode = _detect_scaffold_story_mode(body, seed_draft)
    characters = _scaffold_seed_items(seed_draft, "characters")
    factions = _scaffold_seed_items(seed_draft, "factions")

    mode_defaults = {
        "urban_summon": {
            "protagonist": "陆沉",
            "ally": "林破军",
            "second_ally": "苏晚晴",
            "antagonist": "赵天罡",
            "observer": "军方观察员",
            "primary_faction": "江海市城防军",
            "rival_faction": "赵家",
            "hidden_faction": "深渊黑潮",
            "neutral_faction": "觉醒者协会",
        },
        "urban_signin": {
            "protagonist": "林辰",
            "ally": "秦伯",
            "second_ally": "苏晚晴",
            "antagonist": "赵天朗",
            "observer": "帝豪经理",
            "primary_faction": "帝豪酒店",
            "rival_faction": "赵家",
            "hidden_faction": "猩红之夜",
            "neutral_faction": "江城商会",
        },
        "anomaly": {
            "protagonist": "林泽",
            "ally": "许知夏",
            "second_ally": "顾清禾",
            "antagonist": "魏承霜",
            "observer": "周砚白",
            "primary_faction": "异常处理局深城分部",
            "rival_faction": "监管组第七办公室",
            "hidden_faction": "白塔观测会",
            "neutral_faction": "旧城区互助网络",
        },
        "xianxia": {
            "protagonist": "沈砚",
            "ally": "洛青辞",
            "second_ally": "白迟",
            "antagonist": "陆怀川",
            "observer": "藏经阁守阁人",
            "primary_faction": "青云宗",
            "rival_faction": "陆家",
            "hidden_faction": "上古秘境",
            "neutral_faction": "万宝楼",
        },
        "generic": {
            "protagonist": _infer_protagonist_name(body),
            "ally": "顾清禾",
            "second_ally": "林越",
            "antagonist": "陆怀川",
            "observer": "闻人述",
            "primary_faction": "主线组织",
            "rival_faction": "敌对势力",
            "hidden_faction": "隐藏势力",
            "neutral_faction": "中立情报方",
        },
    }
    defaults = mode_defaults[mode]
    protagonist = _pick_seed_character(
        characters,
        role_terms=("protagonist", "主角", "男主", "女主"),
        fallback=defaults["protagonist"],
    )
    antagonist = _pick_seed_character(
        characters,
        role_terms=("antagonist", "反派", "敌"),
        fallback=defaults["antagonist"],
        exclude={protagonist},
    )
    ally = _pick_seed_character(
        characters,
        role_terms=("supporting", "配角", "盟友", "support"),
        fallback=defaults["ally"],
        exclude={protagonist, antagonist},
    )
    second_ally = _pick_seed_character(
        characters,
        role_terms=("supporting", "配角", "盟友", "support"),
        fallback=defaults["second_ally"],
        exclude={protagonist, antagonist, ally},
    )

    primary_faction = _pick_seed_faction(
        factions,
        preferred_terms=("军", "官方", "学院", "大学", "协会", "宗门", "集团", "酒店", "主角"),
        fallback=defaults["primary_faction"],
    )
    rival_faction = _pick_seed_faction(
        factions,
        preferred_terms=("敌", "对立", "豪门", "赵家", "陆家", "监管", "黑市", "反派"),
        fallback=defaults["rival_faction"],
        exclude={primary_faction},
    )
    hidden_faction = _pick_seed_faction(
        factions,
        preferred_terms=("深渊", "黑潮", "裂缝", "隐藏", "神秘", "异界", "白塔", "黑市", "幕后"),
        fallback=defaults["hidden_faction"],
        exclude={primary_faction, rival_faction},
    )
    neutral_faction = _pick_seed_faction(
        factions,
        preferred_terms=("协会", "大学", "商会", "情报", "中立", "互助", "医疗"),
        fallback=defaults["neutral_faction"],
        exclude={primary_faction, rival_faction, hidden_faction},
    )

    return {
        "mode": mode,
        "protagonist": protagonist,
        "ally": ally,
        "second_ally": second_ally,
        "antagonist": antagonist,
        "observer": defaults["observer"],
        "primary_faction": primary_faction,
        "rival_faction": rival_faction,
        "hidden_faction": hidden_faction,
        "neutral_faction": neutral_faction,
    }


def _build_scaffold_instruction_templates(
    mode: str,
    entities: dict[str, str],
) -> list[tuple[str, str, str, str, str, list[str], str, str]]:
    protagonist = entities["protagonist"]
    ally = entities["ally"]
    second_ally = entities["second_ally"]
    antagonist = entities["antagonist"]
    observer = entities["observer"]
    primary_faction = entities["primary_faction"]
    rival_faction = entities["rival_faction"]
    hidden_faction = entities["hidden_faction"]
    neutral_faction = entities["neutral_faction"]

    if mode == "urban_summon":
        return [
            (
                f"{protagonist}在觉醒日公开验证F级召唤师评级，必须保住母亲遗物并证明自己不是家族废物",
                "江海大学觉醒广场",
                f"{rival_faction}与{antagonist}的当众羞辱",
                f"{protagonist}被判定只能召唤灰铁战灵；{antagonist}推动退学和逐出家族；母亲古戒在精神力崩溃时激活帝皇序列",
                f"{protagonist}召出第一名灰铁战灵并挡下雷系压迫，F级废柴标签第一次被撕开裂缝",
                [f"{protagonist}完成觉醒仪式", f"{antagonist}当众打压召唤师评级", f"青铜古戒激活第一名灰铁战灵"],
                "灰铁战灵单膝跪地称王，检测屏却显示召唤位仍为零",
                "下一章必须解释召唤位异常，并让校园评级规则继续压迫主角",
            ),
            (
                f"{protagonist}在实战课测试召唤位异常，目标是用低阶战灵打破召唤师只能当后勤的结论",
                "江海大学实战训练场",
                "导师评级体系和高阶学生围观施压",
                f"{ally}观察战灵队列稳定性；{protagonist}让十名灰铁战灵完成盾墙、突刺、轮换；高阶学生强行挑战并被军阵压制",
                "学院数据库记录到异常统御波形，召唤师评级从个人废柴转为制度争议",
                [f"{protagonist}测试十名战灵同步行动", f"{ally}发现精神负荷没有上升", "战灵军阵击退高阶学生挑战"],
                "训练场后台弹出一条被封存的军团召唤路径",
                "下一章必须围绕军团召唤路径和协会注册资格展开",
            ),
            (
                f"{protagonist}申请觉醒者协会注册，必须在制度刁难下拿到独立接任务资格",
                f"{neutral_faction}评级大厅",
                f"{neutral_faction}的F级召唤师限制条款",
                f"评级员拒绝给{protagonist}前线资格；{second_ally}用治疗增幅短暂强化战灵；城门裂缝警报打断注册流程",
                f"{protagonist}以临时征召身份奔赴城门，获得第一次公开战场验证机会",
                [f"{protagonist}提交注册申请", f"{second_ally}证明治疗术可增幅召唤物", "城门裂缝警报迫使协会临时放行"],
                "城门外传来兽潮预警，后勤名单上只有陆沉一个召唤师",
                "下一章必须让主角在真实兽潮里兑现军团价值",
            ),
            (
                f"{protagonist}在东海城门兽潮中救下被围连队，目标是证明量产战灵能改变战场数量劣势",
                "东海城门外防线",
                f"{hidden_faction}先遣兽潮与军方旧战法",
                f"{primary_faction}连队被异兽切断；{protagonist}召出百名灰铁战灵组成三层盾枪阵；{ally}确认战损后战灵可重组",
                f"{primary_faction}把{protagonist}列为特殊统帅型觉醒者，豪门开始意识到威胁",
                [f"{protagonist}抵达城门防线", "百名灰铁战灵组成盾枪阵", f"{ally}救下被围连队并提交军报"],
                "军报备注写着：一人成军雏形，建议封存",
                "下一章必须让豪门势力因军报介入并制造资源封锁",
            ),
            (
                f"{protagonist}面对豪门资源封锁，目标是夺回召唤材料并建立第一处军团锚点",
                f"{rival_faction}控制的材料仓库",
                f"{rival_faction}的合同陷阱和私军拦截",
                f"{antagonist}冻结{protagonist}采购权限；{protagonist}带战灵潜入材料仓库查账；他用战功授权反向扣押一批灰铁核心",
                "第一座临时兵营锚点完成，战灵数量上限从百名提升到千名",
                [f"{antagonist}冻结召唤材料渠道", f"{protagonist}查出材料被豪门截留", "战功授权帮助主角建立临时兵营锚点"],
                "兵营锚点深处出现母亲留下的帝皇序列第二条命令",
                "下一章必须解锁千人军阵，并把压力转回城防战场",
            ),
            (
                f"{protagonist}用千人军阵迎击第二波裂缝兽潮，目标是让城防军承认军团召唤的战略价值",
                "东海二号裂缝前沿",
                f"{hidden_faction}的淹没式兽潮",
                f"常规高阶觉醒者被数量压制；{protagonist}把千名战灵拆成盾、枪、弓三阵；{ally}用军方炮火配合战灵轮换推进",
                f"裂缝前沿被夺回，{protagonist}获得军方临时指挥权限",
                ["高阶觉醒者防线被冲散", f"{protagonist}部署千人三阵", f"{primary_faction}授予临时指挥权限"],
                "裂缝深处传来能让战灵集体失控的号角声",
                "下一章必须处理战灵失控风险，并让后勤核心发挥作用",
            ),
            (
                f"{protagonist}处理战灵失控风险，目标是借助治疗增幅稳定军团意志",
                "战地医疗营",
                "异界号角和召唤反噬质疑",
                f"{second_ally}发现治疗术能修复战灵锚点；{protagonist}让失控战灵撤入医疗阵；{antagonist}借机指控军团召唤不可控",
                "生命增幅与军团锚点建立协同，主角阵营形成前线后勤闭环",
                [f"{second_ally}测试治疗术增幅战灵", f"{protagonist}压住失控战灵", f"{antagonist}发起不可控指控"],
                "治疗阵短暂照出一名黄金战灵的影子",
                "下一章必须追查黄金战灵来源，并揭露异界渗透",
            ),
            (
                f"{protagonist}追查黄金战灵影子，目标是找出城内谁在给兽潮传递军团情报",
                "城内黑市与裂缝物资站",
                f"{hidden_faction}潜伏者和{rival_faction}利益链",
                f"{protagonist}跟踪异常材料流向黑市；{ally}截获加密军报；潜伏者释放腐蚀瘴气试图污染战灵锚点",
                f"主角确认兽潮不是随机爆发，而是有人按城防弱点引导",
                [f"{protagonist}进入黑市追查材料", f"{ally}截获被篡改军报", "潜伏者用腐蚀瘴气攻击兵营锚点"],
                "被抓潜伏者临死前说出第七次黑潮已经进城",
                "下一章必须让主角在制度审查中公开部分证据",
            ),
            (
                f"{protagonist}在联合审查会上公开兽潮渗透证据，目标是打破召唤师后勤化军改",
                f"{neutral_faction}联合审查会",
                f"{rival_faction}的舆论绞杀和制度否认",
                f"{antagonist}质疑战功数据造假；{protagonist}展示战灵视角记录；{primary_faction}证明二号裂缝战果无法由个人高阶战力完成",
                "召唤师后勤化政策被暂停，主角从个体逆袭进入制度改写阶段",
                [f"{antagonist}发起审查", f"{protagonist}公开战灵视角证据", f"{primary_faction}为军团战果背书"],
                "审查会外，城墙结界同时亮起七处黑潮裂缝",
                "下一章必须以阶段高潮证明一人成国的雏形",
            ),
            (
                f"{protagonist}面对七处裂缝同时开启，目标是用军团分线守城完成第一阶段封神",
                "江海市七段城墙",
                f"{hidden_faction}发动的第七次黑潮前奏",
                f"{protagonist}把战灵军团拆分到七段城墙；{second_ally}维持生命增幅；{ally}接入军方炮火网；主角亲自镇守最危险主裂缝",
                "江海市守住第一轮黑潮，主角获得一人成国称号但也被更高层异界意志锁定",
                ["七处裂缝同时开启", f"{protagonist}分线部署军团", "主裂缝中的异界意志锁定主角"],
                "主裂缝深处传来王座召唤，要求陆沉交出帝皇序列",
                "下一阶段必须围绕帝皇序列来源和真正黑潮王座展开",
            ),
        ]

    generic_locations = ["开场核心场景", "资源交易现场", "第一处对抗地点", "组织内部节点", "公开审查场", "危机前线", "隐藏档案处", "盟友据点", "阶段决战场", "下一阶段入口"]
    generic_actions = [
        ("保住关键资源", "现实压力和身份否定", "主角夺回第一份主动权"),
        ("追查资源来源", "敌对势力的封锁", "主角拿到半份证据"),
        ("进入核心组织", "内部规则和追兵", "幕后操盘者露出线索"),
        ("验证新能力", "同伴质疑和外部危机", "能力第一次公开兑现"),
        ("反击资源封锁", "合同陷阱和舆论打压", "主角建立稳定据点"),
        ("处理外部危机", "数量劣势和规则限制", "主角获得临时权限"),
        ("修复能力代价", "反噬风险和敌人指控", "团队协作关系成型"),
        ("追查城内内鬼", "潜伏者和利益链", "主角确认危机被人为引导"),
        ("公开阶段证据", "制度审查和舆论围攻", "旧规则被迫让步"),
        ("完成阶段决战", "多线危机和最终压迫", "主角取得第一阶段胜利"),
    ]
    templates: list[tuple[str, str, str, str, str, list[str], str, str]] = []
    for idx, (goal, obstacle, result) in enumerate(generic_actions, start=1):
        location = generic_locations[idx - 1]
        templates.append(
            (
                f"{protagonist}在{location}{goal}，目标是在{obstacle}下推动局势进入新阶段",
                location,
                obstacle,
                f"{protagonist}在{location}{goal}；{ally}针对{obstacle}提供第 {idx} 轮关键协助；{antagonist}或{rival_faction}制造阻碍；{result}",
                result,
                [f"{protagonist}在{location}{goal}", f"{ally}针对{obstacle}提供协助", f"{antagonist}制造第 {idx} 轮阻碍后被主角反制"],
                f"{hidden_faction}留下第 {idx} 条更高层线索",
                f"下一章必须承接第 {idx} 条线索，并让主角付出新的可见代价",
            )
        )
    return templates


def _generate_genesis_scaffold(
    body: GenesisGenerateRequest,
    seed_draft: dict | None = None,
) -> dict:
    """Create a seed-aware editable Genesis draft when live output is incomplete."""
    title = body.title.strip() or "未命名项目"
    genre = body.genre.strip() or "小说"
    premise = body.premise.strip() or f"围绕《{title}》展开的{genre}故事。"
    target_chapters = max(body.target_chapters, 1)
    target_words = _target_word_count(body)
    arc_mid = max(1, min(target_chapters, max(3, target_chapters // 3)))
    arc_two_end = max(arc_mid + 1, min(target_chapters, arc_mid * 2))
    terms = _genre_terms(body)
    entities = _default_scaffold_entities(body, seed_draft)
    mode = entities["mode"]
    protagonist = entities["protagonist"]
    ally = entities["ally"]
    second_ally = entities["second_ally"]
    antagonist = entities["antagonist"]
    observer = entities["observer"]
    primary_faction = entities["primary_faction"]
    rival_faction = entities["rival_faction"]
    hidden_faction = entities["hidden_faction"]
    neutral_faction = entities["neutral_faction"]

    instruction_templates = _build_scaffold_instruction_templates(mode, entities)
    instructions: list[dict] = []
    for chapter in range(1, target_chapters + 1):
        (
            objective,
            primary_location,
            opposing_force,
            key_events,
            visible_result,
            action_chain,
            ending_hook,
            continuity_seed,
        ) = instruction_templates[(chapter - 1) % len(instruction_templates)]
        if chapter > len(instruction_templates):
            objective = f"{protagonist}承接第 {chapter - 1} 章后果，在新战场解决第 {chapter} 章核心危机"
            key_events = f"{protagonist}复盘上一章代价；{ally}带来第 {chapter} 章新线索；{antagonist}升级阻挠；主角用已建立能力完成一次可见兑现"
            ending_hook = f"第 {chapter} 章结尾出现下一阶段更高层威胁"
            continuity_seed = f"下一章必须承接第 {chapter} 章新威胁，并保留主角上一章取得的资源或权限"
            action_chain = [f"复盘第 {chapter - 1} 章后果", "追查新线索", "完成能力兑现"]
            visible_result = "主角能力、资源或阵营关系产生可见升级"
            primary_location = f"第 {chapter} 章新战场"
            opposing_force = f"{hidden_faction}升级后的外部压力"
        instructions.append({
            "chapter_number": chapter,
            "objective": objective,
            "protagonist": protagonist,
            "primary_location": primary_location,
            "opposing_force": opposing_force,
            "action_chain": action_chain,
            "visible_result": visible_result,
            "state_change": f"第 {chapter} 章结束时，{protagonist}相对上一章获得新的资源、权限或敌情，但也暴露新的风险",
            "key_events": key_events,
            "plots_to_plant": [f"{hidden_faction}的真正目标"] if chapter == 1 else [],
            "plots_to_resolve": [],
            "emotion_tone": terms["tone"],
            "ending_hook": ending_hook,
            "continuity_seed": continuity_seed,
            "word_target": target_words,
        })

    if mode == "urban_summon":
        world_settings = [
            {
                "title": "觉醒纪元与都市防线",
                "category": "时代背景",
                "content": "现代都市在觉醒者体系、城墙防线和空间裂缝威胁下维持秩序，天赋评级决定教育、军功和资源分配。",
            },
            {
                "title": "军团召唤与评级误判",
                "category": "能力规则",
                "content": f"{protagonist}表面是F级量产召唤师，实则可用统御锚点替代精神微操，将低阶战灵组成军团。",
            },
            {
                "title": "守城爽点循环",
                "category": "叙事规则",
                "content": "每轮冲突必须包含压迫、召唤扩编、军阵兑现、敌方反噬和更高层裂缝威胁。",
            },
        ]
        characters = [
            {
                "name": protagonist,
                "role": "protagonist",
                "description": f"F级召唤师，目标是以军团召唤证明战略价值并守住城市。\n内在矛盾/秘密: 帝皇序列来源未明，过早暴露会引来豪门和异界双重抹杀。\n与主角利益关系: 本人，所有资源、军功和身份变化都直接推动一人成国路线。",
                "traits": "隐忍、强硬、战场判断快、重视普通人伤亡",
            },
            {
                "name": ally,
                "role": "supporting",
                "description": f"{primary_faction}关键支持者，目标是找到能打破兽潮数量劣势的统帅型觉醒者。\n与主角利益关系: 为{protagonist}提供军方背书和实战战场。",
                "traits": "务实、果断、重军功",
            },
            {
                "name": second_ally,
                "role": "supporting",
                "description": f"治疗或后勤核心，目标是建立不按评级放弃低阶觉醒者的支援体系。\n与主角利益关系: 强化召唤军团续航，是主角军团闭环的重要拼图。",
                "traits": "冷静、善良、有豪门资源但不盲从豪门",
            },
            {
                "name": antagonist,
                "role": "antagonist",
                "description": f"旧秩序代表，目标是维持高评级职业和豪门资源垄断。\n与主角利益关系: 视{protagonist}为动摇制度的威胁，会从舆论、资源和武力层面压制。",
                "traits": "骄傲、强势、擅长调动规则",
            },
        ]
        factions = [
            {
                "name": primary_faction,
                "type": "国家/军方力量",
                "description": "掌握城防、军功和前线资源，当前急需能应对淹没式兽潮的新战法。",
                "relationship_with_protagonist": "潜在靠山和实战舞台",
            },
            {
                "name": rival_faction,
                "type": "豪门/旧秩序势力",
                "description": "依靠高评级觉醒者和资源垄断维持地位，当前试图压制军团召唤复苏。",
                "relationship_with_protagonist": "直接压迫和反噬对象",
            },
            {
                "name": hidden_faction,
                "type": "外部入侵势力",
                "description": "通过裂缝、兽潮和潜伏者冲击城市防线，正在酝酿更大规模黑潮。",
                "relationship_with_protagonist": "长期主线敌人",
            },
            {
                "name": neutral_faction,
                "type": "教育/行业机构",
                "description": "掌握评级、注册和任务资格，当前被既有评价标准限制。",
                "relationship_with_protagonist": "可被战绩改写的制度入口",
            },
        ]
        outlines = [
            {
                "chapters_range": f"1-{arc_mid}",
                "title": "F级压迫与军团觉醒",
                "content": f"阶段冲突: {protagonist}被F级评级和豪门羞辱压入谷底。转折: 帝皇序列让低阶战灵形成军阵。阶段结果: 主角从废柴标签中撕开第一道口子。",
                "level": "arc",
                "sequence": 1,
            },
            {
                "chapters_range": f"{arc_mid + 1}-{arc_two_end}" if arc_mid + 1 <= arc_two_end else f"{arc_mid}",
                "title": "能力验证与军方入场",
                "content": f"阶段冲突: {rival_faction}和评级制度否认召唤师价值。转折: {protagonist}在真实兽潮中用军阵救下{primary_faction}。阶段结果: 军团召唤从个人逆袭升级为战略争夺。",
                "level": "arc",
                "sequence": 2,
            },
            {
                "chapters_range": f"{arc_two_end + 1}-{target_chapters}" if arc_two_end + 1 <= target_chapters else f"{target_chapters}",
                "title": "黑潮前奏与一人成国",
                "content": f"阶段冲突: {hidden_faction}发动更高强度渗透，旧制度仍试图夺走主角战果。转折: 主角分线守城并证明军团召唤可替代单点高阶战力。阶段结果: 一人成国雏形出现，下一阶段引出帝皇序列来源。",
                "level": "arc",
                "sequence": 3,
            },
        ]
        plot_holes = [
            {
                "code": "PH-001",
                "type": "能力伏笔",
                "title": "帝皇序列为何选择主角",
                "description": f"触发场景: {protagonist}F级觉醒时古戒激活。读者表象: 母亲遗物救场。真相方向: 古戒与上古军团召唤禁区有关。预计兑现: 第 {min(target_chapters, 10)} 章后逐步揭示。",
                "planted_chapter": 1,
                "planned_resolve_chapter": min(target_chapters, 10),
                "status": "planted",
            },
            {
                "code": "PH-002",
                "type": "势力伏笔",
                "title": f"{hidden_faction}提前渗透城内",
                "description": f"触发场景: 兽潮总能避开强防线。读者表象: 裂缝随机扩张。真相方向: 城内有人向{hidden_faction}泄露城防信息。预计兑现: 第 {min(target_chapters, 8)} 章。",
                "planted_chapter": 3,
                "planned_resolve_chapter": min(target_chapters, 8),
                "status": "planted",
            },
            {
                "code": "PH-003",
                "type": "关系伏笔",
                "title": f"{second_ally}与军团完全体的关系",
                "description": f"触发场景: {second_ally}治疗术对战灵产生异常增幅。读者表象: 辅助能力适配。真相方向: 生命锚点是军团召唤完全体必要条件。预计兑现: 第 {min(target_chapters, 12)} 章。",
                "planted_chapter": 4,
                "planned_resolve_chapter": min(target_chapters, 12),
                "status": "planted",
            },
        ]
    else:
        world_settings = [
            {
                "title": "故事基础世界",
                "category": "世界观",
                "content": terms["setting"],
            },
            {
                "title": terms["power"],
                "category": "力量规则",
                "content": f"故事的核心成长依赖{terms['resource']}，主角必须通过具体行动逐步兑现能力或资源优势。",
            },
            {
                "title": "冲突结构",
                "category": "叙事规则",
                "content": terms["conflict"],
            },
        ]
        characters = [
            {
                "name": protagonist,
                "role": "protagonist",
                "description": f"《{title}》的核心人物，目标是在压迫和危机中夺回主动权。\n内在矛盾/秘密: 掌握的关键能力或资源尚未被外界理解。\n与主角利益关系: 本人，所有选择推动主线升级。",
                "traits": "克制、果断、能在压力下反击",
            },
            {
                "name": ally,
                "role": "supporting",
                "description": f"主角早期盟友，目标是帮助{protagonist}拿到第一轮关键证据或资源。",
                "traits": "敏锐、可靠、有行动力",
            },
            {
                "name": antagonist,
                "role": "antagonist",
                "description": f"早期对抗者，目标是阻止{protagonist}打破既有秩序。",
                "traits": "强势、谨慎、擅长调动资源",
            },
            {
                "name": observer,
                "role": "supporting",
                "description": f"隐藏线索观察者，目标是测试{protagonist}是否能触及更高层真相。\n内在矛盾/秘密: 掌握关键情报但不会直接替主角解决危机。\n与主角利益关系: 提供方向，同时制造信息压力。",
                "traits": "克制、信息量大、立场暧昧",
            },
        ]
        factions = [
            {
                "name": primary_faction,
                "type": "主线组织",
                "description": "提供任务、资源或冲突舞台，是主角进入更大世界的入口。",
                "relationship_with_protagonist": "既提供机会也形成限制",
            },
            {
                "name": rival_faction,
                "type": "敌对势力",
                "description": "维护旧秩序并压制主角崛起。",
                "relationship_with_protagonist": "早期主要对手",
            },
            {
                "name": hidden_faction,
                "type": "隐藏势力",
                "description": "掌握更高层真相，持续投放线索或威胁。",
                "relationship_with_protagonist": "长期谜团来源",
            },
        ]
        outlines = [
            {
                "chapters_range": f"1-{arc_mid}",
                "title": "开局压迫与能力显形",
                "content": f"{premise} 阶段冲突: {protagonist}在现实压力下保住关键资源。转折: 主角完成第一次可见兑现。阶段结果: 对抗从个人压迫升级为组织关注。",
                "level": "arc",
                "sequence": 1,
            },
            {
                "chapters_range": f"{arc_mid + 1}-{arc_two_end}" if arc_mid + 1 <= arc_two_end else f"{arc_mid}",
                "title": "势力入场与规则碰撞",
                "content": f"阶段冲突: {rival_faction}压制主角扩大影响。转折: {hidden_faction}线索证明危机背后另有操盘者。阶段结果: 主角获得新资源但暴露行动路线。",
                "level": "arc",
                "sequence": 2,
            },
            {
                "chapters_range": f"{arc_two_end + 1}-{target_chapters}" if arc_two_end + 1 <= target_chapters else f"{target_chapters}",
                "title": "阶段高潮与主线升级",
                "content": f"阶段冲突: {protagonist}必须在公开反击和隐藏真相之间选择。转折: 主角把前期资源集中兑现。阶段结果: 第一阶段敌人反噬，更高层危机开启。",
                "level": "arc",
                "sequence": 3,
            },
        ]
        plot_holes = [
            {
                "code": "PH-001",
                "type": "主线谜团",
                "title": f"{hidden_faction}为何关注{protagonist}",
                "description": f"触发场景: {protagonist}第一次反击后出现隐藏线索。读者表象: 偶然被卷入。真相方向: 主角能力或身份与更高层规则有关。预计兑现: 第 {min(target_chapters, 10)} 章。",
                "planted_chapter": 1,
                "planned_resolve_chapter": min(target_chapters, 10),
                "status": "planted",
            },
            {
                "code": "PH-002",
                "type": "势力伏笔",
                "title": f"{rival_faction}背后的资源链",
                "description": f"触发场景: {rival_faction}能提前封锁主角行动。读者表象: 对手资源强。真相方向: 资源链背后连接更高层危机。预计兑现: 第 {min(target_chapters, 8)} 章。",
                "planted_chapter": 2,
                "planned_resolve_chapter": min(target_chapters, 8),
                "status": "planted",
            },
        ]

    return {
        "_meta": {
            "source": "scaffold_fallback",
            "quality_status": "scaffold_fallback",
            "warnings": ["此草案由系统兜底模板生成，不建议直接批准"],
        },
        "project_updates": {"description": _project_description_from_body(body)},
        "world_settings": world_settings,
        "characters": characters,
        "factions": factions,
        "outlines": outlines,
        "plot_holes": plot_holes,
        "instructions": instructions,
    }


def _missing_required_genesis_sections(draft: dict | None) -> list[str]:
    """Return required genesis sections that are absent or empty."""
    if not isinstance(draft, dict):
        from .progress import GENESIS_REQUIRED_SECTIONS
        return list(GENESIS_REQUIRED_SECTIONS.values())
    from .progress import GENESIS_REQUIRED_SECTIONS
    missing: list[str] = []
    project_updates = draft.get("project_updates")
    description = ""
    if isinstance(project_updates, dict):
        description = _as_text(project_updates.get("description", "")).strip()
    else:
        description = _as_text(project_updates).strip()
    if not description:
        missing.append(GENESIS_REQUIRED_SECTIONS["project_description"])
    for key, label in GENESIS_REQUIRED_SECTIONS.items():
        if key == "project_description":
            continue
        value = draft.get(key)
        if isinstance(value, list) and value:
            continue
        if value and not isinstance(value, list):
            continue
        missing.append(label)
    return missing


def _validate_complete_genesis_draft(draft: dict | None) -> tuple[dict | None, list[str]]:
    """Normalize and validate that a generated draft can initialize a project."""
    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft))
    missing = _missing_required_genesis_sections(normalized)
    return normalized, missing


def _incomplete_genesis_message(missing: list[str]) -> str:
    return f"创世草案不完整，缺少：{', '.join(missing)}。请拒绝当前草案后重新生成。"


def _merge_genesis_drafts(base: dict | None, patch: dict | None) -> dict:
    """Merge a missing-section patch into a genesis draft."""
    from .normalizer import _merge_unique_genesis_list
    merged = dict(base or {})
    patch = patch or {}
    if not isinstance(patch, dict):
        return merged

    project_updates = patch.get("project_updates")
    if isinstance(project_updates, dict) and project_updates:
        merged_project = dict(merged.get("project_updates") or {})
        merged_project.update(project_updates)
        merged["project_updates"] = merged_project

    for key in (
        "world_settings",
        "characters",
        "factions",
        "outlines",
        "plot_holes",
        "instructions",
    ):
        incoming = patch.get(key)
        if isinstance(incoming, list) and incoming:
            merged[key] = _merge_unique_genesis_list(merged.get(key) or [], incoming, key)
        elif key not in merged:
            merged[key] = []

    return _dedupe_genesis_draft(merged) or {}


def _fill_missing_genesis_sections(body: GenesisGenerateRequest, draft: dict | None) -> dict:
    """Fill any remaining required Genesis sections from a local editable scaffold.

    v6.6.3: If any section is filled from scaffold, mark the draft with
    _meta.scaffold_sections to track which parts are fallback.
    """
    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft)) or {}
    scaffold = _generate_genesis_scaffold(body, seed_draft=normalized)

    scaffold_sections: list[str] = []

    project_updates = normalized.get("project_updates")
    description = ""
    if isinstance(project_updates, dict):
        description = _as_text(project_updates.get("description", "")).strip()
    else:
        description = _as_text(project_updates).strip()
    if not description:
        normalized["project_updates"] = scaffold["project_updates"]
        scaffold_sections.append("project_updates")

    for key in ("world_settings", "characters", "factions", "outlines", "plot_holes", "instructions"):
        value = normalized.get(key)
        if not isinstance(value, list) or not value:
            normalized[key] = scaffold[key]
            scaffold_sections.append(key)

    # v6.6.3: Mark if any scaffold sections were used
    if scaffold_sections:
        meta = normalized.get("_meta", {})
        if not isinstance(meta, dict):
            meta = {}
        meta["scaffold_sections"] = scaffold_sections
        meta["quality_status"] = "scaffold_fallback"
        meta["warnings"] = [f"以下部分由系统模板补齐：{', '.join(scaffold_sections)}"]
        normalized["_meta"] = meta

    return _dedupe_genesis_draft(normalized) or {}


def _generate_stub_draft(
    body: GenesisGenerateRequest,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Generate a deterministic stub genesis draft.

    v6.7.7: Accepts optional progress callback for SSE streaming.
    In stub mode, simulates realistic progress events with short delays.
    """
    title = body.title or "未命名项目"
    genre = body.genre or "奇幻"
    premise = body.premise or "一个关于冒险与成长的故事"

    def _emit(event_type: str, **kwargs):
        if progress and run_id:
            progress(event_type, {"run_id": run_id, **kwargs})

    # Stub: simulate foundation segment
    _emit("segment_started", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])
    time.sleep(0.05)  # simulate work

    draft: dict = {
        "project_updates": {
            "description": f"《{title}》是一部{genre}题材小说。{premise}",
        },
        "world_settings": [
            {
                "title": "世界观基础",
                "category": "地理",
                "content": f"故事发生在{genre}世界中，存在多个势力和未知领域。",
            },
            {
                "title": "力量体系",
                "category": "规则",
                "content": "修炼体系分为九个大境界，每个境界有初期、中期、后期三个小阶段。",
            },
        ],
    }
    _emit("segment_completed", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])

    # Stub: simulate cast segment
    _emit("segment_started", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])
    time.sleep(0.05)

    draft["characters"] = [
        {
            "name": "主角",
            "role": "protagonist",
            "description": f"《{title}》的核心人物，性格坚毅，有着不为人知的过去。",
            "traits": "聪明、执着、重情义",
        },
        {
            "name": "挚友",
            "role": "supporting",
            "description": "主角的青梅竹马，性格开朗，擅长情报收集。",
            "traits": "机智、幽默、忠诚",
        },
        {
            "name": "反派首领",
            "role": "antagonist",
            "description": "幕后黑手，行事隐秘，目的不明。",
            "traits": "狡猾、冷酷、有魅力",
        },
    ]
    draft["factions"] = [
        {
            "name": "主角所属势力",
            "type": "宗门",
            "description": "主角成长的根据地，历史悠久但近来衰落。",
            "relationship_with_protagonist": "所属",
        },
        {
            "name": "敌对势力",
            "type": "组织",
            "description": "暗中操控局势的神秘组织。",
            "relationship_with_protagonist": "敌对",
        },
    ]
    _emit("segment_completed", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])

    # Stub: simulate plot segment
    _emit("segment_started", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])
    time.sleep(0.05)

    draft["outlines"] = [
        {
            "chapters_range": "1-3",
            "title": "开篇",
            "content": "主角出场，建立日常世界，引出核心冲突。",
            "level": "arc",
            "sequence": 1,
        },
        {
            "chapters_range": "4-6",
            "title": "启程",
            "content": "主角踏上旅程，遇到第一个挑战和盟友。",
            "level": "arc",
            "sequence": 2,
        },
        {
            "chapters_range": "7-10",
            "title": "第一幕高潮",
            "content": "主角面对第一个重大考验，揭示更大的阴谋。",
            "level": "arc",
            "sequence": 3,
        },
    ]
    draft["plot_holes"] = [
        {
            "code": "PH-001",
            "type": "悬念",
            "title": "主角身世之谜",
            "description": "主角的真实身份和家族秘密。",
            "planted_chapter": 1,
            "planned_resolve_chapter": 20,
            "status": "planted",
        },
        {
            "code": "PH-002",
            "type": "伏笔",
            "title": "神秘信物",
            "description": "主角随身携带的古旧物品的来历。",
            "planted_chapter": 1,
            "planned_resolve_chapter": 10,
            "status": "planted",
        },
    ]
    _emit("segment_completed", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])

    # Stub: simulate instructions segment (per-chunk)
    chapter_count = min(body.target_chapters, 10)
    chunk_size = GENESIS_INSTRUCTION_CHUNK_SIZE
    instructions: list = []
    for chunk_start in range(0, chapter_count, chunk_size):
        chunk_end = min(chapter_count, chunk_start + chunk_size)
        _emit("chapter_start", chapter_start=chunk_start + 1, chapter_end=chunk_end,
              label=f"正在生成章节指令 {chunk_start + 1}-{chunk_end}")
        time.sleep(0.03)
        for i in range(chunk_start, chunk_end):
            instructions.append({
                "chapter_number": i + 1,
                "objective": f"第 {i + 1} 章写作指令",
                "key_events": f"关键事件 {i + 1}",
                "emotion_tone": "神秘" if i == 0 else "紧张",
                "word_target": body.target_words // body.target_chapters,
            })
        _emit("chapter_end", chapter_start=chunk_start + 1, chapter_end=chunk_end,
              label=f"章节指令 {chunk_start + 1}-{chunk_end} 完成")
    draft["instructions"] = instructions

    return draft
