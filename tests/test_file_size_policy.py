"""File size policy enforcement for CLI modularization (v3.7.2 Round 1).

Rules:
  - novel_factory/cli.py must be <= 150 lines
  - All novel_factory/cli_app/**/*.py files must be <= 1000 lines
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent / "novel_factory"


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


class TestCLISizePolicy:
    """Verify cli.py is a thin wrapper (<= 150 lines)."""

    def test_cli_py_thin_wrapper(self):
        path = ROOT / "cli.py"
        lines = _count_lines(path)
        assert lines <= 150, f"cli.py has {lines} lines, must be <= 150"


class TestCLIAppSizePolicy:
    """Verify all cli_app/**/*.py files are <= 1000 lines."""

    @pytest.fixture(params=[
        p.relative_to(ROOT)
        for p in (ROOT / "cli_app").rglob("*.py")
    ])
    def cli_app_py(self, request):
        return ROOT / request.param

    def test_file_under_1000_lines(self, cli_app_py):
        lines = _count_lines(cli_app_py)
        assert lines <= 1000, f"{cli_app_py.relative_to(ROOT)} has {lines} lines, must be <= 1000"
