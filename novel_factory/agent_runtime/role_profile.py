"""Agent Role Profile loader and runtime accessor.

v6.0: Each core agent has a declarative role profile defining mission,
success/failure criteria, capabilities, and collaboration contracts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROLES_DIR = Path(__file__).parent / "roles"


@dataclass
class CollaborationContract:
    """Handoff contract between two agents."""

    to_agent: str
    handoff_artifact: str
    required_fields: list[str] = field(default_factory=list)
    quality_bar: str = ""
    feedback_channel: str = ""
    failure_escalation: str = ""


@dataclass
class RoleProfile:
    """Agent Role Profile v6.0."""

    agent_id: str
    display_name: str
    mission: str
    success_criteria: list[str] = field(default_factory=list)
    failure_criteria: list[str] = field(default_factory=list)
    primary_inputs: list[str] = field(default_factory=list)
    primary_outputs: list[str] = field(default_factory=list)
    owned_artifacts: list[str] = field(default_factory=list)
    decision_authority: list[str] = field(default_factory=list)
    cannot_do: list[str] = field(default_factory=list)
    collaboration_contracts: list[CollaborationContract] = field(default_factory=list)
    default_capability_packs: list[str] = field(default_factory=list)
    eval_dimensions: list[str] = field(default_factory=list)
    cost_budget: dict[str, Any] = field(default_factory=dict)
    trace_policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoleProfile":
        contracts = [
            CollaborationContract(**c) if isinstance(c, dict) else c
            for c in data.pop("collaboration_contracts", [])
        ]
        return cls(collaboration_contracts=contracts, **data)


class RoleProfileRegistry:
    """Registry for loading and querying role profiles."""

    def __init__(self, roles_dir: Path | str | None = None) -> None:
        self.roles_dir = Path(roles_dir) if roles_dir else _ROLES_DIR
        self._profiles: dict[str, RoleProfile] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self.roles_dir.is_dir():
            logger.warning("Roles directory not found: %s", self.roles_dir)
            return
        for path in sorted(self.roles_dir.glob("*.yaml")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if "agent_id" not in data:
                    continue
                profile = RoleProfile.from_dict(data)
                self._profiles[profile.agent_id] = profile
                logger.info("Loaded role profile: %s", profile.agent_id)
            except Exception as e:
                logger.warning("Failed to load role profile %s: %s", path, e)

    def get(self, agent_id: str) -> RoleProfile | None:
        return self._profiles.get(agent_id)

    def list_agents(self) -> list[str]:
        return list(self._profiles.keys())

    def all_profiles(self) -> dict[str, RoleProfile]:
        return dict(self._profiles)


# Global singleton for convenient access
_default_registry: RoleProfileRegistry | None = None


def get_role_profile(agent_id: str) -> RoleProfile | None:
    global _default_registry
    if _default_registry is None:
        _default_registry = RoleProfileRegistry()
    return _default_registry.get(agent_id)


def list_role_profiles() -> dict[str, RoleProfile]:
    global _default_registry
    if _default_registry is None:
        _default_registry = RoleProfileRegistry()
    return _default_registry.all_profiles()
