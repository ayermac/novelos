"""Deterministic stub LLM provider for tests, demos, and smoke runs."""

from __future__ import annotations

from .provider import LLMProvider


STUB_CHAPTER_CONTENT = """林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。
"你来了。"身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。
"你是谁？"林默警觉地问道，手已经摸向腰间的短剑。
"我是谁不重要，"黑衣男子缓缓走近，"重要的是，你正在寻找的东西，也在寻找你。"
林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？
"别紧张，"黑衣男子停下脚步，"我是来帮你的。但你必须做出选择。"
"什么选择？"林默紧盯着对方，随时准备出手。
"是继续寻找真相，还是保全你现在的平静生活。"黑衣男子的目光变得复杂。
林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。
"我已经没有退路了，"他终于说道，"不管前面是什么，我都必须走下去。"
黑衣男子点了点头。"很好。那么，从现在开始，你要小心身边的每一个人。"
说完，他的身影渐渐消失在阴影中，仿佛从未出现过。
林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。
他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。
他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。
最后，他只写了一句话：今天，一切都将改变。
就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。
门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。
"救救我，"年轻人喘着气说，"他们...他们要杀我。"
林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。
他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。
黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。"""


class StubLLM(LLMProvider):
    """Stub LLM that returns minimal valid outputs for local tests and demos."""

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
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
            return {
                "title": "测试章节",
                "content": STUB_CHAPTER_CONTENT,
                "word_count": len(STUB_CHAPTER_CONTENT),
                "implemented_events": ["事件1"],
                "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            return {
                "content": STUB_CHAPTER_CONTENT,
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
        return "{}"
