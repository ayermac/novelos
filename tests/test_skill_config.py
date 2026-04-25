"""Tests for v2.1 Skill configuration."""

from __future__ import annotations

import pytest

from novel_factory.skills.registry import SkillRegistry


class TestSkillConfiguration:
    """Test skill configuration loading and behavior."""
    
    def test_default_skills_loaded(self):
        """Test that default skills are loaded."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        
        # Should have at least 3 built-in skills
        skill_ids = [s["id"] for s in skills]
        assert "humanizer-zh" in skill_ids
        assert "ai-style-detector" in skill_ids
        assert "narrative-quality" in skill_ids
    
    def test_skill_types(self):
        """Test that skills have correct types."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        
        for skill in skills:
            # v2.2: Use "kind" field if available, fallback to "type" for v2.1 compatibility
            skill_type = skill.get("kind") or skill.get("type")
            assert skill_type in ("transform", "validator")
    
    def test_agent_skill_configuration(self):
        """Test agent skill configuration from skills.yaml."""
        registry = SkillRegistry()
        
        # Check polisher skills
        polisher_after_llm = registry.get_skills_for_agent("polisher", "after_llm")
        assert isinstance(polisher_after_llm, list)
        
        polisher_before_save = registry.get_skills_for_agent("polisher", "before_save")
        assert isinstance(polisher_before_save, list)
        
        # Check editor skills
        editor_before_review = registry.get_skills_for_agent("editor", "before_review")
        assert isinstance(editor_before_review, list)
    
    def test_disabled_skill_not_in_agent_list(self, tmp_path):
        """Test that disabled skills are not included in agent skill list."""
        import yaml
        
        # Create custom config with disabled skill
        config_path = tmp_path / "skills.yaml"
        config = {
            "skills": {
                "test-skill-1": {
                    "type": "validator",
                    "class": "novel_factory.skills.ai_style_detector.AIStyleDetectorSkill",
                    "enabled": True,
                },
                "test-skill-2": {
                    "type": "validator",
                    "class": "novel_factory.skills.ai_style_detector.AIStyleDetectorSkill",
                    "enabled": False,  # Disabled
                },
            },
            "agent_skills": {
                "test_agent": {
                    "test_stage": ["test-skill-1", "test-skill-2"]
                }
            }
        }
        
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        registry = SkillRegistry(config_path=str(config_path))
        
        # Get skills for test agent
        skills = registry.get_skills_for_agent("test_agent", "test_stage")
        
        # Should only include enabled skill
        assert "test-skill-1" in skills
        assert "test-skill-2" not in skills
    
    def test_run_skills_for_agent_returns_list(self):
        """Test that run_skills_for_agent returns a list."""
        registry = SkillRegistry()
        
        result = registry.run_skills_for_agent(
            agent="polisher",
            stage="after_llm",
            payload={"text": "测试文本"},
        )
        
        # Should return a list
        assert isinstance(result, list)
        
        # Each item should have skill_id and result
        for item in result:
            assert "skill_id" in item
            assert "result" in item
    
    def test_unknown_agent_returns_empty_list(self):
        """Test that unknown agent returns empty list."""
        registry = SkillRegistry()
        
        result = registry.run_skills_for_agent(
            agent="unknown_agent",
            stage="unknown_stage",
            payload={"text": "test"},
        )
        
        # Should return empty list
        assert result == []


class TestSkillPayloadContract:
    """Test skill payload contract."""
    
    def test_text_field_accepted(self):
        """Test that 'text' field is accepted."""
        registry = SkillRegistry()
        
        result = registry.run_skill("ai-style-detector", {"text": "测试文本"})
        assert result["ok"] is True
    
    def test_content_field_accepted(self):
        """Test that 'content' field is also accepted."""
        registry = SkillRegistry()
        
        result = registry.run_skill("ai-style-detector", {"content": "测试文本"})
        assert result["ok"] is True
    
    def test_empty_payload_fails(self):
        """Test that empty payload fails gracefully."""
        registry = SkillRegistry()
        
        result = registry.run_skill("ai-style-detector", {})
        assert result["ok"] is False
        assert "error" in result
