"""Web dependency utilities for FastAPI routes.

Provides shared utilities for:
- Repository creation
- Settings management
- Dispatcher creation
- Template rendering
- Error handling
- Secret masking
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from ..db.repository import Repository
from ..config.settings import Settings
from ..config.loader import load_settings_with_cli
from ..dispatcher import Dispatcher


_templates: Jinja2Templates | None = None


def get_templates() -> Jinja2Templates:
    """Get or create Jinja2Templates instance."""
    global _templates
    if _templates is None:
        template_dir = Path(__file__).parent / "templates"
        _templates = Jinja2Templates(directory=str(template_dir))
    return _templates


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


def get_settings_for_web(request: Request) -> Settings:
    """Get Settings instance for web context."""
    config_path = get_config_path(request)
    db_path = get_db_path(request)
    llm_mode = get_llm_mode(request)
    settings = load_settings_with_cli(
        config_path=config_path,
        db_path=db_path,
        llm_mode=llm_mode,
    )
    return settings


def build_dispatcher_for_web(request: Request, llm_mode: str | None = None) -> Dispatcher:
    """Build a Dispatcher instance for web context.

    Args:
        request: FastAPI request
        llm_mode: Override LLM mode (defaults to app.state.llm_mode)

    Returns:
        Dispatcher instance
    """
    from ..cli_app.common import _build_dispatcher

    repo = get_repo(request)
    settings = get_settings_for_web(request)
    mode = llm_mode or get_llm_mode(request)
    return _build_dispatcher(repo, settings, mode)


def render(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
) -> Any:
    """Render a template with standard context.

    Args:
        request: FastAPI request
        template_name: Template file name
        context: Additional template context
        status_code: HTTP status code

    Returns:
        TemplateResponse
    """
    templates = get_templates()
    ctx = {
        "request": request,
        "db_path": get_db_path(request),
        "llm_mode": get_llm_mode(request),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(template_name, ctx, status_code=status_code)


def safe_error_message(exc: Exception) -> str:
    """Extract a safe error message from an exception.

    Never includes traceback or sensitive information.
    """
    msg = str(exc)
    # Truncate very long messages
    if len(msg) > 500:
        msg = msg[:500] + "..."
    return msg


def mask_secret(value: str | None) -> str:
    """Mask a secret value for display.

    Returns '***' if value exists, empty string otherwise.
    Never reveals the actual secret.
    """
    if value and value.strip():
        return "***"
    return ""


def json_or_form_value(form: dict, name: str, default: str | None = None) -> str | None:
    """Get a value from form data, handling both JSON and form encoding.

    Args:
        form: Form data dict
        name: Field name
        default: Default value if not found

    Returns:
        Field value or default
    """
    value = form.get(name, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value
