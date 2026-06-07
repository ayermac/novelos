"""v6.10.0: In-memory event queue for real-time SSE streaming.

Replaces DB polling with push-based event delivery.
Thread-safe: workflow writes events from sync thread, SSE reads from async thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class EventQueue:
    """Thread-safe event queue for a single workflow run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._events: list[dict[str, Any]] = []
        self._event_id_counter = 0
        self._lock = threading.Lock()
        self._subscribers: list[asyncio.Queue] = []
        self._done = False
        self._done_status: str | None = None
        self._created_at = time.time()

    def push(self, event: dict[str, Any]) -> int:
        """Push an event to the queue (called from workflow thread)."""
        with self._lock:
            self._event_id_counter += 1
            event["id"] = self._event_id_counter
            self._events.append(event)

            # Notify all subscribers
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # Drop if subscriber is too slow

            return self._event_id_counter

    def mark_done(self, status: str = "completed") -> None:
        """Mark the run as done (called from workflow thread)."""
        with self._lock:
            self._done = True
            self._done_status = status
            # Notify subscribers
            done_event = {"type": "done", "status": status}
            for q in self._subscribers:
                try:
                    q.put_nowait(done_event)
                except asyncio.QueueFull:
                    pass

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to new events (called from async SSE thread)."""
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        with self._lock:
            self._subscribers.append(q)
            # Replay existing events to new subscriber
            for ev in self._events:
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    break
            # If already done, send done event
            if self._done:
                try:
                    q.put_nowait({"type": "done", "status": self._done_status})
                except asyncio.QueueFull:
                    pass
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribe from events."""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def get_events_since(self, since_id: int = 0) -> list[dict[str, Any]]:
        """Get all events after the given ID."""
        with self._lock:
            return [ev for ev in self._events if ev.get("id", 0) > since_id]

    @property
    def is_done(self) -> bool:
        with self._lock:
            return self._done

    @property
    def age_seconds(self) -> float:
        return time.time() - self._created_at


class EventQueueManager:
    """Global manager for workflow event queues."""

    def __init__(self, max_queues: int = 50, max_age_seconds: int = 3600):
        self._queues: dict[str, EventQueue] = {}
        self._lock = threading.Lock()
        self._max_queues = max_queues
        self._max_age_seconds = max_age_seconds

    def get_or_create(self, run_id: str) -> EventQueue:
        """Get or create an event queue for a run."""
        with self._lock:
            self._cleanup()
            if run_id not in self._queues:
                self._queues[run_id] = EventQueue(run_id)
            return self._queues[run_id]

    def get(self, run_id: str) -> EventQueue | None:
        """Get an existing event queue."""
        with self._lock:
            return self._queues.get(run_id)

    def _cleanup(self) -> None:
        """Remove old or excess queues."""
        # Remove by age
        to_remove = [
            rid for rid, q in self._queues.items()
            if q.age_seconds > self._max_age_seconds
        ]
        for rid in to_remove:
            del self._queues[rid]

        # Remove by count (oldest first)
        if len(self._queues) > self._max_queues:
            sorted_ids = sorted(
                self._queues.keys(),
                key=lambda rid: self._queues[rid]._created_at,
            )
            for rid in sorted_ids[:len(self._queues) - self._max_queues]:
                del self._queues[rid]


# Global singleton
_event_queue_manager = EventQueueManager()


def get_event_queue_manager() -> EventQueueManager:
    return _event_queue_manager
