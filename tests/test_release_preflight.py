"""Tests for the read-only release preflight."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/release_preflight.py"


def _write_release_fixture(root: Path, version: str = "6.11.02") -> None:
    (root / "novel_factory").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "desktop").mkdir()
    (root / "novel_factory/version.py").write_text(
        f'__version__: str = "{version}"\n', encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "novel-factory"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        f'[[package]]\nname = "novel-factory"\nversion = "{version}"\nsource = {{ editable = "." }}\n',
        encoding="utf-8",
    )
    for workspace, name in (
        ("frontend", "novel-factory-frontend"),
        ("desktop", "novelos-desktop"),
    ):
        package = {"name": name, "version": version}
        lock = {
            "name": name,
            "version": version,
            "lockfileVersion": 3,
            "packages": {"": {"name": name, "version": version}},
        }
        (root / workspace / "package.json").write_text(
            json.dumps(package), encoding="utf-8"
        )
        (root / workspace / "package-lock.json").write_text(
            json.dumps(lock), encoding="utf-8"
        )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## v{version} - Fixture\n", encoding="utf-8"
    )


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_valid_fixture_passes_with_structured_output(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS version.pyproject" in result.stdout
    assert "PASS lock.frontend" in result.stdout
    assert "Release preflight: PASS" in result.stdout


def test_version_drift_blocks_release(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path)
    frontend = tmp_path / "frontend/package.json"
    frontend.write_text(
        json.dumps({"name": "novel-factory-frontend", "version": "6.11.01"}),
        encoding="utf-8",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "FAIL version.frontend-package" in result.stdout
    assert "expected 6.11.02, got 6.11.01" in result.stdout


def test_lock_root_drift_blocks_release(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path)
    lock_path = tmp_path / "desktop/package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["packages"][""]["version"] = "6.11.01"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "FAIL version.desktop-lock-root" in result.stdout
    assert "FAIL lock.desktop" in result.stdout


def test_missing_changelog_entry_blocks_release(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "FAIL changelog.target-version" in result.stdout


def test_preflight_does_not_modify_files(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path)
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    result = _run(tmp_path)

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert result.returncode == 0
    assert after == before


def test_repository_preflight_passes() -> None:
    result = _run(REPO_ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
