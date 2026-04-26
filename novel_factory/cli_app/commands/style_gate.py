"""v4.1 Style Gate & Evolution CLI commands.

Provides:
- style gate: Show Style Gate config for a project
- style gate set: Configure Style Gate
- style versions: List Style Bible version history
- style version show: Show a specific version
- style propose: Generate style evolution proposals
- style proposals: List style evolution proposals
- style proposal show: Show a specific proposal
- style proposal decide: Approve or reject a proposal
"""

from __future__ import annotations

import json
import sys
from typing import Any

from ..output import print_error_and_exit, print_json_envelope


# ── Style Gate ────────────────────────────────────────────────


def cmd_style_gate(args) -> None:
    """Show Style Gate config for a project."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ...models.style_gate import StyleGateConfig
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        # Check Style Bible exists
        record = repo.get_style_bible(project_id)
        if not record:
            print_error_and_exit(f"No Style Bible found for project '{project_id}'", use_json)
            return

        gate_config = repo.get_style_gate_config(project_id)
        if not gate_config:
            # Return defaults
            config = StyleGateConfig()
            gate_config = config.to_storage_dict()

        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": gate_config}, ensure_ascii=False, indent=2))
        else:
            print(f"Style Gate for project '{project_id}':")
            print(f"  Enabled: {gate_config.get('enabled', False)}")
            print(f"  Mode: {gate_config.get('mode', 'warn')}")
            print(f"  Blocking Threshold: {gate_config.get('blocking_threshold', 70)}")
            print(f"  Max Blocking Issues: {gate_config.get('max_blocking_issues', 0)}")
            print(f"  Revision Target: {gate_config.get('revision_target', 'polisher')}")
            print(f"  Apply Stages: {', '.join(gate_config.get('apply_stages', ['polished', 'final_gate']))}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_gate_set(args) -> None:
    """Configure Style Gate for a project."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ...models.style_gate import StyleGateConfig, StyleGateMode, StyleGateStage
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")
    mode = getattr(args, "mode", None)
    threshold = getattr(args, "threshold", None)
    max_blocking = getattr(args, "max_blocking", None)
    revision_target = getattr(args, "revision_target", None)
    enabled = getattr(args, "enabled", None)
    stages = getattr(args, "stages", None)

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        # Check Style Bible exists
        record = repo.get_style_bible(project_id)
        if not record:
            print_error_and_exit(f"No Style Bible found for project '{project_id}'", use_json)
            return

        # Load existing config or defaults
        existing = repo.get_style_gate_config(project_id)
        if existing:
            config = StyleGateConfig.from_storage_dict(existing)
        else:
            config = StyleGateConfig()

        # Apply overrides
        if mode is not None:
            try:
                config.mode = StyleGateMode(mode)
                if config.mode != StyleGateMode.OFF:
                    config.enabled = True
            except ValueError:
                print_error_and_exit(f"Invalid mode '{mode}'. Use: off, warn, block", use_json)
                return

        if threshold is not None:
            config.blocking_threshold = int(threshold)

        if max_blocking is not None:
            config.max_blocking_issues = int(max_blocking)

        if revision_target is not None:
            if revision_target not in ("author", "polisher"):
                print_error_and_exit("revision-target must be 'author' or 'polisher'", use_json)
                return
            config.revision_target = revision_target

        if enabled is not None:
            config.enabled = enabled

        if stages is not None:
            try:
                config.apply_stages = [StyleGateStage(s.strip()) for s in stages.split(",")]
            except ValueError:
                print_error_and_exit(f"Invalid stages. Use: draft, polished, final_gate", use_json)
                return

        # Save
        ok = repo.set_style_gate_config(project_id, config.to_storage_dict())
        if not ok:
            print_error_and_exit(f"Failed to update Style Gate config", use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": config.to_storage_dict(),
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Gate updated for project '{project_id}'")
            print(f"  Mode: {config.mode.value}")
            print(f"  Enabled: {config.enabled}")
            print(f"  Threshold: {config.blocking_threshold}")
            print(f"  Revision Target: {config.revision_target}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


# ── Style Bible Versions ──────────────────────────────────────


def cmd_style_versions(args) -> None:
    """List Style Bible version history."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        versions = repo.get_style_bible_versions(project_id)

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {"versions": versions, "total": len(versions)},
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Bible Versions for '{project_id}' ({len(versions)}):")
            for v in versions:
                print(f"  [{v['version']}] {v['created_at']} by {v['created_by']}")
                if v.get("change_summary"):
                    print(f"    {v['change_summary']}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_version_show(args) -> None:
    """Show a specific Style Bible version."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    version_id = getattr(args, "version_id", "")

    if not version_id:
        print_error_and_exit("--version-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        version = repo.get_style_bible_version(version_id)
        if not version:
            print_error_and_exit(f"Version '{version_id}' not found", use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": version,
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Bible Version: {version['version']}")
            print(f"  ID: {version['id']}")
            print(f"  Project: {version['project_id']}")
            print(f"  Created: {version['created_at']} by {version['created_by']}")
            if version.get("change_summary"):
                print(f"  Summary: {version['change_summary']}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


# ── Style Evolution Proposals ─────────────────────────────────


def cmd_style_propose(args) -> None:
    """Generate style evolution proposals."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ...style_bible.evolution import propose_style_evolution
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        result = propose_style_evolution(project_id, repo)

        if not result.get("ok"):
            print_error_and_exit(result.get("error", "Unknown error"), use_json)
            return

        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            data = result.get("data", {})
            print(f"Style Evolution Proposals for '{project_id}':")
            print(f"  Created: {data.get('proposals_created', 0)}")
            for pid in data.get("proposal_ids", []):
                print(f"    - {pid}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_proposals(args) -> None:
    """List style evolution proposals."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")
    status = getattr(args, "status", None)

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        proposals = repo.list_style_evolution_proposals(project_id, status=status)

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {"proposals": proposals, "total": len(proposals)},
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Evolution Proposals for '{project_id}' ({len(proposals)}):")
            for p in proposals:
                print(f"  [{p['status']}] {p['proposal_type']} - {p.get('rationale', '')[:60]}")
                print(f"    ID: {p['id']}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_proposal_show(args) -> None:
    """Show a specific style evolution proposal."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    proposal_id = getattr(args, "proposal_id", "")

    if not proposal_id:
        print_error_and_exit("--proposal-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        proposal = repo.get_style_evolution_proposal(proposal_id)
        if not proposal:
            print_error_and_exit(f"Proposal '{proposal_id}' not found", use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": proposal,
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Evolution Proposal:")
            print(f"  ID: {proposal['id']}")
            print(f"  Type: {proposal['proposal_type']}")
            print(f"  Status: {proposal['status']}")
            print(f"  Source: {proposal['source']}")
            print(f"  Rationale: {proposal.get('rationale', '')}")
            print(f"  Created: {proposal['created_at']}")
            if proposal.get("decided_at"):
                print(f"  Decided: {proposal['decided_at']} ({proposal['status']})")
                if proposal.get("decision_notes"):
                    print(f"  Notes: {proposal['decision_notes']}")
            print(f"  Proposal: {json.dumps(proposal.get('proposal', {}), ensure_ascii=False, indent=2)}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_proposal_decide(args) -> None:
    """Approve or reject a style evolution proposal."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    proposal_id = getattr(args, "proposal_id", "")
    decision = getattr(args, "decision", "")
    notes = getattr(args, "notes", None)

    if not proposal_id:
        print_error_and_exit("--proposal-id is required", use_json)
        return

    if decision not in ("approve", "reject"):
        print_error_and_exit("--decision must be 'approve' or 'reject'", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        # Verify proposal exists
        proposal = repo.get_style_evolution_proposal(proposal_id)
        if not proposal:
            print_error_and_exit(f"Proposal '{proposal_id}' not found", use_json)
            return

        if proposal["status"] != "pending":
            print_error_and_exit(
                f"Proposal is already '{proposal['status']}', cannot change",
                use_json,
            )
            return

        db_decision = "approved" if decision == "approve" else "rejected"
        ok = repo.decide_style_evolution_proposal(proposal_id, db_decision, notes=notes)
        if not ok:
            print_error_and_exit("Failed to update proposal status", use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {
                    "proposal_id": proposal_id,
                    "decision": db_decision,
                    "notes": notes or "",
                    "note": "v4.1: approve does NOT auto-apply to Style Bible",
                },
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Proposal '{proposal_id}' {db_decision}")
            if notes:
                print(f"  Notes: {notes}")
            print("  Note: v4.1 does not auto-apply proposals to Style Bible")
    except ValueError as e:
        print_error_and_exit(str(e), use_json)
    except Exception as e:
        print_error_and_exit(str(e), use_json)
