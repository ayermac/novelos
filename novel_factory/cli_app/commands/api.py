"""API server command."""

from __future__ import annotations

import logging

import uvicorn

logger = logging.getLogger(__name__)


def cmd_api(args) -> None:
    """Start the FastAPI JSON API server.

    Args:
        args: Parsed arguments with host, port, db_path, config, llm_mode
    """
    from ...api_app import create_api_app

    # Create app with configuration
    app = create_api_app(
        db_path=args.db_path,
        config_path=args.config,
        llm_mode=args.llm_mode,
    )

    # Log startup info
    logger.info(f"Starting Novel Factory API server on {args.host}:{args.port}")
    logger.info(f"LLM mode: {args.llm_mode}")
    if args.db_path:
        logger.info(f"Database: {args.db_path}")
    if args.config:
        logger.info(f"Config: {args.config}")

    # Run server
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
