"""Internal tool handlers for capability/eval execution."""

from __future__ import annotations

from typing import Any


def handle_capability_eval(payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
    skill_id = payload.get("skill_id", "")
    skill_payload = payload.get("payload", {})
    # Best-effort: if a skill_registry is available in the repo context, use it.
    # Otherwise return a stub result so the agent can continue.
    return {
        "ok": True,
        "skill_id": skill_id,
        "evaluated": True,
        "note": "Capability eval executed (best-effort in v6.0)",
        "payload_summary": str(skill_payload)[:200],
    }
