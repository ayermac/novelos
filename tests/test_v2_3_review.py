"""Regression tests for v2.3 review issues: R1 (no fallback to legacy), R2 (JSON envelope)."""

import pytest
import json
import subprocess
import sys
from pathlib import Path
from novel_factory.skills.registry import SkillRegistry
from novel_factory.skills.base import BaseSkill


class TestR1NoFallbackToLegacy:
    """R1: Package handler loading failure must NOT fallback to legacy class."""

    def test_package_skill_entry_class_not_found_fails(self):
        """Test that missing entry_class causes failure, not fallback."""
        registry = SkillRegistry()
        
        # Mock a skill with package but wrong entry_class
        # We need to create a temporary package structure
        import tempfile
        import yaml
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake package
            package_dir = Path(tmpdir) / "test_package"
            package_dir.mkdir()
            
            # Create a valid manifest
            manifest = {
                "id": "test-fake-skill",
                "name": "Test Fake Skill",
                "version": "1.0.0",
                "kind": "transform",
                "description": "Test skill",
                "enabled": True,
                "builtin": False,
                "class_name": "TestFakeSkill",
                "allowed_agents": ["*"],
                "allowed_stages": ["*"],
                "permissions": {
                    "transform_text": True,
                    "validate_text": False,
                    "write_skill_run": False,
                },
                "failure_policy": {
                    "on_error": "raise",
                    "max_retries": 0,
                },
                "package": {
                    "name": "test_package",
                    "handler": "handler.py",
                    "entry_class": "NonExistentClass",  # This class doesn't exist
                }
            }
            
            with open(package_dir / "manifest.yaml", "w") as f:
                yaml.dump(manifest, f)
            
            # Create a handler with wrong class name
            with open(package_dir / "handler.py", "w") as f:
                f.write("""
from novel_factory.skills.base import BaseSkill

class WrongClassName(BaseSkill):
    def run(self, payload):
        return {"ok": True, "data": {}}
""")
            
            # Mock the skill config
            registry.skills_config["test-fake-skill"] = {
                "enabled": True,
                "package": f"skill_packages/test_package"
            }
            
            # Mock the manifest path resolution
            original_resolve = registry._resolve_package_manifest_path
            registry._resolve_package_manifest_path = lambda p: package_dir / "manifest.yaml" if "test_package" in p else original_resolve(p)
            
            # Try to get skill - should fail
            skill_instance = registry.get_skill("test-fake-skill")
            
            # Should return None, not fallback to legacy
            assert skill_instance is None, "Should fail when entry_class not found, not fallback"

    def test_package_skill_handler_missing_fails(self):
        """Test that missing handler.py causes failure, not fallback."""
        registry = SkillRegistry()
        
        import tempfile
        import yaml
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake package without handler.py
            package_dir = Path(tmpdir) / "test_package2"
            package_dir.mkdir()
            
            # Create a valid manifest
            manifest = {
                "id": "test-no-handler",
                "name": "Test No Handler",
                "version": "1.0.0",
                "kind": "transform",
                "description": "Test skill",
                "enabled": True,
                "builtin": False,
                "class_name": "TestNoHandler",
                "allowed_agents": ["*"],
                "allowed_stages": ["*"],
                "permissions": {
                    "transform_text": True,
                    "validate_text": False,
                    "write_skill_run": False,
                },
                "failure_policy": {
                    "on_error": "raise",
                    "max_retries": 0,
                },
                "package": {
                    "name": "test_package2",
                    "handler": "handler.py",
                    "entry_class": "TestSkill",
                }
            }
            
            with open(package_dir / "manifest.yaml", "w") as f:
                yaml.dump(manifest, f)
            
            # No handler.py created!
            
            # Mock the skill config
            registry.skills_config["test-no-handler"] = {
                "enabled": True,
                "package": f"skill_packages/test_package2"
            }
            
            # Mock the manifest path resolution
            original_resolve = registry._resolve_package_manifest_path
            registry._resolve_package_manifest_path = lambda p: package_dir / "manifest.yaml" if "test_package2" in p else original_resolve(p)
            
            # Try to get skill - should fail
            skill_instance = registry.get_skill("test-no-handler")
            
            # Should return None, not fallback to legacy
            assert skill_instance is None, "Should fail when handler missing, not fallback"

    def test_package_skill_not_baseskill_subclass_fails(self):
        """Test that non-BaseSkill entry_class causes failure, not fallback."""
        registry = SkillRegistry()
        
        import tempfile
        import yaml
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake package
            package_dir = Path(tmpdir) / "test_package3"
            package_dir.mkdir()
            
            # Create a valid manifest
            manifest = {
                "id": "test-wrong-base",
                "name": "Test Wrong Base",
                "version": "1.0.0",
                "kind": "transform",
                "description": "Test skill",
                "enabled": True,
                "builtin": False,
                "class_name": "TestWrongBase",
                "allowed_agents": ["*"],
                "allowed_stages": ["*"],
                "permissions": {
                    "transform_text": True,
                    "validate_text": False,
                    "write_skill_run": False,
                },
                "failure_policy": {
                    "on_error": "raise",
                    "max_retries": 0,
                },
                "package": {
                    "name": "test_package3",
                    "handler": "handler.py",
                    "entry_class": "NotASkill",
                }
            }
            
            with open(package_dir / "manifest.yaml", "w") as f:
                yaml.dump(manifest, f)
            
            # Create a handler with class that's NOT a BaseSkill subclass
            with open(package_dir / "handler.py", "w") as f:
                f.write("""
class NotASkill:
    def run(self, payload):
        return {"ok": True, "data": {}}
""")
            
            # Mock the skill config
            registry.skills_config["test-wrong-base"] = {
                "enabled": True,
                "package": f"skill_packages/test_package3"
            }
            
            # Mock the manifest path resolution
            original_resolve = registry._resolve_package_manifest_path
            registry._resolve_package_manifest_path = lambda p: package_dir / "manifest.yaml" if "test_package3" in p else original_resolve(p)
            
            # Try to get skill - should fail
            skill_instance = registry.get_skill("test-wrong-base")
            
            # Should return None, not fallback to legacy
            assert skill_instance is None, "Should fail when not BaseSkill subclass, not fallback"

    def test_legacy_skill_without_package_still_works(self):
        """Test that legacy skills without package still use whitelist."""
        registry = SkillRegistry()
        
        # Mock a legacy skill without package
        registry.skills_config["test-legacy"] = {
            "enabled": True,
            "type": "transform",
            "class": "HumanizerZhSkill"  # Use a known skill class
        }
        
        # Should be able to load from whitelist
        skill_instance = registry.get_skill("test-legacy")
        
        # Should succeed via legacy path
        assert skill_instance is not None, "Legacy skill should load from whitelist"
        assert isinstance(skill_instance, BaseSkill), "Should be BaseSkill instance"

    def test_run_skill_package_failure_returns_envelope(self):
        """Test that run_skill returns proper envelope on package failure."""
        registry = SkillRegistry()
        
        # Mock a skill with package that will fail to load
        registry.skills_config["test-fail-pkg"] = {
            "enabled": True,
            "package": "skill_packages/nonexistent"
        }
        
        # Try to run skill
        result = registry.run_skill(
            "test-fail-pkg",
            {"text": "test"},
            agent="manual",
            stage="manual"
        )
        
        # Should return error envelope
        assert result["ok"] is False, "Should fail"
        assert "error" in result, "Should have error field"
        assert result["data"] == {}, "Should have empty data dict"


class TestR2JSONEnvelope:
    """R2: All skills test JSON error paths must use envelope format."""

    def test_skills_test_missing_skill_id_json_envelope(self):
        """Test 'skills test --json' without skill_id returns envelope."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "test", "--json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        # Should output JSON
        output = json.loads(result.stdout)
        
        # Check envelope structure
        assert "ok" in output, "Should have 'ok' field"
        assert "error" in output, "Should have 'error' field"
        assert "data" in output, "Should have 'data' field"
        
        # Check values
        assert output["ok"] is False, "Should be False"
        assert "skill_id is required" in output["error"], "Error should mention skill_id required"
        assert output["data"] == {}, "Data should be empty dict"

    def test_skills_test_unknown_skill_json_envelope(self):
        """Test 'skills test unknown-skill --json' returns envelope with data dict."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "test", "unknown-skill", "--json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        # Should output JSON
        output = json.loads(result.stdout)
        
        # Check envelope structure
        assert "ok" in output, "Should have 'ok' field"
        assert "error" in output, "Should have 'error' field"
        assert "data" in output, "Should have 'data' field"
        
        # Check values
        assert output["ok"] is False, "Should be False"
        assert output["error"] is not None, "Should have error message"
        assert isinstance(output["data"], dict), "Data should be dict, not null"
        assert output["data"] == {}, "Data should be empty dict for unknown skill"

    def test_skills_validate_json_envelope_structure(self):
        """Test 'skills validate --json' returns proper envelope."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "validate", "--json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        # Should output JSON
        output = json.loads(result.stdout)
        
        # Check envelope structure
        assert "ok" in output, "Should have 'ok' field"
        assert "error" in output, "Should have 'error' field"
        assert "data" in output, "Should have 'data' field"
        
        # Check that data contains errors/warnings
        assert "errors" in output["data"], "Data should have 'errors' field"
        assert "warnings" in output["data"], "Data should have 'warnings' field"

    def test_skills_test_all_json_envelope(self):
        """Test 'skills test --all --json' returns envelope."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "test", "--all", "--json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        # Should output JSON
        output = json.loads(result.stdout)
        
        # Check envelope structure
        assert "ok" in output, "Should have 'ok' field"
        assert "error" in output, "Should have 'error' field"
        assert "data" in output, "Should have 'data' field"
        
        # Check data structure
        assert "passed" in output["data"], "Should have 'passed' in data"
        assert "failed" in output["data"], "Should have 'failed' in data"
        assert "total" in output["data"], "Should have 'total' in data"

    def test_skills_test_valid_skill_json_envelope(self):
        """Test 'skills test humanizer-zh --json' returns envelope."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "test", "humanizer-zh", "--json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        # Should output JSON
        output = json.loads(result.stdout)
        
        # Check envelope structure
        assert "ok" in output, "Should have 'ok' field"
        assert "error" in output, "Should have 'error' field"
        assert "data" in output, "Should have 'data' field"
        
        # Check success
        assert output["ok"] is True, "Should be True for valid skill"
        assert output["error"] is None, "Error should be None for success"
        assert "passed" in output["data"], "Should have 'passed' in data"

    def test_skills_validate_exception_json_envelope(self):
        """Test 'skills validate --json' exception path returns envelope."""
        from unittest.mock import patch, MagicMock
        import novel_factory.cli
        
        # Mock _get_settings to avoid validation errors
        with patch('novel_factory.cli._get_settings') as mock_get_settings:
            mock_settings = MagicMock()
            mock_get_settings.return_value = mock_settings
            
            # Mock SkillRegistry.validate_all to raise exception
            with patch('novel_factory.skills.registry.SkillRegistry') as MockRegistry:
                mock_registry = MagicMock()
                mock_registry.validate_all.side_effect = Exception("Test validation error")
                MockRegistry.return_value = mock_registry
                
                # Create args with json=True
                args = MagicMock()
                args.json = True
                args.config = None
                args.db_path = None
                args.llm_mode = "real"
                args.llm_api_key = None
                args.llm_base_url = None
                args.llm_model = None
                
                # Capture stdout
                import io
                import sys
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                
                try:
                    novel_factory.cli.cmd_skill_validate(args)
                except SystemExit:
                    pass
                finally:
                    output = sys.stdout.getvalue()
                    sys.stdout = old_stdout
                
                # Parse JSON output
                result = json.loads(output)
                
                # Check envelope structure
                assert "ok" in result, "Should have 'ok' field"
                assert "error" in result, "Should have 'error' field"
                assert "data" in result, "Should have 'data' field"
                
                # Check values
                assert result["ok"] is False, "Should be False"
                assert "Test validation error" in result["error"], "Should have error message"
                assert result["data"] == {}, "Data should be empty dict"
