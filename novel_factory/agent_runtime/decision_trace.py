"""Agent Decision Trace persistence and retrieval.

v6.0: Every agent run produces a decision trace that records:
- role profile used
- input summary
- capability packs executed
- tool calls
- self-check result
- autonomy decision
- repair attempts
- collaboration contract validation
- token/cost/latency
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentDecisionTrace:
    """Structured decision trace for a single agent execution."""

    run_id: str
    project_id: str
    chapter_number: int
    agent_id: str
    stage: str
    role_profile_id: str = ""
    input_summary: str = ""
    capability_packs: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    skill_results: list[dict[str, Any]] = field(default_factory=list)
    self_check: dict[str, Any] = field(default_factory=dict)
    autonomy_decision: dict[str, Any] = field(default_factory=dict)
    repair_attempts: list[dict[str, Any]] = field(default_factory=list)
    contract_validation: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0
    latency_ms: int = 0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "chapter_number": self.chapter_number,
            "agent_id": self.agent_id,
            "stage": self.stage,
            "role_profile_id": self.role_profile_id,
            "input_summary": self.input_summary,
            "capability_packs": self.capability_packs,
            "tool_calls": self.tool_calls,
            "skill_results": self.skill_results,
            "self_check": self.self_check,
            "autonomy_decision": self.autonomy_decision,
            "repair_attempts": self.repair_attempts,
            "contract_validation": self.contract_validation,
            "token_count": self.token_count,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at or _now(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentDecisionTrace":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _now() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


class DecisionTraceStore:
    """In-memory decision trace store with optional DB persistence.

    v6.0 initial implementation uses best-effort DB persistence.
    Falls back to in-memory only if DB methods are unavailable.
    """

    def __init__(self, repo: Any | None = None) -> None:
        self.repo = repo
        self._memory: list[dict[str, Any]] = []

    def save(self, trace: AgentDecisionTrace) -> None:
        data = trace.to_dict()
        self._memory.append(data)
        if self.repo is not None:
            try:
                self._save_to_db(data)
            except Exception as e:
                logger.warning("DecisionTrace DB save failed: %s", e)

    def _save_to_db(self, data: dict[str, Any]) -> None:
        # v6.0: Best-effort persistence via generic method or SQL
        if hasattr(self.repo, "save_agent_decision_trace"):
            self.repo.save_agent_decision_trace(
                run_id=data["run_id"],
                project_id=data["project_id"],
                chapter_number=data["chapter_number"],
                agent_id=data["agent_id"],
                stage=data["stage"],
                role_profile_id=data["role_profile_id"],
                input_summary=data["input_summary"],
                capability_packs_json=json.dumps(data.get("capability_packs", []), ensure_ascii=False),
                tool_calls_json=json.dumps(data.get("tool_calls", []), ensure_ascii=False),
                skill_results_json=json.dumps(data.get("skill_results", []), ensure_ascii=False),
                self_check_json=json.dumps(data.get("self_check", {}), ensure_ascii=False),
                autonomy_decision_json=json.dumps(data.get("autonomy_decision", {}), ensure_ascii=False),
                repair_attempts_json=json.dumps(data.get("repair_attempts", []), ensure_ascii=False),
                contract_validation_json=json.dumps(data.get("contract_validation", {}), ensure_ascii=False),
                token_count=data["token_count"],
                latency_ms=data["latency_ms"],
                created_at=data["created_at"],
            )
        elif hasattr(self.repo, "execute"):
            sql = """
                INSERT INTO agent_decision_traces
                (run_id, project_id, chapter_number, agent_id, stage, role_profile_id,
                 input_summary, capability_packs_json, tool_calls_json, skill_results_json,
                 self_check_json, autonomy_decision_json, repair_attempts_json,
                 contract_validation_json, token_count, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self.repo.execute(sql, (
                data["run_id"], data["project_id"], data["chapter_number"],
                data["agent_id"], data["stage"], data["role_profile_id"],
                data["input_summary"], json.dumps(data.get("capability_packs", []), ensure_ascii=False),
                json.dumps(data.get("tool_calls", []), ensure_ascii=False),
                json.dumps(data.get("skill_results", []), ensure_ascii=False),
                json.dumps(data.get("self_check", {}), ensure_ascii=False),
                json.dumps(data.get("autonomy_decision", {}), ensure_ascii=False),
                json.dumps(data.get("repair_attempts", []), ensure_ascii=False),
                json.dumps(data.get("contract_validation", {}), ensure_ascii=False),
                data["token_count"], data["latency_ms"], data["created_at"],
            ))

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        if self.repo is not None and hasattr(self.repo, "list_agent_decision_traces"):
            try:
                return self.repo.list_agent_decision_traces(
                    project_id=None,
                    run_id=run_id,
                )
            except Exception as e:
                logger.warning("DecisionTrace DB list_for_run failed: %s", e)
        return [t for t in self._memory if t.get("run_id") == run_id]

    def list_for_project(
        self, project_id: str, chapter_number: int | None = None
    ) -> list[dict[str, Any]]:
        if self.repo is not None and hasattr(self.repo, "list_agent_decision_traces"):
            try:
                return self.repo.list_agent_decision_traces(
                    project_id=project_id,
                    chapter_number=chapter_number,
                )
            except Exception as e:
                logger.warning("DecisionTrace DB list_for_project failed: %s", e)
        results = [t for t in self._memory if t.get("project_id") == project_id]
        if chapter_number is not None:
            results = [t for t in results if t.get("chapter_number") == chapter_number]
        return results

    def latest_for_agent(
        self, project_id: str, agent_id: str, chapter_number: int | None = None
    ) -> dict[str, Any] | None:
        if self.repo is not None and hasattr(self.repo, "list_agent_decision_traces"):
            try:
                traces = self.repo.list_agent_decision_traces(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    agent_id=agent_id,
                    limit=1,
                )
                return traces[0] if traces else None
            except Exception as e:
                logger.warning("DecisionTrace DB latest_for_agent failed: %s", e)
        candidates = [t for t in self._memory if t.get("project_id") == project_id and t.get("agent_id") == agent_id]
        if chapter_number is not None:
            candidates = [t for t in candidates if t.get("chapter_number") == chapter_number]
        if not candidates:
            return None
        return candidates[-1]
