"""Tests for scripts/release_smoke.py — release readiness validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from novel_factory.version import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestReleaseSmokeScript:
    """Invoke the smoke script and verify its checks."""

    def _run_smoke(self, *extra_args: str) -> tuple[int, str, str]:
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "release_smoke.py")]
        cmd.extend(extra_args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=60,
        )
        return result.returncode, result.stdout, result.stderr

    def test_smoke_skip_api_all_required_pass(self):
        """With --skip-api, all required checks should pass locally."""
        code, out, _ = self._run_smoke("--skip-api")
        assert code == 0, f"Smoke failed:\n{out}"
        assert "ALL CHECKS PASSED" in out or "REQUIRED PASSED" in out

    def test_smoke_json_output_structure(self):
        """--json output must be valid and contain expected fields."""
        code, out, _ = self._run_smoke("--skip-api", "--json")
        data = json.loads(out)
        assert "ok" in data
        assert "version_expected" in data
        assert data["version_expected"] == __version__
        assert "checks" in data
        check_names = {c["name"] for c in data["checks"]}
        assert "cli_version" in check_names
        assert "frontend_version" in check_names
        assert "desktop_version" in check_names
        assert "desktop_sidecar" in check_names

    def test_smoke_cli_version_check_passes(self):
        """CLI version check should report the current version."""
        _, out, _ = self._run_smoke("--skip-api", "--json")
        data = json.loads(out)
        cli = next(c for c in data["checks"] if c["name"] == "cli_version")
        assert cli["passed"] is True
        assert __version__ in cli["message"]

    def test_smoke_frontend_version_matches_runtime(self):
        """Frontend package.json version must match runtime."""
        _, out, _ = self._run_smoke("--skip-api", "--json")
        data = json.loads(out)
        fe = next(c for c in data["checks"] if c["name"] == "frontend_version")
        assert fe["passed"] is True
        assert fe["message"] == __version__

    def test_smoke_desktop_version_matches_runtime(self):
        """Desktop package.json version must match runtime."""
        _, out, _ = self._run_smoke("--skip-api", "--json")
        data = json.loads(out)
        de = next(c for c in data["checks"] if c["name"] == "desktop_version")
        assert de["passed"] is True
        assert de["message"] == __version__

    def test_smoke_desktop_sidecar_version_matches(self):
        """Desktop sidecar health version must match desktop package version."""
        _, out, _ = self._run_smoke("--skip-api", "--json")
        data = json.loads(out)
        sidecar = next(c for c in data["checks"] if c["name"] == "desktop_sidecar")
        assert sidecar["passed"] is True, f"desktop_sidecar failed: {sidecar['message']}"
        assert __version__ in sidecar["message"]

    def test_smoke_api_health_with_running_api(self):
        """If API is running, health check should pass with matching version."""
        from novel_factory.api_app import create_api_app
        from fastapi.testclient import TestClient

        app = create_api_app(db_path=":memory:", llm_mode="stub")
        # The smoke script uses urllib to hit a URL; we can't easily mock that
        # without starting a real server.  Skip this in CI and verify via
        # the API unit test instead.
        pytest.skip("Requires running API server; covered by test_api_health_version_matches_runtime")


class TestHealthStartupMetadata:
    """API /api/health returns startup metadata for mismatch diagnosis."""

    def test_health_includes_startup_metadata(self):
        from novel_factory.api_app import create_api_app
        from fastapi.testclient import TestClient

        app = create_api_app(db_path=":memory:", llm_mode="stub")
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert "startup" in data
        startup = data["startup"]
        assert "started_at" in startup
        assert "python" in startup
        assert "source_root" in startup
        assert "cwd" in startup
        assert isinstance(startup["source_root"], str)
        assert "novelos" in startup["source_root"]

    def test_health_version_matches_runtime(self):
        from novel_factory.api_app import create_api_app
        from fastapi.testclient import TestClient

        app = create_api_app(db_path=":memory:", llm_mode="stub")
        client = TestClient(app)
        resp = client.get("/api/health")
        data = resp.json()["data"]
        assert data["version"] == __version__
