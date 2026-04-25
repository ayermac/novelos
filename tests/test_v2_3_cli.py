"""Tests for v2.3 CLI commands."""

import json
import pytest
from pathlib import Path

from novel_factory.cli import cmd_skill_test


class TestV23CLI:
    """Test v2.3 CLI commands."""

    def test_skills_test_humanizer_zh_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills test humanizer-zh --json'."""
        import sys
        from io import StringIO
        
        # Mock args
        class Args:
            skill_id = "humanizer-zh"
            all = False
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        # Capture output
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_test(Args())
            output = sys.stdout.getvalue()
            
            # Parse JSON output
            result = json.loads(output)
            
            assert result["ok"], "Test should pass"
            assert result["data"]["total"] > 0, "Should have test cases"
            assert result["data"]["failed"] == 0, "No cases should fail"
        finally:
            sys.stdout = old_stdout

    def test_skills_test_ai_style_detector_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills test ai-style-detector --json'."""
        import sys
        from io import StringIO
        
        class Args:
            skill_id = "ai-style-detector"
            all = False
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_test(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"], "Test should pass"
            assert result["data"]["total"] > 0, "Should have test cases"
        finally:
            sys.stdout = old_stdout

    def test_skills_test_narrative_quality_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills test narrative-quality --json'."""
        import sys
        from io import StringIO
        
        class Args:
            skill_id = "narrative-quality"
            all = False
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_test(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"], "Test should pass"
            assert result["data"]["total"] > 0, "Should have test cases"
        finally:
            sys.stdout = old_stdout

    def test_skills_test_all_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills test --all --json'."""
        import sys
        from io import StringIO
        
        class Args:
            skill_id = None
            all = True
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_test(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"], "All tests should pass"
            assert result["data"]["total"] == 3, "Should test 3 skills"
            assert result["data"]["failed"] == 0, "No skills should fail"
        finally:
            sys.stdout = old_stdout

    def test_skills_test_unknown_skill_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills test unknown-skill --json'."""
        import sys
        from io import StringIO
        
        class Args:
            skill_id = "unknown-skill"
            all = False
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_test(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            # Should return error in JSON
            assert not result["ok"], "Should fail for unknown skill"
            assert "not found" in result["error"].lower(), "Error should mention not found"
        finally:
            sys.stdout = old_stdout

    def test_skills_show_includes_package_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills show humanizer-zh --json' includes package."""
        import sys
        from io import StringIO
        from novel_factory.cli import cmd_skill_show
        
        class Args:
            skill_id = "humanizer-zh"
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_show(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"], "Should succeed"
            assert "package" in result["data"], "Should include package field"
            assert result["data"]["package"] == "skill_packages/humanizer_zh", "Package path should match"
        finally:
            sys.stdout = old_stdout

    def test_skills_validate_includes_package_warnings_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills validate --json' includes package checks."""
        import sys
        from io import StringIO
        from novel_factory.cli import cmd_skill_validate
        
        class Args:
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_validate(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"], "Validation should pass"
        finally:
            sys.stdout = old_stdout

    def test_skills_list_includes_package_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills list --json' includes package field."""
        import sys
        from io import StringIO
        from novel_factory.cli import cmd_skill_list
        
        class Args:
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_list(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"], "Should succeed"
            
            # Find humanizer-zh
            skills = result["data"]["skills"]
            humanizer = next((s for s in skills if s["id"] == "humanizer-zh"), None)
            assert humanizer is not None, "Should find humanizer-zh"
            assert "package" in humanizer, "Should include package field"
        finally:
            sys.stdout = old_stdout

    def test_skills_run_from_package_json(self, tmp_path, monkeypatch):
        """Test 'novelos skills run humanizer-zh --text ... --json' still works."""
        import sys
        from io import StringIO
        from novel_factory.cli import cmd_skill_run
        
        class Args:
            skill_id = "humanizer-zh"
            text = "然而，这是一个测试。"
            config_json = None
            agent = "manual"
            stage = "manual"
            json = True
            config = None
            db_path = None
            llm_mode = "stub"
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_skill_run(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"], "Should succeed"
            assert "humanized_text" in result["data"], "Should return humanized_text"
        finally:
            sys.stdout = old_stdout
