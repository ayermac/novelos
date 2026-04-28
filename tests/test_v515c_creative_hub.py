"""v5.1.5c Creative Hub Tests.

Tests for:
1. Dashboard creative hub design (hero card, activity timeline)
2. Settings generation capability diagnostics
3. Projects page card layout
4. Frontend build passes
5. TypeScript typecheck passes
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import seed_context_for_chapter  # noqa: F401


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


class TestDashboardCreativeHub:
    """Test Dashboard creative hub design."""

    def test_dashboard_returns_required_fields(self, client):
        """Dashboard API should return fields for creative hub."""
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Required fields for creative hub
        assert "project_count" in data
        assert "recent_runs" in data
        assert "queue_count" in data
        assert "review_count" in data
        assert "llm_mode" in data

    def test_dashboard_recent_runs_have_status(self, client):
        """Recent runs should include status field for timeline."""
        # Create project and run
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515c_dash",
                "name": "Dashboard Test",
                "initial_chapter_count": 1,
            },
        )
        # v5.3.0: Seed context to pass Context Readiness Gate
        db_path = client.app.state.db_path
        seed_context_for_chapter(db_path, "test_v515c_dash", 1)

        client.post(
            "/api/run/chapter",
            json={"project_id": "test_v515c_dash", "chapter": 1},
        )

        resp = client.get("/api/dashboard")
        runs = resp.json()["data"]["recent_runs"]

        assert len(runs) > 0
        for run in runs:
            assert "status" in run
            assert "project_name" in run
            assert "chapter" in run
            assert "created_at" in run


class TestSettingsGenerationStats:
    """Test Settings generation capability diagnostics."""

    def test_settings_returns_generation_stats(self, client):
        """Settings API should return generation_stats field."""
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert "generation_stats" in data
        stats = data["generation_stats"]

        # Required fields
        assert "test_result" in stats
        assert "success_rate" in stats
        assert "avg_duration_seconds" in stats
        assert "total_runs" in stats

    def test_generation_stats_stub_mode_returns_pending(self, client):
        """In stub mode, test_result should be 'pending'."""
        resp = client.get("/api/settings")
        stats = resp.json()["data"]["generation_stats"]

        # Stub mode always returns pending
        assert stats["test_result"] == "pending"

    def test_generation_stats_after_runs(self, client):
        """After creating runs, generation_stats should reflect them."""
        # Create project and multiple runs
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515c_stats",
                "name": "Stats Test",
                "initial_chapter_count": 3,
            },
        )

        # v5.3.0: Seed context to pass Context Readiness Gate
        db_path = client.app.state.db_path
        for i in range(1, 4):
            seed_context_for_chapter(db_path, "test_v515c_stats", i)

        for i in range(1, 4):
            client.post(
                "/api/run/chapter",
                json={"project_id": "test_v515c_stats", "chapter": i},
            )

        resp = client.get("/api/settings")
        stats = resp.json()["data"]["generation_stats"]

        # Should have recorded runs
        assert stats["total_runs"] >= 3
        # In stub mode, success rate should be 100%
        assert stats["success_rate"] == 100


class TestProjectsCardLayout:
    """Test Projects page card layout."""

    def test_projects_api_returns_required_fields(self, client):
        """Projects API should return fields for card display."""
        # Create project
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515c_card",
                "name": "Card Layout Test",
                "genre": "xuanhuan",
                "description": "Test description for card layout",
                "initial_chapter_count": 5,
            },
        )

        resp = client.get("/api/projects")
        assert resp.status_code == 200
        projects = resp.json()["data"]

        assert len(projects) > 0
        project = projects[0]

        # Fields needed for card layout
        assert "project_id" in project
        assert "name" in project
        assert "chapter_count" in project
        assert "created_at" in project
        # Optional fields
        if project.get("genre"):
            assert isinstance(project["genre"], str)
        if project.get("description"):
            assert isinstance(project["description"], str)

    def test_projects_component_supports_cards(self):
        """Projects component should have card layout code."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        projects_file = frontend_src / "pages" / "Projects.tsx"
        content = projects_file.read_text()

        # Should have card-related styling
        assert "project-card" in content or "ProjectCard" in content
        assert "grid" in content.lower()  # Grid layout for cards
        assert "gridTemplateColumns" in content or "grid-template-columns" in content


class TestFrontendBuild:
    """Test frontend build passes."""

    def test_typecheck_passes(self):
        """TypeScript typecheck should pass."""
        import subprocess

        result = subprocess.run(
            ["npm", "run", "typecheck"],
            cwd=Path(__file__).parent.parent / "frontend",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Typecheck failed: {result.stderr}"

    def test_build_passes(self):
        """Frontend build should pass."""
        import subprocess

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=Path(__file__).parent.parent / "frontend",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Build failed: {result.stderr}"


class TestDashboardComponent:
    """Test Dashboard component structure."""

    def test_dashboard_has_hero_card(self):
        """Dashboard should have hero card section."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        content = dashboard_file.read_text()

        # Hero card with gradient background (uses CSS variable or direct gradient)
        assert "hero-card" in content.lower() or "heroCard" in content
        # v5.2: Uses CSS variable --gradient-ink for gradient
        assert "gradient" in content or "linear-gradient" in content

    def test_dashboard_has_activity_timeline(self):
        """Dashboard should have activity timeline (not table)."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        content = dashboard_file.read_text()

        # Activity timeline
        assert "activity-timeline" in content or "timeline" in content.lower()
        # Should NOT use data-table for recent runs
        assert "data-table" not in content or "recent_runs" not in content.split("data-table")[0] if "data-table" in content else True

    def test_dashboard_has_relative_time(self):
        """Dashboard should show relative time formatting."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        content = dashboard_file.read_text()

        # Relative time function
        assert "formatRelativeTime" in content or "relative" in content.lower()


class TestSettingsComponent:
    """Test Settings component structure."""

    def test_settings_has_generation_diagnostics(self):
        """Settings should display generation capability diagnostics."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        settings_file = frontend_src / "pages" / "Settings.tsx"
        content = settings_file.read_text()

        # Generation stats interface
        assert "GenerationStats" in content
        assert "generation_stats" in content

        # UI elements for diagnostics - should NOT have misleading "LLM 连通性"
        assert "生成记录健康度" in content or "健康度" in content
        assert "LLM 连通性" not in content, "Should not have misleading 'LLM 连通性' label"


class TestDashboardCTARouting:
    """Test Dashboard CTA routing to project workspace."""

    def test_dashboard_cta_not_to_run(self):
        """Dashboard hero CTA should NOT route to /run for daily creation."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        content = dashboard_file.read_text()

        # Check that heroAction does not contain /run?project_id
        # (it should route to /projects/:id instead)
        assert "/run?project_id" not in content, (
            "Dashboard hero CTA should not route to /run?project_id for daily creation"
        )

        # Should have project workspace routes
        assert "/projects/${firstProject.project_id}" in content or "/projects/${latestRun.project_id}" in content

    def test_dashboard_has_workspace_navigation(self):
        """Dashboard should navigate to project workspace."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        content = dashboard_file.read_text()

        # Should have workspace-related labels
        assert "进入工作台" in content or "工作台" in content


class TestNoEmojiIcons:
    """Test that new pages do not use emoji icons."""

    def test_dashboard_no_emoji(self):
        """Dashboard should not use emoji icons in quick actions."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        dashboard_file = frontend_src / "pages" / "Dashboard.tsx"
        content = dashboard_file.read_text()

        # Common emoji patterns that should NOT be present
        emoji_patterns = ["📝", "▶️", "✅", "⚙️", "📚"]
        for emoji in emoji_patterns:
            assert emoji not in content, f"Dashboard should not use emoji: {emoji}"

        # Should use lucide-react icons instead
        assert "from 'lucide-react'" in content

    def test_projects_no_emoji(self):
        """Projects page should not use emoji icons."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        projects_file = frontend_src / "pages" / "Projects.tsx"
        content = projects_file.read_text()

        # Should not use emoji
        emoji_patterns = ["📚", "📖", "📝"]
        for emoji in emoji_patterns:
            assert emoji not in content, f"Projects should not use emoji: {emoji}"

        # Should use lucide-react icons
        assert "from 'lucide-react'" in content


class TestMainFlowRouting:
    """Test that main flow routes to project workspace, not /run."""

    def test_context_sidebar_retry_uses_generate(self):
        """ContextSidebar retry should use onGenerate, not onNavigateToRun."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        sidebar_file = frontend_src / "components" / "ContextSidebar.tsx"
        content = sidebar_file.read_text()

        # Check that blocked/failed retry uses onGenerate
        assert "onClick: onGenerate" in content, (
            "ContextSidebar retry should use onGenerate for in-workspace execution"
        )

    def test_rundetail_next_chapter_to_workspace(self):
        """RunDetail 'continue next chapter' should route to workspace."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        rundetail_file = frontend_src / "pages" / "RunDetail.tsx"
        content = rundetail_file.read_text()

        # Should NOT have /run?project_id
        assert "/run?project_id" not in content, (
            "RunDetail should not route to /run?project_id for next chapter"
        )

        # Should have workspace route for next chapter
        assert "/projects/${data.project_id}?chapter=${data.chapter_number + 1}" in content

    def test_onboarding_first_chapter_to_workspace(self):
        """Onboarding 'generate first chapter' should route to workspace."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        onboarding_file = frontend_src / "pages" / "Onboarding.tsx"
        content = onboarding_file.read_text()

        # Should NOT have /run?project_id
        assert "/run?project_id" not in content, (
            "Onboarding should not route to /run?project_id for first chapter"
        )

        # Should have workspace route
        assert "/projects/${result.project.project_id}?chapter=1" in content

    def test_no_run_project_id_in_main_flows(self):
        """Main flow files should not have /run?project_id pattern."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        main_flow_files = [
            "pages/Dashboard.tsx",
            "pages/RunDetail.tsx",
            "pages/Onboarding.tsx",
            "components/ContextSidebar.tsx",
        ]

        for filename in main_flow_files:
            filepath = frontend_src / filename
            if filepath.exists():
                content = filepath.read_text()
                # /run?project_id should not appear as main flow route
                assert "/run?project_id" not in content, (
                    f"{filename} should not use /run?project_id as main flow route"
                )
