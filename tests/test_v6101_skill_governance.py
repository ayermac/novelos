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
