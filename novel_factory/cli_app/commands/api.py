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

    config_path = getattr(args, "api_config", None) or getattr(args, "config", None)
    db_path = getattr(args, "api_db_path", None) or getattr(args, "db_path", None)
    llm_mode = (
        getattr(args, "api_llm_mode", None)
        or getattr(args, "global_llm_mode", None)
        or "stub"
    )

    # Create app with configuration
    app = create_api_app(
        db_path=db_path,
        config_path=config_path,
        llm_mode=llm_mode,
        skills_config_path=args.skills_config,
    )

    # Log startup info
    logger.info(f"Starting Novel Factory API server on {args.host}:{args.port}")
    logger.info(f"LLM mode: {llm_mode}")
    logger.info(f"Log level: {args.log_level}")
    if args.no_access_log:
        logger.info("Access log: disabled")
    if db_path:
        logger.info(f"Database: {db_path}")
    if config_path:
        logger.info(f"Config: {config_path}")

    # Run server
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=not args.no_access_log,
    )
