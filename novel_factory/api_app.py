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
from .version import get_version
from .security.redaction import redact_sensitive_text


def create_api_app(
    db_path: str | None = None,
    config_path: str | None = None,
    llm_mode: str = "stub",
    skills_config_path: str | None = None,
    openclaw_root_path: str | None = None,
) -> FastAPI:
    """Create and configure the API application.

    Args:
        db_path: Path to SQLite database file
        config_path: Path to config YAML file
        llm_mode: LLM mode ('stub' or 'real'), defaults to 'stub'
        skills_config_path: Path to skills YAML config file
        openclaw_root_path: Path to local OpenClaw legacy workspace

    Returns:
        Configured FastAPI application
    """
    version = get_version()
    app = FastAPI(
        title="小说工厂 API",
        description=f"Novel Factory API v{version}",
        version=version,
        default_response_class=JSONResponse,
    )

    # Store configuration in app state
    app.state.db_path = db_path
    app.state.config_path = config_path
    app.state.llm_mode = llm_mode
    app.state.skills_config_path = skills_config_path
    app.state.openclaw_root_path = openclaw_root_path

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
        project_skill_overrides_router,
        production_router,
        versions_router,
        workflow_timeline_router,
        agent_memory_router,
        agent_ops_router,
        desktop_router,
        quality_diagnosis_router,
        creative_contracts_router,  # v6.9.0
        chapter_briefs_router,  # v6.9.0
        ledgers_router,  # v6.9.0
        editor_reports_router,  # v6.9.0
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
    app.include_router(project_skill_overrides_router, prefix="/api", tags=["project-skill-overrides"])
    app.include_router(production_router, prefix="/api", tags=["production"])
    app.include_router(versions_router, prefix="/api", tags=["versions"])
    app.include_router(workflow_timeline_router, prefix="/api", tags=["workflow-timeline"])
    app.include_router(agent_memory_router, prefix="/api", tags=["agent-memory"])
    app.include_router(agent_ops_router, prefix="/api", tags=["agent-ops"])
    app.include_router(desktop_router, prefix="/api", tags=["desktop"])
    app.include_router(quality_diagnosis_router, prefix="/api", tags=["quality-diagnosis"])
    app.include_router(creative_contracts_router, prefix="/api", tags=["creative-contracts"])  # v6.9.0
    app.include_router(chapter_briefs_router, prefix="/api", tags=["chapter-briefs"])  # v6.9.0
    app.include_router(ledgers_router, prefix="/api", tags=["ledgers"])  # v6.9.0
    app.include_router(editor_reports_router, prefix="/api", tags=["editor-reports"])  # v6.9.0

    # Exception handler - never exposes traceback or secrets
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Global exception handler - returns JSON error envelope."""
        # Safe error message without traceback or secrets
        msg = redact_sensitive_text(str(exc))
        if len(msg) > 200:
            msg = msg[:200] + "..."

        envelope = error_response("INTERNAL_ERROR", f"内部错误: {msg}")
        return JSONResponse(
            status_code=500,
            content=envelope.model_dump(),
        )

    return app
