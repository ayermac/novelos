"""Prevent version drift across runtime, packages, API, frontend, and desktop.

This test ensures that all version sources stay in sync:
- novel_factory/version.py
- pyproject.toml and uv.lock
- API /api/health response
- frontend/package.json
- desktop/package.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from novel_factory.api_app import create_api_app
from novel_factory.version import __version__


def _load_package_json(relative_path: str) -> dict:
    """Load a package.json and return its parsed content."""
    repo_root = Path(__file__).resolve().parents[1]
    pkg_path = repo_root / relative_path
    with open(pkg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_pyproject_version() -> str:
    """Read project.version without requiring tomllib on Python 3.9."""
    content = (_repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    project_section = re.search(
        r"^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)",
        content,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert project_section is not None, "pyproject.toml is missing [project]"
    match = re.search(
        r'^version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
        project_section.group("body"),
        flags=re.MULTILINE,
    )
    assert match is not None, "pyproject.toml [project] is missing version"
    return match.group("version")


def _load_uv_project_version() -> str:
    """Read the editable novel-factory entry from uv.lock."""
    content = (_repo_root() / "uv.lock").read_text(encoding="utf-8")
    match = re.search(
        r'\[\[package\]\]\s*\nname = "novel-factory"\s*\nversion = "(?P<version>[^"]+)"\s*\nsource = \{ editable = "\." \}',
        content,
    )
    assert match is not None, "uv.lock is missing the editable novel-factory package"
    return match.group("version")


class TestRuntimeVersion:
    """novel_factory/version.py is the single source of truth."""

    def test_version_is_semantic(self):
        """Version string must be semantic: major.minor.patch."""
        parts = __version__.split(".")
        assert len(parts) == 3, f"Expected 3 dot-separated parts, got {parts}"
        for p in parts:
            assert p.isdigit(), f"Version part {p!r} is not numeric"

    def test_version_not_placeholder(self):
        """Version must not be placeholder strings like 0.0.0 or dev."""
        assert __version__ not in ("0.0.0", "dev", "unknown", "")


class TestApiHealthVersion:
    """API /api/health returns the same version as runtime."""

    def test_health_endpoint_version_matches_runtime(self):
        """GET /api/health data.version equals novel_factory.version.__version__."""
        app = create_api_app(db_path=":memory:", llm_mode="stub")
        client = pytest.importorskip("fastapi.testclient").TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True
        health_version = body["data"]["version"]
        assert health_version == __version__, (
            f"API health version {health_version!r} != runtime version {__version__!r}"
        )

    def test_fastapi_app_version_matches_runtime(self):
        """FastAPI app.version metadata equals runtime version."""
        app = create_api_app(db_path=":memory:", llm_mode="stub")
        assert app.version == __version__, (
            f"FastAPI app.version {app.version!r} != runtime version {__version__!r}"
        )


class TestPythonPackageVersion:
    """Python package metadata and lock entry match runtime."""

    def test_pyproject_version_matches_runtime(self):
        assert _load_pyproject_version() == __version__

    def test_uv_lock_version_matches_runtime(self):
        assert _load_uv_project_version() == __version__


class TestFrontendVersion:
    """frontend/package.json version matches runtime."""

    def test_frontend_package_version_matches_runtime(self):
        """frontend/package.json version equals runtime version."""
        pkg = _load_package_json("frontend/package.json")
        frontend_version = pkg.get("version", "")
        assert frontend_version == __version__, (
            f"frontend/package.json version {frontend_version!r} != runtime version {__version__!r}"
        )


class TestDesktopVersion:
    """desktop/package.json version matches runtime."""

    def test_desktop_package_version_matches_runtime(self):
        """desktop/package.json version equals runtime version."""
        pkg = _load_package_json("desktop/package.json")
        desktop_version = pkg.get("version", "")
        assert desktop_version == __version__, (
            f"desktop/package.json version {desktop_version!r} != runtime version {__version__!r}"
        )


class TestLockfileVersions:
    """package-lock.json root version matches runtime (npm preserves stale root versions)."""

    def test_frontend_package_lock_version_matches_runtime(self):
        """frontend/package-lock.json top-level version equals runtime version."""
        lock = _load_package_json("frontend/package-lock.json")
        lock_version = lock.get("version", "")
        assert lock_version == __version__, (
            f"frontend/package-lock.json version {lock_version!r} != runtime version {__version__!r}"
        )
        pkg_version = lock.get("packages", {}).get("", {}).get("version", "")
        assert pkg_version == __version__, (
            f"frontend/package-lock.json packages[''] version {pkg_version!r} != runtime version {__version__!r}"
        )

    def test_desktop_package_lock_version_matches_runtime(self):
        """desktop/package-lock.json top-level version equals runtime version."""
        lock = _load_package_json("desktop/package-lock.json")
        lock_version = lock.get("version", "")
        assert lock_version == __version__, (
            f"desktop/package-lock.json version {lock_version!r} != runtime version {__version__!r}"
        )
        pkg_version = lock.get("packages", {}).get("", {}).get("version", "")
        assert pkg_version == __version__, (
            f"desktop/package-lock.json packages[''] version {pkg_version!r} != runtime version {__version__!r}"
        )
