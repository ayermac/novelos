"""Skill Manifest models for v2.3.

Defines the manifest structure for skills, including permissions,
input/output schemas, failure policies, and package metadata.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SkillPermissions(BaseModel):
    """Permissions granted to a skill.

    v2.2 must enforce that skills cannot:
    - write_chapter_content (default False)
    - update_chapter_status (default False)
    - call_network (default False)
    - call_llm (default False)

    Unless explicitly declared in manifest and allowed by registry.
    """

    read_context: bool = False
    read_chapter: bool = False
    transform_text: bool = False
    validate_text: bool = False
    write_quality_report: bool = False
    write_skill_run: bool = True
    write_chapter_content: bool = False
    update_chapter_status: bool = False
    send_agent_message: bool = False
    call_llm: bool = False
    call_network: bool = False


class FailurePolicy(BaseModel):
    """Failure handling policy for a skill.

    Attributes:
        on_error: How to handle errors - "block", "warn", or "skip"
        max_retries: Maximum number of retries on failure
        timeout_seconds: Timeout for skill execution
        blocking_threshold: Threshold for blocking (e.g., score threshold)
    """

    on_error: Literal["block", "warn", "skip"] = "warn"
    max_retries: int = Field(default=0, ge=0)
    timeout_seconds: Optional[int] = Field(default=None, ge=1)
    blocking_threshold: Optional[float] = None


class SkillPackage(BaseModel):
    """Package metadata for v2.3 skill packages.
    
    Attributes:
        name: Package directory name (e.g., "humanizer_zh")
        handler: Handler file name (e.g., "handler.py")
        entry_class: Main skill class name (e.g., "HumanizerZhSkill")
        prompts_dir: Prompts directory name (optional)
        rules_dir: Rules directory name (optional)
        fixtures: Fixtures file path (e.g., "tests/fixtures.yaml")
    """
    
    name: str
    handler: str = "handler.py"
    entry_class: str
    prompts_dir: Optional[str] = None
    rules_dir: Optional[str] = None
    fixtures: str = "tests/fixtures.yaml"


class SkillManifest(BaseModel):
    """Manifest for a skill.

    Defines the skill's identity, permissions, input/output schemas,
    configuration, and package metadata.
    """

    id: str
    name: str
    version: str
    kind: Literal["transform", "validator", "context", "report"]
    class_name: str
    module: Optional[str] = None
    description: str = ""
    enabled: bool = True
    builtin: bool = True
    allowed_agents: list[str]
    allowed_stages: list[str]
    permissions: SkillPermissions
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: dict[str, Any] = Field(default_factory=dict)
    default_config: dict[str, Any] = Field(default_factory=dict)
    failure_policy: FailurePolicy = Field(default_factory=FailurePolicy)
    # v2.3: Package metadata
    package: Optional[SkillPackage] = None
