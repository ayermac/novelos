"""Desktop sidecar entry point — thin wrapper around existing API startup.

This module provides a minimal CLI entry point for the Electron desktop
client to spawn the FastAPI backend without going through the full
interactive CLI argument parser.
"""

from __future__ import annotations

import argparse
import sys

from novel_factory.api_app import create_api_app
import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Novelos Desktop Sidecar")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, required=True, help="Port to bind")
    parser.add_argument("--db-path", required=True, help="Path to SQLite database file")
    parser.add_argument("--config-path", default=None, help="Path to config YAML file")
    parser.add_argument("--llm-mode", default="stub", choices=["stub", "real"], help="LLM mode (default: stub)")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Log level (default: info)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    app = create_api_app(
        db_path=args.db_path,
        config_path=args.config_path,
        llm_mode=args.llm_mode,
    )

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=False,
    )


if __name__ == "__main__":
    main()
