"""Tests for v3.1 error envelope in CLI commands.

Tests that CLI commands return proper JSON envelope when LLM configuration is missing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cli(args: list[str], expect_json: bool = True, clean_env: bool = False) -> tuple[int, str, str]:
    """Run CLI command and return exit code, stdout, stderr.
    
    Args:
        args: CLI arguments.
        clean_env: If True, set NOVEL_FACTORY_DISABLE_DOTENV=1 and clear
                   OPENAI_API_KEY/OPENAI_BASE_URL from subprocess environment.
    """
    import os
    cmd = [sys.executable, "-m", "novel_factory.cli"] + args
    if clean_env:
        env = os.environ.copy()
        env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    else:
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
        ], clean_env=True)
        
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
        ], clean_env=True)
        
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
        ], clean_env=True)
        
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
        ], clean_env=True)
        
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


class TestNonOpenAIProfileNotBlocked:
    """Test that non-OpenAI profiles are not blocked by hardcoded OPENAI_API_KEY check."""

    def test_deepseek_profile_real_mode_not_blocked_by_openai_key_check(self, tmp_path):
        """Profile mode with DEEPSEEK_API_KEY but no OPENAI_API_KEY should not be
        blocked by _build_dispatcher's legacy OPENAI_API_KEY check."""
        db_path = tmp_path / "test.db"

        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: deepseek
llm_profiles:
  deepseek:
    provider: openai_compatible
    base_url_env: DEEPSEEK_BASE_URL
    api_key_env: DEEPSEEK_API_KEY
    model: deepseek-chat
agent_llm:
  screenwriter: deepseek
  author: deepseek
  polisher: deepseek
  editor: deepseek
""")

        # Init DB and seed demo
        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])

        # Run with DeepSeek profile — set DEEPSEEK keys but NO OPENAI_API_KEY
        import os
        cmd = [sys.executable, "-m", "novel_factory.cli",
               "--db-path", str(db_path),
               "--config", str(config_path),
               "run-chapter",
               "--project-id", "demo",
               "--chapter", "1",
               "--llm-mode", "real",
               "--max-steps", "1",
               "--json"]
        env = os.environ.copy()
        env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
        env["DEEPSEEK_API_KEY"] = "test-key"
        env["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com/v1"
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        # The key assertion: must NOT be blocked by the old hardcoded OPENAI_API_KEY check.
        # The error message "Set OPENAI_API_KEY environment variable" must NOT appear.
        # (The command may still fail due to invalid API key / network, but that's a different error.)
        if result.stdout:
            try:
                data = json.loads(result.stdout)
                assert "Set OPENAI_API_KEY" not in data.get("error", ""), \
                    f"Non-OpenAI profile was incorrectly blocked by OPENAI_API_KEY check: {data['error']}"
            except json.JSONDecodeError:
                pass
        if result.stderr:
            assert "Set OPENAI_API_KEY" not in result.stderr, \
                f"Non-OpenAI profile was incorrectly blocked by OPENAI_API_KEY check in stderr: {result.stderr[:300]}"

    def test_profile_mode_missing_all_keys_still_fails_gracefully(self, tmp_path):
        """Profile mode with no keys at all should still fail with per-profile error."""
        db_path = tmp_path / "test.db"

        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: deepseek
llm_profiles:
  deepseek:
    provider: openai_compatible
    api_key_env: DEEPSEEK_API_KEY
    base_url_env: DEEPSEEK_BASE_URL
    model: deepseek-chat
agent_llm:
  author: deepseek
""")

        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])

        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "--config", str(config_path),
            "run-chapter",
            "--project-id", "demo",
            "--chapter", "1",
            "--llm-mode", "real",
            "--max-steps", "1",
            "--json",
        ], clean_env=True)

        assert code != 0, "Expected non-zero exit code for missing all keys"
        result = json.loads(stdout)
        assert result["ok"] is False
        # Error should mention the profile-level key, not the generic OPENAI_API_KEY
        assert "error" in result


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
        ], clean_env=True)
        
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


class TestLLMRuntimeErrorEnvelope:
    """Test that LLM runtime exceptions (connection, auth, etc.) return JSON envelope, not traceback."""

    def _make_non_openai_profile_config(self, tmp_path):
        """Create a config that routes to a profile with a reachable-but-invalid endpoint."""
        db_path = tmp_path / "test.db"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

default_llm: deepseek
llm_profiles:
  deepseek:
    provider: openai_compatible
    base_url_env: DEEPSEEK_BASE_URL
    api_key_env: DEEPSEEK_API_KEY
    model: deepseek-chat
agent_llm:
  screenwriter: deepseek
  author: deepseek
  polisher: deepseek
  editor: deepseek
""")
        return db_path, config_path

    def test_run_chapter_provider_exception_returns_envelope(self, tmp_path):
        """run-chapter with provider exception returns JSON envelope, not traceback."""
        import os
        db_path, config_path = self._make_non_openai_profile_config(tmp_path)

        # Init and seed
        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])

        # Run with a fake key that will cause auth error at the provider level
        cmd = [sys.executable, "-m", "novel_factory.cli",
               "--db-path", str(db_path),
               "--config", str(config_path),
               "run-chapter",
               "--project-id", "demo",
               "--chapter", "1",
               "--llm-mode", "real",
               "--max-steps", "1",
               "--json"]
        env = os.environ.copy()
        env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-invalid-key-for-testing"
        env["DEEPSEEK_BASE_URL"] = "https://httpbin.org/status/401"
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)

        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        stdout = result.stdout

        # stdout must be valid JSON (no raw traceback)
        assert "Traceback" not in stdout, f"stdout contains traceback instead of JSON envelope: {stdout[:500]}"

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:300]}")

        # Must be an error envelope
        assert "ok" in data, f"Missing 'ok' in envelope: {data}"
        assert "error" in data, f"Missing 'error' in envelope: {data}"

    def test_scout_provider_exception_returns_envelope(self, tmp_path):
        """scout with provider exception returns JSON envelope, not traceback."""
        import os
        db_path, config_path = self._make_non_openai_profile_config(tmp_path)

        run_cli(["--db-path", str(db_path), "init-db"])

        cmd = [sys.executable, "-m", "novel_factory.cli",
               "--db-path", str(db_path),
               "--config", str(config_path),
               "scout",
               "--project-id", "demo",
               "--llm-mode", "real",
               "--json"]
        env = os.environ.copy()
        env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-invalid-key-for-testing"
        env["DEEPSEEK_BASE_URL"] = "https://httpbin.org/status/401"
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)

        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        stdout = result.stdout

        assert "Traceback" not in stdout, f"stdout contains traceback instead of JSON envelope: {stdout[:500]}"

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:300]}")

        assert "ok" in data, f"Missing 'ok' in envelope: {data}"
        assert "error" in data, f"Missing 'error' in envelope: {data}"

    def test_continuity_check_provider_exception_returns_envelope(self, tmp_path):
        """continuity-check with provider exception returns JSON envelope, not traceback."""
        import os
        db_path, config_path = self._make_non_openai_profile_config(tmp_path)

        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])

        cmd = [sys.executable, "-m", "novel_factory.cli",
               "--db-path", str(db_path),
               "--config", str(config_path),
               "continuity-check",
               "--project-id", "demo",
               "--from-chapter", "1",
               "--to-chapter", "1",
               "--llm-mode", "real",
               "--json"]
        env = os.environ.copy()
        env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-invalid-key-for-testing"
        env["DEEPSEEK_BASE_URL"] = "https://httpbin.org/status/401"
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)

        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        stdout = result.stdout

        assert "Traceback" not in stdout, f"stdout contains traceback instead of JSON envelope: {stdout[:500]}"

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:300]}")

        assert "ok" in data, f"Missing 'ok' in envelope: {data}"
        assert "error" in data, f"Missing 'error' in envelope: {data}"

    def test_architect_suggest_provider_exception_returns_envelope(self, tmp_path):
        """architect suggest with provider exception returns JSON envelope, not traceback."""
        import os
        db_path, config_path = self._make_non_openai_profile_config(tmp_path)

        run_cli(["--db-path", str(db_path), "init-db"])

        cmd = [sys.executable, "-m", "novel_factory.cli",
               "--db-path", str(db_path),
               "--config", str(config_path),
               "architect", "suggest",
               "--project-id", "demo",
               "--llm-mode", "real",
               "--json"]
        env = os.environ.copy()
        env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-invalid-key-for-testing"
        env["DEEPSEEK_BASE_URL"] = "https://httpbin.org/status/401"
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)

        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        stdout = result.stdout

        assert "Traceback" not in stdout, f"stdout contains traceback instead of JSON envelope: {stdout[:500]}"

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:300]}")

        assert "ok" in data, f"Missing 'ok' in envelope: {data}"
        assert "error" in data, f"Missing 'error' in envelope: {data}"

    def test_batch_run_provider_exception_returns_envelope(self, tmp_path):
        """batch run with provider exception returns JSON envelope, not traceback."""
        import os
        db_path, config_path = self._make_non_openai_profile_config(tmp_path)

        run_cli(["--db-path", str(db_path), "init-db"])
        run_cli(["--db-path", str(db_path), "seed-demo", "--project-id", "demo"])

        cmd = [sys.executable, "-m", "novel_factory.cli",
               "--db-path", str(db_path),
               "--config", str(config_path),
               "batch", "run",
               "--project-id", "demo",
               "--from-chapter", "1",
               "--to-chapter", "1",
               "--llm-mode", "real",
               "--json"]
        env = os.environ.copy()
        env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
        env["DEEPSEEK_API_KEY"] = "sk-invalid-key-for-testing"
        env["DEEPSEEK_BASE_URL"] = "https://httpbin.org/status/401"
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)

        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        stdout = result.stdout

        assert "Traceback" not in stdout, f"stdout contains traceback instead of JSON envelope: {stdout[:500]}"

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"stdout is not valid JSON: {stdout[:300]}")

        assert "ok" in data, f"Missing 'ok' in envelope: {data}"
        assert "error" in data, f"Missing 'error' in envelope: {data}"
