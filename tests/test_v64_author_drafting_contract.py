"""v6.4.1: Author Drafting Contract tests.

Tests SYSTEM_PROMPT constraints, build_context anti-AI guide,
and self-check warning heuristics.
Does NOT modify Polisher/Editor prompts or workflow topology.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from novel_factory.models.state import ChapterStatus


# Sample texts for heuristic testing (must be long enough to pass word gate)
SAMPLE_STRAIGHT_EMOTION = (
    "李明感到一阵愤怒涌上心头。他看着眼前的对手，心中暗想：这次一定要赢。\n"
    "张华觉得有些不安。他知道，这次的任务非常危险。他明白，如果失败，后果将不堪设想。\n"
    "王芳意识到，这场战斗将决定一切。她理解，自己已经没有退路。\n"
    "李明察觉到了空气中的异样。他发现，周围的一切都在发生变化。\n"
    "三人站在十字路口，谁也不知道该往哪个方向走。\n"
    "李明深吸一口气，握紧拳头。他知道不能再犹豫，必须立刻行动。\n"
    "走。他低声说，带头冲进了走廊。张华和王芳紧随其后。\n"
    "走廊尽头是一扇厚重的铁门。李明用力一推，门应声而开。\n"
    "里面的景象让所有人都愣住了。一个巨大的地下空间，灯光昏暗，到处都是复杂的仪器。\n"
    "这是什么地方？王芳喃喃自语。\n"
    "不管什么地方，李明说，我们必须找到出口。\n"
    "他们沿着通道向前走去，脚步声在空旷的空间里回荡。\n"
    "突然，前方传来一阵机械运转的声音。李明停下脚步，示意大家安静。\n"
    "有人。他压低声音说，躲起来。\n"
    "三人迅速躲到一堆废弃的箱子后面，屏住呼吸。\n"
    "一个穿着白大褂的人影从拐角处走过，手里还拿着一份文件。\n"
    "等那人走远。李明用口型示意。\n"
    "几分钟后，脚步声渐渐消失。李明探出头，确认安全后才让大家继续前进。\n"
    "前面有光。张华指着远处说。\n"
    "李明点点头，加快了脚步。他们不知道前面等待他们的是什么，但已经没有退路。\n"
    "光线越来越亮，一个出口隐约可见。李明背脊一紧，知道关键时刻到了。\n"
    "准备好。他说，冲出去。\n"
    "三人同时发力，朝着出口狂奔。身后传来警报声，但他们已经顾不上那么多了。\n"
    "冲出出口的那一刻，刺眼的阳光让他们一时间睁不开眼。\n"
    "出来了。王芳喘着气说。\n"
    "还没结束。李明看了看四周，我们得找到安全的地方。\n"
    "他们沿着小路继续奔跑，直到确信没有人追来才停下来。\n"
    "李明靠在墙上，大口喘气。他看了看同伴，确认大家都没事。\n"
    "接下来怎么办？张华问。\n"
    "先休息。李明说，然后想办法联系外界。\n"
    "王芳从包里拿出水壶，喝了一口水，然后递给李明。\n"
    "李明接过水壶，喝了一口。冰凉的水滑过喉咙，让他稍微清醒了一些。\n"
    "他抬头看了看天空。太阳已经升得很高，阳光透过树叶的缝隙洒下来，在地上形成斑驳的光影。\n"
    "我们得在天黑前找到落脚点。李明说。\n"
    "三人重新上路，沿着山间小路向前走去。\n"
    "鸟儿在枝头鸣叫，风吹过树叶发出沙沙的响声。\n"
    "如果不是身处险境，这倒是一幅宁静的画面。\n"
    "李明握紧手中的短剑，目光警惕地扫视着四周。\n"
    "他知道，危险随时可能降临。\n"
)

SAMPLE_LOW_SENSORY = (
    "会议开始了。大家坐在会议室里，讨论着下一步的计划。\n"
    "张明首先发言，介绍了当前的情况。然后李华补充了一些细节。\n"
    "接着，王强提出了一个新的方案。最后，大家达成了一致意见。\n"
    "会议结束了。所有人都离开了会议室。\n"
    "第二天，大家继续工作。每个人都很忙，没有人注意到办公室里的变化。\n"
    "中午时分，有人送来了一份文件。秘书接过来，放在领导的桌上。\n"
    "下午，领导看完了文件，在上面签了字。然后文件被送了出去。\n"
    "傍晚，下班时间到了。大家纷纷收拾东西，准备回家。\n"
    "办公室里渐渐安静下来。最后一个人离开时，关掉了所有的灯。\n"
    "第二天，同样的节奏再次开始。上午开会，下午处理文件，傍晚下班。\n"
    "这样的日子持续了整整一周。没有人觉得有什么不对。\n"
    "直到周五下午，一封邮件打破了平静。邮件来自总部，内容很简单：下周一开始整改。\n"
    "大家面面相觑，不知道这意味着什么。但没有人敢问。\n"
    "周一很快到来。新的领导走进了办公室，带来了全新的工作方式。\n"
    "有人欢喜有人忧。但不管怎样，工作还得继续。\n"
    "日子一天天过去，新的流程逐渐被大家接受。办公室里又恢复了往日的平静。\n"
    "只是在偶尔的闲聊中，人们还会提起那段整改前的日子。\n"
    "那时候多好啊。有人感叹。\n"
    "是啊。另一个人附和。\n"
    "但感叹归感叹，谁都知道回不去了。\n"
    "办公室的白墙依然雪白，桌椅依然整齐。只是人心，已经不一样了。\n"
    "新的领导制定了一系列规章制度。每个人都要遵守，没有人例外。\n"
    "起初，大家还有些不适应。但时间久了，也就习惯了。\n"
    "办公室里多了一些新面孔，也少了一些老面孔。\n"
    "人来人往，仿佛一切都没有变过。\n"
    "只有那些老员工知道，这里曾经发生过什么。\n"
    "但他们选择了沉默。\n"
    "毕竟，在这个时代，能保住一份工作就已经很不容易了。\n"
    "谁还有心思去怀念过去呢？\n"
    "日子就这样一天天过去。\n"
    "直到有一天，一个年轻人走进了办公室。\n"
    "他的眼神清澈，脸上带着微笑。\n"
    "大家好，他说，我是新来的。\n"
    "所有人都抬起头，看着他。\n"
    "那一刻，办公室里仿佛有了一丝不一样的气息。\n"
    "但很快，一切又恢复了原样。\n"
    "年轻人被分配到角落的位置，开始了他的工作。\n"
    "他不知道，自己即将面对的，是怎样的未来。\n"
)

SAMPLE_SUMMARY_LIKE = (
    "本章首先介绍了主角的背景。然后描述了他在公司的日常。\n"
    "接着，一个突发事件打破了他的平静生活。最后，他做出了一个重大决定。\n"
    "综上所述，本章为后续剧情奠定了基础。\n"
    "首先，主角是一个普通的上班族，每天朝九晚五。然后，他在一次偶然的机会中发现了一个秘密。\n"
    "接着，他开始调查这个秘密。最后，他发现了一个惊天的阴谋。\n"
    "简单来说，主角从一个普通人变成了英雄。\n"
    "首先，他没有什么特殊能力。然后，他通过努力学会了各种技能。\n"
    "接着，他结识了一群志同道合的伙伴。最后，他们一起对抗邪恶势力。\n"
    "综上所述，这是一个关于成长和友谊的故事。\n"
    "首先，主角犯了很多错误。然后，他从错误中吸取教训。\n"
    "接着，他变得越来越强大。最后，他成为了众人敬仰的领袖。\n"
    "说白了，这就是一个逆袭的故事。\n"
    "首先，敌人很强大。然后，主角找到了敌人的弱点。\n"
    "接着，他制定了一个周密的计划。最后，他成功地击败了敌人。\n"
    "综上所述，正义最终战胜了邪恶。\n"
    "首先，主角失去了很多。然后，他明白了什么才是真正重要的。\n"
    "接着，他重新振作起来。最后，他开始了新的旅程。\n"
    "简单来说，这是一个关于希望的故事。\n"
    "首先，主角遇到了很多困难。然后，他一次次地克服了这些困难。\n"
    "接着，他找到了自己的使命。最后，他完成了自己的使命。\n"
    "综上所述，这是一个关于勇气和坚持的故事。\n"
    "首先，主角很迷茫。然后，他找到了方向。\n"
    "接着，他努力奋斗。最后，他实现了自己的梦想。\n"
    "说白了，这就是一个追梦的故事。\n"
    "首先，主角被误解。然后，他证明了自己。\n"
    "接着，他赢得了尊重。最后，他成为了传奇。\n"
    "综上所述，这是一个关于信念的故事。\n"
)

SAMPLE_LOW_DIALOGUE = (
    "李明推开房门，走进屋内。房间里很暗，他摸索着找到了开关。\n"
    "灯光亮起，他看到了桌上的文件。他拿起文件，仔细阅读起来。\n"
    "文件内容让他大吃一惊。他放下文件，在房间里来回踱步。\n"
    "最后，他做出了决定。\n"
    "他走到窗前，看着窗外的夜景。城市的灯火在远处闪烁，像是在诉说着什么。\n"
    "他深吸一口气，转身走向门口。走廊里静悄悄的，只有他的脚步声在回响。\n"
    "他下了楼，走出大楼。夜风拂面，带来一丝凉意。\n"
    "他沿着街道走着，脑子里还在想着那份文件的内容。\n"
    "不知不觉中，他走到了一座桥上。桥下是漆黑的河水，水面倒映着城市的灯光。\n"
    "他靠在桥栏上，点燃了一支烟。火光在黑暗中一闪一闪。\n"
    "烟雾随风飘散，他的思绪也随之飘远。\n"
    "他想起了很多事情。小时候的梦想，少年时的抱负，成年后的无奈。\n"
    "一支烟抽完，他将烟头扔进河里。火星在水面上闪烁了一下，随即消失。\n"
    "他转身离开桥梁，朝着家的方向走去。\n"
    "街道上空无一人，只有路灯在默默地照着。他的影子被拉得很长，又缩短，再拉长。\n"
    "终于，他回到了家。推开门，屋子里一片漆黑。\n"
    "他没有开灯，直接走到沙发前坐下。黑暗中，他的眼睛渐渐适应了。\n"
    "窗外的月光透过窗帘的缝隙洒进来，在地板上投下一道银白色的光带。\n"
    "他盯着那道光带，看了很久。\n"
    "不知过了多久，他终于站起身，走向卧室。\n"
    "躺在床上，他望着天花板，久久无法入睡。\n"
    "夜，还很长。\n"
    "他翻了个身，试图让自己平静下来。但脑海中不断浮现出文件上的内容。\n"
    "那些数字，那些名字，那些他从未想过会联系在一起的人和事。\n"
    "他坐起身，打开床头柜上的台灯。柔和的光线填满了房间的一角。\n"
    "他拿起笔，在笔记本上写下几个关键词。\n"
    "写完后，他盯着这些词看了很久，试图找出其中的关联。\n"
    "但越是思考，谜团就越多。\n"
    "他合上笔记本，关掉台灯，重新躺下。\n"
    "窗外的天色渐渐亮了起来。新的一天即将开始。\n"
    "他不知道，这一天将会带来什么。\n"
    "但他知道，自己不能再逃避了。\n"
    "必须面对。\n"
    "必须解决。\n"
    "他闭上眼睛，强迫自己休息。\n"
    "哪怕只有几个小时，也足够了。\n"
    "因为接下来，他将面对人生中最重要的一次抉择。\n"
)


@pytest.fixture
def repo():
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    repo = Repository(db_path)
    repo.create_project(
        project_id="test_proj",
        name="Test",
        genre="fantasy",
        description="test",
        target_words=10000,
        total_chapters_planned=10,
    )
    repo.add_chapter("test_proj", 1, "第一章", status="scripted")
    repo.create_instruction(
        "test_proj", 1,
        objective="测试目标",
        key_events='["事件1", "事件2"]',
        emotion_tone="紧张",
        ending_hook="悬念",
        word_target=2500,
    )
    repo.save_scene_beats("test_proj", 1, [
        {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "turn": "转折", "hook": "钩子"},
    ])
    yield repo
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestAuthorSystemPrompt:
    """Author SYSTEM_PROMPT contains v6.4.1 drafting contract."""

    def test_prompt_contains_show_dont_tell(self):
        from novel_factory.agents.author import AUTHOR_SYSTEM_PROMPT
        assert "Show, Don't Tell" in AUTHOR_SYSTEM_PROMPT
        assert "感到" in AUTHOR_SYSTEM_PROMPT
        assert "心中暗想" in AUTHOR_SYSTEM_PROMPT

    def test_prompt_contains_scene_based(self):
        from novel_factory.agents.author import AUTHOR_SYSTEM_PROMPT
        assert "场景为单位推进" in AUTHOR_SYSTEM_PROMPT
        assert "剧情摘要" in AUTHOR_SYSTEM_PROMPT
        assert "设定说明" in AUTHOR_SYSTEM_PROMPT

    def test_prompt_contains_sensory_detail(self):
        from novel_factory.agents.author import AUTHOR_SYSTEM_PROMPT
        assert "视觉" in AUTHOR_SYSTEM_PROMPT
        assert "听觉" in AUTHOR_SYSTEM_PROMPT or "触觉" in AUTHOR_SYSTEM_PROMPT

    def test_prompt_contains_dialogue_requirement(self):
        from novel_factory.agents.author import AUTHOR_SYSTEM_PROMPT
        assert "对白" in AUTHOR_SYSTEM_PROMPT
        assert "潜台词" in AUTHOR_SYSTEM_PROMPT or "冲突" in AUTHOR_SYSTEM_PROMPT

    def test_prompt_contains_no_preaching(self):
        from novel_factory.agents.author import AUTHOR_SYSTEM_PROMPT
        assert "禁止归纳人生道理" in AUTHOR_SYSTEM_PROMPT or "说教" in AUTHOR_SYSTEM_PROMPT

    def test_prompt_contains_setting_dramatization(self):
        from novel_factory.agents.author import AUTHOR_SYSTEM_PROMPT
        assert "旁白式解释" in AUTHOR_SYSTEM_PROMPT or "设定必须通过" in AUTHOR_SYSTEM_PROMPT


class TestAuthorBuildContext:
    """Author build_context includes anti-AI drafting guide."""

    def test_context_contains_anti_ai_guide(self, repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.provider import LLMProvider

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, **kw):
                return ""

        agent = AuthorAgent(repo, StubLLM())
        ctx = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })
        assert "去AI味写作指南" in ctx
        assert "感到" in ctx
        assert "心中暗想" in ctx
        assert "简单来说" in ctx or "设定旁白" in ctx

    def test_context_preserves_instruction(self, repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.provider import LLMProvider

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, **kw):
                return ""

        agent = AuthorAgent(repo, StubLLM())
        ctx = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })
        assert "写作指令" in ctx
        assert "测试目标" in ctx


class TestAuthorSelfCheckWarnings:
    """v6.4.1 self-check warning heuristics."""

    def _run_self_check(self, repo, content: str, implemented_events: list | None = None):
        """Helper to run author self-check with given content."""
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.provider import LLMProvider

        # Default to all key_events from instruction to avoid event_coverage fail
        if implemented_events is None:
            implemented_events = ["事件1", "事件2"]

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "title": "测试",
                    "content": content,
                    "word_count": len(content),
                    "implemented_events": implemented_events,
                    "used_plot_refs": [],
                }
            def invoke_text(self, messages, **kw):
                return ""

        agent = AuthorAgent(repo, StubLLM())
        # Build state with llm_mode=stub so repair/sanitize don't trigger real LLM
        state = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "llm_mode": "stub",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        # Run _execute which includes self-check loop
        result = agent.run(state)
        return result

    def test_straight_emotion_triggers_warning(self, repo):
        """Text with straight emotion words should trigger show_dont_tell warning."""
        # Use enough text to pass word gate, but remove "心中暗想" to avoid critical death penalty
        text = SAMPLE_STRAIGHT_EMOTION * 4
        text = text.replace("心中暗想", "暗自思忖")
        result = self._run_self_check(repo, text)
        # Should pass (not fail) but with warnings in trace
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True  # warning should not cause fail
        warnings = sc.get("warnings", [])
        assert any("show_dont_tell" in w for w in warnings)

    def test_low_sensory_triggers_warning(self, repo):
        """Text with low sensory detail should trigger sensory_detail warning."""
        result = self._run_self_check(repo, SAMPLE_LOW_SENSORY * 3)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        warnings = sc.get("warnings", [])
        assert any("sensory_detail" in w for w in warnings)

    def test_summary_like_triggers_warning(self, repo):
        """Text with summary markers should trigger prose_like warning."""
        result = self._run_self_check(repo, SAMPLE_SUMMARY_LIKE * 4)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        warnings = sc.get("warnings", [])
        assert any("prose_like" in w for w in warnings)

    def test_low_dialogue_triggers_warning(self, repo):
        """Text with low dialogue ratio should trigger dialogue warning."""
        result = self._run_self_check(repo, SAMPLE_LOW_DIALOGUE * 3)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        warnings = sc.get("warnings", [])
        assert any("dialogue" in w for w in warnings)

    def test_normal_text_no_warnings(self, repo):
        """Normal prose should have few or no warnings."""
        normal = (
            "林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。\n"
            "你来了。身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。\n"
            "你是谁？林默警觉地问道，手已经摸向腰间的短剑。\n"
            "我是谁不重要，黑衣男子缓缓走近，重要的是，你正在寻找的东西，也在寻找你。\n"
            "窗外的雨越下越大，雷声隐隐传来。林默沉默了片刻。\n"
            "我已经没有退路了，他终于说道，不管前面是什么，我都必须走下去。\n"
            "黑衣男子点了点头。很好。那么，从现在开始，你要小心身边的每一个人。\n"
            "说完，他的身影渐渐消失在阴影中，仿佛从未出现过。\n"
            "林默站在原地，喉头发紧。窗外的雨声似乎变得更加急促，仿佛在预示着什么。\n"
            "他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。\n"
            "他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。\n"
            "最后，他只写了一句话：今天，一切都将改变。\n"
            "就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。\n"
            "门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。\n"
            "救救我，年轻人喘着气说，他们要杀我。\n"
            "林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。\n"
            "他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。\n"
            "黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。\n"
            "年轻人蜷缩在角落里，浑身发抖。林默从窗缝中看到几个黑影从门前掠过。\n"
            "他们没有停留，脚步声渐渐远去。林默松了口气，但并未放松警惕。\n"
            "他们是谁？林默低声问道。\n"
            "我不知道……年轻人摇着头，我只知道，他们想要我手里的东西。\n"
            "林默注意到年轻人紧握着拳头。他伸出手：给我看看。\n"
            "年轻人犹豫了一下，慢慢张开手掌。一枚古旧的玉佩躺在掌心，泛着微弱的幽光。\n"
            "林默瞳孔一缩。这枚玉佩，和他父亲临终前交给他的那枚，竟然一模一样。\n"
            "这东西……你从哪里得到的？林默的声音有些发紧。\n"
            "是我爷爷留给我的遗物。年轻人说，他说，这东西关系到一个大秘密。\n"
            "林默沉默了。父亲当年也是这么说的。两枚玉佩，两个家族，这绝不是巧合。\n"
            "窗外的雨渐渐小了。林默站起身，走到窗前。天边露出了一丝鱼肚白。\n"
            "天快亮了。林默说，你先在这里休息。等安全了，我们再细说。\n"
            "年轻人点了点头，靠在墙角闭上眼睛。林默却没有睡意，他握着两枚玉佩，陷入沉思。\n"
            "父亲当年调查的真相，或许就藏在这两枚玉佩之中。而现在，这个真相正在慢慢浮出水面。\n"
            "他必须做好准备。不管前方有多少危险，他都不会退缩。这是他的选择，也是他的宿命。\n"
            "门外又传来了动静。林默警觉地抬起头，手再次摸向短剑。\n"
            "林兄，是我。一个熟悉的声音传来。林默松了口气，走过去开门。\n"
            "门外站着他的好友陆尘，面色凝重。出事了。你之前调查的那个案子，又有了新的线索。\n"
            "进来说。林默让开身子，同时注意着街道上的动静。\n"
            "陆尘进屋后迅速关门，压低声音说：有人发现了你父亲的日记。\n"
            "林默瞳孔一缩。在哪里？\n"
            "城东的老书店，老板是你们林家的旧识。陆尘说，但那里现在被人盯着。\n"
            "林默看向窗外的晨曦，目光沉了下来。我去一趟。\n"
            "太危险了。陆尘摇头，他们肯定在等你出现。\n"
            "正因为如此，我才要去。林默的目光坚定，这是我唯一的机会。\n"
            "年轻人这时睁开眼睛，我和你一起去。\n"
            "林默看着他，摇了摇头。你先留在这里。等你安全了，我们再一起调查。\n"
            "年轻人想说什么，但最终点了点头。他知道，以他现在的情况，只会是累赘。\n"
            "林默收拾好行装，对着陆尘说：照顾好他。等我回来。\n"
            "陆尘拍了拍他的肩膀，小心。\n"
            "林默推开房门，消失在晨曦中。这一天，注定不平凡。\n"
            "街道上行人稀少，晨雾笼罩着整座城市。林默贴着墙根行走，尽量避开开阔地带。\n"
            "他知道，从现在开始，每一个转角都可能藏着危险。\n"
            "城东的老书店距离这里不算太远，但以他现在的处境，每一步都要格外小心。\n"
            "穿过一条小巷后，林默停下了脚步。前方，书店的招牌已经隐约可见。\n"
            "但更让他警觉的是，书店对面停着一辆黑色的轿车，车窗紧闭，看不清里面的人。\n"
            "林默深吸一口气，压低帽檐，若无其事地向书店走去。\n"
            "就在他即将推门的瞬间，一个苍老的声音从身后传来：年轻人，买书吗？\n"
            "林默转身，看到一个衣着破旧的老者，手中捧着几本书籍。\n"
            "不买。林默简短地回答，正要推门，却听到老者低声说：\n"
            "你父亲的东西，藏在第三排书架的夹层里。记住，快进快出。\n"
            "林默指尖一颤，看向老者。但老者已经转身离去，消失在晨雾中。\n"
            "他推开门，走进书店。空气中弥漫着陈旧纸张的气息，一切都和他记忆中一样。\n"
            "老板坐在柜台后，抬头看了他一眼，没有说话。只是微微点了点头。\n"
            "林默快步走向第三排书架，手指在书脊上滑动，寻找着那个夹层。\n"
            "终于，他找到了。一本看似普通的线装书，封皮微微鼓起。\n"
            "他将书取下，翻开封皮，里面赫然是一叠泛黄的纸张。\n"
            "父亲的笔迹。林默的心跳加速，但他强迫自己冷静下来。\n"
            "他将纸张塞入怀中，正要离开，却听到门外传来汽车引擎熄灭的声音。\n"
            "他们来了。林默看向后门的方向，老板朝他使了个眼色。\n"
            "后门。老板低声说，快。\n"
            "林默没有犹豫，快步冲向后门。就在他推开门的瞬间，前门被猛然推开。\n"
            "几个黑衣人冲了进来，但林默已经消失在后巷的阴影中。\n"
            "他一路狂奔，穿过数条小巷，确信没有人跟上来后，才停下来喘息。\n"
            "怀里的纸张沉甸甸的，父亲留下的线索，终于到了他手中。\n"
            "真相的脚步声越来越近，而危险，也在黑暗中悄然逼近。\n"
            "他沿着后巷一路向东，来到一座废弃的仓库前。这里是他和陆尘的秘密据点。\n"
            "林默推开门，在角落的木箱上坐下，将父亲的日记摊开在膝上。\n"
            "第一页的字迹已经有些模糊，但林默依然能辨认出那熟悉的笔锋。\n"
            "窗外传来远处寺庙的钟声，他合上日记，站起身来。这一切，才刚刚开始。\n"
            "林默深吸一口气，决定连夜研究父亲留下的线索。所有的答案，或许就在这本泛黄的日记之中。\n"
        )
        result = self._run_self_check(repo, normal)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        # Normal text should not have show_dont_tell or prose_like warnings
        warnings = sc.get("warnings", [])
        assert not any("show_dont_tell" in w for w in warnings)
        assert not any("prose_like" in w for w in warnings)

    def test_missing_events_still_fails(self, repo):
        """Missing key events should still cause hard fail."""
        result = self._run_self_check(repo, "正文内容" * 200, implemented_events=[])
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is False
        issues = sc.get("issues", [])
        assert any(i.get("type") == "event_coverage" for i in issues)


class TestStubContent:
    """Stub provider content meets v6.4.1 baseline."""

    def test_stub_no_critical_death_penalty(self):
        from novel_factory.llm.stub_provider import _STORY_TEMPLATES
        from novel_factory.validators.death_penalty import check_death_penalty_structured

        for num, template in _STORY_TEMPLATES.items():
            result = check_death_penalty_structured(template["content"])
            assert not result.has_critical, (
                f"Chapter {num} stub has critical death penalty: {result.violations}"
            )

    def test_stub_content_variety(self):
        from novel_factory.llm.stub_provider import _STORY_TEMPLATES
        titles = {t["title"] for t in _STORY_TEMPLATES.values()}
        assert len(titles) == len(_STORY_TEMPLATES), "Stub chapters should have unique titles"

    def test_stub_meets_min_length(self):
        from novel_factory.llm.stub_provider import _STORY_TEMPLATES
        for num, template in _STORY_TEMPLATES.items():
            assert len(template["content"]) >= 500, f"Chapter {num} too short"


class TestWorkflowNotModified:
    """v6.4.1 does not modify workflow topology."""

    def test_author_node_still_routes_to_drafted(self, repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.provider import LLMProvider

        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 44

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "title": "第一章 测试",
                    "content": long_content,
                    "word_count": len(long_content),
                    "implemented_events": ["事件1"],
                    "used_plot_refs": ["P001"],
                }
            def invoke_text(self, messages, **kw):
                return ""

        agent = AuthorAgent(repo, StubLLM())
        repo.update_chapter_status("test_proj", 1, "scripted")
        repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "llm_mode": "stub",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        chapter = repo.get_chapter("test_proj", 1)
        assert chapter["content"] is not None
