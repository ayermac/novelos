"""FastAPI application factory for Web UI Acceptance Console.

Creates a FastAPI app with:
- Jinja2 templates
- Static file serving
- Route registration
- App state for db_path, config_path, llm_mode
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from .deps import get_templates, render


def create_app(
    db_path: str | None = None,
    config_path: str | None = None,
    llm_mode: str = "stub",
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database file
        config_path: Path to config YAML file
        llm_mode: LLM mode ('stub' or 'real'), defaults to 'stub'

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Novel Factory - Acceptance Console",
        description="Web UI for acceptance testing",
        version="4.5.0",
    )

    # Store configuration in app state
    app.state.db_path = db_path
    app.state.config_path = config_path
    app.state.llm_mode = llm_mode

    # Mount static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Register routes
    from .routes import dashboard, projects, run, batch, queue, serial, review, style, config, onboarding

    app.include_router(dashboard.router, tags=["dashboard"])
    app.include_router(projects.router, prefix="/projects", tags=["projects"])
    app.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
    app.include_router(run.router, prefix="/run", tags=["run"])
    app.include_router(batch.router, prefix="/batch", tags=["batch"])
    app.include_router(queue.router, prefix="/queue", tags=["queue"])
    app.include_router(serial.router, prefix="/serial", tags=["serial"])
    app.include_router(review.router, prefix="/review", tags=["review"])
    app.include_router(style.router, prefix="/style", tags=["style"])
    app.include_router(config.router, prefix="/config", tags=["config"])

    # Exception handler for all errors
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
        """Global exception handler - never shows traceback."""
        from .deps import safe_error_message

        error_msg = safe_error_message(exc)
        templates = get_templates()
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": error_msg,
                "db_path": getattr(app.state, "db_path", None),
                "llm_mode": getattr(app.state, "llm_mode", "stub"),
            },
            status_code=500,
        )

    return app
