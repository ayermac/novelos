"""pytest configuration and shared fixtures."""

import sys
from pathlib import Path

import pytest

# Ensure novel_factory is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def disable_dotenv_for_tests(monkeypatch):
    """Disable .env loading for all tests to prevent project root .env pollution.
    
    This ensures tests that verify "missing API key" behavior are not
    accidentally passing because of keys in the project's .env file.
    
    Individual tests that need .env can temporarily re-enable it by
    removing the env var with monkeypatch.delenv().
    """
    monkeypatch.setenv("NOVEL_FACTORY_DISABLE_DOTENV", "1")
