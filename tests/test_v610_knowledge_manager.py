"""v6.10.0 Knowledge Manager tests."""

from __future__ import annotations

import os
import tempfile

import pytest
import yaml

from novel_factory.skills.knowledge_manager import KnowledgeManager, KnowledgeSkill
from novel_factory.llm.types import ToolDefinition, ToolResult


@pytest.fixture
def knowledge_dir():
    """Create a temporary knowledge directory with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create index
        index = {"skills": ["test-skill"]}
        with open(os.path.join(tmpdir, "_index.yaml"), "w") as f:
            yaml.dump(index, f)

        # Create skill directory
        skill_dir = os.path.join(tmpdir, "test-skill")
        os.makedirs(skill_dir)

        meta = {
            "skill_id": "test-skill",
            "name": "Test Skill",
            "description": "A test knowledge skill",
            "tags": ["test"],
            "applicable_agents": ["author", "editor"],
            "applicable_genres": ["xuanhuan", "urban"],
            "version": "1.0",
        }
        with open(os.path.join(skill_dir, "meta.yaml"), "w") as f:
            yaml.dump(meta, f)

        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("# Test Skill\n\nThis is test content.\n")

        yield tmpdir


def test_load_all_builtin_skills():
    """KnowledgeManager loads all 11 builtin knowledge skills."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    assert len(km._skills) == 11
    assert "webnovel-excitement" in km._skills
    assert "character-building" in km._skills
    assert "dialogue-naturalness" in km._skills
    assert "pacing-rhythm" in km._skills
    assert "ai-style-avoidance" in km._skills
    assert "show-dont-tell" in km._skills
    assert "scene-sensory" in km._skills
    assert "foreshadowing-management" in km._skills
    assert "worldbuilding" in km._skills
    assert "style-consistency" in km._skills
    assert "genre-suspense" in km._skills


def test_all_skills_have_required_fields():
    """All builtin skills have required metadata fields."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    for skill in km.list_all():
        assert skill.skill_id, f"Missing skill_id"
        assert skill.name, f"{skill.skill_id}: missing name"
        assert skill.description, f"{skill.skill_id}: missing description"
        assert skill.content, f"{skill.skill_id}: missing content"
        assert skill.applicable_agents, f"{skill.skill_id}: missing applicable_agents"


def test_all_skills_have_content():
    """All builtin skills have meaningful Markdown content."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    for skill in km.list_all():
        assert len(skill.content) > 200, f"{skill.skill_id}: content too short ({len(skill.content)} chars)"


def test_author_gets_all_relevant_skills():
    """Author agent gets all 4 knowledge skills."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    skills = km.get_for_agent("author")
    skill_ids = {s.skill_id for s in skills}
    assert "webnovel-excitement" in skill_ids
    assert "character-building" in skill_ids
    assert "dialogue-naturalness" in skill_ids
    assert "pacing-rhythm" in skill_ids


def test_editor_gets_all_relevant_skills():
    """Editor agent gets all 4 knowledge skills."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    skills = km.get_for_agent("editor")
    skill_ids = {s.skill_id for s in skills}
    assert "webnovel-excitement" in skill_ids
    assert "character-building" in skill_ids
    assert "dialogue-naturalness" in skill_ids
    assert "pacing-rhythm" in skill_ids


def test_planner_gets_subset():
    """Planner gets only applicable skills (no dialogue-naturalness)."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    skills = km.get_for_agent("planner")
    skill_ids = {s.skill_id for s in skills}
    assert "webnovel-excitement" in skill_ids
    assert "character-building" in skill_ids
    assert "pacing-rhythm" in skill_ids
    # dialogue-naturalness is not for planner
    assert "dialogue-naturalness" not in skill_ids


def test_polisher_gets_polish_related_skills():
    """Polisher gets polish-related skills (dialogue, ai-style, show-dont-tell, scene, style)."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    skills = km.get_for_agent("polisher")
    skill_ids = {s.skill_id for s in skills}
    assert "dialogue-naturalness" in skill_ids
    assert "ai-style-avoidance" in skill_ids
    assert "show-dont-tell" in skill_ids
    assert "scene-sensory" in skill_ids
    assert "style-consistency" in skill_ids
    assert len(skills) == 5


def test_all_skills_to_tool_definitions():
    """All skills can be converted to tool definitions."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    skills = km.list_all()
    tools = km.to_tool_definitions(skills)
    assert len(tools) == len(skills)
    for tool in tools:
        assert tool.name
        assert tool.description
        assert "context" in tool.parameters


def test_all_skills_execute_tool():
    """All skills can be executed and return content."""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    for skill in km.list_all():
        result = km.execute_tool(skill.skill_id, {})
        assert result.content, f"{skill.skill_id}: execute_tool returned empty"
        assert len(result.content) > 100


def test_load_knowledge_skills(knowledge_dir):
    """KnowledgeManager loads skills from _index.yaml."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    assert len(km._skills) == 1
    assert "test-skill" in km._skills


def test_get_skill(knowledge_dir):
    """get() returns a single skill by ID."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    skill = km.get("test-skill")
    assert skill is not None
    assert skill.name == "Test Skill"
    assert skill.description == "A test knowledge skill"
    assert "This is test content." in skill.content


def test_get_nonexistent_skill(knowledge_dir):
    """get() returns None for unknown skill."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    assert km.get("nonexistent") is None


def test_list_all(knowledge_dir):
    """list_all() returns all skills."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    skills = km.list_all()
    assert len(skills) == 1
    assert skills[0].skill_id == "test-skill"


def test_get_for_agent_filters(knowledge_dir):
    """get_for_agent() filters by agent ID."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    author_skills = km.get_for_agent("author")
    assert len(author_skills) == 1
    assert "author" in author_skills[0].applicable_agents

    planner_skills = km.get_for_agent("planner")
    assert len(planner_skills) == 0


def test_get_for_agent_genre_filter(knowledge_dir):
    """get_for_agent() filters by genre."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)

    # xuanhuan matches
    skills = km.get_for_agent("author", genre="xuanhuan")
    assert len(skills) == 1

    # romance does not match
    skills = km.get_for_agent("author", genre="romance")
    assert len(skills) == 0


def test_get_for_agent_project_overrides_disable(knowledge_dir):
    """Project overrides can disable a knowledge skill."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    overrides = {"knowledge_skills": {"disabled": ["test-skill"]}}
    skills = km.get_for_agent("author", project_overrides=overrides)
    assert len(skills) == 0


def test_get_for_agent_project_overrides_enable_whitelist(knowledge_dir):
    """Project overrides with enable list acts as whitelist."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    overrides = {"knowledge_skills": {"enabled": ["test-skill"]}}
    skills = km.get_for_agent("author", project_overrides=overrides)
    assert len(skills) == 1


def test_to_tool_definitions(knowledge_dir):
    """to_tool_definitions() generates correct ToolDefinition."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    skills = km.get_for_agent("author")
    tools = km.to_tool_definitions(skills)
    assert len(tools) == 1
    assert tools[0].name == "test-skill"
    assert tools[0].description == "A test knowledge skill"
    assert "context" in tools[0].parameters


def test_execute_tool_returns_markdown(knowledge_dir):
    """execute_tool() returns full Markdown content."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    result = km.execute_tool("test-skill", {})
    assert "This is test content." in result.content
    assert result.metadata["skill_id"] == "test-skill"


def test_execute_tool_nonexistent(knowledge_dir):
    """execute_tool() returns error message for unknown skill."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    result = km.execute_tool("nonexistent", {})
    assert "不存在" in result.content


def test_create_skill(knowledge_dir):
    """create_skill() writes files and updates index."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    skill = km.create_skill(
        skill_id="new-skill",
        name="New Skill",
        description="A new skill",
        content="# New Skill\n\nNew content.",
        tags=["new"],
        applicable_agents=["planner"],
    )
    assert skill.skill_id == "new-skill"
    assert "new-skill" in km._skills

    # Verify files exist
    assert os.path.exists(os.path.join(knowledge_dir, "new-skill", "meta.yaml"))
    assert os.path.exists(os.path.join(knowledge_dir, "new-skill", "SKILL.md"))

    # Verify index updated
    with open(os.path.join(knowledge_dir, "_index.yaml")) as f:
        index = yaml.safe_load(f)
    assert "new-skill" in index["skills"]


def test_update_skill(knowledge_dir):
    """update_skill() modifies existing skill."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    skill = km.update_skill("test-skill", name="Updated Name", description="Updated desc")
    assert skill is not None
    assert skill.name == "Updated Name"
    assert skill.description == "Updated desc"

    # Verify persistence
    km2 = KnowledgeManager(knowledge_dir=knowledge_dir)
    assert km2.get("test-skill").name == "Updated Name"


def test_update_nonexistent_skill(knowledge_dir):
    """update_skill() returns None for unknown skill."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    assert km.update_skill("nonexistent", name="X") is None


def test_delete_skill(knowledge_dir):
    """delete_skill() removes files and updates index."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    assert km.delete_skill("test-skill") is True
    assert "test-skill" not in km._skills

    # Verify files removed
    assert not os.path.exists(os.path.join(knowledge_dir, "test-skill"))

    # Verify index updated
    with open(os.path.join(knowledge_dir, "_index.yaml")) as f:
        index = yaml.safe_load(f)
    assert "test-skill" not in index["skills"]


def test_delete_nonexistent_skill(knowledge_dir):
    """delete_skill() returns False for unknown skill."""
    km = KnowledgeManager(knowledge_dir=knowledge_dir)
    assert km.delete_skill("nonexistent") is False


def test_missing_index():
    """KnowledgeManager handles missing _index.yaml gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        km = KnowledgeManager(knowledge_dir=tmpdir)
        assert len(km._skills) == 0


def test_missing_skill_dir():
    """KnowledgeManager handles missing skill directory gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        index = {"skills": ["missing-skill"]}
        with open(os.path.join(tmpdir, "_index.yaml"), "w") as f:
            yaml.dump(index, f)
        km = KnowledgeManager(knowledge_dir=tmpdir)
        assert len(km._skills) == 0
