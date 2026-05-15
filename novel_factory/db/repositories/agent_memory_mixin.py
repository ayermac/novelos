"""Mixin to expose AgentMemoryRepository methods on the main Repository."""

from __future__ import annotations

import json
from typing import Any

from .agent_memory import AgentMemoryRepository


class AgentMemoryRepositoryMixin:
    """Provides agent-memory CRUD on the Repository facade."""

    def _agent_memory_repo(self) -> AgentMemoryRepository:
        return AgentMemoryRepository(self._conn())

    def create_agent_memory(
        self,
        project_id: str,
        agent_id: str,
        memory_type: str,
        key: str,
        value: dict[str, Any],
        confidence: float = 1.0,
        source_run_id: str | None = None,
        source_chapter_number: int | None = None,
    ) -> dict[str, Any]:
        return self._agent_memory_repo().create(
            project_id=project_id,
            agent_id=agent_id,
            memory_type=memory_type,
            key=key,
            value=value,
            confidence=confidence,
            source_run_id=source_run_id,
            source_chapter_number=source_chapter_number,
        )

    def list_agent_memories(
        self,
        project_id: str | None = None,
        agent_id: str | None = None,
        memory_type: str | None = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        return self._agent_memory_repo().list_for_project(
            project_id=project_id,
            agent_id=agent_id,
            memory_type=memory_type,
            enabled_only=enabled_only,
        )

    def set_agent_memory_enabled(self, memory_id: int, enabled: bool) -> bool:
        return self._agent_memory_repo().set_enabled(memory_id, enabled)

    def delete_agent_memory(self, memory_id: int) -> bool:
        return self._agent_memory_repo().delete(memory_id)

    def save_agent_decision_trace(
        self,
        run_id: str,
        project_id: str,
        chapter_number: int,
        agent_id: str,
        stage: str,
        role_profile_id: str = "",
        input_summary: str = "",
        capability_packs_json: str = "[]",
        tool_calls_json: str = "[]",
        skill_results_json: str = "[]",
        self_check_json: str = "{}",
        autonomy_decision_json: str = "{}",
        repair_attempts_json: str = "[]",
        contract_validation_json: str = "{}",
        token_count: int = 0,
        latency_ms: int = 0,
        created_at: str = "",
    ) -> None:
        sql = """
            INSERT INTO agent_decision_traces
            (run_id, project_id, chapter_number, agent_id, stage, role_profile_id,
             input_summary, capability_packs_json, tool_calls_json, skill_results_json,
             self_check_json, autonomy_decision_json, repair_attempts_json,
             contract_validation_json, token_count, latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn = self._conn()
        conn.execute(sql, (
            run_id, project_id, chapter_number, agent_id, stage, role_profile_id,
            input_summary, capability_packs_json, tool_calls_json, skill_results_json,
            self_check_json, autonomy_decision_json, repair_attempts_json,
            contract_validation_json, token_count, latency_ms,
            created_at or None,
        ))
        conn.commit()

    def list_agent_decision_traces(
        self,
        project_id: str,
        chapter_number: int | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if chapter_number is not None:
            clauses.append("chapter_number = ?")
            params.append(chapter_number)
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        sql = "SELECT * FROM agent_decision_traces"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn().execute(sql, params).fetchall()
        return [self._agent_trace_row_to_dict(row) for row in rows]

    def _agent_trace_row_to_dict(self, row: Any) -> dict[str, Any]:
        def parse_json(value: str | None, fallback: Any) -> Any:
            if not value:
                return fallback
            try:
                return json.loads(value)
            except Exception:
                return fallback

        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "project_id": row["project_id"],
            "chapter_number": row["chapter_number"],
            "agent_id": row["agent_id"],
            "stage": row["stage"],
            "role_profile_id": row["role_profile_id"],
            "input_summary": row["input_summary"],
            "capability_packs": parse_json(row["capability_packs_json"], []),
            "tool_calls": parse_json(row["tool_calls_json"], []),
            "skill_results": parse_json(row["skill_results_json"], []),
            "self_check": parse_json(row["self_check_json"], {}),
            "autonomy_decision": parse_json(row["autonomy_decision_json"], {}),
            "repair_attempts": parse_json(row["repair_attempts_json"], []),
            "contract_validation": parse_json(row["contract_validation_json"], {}),
            "token_count": row["token_count"],
            "latency_ms": row["latency_ms"],
            "created_at": row["created_at"],
        }
