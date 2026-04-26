"""Acceptance capabilities for v5.1 API backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Capability:
    """A capability to be verified."""

    capability_id: str
    label: str
    web_route: str | None
    cli_command: str | None
    success_test: str | None
    failure_test: str | None
    db_assertion: bool
    safety_check: bool
    status: str
    notes: str


CAPABILITIES = [
    # v1-v4.9 capabilities (migrated from v5.0)
    # Note: v5.0 verified 16 capabilities. v5.1 preserves CLI capabilities.
    # Web routes migrated from Jinja to React frontend.
    Capability(
        capability_id="v10_cli_run_chapter",
        label="v1.0 CLI Run Chapter",
        web_route=None,
        cli_command="run-chapter",
        success_test="test_v1_review.py",
        failure_test="test_v1_review.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Core CLI workflow for chapter production",
    ),
    Capability(
        capability_id="v20_batch_production",
        label="v2.0 Batch Production",
        web_route=None,
        cli_command="batch run",
        success_test="test_v3_0_cli.py",
        failure_test="test_v3_0_cli.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Batch production for multiple chapters",
    ),
    Capability(
        capability_id="v31_llm_routing",
        label="v3.1 LLM Routing",
        web_route=None,
        cli_command="llm-profile list",
        success_test="test_v39_llm_cli.py",
        failure_test="test_v39_llm_cli.py",
        db_assertion=False,
        safety_check=True,
        status="pass",
        notes="LLM profiles and agent-level routing",
    ),
    Capability(
        capability_id="v34_production_queue",
        label="v3.4 Production Queue",
        web_route=None,
        cli_command="queue list",
        success_test="test_v34_production_queue.py",
        failure_test="test_v34_production_queue.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Local SQLite production queue",
    ),
    Capability(
        capability_id="v37_review_workbench",
        label="v3.7 Review Workbench",
        web_route=None,
        cli_command="review list",
        success_test="test_v37_review_workbench.py",
        failure_test="test_v37_review_workbench.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Human review workbench",
    ),
    Capability(
        capability_id="v40_style_bible",
        label="v4.0 Style Bible",
        web_route=None,
        cli_command="style-bible init",
        success_test="test_v40_style_bible_cli.py",
        failure_test="test_v40_style_bible_cli.py",
        db_assertion=True,
        safety_check=True,
        status="pass",
        notes="Project-level style configuration",
    ),
    # v5.0 capabilities
    Capability(
        capability_id="v50_acceptance",
        label="v5.0 Feature Acceptance",
        web_route="/api/acceptance",
        cli_command=None,
        success_test=None,
        failure_test=None,
        db_assertion=False,
        safety_check=True,
        status="partial",
        notes="v5.0 verified 16 capabilities via Jinja WebUI. v5.1 preserves CLI, migrates Web to React.",
    ),
    # v5.1 API Backend
    Capability(
        capability_id="v51_api_backend",
        label="v5.1 API Backend",
        web_route="/api/health",
        cli_command="api --help",
        success_test="test_v51_api_backend.py",
        failure_test="test_v51_api_backend.py",
        db_assertion=False,
        safety_check=True,
        status="pass",
        notes="JSON API backend with unified envelope, error handling, and safety",
    ),
    Capability(
        capability_id="v51_frontend",
        label="v5.1 Frontend",
        web_route="/",
        cli_command=None,
        success_test="test_v51_frontend_build.py",
        failure_test=None,
        db_assertion=False,
        safety_check=True,
        status="pass",
        notes="React + Vite + TypeScript frontend with Chinese UX",
    ),
]
