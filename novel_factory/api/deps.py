"""API dependency utilities.

Provides shared dependencies for API routes:
- Repository access
- Settings access
- Dispatcher creation
- LLM mode detection
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request

from ..db.repository import Repository
from ..config.settings import Settings
from ..config.loader import load_settings_with_cli
from ..dispatcher import Dispatcher


def get_db_path(request: Request) -> str:
    """Get database path from app state or default."""
    return getattr(request.app.state, "db_path", None) or str(
        Path(__file__).parent.parent / "novel_factory.db"
    )


def get_config_path(request: Request) -> str | None:
    """Get config path from app state."""
    return getattr(request.app.state, "config_path", None)


def get_llm_mode(request: Request) -> str:
    """Get LLM mode from app state, defaults to 'stub'."""
    return getattr(request.app.state, "llm_mode", "stub")


def get_repo(request: Request) -> Repository:
    """Create a Repository instance for the current request."""
    db_path = get_db_path(request)
    return Repository(db_path)


def get_settings(request: Request) -> Settings:
    """Get Settings instance for API context."""
    config_path = get_config_path(request)
    db_path = get_db_path(request)
    llm_mode = get_llm_mode(request)
    return load_settings_with_cli(
        config_path=config_path,
        db_path=db_path,
        llm_mode=llm_mode,
    )


def get_dispatcher(request: Request, llm_mode: str | None = None) -> Dispatcher:
    """Build a Dispatcher instance for API context.

    Reuses CLI's _build_dispatcher to ensure consistency.
    """
    from ..cli_app.common import _build_dispatcher

    repo = get_repo(request)
    settings = get_settings(request)
    mode = llm_mode or get_llm_mode(request)
    return _build_dispatcher(repo, settings, mode)
