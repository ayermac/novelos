"""v4.3 Web App tests - create_app and basic functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from novel_factory.web.app import create_app
from novel_factory.db.connection import init_db


def test_create_app_success():
    """create_app() returns a FastAPI app."""
    app = create_app()
    assert app is not None
    assert app.title == "Novel Factory - Acceptance Console"


def test_create_app_with_db_path():
    """create_app() accepts db_path parameter."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        app = create_app(db_path=db_path)
        assert app.state.db_path == db_path


def test_create_app_with_llm_mode():
    """create_app() accepts llm_mode parameter."""
    app = create_app(llm_mode="stub")
    assert app.state.llm_mode == "stub"

    app2 = create_app(llm_mode="real")
    assert app2.state.llm_mode == "real"


def test_create_app_default_llm_mode_is_stub():
    """create_app() defaults llm_mode to 'stub'."""
    app = create_app()
    assert app.state.llm_mode == "stub"


def test_app_has_routes():
    """App has all expected routes registered."""
    app = create_app()
    routes = [route.path for route in app.routes]

    # Dashboard
    assert "/" in routes

    # Projects
    assert "/projects" in routes

    # Run
    assert "/run" in routes
    assert "/run/chapter" in routes

    # Batch
    assert "/batch" in routes

    # Queue
    assert "/queue" in routes

    # Serial
    assert "/serial" in routes

    # Review
    assert "/review" in routes

    # Style
    assert "/style" in routes

    # Config
    assert "/config" in routes
