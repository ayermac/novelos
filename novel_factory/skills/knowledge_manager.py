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
    tags: list[str] = field(default_factory=list)
    applicable_agents: list[str] = field(default_factory=list)
    applicable_genres: list[str] = field(default_factory=list)
    version: str = "1.0"
    source: str = "builtin"


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
                    tags=meta.get("tags", []),
                    applicable_agents=meta.get("applicable_agents", []),
                    applicable_genres=meta.get("applicable_genres", []),
                    version=meta.get("version", "1.0"),
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
        with self._lock:
            skills = list(self._skills.values())

        results: list[KnowledgeSkill] = []
        for skill in skills:
            # 项目级覆盖
            if project_overrides:
                ks_overrides = project_overrides.get("knowledge_skills", {})
                disabled = ks_overrides.get("disabled", [])
                if skill.skill_id in disabled:
                    continue

                enabled = ks_overrides.get("enabled", [])
                if enabled and skill.skill_id not in enabled:
                    continue

            # Agent 过滤
            if agent_id not in skill.applicable_agents:
                continue

            # Genre 过滤
            if genre and skill.applicable_genres:
                if genre not in skill.applicable_genres:
                    continue

            results.append(skill)
        return results

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
            metadata={"skill_id": skill_id, "name": skill.name},
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
    ) -> KnowledgeSkill:
        """创建新的知识 Skill（写入文件系统）."""
        with self._lock:
            skill_dir = os.path.join(self.knowledge_dir, skill_id)
            os.makedirs(skill_dir, exist_ok=True)

        meta = {
            "skill_id": skill_id,
            "name": name,
            "description": description,
            "tags": tags or [],
            "applicable_agents": applicable_agents or [],
            "applicable_genres": applicable_genres or [],
            "version": "1.0",
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
            tags=tags or [],
            applicable_agents=applicable_agents or [],
            applicable_genres=applicable_genres or [],
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

        # 写入 meta.yaml
        meta = {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "tags": skill.tags,
            "applicable_agents": skill.applicable_agents,
            "applicable_genres": skill.applicable_genres,
            "version": skill.version,
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
