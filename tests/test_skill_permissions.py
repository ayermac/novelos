"""Tests for v2.2 Skill Permissions and Agent/Stage validation."""

from __future__ import annotations

import pytest

from novel_factory.skills.registry import SkillRegistry


class TestSkillRegistryManifest:
    """Test SkillRegistry manifest support."""

    def test_get_manifest_humanizer(self):
        """Test getting humanizer-zh manifest."""
        registry = SkillRegistry()
        manifest = registry.get_manifest("humanizer-zh")
        
        assert manifest is not None
        assert manifest.id == "humanizer-zh"
        assert manifest.kind == "transform"
        assert manifest.class_name == "HumanizerZhSkill"

    def test_get_manifest_ai_style_detector(self):
        """Test getting ai-style-detector manifest."""
        registry = SkillRegistry()
        manifest = registry.get_manifest("ai-style-detector")
        
        assert manifest is not None
        assert manifest.id == "ai-style-detector"
        assert manifest.kind == "validator"

    def test_get_manifest_narrative_quality(self):
        """Test getting narrative-quality manifest."""
        registry = SkillRegistry()
        manifest = registry.get_manifest("narrative-quality")
        
        assert manifest is not None
        assert manifest.id == "narrative-quality"
        assert manifest.kind == "validator"

    def test_get_manifest_unknown_skill(self):
        """Test getting manifest for unknown skill."""
        registry = SkillRegistry()
        manifest = registry.get_manifest("unknown-skill")
        
        assert manifest is None


class TestSkillAgentStageValidation:
    """Test skill agent/stage validation."""

    def test_humanizer_allowed_for_polisher_after_llm(self):
        """Test humanizer-zh is allowed for polisher/after_llm."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "humanizer-zh", "polisher", "after_llm"
        )
        
        assert is_valid is True
        assert error_msg == ""

    def test_humanizer_not_allowed_for_editor(self):
        """Test humanizer-zh is not allowed for editor."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "humanizer-zh", "editor", "after_llm"
        )
        
        assert is_valid is False
        assert "not allowed for agent" in error_msg

    def test_ai_style_detector_allowed_for_polisher_before_save(self):
        """Test ai-style-detector is allowed for polisher/before_save."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "ai-style-detector", "polisher", "before_save"
        )
        
        assert is_valid is True
        assert error_msg == ""

    def test_ai_style_detector_allowed_for_editor_before_review(self):
        """Test ai-style-detector is allowed for editor/before_review."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "ai-style-detector", "editor", "before_review"
        )
        
        assert is_valid is True
        assert error_msg == ""

    def test_ai_style_detector_allowed_for_qualityhub_final_gate(self):
        """Test ai-style-detector is allowed for qualityhub/final_gate."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "ai-style-detector", "qualityhub", "final_gate"
        )
        
        assert is_valid is True
        assert error_msg == ""

    def test_narrative_quality_allowed_for_editor_before_review(self):
        """Test narrative-quality is allowed for editor/before_review."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "narrative-quality", "editor", "before_review"
        )
        
        assert is_valid is True
        assert error_msg == ""

    def test_narrative_quality_allowed_for_qualityhub_final_gate(self):
        """Test narrative-quality is allowed for qualityhub/final_gate."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "narrative-quality", "qualityhub", "final_gate"
        )
        
        assert is_valid is True
        assert error_msg == ""

    def test_narrative_quality_not_allowed_for_polisher(self):
        """Test narrative-quality is not allowed for polisher."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "narrative-quality", "polisher", "after_llm"
        )
        
        assert is_valid is False
        assert "not allowed for agent" in error_msg

    def test_unknown_skill_not_valid(self):
        """Test unknown skill is not valid."""
        registry = SkillRegistry()
        is_valid, error_msg = registry.validate_skill_for_agent(
            "unknown-skill", "polisher", "after_llm"
        )
        
        assert is_valid is False
        assert "not found" in error_msg


class TestSkillExecution:
    """Test skill execution with manifest validation."""

    def test_run_skill_manual_stage_allowed(self):
        """Test running skill with manual stage (allowed in manifest)."""
        registry = SkillRegistry()
        
        # ai-style-detector allows manual stage
        result = registry.run_skill(
            "ai-style-detector",
            {"text": "测试文本"},
            agent="manual",
            stage="manual",
        )
        
        assert result.get("ok") is True
        assert "ai_trace_score" in result.get("data", {})

    def test_run_skill_unauthorized_agent(self):
        """Test running skill with unauthorized agent."""
        registry = SkillRegistry()
        
        # humanizer-zh only allows polisher, not editor
        result = registry.run_skill(
            "humanizer-zh",
            {"text": "测试文本"},
            agent="editor",
            stage="after_llm",
        )
        
        assert result.get("ok") is False
        assert "not allowed for agent" in result.get("error", "")

    def test_run_skill_unauthorized_stage(self):
        """Test running skill with unauthorized stage."""
        registry = SkillRegistry()
        
        # humanizer-zh only allows after_llm, not before_save
        result = registry.run_skill(
            "humanizer-zh",
            {"text": "测试文本"},
            agent="polisher",
            stage="before_save",
        )
        
        assert result.get("ok") is False
        assert "not allowed for stage" in result.get("error", "")

    def test_run_skill_disabled(self):
        """Test running disabled skill."""
        registry = SkillRegistry()
        
        # Temporarily disable skill
        original_enabled = registry.skills_config.get("humanizer-zh", {}).get("enabled", True)
        registry.skills_config["humanizer-zh"]["enabled"] = False
        
        result = registry.run_skill(
            "humanizer-zh",
            {"text": "测试文本"},
            agent="polisher",
            stage="after_llm",
        )
        
        # Restore
        registry.skills_config["humanizer-zh"]["enabled"] = original_enabled
        
        assert result.get("ok") is False
        assert "disabled" in result.get("error", "").lower()


class TestValidateAll:
    """Test validate_all method."""

    def test_validate_all_success(self):
        """Test validate_all with valid manifests."""
        registry = SkillRegistry()
        result = registry.validate_all()
        
        assert result["ok"] is True
        assert len(result["errors"]) == 0

    def test_validate_all_warnings_for_v21_compatibility(self):
        """Test validate_all shows warnings for skills without manifest."""
        registry = SkillRegistry()
        result = registry.validate_all()
        
        # v2.2: All built-in skills have manifests, so no warnings expected
        # But if a skill had no manifest, it would show a warning
        assert isinstance(result["warnings"], list)


class TestListSkills:
    """Test list_skills with manifest info."""

    def test_list_skills_includes_manifest_info(self):
        """Test list_skills includes manifest information."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        
        # Find humanizer-zh
        humanizer = next((s for s in skills if s["id"] == "humanizer-zh"), None)
        assert humanizer is not None
        
        # v2.2: Should have manifest fields
        assert "name" in humanizer
        assert "version" in humanizer
        assert "kind" in humanizer
        assert humanizer["kind"] == "transform"
        assert "allowed_agents" in humanizer
        assert "polisher" in humanizer["allowed_agents"]
