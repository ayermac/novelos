"""ContinuityChecker Agent — cross-chapter consistency checker.

ContinuityChecker is a sidecar agent that performs cross-chapter consistency
checks every 3-5 chapters or on manual trigger. It does NOT run on every
chapter in the main pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..db.repository import Repository
from ..llm.provider import LLMProvider
from ..models.sidecar import ContinuityCheckerOutput, ContinuityIssue, ContinuityReport

logger = logging.getLogger(__name__)

CONTINUITY_CHECKER_SYSTEM_PROMPT = """你是小说连续性检查员（ContinuityChecker），负责跨章一致性检查。
你的职责是：检查状态卡连续性、角色关系连续性、伏笔埋设/兑现连续性、地点/时间线跳变、关键设定漂移。

输出格式：严格按 JSON 格式输出，包含以下字段：
- report: 连续性报告对象
  - project_id: 项目ID
  - from_chapter: 起始章节
  - to_chapter: 结束章节
  - issues: 问题列表，每个问题包含：
    - issue_type: 问题类型（state_card, character, plot, location, timeline, setting）
    - severity: 严重程度（error, warning, info）
    - chapter_range: 影响章节范围
    - description: 问题描述
    - recommendation: 建议操作
  - warnings: 警告列表
  - state_card_consistency: 状态卡一致性（布尔值）
  - character_consistency: 角色一致性（布尔值）
  - plot_consistency: 伏笔一致性（布尔值）
  - summary: 总体摘要
- agent_messages: 发送给其他 Agent 的消息列表

核心原则：
1. 只检测问题，不直接修改内容
2. 问题要具体，指出章节号和具体内容
3. 建议要可操作

禁止：
- 直接修改章节内容
- 直接修改状态卡
- 直接退回章节
- 改变章节状态"""


class ContinuityCheckerAgent:
    """ContinuityChecker: cross-chapter consistency checker."""

    agent_id = "continuity_checker"

    def __init__(self, repo: Repository, llm: LLMProvider):
        self.repo = repo
        self.llm = llm

    def run(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
    ) -> dict[str, Any]:
        """Run continuity check across chapters.

        Args:
            project_id: Project identifier.
            from_chapter: Start chapter number.
            to_chapter: End chapter number.

        Returns:
            Dict with success, report, issues, error.
        """
        try:
            # Build context
            context = self._build_context(project_id, from_chapter, to_chapter)

            # Call LLM
            messages = [
                {"role": "system", "content": CONTINUITY_CHECKER_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ]

            response = self.llm.invoke_json(
                messages,
                schema=ContinuityCheckerOutput,
                temperature=0.3,
            )

            # Parse output
            output = ContinuityCheckerOutput(**response)
            report = output.report

            # Count issues and warnings
            issue_count = len([i for i in report.issues if i.severity in ("error", "warning")])
            warning_count = len([i for i in report.issues if i.severity == "warning"])

            # Save to database
            report_id = self.repo.save_continuity_report(
                project_id=project_id,
                from_chapter=from_chapter,
                to_chapter=to_chapter,
                content_json=output.model_dump(),
                summary=report.summary,
                issue_count=issue_count,
                warning_count=warning_count,
            )

            # Send messages to other agents
            for msg in output.agent_messages:
                self.repo.send_agent_message(
                    from_agent=self.agent_id,
                    to_agent=msg.get("to_agent", "planner"),
                    project_id=project_id,
                    message_type=msg.get("type", "continuity_issue"),
                    content=msg.get("content", ""),
                )

            logger.info(f"ContinuityChecker generated report {report_id} for chapters {from_chapter}-{to_chapter}")

            # Send warnings
            self.send_warnings(
                project_id=project_id,
                report_id=report_id,
                report=report,
            )

            return {
                "ok": True,
                "error": None,
                "data": {
                    "report_id": report_id,
                    "report": report.model_dump(),
                    "issue_count": issue_count,
                    "warning_count": warning_count,
                }
            }

        except Exception as e:
            logger.error(f"ContinuityChecker failed: {e}")
            return {"ok": False, "error": str(e), "data": {}}

    def _build_context(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
    ) -> str:
        """Build context for continuity check."""
        parts = []

        # Get chapters in range
        conn = self.repo._conn()
        try:
            chapters = conn.execute(
                "SELECT chapter_number, title, status, word_count "
                "FROM chapters WHERE project_id=? AND chapter_number BETWEEN ? AND ? "
                "ORDER BY chapter_number",
                (project_id, from_chapter, to_chapter),
            ).fetchall()

            if not chapters:
                return f"No chapters found in range {from_chapter}-{to_chapter}"

            chapter_str = "\n".join(
                f"- 第{ch['chapter_number']}章: {ch['title']} (状态: {ch['status']}, 字数: {ch['word_count']})"
                for ch in chapters
            )
            parts.append(f"【章节范围 {from_chapter}-{to_chapter}】\n{chapter_str}")
        finally:
            conn.close()

        # Get chapter states
        states = []
        for ch_num in range(from_chapter, to_chapter + 1):
            state = self.repo.get_chapter_state(project_id, ch_num)
            if state:
                states.append(f"- 第{ch_num}章: {json.dumps(state.get('state_data', {}), ensure_ascii=False)}")
        
        if states:
            parts.append(f"【状态卡】\n" + "\n".join(states))

        # Get plot holes
        plots = self.repo.get_pending_plots(project_id)
        if plots:
            plot_str = "\n".join(
                f"- [{p['code']}] {p['title']} (状态: {p['status']}, 埋设: {p.get('planted_chapter', '?')}, 计划兑现: {p.get('planned_resolve_chapter', '?')})"
                for p in plots
            )
            parts.append(f"【伏笔】\n{plot_str}")

        # Get instructions
        instructions = []
        for ch_num in range(from_chapter, to_chapter + 1):
            instr = self.repo.get_instruction(project_id, ch_num)
            if instr:
                instructions.append(
                    f"- 第{ch_num}章: 目标={instr.get('objective', 'N/A')}, 事件={instr.get('key_events', [])}"
                )
        
        if instructions:
            parts.append(f"【指令】\n" + "\n".join(instructions))

        return "\n\n".join(parts)

    def send_warnings(self, project_id: str, report_id: int, report: ContinuityReport) -> None:
        """Send continuity warnings to Editor and Planner agents.
        
        Args:
            project_id: Project identifier.
            report_id: Continuity report ID.
            report: Continuity report object.
        """
        # Send to Editor if there are issues
        if report.issues:
            self.repo.send_message(
                project_id=project_id,
                from_agent=self.agent_id,
                to_agent="editor",
                msg_type="continuity_warning",
                content={"issues_count": len(report.issues), "report_id": report_id},
            )
        
        # Always send summary to Planner
        self.repo.send_message(
            project_id=project_id,
            from_agent=self.agent_id,
            to_agent="planner",
            msg_type="continuity_summary",
            content={"summary": report.summary, "report_id": report_id},
        )
        
        logger.info(f"ContinuityChecker sent warnings for report {report_id}")
