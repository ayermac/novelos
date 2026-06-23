"""SteerManager — user intervention management.

v6.10.13: Inspired by ainovel-cli's Steer mechanism.
Handles user interventions during runtime and across sessions.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class SteerManager:
    """User intervention management.

    Three temporal modes:
    1. Runtime injection: inject while workflow is running
    2. Offline persistence: save when workflow is stopped
    3. Resume re-injection: re-inject on next startup
    """

    def __init__(
        self,
        repo: Any,
        signal_store: Any = None,
        on_inject: Optional[Callable[[str, str], None]] = None,
    ):
        self.repo = repo
        self.signal_store = signal_store
        self.on_inject = on_inject
        self._lock = threading.Lock()

    def steer(
        self,
        project_id: str,
        text: str,
        is_running: bool = False,
    ) -> dict[str, Any]:
        """Submit user intervention.

        Args:
            project_id: Project ID.
            text: Intervention text.
            is_running: Whether workflow is currently running.

        Returns:
            Result dict with status and message.
        """
        text = text.strip()
        if not text:
            return {"status": "error", "message": "干预内容不能为空"}

        formatted = f"[用户干预] {text}"

        with self._lock:
            if is_running:
                # Runtime injection
                if self.on_inject:
                    self.on_inject(project_id, formatted)

                # Record in history
                self._record_steer(project_id, text)

                logger.info("SteerManager: runtime injection for %s", project_id)
                return {
                    "status": "injected",
                    "message": "干预已注入到当前创作流程",
                }
            else:
                # Offline persistence
                if self.signal_store:
                    self.signal_store.save_pending_steer(project_id, text)
                else:
                    self._save_pending_steer(project_id, text)

                # Record in history
                self._record_steer(project_id, text)

                logger.info("SteerManager: saved pending steer for %s", project_id)
                return {
                    "status": "saved",
                    "message": "干预已保存，下次启动时生效",
                }

    def resume_with_steer(self, project_id: str) -> Optional[str]:
        """Check and load pending steer on resume.

        Returns:
            Formatted steer message if exists, None otherwise.
        """
        with self._lock:
            # Load from signal store
            text = None
            if self.signal_store:
                text = self.signal_store.load_pending_steer(project_id)
            else:
                text = self._load_pending_steer(project_id)

            if not text:
                return None

            # Clear pending steer
            if self.signal_store:
                self.signal_store.clear_pending_steer(project_id)
            else:
                self._clear_pending_steer(project_id)

            formatted = (
                f"用户在停机期间留下了一条干预意见：\n"
                f"「{text}」\n"
                f"请先按干预规则评估处理。"
            )

            logger.info("SteerManager: loaded pending steer for %s", project_id)
            return formatted

    def get_steer_history(
        self,
        project_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get steer history for a project."""
        try:
            return self.repo.get_steer_history(project_id, limit=limit)
        except Exception:
            return []

    def clear_pending(self, project_id: str) -> None:
        """Clear pending steer."""
        with self._lock:
            if self.signal_store:
                self.signal_store.clear_pending_steer(project_id)
            else:
                self._clear_pending_steer(project_id)

    def _record_steer(self, project_id: str, text: str) -> None:
        """Record steer in history."""
        try:
            self.repo.add_steer_entry(
                project_id,
                {
                    "text": text,
                    "timestamp": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning("SteerManager: failed to record steer: %s", e)

    def _save_pending_steer(self, project_id: str, text: str) -> None:
        """Save pending steer to database."""
        try:
            self.repo.save_pending_steer(project_id, text)
        except Exception as e:
            logger.error("SteerManager: failed to save pending steer: %s", e)

    def _load_pending_steer(self, project_id: str) -> Optional[str]:
        """Load pending steer from database."""
        try:
            return self.repo.load_pending_steer(project_id)
        except Exception:
            return None

    def _clear_pending_steer(self, project_id: str) -> None:
        """Clear pending steer from database."""
        try:
            self.repo.clear_pending_steer(project_id)
        except Exception as e:
            logger.warning("SteerManager: failed to clear pending steer: %s", e)
