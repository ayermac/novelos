"""Helpers for exposing core-loop evidence diagnostics to API consumers."""

from __future__ import annotations

import json
from typing import Any


def _parse_ledger_data(row: dict | None) -> dict[str, Any]:
    if not row:
        return {}
    data = row.get("ledger_data") or {}
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def get_core_loop_diagnostics_for_chapter(
    repo: Any,
    project_id: str,
    chapter_number: int,
) -> dict[str, Any] | None:
    """Return the latest contract metrics as UI-friendly diagnostics."""
    try:
        row = repo.get_creative_ledger(project_id, chapter_number, "contract_metrics")
    except Exception:
        row = None
    data = _parse_ledger_data(row)
    if not data:
        return None

    missing = list(data.get("missing_evidence") or [])
    warnings = list(data.get("contract_drift_warnings") or [])
    evidence_spans = data.get("evidence_spans") if isinstance(data.get("evidence_spans"), dict) else {}
    tracked_states = data.get("tracked_states") if isinstance(data.get("tracked_states"), dict) else {}
    state_deltas = data.get("state_deltas") if isinstance(data.get("state_deltas"), list) else []

    return {
        "chapter_number": int(data.get("chapter_number") or chapter_number),
        "score": data.get("contract_score", 0),
        "core_payoff_present": bool(data.get("core_payoff_present")),
        "reward_acquired": bool(data.get("reward_acquired")),
        "reward_used": bool(data.get("reward_used")),
        "enemy_consequence": bool(data.get("enemy_consequence")),
        "required_payoff_present": bool(data.get("required_payoff_present", True)),
        "missing_evidence": missing,
        "warnings": warnings,
        "evidence_spans": evidence_spans,
        "tracked_states": tracked_states,
        "state_deltas": state_deltas,
        "core_loop_steps_completed": data.get("core_loop_steps_completed") or [],
        "dominant_mechanism": data.get("dominant_mechanism") or "",
    }
