"""API routes for AgentOps — role profiles, traces, and eval status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..deps import get_repo
from ...agents.role_profile import list_role_profiles
from ...agents.decision_trace import DecisionTraceStore

router = APIRouter(prefix="/agent-ops", tags=["agent-ops"])


@router.get("/role-profiles")
def list_role_profiles_api() -> dict[str, Any]:
    profiles = list_role_profiles()
    return {
        "ok": True,
        "data": {
            "profiles": [
                {
                    "agent_id": p.agent_id,
                    "display_name": p.display_name,
                    "mission": p.mission,
                    "success_criteria": p.success_criteria,
                    "failure_criteria": p.failure_criteria,
                    "default_capability_packs": p.default_capability_packs,
                    "eval_dimensions": p.eval_dimensions,
                }
                for p in profiles.values()
            ]
        }
    }


@router.get("/agent-traces")
def list_agent_traces(
    request: Request,
    project_id: str,
    agent_id: str | None = None,
) -> dict[str, Any]:
    repo = get_repo(request)
    store = DecisionTraceStore(repo)
    traces = store.list_for_project(project_id)
    if agent_id:
        traces = [t for t in traces if t.get("agent_id") == agent_id]
    return {"ok": True, "data": {"traces": traces}}


@router.get("/agent-eval/{agent_id}")
def agent_eval_status(agent_id: str) -> dict[str, Any]:
    # Best-effort: run eval harness for this agent
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "scripts/eval_agents.py", agent_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        import json
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e), "data": {"passed": 0, "failed": 0, "total": 0}}
