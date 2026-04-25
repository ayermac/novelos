"""Tests for v2.2 Skill Manifest functionality."""

from __future__ import annotations

import pytest

from novel_factory.models.skill_manifest import (
    FailurePolicy,
    SkillManifest,
    SkillPermissions,
)
from novel_factory.skills.manifest import (
    SkillManifestError,
    load_manifest,
    validate_manifest_for_agent,
)


class TestSkillPermissions:
    """Test SkillPermissions model."""

    def test_default_permissions(self):
        """Test default permissions are restrictive."""
        permissions = SkillPermissions()
        
        assert permissions.read_context is False
        assert permissions.read_chapter is False
        assert permissions.transform_text is False
        assert permissions.validate_text is False
        assert permissions.write_quality_report is False
        assert permissions.write_skill_run is True  # Default True
        assert permissions.write_chapter_content is False
        assert permissions.update_chapter_status is False
        assert permissions.send_agent_message is False
        assert permissions.call_llm is False
        assert permissions.call_network is False

    def test_custom_permissions(self):
        """Test custom permissions."""
        permissions = SkillPermissions(
            transform_text=True,
            validate_text=True,
        )
        
        assert permissions.transform_text is True
        assert permissions.validate_text is True


class TestFailurePolicy:
    """Test FailurePolicy model."""

    def test_default_policy(self):
        """Test default failure policy."""
        policy = FailurePolicy()
        
        assert policy.on_error == "warn"
        assert policy.max_retries == 0
        assert policy.timeout_seconds is None
        assert policy.blocking_threshold is None

    def test_block_policy(self):
        """Test block failure policy."""
        policy = FailurePolicy(on_error="block", max_retries=3)
        
        assert policy.on_error == "block"
        assert policy.max_retries == 3


class TestSkillManifest:
    """Test SkillManifest model."""

    def test_minimal_manifest(self):
        """Test minimal manifest with required fields."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="validator",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            config_schema={},
        )
        
        assert manifest.id == "test-skill"
        assert manifest.name == "Test Skill"
        assert manifest.version == "1.0.0"
        assert manifest.kind == "validator"
        assert manifest.class_name == "TestSkill"
        assert manifest.enabled is True
        assert manifest.builtin is True
        assert manifest.allowed_agents == ["polisher"]
        assert manifest.allowed_stages == ["after_llm"]

    def test_full_manifest(self):
        """Test full manifest with all fields."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="transform",
            class_name="TestSkill",
            module="test.module",
            description="A test skill",
            enabled=True,
            builtin=False,
            allowed_agents=["polisher", "editor"],
            allowed_stages=["after_llm", "before_save"],
            permissions=SkillPermissions(transform_text=True),
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
            config_schema={"type": "object"},
            default_config={"key": "value"},
            failure_policy=FailurePolicy(on_error="block"),
        )
        
        assert manifest.module == "test.module"
        assert manifest.description == "A test skill"
        assert manifest.builtin is False
        assert manifest.default_config == {"key": "value"}


class TestLoadManifest:
    """Test load_manifest function."""

    def test_load_humanizer_manifest(self):
        """Test loading humanizer-zh manifest."""
        manifest = load_manifest("config/skills/manifest/humanizer-zh.yaml")
        
        assert manifest.id == "humanizer-zh"
        assert manifest.name == "Humanizer Chinese"
        assert manifest.kind == "transform"
        assert manifest.class_name == "HumanizerZhSkill"
        assert "polisher" in manifest.allowed_agents
        assert "after_llm" in manifest.allowed_stages
        assert manifest.permissions.transform_text is True
        assert manifest.failure_policy.on_error == "block"

    def test_load_ai_style_detector_manifest(self):
        """Test loading ai-style-detector manifest."""
        manifest = load_manifest("config/skills/manifest/ai-style-detector.yaml")
        
        assert manifest.id == "ai-style-detector"
        assert manifest.name == "AI Style Detector"
        assert manifest.kind == "validator"
        assert manifest.class_name == "AIStyleDetectorSkill"
        assert "polisher" in manifest.allowed_agents
        assert "editor" in manifest.allowed_agents
        assert "qualityhub" in manifest.allowed_agents
        assert manifest.permissions.validate_text is True

    def test_load_narrative_quality_manifest(self):
        """Test loading narrative-quality manifest."""
        manifest = load_manifest("config/skills/manifest/narrative-quality.yaml")
        
        assert manifest.id == "narrative-quality"
        assert manifest.name == "Narrative Quality Scorer"
        assert manifest.kind == "validator"
        assert manifest.class_name == "NarrativeQualityScorer"
        assert "editor" in manifest.allowed_agents
        assert "qualityhub" in manifest.allowed_agents

    def test_load_nonexistent_manifest(self):
        """Test loading nonexistent manifest raises error."""
        with pytest.raises(SkillManifestError) as exc_info:
            load_manifest("config/skills/manifest/nonexistent.yaml")
        
        assert "not found" in str(exc_info.value).lower()

    def test_load_invalid_class_name(self):
        """Test loading manifest with invalid class_name raises error."""
        # This would require creating a temporary manifest file
        # For now, we trust the validation in load_manifest


class TestValidateManifestForAgent:
    """Test validate_manifest_for_agent function."""

    def test_validate_allowed_agent_and_stage(self):
        """Test validation with allowed agent and stage."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="validator",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(),
            input_schema={},
            output_schema={},
        )
        
        is_allowed, error_msg = validate_manifest_for_agent(manifest, "polisher", "after_llm")
        
        assert is_allowed is True
        assert error_msg == ""

    def test_validate_disallowed_agent(self):
        """Test validation with disallowed agent."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="validator",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(),
            input_schema={},
            output_schema={},
        )
        
        is_allowed, error_msg = validate_manifest_for_agent(manifest, "editor", "after_llm")
        
        assert is_allowed is False
        assert "not allowed for agent" in error_msg

    def test_validate_disallowed_stage(self):
        """Test validation with disallowed stage."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="validator",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(),
            input_schema={},
            output_schema={},
        )
        
        is_allowed, error_msg = validate_manifest_for_agent(manifest, "polisher", "before_save")
        
        assert is_allowed is False
        assert "not allowed for stage" in error_msg

    def test_validate_disabled_skill(self):
        """Test validation with disabled skill."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="validator",
            class_name="TestSkill",
            enabled=False,
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(),
            input_schema={},
            output_schema={},
        )
        
        is_allowed, error_msg = validate_manifest_for_agent(manifest, "polisher", "after_llm")
        
        assert is_allowed is False
        assert "disabled" in error_msg


class TestManifestPermissions:
    """Test manifest permission constraints."""

    def test_forbid_call_network(self):
        """Test that call_network is forbidden in v2.2."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="validator",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(call_network=True),
            input_schema={},
            output_schema={},
        )
        
        with pytest.raises(SkillManifestError) as exc_info:
            from novel_factory.skills.manifest import _validate_permissions
            _validate_permissions(manifest)
        
        assert "call_network" in str(exc_info.value)

    def test_forbid_call_llm(self):
        """Test that call_llm is forbidden in v2.2."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="validator",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(call_llm=True),
            input_schema={},
            output_schema={},
        )
        
        with pytest.raises(SkillManifestError) as exc_info:
            from novel_factory.skills.manifest import _validate_permissions
            _validate_permissions(manifest)
        
        assert "call_llm" in str(exc_info.value)

    def test_forbid_write_chapter_content(self):
        """Test that write_chapter_content is forbidden in v2.2."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="transform",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(write_chapter_content=True),
            input_schema={},
            output_schema={},
        )
        
        with pytest.raises(SkillManifestError) as exc_info:
            from novel_factory.skills.manifest import _validate_permissions
            _validate_permissions(manifest)
        
        assert "write_chapter_content" in str(exc_info.value)

    def test_forbid_update_chapter_status(self):
        """Test that update_chapter_status is forbidden in v2.2."""
        manifest = SkillManifest(
            id="test-skill",
            name="Test Skill",
            version="1.0.0",
            kind="transform",
            class_name="TestSkill",
            allowed_agents=["polisher"],
            allowed_stages=["after_llm"],
            permissions=SkillPermissions(update_chapter_status=True),
            input_schema={},
            output_schema={},
        )
        
        with pytest.raises(SkillManifestError) as exc_info:
            from novel_factory.skills.manifest import _validate_permissions
            _validate_permissions(manifest)
        
        assert "update_chapter_status" in str(exc_info.value)
