"""Dispatcher — event-driven routing execution.

v6.10.13: Inspired by ainovel-cli's Dispatcher design.
Subscribes to workflow events and triggers routing decisions.
Tracks repeated instructions to detect potential loops.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Optional

from ..db.repository import Repository
from .flow_router import Instruction, RouterState, route
from .state_loader import StateLoader

logger = logging.getLogger(__name__)


class Dispatcher:
    """Event-driven dispatcher for routing decisions."""

    def __init__(
        self,
        repo: Repository,
        on_instruction: Optional[Callable[[Instruction], None]] = None,
        on_repeat: Optional[Callable[[str, str, int], None]] = None,
    ):
        self.repo = repo
        self.state_loader = StateLoader(repo)
        self.on_instruction = on_instruction
        self.on_repeat = on_repeat

        # Repeat tracking
        self._repeat_counts: dict[str, int] = defaultdict(int)
        self._last_instruction: Optional[Instruction] = None
        self._last_dispatch_time: float = 0

        # State
        self._enabled = False
        self._project_id: Optional[str] = None
        self._lock = threading.Lock()

    def enable(self, project_id: str) -> None:
        """Enable dispatcher for a project."""
        with self._lock:
            self._enabled = True
            self._project_id = project_id
            self._repeat_counts.clear()
            self._last_instruction = None
            self._last_dispatch_time = 0

    def disable(self) -> None:
        """Disable dispatcher."""
        with self._lock:
            self._enabled = False
            self._project_id = None

    def reset_repeat(self) -> None:
        """Reset repeat tracking."""
        with self._lock:
            self._repeat_counts.clear()
            self._last_instruction = None

    def dispatch(self) -> Optional[Instruction]:
        """Dispatch routing decision based on current state.

        Returns the instruction if one was generated, None otherwise.
        """
        with self._lock:
            if not self._enabled or not self._project_id:
                return None

            project_id = self._project_id

        try:
            # Load state
            state = self.state_loader.load(project_id)

            # Route
            instruction = route(state)

            if instruction:
                # Track repeats
                self._track_repeat(instruction)

                # Notify
                if self.on_instruction:
                    self.on_instruction(instruction)

                logger.info(
                    "Dispatcher: action=%s chapter=%d reason=%s",
                    instruction.action.value,
                    instruction.chapter,
                    instruction.reason,
                )

            self._last_instruction = instruction
            self._last_dispatch_time = time.time()

            return instruction

        except Exception as e:
            logger.error("Dispatcher: dispatch failed: %s", e)
            return None

    def _track_repeat(self, instruction: Instruction) -> None:
        """Track repeated instructions."""
        key = f"{instruction.action.value}:{instruction.chapter}"

        with self._lock:
            self._repeat_counts[key] += 1
            count = self._repeat_counts[key]

            # Notify if repeated
            if count > 1 and self.on_repeat:
                self.on_repeat(
                    instruction.agent or "system",
                    instruction.task,
                    count,
                )

                logger.warning(
                    "Dispatcher: repeated instruction %d times: %s",
                    count,
                    key,
                )

    def get_repeat_counts(self) -> dict[str, int]:
        """Get current repeat counts."""
        with self._lock:
            return dict(self._repeat_counts)

    def get_last_instruction(self) -> Optional[Instruction]:
        """Get last dispatched instruction."""
        with self._lock:
            return self._last_instruction

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get current state snapshot for debugging."""
        with self._lock:
            if not self._enabled or not self._project_id:
                return {"enabled": False}

            project_id = self._project_id

        try:
            state = self.state_loader.load(project_id)
            return {
                "enabled": True,
                "project_id": project_id,
                "phase": state.phase,
                "flow": state.flow,
                "current_chapter": state.current_chapter,
                "total_chapters": state.total_chapters,
                "completed_count": len(state.completed_chapters or []),
                "pending_rewrites": len(state.pending_rewrites or []),
                "pending_reviews": len(state.pending_reviews or []),
                "pending_memory": len(state.pending_memory_updates or []),
                "pending_steer": state.pending_steer is not None,
                "layered": state.layered,
                "is_arc_end": state.is_arc_end,
                "repeat_counts": dict(self._repeat_counts),
            }
        except Exception as e:
            return {"enabled": True, "error": str(e)}


class AutoDispatcher:
    """Auto-dispatcher that runs on a timer or after events."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        interval_seconds: float = 5.0,
    ):
        self.dispatcher = dispatcher
        self.interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start auto-dispatch loop."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="auto-dispatcher",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop auto-dispatch loop."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 2)
            self._thread = None

    def _loop(self) -> None:
        """Auto-dispatch loop."""
        while self._running and not self._stop_event.is_set():
            try:
                self.dispatcher.dispatch()
            except Exception as e:
                logger.error("AutoDispatcher: dispatch failed: %s", e)

            self._stop_event.wait(self.interval)
