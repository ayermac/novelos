"""Agent Container — Dependency injection for Novelos agents.

v6.11.0 Research Prototype:
Provides a container for lazy-loading and caching agent instances.
This decouples agent creation from usage and enables easier testing.

Design goals:
1. Single instance per agent type (singleton pattern)
2. Lazy loading (create on first access)
3. Memory-safe (no circular references)
4. Testable (can inject mocks)

Usage:
    container = AgentContainer(repo, llm)
    author = container.get_author()
    editor = container.get_editor()
"""

from __future__ import annotations

import logging
from typing import Callable, Type, TypeVar

from ..db.repository import Repository
from ..llm.provider import LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AgentContainer:
    """Dependency injection container for agents.
    
    v6.11.0 Research Prototype:
    Manages agent lifecycle with lazy loading and caching.
    
    Attributes:
        repo: Repository instance for DB access
        llm: LLM provider for AI calls
        skill_registry: Optional skill registry
        _agents: Cache of instantiated agents
    """
    
    def __init__(
        self,
        repo: Repository,
        llm: LLMProvider,
        *,
        skill_registry=None,
        checkpoint_dir: str | None = None,
    ):
        self.repo = repo
        self.llm = llm
        self.skill_registry = skill_registry
        self.checkpoint_dir = checkpoint_dir
        self._agents: dict[str, any] = {}
        
        # Factory functions (can be overridden for testing)
        self._factories: dict[str, Callable[[], any]] = {}
    
    def get_planner(self):
        """Get or create PlannerAgent instance."""
        return self._get_or_create(
            "planner",
            lambda: self._create_agent("planner"),
        )
    
    def get_screenwriter(self):
        """Get or create ScreenwriterAgent instance."""
        return self._get_or_create(
            "screenwriter",
            lambda: self._create_agent("screenwriter"),
        )
    
    def get_author(self):
        """Get or create AuthorAgent instance."""
        return self._get_or_create(
            "author",
            lambda: self._create_agent("author"),
        )
    
    def get_polisher(self):
        """Get or create PolisherAgent instance."""
        return self._get_or_create(
            "polisher",
            lambda: self._create_agent("polisher"),
        )
    
    def get_editor(self):
        """Get or create EditorAgent instance."""
        return self._get_or_create(
            "editor",
            lambda: self._create_agent("editor"),
        )
    
    def get_memory_curator(self):
        """Get or create MemoryCuratorAgent instance."""
        return self._get_or_create(
            "memory_curator",
            lambda: self._create_agent("memory_curator"),
        )
    
    def _get_or_create(self, agent_name: str, factory: Callable[[], any]) -> any:
        """Get cached agent or create new instance.
        
        Args:
            agent_name: Unique key for the agent
            factory: Function to create the agent if not cached
            
        Returns:
            Agent instance (cached or newly created)
        """
        if agent_name not in self._agents:
            logger.debug("Creating agent: %s", agent_name)
            self._agents[agent_name] = factory()
        return self._agents[agent_name]
    
    def _create_agent(self, agent_name: str):
        """Create an agent instance by name.
        
        Args:
            agent_name: Name of the agent to create
            
        Returns:
            New agent instance
        """
        if agent_name == "planner":
            from ..agents.planner import PlannerAgent
            return PlannerAgent(self.repo, self.llm)
        
        elif agent_name == "screenwriter":
            from ..agents.screenwriter import ScreenwriterAgent
            return ScreenwriterAgent(self.repo, self.llm)
        
        elif agent_name == "author":
            from ..agents.author import AuthorAgent
            return AuthorAgent(
                self.repo,
                self.llm,
                skill_registry=self.skill_registry,
                checkpoint_dir=self.checkpoint_dir,
            )
        
        elif agent_name == "polisher":
            from ..agents.polisher import PolisherAgent
            return PolisherAgent(
                self.repo,
                self.llm,
                skill_registry=self.skill_registry,
            )
        
        elif agent_name == "editor":
            from ..agents.editor import EditorAgent
            return EditorAgent(
                self.repo,
                self.llm,
                skill_registry=self.skill_registry,
            )
        
        elif agent_name == "memory_curator":
            from ..agents.memory_curator import MemoryCuratorAgent
            return MemoryCuratorAgent(self.repo, self.llm)
        
        else:
            raise ValueError(f"Unknown agent: {agent_name}")
    
    def register_factory(self, agent_name: str, factory: Callable[[], any]) -> None:
        """Register a custom factory for an agent (useful for testing).
        
        Args:
            agent_name: Name of the agent
            factory: Function that returns an agent instance
        """
        self._factories[agent_name] = factory
        # Clear cached instance if exists
        if agent_name in self._agents:
            del self._agents[agent_name]
    
    def clear_cache(self) -> None:
        """Clear all cached agents.
        
        Useful for testing or when agents need to be recreated.
        """
        self._agents.clear()
    
    def cached_agents(self) -> list[str]:
        """Return list of currently cached agent names."""
        return list(self._agents.keys())
    
    # ========================================================================
    # Context manager support for scoped containers
    # ========================================================================
    
    def __enter__(self) -> "AgentContainer":
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, clearing cache."""
        self.clear_cache()


# =============================================================================
# Convenience function for creating containers
# =============================================================================

def create_agent_container(
    repo: Repository,
    llm: LLMProvider,
    **kwargs,
) -> AgentContainer:
    """Create an AgentContainer with the given dependencies.
    
    Args:
        repo: Repository instance
        llm: LLM provider
        **kwargs: Additional arguments passed to AgentContainer
        
    Returns:
        AgentContainer instance
    """
    return AgentContainer(repo, llm, **kwargs)