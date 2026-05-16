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
        # Use stub ch1 content with Chinese curly quotes so dialogue regex matches
        from novel_factory.llm.stub_provider import _STORY_TEMPLATES
        normal = _STORY_TEMPLATES[1]["content"]
        result = self._run_self_check(repo, normal)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        # Normal text should not have show_dont_tell or prose_like warnings
        warnings = sc.get("warnings", [])
        assert not any("show_dont_tell" in w for w in warnings)
        assert not any("prose_like" in w for w in warnings)
        assert not any("dialogue" in w for w in warnings)
        assert not any("sensory_detail" in w for w in warnings)

    def test_transition_words_do_not_trigger_prose_like(self, repo):
        """Common transition words like '然后/接着' should not trigger prose_like at normal density."""
        text = (
            "李明站在街角，看着对面大楼的灯火。夜幕已经降临，城市的喧嚣渐渐平息。\n"
            "他看了看手表，距离约定的时间还有十分钟。于是，他掏出手机，确认了一下地址。\n"
            "手机屏幕的冷光照亮了他的脸。这时，他注意到街对面停着一辆陌生的黑色轿车。\n"
            "那辆车已经停了很久，车窗紧闭，看不清里面的人。李明皱起眉头，警觉起来。\n"
            "他转身走进旁边的小巷，贴着墙根慢慢移动。脚步声在空荡的巷子里回响。\n"
            "巷子的尽头是一扇铁门。他推开门，里面是一个废弃的院子。杂草丛生，空气中弥漫着潮湿的霉味。\n"
            "李明穿过院子，来到后门。他停下脚步，侧耳倾听。没有任何异常的声音。\n"
            "他推开后门，走进另一栋建筑。楼道里漆黑一片，只有安全出口的标志发出微弱的绿光。\n"
            "他摸索着走到三楼，在一扇门前停下。随后，他轻轻敲了三下门。\n"
            "门内传来一阵窸窣声。片刻后，门锁打开了。张华的脸出现在门缝里。\n"
            "你怎么从后面上来？张华压低声音问。\n"
            "外面有辆车，我觉得不对劲。李明闪身进屋。\n"
            "张华关上门，反锁。客厅里摆着几台电脑，屏幕上闪烁着各种数据和图表。\n"
            "有新发现？李明问。\n"
            "张华走到电脑前，点开一个文件夹。你看这个。\n"
            "李明凑近屏幕，上面是一张监控截图。截图中，一个模糊的人影正走进他们刚才提到的那栋大楼。\n"
            "这是什么时候的？李明问。\n"
            "今天下午。张华说，我调取了附近三个监控点的录像，都拍到了这个人。\n"
            "李明盯着屏幕上的人影。虽然模糊，但那身形他太熟悉了。\n"
            "是王强。他说。\n"
            "张华点头。我也觉得是他。但他不是已经……\n"
            "已经失踪三个月了。李明接过话头，如果他还活着，为什么要躲着我们？\n"
            "两人沉默了片刻。窗外的风吹动窗帘，发出轻微的响声。\n"
            "不管怎样，李明说，明天我们必须去那个地址看看。\n"
            "太危险了。张华摇头，如果王强真的投靠了对方，我们自投罗网。\n"
            "所以才要查清楚。李明的目光坚定，我不能让他继续错下去。\n"
            "张华叹了口气。好吧，我陪你去。但得先准备好撤退路线。\n"
            "李明走到窗前，拉开窗帘的一角。街道上空无一人，那辆黑色轿车已经不见了。\n"
            "他松了口气，但并未放松警惕。在这个城市里，危险随时可能降临。\n"
            "走吧。他说，先找个安全的地方过夜。\n"
            "张华关掉电脑，收拾好东西。两人一前一后走出房间，消失在夜色中。\n"
            "楼道里的声控灯随着他们的脚步声亮起又熄灭。每一步都小心翼翼，生怕惊动了什么。\n"
            "他们来到地下停车场。张华按下车钥匙，远处一辆灰色轿车闪了闪灯。\n"
            "上车。张华说。\n"
            "李明钻进副驾驶，系好安全带。张华发动引擎，车子缓缓驶出停车场。\n"
            "街道上的路灯昏黄，将路面照得斑驳。偶尔有夜归的行人匆匆走过，低着头，仿佛害怕被人认出。\n"
            "李明望着窗外，脑子里还在想着王强的事。三个月前，他们还是并肩作战的伙伴。\n"
            "而现在，一切都变了。他不清楚王强经历了什么，但他必须找到答案。\n"
            "车子拐进一条僻静的小路，最终在一座老旧公寓前停下。\n"
            "这里是我新找的落脚点。张华说，应该安全。\n"
            "李明点点头，推开车门。夜风拂面，带来一丝凉意。\n"
            "他抬头看了看公寓的窗户，只有三楼的一扇还亮着灯。\n"
            "走吧。他说。\n"
            "两人走进公寓楼，脚步声在空旷的大厅里回响。电梯坏了，他们只能走楼梯。\n"
            "爬到三楼，张华掏出钥匙，打开了那扇亮着灯的房门。\n"
            "屋子里陈设简单，但收拾得很干净。桌上摆着两杯还冒着热气的茶。\n"
            "有人来过？李明警觉地问。\n"
            "没有。张华笑了笑，是我出门前泡的，保温效果不错。\n"
            "李明端起茶杯，喝了一口。温热的茶水滑过喉咙，让他紧绷的神经稍稍放松。\n"
            "明天的事，你怎么看？他问。\n"
            "张华坐在沙发上，揉了揉太阳穴。我觉得，我们应该多带几个人。\n"
            "不行。李明摇头，人多反而容易暴露。就我们两个。\n"
            "好吧。张华无奈地说，听你的。\n"
            "李明走到窗前，望着远处闪烁的霓虹灯。城市的夜晚总是如此迷人，又如此危险。\n"
            "他很清楚，从踏入那栋大楼的那一刻起，一切都将无法回头。\n"
            "但他已经做好了准备。不管前面是什么，他都不会退缩。\n"
            "窗外的风渐渐大了，吹得窗框微微颤动。李明关上窗户，拉好窗帘。\n"
            "早点休息。他对张华说，明天还要早起。\n"
            "张华点点头，走进卧室。李明则留在客厅，继续研究那张地图。\n"
            "红色的标记在灯光下格外醒目。每一个点，都是一条线索，都是一个未知的危险。\n"
            "他用红笔在地图上画了一条线，连接起所有的标记。线条错综复杂，像一张巨大的网。\n"
            "而网的中心，就是那个他们明天要去的地方。\n"
            "李明放下笔，揉了揉酸涩的眼睛。他靠在椅背上，闭上眼睛。\n"
            "脑海中浮现出王强的面孔。那个曾经并肩作战的朋友，如今却站在了未知的阴影里。\n"
            "不管怎样，他都要找到真相。哪怕付出一切代价。\n"
            "客厅里的挂钟滴答作响。时间一分一秒地流逝，而黎明，正在悄然逼近。\n"
            "李明睁开眼，重新坐直身体。他拿起放大镜，仔细地观察地图上的每一个细节。\n"
            "突然，他的目光停留在一个不起眼的红点上。这个点之前被他忽略了。\n"
            "他掏出手机，拍了一张照片，发给了张华。\n"
            "几分钟后，张华从卧室走出来，睡眼惺忪。\n"
            "这是什么？他问。\n"
            "一个废弃的工厂。李明说，但我查过，三个月前有人在那里租用过设备。\n"
            "你的意思是……\n"
            "我怀疑那里是他们的据点之一。李明说。\n"
            "张华凑近地图，眉头紧锁。这太冒险了。\n"
            "所以我们需要计划。李明说，每一个细节都不能出错。\n"
            "两人在客厅里低声讨论，直到东方泛起鱼肚白。\n"
            "新的一天即将开始，而他们，已经没有退路。\n"
            "远处的山峦在暮色中勾勒出模糊的轮廓，像是沉睡的巨兽。\n"
            "风吹过树梢，发出沙沙的响声。几片枯叶从枝头飘落，在空中旋转着，最终落在泥泞的地面上。\n"
            "李明却毫无畏惧。他的目光坚定地望着前方，脚步沉稳而有力。\n"
        )
        result = self._run_self_check(repo, text)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        warnings = sc.get("warnings", [])
        assert not any("prose_like" in w for w in warnings)

    def test_dialogue_straight_emotion_ignored(self, repo):
        """Straight emotion words inside dialogue should be ignored by show_dont_tell heuristic."""
        text = (
            "李明站在窗前，看着外面的雨幕。窗外的街道空无一人。\n"
            "他转过身，看到张华走了进来。张华浑身湿透，脸色苍白。\n"
            "\"我感到很不舒服。\"张华说，\"这里太冷了。\"\n"
            "\"我觉得我们应该换个地方。\"李明说，\"这里不安全。\"\n"
            "\"我知道。\"张华点头，\"但我别无选择。\"\n"
            "\"你明白这意味着什么吗？\"李明盯着他。\n"
            "\"我明白。\"张华苦笑，\"但我已经决定了。\"\n"
            "李明走到桌前，拿起那份文件。文件上的字迹已经有些模糊。\n"
            "\"你发现了什么？\"张华问。\n"
            "\"我察觉到有人在跟踪我们。\"李明压低声音。\n"
            "\"什么？\"张华警觉地看向窗外。\n"
            "\"从昨天开始，我就注意到有人在监视这个房子。\"李明说。\n"
            "\"那你觉得是谁？\"张华问。\n"
            "\"我不确定。\"李明摇头，\"但不管是谁，都不会是朋友。\"\n"
            "张华坐了下来，叹了口气。\"那我们现在该怎么办？\"\n"
            "\"先离开这里。\"李明说，\"然后找个安全的地方再细说。\"\n"
            "\"好。\"张华站起身，\"我跟你走。\"\n"
            "两人收拾好东西，悄悄从后门离开。雨越下越大，街道上积起了水洼。\n"
            "他们沿着小巷走了很久，终于来到了一座废弃的仓库前。\n"
            "\"这里应该安全了。\"李明推开门，\"进来吧。\"\n"
            "仓库里堆满了旧箱子，空气中弥漫着霉味。张华皱了皱眉。\n"
            "\"你确定这里安全？\"他问。\n"
            "\"相对安全。\"李明说，\"至少现在没有人能找到我们。\"\n"
            "张华找了个箱子坐下，\"那你现在可以告诉我真相了吧？\"\n"
            "\"真相？\"李明嘴角一沉，\"真相往往比谎言更可怕。\"\n"
            "\"不管多可怕，我都想知道。\"张华的目光坚定。\n"
            "李明沉默了片刻，然后从口袋里掏出一枚玉佩。\n"
            "\"这是……\"张华瞪大了眼睛。\n"
            "\"我父亲留下的。\"李明说，\"也是一切的开始。\"\n"
            "\"你打算怎么做？\"张华问。\n"
            "\"找到幕后的人。\"李明的目光变得冰冷，\"然后结束这一切。\"\n"
            "两人相视无言，仓库里只剩下雨水敲打铁皮屋顶的声响。\n"
            "张华站起身，走到窗前。窗外的世界一片模糊，仿佛被一层灰色的薄纱笼罩。\n"
            "\"接下来怎么办？\"他背对着李明问道。\n"
            "\"等雨停。\"李明说，\"然后联系老周。\"\n"
            "\"老周？\"张华转过身，\"你相信他？\"\n"
            "\"不信。\"李明坦然道，\"但我们没有选择。\"\n"
            "张华走回箱子旁坐下，双手交叠放在膝上。他的衣服还在滴水，在地板上积成一小滩水渍。\n"
            "李明从背包里掏出一条干毛巾扔给他。\"擦干，别感冒了。\"\n"
            "\"谢谢。\"张华接过毛巾，随意地擦了擦头发。\n"
            "仓库的角落里堆着一些旧报纸，纸张已经泛黄，边缘卷曲。\n"
            "李明走过去，捡起一张看了看日期。三年前的报纸，报道的是一起失踪案。\n"
            "\"你看这个。\"他把报纸递给张华。\n"
            "张华扫了一眼，瞳孔微缩。\"这是……\"\n"
            "\"没错。\"李明点头，\"和我们调查的是同一件事。\"\n"
            "\"三年前就有人注意到了？\"张华的声音有些发紧。\n"
            "\"不仅注意到了。\"李明说，\"还试图阻止过。\"\n"
            "\"结果呢？\"\n"
            "\"失踪了。\"李明的声音低沉，\"就像你父亲一样。\"\n"
            "张华的手攥紧了报纸，指节发白。他低下头，久久没有说话。\n"
            "李明走到他身边，拍了拍他的肩膀。\"我们会找到答案的。\"\n"
            "\"希望如此。\"张华抬起头，目光中闪过一丝疲惫。\n"
            "仓库外传来一阵风声，紧接着是树枝断裂的脆响。两人同时警觉起来。\n"
            "\"有人？\"张华低声问。\n"
            "\"不一定。\"李明走到门边，侧耳倾听。\"可能是风。\"\n"
            "但两人都握紧了手中的武器，随时准备应对突发状况。\n"
            "时间一分一秒地过去，外面的雨势渐渐小了。\n"
            "\"走吧。\"李明说，\"趁着雨停，赶紧离开。\"\n"
            "张华点点头，将报纸塞进口袋。\"不管前面是什么，我都不会退缩。\"\n"
            "\"我知道。\"李明说，\"所以我们才需要彼此。\"\n"
            "两人推开仓库的门，清新的空气扑面而来。天边露出了一丝鱼肚白，新的一天即将开始。\n"
            "\"黎明前的黑暗总是最浓的。\"张华说。\n"
            "\"但太阳总会升起。\"李明迈步向前，\"走吧。\"\n"
            "他们沿着泥泞的小路走去，身后留下两串深浅不一的脚印。\n"
            "而在他们看不见的地方，一双眼睛正透过望远镜注视着他们的一举一动。\n"
            "远处的山峦在暮色中勾勒出模糊的轮廓，像是沉睡的巨兽。\n"
            "风吹过树梢，发出沙沙的响声。几片枯叶从枝头飘落，在空中旋转着，最终落在泥泞的地面上。\n"
            "远处传来几声犬吠，打破了黄昏的宁静。炊烟从村落的屋顶升起，袅袅娜娜地消散在渐暗的天空中。\n"
            "李明收起地图，将它小心翼翼地折叠好，塞回背包的夹层里。他站起身，拍了拍裤腿上的尘土。\n"
            "夜风越来越凉，他拉紧了外套的领口。前方的路还很长，但他已经没有回头的理由。\n"
            "他迈开步子，沿着蜿蜒的山路向前走去。脚下的碎石发出咯吱咯吱的声响。\n"
            "月亮从云层后面探出头来，洒下一地银辉。树影婆娑，像无数张牙舞爪的鬼魅。\n"
            "李明却毫无畏惧。他的目光坚定地望着前方，脚步沉稳而有力。\n"
            "山路尽头，隐约可见一座破旧的庙宇。庙宇的飞檐在月光下泛着青灰色的光。\n"
            "他加快脚步，向着那座庙宇走去。不管那里等待他的是什么，他都准备好了。\n"
            "身后的树林里传来一阵异响。李明停下脚步，侧耳倾听。是一只夜枭的叫声。\n"
            "他松了口气，继续前行。山路越来越陡，但他的速度丝毫没有减慢。\n"
            "终于，他来到了庙宇前。大门紧闭，门上的漆已经斑驳脱落。\n"
            "他推了推门，门轴发出刺耳的吱呀声。一股霉味扑面而来。\n"
            "庙宇内昏暗无光，只有几缕月光从破损的屋顶漏下来。他掏出手机，打开手电筒。\n"
            "光束扫过四周，墙壁上布满了蛛网和灰尘。正中央是一尊残破的佛像，面容已经模糊不清。\n"
            "他走到佛像前，注意到底座上刻着一行小字。他蹲下身，仔细地辨认着。\n"
            "字迹已经风化，但他还是读出了关键的内容：真相，就在你脚下。\n"
            "他愣了一下，随即开始检查地面。一块石板与周围的地面略有不同。\n"
            "他用手指敲了敲，发出空洞的声响。下面有东西。\n"
            "他从背包里取出一把短刀，插入石板的缝隙，用力一撬。\n"
            "石板缓缓移开，露出一个黑漆漆的洞口。冷风从洞底涌上来，带着一股潮湿的泥土气息。\n"
            "他深吸一口气，打开手机的手电筒，朝着洞口照去。\n"
            "洞底不深，隐约可见一个铁盒的轮廓。他没有犹豫，纵身跳了下去。\n"
        )
        result = self._run_self_check(repo, text)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        warnings = sc.get("warnings", [])
        assert not any("show_dont_tell" in w for w in warnings)

    def test_homonym_gan_not_sensory(self, repo):
        """Homonym '干' in contexts like '干活/干净' should not inflate sensory detail count."""
        base = (
            "李明推开门，走进屋内。房间很干净，桌上摆着几份文件。\n"
            "他坐下来，开始干活。文件上的数字密密麻麻，看得他眼花缭乱。\n"
            "\"你干完了吗？\"门外传来一个声音。\n"
            "\"还没。\"李明回答，\"这些数据太复杂了。\"\n"
            "\"需要帮忙吗？\"那个声音又问。\n"
            "\"不用。\"李明说，\"我自己能搞定。\"\n"
            "他继续翻阅文件，看到其中有一份特别重要。\n"
            "\"这是什么？\"他自言自语。\n"
            "文件上记录着一些他从未见过的名字和数字。\n"
            "\"奇怪。\"他皱起眉头。\n"
            "就在这时，门外传来脚步声。李明警觉地抬起头。\n"
            "\"谁？\"他问。\n"
            "\"是我。\"张华推门进来，\"你还没下班？\"\n"
            "\"有点事要处理。\"李明说。\n"
            "\"别太拼了。\"张华拍了拍他的肩膀，\"身体要紧。\"\n"
            "\"我清楚。\"李明笑了笑。\n"
            "张华离开后，李明又埋头工作。窗外的天色渐渐暗了下来。\n"
            "\"今天就到这里吧。\"他合上文件，站起身。\n"
            "走廊里静悄悄的，只有他的脚步声在回响。\n"
            "他走到电梯前，按下了按钮。电梯门缓缓打开。\n"
            "\"终于结束了。\"他走进电梯，靠在墙上。\n"
            "电梯下行的过程中，他脑子里还在想着那些数字。\n"
            "\"明天再继续吧。\"他对自己说。\n"
            "走出大楼，夜风拂面，带来一丝凉意。\n"
            "他深吸一口气，朝着家的方向走去。\n"
            "街道上的路灯已经亮起，昏黄的光线照亮了前方的路。\n"
            "\"又是一个漫长的夜晚。\"他喃喃自语。\n"
            "他加快了脚步，希望能在雨下大之前回到家。\n"
            "远处传来雷声，空气中弥漫着雨前的气息。\n"
            "\"快点。\"他对自己说。\n"
            "终于，他推开了家门。屋子里一片温暖。\n"
            "\"我回来了。\"他说。\n"
            "\"饭在桌上。\"妻子从厨房里探出头来，\"快去洗手。\"\n"
            "\"好。\"李明笑了笑，走向洗手间。\n"
            "洗完手，他坐在餐桌前，看着眼前的饭菜。\n"
            "\"今天辛苦了。\"妻子说。\n"
            "\"还好。\"李明说，\"就是有点累。\"\n"
            "\"那早点休息。\"妻子说。\n"
            "\"嗯。\"李明点点头，开始吃饭。\n"
        )
        # Triple the text to pass word gate
        text = base * 3
        result = self._run_self_check(repo, text)
        trace = result.get("_trace", {})
        sc = trace.get("self_check", {})
        assert sc.get("passed") is True
        warnings = sc.get("warnings", [])
        # Should not trigger sensory_detail because "干" replaced with "干燥/干涩"
        assert not any("sensory_detail" in w for w in warnings)

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


class TestAuthorLiveCallBudget:
    """Live Author drafting should not turn one slow request into a long retry loop."""

    def test_plain_text_draft_uses_single_attempt_without_mutating_provider_config(self, repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.config.settings import LLMConfig
        from novel_factory.llm.provider import LLMProvider

        class LiveLikeLLM(LLMProvider):
            def __init__(self):
                self.config = LLMConfig(
                    base_url="https://example.test/v1",
                    api_key="sk-test",
                    model="slow-author-model",
                    request_timeout_seconds=60,
                    retry_attempts=3,
                )
                self.calls = []

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None, max_retries=None):
                return {}

            def invoke_text(self, messages, temperature=None, max_tokens=None, max_retries=None):
                self.calls.append({
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "max_retries": max_retries,
                })
                return "他推开门，潮湿的风贴着袖口钻进来。" * 120

        llm = LiveLikeLLM()
        agent = AuthorAgent(repo, llm)
        output = agent._try_plain_text_draft(
            {
                "project_id": "test_proj",
                "chapter_number": 1,
                "chapter_status": "scripted",
                "llm_mode": "real",
            },
            "创作",
            agent.build_context({
                "project_id": "test_proj",
                "chapter_number": 1,
                "chapter_status": "scripted",
            }),
        )

        assert output.content
        assert llm.calls[-1]["max_retries"] == 1
        assert llm.calls[-1]["max_tokens"] <= 4096
        assert llm.config.request_timeout_seconds == 60
        assert llm.config.retry_attempts == 3
