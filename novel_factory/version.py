"""Single source of truth for Novelos runtime version."""

from __future__ import annotations

__version__: str = "6.10.12"


def get_version() -> str:
    """Return the current runtime version string."""
    return __version__
