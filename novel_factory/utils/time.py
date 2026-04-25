"""Time utilities for timeout detection.

v1.1 provides helper for computing time thresholds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def timeout_threshold(timeout_minutes: int) -> str:
    """Compute the datetime string before which a task is considered timed out.

    Returns an ISO-format datetime string in UTC+8.
    """
    cutoff = datetime.now(tz=timezone(timedelta(hours=8))) - timedelta(minutes=timeout_minutes)
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")
