"""Tests for agents/ — stub LLM agent integration tests.

These tests use a StubLLMProvider to avoid real API calls.
They verify that agents correctly call the LLM, validate output,
and update the database.
"""

from __future__ import annotations

import json
import tempfile
from typing import Any

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState


class StubLLMProvider(LLMProvider):
    """Stub LLM that returns predetermined JSON responses."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self._call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return json.dumps(self.invoke_json(messages))


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_agent.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


@pytest.fixture
def seeded_repo(repo):
    """Seed a project and chapter in 'planned' status."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("test_proj", "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        ("test_proj", 1, "第一章 测试", "planned"),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("test_proj", 1, "测试目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    # Add a character
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("test_proj", "林默", "protagonist", "主角"),
    )
    conn.commit()
    conn.close()
    return repo


class TestPlannerAgent:
    def test_planner_creates_instruction(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent

        stub = StubLLMProvider([{
            "chapter_brief": {
                "objective": "林默Lv1，本章目标：突破困境",
                "required_events": ["事件1"],
                "plots_to_plant": ["P001"],
                "plots_to_resolve": [],
                "ending_hook": "悬念",
                "constraints": ["禁止冷笑"],
            }
        }])

        agent = PlannerAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.PLANNED.value

        # Verify instruction was saved
        instr = seeded_repo.get_instruction("test_proj", 1)
        assert instr is not None

    def test_planner_derives_word_target_when_existing_is_empty(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET word_target = NULL WHERE project_id = ? AND chapter_number = ?",
            ("test_proj", 1),
        )
        conn.commit()
        conn.close()

        stub = StubLLMProvider([{
            "objective": "继续推进主线冲突",
            "key_events": ["事件1", "事件2"],
            "plots_to_plant": [],
            "plots_to_resolve": [],
            "ending_hook": "悬念",
            "constraints": [],
        }])

        agent = PlannerAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)

        assert result["chapter_status"] == ChapterStatus.PLANNED.value
        instr = seeded_repo.get_instruction("test_proj", 1)
        assert instr["word_target"] == 3000

    def test_planner_context_includes_recent_story_facts_and_trusted_memory_batch(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent

        conn = seeded_repo._conn()
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
            ("test_proj", 2, "第二章 测试", "planned"),
        )
        conn.commit()
        conn.close()
        seeded_repo.save_chapter_content("test_proj", 1, "林默收到旧工业区邀约。", "第一章 测试")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {"悬念": ["旧工业区邀约是谁发出的"]},
            "第1章状态卡",
        )
        seeded_repo.create_story_fact(
            "test_proj",
            "chapter_1.appointment",
            "time_constraint",
            json.dumps({"time": "三天后", "location": "旧工业区"}, ensure_ascii=False),
            subject="黑影邀约",
            attribute="会面时间地点",
            source_chapter=1,
            source_agent="memory_curator",
        )

        fallback = seeded_repo.create_memory_batch("test_proj", chapter_number=1, summary="第1章记忆提取 - 状态卡兜底 (1项)")
        seeded_repo.create_memory_item(
            batch_id=fallback["id"],
            project_id="test_proj",
            target_table="story_facts",
            operation="create",
            after_json=json.dumps({"fact_key": "fallback"}, ensure_ascii=False),
            confidence=0.45,
            evidence_text="低可信",
            rationale="状态卡兜底候选：未经过 MemoryCurator LLM 复核，请人工确认后应用。",
        )
        trusted = seeded_repo.create_memory_batch("test_proj", chapter_number=1, summary="第1章记忆提取 (2项)")
        seeded_repo.create_memory_item(
            batch_id=trusted["id"],
            project_id="test_proj",
            target_table="plot_holes",
            operation="update",
            after_json=json.dumps({"code": "PH-014", "title": "旧址会面与72小时访客"}, ensure_ascii=False),
            confidence=0.94,
            evidence_text="黑影再次约定三天后旧工业区",
            rationale="正文复核提取。",
        )

        agent = PlannerAgent(seeded_repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "planned",
        })

        assert "【强制继承资料】" in context
        assert "time_constraint" in context
        assert "三天后" in context
        assert "PH-014" in context
        assert "状态卡兜底候选" not in context

    def test_planner_repairs_brief_that_ignores_previous_suspense(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent

        conn = seeded_repo._conn()
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
            ("test_proj", 2, "第二章 测试", "planned"),
        )
        conn.commit()
        conn.close()
        seeded_repo.save_chapter_content(
            "test_proj",
            1,
            "黑影抬起左手，掌心有微弱蓝光。'三天后，旧工业区。'",
            "第一章 测试",
        )
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {"悬念": ["黑影身份不明", "三天后旧工业区约定"]},
            "第1章状态卡",
        )

        stub = StubLLMProvider([{
            "chapter_brief": {
                "objective": "龙华集团试探林默",
                "required_events": ["龙华集团代表接触林默"],
                "plots_to_plant": [],
                "plots_to_resolve": [],
                "ending_hook": "新危机出现",
                "constraints": [],
            }
        }])
        agent = PlannerAgent(seeded_repo, stub)

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert "error" not in result
        instruction = seeded_repo.get_instruction("test_proj", 2)
        assert instruction is not None
        assert "三天后" in instruction["objective"]
        assert "三天后" in instruction["key_events"]
        assert "本章必须回应或明确延期" in instruction["key_events"]
        assert any(ev["event_type"] == "planner_inheritance_repaired" for ev in result["_exec_events"])

    def test_planner_records_chapter_objective_checker_skill_run(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.skills.registry import SkillRegistry

        stub = StubLLMProvider([{
            "chapter_brief": {
                "objective": "林默Lv1，本章要夺回账册并发现新的追兵",
                "required_events": ["夺回账册"],
                "plots_to_plant": [],
                "plots_to_resolve": [],
                "ending_hook": "追兵现身",
                "constraints": ["不改变上一章数值"],
            }
        }])

        agent = PlannerAgent(seeded_repo, stub, skill_registry=SkillRegistry())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.PLANNED.value
        runs = seeded_repo.get_skill_runs("test_proj", skill_id="chapter-objective-checker", agent_id="planner", chapter_number=1)
        assert runs

    def test_non_critical_planner_skill_failure_does_not_crash(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.skills.registry import SkillRegistry

        stub = StubLLMProvider([{
            "chapter_brief": {
                "objective": "",
                "required_events": [],
                "plots_to_plant": [],
                "plots_to_resolve": [],
                "ending_hook": "",
                "constraints": [],
            }
        }])

        agent = PlannerAgent(seeded_repo, stub, skill_registry=SkillRegistry())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert "error" not in result
        runs = seeded_repo.get_skill_runs("test_proj", skill_id="chapter-objective-checker", agent_id="planner", chapter_number=1)
        assert runs and runs[0]["ok"] == 0


class TestScreenwriterAgent:
    def test_screenwriter_creates_beats(self, seeded_repo):
        from novel_factory.agents.screenwriter import ScreenwriterAgent

        stub = StubLLMProvider([{
            "scene_beats": [
                {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "turn": "转折", "plot_refs": ["P001"], "hook": "钩子"},
            ]
        }])

        agent = ScreenwriterAgent(seeded_repo, stub)
        # Set chapter to planned status for screenwriter
        seeded_repo.update_chapter_status("test_proj", 1, "planned")
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.SCRIPTED.value

        beats = seeded_repo.get_scene_beats("test_proj", 1)
        assert len(beats) == 1

    def test_screenwriter_repairs_missing_sequence(self, seeded_repo):
        from novel_factory.agents.screenwriter import ScreenwriterAgent

        stub = StubLLMProvider([{
            "scene_beats": [
                {"scene_goal": "开场", "conflict": "冲突", "turn": "转折", "plot_refs": ["P001"], "hook": "钩子"},
                {"scene_goal": "升级", "conflict": "阻碍", "turn": "反转", "plot_refs": None, "hook": "悬念"},
            ]
        }])

        agent = ScreenwriterAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "planned")
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.SCRIPTED.value
        beats = seeded_repo.get_scene_beats("test_proj", 1)
        assert [beat["sequence"] for beat in beats] == [1, 2]
        assert beats[1]["plot_refs"] == "[]"

    def test_screenwriter_records_scene_conflict_checker_skill_run(self, seeded_repo):
        from novel_factory.agents.screenwriter import ScreenwriterAgent
        from novel_factory.skills.registry import SkillRegistry

        stub = StubLLMProvider([{
            "scene_beats": [
                {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "turn": "转折", "plot_refs": ["P001"], "hook": "钩子"},
            ]
        }])

        seeded_repo.update_chapter_status("test_proj", 1, "planned")
        agent = ScreenwriterAgent(seeded_repo, stub, skill_registry=SkillRegistry())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })
        assert result["chapter_status"] == ChapterStatus.SCRIPTED.value
        runs = seeded_repo.get_skill_runs("test_proj", skill_id="scene-conflict-checker", agent_id="screenwriter", chapter_number=1)
        assert runs


class TestAuthorAgent:
    def test_author_context_derives_missing_word_target(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET word_target = NULL WHERE project_id = ? AND chapter_number = ?",
            ("test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })

        assert "字数目标: None" not in context
        assert "至少 2550 字符" in context
        assert "建议写到 3050 字符左右" in context

    def test_author_context_includes_scene_beat_turn(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_scene_beats("test_proj", 1, [
            {
                "sequence": 1,
                "scene_goal": "林默进入废弃车站",
                "conflict": "监控画面与现实环境不一致",
                "turn": "服务器显示目标已死亡，本地缓存却显示微弱存活",
                "hook": "通讯里出现不属于队友的人声",
            },
        ])

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })

        assert "【场景 Beat】" in context
        assert "目标: 林默进入废弃车站" in context
        assert "冲突: 监控画面与现实环境不一致" in context
        assert "转折: 服务器显示目标已死亡，本地缓存却显示微弱存活" in context
        assert "钩子: 通讯里出现不属于队友的人声" in context

    def test_author_plain_text_context_includes_all_scene_beats(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_scene_beats("test_proj", 1, [
            {
                "sequence": i,
                "scene_goal": f"第{i}个场景目标",
                "conflict": f"第{i}个场景冲突",
                "turn": f"第{i}个场景转折",
                "hook": f"第{i}个场景钩子",
            }
            for i in range(1, 8)
        ])

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        context = agent._build_plain_text_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }, "")

        assert "1. 第1个场景目标" in context
        assert "7. 第7个场景目标" in context
        assert "第7个场景转折" in context
        assert "第7个场景钩子" in context
        assert "必须按 sequence 覆盖全部 beat" in context

    def test_author_scene_beat_coverage_detects_missing_ending_beats(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入车站", "turn": "发现异常", "hook": "下探站台"},
            {"sequence": 2, "scene_goal": "定位住户", "turn": "数据被篡改", "hook": "系统建议忽略"},
            {"sequence": 3, "scene_goal": "触发隔离", "turn": "系统记录违规", "hook": "住户醒来"},
            {"sequence": 4, "scene_goal": "救出住户", "turn": "灵体停止追击", "hook": "许知夏追问选择"},
            {"sequence": 5, "scene_goal": "任务结算界面三段式展示", "turn": "失败名单滚动出现", "hook": "周砚白名字浮现"},
            {"sequence": 6, "scene_goal": "白塔私信出现", "turn": "周砚白发来坐标", "hook": "聊聊十二年前的事"},
        ])

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        issues = agent._scene_beat_coverage_issues({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }, "林默进入车站，定位住户，触发隔离，然后故事停在站台对抗中。")

        assert issues
        assert any("scene beat" in issue["message"] for issue in issues)

    def test_author_final_scene_beat_guard_converges_instead_of_retrying(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        class MissingHookLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.text_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise AssertionError("real author path should use plain text")

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ) -> str:
                self.text_calls += 1
                if self.text_calls >= 3:
                    return (
                        "林默没有再看结算倒影，白塔私信出现。"
                        "未知联系人逼近的压迫感从屏幕背后渗出来。"
                        "周砚白发来坐标，光标停在一行新字上：聊聊十二年前的事。"
                    ) * 2
                return (
                    "林默进入车站，定位住户，触发隔离。"
                    "他救出住户后，灵体停止追击，许知夏追问选择。"
                    "任务结算界面三段式展示，失败名单滚动出现。"
                    "但是正文停在屏幕闪烁处，没有写到最后的私信。"
                ) * 3

        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入车站", "conflict": "门禁失效", "turn": "发现异常", "hook": "下探站台"},
            {"sequence": 2, "scene_goal": "定位住户", "conflict": "数据被遮蔽", "turn": "数据被篡改", "hook": "系统建议忽略"},
            {"sequence": 3, "scene_goal": "触发隔离", "conflict": "警报响起", "turn": "系统记录违规", "hook": "住户醒来"},
            {"sequence": 4, "scene_goal": "任务结算界面三段式展示", "conflict": "结算异常", "turn": "失败名单滚动出现", "hook": "周砚白名字浮现"},
            {"sequence": 5, "scene_goal": "白塔私信出现", "conflict": "未知联系人逼近", "turn": "周砚白发来坐标", "hook": "聊聊十二年前的事"},
        ])
        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET ending_hook=?, word_target=? WHERE project_id=? AND chapter_number=?",
            ("周砚白发来坐标，聊聊十二年前的事", 120, "test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, MissingHookLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result.get("error") != "Author 未完成场景 beat 覆盖，正文未写到章末钩子"
        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        assert agent.llm.text_calls == 3
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert "白塔私信出现" in chapter["content"]
        assert "周砚白发来坐标" in chapter["content"]
        assert "聊聊十二年前的事" in chapter["content"]

    def test_author_scene_beat_coverage_passes_when_ending_lands(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入车站", "turn": "发现异常", "hook": "下探站台"},
            {"sequence": 2, "scene_goal": "定位住户", "turn": "数据被篡改", "hook": "系统建议忽略"},
            {"sequence": 3, "scene_goal": "触发隔离", "turn": "系统记录违规", "hook": "住户醒来"},
            {"sequence": 4, "scene_goal": "救出住户", "turn": "灵体停止追击", "hook": "许知夏追问选择"},
            {"sequence": 5, "scene_goal": "任务结算界面三段式展示", "turn": "失败名单滚动出现", "hook": "周砚白名字浮现"},
            {"sequence": 6, "scene_goal": "白塔私信出现", "turn": "周砚白发来坐标", "hook": "聊聊十二年前的事"},
        ])

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        content = (
            "林默进入车站，定位住户，完成隔离救援。\n\n"
            "尾段里，他救出住户后，灵体停止追击，许知夏追问选择。"
            "随后任务结算界面三段式展示，失败名单滚动出现，周砚白名字浮现。"
            "随后白塔私信出现，周砚白发来坐标，邀请他聊聊十二年前的事。"
            "林默回头确认救出住户，灵体停止追击，许知夏追问选择。悬念没有消失。"
        )
        issues = agent._scene_beat_coverage_issues({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }, content)

        assert issues == []

    def test_author_scene_beat_coverage_skips_literal_check_for_generic_ending_hook(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入图书馆", "turn": "古籍异常", "hook": "玉佩发热"},
            {"sequence": 2, "scene_goal": "林清雪试探", "turn": "看见灰气", "hook": "医院异常伤者"},
            {"sequence": 3, "scene_goal": "叔叔来电", "turn": "提到城西", "hook": "书房地图"},
            {"sequence": 4, "scene_goal": "夜探旧巷", "turn": "罗盘指针锁定韩立", "hook": "黑影说出空灵根和韩家祭器"},
        ])
        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET ending_hook=? WHERE project_id=? AND chapter_number=?",
            ("留下新的未解线索", "test_proj", 1),
        )
        conn.commit()
        conn.close()

        content = (
            "韩立白天查完古籍，夜里绕进旧巷。"
            + ("雨声贴着墙根往下淌。" * 80)
            + "韩立夜探旧巷时，巷口的黑影抬起罗盘，罗盘指针锁定韩立胸前。"
            "他贴身的玉佩烫得像一枚火炭。黑影压低声音："
            "黑影说出空灵根和韩家祭器，果然都在这里。"
        )

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        issues = agent._scene_beat_coverage_issues({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }, content)

        assert issues == []

    def test_author_scene_beat_coverage_allows_middle_beats_before_tail(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入车站", "turn": "发现异常", "hook": "下探站台"},
            {"sequence": 2, "scene_goal": "定位住户", "turn": "数据被篡改", "hook": "系统建议忽略"},
            {"sequence": 3, "scene_goal": "触发隔离", "turn": "系统记录违规", "hook": "住户醒来"},
            {"sequence": 4, "scene_goal": "提出替代方案", "turn": "隔离结界展开", "hook": "魏承霜通讯切入"},
            {"sequence": 5, "scene_goal": "强行突破进入站台", "turn": "住户手腕有制服编码", "hook": "别相信系统"},
            {"sequence": 6, "scene_goal": "任务结算界面三段式展示", "turn": "失败名单滚动出现", "hook": "周砚白名字浮现"},
        ])

        middle = (
            "进入车站后，林默发现异常，下探站台。定位住户时数据被篡改，系统建议忽略。"
            "他触发隔离，系统记录违规，住户醒来。随后他提出替代方案，隔离结界展开，"
            "魏承霜通讯切入。林默强行突破进入站台，看到住户手腕有制服编码，对方低声说别相信系统。"
        )
        tail = (
            "尾段里，任务结算界面三段式展示，失败名单滚动出现。"
            "周砚白名字浮现，林默盯着那行字没有说话。悬念没有消失。"
        )
        content = middle + ("过渡描写。" * 120) + tail

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        issues = agent._scene_beat_coverage_issues({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }, content)

        assert issues == []

    def test_author_scene_beat_coverage_accepts_paraphrased_final_hook_tail(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入旧库", "turn": "黄光逼近", "hook": "镜头锁定"},
            {"sequence": 2, "scene_goal": "拖延通讯", "turn": "陈科追问", "hook": "旁路监听"},
            {"sequence": 3, "scene_goal": "复核纸册暗记", "turn": "发现新盐痕", "hook": "投放者刚离开"},
            {"sequence": 4, "scene_goal": "复核七分钟窗口", "turn": "底档同批次", "hook": "空白登记码"},
            {"sequence": 5, "scene_goal": "处理外环临时潮汐授权", "turn": "确认堤坝外侧临时潮汐授权", "hook": "旧排潮井箭头"},
            {"sequence": 6, "scene_goal": "沿离线物理痕迹绕向堤坝外侧", "turn": "发现外侧检潮孔", "hook": "新刮痕仍带潮热"},
            {
                "sequence": 7,
                "scene_goal": "让陆澈以非联网方式脱离旧库封控范围，但保留系统追踪压迫，并抵达下一处与“外”级授权相关的门禁结构前",
                "turn": "他利用旧排潮井的机械潮阀回落间隙，从无电子反馈的检潮孔爬向堤坝外侧；身后黄光无法穿透厚混凝土，却沿着旧库连廊转向，说明封控系统已把搜索口径从“人”改成“外级授权残页”",
                "hook": "堤坝外侧检潮孔尽头嵌着一只旧门禁轮盘，轮盘中央刻着“外级临时授权”，签发人栏被一枚新压上的盐封盖住，而盐封边缘仍在发热",
            },
        ])

        content = (
            "陆澈在维护通道里完成前段核验。" + ("潮声压着墙体。" * 90) +
            "\n\n他将纸册和暗记塞进内袋，双手扣住检潮孔边缘的旧格栅。"
            "一阵低频震颤顺着混凝土传来，旧排潮井的机械潮阀正在回落。"
            "陆澈借着这股回震的掩护，猛地推开格栅，侧身挤入狭窄的检潮孔。\n\n"
            "身后，审计黄光扫过他刚才站立的位置，却无法穿透厚重的混凝土墙体。"
            "光斑沿着旧库连廊急速转向——封控系统的搜索口径变了，它们不再找人，"
            "而是在找那张“外级授权残页”。\n\n"
            "陆澈在逼仄的孔道内匍匐，盐砂磨破手背，直到前方透进一丝湿冷的风。"
            "堤坝外侧检潮孔的尽头，嵌着一只锈迹斑斑的旧门禁轮盘。\n\n"
            "他伸手抹去轮盘中央的灰垢，“外级临时授权”几个字赫然入目。\n\n"
            "视线下移，签发人栏的位置被一枚新压上的盐封死死盖住。\n\n"
            "陆澈的指尖悬在盐封上方。盐封边缘的潮热还未散去，"
            "像刚有人在这里按下了他的命运。悬念没有消失。"
        )

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        issues = agent._scene_beat_coverage_issues({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }, content)

        assert issues == []

    def test_author_scene_beat_repair_appends_missing_tail_before_full_rewrite(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.models.schemas import AuthorOutput

        class TailRepairLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.text_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise AssertionError("tail repair should use plain text")

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ) -> str:
                self.text_calls += 1
                assert "只补结尾" in messages[-1]["content"]
                return (
                    "林默没有再看结算倒影，白塔私信在屏幕边缘弹出。"
                    "周砚白发来坐标，光标停在一行新字上：聊聊十二年前的事。"
                    "他终于明白，失败名单不是结算，而是下一道门。"
                )

        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入车站", "turn": "发现异常", "hook": "下探站台"},
            {"sequence": 2, "scene_goal": "定位住户", "turn": "数据被篡改", "hook": "系统建议忽略"},
            {"sequence": 3, "scene_goal": "触发隔离", "turn": "系统记录违规", "hook": "住户醒来"},
            {"sequence": 4, "scene_goal": "救出住户", "turn": "灵体停止追击", "hook": "许知夏追问选择"},
            {"sequence": 5, "scene_goal": "任务结算界面三段式展示", "turn": "失败名单滚动出现", "hook": "周砚白名字浮现"},
            {"sequence": 6, "scene_goal": "白塔私信出现", "turn": "周砚白发来坐标", "hook": "聊聊十二年前的事"},
        ])
        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET ending_hook=? WHERE project_id=? AND chapter_number=?",
            ("周砚白发来坐标，聊聊十二年前的事", "test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, TailRepairLLM())
        state = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "llm_mode": "real",
        }
        output = AuthorOutput(
            title="第1章 车站",
            content=(
                "林默进入车站，定位住户，触发隔离。"
                "他救出住户后，灵体停止追击，许知夏追问选择。"
                "任务结算界面三段式展示，失败名单滚动出现，但正文停在屏幕闪烁处。"
            ),
            word_count=0,
            implemented_events=["事件1"],
            used_plot_refs=["P001"],
        )
        issues = agent._scene_beat_coverage_issues(state, output.content)
        assert issues

        repaired = agent._try_repair_scene_beat_coverage(state, output, issues, "fallback context")

        assert repaired is not None
        assert "正文停在屏幕闪烁处" in repaired.content
        assert "白塔私信在屏幕边缘弹出" in repaired.content
        assert agent.llm.text_calls == 1
        assert agent._scene_beat_coverage_issues(state, repaired.content) == []

    def test_author_scene_beat_repair_does_not_fake_pass_when_llm_misses_hook(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.models.schemas import AuthorOutput

        class BadTailLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.text_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise AssertionError("scene beat repair should use plain text")

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ) -> str:
                self.text_calls += 1
                return "林默抬起头，风从站台尽头吹来，但这一段仍然没有写到指定钩子。"

        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "进入车站", "turn": "发现异常", "hook": "下探站台"},
            {"sequence": 2, "scene_goal": "定位住户", "turn": "数据被篡改", "hook": "系统建议忽略"},
            {"sequence": 3, "scene_goal": "任务结算界面三段式展示", "turn": "失败名单滚动出现", "hook": "周砚白名字浮现"},
            {"sequence": 4, "scene_goal": "白塔私信出现", "turn": "周砚白发来坐标", "hook": "聊聊十二年前的事"},
        ])
        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET ending_hook=? WHERE project_id=? AND chapter_number=?",
            ("周砚白发来坐标，聊聊十二年前的事", "test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, BadTailLLM())
        state = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "llm_mode": "real",
        }
        output = AuthorOutput(
            title="第1章 车站",
            content="林默进入车站，定位住户，触发隔离。正文停在屏幕闪烁处。",
            word_count=0,
            implemented_events=["事件1"],
            used_plot_refs=["P001"],
        )
        issues = agent._scene_beat_coverage_issues(state, output.content)
        assert issues

        repaired = agent._try_repair_scene_beat_coverage(state, output, issues, "fallback context")

        assert repaired is None

    def test_author_context_is_capped_but_preserves_head_and_tail(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent, AUTHOR_CONTEXT_CHAR_LIMIT

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        agent._get_title_contract_context = lambda _project_id: "HEAD_TITLE_CONTRACT"
        agent._get_style_bible_context = lambda _project_id, _agent_id: "MIDDLE_STYLE_" + ("设定" * 8000)
        agent._build_death_penalty_repair_context = lambda _state: "TAIL_REPAIR_CONTEXT"

        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })

        assert len(context) <= AUTHOR_CONTEXT_CHAR_LIMIT
        assert "HEAD_TITLE_CONTRACT" in context
        assert "TAIL_REPAIR_CONTEXT" in context
        assert "【上下文已截断】" in context

    def test_author_plain_text_context_includes_chapter_seam(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        seeded_repo.save_chapter_content(
            "test_proj",
            1,
            "林默站在图书馆外，黑影低声说：'三天后，旧工业区，我很期待。'",
            "第一章 测试",
        )
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {
                "新增事实": ["黑影约林默三天后去旧工业区"],
                "悬念": ["黑影身份与旧工业区约定"],
            },
            "第1章状态卡",
        )
        conn = seeded_repo._conn()
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
            ("test_proj", 2, "第二章 测试", "scripted"),
        )
        conn.execute(
            "INSERT INTO instructions (project_id, chapter_number, objective, key_events, ending_hook, word_target, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active')",
            ("test_proj", 2, "承接旧工业区约定", '["赴约"]', "黑影露面", 2500),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, StubLLMProvider())
        context = agent._build_plain_text_context(
            {
                "project_id": "test_proj",
                "chapter_number": 2,
                "chapter_status": "scripted",
            },
            "",
        )

        assert "【章间衔接硬约束】" in context
        assert "三天后，旧工业区" in context
        assert "黑影身份与旧工业区约定" in context

    def test_base_v6_context_is_capped_for_non_author_agents(self, seeded_repo):
        from novel_factory.agent_runtime.base import BaseAgent

        class BigContextAgent(BaseAgent):
            agent_id = "big_context"
            context_char_limit = 120

            def build_context(self, state):
                return "HEAD-" + ("中间资料" * 80) + "-TAIL"

        agent = BigContextAgent(seeded_repo, StubLLMProvider())
        context = agent._build_v6_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
        })

        assert len(context) <= 120
        assert context.startswith("HEAD-")
        assert context.endswith("-TAIL")
        assert "【上下文已截断】" in context

    def test_author_writes_content(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        # v5.3.0: Content must meet word count threshold (85% of 2500 = 2125)
        # Base content is 51 chars, need 43x to get 2193 chars > 2125
        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 44)  # 2244 chars

        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": long_content,
            "word_count": 2244,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        # Add scene beats
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.DRAFTED.value

        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"] is not None
        assert chapter["content"].startswith("第一章 测试\n\n")

    def test_author_rejects_overlong_draft_before_save(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        overlong_content = "这是一段明显超出章节目标的正文。" * 320
        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": overlong_content,
            "word_count": len(overlong_content),
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == "scripted"
        assert result["quality_gate"]["word_count_fail"] is True
        assert "字数超标" in result["quality_gate"]["message"]
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert not chapter.get("content")

    def test_author_compresses_overlong_real_draft_before_save(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        overlong_content = "这是一段明显超出章节目标的正文。" * 320
        compressed_content = "压缩后的正文保留关键事件、伏笔和章末钩子。" * 130

        class CompressingAuthorLLM(StubLLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                if self._call_count == 0:
                    self._call_count += 1
                    return {
                        "title": "第一章 测试",
                        "content": overlong_content,
                        "word_count": len(overlong_content),
                        "implemented_events": ["事件1"],
                        "used_plot_refs": ["P001"],
                    }
                self._call_count += 1
                return {
                    "title": "第一章 测试",
                    "content": compressed_content,
                    "word_count": len(compressed_content),
                    "implemented_events": ["事件1"],
                    "used_plot_refs": ["P001"],
                }

        agent = AuthorAgent(seeded_repo, CompressingAuthorLLM())
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert "压缩后的正文" in chapter["content"]
        assert "明显超出章节目标" not in chapter["content"]

    def test_author_overlong_real_draft_uses_quality_gate_when_compression_fails(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        overlong_content = "这是一段明显超出章节目标的正文。" * 320
        still_overlong_content = "压缩后仍然明显超出章节目标的正文。" * 320

        class FailingCompressionAuthorLLM(StubLLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                if self._call_count == 0:
                    self._call_count += 1
                    return {
                        "title": "第一章 测试",
                        "content": overlong_content,
                        "word_count": len(overlong_content),
                        "implemented_events": ["事件1"],
                        "used_plot_refs": ["P001"],
                    }
                self._call_count += 1
                return {
                    "title": "第一章 测试",
                    "content": still_overlong_content,
                    "word_count": len(still_overlong_content),
                    "implemented_events": ["事件1"],
                    "used_plot_refs": ["P001"],
                }

        agent = AuthorAgent(seeded_repo, FailingCompressionAuthorLLM())
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result["chapter_status"] == "scripted"
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["revision_target"] == "author"
        assert "字数超标" in result["quality_gate"]["message"]
        assert result["quality_gate"].get("self_check_fail") is not True
        assert "repair_fn returned None" not in result["error"]

    def test_author_long_target_uses_quality_gate_instead_of_fixed_8000_cap(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET word_target=? WHERE project_id=? AND chapter_number=?",
            (12500, "test_proj", 1),
        )
        conn.commit()
        conn.close()

        below_target_content = "长" * 10560
        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": below_target_content,
            "word_count": len(below_target_content),
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == "scripted"
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["word_target"] == 12500
        assert "字数未达标" in result["quality_gate"]["message"]
        assert "8000" not in result.get("error", "")
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert not chapter.get("content")

    def test_author_missing_instruction_word_target_defaults_to_3000(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE projects SET target_words=?, total_chapters_planned=? WHERE project_id=?",
            (50000, 4, "test_proj"),
        )
        conn.execute(
            "UPDATE instructions SET word_target=NULL WHERE project_id=? AND chapter_number=?",
            ("test_proj", 1),
        )
        conn.commit()
        conn.close()

        content = "这是一段按三千字章节目标生成的正文。" * 150
        assert len(content) >= 2550
        assert len(content) < 10625
        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": content,
            "word_count": len(content),
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        assert "12500" not in result.get("error", "")

    def test_author_does_not_use_objective_excerpt_as_chapter_title(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 44
        bad_title = "第1章 引入主角平凡现状，铺垫异"
        stub = StubLLMProvider([{
            "title": bad_title,
            "content": long_content,
            "word_count": 2244,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE chapters SET title=? WHERE project_id=? AND chapter_number=?",
            ("第 1 章", "test_proj", 1),
        )
        conn.execute(
            "UPDATE instructions SET objective=? WHERE project_id=? AND chapter_number=?",
            ("引入主角平凡现状，铺垫异常事件开端，建立都市生活真实感", "test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["title"] != "第1章"
        assert chapter["title"].startswith("第1章 ")
        assert "引入主角" not in chapter["title"]
        assert chapter["content"].startswith(f"{chapter['title']}\n\n")

    def test_author_keeps_real_chapter_title_when_usable(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 44
        stub = StubLLMProvider([{
            "title": "第1章 雨夜玉佩",
            "content": long_content,
            "word_count": 2244,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE chapters SET title=? WHERE project_id=? AND chapter_number=?",
            ("第 1 章", "test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["title"] == "第1章 雨夜玉佩"
        assert chapter["content"].startswith("第1章 雨夜玉佩\n\n")

    def test_author_replaces_placeholder_chapter_title_from_opening(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        body = "林逸盯着手机屏幕。任务完成的界面泛着淡淡蓝光，提交按钮就在那儿一闪一闪。" * 80
        stub = StubLLMProvider([{
            "title": "第 1 章（待命名）",
            "content": f"第 1 章（待命名）\n\n{body}",
            "word_count": len(body),
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE chapters SET title=? WHERE project_id=? AND chapter_number=?",
            ("第 1 章（待命名）", "test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert "待命名" not in chapter["title"]
        assert chapter["title"].startswith("第1章 ")
        assert "待命名" not in chapter["content"].splitlines()[0]
        assert chapter["content"].startswith(f"{chapter['title']}\n\n")

    def test_author_records_event_coverage_checker_skill_run(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.skills.registry import SkillRegistry

        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 44
        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": long_content,
            "word_count": 2244,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [{"sequence": 1, "scene_goal": "开场", "conflict": "冲突"}])
        agent = AuthorAgent(seeded_repo, stub, skill_registry=SkillRegistry())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })
        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        runs = seeded_repo.get_skill_runs("test_proj", skill_id="event-coverage-checker", agent_id="author", chapter_number=1)
        assert runs

    def test_author_recomputes_llm_declared_word_count(self, seeded_repo):
        """LLM word_count guesses should not block otherwise valid content."""
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.validators.chapter_checker import count_words

        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 44

        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": long_content,
            "word_count": 3000,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)

        assert "word_count 不匹配" not in result.get("error", "")
        assert result["chapter_status"] == ChapterStatus.DRAFTED.value

        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"].startswith("第一章 测试\n\n")
        assert chapter["word_count"] == count_words(chapter["content"])

    def test_author_real_mode_expands_short_valid_draft_once(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        short_content = "短正文" * 200  # 600 chars: valid payload, too short for gate.
        long_content = "扩写后的正文内容" * 300  # 2400 chars: passes 2500 * 85%.

        stub = StubLLMProvider([
            {
                "title": "第一章 测试",
                "content": short_content,
                "word_count": 3000,
                "implemented_events": ["事件1"],
                "used_plot_refs": ["P001"],
            },
            {
                "title": "第一章 测试",
                "content": long_content,
                "word_count": 3000,
                "implemented_events": ["事件1"],
                "used_plot_refs": ["P001"],
            },
        ])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        }

        result = agent.run(state)

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        assert stub._call_count == 2
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"] == f"第一章 测试\n\n{long_content}"

    def test_author_revision_rejects_stale_opening_when_seam_was_flagged(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        current_body = (
            "宴会厅主位旁，林辰按住震动的手机，抬眼看向赵宏明。"
            "周老和李博士已经落座，苏婉清立在椅侧，所有宾客都屏住呼吸。"
            "林辰一句话压住场面，直接处理赵家的最后挣扎。"
        ) * 24
        stale_body = (
            "手机屏幕的冷光映着林辰的侧脸。他整理好数据报表，穿过公司走廊离开公司。"
            "初春晚风扑面，他叫了车，定位会馆正门。车上，他闭着眼。"
            "下车步行后，两名黑西装保安拦在门前，说今晚内部包场。"
            "随后故事才重新进入宴会厅。"
        ) * 24

        class StaleOpeningLLM(LLMProvider):
            config = object()

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise AssertionError("live author revision should use plain text primary")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return stale_body

        chapter = seeded_repo.get_chapter("test_proj", 1)
        seeded_repo.save_chapter_content("test_proj", 1, current_body, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, ChapterStatus.REVISION.value)
        seeded_repo.save_review(
            "test_proj",
            chapter["id"],
            passed=False,
            score=50,
            issues=[
                "章首硬性时空断裂：上一章结尾林辰已端坐宴会厅主位，本章首段却倒退回离开公司的出租车中。",
            ],
            suggestions=[
                "彻底删除章首出租车倒叙，直接从宴会厅主位接笔。",
            ],
            revision_target="author",
        )
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "接住宴会厅主位", "conflict": "赵家挣扎"},
        ])

        agent = AuthorAgent(seeded_repo, StaleOpeningLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["revision_continuity_regression"] is True
        assert "旧时空线" in result["quality_gate"]["message"]
        chapter_after = seeded_repo.get_chapter("test_proj", 1)
        assert "宴会厅主位旁" in chapter_after["content"]
        assert "公司走廊离开公司" not in chapter_after["content"]

    def test_author_real_mode_plain_text_fallback_when_json_invalid(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.openai_compatible import OutputValidationError

        class JsonFailTextLLM(LLMProvider):
            def __init__(self):
                self.json_calls = 0
                self.text_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                self.json_calls += 1
                raise OutputValidationError("bad json")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                self.text_calls += 1
                return "兜底正文内容" * 380

        llm = JsonFailTextLLM()
        agent = AuthorAgent(seeded_repo, llm)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        }

        result = agent.run(state)

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        assert llm.json_calls == 1
        assert llm.text_calls == 1
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"].startswith("第一章 测试\n\n兜底正文内容")

    def test_author_real_openai_provider_uses_plain_text_primary(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        class LiveLikeTextLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.json_calls = 0
                self.text_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                self.json_calls += 1
                raise AssertionError("real provider authoring should not use JSON primary")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                self.text_calls += 1
                assert max_tokens >= 2500
                assert max_tokens <= 4096
                return "真实正文内容" * 380

        llm = LiveLikeTextLLM()
        agent = AuthorAgent(seeded_repo, llm)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        }

        result = agent.run(state)

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        assert llm.json_calls == 0
        assert llm.text_calls == 1
        assert any(
            ev["event_type"] == "long_form_generation"
            and ev["payload"].get("mode") == "plain_text_primary"
            for ev in result["_exec_events"]
        )

    def test_author_plain_text_primary_retries_empty_content_once(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        class EmptyThenTextLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.text_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise AssertionError("real provider authoring should not use JSON primary")

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ) -> str:
                self.text_calls += 1
                if self.text_calls == 1:
                    return "   "
                return "林逸盯着手机屏幕。任务完成的界面泛着淡淡蓝光，提交按钮就在那儿一闪一闪。" * 90

        llm = EmptyThenTextLLM()
        agent = AuthorAgent(seeded_repo, llm)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        assert llm.text_calls == 2

    def test_author_segmented_plain_text_merges_overlapping_segment_tail_once(self, seeded_repo, monkeypatch):
        """Later author segments may restate the previous tail; merge must not duplicate it."""
        from novel_factory.agents.author import AuthorAgent

        repeated_tail = "他听见身后钢门震动，外环值守正在逼近。"
        first_segment = f"陆澈压低手电，蓝光照见舱壁上的盐痕。\n{repeated_tail}"
        second_segment = f"{repeated_tail}\n过渡舱深处传来低频轰鸣，神秘人留下的铜牌在地面翻转。"

        class OverlapSegmentLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.text_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise AssertionError("segmented plain text path should not call JSON")

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ) -> str:
                self.text_calls += 1
                return first_segment if self.text_calls == 1 else second_segment

        agent = AuthorAgent(seeded_repo, OverlapSegmentLLM())
        monkeypatch.setattr(agent, "_get_instruction", lambda state: {})
        monkeypatch.setattr(agent, "_get_word_target", lambda state: 300)
        monkeypatch.setattr(agent, "_build_plain_text_context", lambda state, context: "压缩上下文")
        monkeypatch.setattr(agent, "_derive_title", lambda state, instruction, content: "第1章 过渡舱")
        monkeypatch.setattr(agent, "_get_scene_beats", lambda state: [
            {"sequence": i, "scene_goal": f"目标{i}", "conflict": "冲突", "turn": "转折", "hook": "钩子"}
            for i in range(1, 7)
        ])

        output = agent._try_segmented_plain_text_draft(
            {
                "project_id": "test_proj",
                "chapter_number": 1,
                "chapter_status": "scripted",
                "retry_count": 0,
                "max_retries": 3,
                "requires_human": False,
                "error": None,
                "llm_mode": "real",
            },
            "创作",
            "完整上下文",
        )

        assert output.content.count(repeated_tail) == 1
        assert "过渡舱深处传来低频轰鸣" in output.content

    def test_author_segmented_plain_text_trims_near_duplicate_boundary_paragraph(self):
        """Boundary merge also removes lightly revised duplicate paragraphs."""
        from novel_factory.agents.author import AuthorAgent

        previous = "陆澈压低手电，蓝光照见舱壁上的盐痕。\n他听见身后钢门震动，外环值守正在逼近。"
        current = "他听见身后钢门震动，外环值守已在逼近。\n过渡舱深处传来低频轰鸣。"

        merged = AuthorAgent._merge_segment_outputs([previous, current])

        assert "过渡舱深处传来低频轰鸣" in merged
        assert merged.count("他听见身后钢门震动") == 1


class TestPolisherAgent:
    def test_polisher_polishes_content(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        # v5.3.0: Content must meet word count threshold (85% of 2500 = 2125)
        # Base content is 51 chars, need 44x to get 2244 chars > 2125
        base_content = "这是一段测试正文内容，用于验证 Polisher Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 44)  # 2244 chars

        # Setup: chapter with content in 'drafted' status
        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        stub = StubLLMProvider([{
            "content": long_content + "润色后。",
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])

        agent = PolisherAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.POLISHED.value
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"].startswith("第一章 测试\n\n")

    def test_polisher_real_mode_uses_plain_text_primary(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        class PlainTextPolisherLLM(LLMProvider):
            config = type("Config", (), {"max_tokens": 4096})()

            def __init__(self):
                self.json_calls = 0
                self.text_calls = 0
                self.last_timeout = None

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                self.json_calls += 1
                raise AssertionError("real provider polishing should not require long JSON output")

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ) -> str:
                self.text_calls += 1
                self.last_timeout = request_timeout_seconds
                return "林逸盯着手机屏幕。任务完成的界面泛着淡淡蓝光，提交按钮就在那儿一闪一闪。" * 80

        base_content = "林逸盯着手机屏幕。任务完成的界面泛着淡淡蓝光，提交按钮就在那儿一闪一闪。" * 80
        seeded_repo.save_chapter_content("test_proj", 1, base_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        llm = PlainTextPolisherLLM()
        agent = PolisherAgent(seeded_repo, llm)

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result["chapter_status"] == ChapterStatus.POLISHED.value
        assert llm.json_calls == 0
        assert llm.text_calls == 1
        assert llm.last_timeout == 300

    def test_polisher_rejects_overlong_output_before_save(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        base_content = "草稿正文。" * 900
        overlong_content = "润色后正文明显过长。" * 900
        seeded_repo.save_chapter_content("test_proj", 1, base_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")
        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET word_target=? WHERE project_id=? AND chapter_number=?",
            (3000, "test_proj", 1),
        )
        conn.commit()
        conn.close()

        stub = StubLLMProvider([{
            "content": overlong_content,
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])

        result = PolisherAgent(seeded_repo, stub).run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == "drafted"
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["revision_target"] == "polisher"
        assert "字数超标" in result["quality_gate"]["message"]
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"].startswith("草稿正文。")
        assert "润色后正文明显过长" not in chapter["content"]

    def test_polisher_compresses_overlong_real_output_before_save(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        base_content = "草稿正文。" * 900
        overlong_content = "润色后正文明显过长。" * 900
        compressed_content = "压缩后的润色正文仍保留关键事件和章末钩子。" * 130
        seeded_repo.save_chapter_content("test_proj", 1, base_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")
        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET word_target=? WHERE project_id=? AND chapter_number=?",
            (3000, "test_proj", 1),
        )
        conn.commit()
        conn.close()

        class CompressingPolisherLLM(StubLLMProvider):
            config = type("Config", (), {"max_tokens": 4096})()

            def invoke_text(self, messages, temperature=None, max_tokens=None, **kwargs) -> str:
                if self._call_count == 0:
                    self._call_count += 1
                    return overlong_content
                self._call_count += 1
                return compressed_content

        result = PolisherAgent(seeded_repo, CompressingPolisherLLM()).run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result["chapter_status"] == ChapterStatus.POLISHED.value
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert "压缩后的润色正文" in chapter["content"]
        assert "润色后正文明显过长" not in chapter["content"]

    def test_polisher_keeps_quality_gate_when_compression_still_overlong(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        base_content = "草稿正文。" * 900
        overlong_content = "润色后正文明显过长。" * 900
        still_overlong_content = "压缩后仍然明显过长。" * 900
        seeded_repo.save_chapter_content("test_proj", 1, base_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")
        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE instructions SET word_target=? WHERE project_id=? AND chapter_number=?",
            (3000, "test_proj", 1),
        )
        conn.commit()
        conn.close()

        class FailingCompressionPolisherLLM(StubLLMProvider):
            config = type("Config", (), {"max_tokens": 4096})()

            def invoke_text(self, messages, temperature=None, max_tokens=None, **kwargs) -> str:
                if self._call_count == 0:
                    self._call_count += 1
                    return overlong_content
                self._call_count += 1
                return still_overlong_content

        result = PolisherAgent(seeded_repo, FailingCompressionPolisherLLM()).run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert result["chapter_status"] == "drafted"
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["revision_target"] == "polisher"
        assert "字数超标" in result["quality_gate"]["message"]
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"].startswith("草稿正文。")
        assert "压缩后仍然明显过长" not in chapter["content"]

    def test_polisher_v6_context_preserves_complete_current_draft_when_aux_context_is_large(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        draft = "DRAFT_BEGIN_UNIQUE_6617\n" + ("林逸确认通讯器仍在闪烁。" * 180) + "\nDRAFT_END_UNIQUE_6617"
        seeded_repo.save_chapter_content("test_proj", 1, draft, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        agent = PolisherAgent(seeded_repo, StubLLMProvider())
        agent._get_title_contract_context = lambda _project_id: "TITLE_CONTEXT_" + ("设定" * 7000)
        agent._get_style_bible_context = lambda _project_id, _agent_id: "STYLE_CONTEXT_" + ("风格" * 7000)
        agent._build_quality_feedback = lambda _state: "QUALITY_CONTEXT_" + ("反馈" * 7000)

        context = agent._build_v6_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
        })

        assert "DRAFT_BEGIN_UNIQUE_6617" in context
        assert "DRAFT_END_UNIQUE_6617" in context
        assert context.index("DRAFT_BEGIN_UNIQUE_6617") < context.index("DRAFT_END_UNIQUE_6617")

    def test_polisher_real_mode_preserves_draft_when_llm_fails(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        class FailingPolisherLLM(LLMProvider):
            config = type("Config", (), {"max_tokens": 4096})()

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise AssertionError("real provider should use plain text first")

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ) -> str:
                raise RuntimeError("LLM 输出不是有效的 JSON 格式")

        draft = "林逸盯着手机屏幕。任务完成的界面泛着淡淡蓝光，提交按钮就在那儿一闪一闪。" * 80
        seeded_repo.save_chapter_content("test_proj", 1, draft, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        agent = PolisherAgent(seeded_repo, FailingPolisherLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert "error" not in result
        assert result["chapter_status"] == ChapterStatus.POLISHED.value
        assert any(ev["event_type"] == "fallback_used" for ev in result["_exec_events"])
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert "林逸盯着手机屏幕" in chapter["content"]

    def test_polisher_ai_trace_warning_does_not_block(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        class HighTraceSkillRegistry:
            skills_config = {"ai-style-detector": {"type": "validator"}}

            def run_skills_for_agent(self, agent, stage, payload, project_overrides=None):
                if agent == "polisher" and stage == "before_save":
                    return [{
                        "skill_id": "ai-style-detector",
                        "result": {"ok": True, "data": {"ai_trace_score": 95}},
                    }]
                return []

            def get_manifest(self, skill_id):
                return None

            def run_skill(self, skill_id, payload, agent=None, stage=None):
                return {"ok": False, "error": "not mounted"}

        draft = "林逸盯着手机屏幕。任务完成的界面泛着淡淡蓝光，提交按钮就在那儿一闪一闪。" * 80
        seeded_repo.save_chapter_content("test_proj", 1, draft, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        stub = StubLLMProvider([{
            "content": draft + "润色后。",
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])
        agent = PolisherAgent(seeded_repo, stub, skill_registry=HighTraceSkillRegistry())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert "error" not in result
        assert result["chapter_status"] == ChapterStatus.POLISHED.value
        assert any(
            ev["event_type"] == "skill_completed" and ev["payload"].get("ai_trace_score") == 95
            for ev in result["_exec_events"]
        )

    def test_polisher_rejects_fact_change(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        # v5.3.0: Content must meet word count threshold
        base_content = "这是一段测试正文内容，用于验证 Polisher Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 35)  # ~2200 words

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        stub = StubLLMProvider([{
            "content": "改变了事实的内容",
            "fact_change_risk": "high",
            "changed_scope": ["plot"],
            "summary": "改变了剧情",
        }])

        agent = PolisherAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert "error" in result
        assert "fact_change_risk" in result["error"]


class TestEditorAgent:
    def test_editor_review_excerpt_preserves_chapter_tail(self):
        from novel_factory.agents.editor import EditorAgent

        content = "开头。" + ("中段内容。" * 1000) + "【任务状态：部分完成】\n【失败名单】\n周砚白。"

        excerpt = EditorAgent._format_review_content_excerpt(content, 1200)

        assert "正文开头节选" in excerpt
        assert "正文章末尾段" in excerpt
        assert "失败名单" in excerpt
        assert "周砚白" in excerpt

    def test_editor_pass(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        # v5.3.0: Content must meet word count threshold (90% of 2500 = 2250)
        # Base content is 51 chars, need 45x to get 2295 chars > 2250
        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 45)  # 2295 chars

        # Setup: chapter with content in 'polished' status
        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"assets": {"credits": 100}},
        }])

        agent = EditorAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value
        assert result["quality_gate"]["pass"] is True

    def test_editor_blocks_explicit_previous_chapter_seam_break(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        previous = "林默合上电脑，窗外的黑影低声说：'三天后，旧工业区，我很期待。'"
        seeded_repo.save_chapter_content("test_proj", 1, previous, "第一章 测试")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {
                "新增事实": ["黑影约林默三天后去旧工业区"],
                "悬念": ["黑影身份与旧工业区约定"],
            },
            "第1章状态卡",
        )

        current = "第二章 测试\n" + (
            "林默走出图书馆的时候，手机忽然震动。龙华集团的人拦住了他，新的危机扑面而来。"
            "他低头看着屏幕，完全没有想起旧约。"
        ) * 40
        conn = seeded_repo._conn()
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test_proj", 2, "第二章 测试", "polished", current, len(current)),
        )
        conn.execute(
            "INSERT INTO instructions (project_id, chapter_number, objective, key_events, ending_hook, word_target, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active')",
            ("test_proj", 2, "承接上一章", '["处理黑影约定"]', "新危机", 2500),
        )
        conn.commit()
        conn.close()

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 23, "poison": 18, "text": 14, "pacing": 14},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"新增事实": ["龙华集团接触林默"]},
        }])
        agent = EditorAgent(seeded_repo, stub)

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["pass"] is False
        assert result["quality_gate"]["revision_target"] == "author"
        assert result["quality_gate"]["chapter_seam_fail"] is True
        review = seeded_repo.get_latest_review("test_proj", 2)
        assert review is not None
        assert review["pass"] == 0
        assert review["revision_target"] == "author"
        assert "章间衔接" in review["issues"]

    def test_editor_accepts_same_venue_seam_with_natural_rewording(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        previous = (
            "苏婉清看向林辰，声音不高：'还有几位老朋友，听说您在这儿，已经到楼下了。'"
            "她侧身示意，赵家今晚在云澜预订的宴厅里，所有人都屏住了呼吸。"
        )
        seeded_repo.save_chapter_content("test_proj", 1, previous, "第一章 测试")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {
                "新增事实": ["赵家今晚在云澜预订的宴厅被苏婉清接管"],
                "悬念": ["几位老朋友已到云澜楼下"],
            },
            "第1章状态卡",
        )

        opening = (
            "林辰推开云澜宴会厅那扇沉重的鎏金双开门时，里面正好一静。"
            "他径直走到正中央那张主位前坐下，苏婉清立在侧后方半步。"
            "赵天宇和柳梦瑶周围的人群像退潮般让开，压低声音议论着楼下刚到的客人。"
        )
        current = "第二章 旧友压场\n" + opening * 35
        conn = seeded_repo._conn()
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test_proj", 2, "第二章 旧友压场", "polished", current, len(current)),
        )
        conn.execute(
            "INSERT INTO instructions (project_id, chapter_number, objective, key_events, ending_hook, word_target, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active')",
            ("test_proj", 2, "揭晓老朋友身份", '["老朋友登场"]', "新的反扑", 2500),
        )
        conn.commit()
        conn.close()

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 23, "poison": 18, "text": 14, "pacing": 14},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"新增事实": ["林辰在云澜宴会厅等老朋友登场"]},
        }])
        agent = EditorAgent(seeded_repo, stub)

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.REVIEWED.value
        assert result["quality_gate"]["pass"] is True
        assert "chapter_seam_fail" not in result["quality_gate"]

    def test_editor_fail_routes_to_revision(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        # v5.3.0: Content must meet word count threshold
        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 36)  # ~2300 words

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": False,
            "score": 65,
            "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
            "issues": ["逻辑漏洞"],
            "suggestions": ["修复逻辑"],
            "revision_target": "author",
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["pass"] is False
        assert result["_revision_review"]["revision_target"] == result["quality_gate"]["revision_target"]
        assert result["_revision_review"]["review_id"] is not None
        assert result["_revision_review"]["issues"]

    def test_editor_corrects_structural_issue_target_to_author(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 45

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": False,
            "score": 81,
            "scores": {"setting": 20, "logic": 20, "poison": 16, "text": 12, "pacing": 13},
            "issues": [
                "[LOW_DIALOGUE_RATIO] 对白占比2.8%严重偏低（目标10%）",
                "冲突强度不足，缺乏面对面的张力场景",
                "人物动机表达不够清晰",
            ],
            "suggestions": ["增加一段有分歧的对话"],
            "revision_target": "polisher",
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub)
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["revision_target"] == "author"
        assert result["_revision_review"]["revision_target"] == "author"

    def test_editor_low_score_llm_pass_is_forced_to_revision(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 45

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 70,
            "scores": {"setting": 16, "logic": 14, "poison": 14, "text": 13, "pacing": 13},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub)
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["pass"] is False
        assert result["quality_gate"]["score"] == 70
        assert result["quality_gate"]["revision_target"] == "polisher"

        review = seeded_repo.get_latest_review("test_proj", 1)
        assert review is not None
        assert review["pass"] == 0
        assert review["revision_target"] == "polisher"

    def test_editor_accepts_null_state_card(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 45

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 88,
            "scores": {"setting": 20, "logic": 18, "poison": 18, "text": 16, "pacing": 16},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": None,
        }])

        agent = EditorAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert "validation error" not in result.get("error", "")
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value
        assert result["quality_gate"]["pass"] is True

    def test_editor_real_mode_timeout_degrades_to_rule_review(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.llm.openai_compatible import LLMTimeoutError

        class TimeoutEditorLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.json_calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                self.json_calls += 1
                assert max_tokens == 700
                raise LLMTimeoutError("timeout")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return ""

        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 45

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        llm = TimeoutEditorLLM()
        agent = EditorAgent(seeded_repo, llm)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        }

        result = agent.run(state)

        # v6.7.9: Fallback can no longer auto-pass (score capped at 70)
        assert result["quality_gate"]["score"] <= 70
        exec_events = result.get("_exec_events", [])
        assert any(ev.get("event_type") == "fallback_used" for ev in exec_events)
        assert llm.json_calls == 1

    def test_editor_real_mode_generic_llm_error_degrades_to_rule_review(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        class BrokenEditorLLM(LLMProvider):
            config = object()

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                assert max_tokens == 700
                raise RuntimeError("LLM 输出不是有效的 JSON 格式")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return ""

        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 45

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        agent = EditorAgent(seeded_repo, BrokenEditorLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        })

        assert "error" not in result
        # v6.7.9: Fallback can no longer auto-pass (score capped at 70)
        assert result["quality_gate"]["score"] <= 70
        exec_events = result.get("_exec_events", [])
        assert any(ev.get("event_type") == "fallback_used" for ev in exec_events)

    def test_editor_word_gate_reports_target_details(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        short_content = "短正文" * 700  # 2100 chars, below editor threshold 2500 * 90%.

        seeded_repo.save_chapter_content("test_proj", 1, short_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 90,
            "scores": {"setting": 20, "logic": 18, "poison": 18, "text": 17, "pacing": 17},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "workflow_run_id": "run-word-gate",
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["pass"] is False
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["actual_word_count"] == 2100
        assert result["quality_gate"]["word_target"] == 2500
        assert result["quality_gate"]["workflow_run_id"] == "run-word-gate"

    def test_editor_word_gate_persists_fail_in_review_record(self, seeded_repo):
        """When LLM says pass but word-count gate fails, the review row must reflect fail."""
        from novel_factory.agents.editor import EditorAgent

        short_content = "短正文" * 700  # 2100 chars, below editor threshold.

        seeded_repo.save_chapter_content("test_proj", 1, short_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 20, "logic": 18, "poison": 18, "text": 17, "pacing": 17},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["pass"] is False
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["revision_target"] == "polisher"

        # Verify the persisted review record matches the gate decision
        review = seeded_repo.get_latest_review("test_proj", 1)
        assert review is not None
        assert review["pass"] == 0  # SQLite stores bool as int
        assert review["revision_target"] == "polisher"
        issues = json.loads(review["issues"])
        assert any("字数" in i or "word" in i.lower() for i in issues)


class TestMemoryCuratorAgent:
    def test_memory_curator_preserves_plot_hole_resolve_operation(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.api.routes.memory_updates import _apply_memory_item
        from novel_factory.skills.registry import SkillRegistry

        plot = seeded_repo.create_plot_hole(
            "test_proj",
            code="PH-001",
            type="悬念",
            title="铜钥匙用途",
            description="铜钥匙能打开哪里仍未知。",
            planted_chapter=1,
            planned_resolve_chapter=2,
            status="planted",
        )
        conn = seeded_repo._conn()
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) "
            "VALUES (?, ?, ?, ?)",
            ("test_proj", 2, "第二章 旧宅", "reviewed"),
        )
        conn.commit()
        conn.close()
        seeded_repo.save_chapter_content(
            "test_proj",
            2,
            "林默终于用铜钥匙打开城南旧宅地下室，确认它正是旧宅机关的钥匙。",
            "第二章 旧宅",
        )
        seeded_repo.update_chapter_status("test_proj", 2, "reviewed")

        agent = MemoryCuratorAgent(
            seeded_repo,
            StubLLMProvider([{
                "patches": [{
                    "target_table": "plot_holes",
                    "operation": "resolve",
                    "target_name": "PH-001",
                    "data": {
                        "description": "铜钥匙已用于打开城南旧宅地下室，钥匙用途伏笔兑现。",
                    },
                    "confidence": 0.9,
                    "evidence_text": "用铜钥匙打开城南旧宅地下室",
                    "rationale": "本章明确兑现铜钥匙用途。",
                }]
            }]),
            skill_registry=SkillRegistry(),
        )

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-resolve",
        })

        assert result["memory_curator_processed"] is True
        assert result["memory_items_count"] == 1
        batch = seeded_repo.list_memory_batches("test_proj")[0]
        item = seeded_repo.list_memory_items(batch["id"])[0]
        assert item["operation"] == "resolve"
        assert item["target_id"] == str(plot["id"])

        apply_result = _apply_memory_item(seeded_repo, "test_proj", item, 2)
        assert apply_result["success"] is True
        resolved_plot = seeded_repo.get_plot_hole("test_proj", plot["id"])
        assert resolved_plot["status"] == "resolved"
        assert resolved_plot["resolved_chapter"] == 2

    def test_memory_curator_falls_back_to_editor_state_card_when_llm_empty(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.skills.registry import SkillRegistry

        seeded_repo.save_chapter_content("test_proj", 1, "林默夺回账册，并发现账册夹层里藏着铜钥匙。", "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {
                "new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"],
                "character_status": {"林默": "已夺回账册，掌握铜钥匙线索"},
                "suspense_hooks": ["铜钥匙能打开城南旧宅地下室"],
            },
            "第1章状态卡",
        )
        agent = MemoryCuratorAgent(
            seeded_repo,
            StubLLMProvider([{"patches": []}]),
            skill_registry=SkillRegistry(),
        )

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-fallback",
        })

        assert result["memory_curator_processed"] is True
        assert result["memory_curator_fallback"] == "chapter_state"
        assert result["memory_items_count"] == 3

        batches = seeded_repo.list_memory_batches("test_proj")
        assert len(batches) == 1
        assert batches[0]["status"] == "pending"
        assert batches[0]["summary"] == "第1章记忆提取 - 状态卡兜底 (3项)"

        items = seeded_repo.list_memory_items(batches[0]["id"])
        assert len(items) == 3
        assert {item["target_table"] for item in items} == {"story_facts"}
        assert {item["confidence"] for item in items} == {0.45}
        assert all("请人工确认后应用" in item["rationale"] for item in items)
        after_payloads = [json.loads(item["after_json"]) for item in items]
        fact_types = {payload["fact_type"] for payload in after_payloads}
        assert fact_types == {"narrative_event", "character_state", "suspense_hook"}
        assert all(payload["source_chapter"] == 1 for payload in after_payloads)

    def test_memory_curator_real_empty_extraction_repairs_before_fallback(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.skills.registry import SkillRegistry

        class EmptyThenPatchLLM(StubLLMProvider):
            def __init__(self):
                super().__init__([
                    {"patches": []},
                    {
                        "patches": [{
                            "target_table": "story_facts",
                            "operation": "create",
                            "target_name": "chapter_1.key",
                            "data": {
                                "fact_key": "chapter_1.key",
                                "fact_type": "narrative_event",
                                "subject": "第1章",
                                "attribute": "关键物",
                                "value": {"text": "铜钥匙出现"},
                            },
                            "confidence": 0.9,
                            "evidence_text": "账册夹层里藏着铜钥匙",
                            "rationale": "本章新增关键物。",
                        }]
                    },
                ])

        seeded_repo.save_chapter_content(
            "test_proj",
            1,
            "林默夺回账册，并发现账册夹层里藏着铜钥匙。" * 80,
            "第一章 测试",
        )
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {"new_facts": ["林默发现铜钥匙"]},
            "第1章状态卡",
        )
        llm = EmptyThenPatchLLM()
        agent = MemoryCuratorAgent(
            seeded_repo,
            llm,
            skill_registry=SkillRegistry(),
        )

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-empty-repair",
            "llm_mode": "real",
        })

        assert llm._call_count == 2
        assert result["extraction_success"] is True
        assert result["fallback_created"] is False
        assert result["memory_items_count"] == 1
        assert "memory_curator_fallback" not in result

        batches = seeded_repo.list_memory_batches("test_proj")
        assert len(batches) == 1
        assert "状态卡兜底" not in batches[0]["summary"]

    def test_memory_curator_fallback_accepts_chinese_state_card_keys(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.skills.registry import SkillRegistry

        seeded_repo.save_chapter_content("test_proj", 1, "林默发现铜钥匙。", "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {
                "新增事实": ["林默发现铜钥匙"],
                "角色状态": {"林默": "掌握铜钥匙线索"},
                "悬念": ["铜钥匙能打开什么"],
            },
            "第1章状态卡",
        )
        agent = MemoryCuratorAgent(
            seeded_repo,
            StubLLMProvider([{"patches": []}]),
            skill_registry=SkillRegistry(),
        )

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-cn-state",
        })

        assert result["memory_curator_fallback"] == "chapter_state"
        assert result["memory_items_count"] == 3
        batches = seeded_repo.list_memory_batches("test_proj")
        assert len(batches) == 1
        items = seeded_repo.list_memory_items(batches[0]["id"])
        fact_types = {json.loads(item["after_json"])["fact_type"] for item in items}
        assert fact_types == {"narrative_event", "character_state", "suspense_hook"}

    def test_memory_curator_json_parse_error_repairs_before_fallback(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.llm.openai_compatible import OutputValidationError
        from novel_factory.skills.registry import SkillRegistry

        class BrokenThenPatchLLM(LLMProvider):
            config = object()

            def __init__(self):
                self.calls = 0

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                self.calls += 1
                if self.calls == 1:
                    raise OutputValidationError("bad memory json")
                return {
                    "patches": [{
                        "target_table": "story_facts",
                        "operation": "create",
                        "target_name": "chapter_1.fixed",
                        "data": {"fact_key": "chapter_1.fixed", "fact_type": "narrative_event"},
                        "confidence": 0.9,
                        "evidence_text": "铜钥匙出现",
                        "rationale": "修复后提取成功。",
                    }]
                }

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return ""

        seeded_repo.save_chapter_content("test_proj", 1, "林默发现铜钥匙。" * 80, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {"新增事实": ["林默发现铜钥匙"]},
            "第1章状态卡",
        )
        llm = BrokenThenPatchLLM()
        agent = MemoryCuratorAgent(
            seeded_repo,
            llm,
            skill_registry=SkillRegistry(),
        )

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-json-repair",
            "llm_mode": "real",
        })

        assert llm.calls == 2
        assert result["extraction_success"] is True
        assert result["fallback_created"] is False
        assert result["memory_items_count"] == 1
        assert "memory_curator_fallback" not in result

    def test_memory_curator_json_failure_falls_back_to_editor_state_card(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.llm.openai_compatible import OutputValidationError
        from novel_factory.skills.registry import SkillRegistry

        class BrokenJsonMemoryLLM(LLMProvider):
            config = object()

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                assert max_tokens is None
                raise OutputValidationError("bad memory json")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return ""

        seeded_repo.save_chapter_content("test_proj", 1, "林默夺回账册，并发现账册夹层里藏着铜钥匙。", "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {
                "new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"],
                "character_status": {"林默": "已夺回账册，掌握铜钥匙线索"},
                "suspense_hooks": ["铜钥匙能打开城南旧宅地下室"],
            },
            "第1章状态卡",
        )
        agent = MemoryCuratorAgent(
            seeded_repo,
            BrokenJsonMemoryLLM(),
            skill_registry=SkillRegistry(),
        )

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-json-fallback",
            "llm_mode": "real",
        })

        assert result["memory_curator_processed"] is True
        assert result["memory_curator_fallback"] == "chapter_state_after_llm_extraction_failure"
        assert result["memory_items_count"] == 3
        assert result["memory_curator_warning"] == "bad memory json"
        assert result.get("memory_curator_degraded") is None

        batches = seeded_repo.list_memory_batches("test_proj")
        assert len(batches) == 1
        assert batches[0]["status"] == "pending"

        items = seeded_repo.list_memory_items(batches[0]["id"])
        assert len(items) == 3
        assert {json.loads(item["after_json"])["source_agent"] for item in items} == {"memory_curator"}

    def test_memory_curator_records_memory_patch_validator_skill_run(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.skills.registry import SkillRegistry

        seeded_repo.save_chapter_content("test_proj", 1, "林默夺回账册。", "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        stub = StubLLMProvider([{
            "patches": [{
                "target_table": "story_facts",
                "operation": "create",
                "target_name": "linmo.asset.ledger",
                "data": {"fact_key": "linmo.asset.ledger", "fact_type": "asset", "subject": "林默", "attribute": "账册", "value": {"state": "recovered"}},
                "confidence": 0.9,
                "evidence_text": "林默夺回账册",
                "rationale": "本章明确夺回账册",
            }]
        }])
        agent = MemoryCuratorAgent(seeded_repo, stub, skill_registry=SkillRegistry())

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-skill",
        })

        assert result["memory_curator_processed"] is True
        runs = seeded_repo.get_skill_runs("test_proj", skill_id="memory-patch-validator", agent_id="memory_curator", chapter_number=1)
        assert runs

    def test_memory_curator_timeout_degrades_to_noop(self, seeded_repo):
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.llm.openai_compatible import LLMTimeoutError

        class TimeoutMemoryLLM(LLMProvider):
            config = object()

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                assert max_tokens is None
                raise LLMTimeoutError("timeout")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return ""

        seeded_repo.save_chapter_content("test_proj", 1, "测试正文" * 100, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        agent = MemoryCuratorAgent(seeded_repo, TimeoutMemoryLLM())

        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-memory-timeout",
            "llm_mode": "real",
        })

        assert result["memory_curator_processed"] is True
        assert result["memory_curator_degraded"] is True
        assert "error" not in result

    def test_memory_curator_timeout_with_chapter_state_creates_fallback(self, seeded_repo):
        """When LLM times out but chapter_state exists, create fallback batch with low confidence."""
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.llm.openai_compatible import LLMTimeoutError

        class TimeoutMemoryLLM(LLMProvider):
            config = object()

            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                raise LLMTimeoutError("timeout")

            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return ""

        seeded_repo.save_chapter_content("test_proj", 1, "林默夺回账册，并发现账册夹层里藏着铜钥匙。", "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {
                "new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"],
                "character_status": {"林默": "已夺回账册"},
            },
            "第1章状态卡",
        )

        agent = MemoryCuratorAgent(seeded_repo, TimeoutMemoryLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-timeout-fallback",
            "llm_mode": "real",
        })

        # Should create fallback batch, not degraded no-op
        assert result["memory_curator_processed"] is True
        assert result.get("memory_curator_degraded") is None
        assert result["memory_curator_fallback"] == "chapter_state_after_llm_extraction_failure"
        assert result["extraction_success"] is False
        assert result["fallback_created"] is True
        assert result["memory_items_count"] == 2  # new_facts + character_status

        batches = seeded_repo.list_memory_batches("test_proj")
        assert len(batches) == 1
        items = seeded_repo.list_memory_items(batches[0]["id"])
        assert all(item["confidence"] <= 0.45 for item in items)
        assert all("状态卡兜底" in item["rationale"] for item in items)

    def test_memory_curator_returns_extraction_success_flag(self, seeded_repo):
        """Verify extraction_success is True for successful LLM extraction."""
        from novel_factory.agents.memory_curator import MemoryCuratorAgent
        from novel_factory.llm.stub_provider import StubLLM

        class SuccessLLM(StubLLM):
            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None) -> dict:
                return {"patches": [{
                    "target_table": "story_facts",
                    "operation": "create",
                    "target_name": "test.fact",
                    "data": {"fact_key": "test.fact", "fact_type": "narrative_event"},
                    "confidence": 0.9,
                    "evidence_text": "test",
                    "rationale": "test",
                }]}

        seeded_repo.save_chapter_content("test_proj", 1, "测试正文", "第一章")
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")

        agent = MemoryCuratorAgent(seeded_repo, SuccessLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "reviewed",
            "workflow_run_id": "run-success",
            "llm_mode": "real",
        })

        assert result["extraction_success"] is True
        assert result["fallback_created"] is False
        assert "memory_curator_fallback" not in result
