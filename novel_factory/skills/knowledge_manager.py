"""知识 Skill 管理器.

v6.10.0: 加载、查询和执行知识 Skill（Markdown 领域知识文档）。
知识 Skill 是 LLM 可主动咨询的领域知识，不同于 Code Skill（Python 代码执行器）。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

import yaml

from novel_factory.llm.types import ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeSkill:
    """知识 Skill 数据模型."""

    skill_id: str
    name: str
    description: str
    content: str
    namespace: str = "knowledge"
    tags: list[str] = field(default_factory=list)
    applicable_agents: list[str] = field(default_factory=list)
    applicable_genres: list[str] = field(default_factory=list)
    enabled: bool = True
    priority: int = 50
    token_budget: int = 1200
    injection_mode: str = "auto"  # auto | always | agentic_only | disabled
    version: str = "1.0"
    source: str = "builtin"
    layer: str = "knowledge"
    category: str = "general"
    paired_code_skill_ids: list[str] = field(default_factory=list)
    default_agents: list[str] = field(default_factory=list)
    editable: bool = True

    @property
    def qualified_id(self) -> str:
        """Return namespaced id for UI/logs."""
        return f"{self.namespace}:{self.skill_id}"

    @property
    def estimated_tokens(self) -> int:
        """Cheap deterministic token estimate for budget selection."""
        return max(1, len(self.content) // 4)


@dataclass
class KnowledgeSelection:
    """Result of selecting knowledge skills for an agent invocation."""

    skills: list[KnowledgeSkill] = field(default_factory=list)
    selection_reason: dict[str, list[str]] = field(default_factory=dict)
    estimated_tokens: int = 0
    token_budget: int = 0
    trimmed_skill_ids: list[str] = field(default_factory=list)

    def to_audit_payload(self, *, agent: str, genre: str | None = None) -> dict[str, Any]:
        """Serialize selection for timeline/audit events."""
        return {
            "agent": agent,
            "genre": genre,
            "skill_ids": [s.qualified_id for s in self.skills],
            "versions": {s.skill_id: s.version for s in self.skills},
            "estimated_tokens": self.estimated_tokens,
            "token_budget": self.token_budget,
            "selection_reason": self.selection_reason,
            "trimmed_skill_ids": self.trimmed_skill_ids,
        }


class KnowledgeManager:
    """管理知识 Skill 的加载和查询.

    知识 Skill 存储在 novel_factory/skills/knowledge/ 目录下，
    每个 Skill 包含 meta.yaml（元数据）和 SKILL.md（Markdown 内容）。
    """

    _instance_cache: dict[str, KnowledgeManager] = {}

    def __new__(cls, knowledge_dir: str) -> KnowledgeManager:
        """Singleton per directory to avoid重复加载."""
        abs_dir = os.path.abspath(knowledge_dir)
        if abs_dir not in cls._instance_cache:
            instance = super().__new__(cls)
            cls._instance_cache[abs_dir] = instance
        return cls._instance_cache[abs_dir]

    def __init__(self, knowledge_dir: str):
        abs_dir = os.path.abspath(knowledge_dir)
        if hasattr(self, '_initialized') and self._knowledge_dir == abs_dir:
            return
        self._initialized = True
        self._knowledge_dir = abs_dir
        self.knowledge_dir = knowledge_dir
        self._skills: dict[str, KnowledgeSkill] = {}
        self._lock = threading.RLock()
        self._load_all()

    def _load_all(self) -> None:
        """扫描目录，加载所有知识 Skill."""
        index_path = os.path.join(self.knowledge_dir, "_index.yaml")
        if not os.path.exists(index_path):
            logger.warning("Knowledge index not found: %s", index_path)
            return

        with open(index_path, encoding="utf-8") as f:
            index = yaml.safe_load(f)

        for skill_id in index.get("skills", []):
            skill_dir = os.path.join(self.knowledge_dir, skill_id)
            meta_path = os.path.join(skill_dir, "meta.yaml")
            skill_path = os.path.join(skill_dir, "SKILL.md")

            if not os.path.exists(meta_path):
                logger.warning("Meta not found for knowledge skill: %s", skill_id)
                continue
            if not os.path.exists(skill_path):
                logger.warning("SKILL.md not found for knowledge skill: %s", skill_id)
                continue

            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = yaml.safe_load(f)
                with open(skill_path, encoding="utf-8") as f:
                    content = f.read()

                self._skills[skill_id] = KnowledgeSkill(
                    skill_id=skill_id,
                    name=meta.get("name", skill_id),
                    description=meta.get("description", ""),
                    namespace=meta.get("namespace", "knowledge"),
                    tags=meta.get("tags", []),
                    applicable_agents=meta.get("applicable_agents", []),
                    applicable_genres=meta.get("applicable_genres", []),
                    enabled=bool(meta.get("enabled", True)),
                    priority=int(meta.get("priority", 50) or 50),
                    token_budget=int(meta.get("token_budget", 1200) or 1200),
                    injection_mode=meta.get("injection_mode", "auto") or "auto",
                    version=meta.get("version", "1.0"),
                    source=meta.get("source", "builtin"),
                    layer=meta.get("layer", "knowledge"),
                    category=meta.get("category", "general"),
                    paired_code_skill_ids=meta.get("paired_code_skill_ids", []),
                    default_agents=meta.get("default_agents", meta.get("applicable_agents", [])),
                    editable=bool(meta.get("editable", True)),
                    content=content,
                )
                logger.info("Loaded knowledge skill: %s", skill_id)
            except Exception:
                logger.exception("Failed to load knowledge skill: %s", skill_id)

    def list_all(self) -> list[KnowledgeSkill]:
        """列出所有知识 Skill."""
        with self._lock:
            return list(self._skills.values())

    def get(self, skill_id: str) -> KnowledgeSkill | None:
        """获取单个知识 Skill."""
        with self._lock:
            return self._skills.get(skill_id)

    def get_for_agent(
        self,
        agent_id: str,
        genre: str | None = None,
        project_overrides: dict[str, Any] | None = None,
    ) -> list[KnowledgeSkill]:
        """获取指定 Agent 可用的知识 Skill（支持 genre 和项目覆盖过滤）."""
        return self.select_for_agent(
            agent_id,
            genre=genre,
            project_overrides=project_overrides,
            token_budget=10**9,
        ).skills

    def select_for_agent(
        self,
        agent_id: str,
        genre: str | None = None,
        project_overrides: dict[str, Any] | None = None,
        token_budget: int | None = None,
        target: str = "prompt",
        quality_signals: list[str] | None = None,
    ) -> KnowledgeSelection:
        """Select knowledge skills for an agent with budget and audit reasons.

        Args:
            agent_id: Agent id such as ``author``.
            genre: Optional project genre.
            project_overrides: Project-level override document.
            token_budget: Hard budget for selected knowledge.
            target: ``prompt`` or ``agentic``.
            quality_signals: Optional quality issue codes to bias selection.
        """
        with self._lock:
            skills = list(self._skills.values())

        quality_signals = quality_signals or []
        budget = max(
            0,
            int(
                token_budget
                if token_budget is not None
                else self._default_token_budget(project_overrides) or 2400
            ),
        )
        candidates: list[tuple[KnowledgeSkill, list[str]]] = []
        for skill in skills:
            effective = self._apply_project_override(skill, project_overrides)
            if not effective.enabled or effective.injection_mode == "disabled":
                continue

            if agent_id not in effective.applicable_agents:
                continue

            if genre and effective.applicable_genres:
                if genre not in effective.applicable_genres:
                    continue

            if target == "prompt" and effective.injection_mode == "agentic_only":
                continue

            reasons = ["agent_match"]
            if genre and effective.applicable_genres:
                reasons.append(f"genre_match:{genre}")
            if effective.injection_mode == "always":
                reasons.append("injection_mode:always")
            for signal in quality_signals:
                if self._signal_matches_skill(signal, effective):
                    reasons.append(f"quality_signal:{signal}")
            candidates.append((effective, reasons))

        candidates.sort(
            key=lambda item: (
                0 if item[0].injection_mode == "always" else 1,
                -item[0].priority,
                item[0].skill_id,
            )
        )

        selected: list[KnowledgeSkill] = []
        reasons_by_id: dict[str, list[str]] = {}
        trimmed: list[str] = []
        used = 0
        for skill, reasons in candidates:
            estimate = min(skill.estimated_tokens, max(1, skill.token_budget))
            if used + estimate > budget:
                trimmed.append(skill.skill_id)
                continue
            selected.append(skill)
            reasons_by_id[skill.skill_id] = reasons
            used += estimate

        return KnowledgeSelection(
            skills=selected,
            selection_reason=reasons_by_id,
            estimated_tokens=used,
            token_budget=budget,
            trimmed_skill_ids=trimmed,
        )

    @staticmethod
    def _default_token_budget(project_overrides: dict[str, Any] | None) -> int | None:
        if not isinstance(project_overrides, dict):
            return None
        ks_overrides = project_overrides.get("knowledge_skills", {})
        if not isinstance(ks_overrides, dict):
            return None
        value = ks_overrides.get("token_budget") or ks_overrides.get("default_token_budget")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _apply_project_override(
        self,
        skill: KnowledgeSkill,
        project_overrides: dict[str, Any] | None,
    ) -> KnowledgeSkill:
        """Return an effective skill copy with project overrides applied."""
        if not isinstance(project_overrides, dict):
            return skill
        ks_overrides = project_overrides.get("knowledge_skills", {})
        if not isinstance(ks_overrides, dict):
            return skill

        disabled = set(ks_overrides.get("disabled", []) or [])
        enabled_list = ks_overrides.get("enabled", []) or []
        enabled_set = set(enabled_list) if isinstance(enabled_list, list) else set()
        per_skill = ks_overrides.get("overrides", {})
        if not isinstance(per_skill, dict):
            per_skill = {}
        entry = per_skill.get(skill.skill_id, {})
        if not isinstance(entry, dict):
            entry = {}

        effective = KnowledgeSkill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            content=skill.content,
            namespace=skill.namespace,
            tags=list(skill.tags),
            applicable_agents=list(skill.applicable_agents),
            applicable_genres=list(skill.applicable_genres),
            enabled=skill.enabled,
            priority=skill.priority,
            token_budget=skill.token_budget,
            injection_mode=skill.injection_mode,
            version=skill.version,
            source=skill.source,
            layer=skill.layer,
            category=skill.category,
            paired_code_skill_ids=list(skill.paired_code_skill_ids),
            default_agents=list(skill.default_agents),
            editable=skill.editable,
        )

        if skill.skill_id in disabled or skill.qualified_id in disabled:
            effective.enabled = False
        if enabled_set and skill.skill_id not in enabled_set and skill.qualified_id not in enabled_set:
            effective.enabled = False
        if "enabled" in entry:
            effective.enabled = bool(entry.get("enabled"))
        if "priority" in entry:
            try:
                effective.priority = int(entry["priority"])
            except (TypeError, ValueError):
                pass
        if "token_budget" in entry:
            try:
                effective.token_budget = int(entry["token_budget"])
            except (TypeError, ValueError):
                pass
        if entry.get("injection_mode"):
            effective.injection_mode = str(entry["injection_mode"])
        return effective

    @staticmethod
    def _signal_matches_skill(signal: str, skill: KnowledgeSkill) -> bool:
        signal_text = str(signal).lower()
        haystack = " ".join([skill.skill_id, skill.name, *skill.tags]).lower()
        signal_map = {
            "straight_emotion": ["show-dont-tell", "ai-style", "naturalness"],
            "low_colloquial": ["dialogue", "naturalness"],
            "exposition": ["info", "worldbuilding", "scene"],
            "system_mechanics": ["webnovel", "worldbuilding", "pacing"],
        }
        for key, needles in signal_map.items():
            if key in signal_text:
                return any(needle in haystack for needle in needles)
        return signal_text in haystack

    def to_tool_definitions(self, skills: list[KnowledgeSkill]) -> list[ToolDefinition]:
        """将知识 Skill 转换为 LLM Tool 定义."""
        return [
            ToolDefinition(
                name=s.skill_id,
                description=s.description,
                parameters={
                    "context": {
                        "type": "string",
                        "description": "当前写作上下文（可选），用于获取更有针对性的建议",
                    }
                },
            )
            for s in skills
        ]

    def execute_tool(self, skill_id: str, arguments: dict[str, Any]) -> ToolResult:
        """执行知识 Tool：返回 Markdown 内容."""
        skill = self._skills.get(skill_id)
        if not skill:
            return ToolResult(content=f"知识 Skill '{skill_id}' 不存在")

        return ToolResult(
            content=skill.content,
            metadata={
                "skill_id": skill_id,
                "qualified_id": skill.qualified_id,
                "name": skill.name,
                "version": skill.version,
            },
        )

    def create_skill(
        self,
        skill_id: str,
        name: str,
        description: str,
        content: str,
        tags: list[str] | None = None,
        applicable_agents: list[str] | None = None,
        applicable_genres: list[str] | None = None,
        enabled: bool = True,
        priority: int = 50,
        token_budget: int = 1200,
        injection_mode: str = "auto",
        source: str = "user",
    ) -> KnowledgeSkill:
        """创建新的知识 Skill（写入文件系统）."""
        with self._lock:
            skill_dir = os.path.join(self.knowledge_dir, skill_id)
            os.makedirs(skill_dir, exist_ok=True)

        meta = {
            "skill_id": skill_id,
            "name": name,
            "description": description,
            "namespace": "knowledge",
            "layer": "knowledge",
            "category": "general",
            "paired_code_skill_ids": [],
            "default_agents": applicable_agents or [],
            "editable": True,
            "enabled": enabled,
            "priority": priority,
            "token_budget": token_budget,
            "injection_mode": injection_mode,
            "tags": tags or [],
            "applicable_agents": applicable_agents or [],
            "applicable_genres": applicable_genres or [],
            "version": "1.0",
            "source": source,
        }

        with open(os.path.join(skill_dir, "meta.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(meta, f, allow_unicode=True, default_flow_style=False)

        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(content)

        # 更新 index
        index_path = os.path.join(self.knowledge_dir, "_index.yaml")
        with open(index_path, encoding="utf-8") as f:
            index = yaml.safe_load(f)

        skills_list = index.get("skills", [])
        if skill_id not in skills_list:
            skills_list.append(skill_id)
            index["skills"] = skills_list
            with open(index_path, "w", encoding="utf-8") as f:
                yaml.dump(index, f, allow_unicode=True, default_flow_style=False)

        skill = KnowledgeSkill(
            skill_id=skill_id,
            name=name,
            description=description,
            content=content,
            namespace="knowledge",
            tags=tags or [],
            applicable_agents=applicable_agents or [],
            applicable_genres=applicable_genres or [],
            enabled=enabled,
            priority=priority,
            token_budget=token_budget,
            injection_mode=injection_mode,
            source=source,
            layer="knowledge",
            category="general",
            paired_code_skill_ids=[],
            default_agents=applicable_agents or [],
            editable=True,
        )
        self._skills[skill_id] = skill
        logger.info("Created knowledge skill: %s", skill_id)
        return skill

    def update_skill(
        self,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        applicable_agents: list[str] | None = None,
        applicable_genres: list[str] | None = None,
        enabled: bool | None = None,
        priority: int | None = None,
        token_budget: int | None = None,
        injection_mode: str | None = None,
    ) -> KnowledgeSkill | None:
        """更新知识 Skill."""
        with self._lock:
            skill = self._skills.get(skill_id)
            if not skill:
                return None

        skill_dir = os.path.join(self.knowledge_dir, skill_id)

        if name is not None:
            skill.name = name
        if description is not None:
            skill.description = description
        if content is not None:
            skill.content = content
        if tags is not None:
            skill.tags = tags
        if applicable_agents is not None:
            skill.applicable_agents = applicable_agents
        if applicable_genres is not None:
            skill.applicable_genres = applicable_genres
        if enabled is not None:
            skill.enabled = enabled
        if priority is not None:
            skill.priority = priority
        if token_budget is not None:
            skill.token_budget = token_budget
        if injection_mode is not None:
            skill.injection_mode = injection_mode

        # 写入 meta.yaml
        meta = {
            "skill_id": skill.skill_id,
            "namespace": skill.namespace,
            "name": skill.name,
            "description": skill.description,
            "layer": skill.layer,
            "category": skill.category,
            "paired_code_skill_ids": skill.paired_code_skill_ids,
            "default_agents": skill.default_agents,
            "editable": skill.editable,
            "enabled": skill.enabled,
            "priority": skill.priority,
            "token_budget": skill.token_budget,
            "injection_mode": skill.injection_mode,
            "tags": skill.tags,
            "applicable_agents": skill.applicable_agents,
            "applicable_genres": skill.applicable_genres,
            "version": skill.version,
            "source": skill.source,
        }
        with open(os.path.join(skill_dir, "meta.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(meta, f, allow_unicode=True, default_flow_style=False)

        # 写入 SKILL.md
        if content is not None:
            with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(content)

        logger.info("Updated knowledge skill: %s", skill_id)
        return skill

    def delete_skill(self, skill_id: str) -> bool:
        """删除知识 Skill."""
        with self._lock:
            if skill_id not in self._skills:
                return False

        skill_dir = os.path.join(self.knowledge_dir, skill_id)

        # 删除文件
        meta_path = os.path.join(skill_dir, "meta.yaml")
        skill_path = os.path.join(skill_dir, "SKILL.md")
        if os.path.exists(meta_path):
            os.remove(meta_path)
        if os.path.exists(skill_path):
            os.remove(skill_path)
        if os.path.exists(skill_dir):
            os.rmdir(skill_dir)

        # 从 index 移除
        index_path = os.path.join(self.knowledge_dir, "_index.yaml")
        with open(index_path, encoding="utf-8") as f:
            index = yaml.safe_load(f)

        skills_list = index.get("skills", [])
        if skill_id in skills_list:
            skills_list.remove(skill_id)
            index["skills"] = skills_list
            with open(index_path, "w", encoding="utf-8") as f:
                yaml.dump(index, f, allow_unicode=True, default_flow_style=False)

        del self._skills[skill_id]
        logger.info("Deleted knowledge skill: %s", skill_id)
        return True
