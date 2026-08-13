#!/usr/bin/env python3
"""Read-only release preflight for Novelos.

The runtime version in ``novel_factory/version.py`` is authoritative. This
script validates release manifests, package and lock versions, changelog
coverage, and reports (but never modifies) the Git worktree state.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
REQUIRED_FILES = (
    "novel_factory/version.py",
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
    "desktop/package.json",
    "desktop/package-lock.json",
    "CHANGELOG.md",
)


@dataclass(frozen=True)
class PreflightResult:
    """One deterministic preflight outcome."""

    status: str
    name: str
    detail: str

    @property
    def passed(self) -> bool:
        return self.status != "FAIL"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _runtime_version(root: Path) -> str:
    content = _read_text(root / "novel_factory/version.py")
    match = re.search(
        r'^__version__(?:\s*:\s*str)?\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
        content,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError("missing __version__ assignment")
    return match.group("version")


def _pyproject_version(root: Path) -> str:
    content = _read_text(root / "pyproject.toml")
    project = re.search(
        r"^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)",
        content,
        flags=re.MULTILINE | re.DOTALL,
    )
    if project is None:
        raise ValueError("missing [project] section")
    match = re.search(
        r'^version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
        project.group("body"),
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError("missing [project].version")
    return match.group("version")


def _uv_lock_version(root: Path) -> str:
    content = _read_text(root / "uv.lock")
    match = re.search(
        r'\[\[package\]\]\s*\nname = "novel-factory"\s*\nversion = "(?P<version>[^"]+)"\s*\nsource = \{ editable = "\." \}',
        content,
    )
    if match is None:
        raise ValueError("missing editable novel-factory package")
    return match.group("version")


def _json_version(root: Path, relative_path: str) -> str:
    with (root / relative_path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    version = data.get("version")
    if not isinstance(version, str):
        raise ValueError("missing string version")
    return version


def _lock_root_version(root: Path, relative_path: str) -> str:
    with (root / relative_path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    version = data.get("packages", {}).get("", {}).get("version")
    if not isinstance(version, str):
        raise ValueError('missing packages[""].version')
    return version


def _load_version(
    results: list[PreflightResult],
    name: str,
    loader: Callable[[], str],
) -> Optional[str]:
    try:
        return loader()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        results.append(
            PreflightResult("FAIL", name, f"cannot read version ({type(exc).__name__})")
        )
        return None


def _version_detail(expected: str, actual: Optional[str]) -> str:
    if actual is None:
        return "version unavailable"
    if not SEMVER_PATTERN.fullmatch(actual):
        return "version is not major.minor.patch"
    if actual == expected:
        return actual
    return f"expected {expected}, got {actual}"


def _worktree_result(root: Path) -> PreflightResult:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PreflightResult(
            "INFO", "git.worktree", f"status unavailable ({type(exc).__name__})"
        )
    if result.returncode != 0:
        return PreflightResult("INFO", "git.worktree", "not a Git worktree")
    changed_count = len([line for line in result.stdout.splitlines() if line.strip()])
    detail = "clean" if changed_count == 0 else f"{changed_count} changed path(s); review before release"
    return PreflightResult("INFO", "git.worktree", detail)


def run_preflight(root: Path) -> list[PreflightResult]:
    """Evaluate the repository without mutating it."""
    root = root.resolve()
    results: list[PreflightResult] = []

    for relative_path in REQUIRED_FILES:
        exists = (root / relative_path).is_file()
        results.append(
            PreflightResult(
                "PASS" if exists else "FAIL",
                f"manifest.{relative_path}",
                "present" if exists else "missing",
            )
        )

    runtime = _load_version(results, "version.runtime.read", lambda: _runtime_version(root))
    if runtime is None:
        results.append(PreflightResult("FAIL", "version.runtime.semver", "version unavailable"))
    else:
        results.append(
            PreflightResult(
                "PASS" if SEMVER_PATTERN.fullmatch(runtime) else "FAIL",
                "version.runtime.semver",
                runtime if SEMVER_PATTERN.fullmatch(runtime) else "version is not major.minor.patch",
            )
        )

    version_loaders: tuple[tuple[str, Callable[[], str]], ...] = (
        ("version.pyproject", lambda: _pyproject_version(root)),
        ("version.uv-lock", lambda: _uv_lock_version(root)),
        ("version.frontend-package", lambda: _json_version(root, "frontend/package.json")),
        ("version.frontend-lock", lambda: _json_version(root, "frontend/package-lock.json")),
        ("version.frontend-lock-root", lambda: _lock_root_version(root, "frontend/package-lock.json")),
        ("version.desktop-package", lambda: _json_version(root, "desktop/package.json")),
        ("version.desktop-lock", lambda: _json_version(root, "desktop/package-lock.json")),
        ("version.desktop-lock-root", lambda: _lock_root_version(root, "desktop/package-lock.json")),
    )
    expected = runtime or "<runtime-unavailable>"
    loaded_versions: dict[str, Optional[str]] = {}
    for name, loader in version_loaders:
        actual = _load_version(results, f"{name}.read", loader)
        loaded_versions[name] = actual
        detail = _version_detail(expected, actual)
        passed = runtime is not None and actual == runtime and SEMVER_PATTERN.fullmatch(actual or "")
        results.append(PreflightResult("PASS" if passed else "FAIL", name, detail))

    for surface in ("frontend", "desktop"):
        package = loaded_versions[f"version.{surface}-package"]
        lock = loaded_versions[f"version.{surface}-lock"]
        lock_root = loaded_versions[f"version.{surface}-lock-root"]
        aligned = package is not None and package == lock == lock_root
        results.append(
            PreflightResult(
                "PASS" if aligned else "FAIL",
                f"lock.{surface}",
                "package, lock, and lock root aligned" if aligned else "package and lock roots differ",
            )
        )

    if runtime is None:
        results.append(PreflightResult("FAIL", "changelog.target-version", "runtime version unavailable"))
    else:
        try:
            changelog = _read_text(root / "CHANGELOG.md")
            found = re.search(rf"^## v{re.escape(runtime)}(?:\s|$)", changelog, re.MULTILINE) is not None
            results.append(
                PreflightResult(
                    "PASS" if found else "FAIL",
                    "changelog.target-version",
                    f"v{runtime} entry present" if found else f"missing v{runtime} heading",
                )
            )
        except OSError as exc:
            results.append(
                PreflightResult(
                    "FAIL", "changelog.target-version", f"cannot read changelog ({type(exc).__name__})"
                )
            )

    results.append(_worktree_result(root))
    return results


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the read-only Novelos release preflight")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root to inspect (defaults to this script's repository)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    results = run_preflight(args.root)
    for result in results:
        print(f"{result.status:<4} {result.name}: {result.detail}")

    failures = sum(result.status == "FAIL" for result in results)
    checks = sum(result.status in {"PASS", "FAIL"} for result in results)
    if failures:
        print(f"\nRelease preflight: FAIL ({failures} failure(s), {checks} checks)")
        return 1
    print(f"\nRelease preflight: PASS ({checks}/{checks} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
