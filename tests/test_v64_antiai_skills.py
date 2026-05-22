"""v6.4.3: Anti-AI quality skills tests.

Tests ShowDontTellValidator, InfoDumpDetector, SceneTextureChecker,
DialogueNaturalnessChecker, and their integration into QualityHub + Polisher.
"""

from __future__ import annotations

import os
import tempfile

import pytest


# -- Sample texts --

SAMPLE_STRAIGHT_EMOTION = (
    "李明感到一阵愤怒涌上心头。他看着眼前的对手，暗自思忖：这次一定要赢。\n"
    "张华觉得有些不安。他明白，这次的任务非常危险。\n"
    "王芳意识到，这场战斗将决定一切。她理解，自己已经没有退路。\n"
    "李明察觉到了空气中的异样。\n"
    "三人站在十字路口。\n"
)

SAMPLE_GOOD_SHOW = (
    "李明攥紧拳头，指节发白。\n"
    "眼前的对手正冷笑着逼近。李明没有后退，反手一记肘击撞在对手肋下。\n"
    "张华靠在石柱旁，手里把玩着一枚铜币。铜币在他指间翻转，发出细碎的摩擦声。\n"
    "王芳站在阴影里，手指无意识地摩挲着腰间的短刀。刀柄已经被汗水浸得湿滑。\n"
)

SAMPLE_INFO_DUMP = (
    "这个世界是一个充满魔法的世界，在这个世界里，人们可以通过修炼获得强大的力量。\n"
    "所谓修炼，是指通过吸收天地灵气来增强自身实力的过程。\n"
    "简单来说，修炼就是变强的途径。\n"
    "说白了，不修炼就没有出路。\n"
    "这个世界有七大势力，各自掌控不同的资源。在这个时代，力量就是一切。\n"
)

SAMPLE_LOW_SCENE = (
    "会议开始了。大家坐在会议室里，讨论着下一步的计划。\n"
    "张明首先发言，介绍了当前的情况。然后李华补充了一些细节。\n"
    "接着，王强提出了一个新的方案。最后，大家达成了一致意见。\n"
    "会议结束了。所有人都离开了会议室。\n"
)

SAMPLE_GOOD_SCENE = (
    "清晨的阳光透过窗帘，在地板上投下斑驳的光影。\n"
    "空气中弥漫着一股淡淡的茶香，混合着雨后的湿气。\n"
    "他推开窗户，冷风扑面而来，带着远处寺庙的钟声。\n"
    "街道上的积水倒映着灰色的天空，行人撑着伞匆匆走过。\n"
)

SAMPLE_LOW_DIALOGUE = (
    "李明推开房门，走进屋内。房间里很暗，他摸索着找到了开关。\n"
    "灯光亮起，他看到了桌上的文件。他拿起文件，仔细阅读起来。\n"
    "文件内容让他大吃一惊。他放下文件，在房间里来回踱步。\n"
    "最后，他做出了决定。\n"
)

SAMPLE_GOOD_DIALOGUE = (
    "\u201c你来了。\u201d身后传来一个低沉的声音。\n"
    "\u201c你是谁？\u201d李明警觉地问道。\n"
    "\u201c我是谁不重要，\u201d黑衣男子缓缓走近，\u201c重要的是，你正在寻找的东西，也在寻找你。\u201d\n"
    "\u201c别紧张嘛，\u201d黑衣男子停下脚步，\u201c我是来帮你的。\u201d\n"
    "\u201c什么选择？\u201d李明紧盯着对方。\n"
)


# -- Skill unit tests --

class TestShowDontTellValidator:
    """ShowDontTellValidator deterministic detection."""

    def test_detects_straight_emotion(self):
        from novel_factory.skills.show_dont_tell_validator import ShowDontTellValidator
        skill = ShowDontTellValidator()
        result = skill.run({"text": SAMPLE_STRAIGHT_EMOTION})
        assert result["ok"]
        data = result["data"]
        assert data["straight_emotion_count"] > 0
        assert data["score"] < 100
        assert any(f["code"] == "STRAIGHT_EMOTION" for f in data["findings"])

    def test_excludes_dialogue(self):
        from novel_factory.skills.show_dont_tell_validator import ShowDontTellValidator
        skill = ShowDontTellValidator()
        text = (
            "他站在门口。\n"
            '\u201c我感到非常愤怒，\u201d他说，\u201c你为什么要这么做？\u201d\n'
            "\u201c我觉得你应该冷静一下。\u201d对方回答。\n"
            "窗外的风声呼啸。\n"
        )
        result = skill.run({"text": text})
        assert result["ok"]
        data = result["data"]
        # Dialogue "感到/觉得" should NOT be counted
        assert data["straight_emotion_count"] == 0
        assert data["score"] == 100

    def test_good_text_high_score(self):
        from novel_factory.skills.show_dont_tell_validator import ShowDontTellValidator
        skill = ShowDontTellValidator()
        result = skill.run({"text": SAMPLE_GOOD_SHOW})
        assert result["ok"]
        assert result["data"]["score"] >= 80

    def test_neutral_know_not_flagged(self):
        """Objective action word '知道' used for factual knowledge should not trigger."""
        from novel_factory.skills.show_dont_tell_validator import ShowDontTellValidator
        skill = ShowDontTellValidator()
        text = "他知道这条路通向城堡。她知道这个秘密。"
        result = skill.run({"text": text})
        assert result["ok"]
        assert result["data"]["straight_emotion_count"] == 0
        assert result["data"]["score"] == 100

    def test_evidence_not_huge(self):
        from novel_factory.skills.show_dont_tell_validator import ShowDontTellValidator
        skill = ShowDontTellValidator()
        result = skill.run({"text": SAMPLE_STRAIGHT_EMOTION * 10})
        assert result["ok"]
        for f in result["data"]["findings"]:
            evidence = str(f.get("evidence", ""))
            assert len(evidence) < 2000


class TestInfoDumpDetector:
    """InfoDumpDetector deterministic detection."""

    def test_detects_lore_dump(self):
        from novel_factory.skills.info_dump_detector import InfoDumpDetector
        skill = InfoDumpDetector()
        result = skill.run({"text": SAMPLE_INFO_DUMP})
        assert result["ok"]
        data = result["data"]
        assert data["lore_count"] > 0
        assert data["score"] < 100
        assert any(f["code"] == "LORE_DUMP" for f in data["findings"])

    def test_good_text_high_score(self):
        from novel_factory.skills.info_dump_detector import InfoDumpDetector
        skill = InfoDumpDetector()
        result = skill.run({"text": SAMPLE_GOOD_SHOW})
        assert result["ok"]
        assert result["data"]["score"] >= 80

    def test_evidence_not_huge(self):
        from novel_factory.skills.info_dump_detector import InfoDumpDetector
        skill = InfoDumpDetector()
        result = skill.run({"text": SAMPLE_INFO_DUMP})
        for f in result["data"]["findings"]:
            evidence = str(f.get("evidence", ""))
            assert len(evidence) < 1000


class TestSceneTextureChecker:
    """SceneTextureChecker deterministic detection."""

    def test_low_scene_texture(self):
        from novel_factory.skills.scene_texture_checker import SceneTextureChecker
        skill = SceneTextureChecker()
        result = skill.run({"text": SAMPLE_LOW_SCENE})
        assert result["ok"]
        data = result["data"]
        assert data["sensory_per_1000"] < 3
        assert data["score"] < 80
        assert any(f["code"] == "LOW_SENSORY_DETAIL" for f in data["findings"])

    def test_good_scene_texture(self):
        from novel_factory.skills.scene_texture_checker import SceneTextureChecker
        skill = SceneTextureChecker()
        result = skill.run({"text": SAMPLE_GOOD_SCENE})
        assert result["ok"]
        assert result["data"]["sensory_per_1000"] >= 3
        assert result["data"]["score"] >= 60

    def test_no_duplicate_sensory_count(self):
        """Overlapping sensory words (e.g. '阳光' containing '光') must not be double-counted."""
        from novel_factory.skills.scene_texture_checker import SceneTextureChecker
        skill = SceneTextureChecker()
        # Pad with neutral text so per_1000 stays low; only one line has sensory words
        padding = "他沿着走廊向前走去，脚步在空旷的空间里回荡。\n" * 100
        sensory_line = "阳光透过窗户，光线洒在地上，灯光照亮了房间。\n"
        text = padding + sensory_line + padding
        result = skill.run({"text": text})
        assert result["ok"]
        data = result["data"]
        # Exactly 3 distinct sensory matches; without dedup '光' would count 6+
        assert data["sensory_per_1000"] <= 10


class TestDialogueNaturalnessChecker:
    """DialogueNaturalnessChecker deterministic detection."""

    def test_low_dialogue(self):
        from novel_factory.skills.dialogue_naturalness_checker import DialogueNaturalnessChecker
        skill = DialogueNaturalnessChecker()
        result = skill.run({"text": SAMPLE_LOW_DIALOGUE})
        assert result["ok"]
        data = result["data"]
        assert data["dialogue_ratio"] < 0.05
        assert data["score"] < 80
        assert any(f["code"] == "LOW_DIALOGUE_RATIO" for f in data["findings"])

    def test_good_dialogue(self):
        from novel_factory.skills.dialogue_naturalness_checker import DialogueNaturalnessChecker
        skill = DialogueNaturalnessChecker()
        result = skill.run({"text": SAMPLE_GOOD_DIALOGUE})
        assert result["ok"]
        data = result["data"]
        assert data["dialogue_ratio"] >= 0.05
        assert data["colloquial_ratio"] >= 0.1

    def test_nested_quotes_does_not_crash(self):
        """Malformed nested curly quotes should not crash the checker."""
        from novel_factory.skills.dialogue_naturalness_checker import DialogueNaturalnessChecker
        skill = DialogueNaturalnessChecker()
        text = (
            '\u201c你来了。\u201d身后传来一个低沉的声音。\n'
            '\u201c你\u201c说\u201d什么？\u201d李明警觉地问道。\n'
        )
        result = skill.run({"text": text})
        assert result["ok"]
        # Should still detect at least one dialogue segment
        assert result["data"]["dialogue_count"] >= 1


# -- Integration tests --

class TestQualityHubIntegration:
    """QualityHub.diagnose uses v6.4.3 skills."""

    def test_diagnose_dimensions_from_skills(self):
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())
            result = hub.diagnose(SAMPLE_STRAIGHT_EMOTION + SAMPLE_INFO_DUMP)

            dims = result["dimensions"]
            # v6.4.3 dimensions must be present
            assert "show_dont_tell" in dims
            assert "info_dump" in dims
            assert "scene_immersion" in dims
            assert "dialogue_naturalness" in dims

            # AI-heavy text should score low on these dimensions
            assert dims["show_dont_tell"] < 90
            assert dims["info_dump"] < 90

            # Findings should contain skill-derived codes
            codes = [f["code"] for f in result["findings"]]
            assert any("SHOW_DONT_TELL" in c for c in codes)
            assert any("INFO_DUMP" in c for c in codes)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_diagnose_good_text_high_scores(self):
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())
            result = hub.diagnose(SAMPLE_GOOD_SCENE + SAMPLE_GOOD_DIALOGUE)

            dims = result["dimensions"]
            assert dims["show_dont_tell"] >= 80
            assert dims["info_dump"] >= 80
            assert dims["scene_immersion"] >= 50
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_diagnose_no_regression(self):
        """diagnose() must not break existing API shape."""
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())
            result = hub.diagnose(SAMPLE_STRAIGHT_EMOTION)
            assert "overall_score" in result
            assert "dimensions" in result
            assert "findings" in result
            assert "metrics" in result
            for f in result["findings"]:
                assert "severity" in f
                assert "code" in f
                assert "message" in f
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestPolisherWarningsIntegration:
    """Polisher warnings reuse v6.4.3 skill results."""

    def _run_polisher(self, repo, content: str):
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider
        from novel_factory.skills.registry import SkillRegistry

        while len(content) < 2200:
            content = content + "\n" + content

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "content": content,
                    "fact_change_risk": "none",
                    "changed_scope": ["sentence"],
                    "summary": "test",
                }
            def invoke_text(self, messages, **kw):
                return ""

        agent = PolisherAgent(repo, StubLLM(), skill_registry=SkillRegistry())
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
        return agent.run(state)

    def test_warnings_from_skills(self):
        from novel_factory.models.state import ChapterStatus
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        repo.create_project("test_proj", "Test", "fantasy", "test", 10000, 10)
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
        try:
            result = self._run_polisher(repo, SAMPLE_STRAIGHT_EMOTION * 5)
            assert result.get("chapter_status") == ChapterStatus.POLISHED.value
            events = result.get("_exec_events", [])
            warn_events = [e for e in events if e.get("event_type") == "polisher_warnings"]
            assert len(warn_events) > 0
            warnings = warn_events[0].get("payload", {}).get("warnings", [])
            assert any("excessive_explanation" in w for w in warnings)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_warnings_do_not_block(self):
        from novel_factory.models.state import ChapterStatus
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        repo.create_project("test_proj", "Test", "fantasy", "test", 10000, 10)
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
        try:
            result = self._run_polisher(repo, SAMPLE_STRAIGHT_EMOTION * 5)
            assert result.get("chapter_status") == ChapterStatus.POLISHED.value
            assert "error" not in result or result.get("error") is None
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
