"""Tests for v2.2 CLI commands."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


class TestSkillsShowCLI:
    """Test v2.2 'novelos skills show' command."""

    def test_skills_show_humanizer_zh_json(self):
        """Test 'novelos skills show humanizer-zh --json' command."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "show", "humanizer-zh",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "data" in output
        
        # Check manifest fields
        data = output["data"]
        assert data["id"] == "humanizer-zh"
        assert data["name"] == "Humanizer Chinese"
        assert data["kind"] == "transform"
        assert data["class_name"] == "HumanizerZhSkill"
        assert "polisher" in data["allowed_agents"]
        assert "after_llm" in data["allowed_stages"]

    def test_skills_show_ai_style_detector_json(self):
        """Test 'novelos skills show ai-style-detector --json' command."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "show", "ai-style-detector",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        
        data = output["data"]
        assert data["id"] == "ai-style-detector"
        assert data["kind"] == "validator"
        assert "polisher" in data["allowed_agents"]
        assert "editor" in data["allowed_agents"]
        assert "qualityhub" in data["allowed_agents"]

    def test_skills_show_narrative_quality_json(self):
        """Test 'novelos skills show narrative-quality --json' command."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "show", "narrative-quality",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        
        data = output["data"]
        assert data["id"] == "narrative-quality"
        assert data["kind"] == "validator"

    def test_skills_show_unknown_skill_fails(self):
        """Test 'novelos skills show unknown-skill' fails clearly."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "show", "unknown-skill",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should fail with non-zero exit code
        assert result.returncode != 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is False
        assert "error" in output
        assert "not found" in output["error"].lower()

    def test_skills_show_human_readable(self):
        """Test 'novelos skills show humanizer-zh' human-readable output."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "show", "humanizer-zh",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "humanizer-zh" in result.stdout
        assert "Humanizer Chinese" in result.stdout
        assert "transform" in result.stdout


class TestSkillsValidateCLI:
    """Test v2.2 'novelos skills validate' command."""

    def test_skills_validate_json(self):
        """Test 'novelos skills validate --json' command."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "validate",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "error" in output
        assert "data" in output
        assert "errors" in output["data"]
        assert len(output["data"]["errors"]) == 0

    def test_skills_validate_human_readable(self):
        """Test 'novelos skills validate' human-readable output."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "validate",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "valid" in result.stdout.lower()


class TestSkillsRunCLI:
    """Test v2.2 'novelos skills run' command with manifest validation."""

    def test_skills_run_humanizer_zh_manual_stage(self):
        """Test 'novelos skills run humanizer-zh' with manual stage."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "humanizer-zh",
                "--text", "这是一个测试文本。",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should succeed (humanizer-zh now allows manual stage)
        assert result.returncode == 0
        
        output = json.loads(result.stdout)
        assert output["ok"] is True

    def test_skills_run_ai_style_detector_manual_stage(self):
        """Test 'novelos skills run ai-style-detector' with manual stage."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "ai-style-detector",
                "--text", "这是一个测试文本。",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should succeed (ai-style-detector allows manual stage)
        assert result.returncode == 0
        
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "ai_trace_score" in output["data"]

    def test_skills_run_narrative_quality_manual_stage(self):
        """Test 'novelos skills run narrative-quality' with manual stage."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "narrative-quality",
                "--text", "这是一个测试文本。" * 50,
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should succeed (narrative-quality allows manual stage)
        assert result.returncode == 0
        
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "scores" in output["data"]


class TestSkillsListCLI:
    """Test v2.2 'novelos skills list' command with manifest info."""

    def test_skills_list_includes_manifest_info(self):
        """Test 'novelos skills list --json' includes manifest info."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "list",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "data" in output
        assert "skills" in output["data"]
        
        # Find humanizer-zh
        skills = output["data"]["skills"]
        humanizer = next((s for s in skills if s["id"] == "humanizer-zh"), None)
        assert humanizer is not None
        
        # v2.2: Should have manifest fields
        assert "name" in humanizer
        assert "version" in humanizer
        assert "kind" in humanizer
        assert humanizer["kind"] == "transform"
