"""Base Agent class for Novel Factory.

All agents inherit from BaseAgent and implement build_context, run, validate_output.
v6.0: BaseAgent now integrates role profiles, tool registry, decision trace,
and agent memory context in a backward-compatible way.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..db.repository import Repository
from ..llm.provider import LLMProvider
from ..models.state import FactoryState
from ..validators.state_verifier import check_status_precondition

logger = logging.getLogger(__name__)


class BaseAgent:
    """Abstract base for all Novel Factory agents.

    Subclasses must define:
    - agent_id: unique identifier
    - build_context(): assemble LLM context from FactoryState
    - _execute(): execute the agent's task (called by run template method)
    - validate_output(): validate structured output before writing to DB
    """

    agent_id: str = "base"
    use_self_check: bool = False
    context_char_limit: int = 14000

    def __init__(
        self,
        repo: Repository,
        llm: LLMProvider,
        skill_registry: Any | None = None,
        tool_registry: Any | None = None,
        trace_store: Any | None = None,
    ) -> None:
        self.repo = repo
        self.llm = llm
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.trace_store = trace_store
        self._role_profile: Any | None = None
        self._load_role_profile()

    def _load_role_profile(self) -> None:
        """v6.0: Load declarative role profile for this agent."""
        try:
            from .role_profile import get_role_profile
            self._role_profile = get_role_profile(self.agent_id)
            if self._role_profile:
                logger.debug("Loaded role profile for %s", self.agent_id)
        except Exception:
            logger.debug("Role profile load failed for %s", self.agent_id, exc_info=True)

    def _invoke_json(self, messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
        """Invoke LLM with JSON output, passing agent_id if the provider accepts it.

        v6.6.21-review: Wrapper that gracefully handles providers (including
        test fakes) that don't yet accept agent_id in invoke_json().
        If the provider raises TypeError for agent_id, retries without it.
        """
        # Try with agent_id first
        try:
            return self.llm.invoke_json(messages, agent_id=self.agent_id, **kwargs)
        except TypeError as e:
            if "agent_id" in str(e):
                # Provider doesn't accept agent_id (e.g. test fakes), retry without
                kwargs.pop("agent_id", None)
                return self.llm.invoke_json(messages, **kwargs)
            raise

    def _get_role_profile_context(self) -> str:
        """v6.0: Return role profile mission/context for prompt injection."""
        if not self._role_profile:
            return ""
        parts = [f"【角色目标】{self._role_profile.mission}"]
        if self._role_profile.success_criteria:
            parts.append("【成功标准】" + "; ".join(self._role_profile.success_criteria[:3]))
        if self._role_profile.cannot_do:
            parts.append("【禁止事项】" + "; ".join(self._role_profile.cannot_do[:3]))
        return "\n".join(parts)

    def _get_agent_memory_context(self, project_id: str) -> str:
        """v6.0: Query enabled agent memories and inject relevant notes."""
        try:
            items = self.repo.list_agent_memories(
                project_id=project_id,
                agent_id=self.agent_id,
                enabled_only=True,
            )
        except Exception:
            logger.debug("Agent memory query failed for %s", self.agent_id, exc_info=True)
            return ""
        if not items:
            return ""
        lines = ["【Agent 记忆】"]
        for item in items[:5]:
            key = item.get("key", "")
            value = item.get("value", {})
            note = value.get("note") or value.get("content") or str(value)[:120]
            lines.append(f"- {key}: {note}")
        return "\n".join(lines)

    @staticmethod
    def _limit_context_size(context: str, limit: int, *, agent_id: str = "agent") -> str:
        """Bound prompt context while preserving task head and late constraints."""
        text = str(context or "")
        if limit <= 0 or len(text) <= limit:
            return text
        marker = "\n\n【上下文已截断】中间资料过长，已保留开头任务要求和末尾约束信息。\n\n"
        head_len = max(0, int(limit * 0.7) - len(marker))
        tail_len = max(0, limit - head_len - len(marker))
        logger.warning(
            "%s context truncated from %d to %d chars",
            agent_id,
            len(text),
            limit,
        )
        return f"{text[:head_len]}{marker}{text[-tail_len:]}"

    def _build_v6_context(self, state: FactoryState) -> str:
        """v6.0: Assemble enhanced context with role profile and memory."""
        parts = []
        role_ctx = self._get_role_profile_context()
        if role_ctx:
            parts.append(role_ctx)
        mem_ctx = self._get_agent_memory_context(state.get("project_id", ""))
        if mem_ctx:
            parts.append(mem_ctx)
        base_ctx = self.build_context(state)
        if base_ctx:
            parts.append(base_ctx)
        return self._limit_context_size(
            "\n\n".join(parts),
            self.context_char_limit,
            agent_id=self.agent_id,
        )

    def build_context(self, state: FactoryState) -> str:
        """Build the LLM prompt context from the current workflow state.

        Override in subclasses to customize context per agent.
        """
        return ""

    def validate_output(self, output: dict) -> None:
        """Validate agent output against its schema.

        Raises ValueError if output is invalid.
        Override in subclasses.
        """
        pass

    def check_precondition(self, state: FactoryState) -> None:
        """Check chapter status precondition before writing.

        Reads DB current status as source of truth. If DB status differs
        from FactoryState, raises ValueError to prevent stale writes.

        Raises ValueError if the current chapter status does not allow
        this agent to write.
        """
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)

        # Read DB status as source of truth
        db_status = self.repo.get_chapter_status(project_id, chapter_number)
        if not db_status:
            raise ValueError(
                f"Agent '{self.agent_id}' precondition failed: chapter not found in DB"
            )

        state_status = state.get("chapter_status", "")
        if db_status != state_status:
            raise ValueError(
                f"Agent '{self.agent_id}' precondition failed: "
                f"DB status '{db_status}' != state status '{state_status}'. "
                f"Stale state, refusing to write."
            )

        violations = check_status_precondition(self.agent_id, db_status)
        if violations:
            raise ValueError(
                f"Agent '{self.agent_id}' precondition failed: {'; '.join(violations)}"
            )

    def _record_trace(
        self,
        state: FactoryState,
        stage: str,
        input_summary: str = "",
        capability_packs: list[str] | None = None,
        skill_results: list[dict[str, Any]] | None = None,
        self_check: dict[str, Any] | None = None,
        autonomy_decision: dict[str, Any] | None = None,
        repair_attempts: list[dict[str, Any]] | None = None,
        contract_validation: dict[str, Any] | None = None,
        token_count: int = 0,
        latency_ms: int = 0,
    ) -> None:
        """v6.0: Best-effort save a decision trace. Never raises."""
        if self.trace_store is None:
            return
        try:
            from .decision_trace import AgentDecisionTrace
            trace = AgentDecisionTrace(
                run_id=state.get("workflow_run_id", ""),
                project_id=state.get("project_id", ""),
                chapter_number=state.get("chapter_number", 0),
                agent_id=self.agent_id,
                stage=stage,
                role_profile_id=self._role_profile.agent_id if self._role_profile else self.agent_id,
                input_summary=input_summary,
                capability_packs=capability_packs or [],
                skill_results=skill_results or [],
                self_check=self_check or {},
                autonomy_decision=autonomy_decision or {},
                repair_attempts=repair_attempts or [],
                contract_validation=contract_validation or {},
                token_count=token_count,
                latency_ms=latency_ms,
            )
            self.trace_store.save(trace)
        except Exception:
            logger.debug("Trace save failed for %s", self.agent_id, exc_info=True)

    def run(self, state: FactoryState) -> dict[str, Any]:
        """Execute the agent's core logic with precondition and validation guards.

        Returns a dict of updates to merge into FactoryState.
        Must NOT mutate state directly.

        Subclasses should override _execute() instead of this method.
        """
        started_at = time.perf_counter()
        input_summary = f"project={state.get('project_id')} chapter={state.get('chapter_number')} status={state.get('chapter_status')}"
        try:
            self.check_precondition(state)
            result = self._execute(state)
        except ValueError as e:
            message = str(e)
            logger.error("Agent '%s' validation failed: %s", self.agent_id, message)
            if "死刑红线" in message:
                result = {
                    "error": message,
                    "chapter_status": state.get("chapter_status"),
                    "quality_gate": {
                        "pass": False,
                        "revision_target": self.agent_id if self.agent_id in ("author", "polisher") else "author",
                        "death_penalty_fail": True,
                        "message": message,
                        "agent": self.agent_id,
                        "workflow_run_id": state.get("workflow_run_id"),
                    },
                }
            else:
                result = {"error": message, "chapter_status": state.get("chapter_status")}
        except Exception as e:
            logger.exception("Agent '%s' execution failed", self.agent_id)
            result = {"error": str(e), "chapter_status": state.get("chapter_status")}

        latency_ms = int((time.perf_counter() - started_at) * 1000)

        # v6.0: Attach trace and autonomy metadata (best-effort)
        trace_payload = result.get("_trace")
        autonomy = result.get("_autonomy")
        self._record_trace(
            state=state,
            stage="execute",
            input_summary=input_summary,
            self_check=trace_payload.get("self_check") if isinstance(trace_payload, dict) else None,
            autonomy_decision=autonomy,
            repair_attempts=trace_payload.get("repair_attempts") if isinstance(trace_payload, dict) else None,
            token_count=result.get("total_tokens", 0),
            latency_ms=latency_ms,
        )

        return result

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        """Internal execution method. Subclasses must implement this."""
        raise NotImplementedError

    def _compensate_status(
        self, project_id: str, chapter_number: int,
        current_status: str, target_status: str,
    ) -> None:
        """Roll back chapter status after a write failure.

        Best-effort: uses expected_status guard so it only rolls back if
        the status is still ``current_status``.  Logs a warning if the
        compensation itself fails.
        """
        try:
            self.repo.update_chapter_status(
                project_id, chapter_number, target_status,
                expected_status=current_status,
            )
        except Exception:
            logger.warning(
                "Failed to compensate status %s->%s for %s/%s",
                current_status, target_status, project_id, chapter_number,
                exc_info=True,
            )

    def _get_chapter_info(self, state: FactoryState) -> dict | None:
        """Helper: get current chapter from DB."""
        return self.repo.get_chapter(state["project_id"], state["chapter_number"])

    def _get_instruction(self, state: FactoryState) -> dict | None:
        """Helper: get instruction for current chapter."""
        return self.repo.get_instruction(state["project_id"], state["chapter_number"])

    def _get_scene_beats(self, state: FactoryState) -> list[dict]:
        """Helper: get scene beats for current chapter."""
        return self.repo.get_scene_beats(state["project_id"], state["chapter_number"])

    def _get_prev_state_card(self, state: FactoryState) -> dict | None:
        """Helper: get previous chapter's state card."""
        prev_ch = state["chapter_number"] - 1
        if prev_ch < 1:
            return None
        return self.repo.get_chapter_state(state["project_id"], prev_ch)

    def _get_style_bible_context(self, project_id: str, agent_id: str) -> str:
        """Helper: get Style Bible context for a specific agent (v4.0).

        Returns an empty string if no Style Bible exists for the project.
        Silently returns "" on any error (never blocks the main flow).
        """
        try:
            from ..style_bible.loader import get_style_context_for_agent
            return get_style_context_for_agent(project_id, agent_id, self.repo)
        except Exception:
            logger.debug("Style bible context load failed for %s", agent_id, exc_info=True)
            return ""

    def _get_title_contract_context(self, project_id: str) -> str:
        """Helper: get title-promise constraints for generation prompts."""
        try:
            from .title_contract import build_title_contract
            project = self.repo.get_project(project_id)
            return build_title_contract(project)
        except Exception:
            logger.debug("Title contract build failed for %s", project_id, exc_info=True)
            return ""

    def _get_style_prompt_injection(self, project_id: str, agent_id: str) -> str:
        """v6.8.1: Return style-aware prompt injection for this agent.

        Detects style from project metadata (title, genre, premise) and returns
        agent-specific style instructions. Returns "" if no style applies or
        on any error (never blocks the main flow).
        """
        try:
            from ..quality.style_detector import detect_style_from_text, get_style_prompt_injection
            project = self.repo.get_project(project_id)
            if not project:
                return ""
            text = " ".join(filter(None, [
                project.get("name", ""),  # 项目名称
                project.get("genre", ""),  # 类型
                project.get("description", ""),  # 项目描述
            ]))
            if not text.strip():
                return ""
            profile = detect_style_from_text(text)
            return get_style_prompt_injection(profile, agent_id)
        except Exception:
            logger.debug("Style prompt injection failed for %s/%s", project_id, agent_id, exc_info=True)
            return ""

    def _get_project_skill_overrides(self, project_id: str) -> dict[str, Any]:
        """Helper: get project-specific skill override document.

        Returns an empty override doc when none exists or when loading fails.
        """
        try:
            record = self.repo.get_project_skill_overrides(project_id)
            if not isinstance(record, dict):
                return {}
            overrides = record.get("overrides", {})
            return overrides if isinstance(overrides, dict) else {}
        except Exception:
            logger.debug("Project skill overrides load failed for %s", project_id, exc_info=True)
            return {}
