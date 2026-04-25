"""Tests for v2.3 Skill Package functionality."""

import pytest
from pathlib import Path

from novel_factory.skills.registry import SkillRegistry
from novel_factory.models.skill_manifest import SkillManifest, SkillPackage


class TestSkillPackageStructure:
    """Test skill package directory structure."""

    def test_humanizer_zh_package_exists(self):
        """Test humanizer_zh package directory exists."""
        package_dir = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "humanizer_zh"
        assert package_dir.exists(), "humanizer_zh package directory should exist"
        assert package_dir.is_dir(), "humanizer_zh should be a directory"

    def test_ai_style_detector_package_exists(self):
        """Test ai_style_detector package directory exists."""
        package_dir = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "ai_style_detector"
        assert package_dir.exists(), "ai_style_detector package directory should exist"
        assert package_dir.is_dir(), "ai_style_detector should be a directory"

    def test_narrative_quality_package_exists(self):
        """Test narrative_quality package directory exists."""
        package_dir = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "narrative_quality"
        assert package_dir.exists(), "narrative_quality package directory should exist"
        assert package_dir.is_dir(), "narrative_quality should be a directory"

    def test_humanizer_zh_has_manifest(self):
        """Test humanizer_zh has manifest.yaml."""
        manifest_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "humanizer_zh" / "manifest.yaml"
        assert manifest_path.exists(), "humanizer_zh should have manifest.yaml"

    def test_ai_style_detector_has_manifest(self):
        """Test ai_style_detector has manifest.yaml."""
        manifest_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "ai_style_detector" / "manifest.yaml"
        assert manifest_path.exists(), "ai_style_detector should have manifest.yaml"

    def test_narrative_quality_has_manifest(self):
        """Test narrative_quality has manifest.yaml."""
        manifest_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "narrative_quality" / "manifest.yaml"
        assert manifest_path.exists(), "narrative_quality should have manifest.yaml"

    def test_humanizer_zh_has_handler(self):
        """Test humanizer_zh has handler.py."""
        handler_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "humanizer_zh" / "handler.py"
        assert handler_path.exists(), "humanizer_zh should have handler.py"

    def test_ai_style_detector_has_handler(self):
        """Test ai_style_detector has handler.py."""
        handler_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "ai_style_detector" / "handler.py"
        assert handler_path.exists(), "ai_style_detector should have handler.py"

    def test_narrative_quality_has_handler(self):
        """Test narrative_quality has handler.py."""
        handler_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "narrative_quality" / "handler.py"
        assert handler_path.exists(), "narrative_quality should have handler.py"

    def test_humanizer_zh_has_fixtures(self):
        """Test humanizer_zh has tests/fixtures.yaml."""
        fixtures_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "humanizer_zh" / "tests" / "fixtures.yaml"
        assert fixtures_path.exists(), "humanizer_zh should have tests/fixtures.yaml"

    def test_ai_style_detector_has_fixtures(self):
        """Test ai_style_detector has tests/fixtures.yaml."""
        fixtures_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "ai_style_detector" / "tests" / "fixtures.yaml"
        assert fixtures_path.exists(), "ai_style_detector should have tests/fixtures.yaml"

    def test_narrative_quality_has_fixtures(self):
        """Test narrative_quality has tests/fixtures.yaml."""
        fixtures_path = Path(__file__).parent.parent / "novel_factory" / "skill_packages" / "narrative_quality" / "tests" / "fixtures.yaml"
        assert fixtures_path.exists(), "narrative_quality should have tests/fixtures.yaml"


class TestSkillPackageManifest:
    """Test skill package manifest loading."""

    def test_load_humanizer_zh_manifest_from_package(self):
        """Test loading humanizer-zh manifest from package."""
        registry = SkillRegistry()
        manifest = registry.get_manifest("humanizer-zh")
        
        assert manifest is not None, "Should load manifest"
        assert manifest.id == "humanizer-zh", "Manifest id should match"
        assert manifest.name == "Humanizer Chinese", "Manifest name should match"
        assert manifest.version == "2.3.0", "Manifest version should be 2.3.0"
        assert manifest.package is not None, "Should have package metadata"
        assert manifest.package.name == "humanizer_zh", "Package name should match"

    def test_load_ai_style_detector_manifest_from_package(self):
        """Test loading ai-style-detector manifest from package."""
        registry = SkillRegistry()
        manifest = registry.get_manifest("ai-style-detector")
        
        assert manifest is not None, "Should load manifest"
        assert manifest.id == "ai-style-detector", "Manifest id should match"
        assert manifest.name == "AI Style Detector", "Manifest name should match"
        assert manifest.version == "2.3.0", "Manifest version should be 2.3.0"
        assert manifest.package is not None, "Should have package metadata"

    def test_load_narrative_quality_manifest_from_package(self):
        """Test loading narrative-quality manifest from package."""
        registry = SkillRegistry()
        manifest = registry.get_manifest("narrative-quality")
        
        assert manifest is not None, "Should load manifest"
        assert manifest.id == "narrative-quality", "Manifest id should match"
        assert manifest.name == "Narrative Quality Scorer", "Manifest name should match"
        assert manifest.version == "2.3.0", "Manifest version should be 2.3.0"
        assert manifest.package is not None, "Should have package metadata"


class TestSkillPackageSecurity:
    """Test skill package security validation."""

    def test_reject_absolute_path(self):
        """Test that absolute paths are rejected."""
        registry = SkillRegistry()
        
        # Mock a skill config with absolute path
        registry.skills_config["test-absolute"] = {
            "enabled": True,
            "package": "/absolute/path/to/package"
        }
        
        manifest = registry.get_manifest("test-absolute")
        assert manifest is None, "Should reject absolute path"

    def test_reject_directory_traversal(self):
        """Test that directory traversal is rejected."""
        registry = SkillRegistry()
        
        # Mock a skill config with directory traversal
        registry.skills_config["test-traversal"] = {
            "enabled": True,
            "package": "../outside/package"
        }
        
        manifest = registry.get_manifest("test-traversal")
        assert manifest is None, "Should reject directory traversal"


class TestSkillPackageValidation:
    """Test skill package validation."""

    def test_validate_all_with_packages(self):
        """Test validate_all with packages."""
        registry = SkillRegistry()
        result = registry.validate_all()
        
        assert result["ok"], "Validation should pass"
        # Should have warnings about missing handlers/fixtures if any
        # but no errors

    def test_validate_package_structure(self):
        """Test package structure validation."""
        registry = SkillRegistry()
        result = registry.validate_all()
        
        # All 3 packages should be valid
        assert result["ok"], "All packages should be valid"


class TestSkillPackageList:
    """Test list_skills with package info."""

    def test_list_skills_includes_package(self):
        """Test that list_skills includes package field."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        
        # Find humanizer-zh
        humanizer = next((s for s in skills if s["id"] == "humanizer-zh"), None)
        assert humanizer is not None, "Should find humanizer-zh"
        assert "package" in humanizer, "Should include package field"
        assert humanizer["package"] == "skill_packages/humanizer_zh", "Package path should match"

    def test_list_skills_includes_package_info(self):
        """Test that list_skills includes package_info."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        
        # Find humanizer-zh
        humanizer = next((s for s in skills if s["id"] == "humanizer-zh"), None)
        assert humanizer is not None, "Should find humanizer-zh"
        assert "package_info" in humanizer, "Should include package_info"
        
        package_info = humanizer["package_info"]
        assert package_info["name"] == "humanizer_zh", "Package name should match"
        assert package_info["handler"] == "handler.py", "Handler should match"
        assert package_info["entry_class"] == "HumanizerZhSkill", "Entry class should match"


class TestSkillPackageTest:
    """Test skill package test functionality."""

    def test_test_humanizer_zh(self):
        """Test running humanizer-zh fixtures."""
        registry = SkillRegistry()
        result = registry.test_skill("humanizer-zh")
        
        assert result["ok"], "Test should pass"
        assert result["data"]["total"] > 0, "Should have test cases"
        assert result["data"]["failed"] == 0, "No cases should fail"

    def test_test_ai_style_detector(self):
        """Test running ai-style-detector fixtures."""
        registry = SkillRegistry()
        result = registry.test_skill("ai-style-detector")
        
        assert result["ok"], "Test should pass"
        assert result["data"]["total"] > 0, "Should have test cases"
        assert result["data"]["failed"] == 0, "No cases should fail"

    def test_test_narrative_quality(self):
        """Test running narrative-quality fixtures."""
        registry = SkillRegistry()
        result = registry.test_skill("narrative-quality")
        
        assert result["ok"], "Test should pass"
        assert result["data"]["total"] > 0, "Should have test cases"
        assert result["data"]["failed"] == 0, "No cases should fail"

    def test_test_unknown_skill(self):
        """Test running fixtures for unknown skill."""
        registry = SkillRegistry()
        result = registry.test_skill("unknown-skill")
        
        assert not result["ok"], "Should fail for unknown skill"
        assert "not found" in result["error"].lower(), "Error should mention not found"


class TestSkillPackageBackwardCompatibility:
    """Test backward compatibility with v2.2."""

    def test_run_skill_from_package(self):
        """Test running skill loaded from package."""
        registry = SkillRegistry()
        result = registry.run_skill(
            "humanizer-zh",
            {"text": "然而，这是一个测试。"},
            agent="polisher",
            stage="after_llm"
        )
        
        assert result["ok"], "Skill should run successfully"
        assert "humanized_text" in result["data"], "Should return humanized_text"

    def test_run_ai_style_detector_from_package(self):
        """Test running ai-style-detector from package."""
        registry = SkillRegistry()
        result = registry.run_skill(
            "ai-style-detector",
            {"text": "然而，这是一个测试。"},
            agent="polisher",
            stage="before_save"
        )
        
        assert result["ok"], "Skill should run successfully"
        assert "ai_trace_score" in result["data"], "Should return ai_trace_score"

    def test_run_narrative_quality_from_package(self):
        """Test running narrative-quality from package."""
        registry = SkillRegistry()
        result = registry.run_skill(
            "narrative-quality",
            {"text": "他走在路上，思考着问题。"},
            agent="editor",
            stage="final_gate"
        )
        
        assert result["ok"], "Skill should run successfully"
        assert "scores" in result["data"], "Should return scores"
        assert "grade" in result["data"], "Should return grade"
