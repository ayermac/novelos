"""Tests for v3.1 error envelope in CLI commands.

Tests that CLI commands return proper JSON envelope when LLM configuration is missing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cli(args: list[str], expect_json: bool = True) -> tuple[int, str, str]:
    """Run CLI command and return exit code, stdout, stderr."""
    cmd = [sys.executable, "-m", "novel_factory.cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


class TestRunChapterErrorEnvelope:
    """Test run-chapter returns JSON envelope on LLM config errors."""

    def test_run_chapter_real_mode_missing_env_returns_json_envelope(self, tmp_path):
        """run-chapter --llm-mode real --json with missing env returns JSON envelope."""
        db_path = tmp_path / "test.db"
        
        # Create a config with llm_profiles but no actual env vars
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: author
llm_profiles:
  author:
    provider: openai_compatible
    base_url_env: MISSING_BASE_URL
    api_key_env: MISSING_API_KEY
    model: gpt-4o-mini
agent_llm:
  author: author
""")
        
        # Init DB and seed demo
        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])
        
        # Run chapter with real mode (will fail due to missing env)
        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "--config", str(config_path),
            "--llm-mode", "real",
            "run-chapter",
            "--project-id", "demo",
            "--chapter", "1",
            "--json",
        ])
        
        # Should return error code
        assert code != 0, f"Expected non-zero exit code, got {code}"
        
        # stdout should be valid JSON
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:200]}\nError: {e}")
        
        # Should have envelope format
        assert "ok" in result, f"Missing 'ok' in result: {result}"
        assert "error" in result, f"Missing 'error' in result: {result}"
        assert "data" in result, f"Missing 'data' in result: {result}"
        
        # Should indicate failure
        assert result["ok"] is False, f"Expected ok=false, got {result['ok']}"
        assert result["error"], f"Expected error message, got: {result['error']}"
        # data should contain error details
        assert isinstance(result["data"], dict), f"Expected data to be dict, got: {type(result['data'])}"
        assert "error" in result["data"], f"Expected 'error' in data, got: {result['data']}"
        
        # Should NOT contain traceback in stdout
        assert "Traceback" not in stdout, f"stdout contains traceback: {stdout[:500]}"
        
        # Should NOT contain traceback in stderr (ideally)
        # Note: Some logging might appear in stderr, but no Python traceback
        if "Traceback" in stderr:
            # Check it's not a Python traceback (just logging)
            assert "File " not in stderr or "Error: " not in stderr, \
                f"stderr contains Python traceback: {stderr[:500]}"


class TestBatchRunErrorEnvelope:
    """Test batch run returns JSON envelope on LLM config errors."""

    def test_batch_run_real_mode_missing_env_returns_json_envelope(self, tmp_path):
        """batch run --llm-mode real --json with missing env returns JSON envelope."""
        db_path = tmp_path / "test.db"
        
        # Create a config with llm_profiles but no actual env vars
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: author
llm_profiles:
  author:
    provider: openai_compatible
    base_url_env: MISSING_BASE_URL
    api_key_env: MISSING_API_KEY
    model: gpt-4o-mini
agent_llm:
  author: author
""")
        
        # Init DB and seed demo
        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])
        
        # Run batch with real mode (will fail due to missing env)
        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "--config", str(config_path),
            "--llm-mode", "real",
            "batch", "run",
            "--project-id", "demo",
            "--from-chapter", "1",
            "--to-chapter", "1",
            "--json",
        ])
        
        # Should return error code
        assert code != 0, f"Expected non-zero exit code, got {code}"
        
        # stdout should be valid JSON
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:200]}\nError: {e}")
        
        # Should have envelope format
        assert "ok" in result, f"Missing 'ok' in result: {result}"
        assert "error" in result, f"Missing 'error' in result: {result}"
        assert "data" in result, f"Missing 'data' in result: {result}"
        
        # Should indicate failure
        assert result["ok"] is False, f"Expected ok=false, got {result['ok']}"
        assert result["error"], f"Expected error message, got: {result['error']}"
        
        # Should NOT contain traceback in stdout
        assert "Traceback" not in stdout, f"stdout contains traceback: {stdout[:500]}"


class TestScoutErrorEnvelope:
    """Test scout returns JSON envelope on LLM config errors."""

    def test_scout_real_mode_missing_env_returns_json_envelope(self, tmp_path):
        """scout --llm-mode real --json with missing env returns JSON envelope."""
        db_path = tmp_path / "test.db"
        
        # Create a config with llm_profiles but no actual env vars
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: scout
llm_profiles:
  scout:
    provider: openai_compatible
    base_url_env: MISSING_BASE_URL
    api_key_env: MISSING_API_KEY
    model: gpt-4o-mini
agent_llm:
  scout: scout
""")
        
        # Init DB
        run_cli(["--db-path", str(db_path), "init-db"])
        
        # Run scout with real mode (will fail due to missing env)
        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "--config", str(config_path),
            "--llm-mode", "real",
            "scout",
            "--project-id", "demo",
            "--json",
        ])
        
        # Should return error code
        assert code != 0, f"Expected non-zero exit code, got {code}"
        
        # stdout should be valid JSON
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:200]}\nError: {e}")
        
        # Should have envelope format
        assert "ok" in result, f"Missing 'ok' in result: {result}"
        assert "error" in result, f"Missing 'error' in result: {result}"
        assert "data" in result, f"Missing 'data' in result: {result}"
        
        # Should indicate failure
        assert result["ok"] is False, f"Expected ok=false, got {result['ok']}"
        assert result["error"], f"Expected error message, got: {result['error']}"
        
        # Should NOT contain traceback in stdout
        assert "Traceback" not in stdout, f"stdout contains traceback: {stdout[:500]}"


class TestContinuityCheckErrorEnvelope:
    """Test continuity-check returns JSON envelope on LLM config errors."""

    def test_continuity_check_real_mode_missing_env_returns_json_envelope(self, tmp_path):
        """continuity-check --llm-mode real --json with missing env returns JSON envelope."""
        db_path = tmp_path / "test.db"
        
        # Create a config with llm_profiles but no actual env vars
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: continuity_checker
llm_profiles:
  continuity_checker:
    provider: openai_compatible
    base_url_env: MISSING_BASE_URL
    api_key_env: MISSING_API_KEY
    model: gpt-4o-mini
agent_llm:
  continuity_checker: continuity_checker
""")
        
        # Init DB and seed demo
        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])
        
        # Run continuity-check with real mode (will fail due to missing env)
        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "--config", str(config_path),
            "--llm-mode", "real",
            "continuity-check",
            "--project-id", "demo",
            "--from-chapter", "1",
            "--to-chapter", "1",
            "--json",
        ])
        
        # Should return error code
        assert code != 0, f"Expected non-zero exit code, got {code}"
        
        # stdout should be valid JSON
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:200]}\nError: {e}")
        
        # Should have envelope format
        assert "ok" in result, f"Missing 'ok' in result: {result}"
        assert "error" in result, f"Missing 'error' in result: {result}"
        assert "data" in result, f"Missing 'data' in result: {result}"
        
        # Should indicate failure
        assert result["ok"] is False, f"Expected ok=false, got {result['ok']}"
        assert result["error"], f"Expected error message, got: {result['error']}"
        
        # Should NOT contain traceback in stdout
        assert "Traceback" not in stdout, f"stdout contains traceback: {stdout[:500]}"


class TestArchitectSuggestErrorEnvelope:
    """Test architect suggest returns JSON envelope on LLM config errors."""

    def test_architect_suggest_real_mode_missing_env_returns_json_envelope(self, tmp_path):
        """architect suggest --llm-mode real --json with missing env returns JSON envelope."""
        db_path = tmp_path / "test.db"
        
        # Create a config with llm_profiles but no actual env vars
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: architect
llm_profiles:
  architect:
    provider: openai_compatible
    base_url_env: MISSING_BASE_URL
    api_key_env: MISSING_API_KEY
    model: gpt-4o-mini
agent_llm:
  architect: architect
""")
        
        # Init DB
        run_cli(["--db-path", str(db_path), "init-db"])
        
        # Run architect suggest with real mode (will fail due to missing env)
        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "--config", str(config_path),
            "--llm-mode", "real",
            "architect", "suggest",
            "--project-id", "demo",
            "--json",
        ])
        
        # Should return error code
        assert code != 0, f"Expected non-zero exit code, got {code}"
        
        # stdout should be valid JSON
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:200]}\nError: {e}")
        
        # Should have envelope format
        assert "ok" in result, f"Missing 'ok' in result: {result}"
        assert "error" in result, f"Missing 'error' in result: {result}"
        assert "data" in result, f"Missing 'data' in result: {result}"
        
        # Should indicate failure
        assert result["ok"] is False, f"Expected ok=false, got {result['ok']}"
        assert result["error"], f"Expected error message, got: {result['error']}"
        
        # Should NOT contain traceback in stdout
        assert "Traceback" not in stdout, f"stdout contains traceback: {stdout[:500]}"
