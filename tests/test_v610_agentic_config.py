"""v6.10.0 Agentic configuration and BaseAgent integration tests."""

from __future__ import annotations

import pytest

from novel_factory.config.settings import AgenticConfig, AgenticAgentConfig, Settings


def test_agentic_agent_config_defaults():
    """AgenticAgentConfig has sensible defaults."""
    cfg = AgenticAgentConfig()
    assert cfg.agentic_mode is False
    assert cfg.max_tool_rounds == 3


def test_agentic_config_defaults():
    """AgenticConfig has all agents configured by default."""
    cfg = AgenticConfig()
    assert cfg.enabled is False
    assert "planner" in cfg.agents
    assert "screenwriter" in cfg.agents
    assert "author" in cfg.agents
    assert "polisher" in cfg.agents
    assert "editor" in cfg.agents
    assert "memory_curator" in cfg.agents


def test_agentic_config_custom():
    """AgenticConfig can be customized."""
    cfg = AgenticConfig(
        enabled=True,
        agents={
            "author": AgenticAgentConfig(agentic_mode=True, max_tool_rounds=5),
        },
    )
    assert cfg.enabled is True
    assert cfg.agents["author"].agentic_mode is True
    assert cfg.agents["author"].max_tool_rounds == 5


def test_settings_has_agentic():
    """Settings model includes AgenticConfig."""
    settings = Settings()
    assert hasattr(settings, "agentic")
    assert isinstance(settings.agentic, AgenticConfig)
    assert settings.agentic.enabled is False


def test_settings_has_memory_curator_node_timeout_override():
    """memory_curator gets a longer default node timeout."""
    settings = Settings()
    assert settings.workflow.node_timeout_seconds == 300
    assert settings.workflow.node_timeout_overrides["memory_curator"] == 600


def test_node_timeout_resolves_memory_curator_override():
    """Workflow nodes resolve per-node timeout overrides."""
    from novel_factory.workflow.nodes import _node_timeout_seconds

    settings = Settings()
    assert _node_timeout_seconds(settings, "memory_curator") == 600
    assert _node_timeout_seconds(settings, "author") == 300


def test_settings_from_dict():
    """Settings can be created from dict with agentic config."""
    data = {
        "agentic": {
            "enabled": True,
            "agents": {
                "author": {"agentic_mode": True, "max_tool_rounds": 3},
            },
        }
    }
    settings = Settings(**data)
    assert settings.agentic.enabled is True
    assert settings.agentic.agents["author"].agentic_mode is True


def test_base_agent_agentic_properties():
    """BaseAgent exposes agentic config as properties."""
    from novel_factory.agent_runtime.base import BaseAgent

    # Create a minimal concrete agent for testing
    class TestAgent(BaseAgent):
        agent_id = "test"

        def _execute(self, state):
            return {}

    # Test with agentic_mode=False (default)
    agent = TestAgent(repo=None, llm=None)
    assert agent.use_agentic_mode is False
    assert agent.max_tool_rounds == 3

    # Test with agentic_mode=True
    agent = TestAgent(
        repo=None,
        llm=None,
        agent_config={"agentic_mode": True, "max_tool_rounds": 5},
    )
    assert agent.use_agentic_mode is True
    assert agent.max_tool_rounds == 5


def test_base_agent_knowledge_context():
    """BaseAgent._get_knowledge_context() returns empty when no knowledge_manager."""
    from novel_factory.agent_runtime.base import BaseAgent

    class TestAgent(BaseAgent):
        agent_id = "test"

        def _execute(self, state):
            return {}

    agent = TestAgent(repo=None, llm=None)
    assert agent._get_knowledge_context("author") == ""


def test_base_agent_project_genre():
    """BaseAgent._get_project_genre() returns None when no repo."""
    from novel_factory.agent_runtime.base import BaseAgent

    class TestAgent(BaseAgent):
        agent_id = "test"

        def _execute(self, state):
            return {}

    agent = TestAgent(repo=None, llm=None)
    assert agent._get_project_genre("proj-1") is None
