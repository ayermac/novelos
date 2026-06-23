"""Flow Integration — integrate FlowRouter with LangGraph workflow.

v6.10.13: Connects deterministic routing with LangGraph state machine.
Provides flow_control_node that uses FlowRouter for routing decisions.
"""

from __future__ import annotations

import logging
from typing import Any

from ..dispatch.flow_router import FlowAction, Instruction, RouterState, route
from ..dispatch.signal_store import SignalStore
from ..dispatch.state_loader import StateLoader
from ..db.repository import Repository
from ..models.state import FactoryState

logger = logging.getLogger(__name__)


class FlowIntegration:
    """Integration layer between FlowRouter and LangGraph workflow."""

    def __init__(self, repo: Repository, signal_store: SignalStore | None = None):
        self.repo = repo
        self.signal_store = signal_store
        self.state_loader = StateLoader(repo)

    def load_router_state(self, project_id: str) -> RouterState:
        """Load RouterState for FlowRouter."""
        return self.state_loader.load(project_id)

    def get_routing_instruction(
        self, project_id: str
    ) -> Instruction | None:
        """Get routing instruction from FlowRouter."""
        state = self.load_router_state(project_id)
        return route(state)

    def apply_instruction_to_state(
        self,
        state: FactoryState,
        instruction: Instruction,
    ) -> FactoryState:
        """Apply FlowRouter instruction to FactoryState.

        This updates the state with routing information.
        """
        if not instruction:
            return state

        # Add routing info to state
        state["_flow_action"] = instruction.action.value
        state["_flow_chapter"] = instruction.chapter
        state["_flow_agent"] = instruction.agent
        state["_flow_task"] = instruction.task
        state["_flow_reason"] = instruction.reason

        return state

    def check_pending_signals(self, project_id: str) -> dict[str, Any]:
        """Check for pending signals that need processing."""
        signals = {}

        if self.signal_store:
            # Check pending commit
            pending_commit = self.signal_store.load_pending_commit(project_id)
            if pending_commit:
                signals["pending_commit"] = pending_commit

            # Check pending review
            pending_review = self.signal_store.load_pending_review(project_id)
            if pending_review:
                signals["pending_review"] = pending_review

            # Check pending memory
            pending_memory = self.signal_store.load_pending_memory(project_id)
            if pending_memory:
                signals["pending_memory"] = pending_memory

            # Check pending steer
            pending_steer = self.signal_store.load_pending_steer(project_id)
            if pending_steer:
                signals["pending_steer"] = pending_steer

        return signals

    def clear_handled_signal(
        self,
        project_id: str,
        signal_type: str,
    ) -> None:
        """Clear a signal after it's been handled."""
        if not self.signal_store:
            return

        if signal_type == "pending_commit":
            self.signal_store.clear_pending_commit(project_id)
        elif signal_type == "pending_review":
            self.signal_store.clear_pending_review(project_id)
        elif signal_type == "pending_memory":
            self.signal_store.clear_pending_memory(project_id)
        elif signal_type == "pending_steer":
            self.signal_store.clear_pending_steer(project_id)


def flow_control_node(
    state: FactoryState,
    repo: Repository,
    signal_store: SignalStore | None = None,
) -> dict[str, Any]:
    """Flow control node for LangGraph workflow.

    This node uses FlowRouter to determine the next step.
    It should be placed before task_discovery to override routing.
    """
    project_id = state.get("project_id", "")
    if not project_id:
        return {}

    integration = FlowIntegration(repo, signal_store)

    # Check for pending signals first
    signals = integration.check_pending_signals(project_id)

    # Get routing instruction
    instruction = integration.get_routing_instruction(project_id)

    if instruction:
        logger.info(
            "FlowControl: action=%s chapter=%d reason=%s",
            instruction.action.value,
            instruction.chapter,
            instruction.reason,
        )

        # Apply instruction to state
        return integration.apply_instruction_to_state(state, instruction)

    # No instruction, let LangGraph handle routing
    return {}


def create_flow_control_node(
    repo: Repository,
    signal_store: SignalStore | None = None,
):
    """Create a flow control node function for LangGraph."""

    def node(state: FactoryState) -> dict[str, Any]:
        return flow_control_node(state, repo, signal_store)

    return node
