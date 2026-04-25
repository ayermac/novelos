"""Architect Agent — generates architecture and prompt improvement proposals.

Architect is a sidecar agent that analyzes run data, review results,
and learned patterns to propose improvements to rules, prompts, and architecture.
It does NOT automatically apply changes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..db.repository import Repository
from ..llm.provider import LLMProvider
from ..models.sidecar import ArchitectOutput, ArchitectureProposal

logger = logging.getLogger(__name__)

ARCHITECT_SYSTEM_PROMPT = """你是系统架构师（Architect），负责分析运行数据并提出改进建议。
你的职责是：根据运行数据、退回原因、learned_patterns、death penalty 命中、workflow 失败，提出规则和 Prompt 改进建议。

输出格式：严格按 JSON 格式输出，包含以下字段：
- proposals: 提案列表，每个提案包含：
  - proposal_type: 提案类型（architecture, prompt, quality_rule, migration）
  - scope: 范围（quality, workflow, agent, system）
  - title: 提案标题
  - description: 详细描述
  - risk_level: 风险级别（low, medium, high）
  - affected_area: 影响区域列表
  - recommendation: 建议操作
  - rationale: 理由
  - implementation_notes: 实施说明
  - status: 状态（固定为 pending）
- summary: 提案摘要
- total_proposals: 提案总数

核心原则：
1. 提案必须基于数据，避免主观臆断
2. 风险评估要客观
3. 建议要具体可操作
4. 所有提案默认状态为 pending

禁止：
- 自动修改代码
- 自动修改 prompt
- 自动修改 DB schema
- 自动修改配置
- 修改章节内容"""


class ArchitectAgent:
    """Architect: generates architecture and prompt improvement proposals."""

    agent_id = "architect"

    def __init__(self, repo: Repository, llm: LLMProvider):
        self.repo = repo
        self.llm = llm

    def run(
        self,
        project_id: str,
        scope: str = "quality",
    ) -> dict[str, Any]:
        """Run Architect agent to generate proposals.

        Args:
            project_id: Project identifier.
            scope: Scope of analysis (quality, workflow, agent, system).

        Returns:
            Dict with success, proposals, error.
        """
        try:
            # Build context
            context = self._build_context(project_id, scope)

            # Call LLM
            messages = [
                {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ]

            response = self.llm.invoke_json(
                messages,
                schema=ArchitectOutput,
                temperature=0.5,
            )

            # Parse output
            output = ArchitectOutput(**response)

            # Save proposals to database
            proposal_ids = []
            for proposal in output.proposals:
                proposal_id = self.repo.save_architecture_proposal(
                    project_id=project_id,
                    proposal_type=proposal.proposal_type,
                    scope=proposal.scope,
                    title=proposal.title,
                    description=proposal.description,
                    recommendation=proposal.recommendation,
                    risk_level=proposal.risk_level,
                    affected_area=proposal.affected_area,
                    rationale=proposal.rationale,
                    implementation_notes=proposal.implementation_notes,
                    status="pending",
                )
                proposal_ids.append(proposal_id)

            logger.info(f"Architect generated {len(proposal_ids)} proposals for project {project_id}")

            return {
                "ok": True,
                "error": None,
                "data": {
                    "proposal_ids": proposal_ids,
                    "proposals": [p.model_dump() for p in output.proposals],
                    "summary": output.summary,
                    "total_proposals": output.total_proposals,
                }
            }

        except Exception as e:
            logger.error(f"Architect agent failed: {e}")
            return {"ok": False, "error": str(e), "data": {}}

    def _build_context(self, project_id: str, scope: str) -> str:
        """Build context for Architect analysis."""
        parts = []

        parts.append(f"【分析范围】\n{scope}")

        # Get reviews
        conn = self.repo._conn()
        try:
            reviews = conn.execute(
                "SELECT score, pass, revision_target, summary "
                "FROM reviews WHERE project_id=? "
                "ORDER BY reviewed_at DESC LIMIT 20",
                (project_id,),
            ).fetchall()

            if reviews:
                review_str = "\n".join(
                    f"- 评分: {r['score']}, 通过: {r['pass']}, 退回: {r.get('revision_target', 'N/A')}"
                    for r in reviews
                )
                parts.append(f"【最近审核】\n{review_str}")

                # Calculate statistics
                avg_score = sum(r['score'] for r in reviews) / len(reviews)
                pass_rate = sum(1 for r in reviews if r['pass']) / len(reviews) * 100
                parts.append(f"\n平均分: {avg_score:.1f}, 通过率: {pass_rate:.1f}%")
        finally:
            conn.close()

        # Get workflow runs
        runs = self.repo.get_workflow_runs_for_project(project_id, limit=20)
        if runs:
            failed_runs = [r for r in runs if r.get("status") in ("failed", "blocked")]
            if failed_runs:
                error_str = "\n".join(
                    f"- [{r.get('current_node', '?')}] {r.get('error_message', 'Unknown')[:100]}"
                    for r in failed_runs[:5]
                )
                parts.append(f"【最近失败】\n{error_str}")

        # Get learned patterns
        patterns = self.repo.get_learned_patterns(project_id)
        if patterns:
            pattern_str = "\n".join(
                f"- [{p['pattern_type']}] {p['pattern_data'][:100]}"
                for p in patterns[:10]
            )
            parts.append(f"【学习模式】\n{pattern_str}")

        # Get agent artifacts
        conn = self.repo._conn()
        try:
            artifacts = conn.execute(
                "SELECT agent_id, artifact_type, COUNT(*) as count "
                "FROM agent_artifacts WHERE project_id=? "
                "GROUP BY agent_id, artifact_type",
                (project_id,),
            ).fetchall()

            if artifacts:
                artifact_str = "\n".join(
                    f"- {r['agent_id']}/{r['artifact_type']}: {r['count']}"
                    for r in artifacts
                )
                parts.append(f"【产物统计】\n{artifact_str}")
        finally:
            conn.close()

        return "\n\n".join(parts)
