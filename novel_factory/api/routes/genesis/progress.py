"""Genesis progress streaming — SSE support for real-time progress updates.

v6.7.7: In-memory progress store for SSE streaming during genesis generation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)

GENESIS_RUNNING_TIMEOUT_MINUTES = 30

# Maps run_id -> asyncio.Queue for SSE streaming
_genesis_progress_queues: dict[str, asyncio.Queue] = {}

# Expose for backward compatibility (tests may need direct access)
__all__ = ['_genesis_progress_queues']

# Segment display names for UI
GENESIS_SEGMENT_LABELS = {
    "foundation": "正在生成基础设定",
    "cast": "正在生成角色与势力",
    "plot": "正在生成剧情大纲",
    "instructions": "正在生成章节指令",
    "repair": "正在校验设定完整性",
    "quality_report": "正在评估草案质量",
}

GENESIS_REQUIRED_SECTIONS = {
    "project_description": "项目简介",
    "world_settings": "世界观设定",
    "characters": "角色",
    "factions": "势力/组织",
    "outlines": "大纲",
    "plot_holes": "伏笔/悬念",
    "instructions": "章节指令",
}

GENESIS_SEGMENT_MAX_TOKENS = {
    "foundation": 2400,
    "cast": 3000,
    "plot": 3200,
}
GENESIS_INSTRUCTION_CHUNK_SIZE = 5

GENESIS_REPAIRABLE_INSTRUCTION_CODES = {
    "ABSTRACT_OBJECTIVE",
    "GENERIC_INSTRUCTIONS",
    "MISSING_CONTINUITY_SEED",
    "REPETITIVE_KEY_EVENTS",
    "REPETITIVE_OBJECTIVE",
    "SHALLOW_INSTRUCTION",
    "WEAK_KEY_EVENTS",
}


def _push_progress(run_id: str, event: dict) -> None:
    """Push a progress event to the SSE queue for a given run."""
    queue = _genesis_progress_queues.get(run_id)
    if queue is not None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Genesis progress queue full for run %s, dropping event", run_id)


def _make_progress_event(event_type: str, run_id: str, **kwargs) -> dict:
    """Build a standard progress event dict."""
    evt = {"event": event_type, "data": {"run_id": run_id, **kwargs}}
    return evt


# Type alias for progress callback
ProgressCallback = "Callable[[str, dict], None] | None"


def get_progress_queue(run_id: str) -> asyncio.Queue | None:
    """Get the progress queue for a run."""
    return _genesis_progress_queues.get(run_id)


def create_progress_queue(run_id: str, maxsize: int = 500) -> asyncio.Queue:
    """Create a new progress queue for a run."""
    queue = asyncio.Queue(maxsize=maxsize)
    _genesis_progress_queues[run_id] = queue
    return queue


def remove_progress_queue(run_id: str) -> None:
    """Remove the progress queue for a run."""
    _genesis_progress_queues.pop(run_id, None)