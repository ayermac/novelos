"""Deterministic stub LLM provider for tests, demos, and smoke runs."""

from __future__ import annotations

import hashlib
import re

from .provider import LLMProvider
from .openai_compatible import TokenUsage

# Per-chapter content templates — keyed by chapter number for variety
_STORY_TEMPLATES = {
    1: {
        "title": "初入江湖",
        "content": (
            "林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。\n"
            "\u201c你来了。\u201d身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。\n"
            "\u201c你是谁？\u201d林默警觉地问道，手已经摸向腰间的短剑。\n"
            "\u201c我是谁不重要，\u201d黑衣男子缓缓走近，\u201c重要的是，你正在寻找的东西，也在寻找你。\u201d\n"
            "林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？\n"
            "\u201c别紧张，\u201d黑衣男子停下脚步，\u201c我是来帮你的。但你必须做出选择。\u201d\n"
            "\u201c什么选择？\u201d林默紧盯着对方，随时准备出手。\n"
            "\u201c是继续寻找真相，还是保全你现在的平静生活。\u201d黑衣男子的目光变得复杂。\n"
            "林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。\n"
            "\u201c我已经没有退路了，\u201d他终于说道，\u201c不管前面是什么，我都必须走下去。\u201d\n"
            "黑衣男子点了点头。\u201c很好。那么，从现在开始，你要小心身边的每一个人。\u201d\n"
            "说完，他的身影渐渐消失在阴影中，仿佛从未出现过。\n"
            "林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。\n"
            "他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。\n"
            "他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。\n"
            "最后，他只写了一句话：今天，一切都将改变。\n"
            "就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。\n"
            "门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。\n"
            "\u201c救救我，\u201d年轻人喘着气说，\u201c他们\u2026\u2026他们要杀我。\u201d\n"
            "林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。\n"
            "他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。\n"
            "黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。"
        ),
    },
    2: {
        "title": "暗流涌动",
        "content": (
            "苏晚站在天台上，俯瞰着灯火通明的城市。夜风吹动她的长发，她却毫无察觉。\n"
            "手机震动了一下。是一条加密信息：\u201c明天下午三点，老地方见。\u201d\n"
            "她删掉信息，将手机握在手心。三年了，她等的就是这个机会。\n"
            "楼下传来引擎声。一辆黑色轿车停在路边，车门打开，走下来一个西装革履的男人。\n"
            "苏晚认出了他\u2014\u2014陈氏集团的副总裁，周衡。\n"
            "周衡抬头看向天台，仿佛感应到了什么。苏晚迅速退后一步，隐入阴影。\n"
            "\u201c苏小姐，\u201d身后突然响起一个声音，\u201c周总让我来接你。\u201d\n"
            "苏晚转身，看到一个面带微笑的年轻人。她不认识这个人，但对方显然认识她。\n"
            "\u201c我不认识周总。\u201d苏晚平静地说。\n"
            "年轻人笑了笑：\u201c没关系，周总认识你就行。请吧。\u201d\n"
            "苏晚看了看楼下的黑色轿车，又看了看面前的年轻人。她知道，拒绝不是一个选项。\n"
            "\u201c带路。\u201d她说。年轻人侧身做出请的手势。苏晚走向电梯，心中默默盘算着一切。\n"
            "电梯下行的过程中，苏晚注意到年轻人按了负二层的按钮。\n"
            "\u201c不是说去见周总吗？\u201d苏晚问道。\n"
            "\u201c周总在地下车库等你。\u201d年轻人依然面带微笑，\u201c这样更方便。\u201d\n"
            "苏晚不动声色地观察着电梯内的监控摄像头。她知道，从现在开始，每一步都不能走错。\n"
            "电梯门打开，地下车库昏暗的灯光下，那辆黑色轿车已经等在那里了。\n"
            "周衡站在车旁，手中夹着一支尚未点燃的雪茄。看到苏晚走出来，他微微点头。\n"
            "\u201c苏小姐，好久不见。\u201d周衡的声音低沉而富有磁性，\u201c上车吧，我们边走边谈。\u201d\n"
            "苏晚深吸一口气，迈步走向了那辆黑色轿车。车窗上映出她的倒影\u2014\u2014冷静、坚定、毫无畏惧。"
        ),
    },
    3: {
        "title": "风云际会",
        "content": (
            "剑光一闪，三柄暗器同时落地。\n"
            "叶知秋收剑入鞘，神色淡然。围攻他的五人面面相觑，不敢再上前一步。\n"
            "\u201c诸位，\u201d叶知秋缓缓开口，\u201c我无意与各位为敌。但我必须走这条路。\u201d\n"
            "\u201c叶少侠好身手，\u201d为首的老者拱手道，\u201c但前方是禁地，任何人不得擅入。\u201d\n"
            "叶知秋看了老者一眼。此人武功深厚，远非其余四人可比。若是全力一战，胜负难料。\n"
            "\u201c前辈，\u201d叶知秋语气放缓，\u201c三天前，有人在禁地中发现了我师弟的佩剑。\u201d\n"
            "老者面色微变。这个消息他并不知道。\n"
            "\u201c我师弟下山执行任务，至今未归。如果他还活着，我必须找到他。\u201d叶知秋的目光坚定。\n"
            "老者沉默了许久，终于叹了口气：\u201c你跟我来。但我只能带你到入口，剩下的路你自己走。\u201d\n"
            "叶知秋抱拳行礼：\u201c多谢前辈。\u201d\n"
            "两人并肩走向浓雾深处。身后，其余四人默默让开了路。\n"
            "浓雾中，叶知秋感受到一股诡异的力量在空气中流动。这是阵法的气息。\n"
            "\u201c前辈，这是什么阵法？\u201d叶知秋问道。\n"
            "\u201c迷天阵。\u201d老者淡淡说道，\u201c一旦踏入，便只能向前，不能回头。\u201d\n"
            "叶知秋紧了紧手中的剑柄。他回头看了一眼来时的路，已经被浓雾完全吞没了。\n"
            "前方隐约传来一阵金属碰撞声，还有\u2026\u2026一个人的呼喊声。\n"
            "\u201c师弟！\u201d叶知秋猛然加速，向着声音传来的方向奔去。\n"
            "老者没有跟上去。他只是站在原地，看着叶知秋的身影消失在迷雾之中，低声自语：\u201c年轻人啊\u2026\u2026\u201d"
        ),
    },
}


def _extract_chapter_number(messages: list | None) -> int:
    """Extract chapter number from LLM messages for deterministic content."""
    if not messages:
        return 1
    for msg in messages:
        content = ""
        if isinstance(msg, dict):
            content = str(msg.get("content", ""))
        elif isinstance(msg, str):
            content = msg
        m = re.search(r"章节号[：:]\s*(\d+)", content)
        if not m:
            m = re.search(r"第(\d+)章", content)
        if not m:
            m = re.search(r"chapter_number[=：:]\s*(\d+)", content)
        if m:
            return int(m.group(1))
    return 1


def _get_stub_chapter_content(messages: list | None = None) -> dict:
    """Get chapter content based on chapter number extracted from messages.

    Returns dict with title, content, and word_count.
    Deterministic: same chapter_number always produces same output.
    """
    chapter_num = _extract_chapter_number(messages)
    template = _STORY_TEMPLATES.get(chapter_num)

    if not template:
        # Generate deterministic content for chapters beyond templates
        seed = hashlib.md5(f"chapter_{chapter_num}".encode()).hexdigest()
        titles = ["迷雾重重", "暗夜追击", "真相浮出", "风暴将至", "绝地反击", "峰回路转"]
        title = titles[int(seed[:8], 16) % len(titles)]
        content = (
            f"第{chapter_num}章的故事从这里开始。{title}\u2014\u2014\n\n"
            "清晨的阳光透过窗帘，在地板上投下斑驳的光影。空气中弥漫着一股说不清的气息。\n"
            f"主角站在窗前，思绪万千。这一切究竟是怎么回事？第{chapter_num}章的谜团比之前更加扑朔迷离。\n"
            "电话铃声突然响起，打破了清晨的宁静。屏幕上显示的是一个陌生号码。\n"
            "\u201c喂？\u201d主角接起电话。\n"
            "\u201c不要说话，听我说。\u201d电话那头的声音急促而低沉，\u201c你现在很危险。\u201d\n"
            "主角握紧了手机，目光扫过窗外的街道。一辆陌生的车停在楼下，车里似乎有人在观察着这栋楼。\n"
            "\u201c你是谁？\u201d主角压低声音问道。\n"
            "\u201c这不重要。重要的是，你必须马上离开那里。\u201d电话那头的声音变得更加急切。\n"
            "主角深吸一口气，迅速收拾了必要的物品，从后门离开了公寓。\n"
            "街道上人来人往，看似平静的日常背后，暗流涌动。每一步都可能是陷阱，每一个陌生人都可能是敌人。\n"
            "拐过三个街角之后，主角确信身后已经没有了跟踪者。他站在一家咖啡店的橱窗前，假装看菜单，\n"
            "实则在观察玻璃上的倒影。一切看似正常，但那种被人注视的感觉始终挥之不去。\n"
            "他推门走进咖啡店，选了角落靠窗的位置坐下。服务员走过来时，他点了一杯黑咖啡。\n"
            "\u201c先生，您的咖啡。\u201d服务员放下杯子，同时悄悄塞了一张纸条。\n"
            "主角不动声色地打开纸条，上面只写了一行字和一个地址。他喝了一口咖啡，\n"
            "起身离开，朝纸条上的地址走去。这条路，注定不会平坦。"
        )
        template = {"title": title, "content": content}

    word_count = len(template["content"])
    return {
        "title": template["title"],
        "content": template["content"],
        "word_count": word_count,
    }


class StubLLM(LLMProvider):
    """Stub LLM that returns minimal valid outputs for local tests and demos."""

    def __init__(self):
        """Initialize stub LLM with token usage tracking (v5.2)."""
        self.last_token_usage: TokenUsage | None = None

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
        # Set mock token usage for tracking (v5.2)
        self.last_token_usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            duration_ms=50,
        )

        schema_name = getattr(schema, "__name__", "") if schema else ""
        if "Planner" in schema_name:
            return {
                "chapter_brief": {
                    "objective": "推进剧情",
                    "required_events": ["事件1"],
                    "plots_to_plant": [],
                    "plots_to_resolve": [],
                    "ending_hook": "悬念",
                    "constraints": [],
                }
            }
        if "Screenwriter" in schema_name:
            return {"scene_beats": [{"sequence": 1, "scene_goal": "场景目标", "conflict": "冲突", "hook": "钩子"}]}
        if "Author" in schema_name:
            chapter_data = _get_stub_chapter_content(messages)
            return {
                "title": chapter_data["title"],
                "content": chapter_data["content"],
                "word_count": chapter_data["word_count"],
                "implemented_events": ["事件1"],
                "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            # Polisher should use the same chapter content from messages
            chapter_data = _get_stub_chapter_content(messages)
            return {
                "content": chapter_data["content"],
                "fact_change_risk": "none",
                "changed_scope": ["sentence", "rhythm"],
                "summary": "微调表达",
            }
        if "Editor" in schema_name:
            return {
                "pass": True,
                "score": 92,
                "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 17, "pacing": 17},
                "issues": [],
                "suggestions": [],
                "revision_target": None,
                "state_card": {},
            }
        if "ScoutOutput" in schema_name:
            return {
                "market_report": {
                    "genre": "玄幻",
                    "platform": "起点",
                    "audience": "男性读者",
                    "trends": ["趋势1", "趋势2"],
                    "opportunities": ["机会1", "机会2"],
                    "reader_preferences": ["偏好1", "偏好2"],
                    "competitor_notes": ["竞品1", "竞品2"],
                    "summary": "市场分析摘要",
                    "recommendations": ["建议1", "建议2"],
                },
                "topic": "都市异能",
                "keywords": ["关键词1", "关键词2"],
            }
        if "ContinuityCheckerOutput" in schema_name:
            return {
                "report": {
                    "project_id": "demo",
                    "from_chapter": 1,
                    "to_chapter": 5,
                    "issues": [{
                        "issue_type": "character",
                        "severity": "warning",
                        "chapter_range": "1-5",
                        "description": "角色不一致",
                        "recommendation": "检查角色设定",
                    }],
                    "warnings": ["警告1"],
                    "state_card_consistency": True,
                    "character_consistency": True,
                    "plot_consistency": True,
                    "summary": "连续性检查摘要",
                },
                "agent_messages": [],
            }
        if "ArchitectOutput" in schema_name:
            return {
                "proposals": [{
                    "proposal_type": "quality_rule",
                    "scope": "quality",
                    "title": "改进提案",
                    "description": "描述",
                    "risk_level": "medium",
                    "affected_area": ["editor"],
                    "recommendation": "建议",
                    "rationale": "理由",
                    "implementation_notes": "实施说明",
                }],
                "summary": "架构改进提案摘要",
                "total_proposals": 1,
            }
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        # Set mock token usage for tracking (v5.2)
        self.last_token_usage = TokenUsage(
            prompt_tokens=50,
            completion_tokens=100,
            total_tokens=150,
            duration_ms=30,
        )
        return "{}"
