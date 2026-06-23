"""SignalStore — one-time signal files for cross-session recovery.

v6.10.13: Inspired by ainovel-cli's Signal mechanism.
Manages pending state signals that survive process restarts.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SignalStore:
    """Manage one-time signal files for pending state."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.signals_dir = self.base_dir / "signals"
        self._lock = threading.Lock()

        # Ensure signals directory exists
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    # ── Pending Commit ──

    def save_pending_commit(
        self, project_id: str, chapter: int, data: dict[str, Any]
    ) -> None:
        """Save pending commit state."""
        self._write_signal(
            project_id,
            "pending_commit.json",
            {
                "chapter_number": chapter,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def load_pending_commit(self, project_id: str) -> Optional[dict[str, Any]]:
        """Load pending commit state."""
        return self._read_signal(project_id, "pending_commit.json")

    def clear_pending_commit(self, project_id: str) -> None:
        """Clear pending commit state."""
        self._remove_signal(project_id, "pending_commit.json")

    # ── Pending Review ──

    def save_pending_review(
        self, project_id: str, chapter: int, review: dict[str, Any]
    ) -> None:
        """Save pending review result."""
        self._write_signal(
            project_id,
            "pending_review.json",
            {
                "chapter_number": chapter,
                "review": review,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def load_pending_review(self, project_id: str) -> Optional[dict[str, Any]]:
        """Load pending review result."""
        return self._read_signal(project_id, "pending_review.json")

    def clear_pending_review(self, project_id: str) -> None:
        """Clear pending review result."""
        self._remove_signal(project_id, "pending_review.json")

    # ── Pending Memory ──

    def save_pending_memory(
        self, project_id: str, batch_id: str, summary: str
    ) -> None:
        """Save pending memory update."""
        self._write_signal(
            project_id,
            "pending_memory.json",
            {
                "batch_id": batch_id,
                "summary": summary,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def load_pending_memory(self, project_id: str) -> Optional[dict[str, Any]]:
        """Load pending memory update."""
        return self._read_signal(project_id, "pending_memory.json")

    def clear_pending_memory(self, project_id: str) -> None:
        """Clear pending memory update."""
        self._remove_signal(project_id, "pending_memory.json")

    # ── Pending Steer ──

    def save_pending_steer(self, project_id: str, text: str) -> None:
        """Save pending user intervention."""
        self._write_signal(
            project_id,
            "pending_steer.json",
            {
                "text": text,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def load_pending_steer(self, project_id: str) -> Optional[str]:
        """Load pending user intervention text."""
        data = self._read_signal(project_id, "pending_steer.json")
        if data:
            return data.get("text")
        return None

    def clear_pending_steer(self, project_id: str) -> None:
        """Clear pending user intervention."""
        self._remove_signal(project_id, "pending_steer.json")

    # ── Cleanup ──

    def clear_stale_signals(self, project_id: str) -> None:
        """Clear stale signal files on process restart.

        Called on startup to clean up signals from previous session
        that may have been left due to crash.
        """
        with self._lock:
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                return

            for signal_file in project_dir.glob("*.json"):
                try:
                    signal_file.unlink()
                    logger.info(
                        "SignalStore: cleared stale signal %s",
                        signal_file.name,
                    )
                except Exception as e:
                    logger.warning(
                        "SignalStore: failed to clear %s: %s",
                        signal_file.name,
                        e,
                    )

    def clear_all_signals(self, project_id: str) -> None:
        """Clear all signal files for a project."""
        self.clear_stale_signals(project_id)

    def list_signals(self, project_id: str) -> list[str]:
        """List all active signal files for a project."""
        with self._lock:
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                return []

            return [f.stem for f in project_dir.glob("*.json")]

    # ── Internal ──

    def _project_dir(self, project_id: str) -> Path:
        """Get project signals directory."""
        return self.signals_dir / project_id

    def _signal_path(self, project_id: str, filename: str) -> Path:
        """Get signal file path."""
        return self._project_dir(project_id) / filename

    def _write_signal(
        self, project_id: str, filename: str, data: dict[str, Any]
    ) -> None:
        """Write signal file atomically."""
        with self._lock:
            project_dir = self._project_dir(project_id)
            project_dir.mkdir(parents=True, exist_ok=True)

            signal_path = self._signal_path(project_id, filename)
            temp_path = signal_path.with_suffix(".tmp")

            try:
                # Write to temp file first
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # Atomic rename
                temp_path.rename(signal_path)

                logger.debug(
                    "SignalStore: saved %s for %s",
                    filename,
                    project_id,
                )
            except Exception as e:
                logger.error(
                    "SignalStore: failed to save %s: %s",
                    filename,
                    e,
                )
                # Clean up temp file
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise

    def _read_signal(
        self, project_id: str, filename: str
    ) -> Optional[dict[str, Any]]:
        """Read signal file."""
        with self._lock:
            signal_path = self._signal_path(project_id, filename)
            if not signal_path.exists():
                return None

            try:
                with open(signal_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(
                    "SignalStore: failed to read %s: %s",
                    filename,
                    e,
                )
                return None

    def _remove_signal(self, project_id: str, filename: str) -> None:
        """Remove signal file."""
        with self._lock:
            signal_path = self._signal_path(project_id, filename)
            if signal_path.exists():
                try:
                    signal_path.unlink()
                    logger.debug(
                        "SignalStore: cleared %s for %s",
                        filename,
                        project_id,
                    )
                except Exception as e:
                    logger.warning(
                        "SignalStore: failed to clear %s: %s",
                        filename,
                        e,
                    )
