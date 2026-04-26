"""File size policy enforcement for CLI, Repository & Dispatcher modularization (v3.7.2).

Rules:
  - novel_factory/cli.py must be <= 150 lines
  - All novel_factory/cli_app/**/*.py files must be <= 1000 lines
  - novel_factory/db/repository.py must be <= 300 lines
  - All novel_factory/db/repositories/**/*.py files must be <= 1000 lines
  - novel_factory/dispatcher.py must be <= 300 lines
  - All novel_factory/dispatch/**/*.py files must be <= 1000 lines
  - All novel_factory/llm/**/*.py files must be <= 1000 lines (v3.9)
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


class TestRepositorySizePolicy:
    """Verify db/repository.py is a thin facade (<= 300 lines)."""

    def test_repository_py_thin_facade(self):
        path = ROOT / "db" / "repository.py"
        lines = _count_lines(path)
        assert lines <= 300, f"db/repository.py has {lines} lines, must be <= 300"


class TestRepositoriesSizePolicy:
    """Verify all db/repositories/**/*.py files are <= 1000 lines."""

    @pytest.fixture(params=[
        p.relative_to(ROOT)
        for p in (ROOT / "db" / "repositories").rglob("*.py")
    ])
    def repo_py(self, request):
        return ROOT / request.param

    def test_file_under_1000_lines(self, repo_py):
        lines = _count_lines(repo_py)
        assert lines <= 1000, f"{repo_py.relative_to(ROOT)} has {lines} lines, must be <= 1000"


class TestDispatcherSizePolicy:
    """Verify dispatcher.py is a thin facade (<= 300 lines)."""

    def test_dispatcher_py_thin_facade(self):
        path = ROOT / "dispatcher.py"
        lines = _count_lines(path)
        assert lines <= 300, f"dispatcher.py has {lines} lines, must be <= 300"


class TestDispatchSizePolicy:
    """Verify all dispatch/**/*.py files are <= 1000 lines."""

    @pytest.fixture(params=[
        p.relative_to(ROOT)
        for p in (ROOT / "dispatch").rglob("*.py")
    ])
    def dispatch_py(self, request):
        return ROOT / request.param

    def test_file_under_1000_lines(self, dispatch_py):
        lines = _count_lines(dispatch_py)
        assert lines <= 1000, f"{dispatch_py.relative_to(ROOT)} has {lines} lines, must be <= 1000"


class TestLLMSizePolicy:
    """Verify all llm/**/*.py files are <= 1000 lines (v3.9)."""

    @pytest.fixture(params=[
        p.relative_to(ROOT)
        for p in (ROOT / "llm").rglob("*.py")
    ])
    def llm_py(self, request):
        return ROOT / request.param

    def test_file_under_1000_lines(self, llm_py):
        lines = _count_lines(llm_py)
        assert lines <= 1000, f"{llm_py.relative_to(ROOT)} has {lines} lines, must be <= 1000"
