"""v6.10.1 Skill governance tests."""

from __future__ import annotations


def test_project_skill_overrides_preserve_knowledge_skills():
    """Project override normalization keeps Knowledge Skill overrides."""
    from novel_factory.api.routes.project_skill_overrides import _normalize_overrides

    overrides = {
        "skills": {"death-penalty": {"enabled": True}},
        "agent_skills": {"author": {"after_llm": ["death-penalty"]}},
        "knowledge_skills": {
            "disabled": ["genre-suspense"],
            "overrides": {
                "webnovel-excitement": {
                    "priority": 90,
                    "token_budget": 1600,
                    "injection_mode": "always",
                }
            },
        },
    }

    normalized = _normalize_overrides(overrides)

    assert normalized["skills"]["death-penalty"]["enabled"] is True
    assert normalized["agent_skills"]["author"]["after_llm"] == ["death-penalty"]
    assert normalized["knowledge_skills"]["disabled"] == ["genre-suspense"]
    assert normalized["knowledge_skills"]["overrides"]["webnovel-excitement"]["priority"] == 90


def test_desktop_knowledge_config_cleaner_is_safe():
    """Desktop config cleaner preserves safe knowledge settings and tolerates bad numbers."""
    from novel_factory.api.routes.desktop import _clean_knowledge_config

    cleaned = _clean_knowledge_config({
        "enabled": True,
        "default_injection_mode": "hybrid",
        "default_token_budget": "bad",
        "api_key": "must-not-pass",
        "agents": {
            "author": {
                "token_budget": 3000,
                "agentic_mode": True,
                "max_tool_rounds": 99,
                "secret": "must-not-pass",
            },
            "": {"token_budget": 100},
        },
    })

    assert cleaned == {
        "enabled": True,
        "default_injection_mode": "hybrid",
        "default_token_budget": 0,
        "agents": {
            "author": {
                "token_budget": 3000,
                "agentic_mode": True,
                "max_tool_rounds": 10,
            }
        },
    }


def test_author_revision_blocking_priority_mentions_quality_gate_contracts():
    """Author revision prompt must make QualityGate blockers first-class constraints."""
    from novel_factory.agents.author import AuthorAgent

    block = AuthorAgent._revision_blocking_priority_block({
        "issues": [
            "QualityGate 阻断：章间衔接断裂：上一章结尾存在明确时间节点“今晚”，本章开头未承接。",
            "[连续性阻断] 标题与正文脱节：标题关键词「帝豪血衣令」未在正文中出现。",
            "[连续性阻断] 章中时空回退：正文出现“十分钟前”并回到已完成的旧场景。",
        ],
        "suggestions": [
            "章首必须承接上一章钩子。",
            "标题关键词必须以原词自然落入正文。",
        ],
    })

    assert "QualityGate / 质检门禁阻断" in block
    assert "章首必须明确承接上一章" in block
    assert "禁止用“十分钟前/刚才/回到前台”" in block
    assert "标题核心关键词必须以原词自然落入正文" in block
