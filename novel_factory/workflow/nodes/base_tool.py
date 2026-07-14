"""Base Node Tool — Atomic execution pattern for LangGraph nodes.

v6.11.0 Research Prototype: Borrowing from ainovel-cli's "three-piece" pattern:
1. Load artifacts (read context from DB/files)
2. Execute agent logic (core LLM call)
3. Save artifacts (persist results to DB)
4. Update progress (advance state)
5. Append checkpoint (record metadata for recovery)

Key principles:
- Idempotent: Can be safely re-executed without side effects
- Atomic: All-or-nothing execution with rollback on failure
- Observable: Clear logging and tracing at each phase
"""

from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

from ...db.repository import Repository
from ...llm.provider import LLMProvider
from ...models.state import FactoryState

logger = logging.getLogger(__name__)


class NodeToolResult:
    """Result from a node tool execution.
    
    Encapsulates the result dict that will be merged into FactoryState,
    with additional metadata for observability.
    """
    
    def __init__(
        self,
        updates: dict[str, Any],
        *,
        success: bool = True,
        phase: str = "",
        agent: str = "",
        error: str | None = None,
    ):
        self.updates = updates
        self.success = success
        self.phase = phase
        self.agent = agent
        self.error = error
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for merging into FactoryState."""
        result = dict(self.updates)
        if self.error:
            result["error"] = self.error
        return result


class BaseNodeTool(ABC):
    """Base class for atomic node tools.
    
    v6.11.0 Research Prototype:
    Implements the "three-piece" pattern within LangGraph nodes.
    
    Subclasses implement:
    - _load_artifacts(): Read context from DB/state
    - _execute_agent(): Core agent logic (LLM call)
    - _save_artifacts(): Persist results to DB
    - _update_progress(): Advance state
    - _compute_digest(): For idempotency check
    
    Usage:
        class AuthorNodeTool(BaseNodeTool):
            ...
        
        tool = AuthorNodeTool(repo, llm)
        result = tool.execute(state)
        return result.to_dict()
    """
    
    # Subclass should override
    NODE_NAME: str = "base"
    AGENT_NAME: str = "base"
    
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
        self._start_time: float | None = None
        self._phase: str = "init"
    
    def execute(self, state: FactoryState) -> NodeToolResult:
        """Execute the atomic tool with idempotency check.
        
        This is the main entry point. It orchestrates:
        1. Idempotency check (skip if already completed)
        2. Load artifacts
        3. Execute agent
        4. Save artifacts
        5. Update progress
        6. Return result
        """
        self._start_time = time.time()
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)
        
        try:
            # Phase 1: Idempotency check
            self._phase = "idempotency_check"
            if self._is_idempotent(state):
                logger.info(
                    "[%s] Skipping %s.%d - already completed (idempotent)",
                    self.NODE_NAME, project_id, chapter_number,
                )
                return self._return_cached_result(state)
            
            # Phase 2: Load artifacts
            self._phase = "load_artifacts"
            logger.debug(
                "[%s] Loading artifacts for %s.%d",
                self.NODE_NAME, project_id, chapter_number,
            )
            context = self._load_artifacts(state)
            
            # Phase 3: Execute agent
            self._phase = "execute_agent"
            logger.info(
                "[%s] Executing agent for %s.%d",
                self.NODE_NAME, project_id, chapter_number,
            )
            agent_result = self._execute_agent(state, context)
            
            # Phase 4: Save artifacts
            self._phase = "save_artifacts"
            logger.debug(
                "[%s] Saving artifacts for %s.%d",
                self.NODE_NAME, project_id, chapter_number,
            )
            self._save_artifacts(state, agent_result)
            
            # Phase 5: Update progress
            self._phase = "update_progress"
            logger.debug(
                "[%s] Updating progress for %s.%d",
                self.NODE_NAME, project_id, chapter_number,
            )
            progress_updates = self._update_progress(state, agent_result)
            
            # Phase 6: Build result
            self._phase = "complete"
            elapsed = time.time() - self._start_time
            logger.info(
                "[%s] Completed %s.%d in %.2fs",
                self.NODE_NAME, project_id, chapter_number, elapsed,
            )
            
            return NodeToolResult(
                updates=progress_updates,
                success=True,
                phase=self._phase,
                agent=self.AGENT_NAME,
            )
            
        except Exception as e:
            elapsed = time.time() - self._start_time if self._start_time else 0
            logger.error(
                "[%s] Failed %s.%d after %.2fs: %s",
                self.NODE_NAME, project_id, chapter_number, elapsed, e,
                exc_info=True,
            )
            return NodeToolResult(
                updates={},
                success=False,
                phase=self._phase,
                agent=self.AGENT_NAME,
                error=str(e),
            )
    
    # =========================================================================
    # Subclass must implement these methods
    # =========================================================================
    
    @abstractmethod
    def _load_artifacts(self, state: FactoryState) -> dict[str, Any]:
        """Load context from DB/state.
        
        Returns:
            Context dict for the agent.
        """
        raise NotImplementedError
    
    @abstractmethod
    def _execute_agent(self, state: FactoryState, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the core agent logic.
        
        Args:
            state: Current workflow state
            context: Loaded context from _load_artifacts
            
        Returns:
            Agent result dict
        """
        raise NotImplementedError
    
    @abstractmethod
    def _save_artifacts(self, state: FactoryState, result: dict[str, Any]) -> None:
        """Persist results to DB.
        
        Args:
            state: Current workflow state
            result: Agent result from _execute_agent
        """
        raise NotImplementedError
    
    @abstractmethod
    def _update_progress(self, state: FactoryState, result: dict[str, Any]) -> dict[str, Any]:
        """Update progress and return state updates.
        
        Args:
            state: Current workflow state
            result: Agent result from _execute_agent
            
        Returns:
            Dict to merge into FactoryState
        """
        raise NotImplementedError
    
    # =========================================================================
    # Optional overrides for idempotency
    # =========================================================================
    
    def _compute_digest(self, state: FactoryState) -> str:
        """Compute a digest for idempotency check.
        
        Override this to define what makes a request unique.
        Default implementation uses project_id + chapter_number + node_name.
        """
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)
        key = f"{project_id}:{chapter_number}:{self.NODE_NAME}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def _is_idempotent(self, state: FactoryState) -> bool:
        """Check if this execution can be skipped (already completed).
        
        Default implementation returns False (always execute).
        Override to implement actual idempotency check.
        """
        return False
    
    def _return_cached_result(self, state: FactoryState) -> NodeToolResult:
        """Return cached result when idempotency check passes.
        
        Override to return actual cached result.
        """
        return NodeToolResult(
            updates={},
            success=True,
            phase="cached",
            agent=self.AGENT_NAME,
        )


# =============================================================================
# Concrete Implementation Example: AuthorNodeTool
# =============================================================================

class AuthorNodeTool(BaseNodeTool):
    """Atomic tool for Author agent.
    
    v6.11.0 Research Prototype:
    Wraps AuthorAgent execution in the three-piece pattern.
    """
    
    NODE_NAME = "author"
    AGENT_NAME = "author"
    
    def __init__(self, repo: Repository, llm: LLMProvider, **kwargs):
        super().__init__(repo, llm, **kwargs)
        self._agent_result: dict[str, Any] | None = None
    
    def _load_artifacts(self, state: FactoryState) -> dict[str, Any]:
        """Load chapter context from DB.
        
        Returns context needed for Author agent:
        - Project info
        - Chapter instruction
        - Previous chapters (for continuity)
        - Characters, world settings, etc.
        """
        from ...agent_runtime.context_builder import AgentContextBuilder
        
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)
        
        builder = AgentContextBuilder(self.repo)
        context = builder.build_author_context(project_id, chapter_number)
        
        return context
    
    def _execute_agent(self, state: FactoryState, context: dict[str, Any]) -> dict[str, Any]:
        """Execute AuthorAgent with loaded context."""
        from ...agents.author import AuthorAgent
        
        agent = AuthorAgent(
            self.repo,
            self.llm,
            skill_registry=self.skill_registry,
            checkpoint_dir=self.checkpoint_dir,
        )
        
        # The agent's run() method handles the actual LLM call
        result = agent.run(state)
        self._agent_result = result
        return result
    
    def _save_artifacts(self, state: FactoryState, result: dict[str, Any]) -> None:
        """Save chapter content to DB.
        
        The AuthorAgent already saves the chapter content in its run() method,
        so this is a no-op for now. Future iterations could separate
        the persistence logic from the agent.
        """
        # AuthorAgent already persists the chapter content
        # This hook is for additional artifact storage if needed
        pass
    
    def _update_progress(self, state: FactoryState, result: dict[str, Any]) -> dict[str, Any]:
        """Return state updates from agent result."""
        updates = {}
        
        if "error" not in result:
            # Update chapter status
            updates["chapter_status"] = "drafted"
            updates["requires_human"] = False
        
        # Include any token usage updates
        if "prompt_tokens" in result:
            updates["prompt_tokens"] = result["prompt_tokens"]
        if "completion_tokens" in result:
            updates["completion_tokens"] = result["completion_tokens"]
        
        return updates
    
    def _compute_digest(self, state: FactoryState) -> str:
        """Compute digest based on input that affects output.
        
        For Author, this includes:
        - project_id
        - chapter_number
        - instruction content (if changed, should re-execute)
        """
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)
        
        # Include instruction hash to detect changes
        instruction = self.repo.get_instruction(project_id, chapter_number)
        instruction_hash = ""
        if instruction:
            obj_text = str(instruction.get("objective", ""))
            instruction_hash = hashlib.sha256(obj_text.encode()).hexdigest()[:8]
        
        key = f"{project_id}:{chapter_number}:{self.NODE_NAME}:{instruction_hash}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def _is_idempotent(self, state: FactoryState) -> bool:
        """Check if chapter is already drafted and content exists.
        
        v6.11.0 Prototype: Basic idempotency check.
        If chapter has content and status is 'drafted', skip execution.
        """
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)
        
        try:
            content = self.repo.get_chapter_content(project_id, chapter_number)
            if content and len(content) > 100:
                status = self.repo.get_chapter_status(project_id, chapter_number)
                if status == "drafted":
                    return True
        except Exception:
            pass
        
        return False
    
    def _return_cached_result(self, state: FactoryState) -> NodeToolResult:
        """Return result indicating cached execution."""
        return NodeToolResult(
            updates={"chapter_status": "drafted", "from_cache": True},
            success=True,
            phase="cached",
            agent=self.AGENT_NAME,
        )
