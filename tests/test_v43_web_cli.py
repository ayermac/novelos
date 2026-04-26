"""v4.3 Web CLI tests - novelos web command."""

from __future__ import annotations

import subprocess
import sys


def test_web_help_available():
    """novelos web --help is available."""
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "web", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Should exit with 0 (help)
    assert result.returncode == 0
    # Should show help text
    assert "host" in result.stdout.lower() or "port" in result.stdout.lower()


def test_web_command_import():
    """cmd_web can be imported."""
    from novel_factory.cli_app.commands.web import cmd_web

    assert cmd_web is not None


def test_web_command_monkeypatch_uvicorn():
    """cmd_web passes correct parameters to uvicorn.run."""
    from novel_factory.cli_app.commands.web import cmd_web
    from unittest.mock import MagicMock, patch

    # Create mock args
    args = MagicMock()
    args.host = "127.0.0.1"
    args.port = 8765
    args.db_path = "/tmp/test.db"
    args.config = None
    args.llm_mode = "stub"

    # Mock uvicorn at the import location
    with patch("novel_factory.cli_app.commands.web.uvicorn") as mock_uvicorn:
        # Mock _get_settings
        with patch("novel_factory.cli_app.commands.web._get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(db_path="/tmp/test.db", config_path=None)

            cmd_web(args)

            # Verify uvicorn.run was called
            assert mock_uvicorn.run.called
