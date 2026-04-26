"""Acceptance Matrix definitions for Web UI.

This module defines all capabilities and their acceptance status
for the Novel Factory Web UI Acceptance Console.

Each capability tracks:
- Web route availability
- CLI command availability
- Test coverage (success and failure cases)
- Database assertion coverage
- Safety checks (no API key/traceback leaks)
- Overall status (pass/partial/missing)
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class Capability(BaseModel):
    """A single capability with acceptance criteria."""
    
    capability_id: str = Field(..., description="Unique identifier for the capability")
    label: str = Field(..., description="Human-readable label")
    web_route: str | None = Field(None, description="Web route path (e.g., '/onboarding')")
    cli_command: str | None = Field(None, description="CLI command (e.g., 'novelos run-chapter')")
    success_test: str | None = Field(None, description="Test file covering success path")
    failure_test: str | None = Field(None, description="Test file covering failure path")
    db_assertion: bool = Field(False, description="Whether tests verify DB state changes")
    safety_check: bool = Field(False, description="Whether tests verify no API key/traceback leaks")
    status: Literal["pass", "partial", "missing"] = Field(..., description="Overall acceptance status")
    notes: str | None = Field(None, description="Additional notes or caveats")


# Define all capabilities
CAPABILITIES: list[Capability] = [
    # Onboarding (v4.5)
    Capability(
        capability_id="onboarding",
        label="Onboarding",
        web_route="/onboarding",
        cli_command=None,
        success_test="test_v45_onboarding.py",
        failure_test="test_v45_onboarding.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Full project creation with chapters, characters, world settings, Style Bible, and optional Serial Plan",
    ),
    
    # Run Chapter (v4.3)
    Capability(
        capability_id="run_chapter",
        label="Run Chapter",
        web_route="/run/chapter",
        cli_command="novelos run-chapter",
        success_test="test_v43_web_routes.py",
        failure_test="test_v43_web_routes.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Single chapter production via Web and CLI",
    ),
    
    # Project Workspace (v4.7)
    Capability(
        capability_id="project_workspace",
        label="Project Workspace",
        web_route="/projects/{project_id}",
        cli_command=None,
        success_test="test_v47_project_workspace.py",
        failure_test="test_v47_project_workspace.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Project-level author cockpit with aggregated status and Next Best Action",
    ),
    
    # Batch Production (v3.0)
    Capability(
        capability_id="batch",
        label="Batch Production",
        web_route="/batch",
        cli_command="novelos batch run",
        success_test="test_batch_production.py",
        failure_test="test_v44_web_ux.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Multi-chapter batch production with review workflow. CLI tests in test_batch_production.py, Web tests in test_v44_web_ux.py",
    ),
    
    # Production Queue (v3.4)
    Capability(
        capability_id="queue",
        label="Production Queue",
        web_route="/queue",
        cli_command="novelos queue",
        success_test="test_v34_production_queue.py",
        failure_test="test_v35_queue_runtime_hardening.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Queue management with pause/resume/retry. Web coverage in test_v44_web_ux.py",
    ),
    
    # Serial Plan (v3.6)
    Capability(
        capability_id="serial",
        label="Serial Plan",
        web_route="/serial",
        cli_command="novelos serial",
        success_test="test_v36_semi_auto_serial_mode.py",
        failure_test="test_v44_web_ux.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Semi-auto serial production with human confirmation gates. Web coverage in test_v44_web_ux.py",
    ),
    
    # Review Workbench (v3.7)
    Capability(
        capability_id="review",
        label="Review Workbench",
        web_route="/review",
        cli_command="novelos review",
        success_test="test_v37_review_workbench.py",
        failure_test="test_v44_web_ux.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Review pack, timeline, diff, and export. Web coverage in test_v44_web_ux.py",
    ),
    
    # Style Bible (v4.0)
    Capability(
        capability_id="style_bible",
        label="Style Bible",
        web_route="/style",
        cli_command="novelos style",
        success_test="test_v40_style_bible_cli.py",
        failure_test="test_v40_style_bible_repository.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Project-level style configuration with templates. Additional tests: test_v40_style_bible_models.py, test_v40_style_bible_context.py, test_v40_style_bible_skill.py",
    ),
    
    # Style Gate (v4.1)
    Capability(
        capability_id="style_gate",
        label="Style Gate",
        web_route="/style",
        cli_command="novelos style gate",
        success_test="test_v41_style_gate.py",
        failure_test="test_v41_style_cli.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Configurable gate (off/warn/block) for style enforcement. Additional tests: test_v41_style_evolution.py, test_v41_style_versions.py",
    ),
    
    # Style Samples (v4.2)
    Capability(
        capability_id="style_samples",
        label="Style Samples",
        web_route="/style",
        cli_command="novelos style sample-import",
        success_test="test_v42_style_sample_repository.py",
        failure_test="test_v42_style_sample_cli.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Sample text analysis for style extraction. Additional tests: test_v42_style_sample_analyzer.py, test_v42_style_sample_proposal.py, test_v42_style_sample_qualityhub.py",
    ),
    
    # Style Proposals (v4.1)
    Capability(
        capability_id="style_proposals",
        label="Style Proposals",
        web_route="/style",
        cli_command="novelos style propose",
        success_test="test_v41_style_evolution.py",
        failure_test="test_v41_style_cli.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Style evolution proposals with human approval. Covered by v4.1 tests",
    ),
    
    # Config / Diagnostics (v4.3)
    Capability(
        capability_id="config",
        label="Config / Diagnostics",
        web_route="/config",
        cli_command="novelos config show",
        success_test="test_v43_web_routes.py",
        failure_test="test_v43_web_routes.py",
        db_assertion=False,
        safety_check=True,
        status="pass",
        notes="Configuration display with API key masking",
    ),
    
    # First Run Guided Workflow (v4.6)
    Capability(
        capability_id="first_run",
        label="First Run Guided Workflow",
        web_route="/onboarding",
        cli_command=None,
        success_test="test_v46_first_run_guided_workflow.py",
        failure_test="test_v46_first_run_guided_workflow.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Guided workflow from project creation to first chapter run",
    ),
    
    # Web UI Acceptance Matrix (v4.8)
    Capability(
        capability_id="acceptance_matrix",
        label="Acceptance Matrix",
        web_route="/acceptance",
        cli_command=None,
        success_test="test_v48_web_acceptance_matrix.py",
        failure_test="test_v48_web_acceptance_matrix.py",
        db_assertion=False,
        safety_check=True,
        status="pass",
        notes="This page - shows acceptance status of all capabilities",
    ),
    
    # Settings / LLM / Agent Ops Console (v4.9)
    Capability(
        capability_id="settings_ops",
        label="Settings / LLM / Agent Ops",
        web_route="/settings",
        cli_command=None,
        success_test="test_v49_settings_llm_agent_ops_console.py",
        failure_test="test_v49_settings_llm_agent_ops_console.py",
        db_assertion=False,
        safety_check=True,
        status="pass",
        notes="Configuration and runtime status console for LLM profiles, agent routing, model recommendations, and diagnostics",
    ),
    
    # Implemented Features & WebUI Acceptance (v5.0)
    Capability(
        capability_id="v50_acceptance",
        label="v5.0 Feature Acceptance",
        web_route="/acceptance",
        cli_command=None,
        success_test="test_v50_implemented_features_webui_acceptance.py",
        failure_test="test_v50_implemented_features_webui_acceptance.py",
        db_assertion=False,
        safety_check=True,
        status="pass",
        notes="Comprehensive acceptance verification of all v1-v4.9 implemented features and WebUI paths",
    ),
]


def get_acceptance_matrix() -> dict:
    """Get the acceptance matrix data for rendering.
    
    Returns:
        Dict with capabilities list and summary statistics
    """
    capabilities_dict = [cap.model_dump() for cap in CAPABILITIES]
    
    # Calculate summary statistics
    total = len(CAPABILITIES)
    passed = sum(1 for cap in CAPABILITIES if cap.status == "pass")
    partial = sum(1 for cap in CAPABILITIES if cap.status == "partial")
    missing = sum(1 for cap in CAPABILITIES if cap.status == "missing")
    
    # Count capabilities with various attributes
    with_web_route = sum(1 for cap in CAPABILITIES if cap.web_route)
    with_cli = sum(1 for cap in CAPABILITIES if cap.cli_command)
    with_success_test = sum(1 for cap in CAPABILITIES if cap.success_test)
    with_failure_test = sum(1 for cap in CAPABILITIES if cap.failure_test)
    with_db_assertion = sum(1 for cap in CAPABILITIES if cap.db_assertion)
    with_safety_check = sum(1 for cap in CAPABILITIES if cap.safety_check)
    
    return {
        "capabilities": capabilities_dict,
        "summary": {
            "total": total,
            "passed": passed,
            "partial": partial,
            "missing": missing,
            "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "0%",
            "with_web_route": with_web_route,
            "with_cli": with_cli,
            "with_success_test": with_success_test,
            "with_failure_test": with_failure_test,
            "with_db_assertion": with_db_assertion,
            "with_safety_check": with_safety_check,
        },
    }


def get_capability_by_id(capability_id: str) -> Capability | None:
    """Get a capability by its ID.
    
    Args:
        capability_id: The unique identifier for the capability
        
    Returns:
        Capability if found, None otherwise
    """
    for cap in CAPABILITIES:
        if cap.capability_id == capability_id:
            return cap
    return None


def validate_capability_ids() -> list[str]:
    """Validate that all capability IDs are unique.
    
    Returns:
        List of duplicate IDs (empty if all unique)
    """
    seen = set()
    duplicates = []
    
    for cap in CAPABILITIES:
        if cap.capability_id in seen:
            duplicates.append(cap.capability_id)
        seen.add(cap.capability_id)
    
    return duplicates
