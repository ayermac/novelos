"""v6.4.2: Polisher Dialogue and Scene Texture Pass tests.

Tests SYSTEM_PROMPT constraints, build_context quality reminders,
and self-check warning heuristics.
Does NOT modify workflow topology.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from novel_factory.models.state import ChapterStatus


# Sample texts for heuristic testing
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

SAMPLE_EXCESSIVE_EXPLANATION = (
    "李明感到一阵愤怒涌上心头。他看着眼前的对手，暗自思忖：这次一定要赢。\n"
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
    "综上所述，本章讲述了李明等人逃离地下设施的过程。\n"
    "总之，他们虽然成功脱险，但前路依然充满未知。\n"
    "简单来说，这只是一个开始。\n"
)

SAMPLE_UNIFORM_PACING = (
    "李明推开房门，走进屋内。他环顾四周，确认没有异常。\n\n"
    "他走到窗前，看着外面的街道。行人稀少，一切安静。\n\n"
    "他转身走向书桌，拿起一份文件。文件上记录着重要的信息。\n\n"
    "他仔细阅读文件，眉头紧锁。情况比他想象的更加复杂。\n\n"
    "他放下文件，揉了揉太阳穴。需要想一个对策。\n\n"
    "他站起身，在房间里来回踱步。每一步都显得格外沉重。\n\n"
    "他停下脚步，看向窗外。天色渐暗，夜幕即将降临。\n\n"
    "他走到门口，侧耳倾听。走廊里没有任何动静。\n\n"
    "他打开门，探头向外张望。一切正常。\n\n"
    "他关上门，回到房间。现在不是行动的时候。\n\n"
    "他坐在椅子上，闭上眼睛。脑海中浮现出各种可能性。\n\n"
    "他睁开眼睛，目光坚定。无论如何，他都必须完成使命。\n\n"
    "他站起身，整理了一下衣服。准备迎接即将到来的挑战。\n\n"
    "他走到窗前，最后看了一眼外面的景色。然后拉上了窗帘。\n\n"
    "他回到书桌前，拿起笔。在纸上写下几个关键词。\n\n"
    "他盯着这些词看了很久。试图找出其中的关联。\n\n"
    "他放下笔，靠在椅背上。时间在一分一秒地流逝。\n\n"
    "他站起身，走到床边。和衣躺下，却毫无睡意。\n\n"
    "他盯着天花板，思绪万千。明天将会发生什么？\n\n"
    "他翻了个身，强迫自己闭上眼睛。必须保存体力。\n\n"
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
    repo.add_chapter("test_proj", 1, "第一章", status="drafted")
    repo.save_chapter_content("test_proj", 1, "草稿内容" * 50, "第一章")
    repo.create_instruction(
        "test_proj", 1,
        objective="测试目标",
        key_events='["事件1", "事件2"]',
        emotion_tone="紧张",
        ending_hook="悬念",
        word_target=2500,
    )
    yield repo
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestPolisherSystemPrompt:
    """Polisher SYSTEM_PROMPT contains v6.4.2 constraints."""

    def test_prompt_contains_fact_boundary(self):
        from novel_factory.agents.polisher import POLISHER_SYSTEM_PROMPT
        assert "保留剧情事实" in POLISHER_SYSTEM_PROMPT or "不得改写剧情走向" in POLISHER_SYSTEM_PROMPT

    def test_prompt_contains_dialogue_naturalization(self):
        from novel_factory.agents.polisher import POLISHER_SYSTEM_PROMPT
        assert "对白自然化" in POLISHER_SYSTEM_PROMPT
        assert "语气词" in POLISHER_SYSTEM_PROMPT or "打断" in POLISHER_SYSTEM_PROMPT

    def test_prompt_contains_scene_texture(self):
        from novel_factory.agents.polisher import POLISHER_SYSTEM_PROMPT
        assert "场景质感" in POLISHER_SYSTEM_PROMPT
        assert "感官" in POLISHER_SYSTEM_PROMPT or "光影" in POLISHER_SYSTEM_PROMPT

    def test_prompt_contains_rhythm(self):
        from novel_factory.agents.polisher import POLISHER_SYSTEM_PROMPT
        assert "节奏" in POLISHER_SYSTEM_PROMPT
        assert "长短句" in POLISHER_SYSTEM_PROMPT or "短句" in POLISHER_SYSTEM_PROMPT

    def test_prompt_contains_anti_ai(self):
        from novel_factory.agents.polisher import POLISHER_SYSTEM_PROMPT
        assert "总结句" in POLISHER_SYSTEM_PROMPT or "综上所述" in POLISHER_SYSTEM_PROMPT
        assert "直白心理" in POLISHER_SYSTEM_PROMPT or "感到愤怒" in POLISHER_SYSTEM_PROMPT


class TestPolisherBuildContext:
    """Polisher build_context includes quality-derived writing reminders."""

    def test_context_contains_polishing_reminders(self, repo):
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, **kw):
                return ""

        agent = PolisherAgent(repo, StubLLM())
        ctx = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
        })
        assert "润色写作提醒" in ctx
        assert "对白自然化" in ctx
        assert "场景质感" in ctx
        assert "节奏变化" in ctx
        assert "去AI味" in ctx or "Show, Don't Tell" in ctx

    def test_context_preserves_fact_lock(self, repo):
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, **kw):
                return ""

        agent = PolisherAgent(repo, StubLLM())
        ctx = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
        })
        assert "事实锁定" in ctx


class TestPolisherSelfCheckWarnings:
    """v6.4.2 Polisher deterministic warning heuristics."""

    def _run_polisher(self, repo, content: str):
        """Helper to run polisher with given content."""
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        # Ensure content is long enough to pass word gate
        while len(content) < 2200:
            content = content + "\n" + content

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "content": content,
                    "fact_change_risk": "none",
                    "changed_scope": ["sentence", "dialogue"],
                    "summary": "测试润色",
                }
            def invoke_text(self, messages, **kw):
                return ""

        agent = PolisherAgent(repo, StubLLM())
        state = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "llm_mode": "stub",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }
        result = agent.run(state)
        return result

    def test_low_dialogue_triggers_warning(self, repo):
        result = self._run_polisher(repo, SAMPLE_LOW_DIALOGUE * 5)
        events = result.get("_exec_events", [])
        warn_events = [e for e in events if e.get("event_type") == "polisher_warnings"]
        assert len(warn_events) > 0
        warnings = warn_events[0].get("payload", {}).get("warnings", [])
        assert any("dialogue_naturalness_low" in w for w in warnings)

    def test_low_sensory_triggers_warning(self, repo):
        result = self._run_polisher(repo, SAMPLE_LOW_SENSORY * 5)
        events = result.get("_exec_events", [])
        warn_events = [e for e in events if e.get("event_type") == "polisher_warnings"]
        assert len(warn_events) > 0
        warnings = warn_events[0].get("payload", {}).get("warnings", [])
        assert any("scene_texture_low" in w for w in warnings)

    def test_excessive_explanation_triggers_warning(self, repo):
        result = self._run_polisher(repo, SAMPLE_EXCESSIVE_EXPLANATION * 5)
        events = result.get("_exec_events", [])
        warn_events = [e for e in events if e.get("event_type") == "polisher_warnings"]
        assert len(warn_events) > 0
        warnings = warn_events[0].get("payload", {}).get("warnings", [])
        assert any("excessive_explanation" in w for w in warnings)

    def test_uniform_pacing_triggers_warning(self, repo):
        result = self._run_polisher(repo, SAMPLE_UNIFORM_PACING * 5)
        events = result.get("_exec_events", [])
        warn_events = [e for e in events if e.get("event_type") == "polisher_warnings"]
        assert len(warn_events) > 0
        warnings = warn_events[0].get("payload", {}).get("warnings", [])
        assert any("pacing_too_uniform" in w for w in warnings)

    def test_normal_text_few_warnings(self, repo):
        """Normal stub content should have minimal warnings."""
        from novel_factory.llm.stub_provider import _STORY_TEMPLATES
        normal = _STORY_TEMPLATES[1]["content"]
        result = self._run_polisher(repo, normal)
        assert result.get("chapter_status") == ChapterStatus.POLISHED.value
        events = result.get("_exec_events", [])
        warn_events = [e for e in events if e.get("event_type") == "polisher_warnings"]
        # Normal text may have 0-2 minor warnings; should not have excessiveExplanation or lowDialogue
        if warn_events:
            warnings = warn_events[0].get("payload", {}).get("warnings", [])
            assert not any("excessive_explanation" in w for w in warnings)
            assert not any("pacing_too_uniform" in w for w in warnings)

    def test_does_not_block_workflow(self, repo):
        """Warnings must not prevent status advance to polished."""
        result = self._run_polisher(repo, SAMPLE_LOW_DIALOGUE * 5)
        assert result.get("chapter_status") == ChapterStatus.POLISHED.value
        assert "error" not in result or result.get("error") is None


class TestStubPolisherContract:
    """Stub provider Polisher output meets v6.4.2 contract."""

    def test_stub_polisher_scope_includes_scene_texture(self):
        from novel_factory.llm.stub_provider import StubLLM
        stub = StubLLM()
        result = stub.invoke_json(
            [{"role": "user", "content": "章节号: 1\n任务: 润色"}],
            schema=type("PolisherOutput", (), {}),
        )
        assert result.get("fact_change_risk") == "none"
        changed_scope = result.get("changed_scope", [])
        assert "scene_texture" in changed_scope or "dialogue" in changed_scope

    def test_stub_polisher_summary_not_generic(self):
        from novel_factory.llm.stub_provider import StubLLM
        stub = StubLLM()
        result = stub.invoke_json(
            [{"role": "user", "content": "章节号: 1\n任务: 润色"}],
            schema=type("PolisherOutput", (), {}),
        )
        summary = result.get("summary", "")
        assert "微调表达" not in summary
        assert len(summary) > 4


class TestWorkflowNotModified:
    """v6.4.2 does not modify workflow topology."""

    def test_polisher_still_routes_to_polished(self, repo):
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        base_content = "这是一段测试正文内容，用于验证 Polisher Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 44

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "content": long_content,
                    "fact_change_risk": "none",
                    "changed_scope": ["sentence", "dialogue"],
                    "summary": "测试润色",
                }
            def invoke_text(self, messages, **kw):
                return ""

        agent = PolisherAgent(repo, StubLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "llm_mode": "stub",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.POLISHED.value
        chapter = repo.get_chapter("test_proj", 1)
        assert chapter["content"] is not None
