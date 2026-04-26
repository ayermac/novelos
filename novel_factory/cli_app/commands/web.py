"""CLI command to start the web UI server."""

from __future__ import annotations

import uvicorn

from ...web.app import create_app
from ..common import _get_settings


def cmd_web(args) -> None:
    """Start the web UI server."""
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    db_path = getattr(args, "db_path", None)
    config_path = getattr(args, "config", None)
    llm_mode = getattr(args, "llm_mode", "stub")

    # Get settings if available
    settings = _get_settings(args)
    if not db_path:
        db_path = settings.db_path
    if not config_path:
        config_path = getattr(settings, "config_path", None)

    print(f"Starting Novel Factory Web UI...")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  DB: {db_path}")
    print(f"  LLM Mode: {llm_mode}")
    print(f"\nOpen http://{host}:{port} in your browser")

    app = create_app(db_path=db_path, config_path=config_path, llm_mode=llm_mode)

    uvicorn.run(app, host=host, port=port)
