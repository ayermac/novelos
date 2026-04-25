"""Scout Agent — generates market reports and opportunity analysis.

Scout is a sidecar agent that analyzes market trends, reader preferences,
and competitor notes to provide context for Planner.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..db.repository import Repository
from ..llm.provider import LLMProvider
from ..models.sidecar import MarketReport, ScoutOutput

logger = logging.getLogger(__name__)

SCOUT_SYSTEM_PROMPT = """你是网文市场分析师（Scout），负责分析市场趋势和读者偏好。
你的职责是：分析题材趋势、读者偏好、竞品情况，为 Planner 提供选题和风格参考。

输出格式：严格按 JSON 格式输出，包含以下字段：
- market_report: 市场报告对象
  - genre: 目标题材
  - platform: 目标平台（可选）
  - audience: 目标读者（可选）
  - trends: 市场趋势列表（3-5条）
  - opportunities: 市场机会列表（2-3条）
  - reader_preferences: 读者偏好列表（3-5条）
  - competitor_notes: 竞品分析列表（2-3条）
  - summary: 执行摘要（1-2句话）
  - recommendations: 可操作建议列表（2-3条）

核心原则：
1. 趋势分析要具体，避免泛泛而谈
2. 读者偏好要基于数据或观察
3. 建议要可操作，能直接指导创作

禁止：
- 直接生成章节内容
- 修改章节状态
- 发布任何内容"""


class ScoutAgent:
    """Scout: generates market reports and opportunity analysis."""

    agent_id = "scout"

    def __init__(self, repo: Repository, llm: LLMProvider):
        self.repo = repo
        self.llm = llm

    def run(
        self,
        project_id: str,
        topic: str | None = None,
        genre: str | None = None,
        platform: str | None = None,
        audience: str | None = None,
    ) -> dict[str, Any]:
        """Run Scout agent to generate market report.

        Args:
            project_id: Project identifier.
            topic: Optional topic to analyze.
            genre: Optional target genre.
            platform: Optional target platform.
            audience: Optional target audience.

        Returns:
            Dict with success, report, and error.
        """
        try:
            # Get project info
            project = self.repo.get_project(project_id)
            if not project:
                return {"ok": False, "error": f"Project not found: {project_id}", "data": {}}

            # Build context
            context = self._build_context(project_id, topic, genre, platform, audience)

            # Call LLM
            messages = [
                {"role": "system", "content": SCOUT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ]

            response = self.llm.invoke_json(
                messages,
                schema=ScoutOutput,
                temperature=0.7,
            )

            # Parse output
            output = ScoutOutput(**response)
            market_report = output.market_report

            # Save to database
            report_id = self.repo.save_market_report(
                project_id=project_id,
                report_type="market_analysis",
                content_json=market_report.model_dump(),
                summary=market_report.summary,
                topic=topic,
                keywords=output.keywords,
            )

            logger.info(f"Scout generated market report {report_id} for project {project_id}")

            # Send summary to Planner
            self.send_summary_to_planner(
                project_id=project_id,
                report_id=report_id,
                summary=market_report.summary,
            )

            return {
                "ok": True,
                "error": None,
                "data": {
                    "report_id": report_id,
                    "market_report": market_report.model_dump(),
                    "keywords": output.keywords,
                }
            }

        except Exception as e:
            logger.error(f"Scout agent failed: {e}")
            return {"ok": False, "error": str(e), "data": {}}

    def _build_context(
        self,
        project_id: str,
        topic: str | None,
        genre: str | None,
        platform: str | None,
        audience: str | None,
    ) -> str:
        """Build context for Scout analysis."""
        parts = []

        # Project info
        project = self.repo.get_project(project_id)
        if project:
            parts.append(f"【项目信息】\n名称: {project.get('name', 'N/A')}\n题材: {project.get('genre', 'N/A')}")

        # Target parameters
        if topic:
            parts.append(f"【分析主题】\n{topic}")
        if genre:
            parts.append(f"【目标题材】\n{genre}")
        if platform:
            parts.append(f"【目标平台】\n{platform}")
        if audience:
            parts.append(f"【目标读者】\n{audience}")

        # Recent chapters summary
        chapters = self.repo.get_recent_chapter_summaries(project_id, before_chapter=999, limit=3)
        if chapters:
            chapter_str = "\n".join(
                f"- 第{c['chapter_number']}章: {c.get('title', 'N/A')}"
                for c in chapters
            )
            parts.append(f"【最近章节】\n{chapter_str}")

        return "\n\n".join(parts)

    def send_summary_to_planner(
        self,
        project_id: str,
        report_id: int,
        summary: str,
    ) -> None:
        """Send a summary message to Planner agent.

        Args:
            project_id: Project identifier.
            report_id: Market report ID.
            summary: Summary message.
        """
        self.repo.send_message(
            project_id=project_id,
            from_agent=self.agent_id,
            to_agent="planner",
            msg_type="market_insight",
            content={"summary": summary, "report_id": report_id},
        )
        logger.info(f"Scout sent market insight to Planner for project {project_id}")
