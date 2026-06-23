"""Notifier — unattended alert notification system.

v6.10.13: Inspired by ainovel-cli's Notifier design.
Sends notifications via custom command or system notification.
Pure observation layer — never intervenes in control flow.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """Notification message."""

    kind: str  # "run_end", "budget", "repeat", "memory", "steer"
    level: str  # "info", "warn", "error"
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


class Notifier:
    """Unattended alert notification system.

    Features:
    - Custom command support (e.g., curl webhook)
    - System notification (macOS/Linux)
    - Event filtering
    - Async non-blocking
    """

    def __init__(
        self,
        command: Optional[str] = None,
        events: Optional[list[str]] = None,
        on_notification: Optional[Callable[[Notification], None]] = None,
    ):
        self.command = command
        self.events = events  # None = all events
        self.on_notification = on_notification
        self._lock = threading.Lock()

    def send(self, notification: Notification) -> None:
        """Send notification asynchronously.

        Args:
            notification: Notification to send.
        """
        # Filter events
        if self.events and notification.kind not in self.events:
            return

        # Callback
        if self.on_notification:
            try:
                self.on_notification(notification)
            except Exception as e:
                logger.warning("Notifier: callback failed: %s", e)

        # Async send
        thread = threading.Thread(
            target=self._send_impl,
            args=(notification,),
            daemon=True,
            name=f"notify-{notification.kind}",
        )
        thread.start()

    def _send_impl(self, notification: Notification) -> None:
        """Send implementation."""
        try:
            if self.command:
                self._send_command(notification)
            else:
                self._send_system(notification)
        except Exception as e:
            logger.warning("Notifier: send failed: %s", e)

    def _send_command(self, notification: Notification) -> None:
        """Send via custom command."""
        env = {
            **os.environ,
            "NOTIFY_KIND": notification.kind,
            "NOTIFY_LEVEL": notification.level,
            "NOTIFY_TITLE": notification.title,
            "NOTIFY_BODY": notification.body,
        }

        try:
            result = subprocess.run(
                self.command,
                shell=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "Notifier: command failed (exit %d): %s",
                    result.returncode,
                    result.stderr[:200],
                )
        except subprocess.TimeoutExpired:
            logger.warning("Notifier: command timeout")
        except Exception as e:
            logger.warning("Notifier: command error: %s", e)

    def _send_system(self, notification: Notification) -> None:
        """Send via system notification."""
        import platform

        system = platform.system()

        if system == "Darwin":
            self._send_macos(notification)
        elif system == "Linux":
            self._send_linux(notification)
        else:
            # Fallback: just log
            logger.info(
                "Notifier [%s/%s]: %s - %s",
                notification.kind,
                notification.level,
                notification.title,
                notification.body,
            )

    def _send_macos(self, notification: Notification) -> None:
        """Send macOS notification."""
        script = (
            f'display notification "{notification.body}" '
            f'with title "{notification.title}" '
            f'subtitle "Novelos [{notification.kind}]"'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
        except Exception as e:
            logger.debug("Notifier: macOS notification failed: %s", e)

    def _send_linux(self, notification: Notification) -> None:
        """Send Linux notification."""
        try:
            subprocess.run(
                [
                    "notify-send",
                    f"[{notification.kind}] {notification.title}",
                    notification.body,
                    "--urgency=normal",
                ],
                capture_output=True,
                timeout=5,
            )
        except Exception as e:
            logger.debug("Notifier: Linux notification failed: %s", e)


# ── Convenience functions ──

_default_notifier: Optional[Notifier] = None


def get_notifier() -> Optional[Notifier]:
    """Get default notifier instance."""
    return _default_notifier


def set_notifier(notifier: Notifier) -> None:
    """Set default notifier instance."""
    global _default_notifier
    _default_notifier = notifier


def send_notification(notification: Notification) -> None:
    """Send notification via default notifier."""
    notifier = get_notifier()
    if notifier:
        notifier.send(notification)


def notify_run_end(
    novel_name: str,
    summary: str,
    cost: float = 0.0,
    level: str = "info",
) -> None:
    """Send run end notification."""
    body = summary
    if novel_name:
        body = f"《{novel_name}》{summary}"
    if cost > 0:
        body += f" · 花费 ${cost:.2f}"

    send_notification(Notification(
        kind="run_end",
        level=level,
        title="Novelos: 创作完成" if level == "info" else "Novelos: 创作停止",
        body=body,
    ))


def notify_budget(level: str, message: str) -> None:
    """Send budget notification."""
    send_notification(Notification(
        kind="budget",
        level=level,
        title="Novelos: 预算",
        body=message,
    ))


def notify_repeat(agent: str, task: str, count: int) -> None:
    """Send repeat warning notification."""
    send_notification(Notification(
        kind="repeat",
        level="warn",
        title="Novelos: 指令重复",
        body=f"同一指令已第 {count} 次下达（{agent}）：{task}",
    ))


def notify_memory_pending(count: int) -> None:
    """Send memory pending notification."""
    send_notification(Notification(
        kind="memory",
        level="info",
        title="Novelos: 记忆更新",
        body=f"有 {count} 个待处理的记忆更新",
    ))
