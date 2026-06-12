"""v6.10.6 Genesis hardening tests."""

from __future__ import annotations

import pytest

from novel_factory.api.routes import genesis as genesis_routes
from novel_factory.llm.openai_compatible import LLMTimeoutError
from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft


def _request() -> genesis_routes.GenesisGenerateRequest:
    return genesis_routes.GenesisGenerateRequest(
        project_id="genesis-hardening",
        title="开局召唤神军",
        genre="都市系统召唤爽文",
        premise="F级召唤师在都市战场召唤神军逆袭",
        target_chapters=2,
        target_words=6000,
        target_audience="男频爽文读者",
        style_preference="热血、强爽点",
        constraints="章节指令必须具体",
    )


def _long_request() -> genesis_routes.GenesisGenerateRequest:
    return genesis_routes.GenesisGenerateRequest(
        project_id="genesis-hardening-long",
        title="开局召唤神军",
        genre="都市系统召唤爽文",
        premise="F级最废召唤师凭借亿万神军逆天改命，以一人成国之姿热血守城、保家卫国。",
        target_chapters=10,
        target_words=30000,
        target_audience="男频爽文读者",
        style_preference="热血、强爽点、守城、反压迫",
        constraints="每章必须有独立关键事件，不能模板化。",
    )


def _base_draft(instructions: list[dict]) -> dict:
    return {
        "project_updates": {
            "description": "F级召唤师陆恒在都市裂隙战场召唤英灵军团逆袭。"
        },
        "world_settings": [
            {
                "title": "觉醒都市",
                "category": "时代背景",
                "content": "现代都市与异位面裂隙重叠，学院、豪门和军方共同争夺觉醒资源。",
            },
            {
                "title": "军势空间",
                "category": "能力规则",
                "content": "陆恒可用国运共鸣绕过普通召唤师精神池限制，召唤英灵战阵。",
            },
            {
                "title": "评级压迫",
                "category": "冲突结构",
                "content": "F级学生被学院当作裂隙炮灰，豪门通过评级垄断资源。",
            },
        ],
        "characters": [
            {
                "name": "陆恒",
                "role": "protagonist",
                "description": "F级召唤师。目标：证明军势空间能一人成军。矛盾：初期召唤时限极短。与主角利益关系：自身。",
            },
            {
                "name": "刘明辉",
                "role": "antagonist",
                "description": "F班教导主任。目标：替赵家打压陆恒。秘密：靠牺牲F班学生换资源。与主角利益关系：直接压迫者。",
            },
        ],
        "factions": [
            {
                "name": "临江觉醒者学院",
                "type": "学院",
                "description": "掌握觉醒仪式台和低级裂隙入口。对主角态度：歧视并试图控制。当前阶段行动：安排F班参加高危考核。",
            },
            {
                "name": "龙夏军方特勤组",
                "type": "军方",
                "description": "负责监测异常觉醒数据。对主角态度：从怀疑转向观察。当前阶段行动：记录陆恒召唤数据。",
            },
        ],
        "outlines": [
            {
                "chapters_range": "1-2",
                "title": "废材觉醒",
                "content": "阶段冲突：陆恒被学院和刘明辉压入F班炮灰位。转折：军势空间在考核场响应。阶段结果：陆恒打破F班必败定律并进入军方视野。",
                "level": "arc",
                "sequence": 1,
            }
        ],
        "plot_holes": [
            {
                "code": "PH-001",
                "type": "能力伏笔",
                "title": "军势空间来源",
                "description": "触发场景：陆恒召唤刀盾手时。读者表象：普通召唤变异。真相方向：国运英灵传承。预计兑现章节：第10章。",
                "status": "planted",
            }
        ],
        "instructions": instructions,
    }


def _summon_seed_draft_without_instructions() -> dict:
    draft = _base_draft([])
    draft["project_updates"] = {
        "description": "F级最废召唤师凭借亿万神军逆天改命，以一人成国之姿热血守城、保家卫国。"
    }
    draft["characters"] = [
        {
            "name": "陆沉",
            "role": "protagonist",
            "description": "江海大学觉醒系学生，目标是以亿万军团打破天赋歧视与豪门垄断。",
        },
        {
            "name": "林破军",
            "role": "supporting",
            "description": "江海市城防军少校，寻找统帅型觉醒者。",
        },
        {
            "name": "苏晚晴",
            "role": "supporting",
            "description": "S级生命泉源治疗师，能增幅召唤物。",
        },
        {
            "name": "赵天罡",
            "role": "antagonist",
            "description": "S级雷霆法神，维护豪门天才秩序。",
        },
    ]
    draft["factions"] = [
        {
            "name": "江海市城防军",
            "type": "国家暴力机关",
            "description": "负责守护东海防线，急需打破兽潮数量劣势。",
        },
        {
            "name": "赵家",
            "type": "顶级豪门",
            "description": "垄断高阶魔兽材料与跨国资本，压制召唤师复苏。",
        },
        {
            "name": "深渊黑潮与裂缝议会",
            "type": "异界入侵势力",
            "description": "正在积蓄第七次大规模黑潮。",
        },
        {
            "name": "江海大学与觉醒者协会",
            "type": "教育-行业联合体",
            "description": "掌握评级数据库与公立任务渠道。",
        },
    ]
    draft["outlines"] = []
    draft["plot_holes"] = []
    draft["instructions"] = []
    return draft


def test_instruction_segment_prompt_requires_structured_contract():
    prompt = genesis_routes._build_genesis_segment_prompt(
        _request(),
        segment="instructions",
        draft_json='{"characters":[{"name":"陆恒"}]}',
        chapter_start=1,
        chapter_end=2,
    )

    assert "primary_location" in prompt
    assert "opposing_force" in prompt
    assert "action_chain" in prompt
    assert "visible_result" in prompt
    assert "state_change" in prompt
    assert "不是阶段大纲" in prompt
    assert "禁止只写" in prompt


def test_structured_instruction_passes_depth_gate():
    draft = _base_draft([
        {
            "chapter_number": 1,
            "objective": "陆恒在临江觉醒者学院月度实战考核场击败刘明辉安排的E级魔物群，因此让军方记录异常召唤数据",
            "protagonist": "陆恒",
            "primary_location": "临江觉醒者学院月度实战考核场",
            "opposing_force": "刘明辉与E级魔物群",
            "action_chain": [
                "陆恒在考核场拒绝刘明辉的诱饵位安排",
                "陆恒召唤刀盾手挡住E级魔物群冲锋",
                "陆恒指挥游弩手点杀魔物首领并保住F班学生",
            ],
            "visible_result": "E级魔物群被击溃，F班第一次拿到实战考核第一",
            "state_change": "陆恒从F级废材变成军方特勤组重点观察对象",
            "key_events": "刘明辉强行安排诱饵位；陆恒召唤刀盾手抗住魔物群；游弩手点杀首领，军方记录异常数据",
            "emotion_tone": "压迫后的反杀",
            "ending_hook": "军方观察员调出陆恒觉醒日的红光异常记录",
            "continuity_seed": "下一章必须让赵天擎发现军方关注陆恒并升级压制",
            "word_target": 3000,
        }
    ])

    report = evaluate_genesis_draft(
        draft,
        title="开局召唤神军",
        genre="都市系统召唤爽文",
        premise="F级召唤师在都市战场召唤神军逆袭",
        target_chapters=1,
    )
    codes = {issue.code for issue in report.issues}
    assert "SHALLOW_INSTRUCTION" not in codes
    assert report.quality_status != "blocked"


def test_old_abstract_instruction_still_fails_depth_gate():
    draft = _base_draft([
        {
            "chapter_number": 1,
            "objective": "第5章在月度实战考核中打破F班必败定律，以战绩换取生存尊严并吸引军方注意",
            "key_events": "打破定律；吸引注意；推动剧情",
            "emotion_tone": "热血",
        }
    ])

    report = evaluate_genesis_draft(
        draft,
        title="开局召唤神军",
        genre="都市系统召唤爽文",
        premise="F级召唤师在都市战场召唤神军逆袭",
        target_chapters=1,
    )
    codes = {issue.code for issue in report.issues}
    assert "SHALLOW_INSTRUCTION" in codes
    assert report.quality_status == "blocked"


@pytest.mark.asyncio
async def test_instruction_quality_repair_only_replaces_instructions(monkeypatch):
    shallow_draft = _base_draft([
        {
            "chapter_number": 1,
            "objective": "第5章在月度实战考核中打破F班必败定律，以战绩换取生存尊严并吸引军方注意",
            "key_events": "打破定律；吸引注意；推动剧情",
            "emotion_tone": "热血",
        }
    ])
    initial_report = evaluate_genesis_draft(
        shallow_draft,
        title="开局召唤神军",
        genre="都市系统召唤爽文",
        premise="F级召唤师在都市战场召唤神军逆袭",
        target_chapters=1,
    )

    class RepairLLM:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            user_prompt = messages[-1]["content"]
            assert "只重写 instructions" in user_prompt
            return {
                "instructions": [
                    {
                        "chapter_number": 1,
                        "objective": "陆恒在临江觉醒者学院月度实战考核场击败刘明辉安排的E级魔物群，因此让军方记录异常召唤数据",
                        "protagonist": "陆恒",
                        "primary_location": "临江觉醒者学院月度实战考核场",
                        "opposing_force": "刘明辉与E级魔物群",
                        "action_chain": [
                            "陆恒在考核场拒绝刘明辉的诱饵位安排",
                            "陆恒召唤刀盾手挡住E级魔物群冲锋",
                            "陆恒指挥游弩手点杀魔物首领并保住F班学生",
                        ],
                        "visible_result": "E级魔物群被击溃，F班第一次拿到实战考核第一",
                        "state_change": "陆恒从F级废材变成军方特勤组重点观察对象",
                        "key_events": "刘明辉强行安排诱饵位；陆恒召唤刀盾手抗住魔物群；游弩手点杀首领，军方记录异常数据",
                        "emotion_tone": "压迫后的反杀",
                        "ending_hook": "军方观察员调出陆恒觉醒日的红光异常记录",
                        "continuity_seed": "下一章必须让赵天擎发现军方关注陆恒并升级压制",
                        "word_target": 3000,
                    }
                ]
            }

    monkeypatch.setattr(genesis_routes, "_build_genesis_llm", lambda settings: RepairLLM())

    repaired = await genesis_routes._repair_genesis_instruction_quality(
        _request(),
        settings=object(),
        draft=shallow_draft,
        quality_report=initial_report,
    )

    assert repaired["world_settings"] == shallow_draft["world_settings"]
    assert repaired["characters"] == shallow_draft["characters"]
    assert repaired["outlines"] == shallow_draft["outlines"]
    assert repaired["plot_holes"] == shallow_draft["plot_holes"]
    assert repaired["instructions"][0]["primary_location"]
    assert repaired["_meta"]["instruction_repair_source"] == "local_seeded_rebuild"

    repaired_report = evaluate_genesis_draft(
        repaired,
        title="开局召唤神军",
        genre="都市系统召唤爽文",
        premise="F级召唤师在都市战场召唤神军逆袭",
        target_chapters=1,
    )
    assert "SHALLOW_INSTRUCTION" not in {issue.code for issue in repaired_report.issues}


def test_non_instruction_blocker_does_not_trigger_instruction_repair():
    draft = _base_draft([
        {
            "chapter_number": 1,
            "objective": "陆恒在临江觉醒者学院考核场击败刘明辉，因此获得军方关注",
            "key_events": "陆恒进入考核场；陆恒击败刘明辉安排的魔物；军方记录异常数据",
            "ending_hook": "军方记录被赵家内线看见",
            "continuity_seed": "下一章赵家开始干预军方调查",
        }
    ])
    draft["_meta"] = {"source": "scaffold_fallback", "quality_status": "scaffold_fallback"}

    report = evaluate_genesis_draft(
        draft,
        title="开局召唤神军",
        genre="都市系统召唤爽文",
        premise="F级召唤师在都市战场召唤神军逆袭",
        target_chapters=1,
    )

    assert report.quality_status == "scaffold_fallback"
    assert not genesis_routes._has_instruction_repair_target(report)


def test_seeded_scaffold_inherits_summon_entities_and_unique_instructions():
    scaffold = genesis_routes._generate_genesis_scaffold(
        _long_request(),
        seed_draft=_summon_seed_draft_without_instructions(),
    )
    serialized = str(scaffold)

    assert "陆沉" in serialized
    assert "赵天罡" in serialized
    assert "江海市城防军" in serialized
    assert "深渊黑潮" in serialized
    assert "沈砚" not in serialized
    assert "星环事务所" not in serialized
    assert "雾港档案馆" not in serialized
    assert "裁衡" not in serialized

    instructions = scaffold["instructions"]
    assert len(instructions) == 10
    key_events_4_to_8 = [item["key_events"] for item in instructions[3:8]]
    hooks_4_to_8 = [item["ending_hook"] for item in instructions[3:8]]
    assert len(set(key_events_4_to_8)) == 5
    assert len(set(hooks_4_to_8)) == 5
    assert instructions[3]["primary_location"] == "东海城门外防线"
    assert instructions[4]["visible_result"]

    content_only = dict(scaffold)
    content_only.pop("_meta", None)
    report = evaluate_genesis_draft(
        content_only,
        title=_long_request().title,
        genre=_long_request().genre,
        premise=_long_request().premise,
        target_chapters=10,
    )
    codes = {issue.code for issue in report.issues}
    assert "REPETITIVE_KEY_EVENTS" not in codes
    assert "SHALLOW_INSTRUCTION" not in codes


@pytest.mark.asyncio
async def test_repetitive_key_events_get_local_seeded_repair_without_llm(monkeypatch):
    repeated = []
    for chapter in range(1, 11):
        repeated.append({
            "chapter_number": chapter,
            "objective": f"陆沉在第 {chapter} 章围绕前章坐标展开行动，目标是取得能改变局势的证据",
            "key_events": "陆沉抵达新地点后发现证据被转移；林破军交换情报；赵天罡制造阻碍迫使主角选择公开或隐藏真相",
            "ending_hook": "证据中出现一个与陆沉过去有关的名字",
            "continuity_seed": f"下一章必须解释第 {chapter} 章证据中的名字",
            "word_target": 3000,
        })
    draft = _summon_seed_draft_without_instructions()
    draft["instructions"] = repeated

    initial_report = evaluate_genesis_draft(
        draft,
        title=_long_request().title,
        genre=_long_request().genre,
        premise=_long_request().premise,
        target_chapters=10,
    )
    assert "REPETITIVE_KEY_EVENTS" in {issue.code for issue in initial_report.issues}
    assert genesis_routes._has_instruction_repair_target(initial_report)

    def fail_if_llm_needed(_settings):
        raise AssertionError("local seeded repair should resolve repetitive key_events before LLM repair")

    monkeypatch.setattr(genesis_routes, "_build_genesis_llm", fail_if_llm_needed)

    repaired = await genesis_routes._repair_genesis_instruction_quality(
        _long_request(),
        settings=object(),
        draft=draft,
        quality_report=initial_report,
    )

    assert repaired["characters"] == draft["characters"]
    assert repaired["factions"] == draft["factions"]
    assert repaired["_meta"]["instruction_repair_source"] == "local_seeded_rebuild"
    repaired_report = evaluate_genesis_draft(
        repaired,
        title=_long_request().title,
        genre=_long_request().genre,
        premise=_long_request().premise,
        target_chapters=10,
    )
    repaired_codes = {issue.code for issue in repaired_report.issues}
    assert "REPETITIVE_KEY_EVENTS" not in repaired_codes
    assert "SHALLOW_INSTRUCTION" not in repaired_codes


@pytest.mark.asyncio
async def test_genesis_segment_timeout_recovers_partial_draft(monkeypatch):
    calls: list[str] = []

    class TimeoutOnInstructionsLLM:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            prompt = messages[-1]["content"]
            if "【生成段落】foundation" in prompt:
                calls.append("foundation")
                return {
                    "project_updates": {"description": "陆恒召唤英灵军团逆袭都市觉醒体系。"},
                    "world_settings": [
                        {"title": "觉醒都市", "category": "时代背景", "content": "学院、军方和豪门共同掌控裂隙资源。"},
                        {"title": "军势空间", "category": "能力规则", "content": "陆恒能召唤英灵军团绕过普通精神池限制。"},
                        {"title": "评级压迫", "category": "冲突结构", "content": "F级觉醒者被当作裂隙炮灰。"},
                    ],
                }
            if "【生成段落】cast" in prompt:
                calls.append("cast")
                return {
                    "characters": [
                        {"name": "陆恒", "role": "protagonist", "description": "目标：打破F级歧视。矛盾：召唤时限很短。与主角利益关系：自身。"},
                        {"name": "刘明辉", "role": "antagonist", "description": "目标：替赵家打压陆恒。秘密：牺牲F班换资源。与主角利益关系：直接压迫者。"},
                    ],
                    "factions": [
                        {"name": "临江觉醒者学院", "type": "学院", "description": "资源：觉醒仪式台和裂隙入口。对主角态度：歧视。当前阶段行动：安排高危考核。"},
                    ],
                }
            if "【生成段落】plot" in prompt:
                calls.append("plot")
                return {
                    "outlines": [
                        {"chapters_range": "1-2", "title": "废材觉醒", "content": "阶段冲突：陆恒被压入F班。转折：军势空间响应。阶段结果：军方开始关注。", "level": "arc", "sequence": 1},
                    ],
                    "plot_holes": [
                        {"code": "PH-001", "type": "能力伏笔", "title": "军势空间来源", "description": "触发场景：陆恒召唤刀盾手。读者表象：召唤变异。真相方向：国运英灵传承。预计兑现章节：第10章。", "status": "planted"},
                    ],
                }
            if "【生成段落】instructions" in prompt:
                calls.append("instructions")
                raise LLMTimeoutError("LLM 响应超时（>300秒），请稍后重试")
            raise AssertionError(f"Unexpected prompt: {prompt[:120]}")

    monkeypatch.setattr(genesis_routes, "_build_genesis_llm", lambda settings: TimeoutOnInstructionsLLM())

    recovered = await genesis_routes._generate_real_draft(
        _request(),
        settings=object(),
        run_id="run-timeout",
        progress=lambda *_args, **_kwargs: None,
    )

    assert calls == ["foundation", "cast", "plot", "instructions"]
    assert recovered["project_updates"]["description"] == "陆恒召唤英灵军团逆袭都市觉醒体系。"
    assert recovered["world_settings"][0]["title"] == "觉醒都市"
    assert recovered["characters"][0]["name"] == "陆恒"
    assert recovered["outlines"][0]["title"] == "废材觉醒"
    assert recovered["instructions"]
    assert recovered["_meta"]["source"] == "local_recovery"
    assert recovered["_meta"]["fallback_reason"] == "instructions:1-2_llm_unavailable"


@pytest.mark.asyncio
async def test_genesis_completion_timeout_recovers_partial_draft(monkeypatch):
    class TimeoutCompletionLLM:
        def invoke_json(self, messages, max_tokens=None, max_retries=1):
            raise LLMTimeoutError("LLM 响应超时（>300秒），请稍后重试")

    monkeypatch.setattr(genesis_routes, "_build_genesis_llm", lambda settings: TimeoutCompletionLLM())

    partial = {
        "project_updates": {"description": "陆恒召唤英灵军团逆袭都市觉醒体系。"},
        "world_settings": [
            {"title": "觉醒都市", "category": "时代背景", "content": "学院、军方和豪门共同掌控裂隙资源。"},
        ],
    }

    recovered = await genesis_routes._complete_real_genesis_draft(
        _request(),
        settings=object(),
        draft=partial,
    )

    assert recovered["project_updates"]["description"] == "陆恒召唤英灵军团逆袭都市觉醒体系。"
    assert recovered["world_settings"][0]["title"] == "觉醒都市"
    assert recovered["characters"]
    assert recovered["instructions"]
    assert recovered["_meta"]["source"] == "local_recovery"
    assert recovered["_meta"]["fallback_reason"] == "completion_llm_unavailable"
