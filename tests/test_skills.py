"""Tests for v2.1 Skill system."""

from __future__ import annotations

import pytest

from novel_factory.skills.registry import SkillRegistry
from novel_factory.skills.base import BaseSkill, TransformSkill, ValidatorSkill


class TestSkillRegistry:
    """Test SkillRegistry functionality."""
    
    def test_list_skills(self):
        """Test listing available skills."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        
        # Should have at least 3 built-in skills
        assert len(skills) >= 3
        
        # Check skill structure
        for skill in skills:
            assert "id" in skill
            # v2.2: "kind" or "type" field
            assert "kind" in skill or "type" in skill
            # v2.2: "class_name" or "class" field
            assert "class_name" in skill or "class" in skill
            assert "enabled" in skill
    
    def test_get_skills_for_agent(self):
        """Test getting skills configured for an agent."""
        registry = SkillRegistry()
        
        # Get skills for polisher at after_llm stage
        skills = registry.get_skills_for_agent("polisher", "after_llm")
        assert isinstance(skills, list)
        
        # Get skills for editor at before_review stage
        skills = registry.get_skills_for_agent("editor", "before_review")
        assert isinstance(skills, list)
    
    def test_run_skill_humanizer_zh(self):
        """Test running humanizer-zh skill."""
        registry = SkillRegistry()
        
        result = registry.run_skill("humanizer-zh", {"text": "这是一个测试文本。"})
        
        assert "ok" in result
        assert "data" in result
        if result["ok"]:
            assert "humanized_text" in result["data"]
    
    def test_run_skill_ai_style_detector(self):
        """Test running ai-style-detector skill."""
        registry = SkillRegistry()
        
        result = registry.run_skill("ai-style-detector", {"text": "这是一个测试文本。"})
        
        assert "ok" in result
        assert "data" in result
        if result["ok"]:
            assert "ai_trace_score" in result["data"]
    
    def test_run_skill_narrative_quality(self):
        """Test running narrative-quality skill."""
        registry = SkillRegistry()
        
        result = registry.run_skill("narrative-quality", {"text": "这是一个测试文本。" * 50})
        
        assert "ok" in result
        assert "data" in result
        if result["ok"]:
            assert "scores" in result["data"]
    
    def test_run_unknown_skill_fails(self):
        """Test running unknown skill fails clearly."""
        registry = SkillRegistry()
        
        result = registry.run_skill("unknown-skill", {"text": "test"})
        
        assert result["ok"] is False
        assert "error" in result
        assert "not found" in result["error"].lower() or "disabled" in result["error"].lower()
    
    def test_skill_payload_text_and_content_compatibility(self):
        """Test that skills accept both 'text' and 'content' fields."""
        registry = SkillRegistry()
        
        # Test with 'text' field
        result1 = registry.run_skill("ai-style-detector", {"text": "测试文本"})
        
        # Test with 'content' field
        result2 = registry.run_skill("ai-style-detector", {"content": "测试文本"})
        
        # Both should work
        assert result1["ok"] is True
        assert result2["ok"] is True


class TestDisabledSkill:
    """Test disabled skill behavior."""
    
    def test_disabled_skill_not_executed(self, tmp_path):
        """Test that disabled skills are not executed."""
        # Create a custom skills.yaml with disabled skill
        import yaml
        config_path = tmp_path / "skills.yaml"
        config = {
            "skills": [
                {
                    "id": "disabled-test-skill",
                    "type": "validator",
                    "class": "novel_factory.skills.ai_style_detector.AIStyleDetectorSkill",
                    "enabled": False,
                }
            ]
        }
        
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        registry = SkillRegistry(config_path=str(config_path))
        
        # Try to run disabled skill
        result = registry.run_skill("disabled-test-skill", {"text": "test"})
        
        # Should fail or return disabled status
        assert result["ok"] is False or "disabled" in str(result).lower()


class TestSkillRuns:
    """Test skill_runs database operations."""
    
    def test_save_skill_run_success(self, tmp_db):
        """Test saving successful skill run."""
        from novel_factory.db.repository import Repository
        
        repo = Repository(tmp_db)
        
        # Seed test project
        _seed_test_project_skill(repo, "test_proj", 1)
        
        # Save successful skill run
        run_id = repo.save_skill_run(
            project_id="test_proj",
            skill_id="humanizer-zh",
            skill_type="transform",
            ok=True,
            input_json={"text": "test"},
            output_json={"humanized_text": "test"},
            chapter_number=1,
        )
        
        assert run_id > 0
        
        # Query skill runs
        runs = repo.get_skill_runs(project_id="test_proj")
        assert len(runs) >= 1
        assert runs[0]["skill_id"] == "humanizer-zh"
        assert runs[0]["ok"] == 1
    
    def test_save_skill_run_failure(self, tmp_db):
        """Test saving failed skill run."""
        from novel_factory.db.repository import Repository
        
        repo = Repository(tmp_db)
        
        # Seed test project
        _seed_test_project_skill(repo, "test_proj", 1)
        
        # Save failed skill run
        run_id = repo.save_skill_run(
            project_id="test_proj",
            skill_id="unknown-skill",
            skill_type="validator",
            ok=False,
            error="Skill not found",
            input_json={"text": "test"},
            chapter_number=1,
        )
        
        assert run_id > 0
        
        # Query skill runs
        runs = repo.get_skill_runs(project_id="test_proj")
        assert len(runs) >= 1
        assert runs[0]["ok"] == 0
        assert runs[0]["error"] == "Skill not found"


def _seed_test_project_skill(repo, project_id: str, chapter_number: int):
    """Seed test project for skill runs."""
    conn = repo._conn()
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_id, name, genre) VALUES (?, ?, ?)",
        (project_id, "Test Project", "fantasy"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        (project_id, chapter_number, f"Chapter {chapter_number}", "drafted"),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def tmp_db(tmp_path):
    """Create temporary database for testing."""
    from novel_factory.db.connection import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return str(db_path)
