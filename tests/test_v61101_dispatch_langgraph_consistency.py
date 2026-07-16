"""v6.11.01 P0: Verify CLI and API production paths converge on LangGraph.

After v6.11.01 P0, both:
- CLI ``cmd_run_chapter`` (direct ``run_with_graph``)
- API ``get_dispatcher`` → ``Dispatcher.run_chapter`` (delegates to ``run_with_graph``)

must produce the same LangGraph entry point so that timeout/retry semantics are
identical. This test verifies the delegation contract without running a full
workflow.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from novel_factory.dispatcher import Dispatcher
from novel_factory.config.settings import Settings


@pytest.fixture
def minimal_settings() -> Settings:
    """Settings sufficient for Dispatcher.run_chapter to choose LangGraph."""
    return Settings(
        db_path=":memory:",
        llm={"api_key": "test", "model": "test-model"},
    )


def test_dispatcher_run_chapter_delegates_to_run_with_graph_when_settings_present(
    minimal_settings,
):
    """When Dispatcher has settings, run_chapter must call run_with_graph."""
    repo = MagicMock()
    repo.get_chapter.return_value = {"id": "ch1", "status": "planned"}

    dispatcher = Dispatcher(
        repo=repo,
        llm=MagicMock(),
        max_retries=3,
        settings=minimal_settings,
        llm_mode="stub",
    )

    with patch("novel_factory.workflow.runner.run_with_graph") as mock_run:
        mock_run.return_value = {
            "chapter_status": "published",
            "steps": [],
            "error": None,
            "requires_human": False,
        }

        result = dispatcher.run_chapter(
            project_id="demo",
            chapter_number=1,
            max_steps=20,
        )

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == "demo"          # project_id
        assert args[1] == 1              # chapter_number
        assert args[2] is minimal_settings  # settings
        assert kwargs["llm_mode"] == "stub"
        assert result["chapter_status"] == "published"


def test_dispatcher_run_chapter_uses_legacy_fallback_without_settings():
    """When Dispatcher lacks settings, run_chapter falls back to legacy loop."""
    repo = MagicMock()
    repo.get_chapter.return_value = {"id": "ch1", "status": "planned"}

    dispatcher = Dispatcher(
        repo=repo,
        llm=MagicMock(),
        max_retries=3,
    )

    with patch("novel_factory.workflow.runner.run_with_graph") as mock_run:
        dispatcher.run_chapter(
            project_id="demo",
            chapter_number=1,
            max_steps=20,
        )

        mock_run.assert_not_called()
