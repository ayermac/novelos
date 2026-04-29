"""v5.1.6 Phase 0 Frontend Closure Tests.

Tests for:
1. Review API returns correct structure
2. Style API returns correct structure
3. Frontend build passes
4. TypeScript typecheck passes
"""

from __future__ import annotations

import os
import tempfile
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        test_client = TestClient(app)
        yield test_client
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestReviewAPI:
    """Test Review API structure."""

    def test_review_workbench_returns_required_fields(self, client):
        """Review API should return queue and stats."""
        resp = client.get("/api/review/workbench")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Required fields
        assert "queue" in data
        assert "stats" in data
        assert isinstance(data["queue"], list)
        assert isinstance(data["stats"], dict)

        # Stats fields
        stats = data["stats"]
        assert "review" in stats
        assert "blocking" in stats
        assert "approved" in stats
        assert "rejected" in stats


class TestStyleAPI:
    """Test Style API structure."""

    def test_style_console_returns_required_fields(self, client):
        """Style API should return style_bibles, gate_configs, samples, and health."""
        resp = client.get("/api/style/console")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Required fields
        assert "style_bibles" in data
        assert "style_gate_configs" in data
        assert "style_samples" in data
        assert "health" in data

        # Health fields
        health = data["health"]
        assert "total_projects" in health
        assert "projects_with_bible" in health
        assert "gate_configs" in health


class TestFrontendBuild:
    """Test frontend build passes."""

    def test_typecheck_passes(self):
        """TypeScript typecheck should pass."""
        result = subprocess.run(
            ["npm", "run", "typecheck"],
            cwd=Path(__file__).parent.parent / "frontend",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Typecheck failed: {result.stderr}"

    def test_build_passes(self):
        """Frontend build should pass."""
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=Path(__file__).parent.parent / "frontend",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Build failed: {result.stderr}"


class TestNavigationStructure:
    """Test navigation structure has section labels."""

    def test_layout_has_section_labels(self):
        """Layout should have section labels for navigation groups."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        layout_file = frontend_src / "components" / "Layout.tsx"
        content = layout_file.read_text()

        # Should have isSectionLabel property
        assert "isSectionLabel" in content

        # Should have section labels
        assert "创作" in content
        assert "工具" in content


class TestAcceptanceRouteRemoved:
    """Test that /acceptance route has been removed."""

    def test_no_acceptance_import(self):
        """App.tsx should not import Acceptance."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        app_file = frontend_src / "App.tsx"
        content = app_file.read_text()

        # Should not have Acceptance import
        assert "Acceptance" not in content, "App.tsx should not import Acceptance"

    def test_no_acceptance_route(self):
        """App.tsx should not have /acceptance route."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        app_file = frontend_src / "App.tsx"
        content = app_file.read_text()

        # Should not have /acceptance route
        assert 'path="acceptance"' not in content, "App.tsx should not have /acceptance route"

    def test_acceptance_file_deleted(self):
        """Acceptance.tsx should be deleted."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        acceptance_file = frontend_src / "pages" / "Acceptance.tsx"

        assert not acceptance_file.exists(), "Acceptance.tsx should be deleted"


class TestEmptyStateMultiActions:
    """Test EmptyState component supports multiple actions."""

    def test_empty_state_has_actions_prop(self):
        """EmptyState should have actions prop support."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        empty_state_file = frontend_src / "components" / "EmptyState.tsx"
        content = empty_state_file.read_text()

        # Should have actions property
        assert "actions" in content
        assert "Array<" in content or "actions?:" in content
