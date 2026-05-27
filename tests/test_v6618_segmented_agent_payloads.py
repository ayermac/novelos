"""Tests for v6.6.18 Segmented Agent Payloads."""

from typing import Any

import pytest

from novel_factory.agent_runtime.segmented_generation import (
    chunk_items,
    chunk_text_by_paragraphs,
)


# ---------------------------------------------------------------------------
# Shared Segmentation Helper
# ---------------------------------------------------------------------------


def test_chunk_items_preserves_order_and_size():
    chunks = list(chunk_items([1, 2, 3, 4, 5], size=2))
    assert chunks == [[1, 2], [3, 4], [5]]


def test_chunk_items_empty():
    assert list(chunk_items([], size=2)) == []


def test_chunk_items_size_zero_falls_back_to_one():
    chunks = list(chunk_items([1, 2, 3], size=0))
    assert chunks == [[1], [2], [3]]


def test_chunk_text_by_paragraphs_keeps_paragraphs_under_soft_limit():
    text = "甲" * 10 + "\n\n" + "乙" * 10 + "\n\n" + "丙" * 10
    chunks = list(chunk_text_by_paragraphs(text, soft_limit=25))
    assert chunks == ["甲" * 10 + "\n\n" + "乙" * 10, "丙" * 10]


def test_chunk_text_by_paragraphs_single_paragraph():
    text = "甲" * 10
    chunks = list(chunk_text_by_paragraphs(text, soft_limit=5))
    assert chunks == ["甲" * 10]


def test_chunk_text_by_paragraphs_empty():
    assert list(chunk_text_by_paragraphs("", soft_limit=10)) == []


def test_chunk_text_by_paragraphs_oversized_paragraph_not_split():
    text = "甲" * 100
    chunks = list(chunk_text_by_paragraphs(text, soft_limit=10))
    assert chunks == ["甲" * 100]


# ---------------------------------------------------------------------------
# Genesis Quality Gate Semantic Alignment (v6.6.18)
# ---------------------------------------------------------------------------


def _ocean_city_draft() -> dict[str, Any]:
    """A realistic Genesis output shaped like the v6.6.17 ocean-city sample."""
    return {
        "project_updates": {
            "description": "《海渊城》是一部近未来悬疑科幻小说。记者林潮追查父亲旧案时发现潮汐能源系统隐藏着城市级记忆改写实验。",
        },
        "world_settings": [
            {"title": "海渊城地理", "category": "地理", "content": "一座建立在海底大陆架上的近未来城邦，依赖潮汐能发电。"},
            {"title": "潮汐能源系统", "category": "科技", "content": "城市核心能源，同时被用于备份和改写居民记忆。"},
        ],
        "characters": [
            {
                "name": "林潮",
                "role": "protagonist",
                "description": "旧港报记者，性格执拗。",
                "goal": "查清父亲死亡真相",
                "conflict": "她发现自己可能也是潮汐系统的备份对象",
                "relationship_with_protagonist": "自身即主角",
            },
            {
                "name": "沈澜",
                "role": "antagonist",
                "description": "潮汐管理局技术负责人。",
                "goal": "阻止真相外泄",
                "secret": "她参与过旧案的善后处理",
                "relationship_with_protagonist": "压制调查，表面配合，真实摇摆",
            },
            {
                "name": "许闻",
                "role": "supporting",
                "description": "旧港档案员。",
                "goal": "帮助林潮读取被删记录",
                "interest_relation": "关键证人与线索提供者",
            },
        ],
        "factions": [
            {
                "name": "潮汐管理局",
                "type": "官方机构",
                "description": "掌握城市水位调度和记忆备份权限。",
                "resources": "城市泵站、档案系统、验证协议、安防网络",
                "current_action": "封锁旧案并监控林潮",
                "relationship_with_protagonist": "压制调查",
            },
            {
                "name": "旧港互助会",
                "type": "民间组织",
                "description": "由异常幸存者和旧城区居民组成。",
                "means": "民间目击记录、地下避难点、未清洗记忆者",
                "stage_action": "在保护自身安全的前提下向林潮提供碎片证词",
                "relationship_with_protagonist": "可争取对象",
            },
        ],
        "outlines": [
            {
                "chapters_range": "1-3",
                "title": "旧案重启",
                "content": "林潮调查父亲旧案并被管理局阻止。阶段冲突：记者与官方机构的对抗。转折：潮位记录证明父亲死亡当天系统被人工改写。阶段结果：林潮取得第一份证据。",
                "level": "arc",
                "sequence": 1,
            },
        ],
        "plot_holes": [
            {
                "code": "PH-001",
                "type": "主线谜团",
                "title": "父亲为何留下潮位表",
                "description": "触发场景：林潮发现潮位表。读者表象：普通遗物。真相方向：潮位表是记忆备份索引。预计兑现：第3章。",
                "planted_chapter": 1,
                "planned_resolve_chapter": 3,
                "status": "planted",
            },
        ],
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "林潮进入旧港泵站寻找父亲留下的潮位表",
                "key_events": "林潮收到匿名潮位短信；他潜入泵站发现监控被删；沈澜派人封锁出口",
                "emotion_tone": "悬疑紧张",
                "ending_hook": "潮位表上出现林潮自己的死亡时间",
                "continuity_seed": "下一章追查死亡时间来源",
            },
        ],
    }


def test_genesis_quality_gate_no_false_positives_for_structured_fields():
    """High-quality natural-language genesis with structured fields must not be falsely flagged."""
    from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft

    draft = _ocean_city_draft()
    report = evaluate_genesis_draft(
        draft,
        title="海渊城",
        genre="悬疑科幻",
        premise="记者调查父亲旧案时发现潮汐系统隐藏着城市级实验",
        target_chapters=3,
    )

    codes = {i.code for i in report.issues}
    assert "OUTLINE_NOT_REFLECTING_PREMISE" not in codes, f"False positive: {codes}"
    assert "SHALLOW_CHARACTER_MOTIVATION" not in codes, f"False positive: {codes}"
    assert "SHALLOW_FACTION_ACTION" not in codes, f"False positive: {codes}"


def test_genesis_quality_gate_reads_natural_language_character_dimensions():
    """High-quality character prose should satisfy goal/conflict/interest checks."""
    from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft

    draft = {
        "project_updates": {
            "description": "《潮汐档案》以2107年海洋城邦的潮汐能源系统为核心，将系列失联案、城市记忆改写与个体身份危机交织成一部冷峻克制的近未来科幻悬疑。",
        },
        "world_settings": [
            {
                "title": "2107年的海渊城",
                "category": "时代背景",
                "content": "海渊城依靠潮汐能源实现供电、供氧、温控、交通调度和信息同步。",
            },
            {
                "title": "潮汐能源系统",
                "category": "核心科技",
                "content": "系统产生的低频潮汐噪声能够影响海马体记忆巩固机制。",
            },
        ],
        "characters": [
            {
                "name": "陆澈",
                "role": "protagonist",
                "description": "海渊城调查员，专门处理失联案与异常档案比对，习惯从潮汐日志、通勤轨迹和监控残片里拼出真相。他追查一连串失联者时，发现自己过去某段关键经历被潮汐系统动过手脚，而他越接近核心，越怀疑自己也曾被改写过。目标是查明失联案背后的系统真相并保住自我记忆完整性。",
            },
            {
                "name": "沈珂",
                "role": "supporting",
                "description": "潮汐档案中心的高级校验员，负责比对能源调度记录与居民神经共振数据，表面上只按规程办事，实际上一直在私下保存被删除的异常条目。她希望找出失联者真正的去向，但她自己也有一段关于家人的记忆空洞，疑似被系统修正过。她与陆澈既是线索互换的盟友，也是彼此都不完全信任的同路人。",
            },
            {
                "name": "唐屿",
                "role": "supporting",
                "description": "海底能源塔的维护技师，出身下沉式居住层，熟悉潮汐噪声的物理传输和设备层绕行路径。他最初只想借调查保护自己被列入失联风险名单的妹妹，后来被迫承认自己曾参与过一次掩盖事故的维修任务，而那次事故可能就是记忆改写的起点之一。对陆澈的帮助是真实的，但他的立场会随着妹妹的下落不断摇摆。",
            },
            {
                "name": "祁闻舟",
                "role": "antagonist",
                "description": "潮汐调度局记忆协调司负责人，公开身份是维护城市稳定的高阶官员，实际掌握潮汐噪声的阈值调控权限，知道系统可以在特定条件下重排居民记忆。他的目标是用有限度的记忆修正维持海渊城秩序，必要时抹除个体真相以避免城市级崩溃。陆澈越逼近失联案核心，越会触碰他刻意封存的旧事故。",
            },
            {
                "name": "纪梓",
                "role": "supporting",
                "description": "曾与陆澈共同处理失联案的调查员，后在一次暴潮事件后突然调岗并从陆澈的社交记录中被整体抹去痕迹。她究竟是主动失联、被系统收编，还是已经成为潮汐改写的样本，都是推动主线的重要悬念。她和陆澈之间残留着一种说不清来源的熟悉感，成为他判断自己记忆是否可靠的关键参照。",
            },
        ],
        "factions": [
            {
                "name": "潮汐调度局",
                "type": "官方机构",
                "description": "掌管海渊城供能、供氧、温控、交通与信息同步，拥有潮汐能源系统的最高调度权限。当前阶段正在以系统维护为名压低失联案曝光度。",
            },
            {
                "name": "失联者互助网",
                "type": "地下组织",
                "description": "成员依靠手写记录、离线存储和低频信号交换情报，当前阶段正在收集失联者最后一次真实活动轨迹。",
            },
        ],
        "outlines": [
            {
                "chapters_range": "1-3",
                "title": "失联者仍在通勤",
                "content": "陆澈接手梁述失联案。阶段冲突集中在陆澈与官方程序之间。转折：梁述最后一次真实出现的时间与一次短暂暴潮重合。阶段结果：陆澈获得梁述留下的离线录音，并在案件记录里看到陌生姓名纪梓。",
            },
        ],
        "plot_holes": [
            {
                "code": "identity-partner",
                "title": "不存在于陆澈记忆中的前搭档",
                "description": "触发场景：陆澈在案件系统的旧权限栏里看到纪梓。读者看到的表象：可能是系统误录或档案串档。真相方向：纪梓曾与陆澈共同调查三年前暴潮事故。预计兑现章节：第8章。",
            },
        ],
        "instructions": [
            {
                "chapter_number": 1,
                "objective": "陆澈接手梁述失联案，确认案件不是普通人口流失，而是与海渊城的潮汐系统有关",
                "key_events": "陆澈核验梁述通勤记录；家属证词与系统记录冲突；他争取原始档案权限",
                "ending_hook": "案件系统出现陌生的共同经办人纪梓",
                "continuity_seed": "下一章继续验证梁述案中的时间异常",
            },
        ],
    }

    report = evaluate_genesis_draft(
        draft,
        title="潮汐档案",
        genre="近未来科幻悬疑",
        premise="海洋城邦潮汐能源系统导致系列失联案、城市记忆改写与个体身份危机。",
        target_chapters=3,
    )

    codes = {i.code for i in report.issues}
    assert "SHALLOW_CHARACTER_MOTIVATION" not in codes, f"False positive: {codes}"


def test_genesis_quality_gate_still_catches_low_quality_template_draft():
    """Low-quality template drafts must still be intercepted."""
    from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft

    draft = {
        "instructions": [
            {"chapter_number": 1, "objective": "第一章", "key_events": "事件"},
        ],
        "outlines": [{"chapters_range": "1", "title": "开篇", "content": "开始。"}],
        "characters": [
            {"name": "主角", "role": "protagonist", "description": "主角。"},
        ],
        "factions": [
            {"name": "敌对势力", "type": "势力", "description": "势力。"},
        ],
        "plot_holes": [{"code": "PH-001", "title": "身世", "description": "身世。"}],
    }
    report = evaluate_genesis_draft(
        draft,
        title="测试",
        genre="都市",
        premise="测试",
        target_chapters=1,
    )
    codes = {i.code for i in report.issues}
    assert "MOST_GENERIC_CHARACTERS" in codes or "GENERIC_CHARACTER_NAME" in codes
    assert "MOST_GENERIC_FACTIONS" in codes or "GENERIC_FACTION_NAME" in codes


# ---------------------------------------------------------------------------
# Author Segmented Drafting
# ---------------------------------------------------------------------------


def test_author_real_mode_generates_scene_beat_segments(monkeypatch, tmp_path):
    """Author with 6 scene beats must trigger at least 2 invoke_text calls in real mode."""
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository
    from novel_factory.agents.author import AuthorAgent

    db_path = str(tmp_path / "author_segment.db")
    init_db(db_path)
    repo = Repository(db_path)

    repo.create_project(
        project_id="seg-test",
        name="Segment Test",
        genre="都市",
        description="测试",
        total_chapters_planned=10,
        target_words=30000,
    )
    repo.save_chapter(
        project_id="seg-test",
        chapter_number=1,
        title="第一章",
        content="",
        word_count=0,
        status="planned",
    )
    repo.create_instruction(
        project_id="seg-test",
        chapter_number=1,
        objective="测试写作",
        key_events="事件1；事件2；事件3",
        emotion_tone="紧张",
    )
    beats = []
    for seq in range(1, 7):
        beats.append(
            {
                "sequence": seq,
                "scene_goal": f"目标{seq}",
                "conflict": f"冲突{seq}",
                "turn": f"转折{seq}",
                "hook": f"钩子{seq}",
            }
        )
    repo.save_scene_beats("seg-test", 1, beats)
    repo.update_chapter_status("seg-test", 1, "scripted")

    calls: list[dict[str, Any]] = []

    class FakeLLM:
        config = {"model": "fake"}

        def invoke_text(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
            calls.append({
                "type": "invoke_text",
                "messages": messages,
                "max_tokens": max_tokens,
                "max_retries": kwargs.get("max_retries"),
            })
            seg = len([c for c in calls if c["type"] == "invoke_text"])
            body = f"【正文分段】这是第{seg}段正文内容。" * 115
            body += " 目标4 冲突4 转折4 钩子4 目标5 冲突5 转折5 钩子5 目标6 冲突6 转折6 钩子6"
            return body

        def invoke_json(self, messages, **kwargs):
            raise RuntimeError("JSON not expected")

    agent = AuthorAgent(repo, FakeLLM(), skill_registry=None)
    state = {
        "project_id": "seg-test",
        "chapter_number": 1,
        "llm_mode": "real",
        "workflow_run_id": "test-run",
        "chapter_status": "scripted",
    }
    result = agent.run(state)

    text_calls = [c for c in calls if c["type"] == "invoke_text"]
    assert len(text_calls) >= 2, f"Expected >=2 text calls, got {len(text_calls)}"
    assert all(c["max_retries"] is None for c in text_calls)
    assert any("【正文分段】" in str(c["messages"]) for c in text_calls)
    assert result.get("chapter_status") == "drafted"


def test_author_segmented_prompts_use_per_segment_length_budget(tmp_path):
    """Segmented author prompts must not repeat the full chapter target per segment."""
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository
    from novel_factory.agents.author import AuthorAgent

    db_path = str(tmp_path / "author_segment_budget.db")
    init_db(db_path)
    repo = Repository(db_path)

    repo.create_project(
        project_id="seg-budget",
        name="Segment Budget Test",
        genre="科幻",
        description="测试",
        total_chapters_planned=10,
        target_words=30000,
    )
    repo.save_chapter(
        project_id="seg-budget",
        chapter_number=1,
        title="第一章",
        content="",
        word_count=0,
        status="planned",
    )
    repo.create_instruction(
        project_id="seg-budget",
        chapter_number=1,
        objective="测试分段预算",
        key_events="事件1；事件2；事件3；事件4；事件5；事件6",
        emotion_tone="紧张",
        word_target=3000,
    )
    repo.save_scene_beats(
        "seg-budget",
        1,
        [
            {
                "sequence": seq,
                "scene_goal": f"目标{seq}",
                "conflict": f"冲突{seq}",
                "turn": f"转折{seq}",
                "hook": f"钩子{seq}",
            }
            for seq in range(1, 7)
        ],
    )
    repo.update_chapter_status("seg-budget", 1, "scripted")

    prompts: list[str] = []

    class BudgetLLM:
        config = {"model": "fake"}

        def invoke_text(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
            prompts.append(messages[-1]["content"])
            seg = len(prompts)
            return (
                f"第{seg}段正文覆盖 目标{seg * 3 - 2} 冲突{seg * 3 - 2} "
                f"转折{seg * 3 - 2} 钩子{seg * 3 - 2} "
                f"目标{seg * 3 - 1} 冲突{seg * 3 - 1} 转折{seg * 3 - 1} 钩子{seg * 3 - 1} "
                f"目标{seg * 3} 冲突{seg * 3} 转折{seg * 3} 钩子{seg * 3} "
                + "正文内容" * 400
            )

        def invoke_json(self, messages, **kwargs):
            raise RuntimeError("JSON not expected")

    result = AuthorAgent(repo, BudgetLLM(), skill_registry=None).run({
        "project_id": "seg-budget",
        "chapter_number": 1,
        "llm_mode": "real",
        "workflow_run_id": "test-run",
        "chapter_status": "scripted",
    })

    assert result.get("chapter_status") == "drafted"
    assert len(prompts) == 2
    assert all("正文至少 1275 字符，建议接近 1500 字符" in prompt for prompt in prompts)
    assert all("正文至少 2550 字符，建议接近 3000 字符" not in prompt for prompt in prompts)


def test_author_revision_uses_single_pass_instead_of_segmenting_full_draft(tmp_path):
    """Revision prompts should not repeat the full saved draft once per segment."""
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository
    from novel_factory.agents.author import AuthorAgent

    db_path = str(tmp_path / "author_revision_single_pass.db")
    init_db(db_path)
    repo = Repository(db_path)

    repo.create_project(
        project_id="revision-single",
        name="Revision Single Pass Test",
        genre="科幻",
        description="测试",
        total_chapters_planned=10,
        target_words=30000,
    )
    existing_body = "当前保留稿。" * 300
    repo.save_chapter(
        project_id="revision-single",
        chapter_number=1,
        title="第一章",
        content=existing_body,
        word_count=len(existing_body),
        status="planned",
    )
    repo.create_instruction(
        project_id="revision-single",
        chapter_number=1,
        objective="测试返修",
        key_events="事件1；事件2；事件3；事件4；事件5；事件6",
        emotion_tone="紧张",
        ending_hook="钩子6",
        word_target=3000,
    )
    repo.save_scene_beats(
        "revision-single",
        1,
        [
            {
                "sequence": seq,
                "scene_goal": f"目标{seq}",
                "conflict": f"冲突{seq}",
                "turn": f"转折{seq}",
                "hook": f"钩子{seq}",
            }
            for seq in range(1, 7)
        ],
    )
    repo.update_chapter_status("revision-single", 1, "revision")

    prompts: list[str] = []

    class RevisionLLM:
        config = {"model": "fake"}

        def invoke_text(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
            prompts.append(messages[-1]["content"])
            return "返修正文。" * 600 + " 目标6 冲突6 转折6 钩子6"

        def invoke_json(self, messages, **kwargs):
            raise RuntimeError("JSON not expected")

    result = AuthorAgent(repo, RevisionLLM(), skill_registry=None).run({
        "project_id": "revision-single",
        "chapter_number": 1,
        "llm_mode": "real",
        "workflow_run_id": "test-run",
        "chapter_status": "revision",
        "_revision_review": {
            "review_id": 1,
            "revision_target": "author",
            "issues": ["中段纸册静态比对过长"],
            "suggestions": ["插入门外威胁的实时感官标记"],
        },
    })

    assert result.get("chapter_status") == "drafted"
    assert len(prompts) == 1
    assert "【分段写作】" not in prompts[0]
    assert prompts[0].count("【当前保留稿 / 必须在此基础上返修】") == 1


# ---------------------------------------------------------------------------
# Polisher Segmented Polishing
# ---------------------------------------------------------------------------


def test_polisher_real_mode_polishes_long_text_in_chunks(monkeypatch, tmp_path):
    """Polisher with 8 paragraphs must trigger multiple invoke_text calls."""
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository
    from novel_factory.agents.polisher import PolisherAgent

    db_path = str(tmp_path / "polisher_segment.db")
    init_db(db_path)
    repo = Repository(db_path)

    repo.create_project(
        project_id="polish-seg",
        name="Polish Seg",
        genre="都市",
        description="测试",
        total_chapters_planned=10,
        target_words=30000,
    )
    repo.save_chapter(
        project_id="polish-seg",
        chapter_number=1,
        title="第一章",
        content="\n\n".join([f"段落{i}：这是一段测试正文，用于验证润色分段逻辑。" * 20 for i in range(8)]),
        word_count=0,
        status="drafted",
    )
    repo.create_instruction(
        project_id="polish-seg",
        chapter_number=1,
        objective="测试",
        key_events="事件",
        emotion_tone="紧张",
    )
    repo.update_chapter_status(
        project_id="polish-seg",
        chapter_number=1,
        status="drafted",
    )

    calls: list[dict[str, Any]] = []

    class FakeLLM:
        config = {"model": "fake"}

        def invoke_text(self, messages, temperature=0.65, max_tokens=4096, **kwargs):
            calls.append({
                "type": "invoke_text",
                "messages": messages,
                "max_tokens": max_tokens,
                "max_retries": kwargs.get("max_retries"),
            })
            seg = len([c for c in calls if c["type"] == "invoke_text"])
            return f"润色段{seg}：优化后的段落内容更加流畅自然。" * 300

        def invoke_json(self, messages, **kwargs):
            raise RuntimeError("JSON not expected")

    agent = PolisherAgent(repo, FakeLLM(), skill_registry=None)
    state = {
        "project_id": "polish-seg",
        "chapter_number": 1,
        "llm_mode": "real",
        "workflow_run_id": "test-run",
        "chapter_status": "drafted",
    }
    result = agent.run(state)

    text_calls = [c for c in calls if c["type"] == "invoke_text"]
    assert len(text_calls) >= 2, f"Expected >=2 polish calls, got {len(text_calls)}"
    assert all(c["max_retries"] is None for c in text_calls)
    assert result.get("chapter_status") == "polished"


# ---------------------------------------------------------------------------
# MemoryCurator Segmented Extraction
# ---------------------------------------------------------------------------


def test_memory_curator_extracts_long_chapter_in_chunks(monkeypatch, tmp_path):
    """Long chapter with distant facts should be extracted in chunks and merged."""
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository
    from novel_factory.agents.memory_curator import MemoryCuratorAgent

    db_path = str(tmp_path / "mc_segment.db")
    init_db(db_path)
    repo = Repository(db_path)

    repo.create_project(
        project_id="mc-seg",
        name="MC Seg",
        genre="都市",
        description="测试",
        total_chapters_planned=10,
        target_words=30000,
    )
    content = (
        "开头段落。" * 50 + "\n\n"
        + "林潮发现父亲留下的潮位表。" * 20 + "\n\n"
        + "中间过渡段落。" * 50 + "\n\n"
        + "沈澜承认自己参与过旧案善后。" * 20 + "\n\n"
        + "结尾段落。" * 50
    )
    repo.save_chapter(
        project_id="mc-seg",
        chapter_number=1,
        title="第一章",
        content=content,
        word_count=0,
        status="reviewed",
    )
    repo.create_instruction(
        project_id="mc-seg",
        chapter_number=1,
        objective="测试",
        key_events="事件",
        emotion_tone="紧张",
    )
    repo.update_chapter_status(
        project_id="mc-seg",
        chapter_number=1,
        status="reviewed",
    )
    ch = repo.get_chapter("mc-seg", 1)
    repo.save_review(
        project_id="mc-seg",
        chapter_id=ch["id"],
        passed=True,
        score=85,
        issues=[],
        suggestions=[],
    )

    calls: list[dict[str, Any]] = []

    class FakeLLM:
        config = {"model": "fake"}

        def invoke_json(self, messages, **kwargs):
            calls.append({"type": "invoke_json", "messages": messages})
            user_content = messages[-1]["content"] if messages else ""
            if "潮位表" in user_content:
                return {
                    "patches": [
                        {
                            "target_table": "story_facts",
                            "operation": "create",
                            "target_name": "fact-001",
                            "data": {"fact_key": "fact-001", "value": "潮位表"},
                            "confidence": 0.8,
                            "evidence_text": "林潮发现父亲留下的潮位表",
                        }
                    ]
                }
            if "善后" in user_content:
                return {
                    "patches": [
                        {
                            "target_table": "story_facts",
                            "operation": "create",
                            "target_name": "fact-002",
                            "data": {"fact_key": "fact-002", "value": "善后"},
                            "confidence": 0.8,
                            "evidence_text": "沈澜承认参与旧案善后",
                        }
                    ]
                }
            return {"patches": []}

        def invoke_text(self, messages, **kwargs):
            raise RuntimeError("text not expected")

    agent = MemoryCuratorAgent(repo, FakeLLM(), skill_registry=None)
    state = {
        "project_id": "mc-seg",
        "chapter_number": 1,
        "llm_mode": "real",
        "workflow_run_id": "test-run",
        "chapter_status": "reviewed",
    }
    result = agent.run(state)

    json_calls = [c for c in calls if c["type"] == "invoke_json"]
    assert len(json_calls) >= 2, f"Expected >=2 MC calls, got {len(json_calls)}"
    assert result.get("memory_items_count") == 2, f"Expected 2 memory items, got {result}"


# ---------------------------------------------------------------------------
# Segment Observability
# ---------------------------------------------------------------------------


def test_segment_events_logged_for_author_segments(monkeypatch, tmp_path):
    """Segmented Author execution should emit segment_started / segment_completed events."""
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository
    from novel_factory.agents.author import AuthorAgent

    db_path = str(tmp_path / "segment_events.db")
    init_db(db_path)
    repo = Repository(db_path)

    repo.create_project(
        project_id="evt-test",
        name="Event Test",
        genre="都市",
        description="测试",
        total_chapters_planned=10,
        target_words=30000,
    )
    repo.save_chapter(
        project_id="evt-test",
        chapter_number=1,
        title="第一章",
        content="",
        word_count=0,
        status="planned",
    )
    repo.create_instruction(
        project_id="evt-test",
        chapter_number=1,
        objective="测试写作",
        key_events="事件1；事件2；事件3",
        emotion_tone="紧张",
    )
    beats = []
    for seq in range(1, 7):
        beats.append(
            {
                "sequence": seq,
                "scene_goal": f"目标{seq}",
                "conflict": f"冲突{seq}",
                "turn": f"转折{seq}",
                "hook": f"钩子{seq}",
            }
        )
    repo.save_scene_beats("evt-test", 1, beats)
    repo.update_chapter_status("evt-test", 1, "scripted")

    class FakeLLM:
        config = {"model": "fake"}

        def invoke_text(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
            body = "正文段落。" * 400
            body += " 目标4 冲突4 转折4 钩子4 目标5 冲突5 转折5 钩子5 目标6 冲突6 转折6 钩子6"
            return body

        def invoke_json(self, messages, **kwargs):
            raise RuntimeError("JSON not expected")

    agent = AuthorAgent(repo, FakeLLM(), skill_registry=None)
    state = {
        "project_id": "evt-test",
        "chapter_number": 1,
        "llm_mode": "real",
        "workflow_run_id": "test-run",
        "chapter_status": "scripted",
    }
    result = agent.run(state)

    exec_events = result.get("_exec_events", [])
    event_types = {e["event_type"] for e in exec_events}
    assert (
        "segment_started" in event_types
        or "segment_completed" in event_types
        or "long_form_generation" in event_types
    ), f"Expected segment or long_form events, got {event_types}"
