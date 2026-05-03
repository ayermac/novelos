"""v5.3 API Application Factory.

Creates a FastAPI app with:
- JSON API routes under /api
- Unified envelope responses
- Error handling without traceback exposure
- No API key/secret exposure
- Stub mode safety
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .api.envelope import error_response, EnvelopeResponse


def create_api_app(
    db_path: str | None = None,
    config_path: str | None = None,
    llm_mode: str = "stub",
) -> FastAPI:
    """Create and configure the API application.

    Args:
        db_path: Path to SQLite database file
        config_path: Path to config YAML file
        llm_mode: LLM mode ('stub' or 'real'), defaults to 'stub'

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="小说工厂 API",
        description="Novel Factory API v5.3",
        version="5.3.0",
        default_response_class=JSONResponse,
    )

    # Store configuration in app state
    app.state.db_path = db_path
    app.state.config_path = config_path
    app.state.llm_mode = llm_mode

    # Auto-initialize database on startup
    @app.on_event("startup")
    async def _ensure_db_ready() -> None:
        """Ensure database tables exist when API starts."""
        from .db.connection import init_db
        if db_path:
            init_db(db_path)

    # CORS for frontend development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    from .api.routes import (
        health_router,
        dashboard_router,
        projects_router,
        onboarding_router,
        run_router,
        runs_router,
        review_router,
        style_router,
        settings_router,
        acceptance_router,
        characters_router,
        outlines_router,
        world_settings_router,
        factions_router,
        plot_holes_router,
        instructions_router,
        context_router,
        readonly_router,
        genesis_router,
        memory_updates_router,
        story_facts_router,
        skills_router,
    )

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
    app.include_router(projects_router, prefix="/api", tags=["projects"])
    app.include_router(onboarding_router, prefix="/api", tags=["onboarding"])
    app.include_router(run_router, prefix="/api", tags=["run"])
    app.include_router(runs_router, prefix="/api", tags=["runs"])
    app.include_router(review_router, prefix="/api", tags=["review"])
    app.include_router(style_router, prefix="/api", tags=["style"])
    app.include_router(settings_router, prefix="/api", tags=["settings"])
    app.include_router(acceptance_router, prefix="/api", tags=["acceptance"])
    app.include_router(characters_router, prefix="/api", tags=["characters"])
    app.include_router(outlines_router, prefix="/api", tags=["outlines"])
    app.include_router(world_settings_router, prefix="/api", tags=["world-settings"])
    app.include_router(factions_router, prefix="/api", tags=["factions"])
    app.include_router(plot_holes_router, prefix="/api", tags=["plot-holes"])
    app.include_router(instructions_router, prefix="/api", tags=["instructions"])
    app.include_router(context_router, prefix="/api", tags=["context"])
    app.include_router(readonly_router, prefix="/api", tags=["readonly"])
    app.include_router(genesis_router, prefix="/api", tags=["genesis"])
    app.include_router(memory_updates_router, prefix="/api", tags=["memory-updates"])
    app.include_router(story_facts_router, prefix="/api", tags=["story-facts"])
    app.include_router(skills_router, prefix="/api", tags=["skills"])

    # Exception handler - never exposes traceback
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Global exception handler - returns JSON error envelope."""
        # Safe error message without traceback
        msg = str(exc)
        if len(msg) > 200:
            msg = msg[:200] + "..."

        envelope = error_response("INTERNAL_ERROR", f"内部错误: {msg}")
        return JSONResponse(
            status_code=500,
            content=envelope.model_dump(),
        )

    return app
