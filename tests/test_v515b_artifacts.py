"""v5.1.5b Agent Artifacts Display Tests.

Tests for:
1. /api/runs/{run_id} returns steps with artifacts field
2. Artifacts not null in stub mode
3. Different chapters have different artifacts content
4. artifacts.summary not empty string
5. Frontend build passes
6. TypeScript typecheck passes
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import seed_context_for_chapter


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


class TestArtifactsAPI:
    """Test artifacts field in runs API."""

    def test_run_detail_steps_have_artifacts_field(self, client):
        """Steps should include artifacts field (can be null)."""
        # Create project and run
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515b_001",
                "name": "Artifacts Test",
                "initial_chapter_count": 1,
            },
        )
        seed_context_for_chapter(client.app.state.db_path, "test_v515b_001", 1)
        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v515b_001", "chapter": 1},
        )
        run_id = resp.json()["data"]["run_id"]

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        steps = data["steps"]

        # All steps should have artifacts field
        for step in steps:
            assert "artifacts" in step, f"Step {step['key']} missing artifacts field"

    def test_artifacts_not_null_in_stub_mode(self, client):
        """Completed steps should have non-null artifacts in stub mode."""
        # Create project and run
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515b_002",
                "name": "Stub Artifacts Test",
                "initial_chapter_count": 1,
            },
        )
        seed_context_for_chapter(client.app.state.db_path, "test_v515b_002", 1)
        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v515b_002", "chapter": 1},
        )
        run_id = resp.json()["data"]["run_id"]

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        steps = resp.json()["data"]["steps"]

        # Completed steps should have artifacts
        for step in steps:
            if step["status"] == "completed":
                assert step["artifacts"] is not None, (
                    f"Completed step {step['key']} should have artifacts in stub mode"
                )

    def test_different_chapters_different_artifacts(self, client):
        """Different chapters should produce different artifacts content."""
        # Create project with multiple chapters
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515b_003",
                "name": "Different Chapters",
                "initial_chapter_count": 3,
            },
        )

        seed_context_for_chapter(client.app.state.db_path, "test_v515b_003", 1)
        seed_context_for_chapter(client.app.state.db_path, "test_v515b_003", 2)

        # Run chapter 1
        resp1 = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v515b_003", "chapter": 1},
        )
        run_id_1 = resp1.json()["data"]["run_id"]

        # Run chapter 2
        resp2 = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v515b_003", "chapter": 2},
        )
        run_id_2 = resp2.json()["data"]["run_id"]

        # Get run details
        steps1 = client.get(f"/api/runs/{run_id_1}").json()["data"]["steps"]
        steps2 = client.get(f"/api/runs/{run_id_2}").json()["data"]["steps"]

        # Find screenwriter step for both
        sw1 = next(s for s in steps1 if s["key"] == "screenwriter")
        sw2 = next(s for s in steps2 if s["key"] == "screenwriter")

        # Artifacts should be different
        assert sw1["artifacts"]["summary"] != sw2["artifacts"]["summary"], (
            "Different chapters should have different artifacts"
        )

    def test_artifacts_summary_not_empty(self, client):
        """Artifacts summary should not be empty string."""
        # Create project and run
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515b_004",
                "name": "Summary Test",
                "initial_chapter_count": 1,
            },
        )
        seed_context_for_chapter(client.app.state.db_path, "test_v515b_004", 1)
        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v515b_004", "chapter": 1},
        )
        run_id = resp.json()["data"]["run_id"]

        # Get run detail
        steps = client.get(f"/api/runs/{run_id}").json()["data"]["steps"]

        # Check completed steps have non-empty summary
        for step in steps:
            if step["status"] == "completed" and step["artifacts"]:
                assert step["artifacts"]["summary"], (
                    f"Step {step['key']} artifacts.summary should not be empty"
                )
                assert len(step["artifacts"]["summary"]) > 10, (
                    f"Step {step['key']} summary too short"
                )

    def test_artifacts_output_preview_bounded(self, client):
        """Output preview should be reasonably bounded."""
        # Create project and run
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_v515b_005",
                "name": "Preview Bound Test",
                "initial_chapter_count": 1,
            },
        )
        seed_context_for_chapter(client.app.state.db_path, "test_v515b_005", 1)
        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_v515b_005", "chapter": 1},
        )
        run_id = resp.json()["data"]["run_id"]

        # Get run detail
        steps = client.get(f"/api/runs/{run_id}").json()["data"]["steps"]

        # Check output_preview length
        for step in steps:
            if step["status"] == "completed" and step["artifacts"]:
                preview = step["artifacts"].get("output_preview", "")
                if preview:
                    # Should be under 150 chars (requirement says ~100)
                    assert len(preview) <= 150, (
                        f"Step {step['key']} output_preview too long: {len(preview)} chars"
                    )


class TestFrontendArtifacts:
    """Test frontend artifacts display."""

    def test_workflow_timeline_has_artifacts_support(self):
        """WorkflowTimeline should support artifacts prop."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        timeline_file = frontend_src / "components" / "WorkflowTimeline.tsx"
        content = timeline_file.read_text()

        assert "artifacts" in content, "WorkflowTimeline should handle artifacts"
        assert "查看产物" in content or "展开" in content, (
            "WorkflowTimeline should have expand button for artifacts"
        )

    def test_project_detail_artifacts_tab_updated(self):
        """ProjectDetail ArtifactsTab should display structured artifacts."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        detail_file = frontend_src / "pages" / "ProjectDetail.tsx"
        content = detail_file.read_text()

        # Should have artifacts-related code
        assert "artifacts" in content.lower(), "Should reference artifacts"
        assert "artifact-card" in content or "artifactCard" in content.lower(), (
            "Should have artifact card styling"
        )
        assert "tab === 'workflow' || tab === 'artifacts'" in content, (
            "Artifacts tab should load run detail without requiring workflow tab first"
        )

    def test_step_interface_has_artifacts(self):
        """Step interface should include artifacts field."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        detail_file = frontend_src / "pages" / "ProjectDetail.tsx"
        content = detail_file.read_text()

        # Interface should define artifacts
        assert "interface Step" in content or "type Step" in content
        assert "artifacts" in content, "Step interface should include artifacts"

    def test_no_raw_status_in_artifacts(self):
        """Artifacts display should not show raw JSON/undefined/null."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        detail_file = frontend_src / "pages" / "ProjectDetail.tsx"
        content = detail_file.read_text()

        # Should use summary field, not dump entire object
        assert "artifacts!.summary" in content or "artifacts?.summary" in content, (
            "Should display artifacts.summary, not raw artifacts object"
        )

        # Should NOT have dangerous patterns
        assert "JSON.stringify(step.artifacts)" not in content, (
            "Should not dump raw JSON to UI"
        )

    def test_artifacts_tab_uses_non_emoji_marks(self):
        """Artifacts tab should not reintroduce emoji icons."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        detail_file = frontend_src / "pages" / "ProjectDetail.tsx"
        content = detail_file.read_text()

        for emoji in ["📦", "📋", "✍️", "✨", "🔍", "📤", "📄"]:
            assert emoji not in content, f"ProjectDetail should not use emoji icon {emoji}"


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
