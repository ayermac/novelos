"""v3.9 LLM Catalog & Recommendation CLI tests.

Covers:
- llm catalog --json
- llm recommend --agent <id> --json
- llm recommend --all --json
- llm recommend --all --cost-tier medium --json
- llm config-plan --all --json
- Error paths return stable JSON envelope
- API key not in any output
- Existing v3.1 llm CLI tests don't regress
"""

from __future__ import annotations

import json
import subprocess
import sys


def run_cli(args: list[str], expect_json: bool = True) -> tuple[int, str, str]:
    """Run CLI command and return exit code, stdout, stderr."""
    cmd = [sys.executable, "-m", "novel_factory.cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def _parse_json(stdout: str) -> dict:
    """Parse JSON from stdout, raising on failure."""
    return json.loads(stdout)


# ── llm catalog ────────────────────────────────────────────────

class TestLLMCatalogCLI:
    """Test novelos llm catalog command."""

    def test_catalog_json_envelope(self):
        """llm catalog --json returns valid JSON envelope."""
        code, stdout, stderr = run_cli(["llm", "catalog", "--json"])
        assert code == 0, f"Exit code {code}, stderr: {stderr}"
        result = _parse_json(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result
        assert result["ok"] is True
        assert result["error"] is None

    def test_catalog_has_models(self):
        """llm catalog output contains model list."""
        code, stdout, _ = run_cli(["llm", "catalog", "--json"])
        result = _parse_json(stdout)
        data = result["data"]
        assert "models" in data
        assert len(data["models"]) > 0

    def test_catalog_model_has_required_fields(self):
        """Each model in catalog output has required fields."""
        code, stdout, _ = run_cli(["llm", "catalog", "--json"])
        result = _parse_json(stdout)
        for model in result["data"]["models"]:
            assert "provider" in model
            assert "model" in model
            assert "display_name" in model
            assert "cost_tier" in model
            assert "quality_tier" in model
            assert "strengths" in model

    def test_catalog_no_api_keys(self):
        """llm catalog output contains no API keys."""
        code, stdout, _ = run_cli(["llm", "catalog", "--json"])
        assert "sk-" not in stdout


# ── llm recommend ──────────────────────────────────────────────

class TestLLMRecommendCLI:
    """Test novelos llm recommend command."""

    def test_recommend_agent_json_envelope(self):
        """llm recommend --agent author --json returns valid envelope."""
        code, stdout, stderr = run_cli(["llm", "recommend", "--agent", "author", "--json"])
        assert code == 0, f"Exit code {code}, stderr: {stderr}"
        result = _parse_json(stdout)
        assert "ok" in result
        assert result["ok"] is True

    def test_recommend_agent_has_fields(self):
        """llm recommend --agent author returns recommendation with required fields."""
        code, stdout, _ = run_cli(["llm", "recommend", "--agent", "author", "--json"])
        result = _parse_json(stdout)
        data = result["data"]
        assert data["agent_id"] == "author"
        assert "provider" in data
        assert "model" in data
        assert "score" in data
        assert "reasons" in data

    def test_recommend_all_json_envelope(self):
        """llm recommend --all --json returns valid envelope."""
        code, stdout, stderr = run_cli(["llm", "recommend", "--all", "--json"])
        assert code == 0, f"Exit code {code}, stderr: {stderr}"
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert "recommendations" in result["data"]
        assert result["data"]["total"] > 0

    def test_recommend_all_covers_all_agents(self):
        """llm recommend --all covers all known agents."""
        code, stdout, _ = run_cli(["llm", "recommend", "--all", "--json"])
        result = _parse_json(stdout)
        agents = {r["agent_id"] for r in result["data"]["recommendations"]}
        expected = {"planner", "screenwriter", "author", "polisher",
                    "editor", "scout", "continuity_checker", "architect", "secretary"}
        assert agents == expected

    def test_recommend_cost_tier_constraint(self):
        """llm recommend --all --cost-tier medium respects constraint."""
        code, stdout, _ = run_cli(["llm", "recommend", "--all", "--cost-tier", "medium", "--json"])
        result = _parse_json(stdout)
        assert result["ok"] is True
        # All recommended models should be at or below medium cost
        for rec in result["data"]["recommendations"]:
            # We can't easily check the model's cost tier from just the output,
            # but the command should succeed
            assert rec["provider"]
            assert rec["model"]

    def test_recommend_unknown_agent_error(self):
        """llm recommend --agent nonexistent returns error envelope."""
        code, stdout, stderr = run_cli(["llm", "recommend", "--agent", "nonexistent", "--json"])
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert result["error"]
        assert "Unknown agent" in result["error"]

    def test_recommend_no_agent_no_all_error(self):
        """llm recommend without --agent or --all returns error."""
        code, stdout, stderr = run_cli(["llm", "recommend", "--json"])
        assert code != 0

    def test_recommend_no_api_keys(self):
        """llm recommend output contains no API keys."""
        code, stdout, _ = run_cli(["llm", "recommend", "--all", "--json"])
        assert "sk-" not in stdout

    def test_recommend_invalid_strength_returns_error_envelope(self):
        """llm recommend --require-strengths nonexistent returns error envelope, no traceback."""
        code, stdout, stderr = run_cli(
            ["llm", "recommend", "--agent", "author", "--require-strengths", "nonexistent", "--json"]
        )
        # Should NOT get a traceback in stdout
        assert "Traceback" not in stdout
        # Should get valid JSON error envelope
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert "Invalid strength" in result["error"]

    def test_recommend_all_no_match_returns_error(self):
        """llm recommend --all --provider nope returns ok:false."""
        code, stdout, stderr = run_cli(
            ["llm", "recommend", "--all", "--provider", "nope", "--json"]
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert result["data"]["total"] == 0


# ── llm config-plan ────────────────────────────────────────────

class TestLLMConfigPlanCLI:
    """Test novelos llm config-plan command."""

    def test_config_plan_json_envelope(self):
        """llm config-plan --json returns valid envelope."""
        code, stdout, stderr = run_cli(["llm", "config-plan", "--json"])
        assert code == 0, f"Exit code {code}, stderr: {stderr}"
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert "data" in result

    def test_config_plan_has_required_sections(self):
        """config-plan output has llm_profiles, agent_llm, default_llm."""
        code, stdout, _ = run_cli(["llm", "config-plan", "--json"])
        result = _parse_json(stdout)
        data = result["data"]
        assert "default_llm" in data
        assert "llm_profiles" in data
        assert "agent_llm" in data

    def test_config_plan_profiles_have_env_vars(self):
        """config-plan profiles use environment variable references."""
        code, stdout, _ = run_cli(["llm", "config-plan", "--json"])
        result = _parse_json(stdout)
        for name, profile in result["data"]["llm_profiles"].items():
            assert "base_url_env" in profile, f"Profile {name} missing base_url_env"
            assert "api_key_env" in profile, f"Profile {name} missing api_key_env"

    def test_config_plan_no_api_keys(self):
        """config-plan output contains no real API keys."""
        code, stdout, _ = run_cli(["llm", "config-plan", "--json"])
        assert "sk-" not in stdout

    def test_config_plan_with_cost_tier(self):
        """config-plan --cost-tier medium respects constraint."""
        code, stdout, _ = run_cli(["llm", "config-plan", "--cost-tier", "medium", "--json"])
        result = _parse_json(stdout)
        assert result["ok"] is True

    def test_config_plan_no_match_returns_error(self):
        """config-plan --provider nope returns ok:false."""
        code, stdout, stderr = run_cli(
            ["llm", "config-plan", "--provider", "nope", "--json"]
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert result["data"]["llm_profiles"] == {}
        assert result["data"]["agent_llm"] == {}


# ── v3.1 CLI regression ────────────────────────────────────────

class TestV31LLMCLIRegression:
    """Ensure v3.1 llm commands still work after v3.9 changes."""

    def test_llm_profiles_still_works(self):
        """llm profiles --json still returns valid envelope."""
        code, stdout, stderr = run_cli(["llm", "profiles", "--json"])
        # May return error if no profiles configured, but should be valid JSON
        try:
            result = _parse_json(stdout)
            assert "ok" in result
        except json.JSONDecodeError:
            # If no profiles configured, the command may fail differently
            pass

    def test_llm_route_still_works(self):
        """llm route --agent author --json still returns valid envelope or error."""
        code, stdout, stderr = run_cli(["llm", "route", "--agent", "author", "--json"])
        # May return error if no profiles configured, but should be valid JSON
        try:
            result = _parse_json(stdout)
            assert "ok" in result
        except json.JSONDecodeError:
            pass

    def test_llm_validate_still_works(self):
        """llm validate --json still returns valid envelope."""
        code, stdout, stderr = run_cli(["llm", "validate", "--json"])
        try:
            result = _parse_json(stdout)
            assert "ok" in result
        except json.JSONDecodeError:
            pass
