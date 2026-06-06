"""v6.9.0: CreativeLedgerCurator agent skeleton.

Updates creative ledgers (reader promises, power growth, character arcs,
mystery reveals, conflicts, payoffs, style fatigue) after each chapter
passes review. Produces incremental patches, not full rewrites.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..agent_runtime.base import BaseAgent

logger = logging.getLogger(__name__)


class CreativeLedgerCurator(BaseAgent):
    """Agent responsible for updating creative ledgers after chapter review.

    This agent runs AFTER a chapter passes the chief_editor review.
    It reads the previous chapter's ledger snapshots and the current chapter's
    content/review, then produces incremental patches for each ledger.
    """

    def __init__(self, repo: Any, llm: Any) -> None:
        super().__init__(repo, llm)
        self.ledger_types = [
            "reader_promise",
            "power_growth",
            "character_arc",
            "mystery_reveal",
            "conflict",
            "payoff",
            "style_fatigue",
        ]

    def _execute(self, state: dict) -> dict:
        """Execute creative ledger updates.

        Internal entry used by BaseAgent.run. Most call sites should use
        ``update_for_chapter`` which provides a clearer signature.

        Args:
            state: Chapter workflow state containing project_id, chapter_number, etc.

        Returns:
            Updated state with ledger_update_result.
        """
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)

        if not project_id or not chapter_number:
            logger.warning("CreativeLedgerCurator: missing project_id or chapter_number")
            return {"ledger_update_result": {"status": "skipped", "reason": "missing identifiers"}}

        results = {}
        for ledger_type in self.ledger_types:
            try:
                result = self._update_ledger(project_id, chapter_number, ledger_type, state)
                results[ledger_type] = result
            except Exception as e:
                logger.warning("CreativeLedgerCurator: failed to update %s: %s", ledger_type, e)
                results[ledger_type] = {"status": "error", "error": str(e)}

        return {"ledger_update_result": results}

    def update_for_chapter(
        self,
        project_id: str,
        chapter_number: int,
        content: str,
        review_data: dict | None = None,
        workflow_run_id: str | None = None,
    ) -> dict:
        """Public entry to update ledgers for a single chapter.

        Wraps ``_execute`` with a clearer signature and explicit
        identifiers, avoiding the need for callers to construct a partial
        FactoryState dict.
        """
        return self._execute({
            "project_id": project_id,
            "chapter_number": chapter_number,
            "content": content or "",
            "review_data": review_data or {},
            "workflow_run_id": workflow_run_id,
        })

    def _update_ledger(
        self,
        project_id: str,
        chapter_number: int,
        ledger_type: str,
        state: dict,
    ) -> dict:
        """Update a single ledger type.

        Reads previous snapshot, generates patch via LLM, persists new snapshot.
        """
        # Get previous chapter's ledger snapshot
        previous = self.repo.get_creative_ledger(project_id, chapter_number - 1, ledger_type)
        previous_data = {}
        if previous:
            import json
            try:
                previous_data = json.loads(previous.get("ledger_data", "{}"))
            except (json.JSONDecodeError, TypeError):
                previous_data = {}

        # Get current chapter content and review
        chapter_content = state.get("content", "")
        review_data = state.get("review_data", {})

        # Generate ledger update via LLM
        try:
            new_data = self._generate_ledger_update(
                ledger_type=ledger_type,
                previous_data=previous_data,
                chapter_content=chapter_content,
                review_data=review_data,
                chapter_number=chapter_number,
            )
        except Exception as e:
            logger.warning(f"LLM ledger update failed for {ledger_type}: {e}")
            # Fallback: keep previous data
            new_data = previous_data

        # Compute patch from previous
        patch = self._compute_patch(previous_data, new_data)

        # Persist new snapshot
        self.repo.upsert_creative_ledger(
            project_id=project_id,
            chapter_number=chapter_number,
            ledger_type=ledger_type,
            ledger_data=new_data,
            patch_from_previous=patch,
            workflow_run_id=state.get("workflow_run_id"),
        )

        return {"status": "ok", "ledger_type": ledger_type, "entries_count": len(new_data.get("entries", []))}

    def _generate_ledger_update(
        self,
        ledger_type: str,
        previous_data: dict,
        chapter_content: str,
        review_data: dict,
        chapter_number: int,
    ) -> dict:
        """Generate ledger update via LLM.

        Uses different prompts for each ledger type to extract relevant information.
        """
        if not chapter_content or len(chapter_content) < 50:
            return previous_data

        if not self.llm:
            return previous_data

        prompt = self._build_ledger_prompt(
            ledger_type=ledger_type,
            previous_data=previous_data,
            chapter_content=chapter_content[:2000],  # Limit token usage
            chapter_number=chapter_number,
        )

        try:
            response = self.llm.invoke_json(prompt)
            if isinstance(response, dict):
                return response
            return previous_data
        except Exception as e:
            logger.warning(f"LLM ledger generation failed: {e}")
            return previous_data

    def _build_ledger_prompt(
        self,
        ledger_type: str,
        previous_data: dict,
        chapter_content: str,
        chapter_number: int,
    ) -> str:
        """Build prompt for specific ledger type."""
        prompts = {
            "reader_promise": """分析章节内容，提取读者承诺台账更新。

之前的台账：
{previous}

章节内容：
{chapter}

返回JSON格式：
{{
    "entries": [
        {{"promise": "承诺内容", "status": "active/fulfilled/broken", "chapter_introduced": N, "chapter_resolved": N}}
    ],
    "summary": "本章承诺状态摘要"
}}""",

            "power_growth": """分析章节内容，提取力量成长台账更新。

之前的台账：
{previous}

章节内容：
{chapter}

返回JSON格式：
{{
    "entries": [
        {{"ability": "能力名称", "level": "当前等级", "chapter_acquired": N, "chapter_upgraded": N}}
    ],
    "summary": "本章力量成长摘要"
}}""",

            "character_arc": """分析章节内容，提取角色弧线台账更新。

之前的台账：
{previous}

章节内容：
{chapter}

返回JSON格式：
{{
    "entries": [
        {{"character": "角色名", "arc_type": "成长/堕落/转变", "milestone": "里程碑描述", "chapter": N}}
    ],
    "summary": "本章角色弧线摘要"
}}""",

            "mystery_reveal": """分析章节内容，提取悬疑揭示台账更新。

之前的台账：
{previous}

章节内容：
{chapter}

返回JSON格式：
{{
    "entries": [
        {{"mystery": "悬疑内容", "status": "introduced/deepening/revealed", "chapter_introduced": N, "chapter_revealed": N}}
    ],
    "summary": "本章悬疑状态摘要"
}}""",

            "conflict": """分析章节内容，提取冲突台账更新。

之前的台账：
{previous}

章节内容：
{chapter}

返回JSON格式：
{{
    "entries": [
        {{"conflict": "冲突描述", "status": "active/escalating/resolved", "chapter_started": N, "chapter_resolved": N}}
    ],
    "summary": "本章冲突状态摘要"
}}""",

            "payoff": """分析章节内容，提取回报台账更新。

之前的台账：
{previous}

章节内容：
{chapter}

返回JSON格式：
{{
    "entries": [
        {{"payoff": "回报内容", "type": "triumph/revelation/revenge/catharsis", "chapter": N}}
    ],
    "summary": "本章回报摘要"
}}""",

            "style_fatigue": """分析章节内容，提取风格疲劳台账更新。

之前的台账：
{previous}

章节内容：
{chapter}

返回JSON格式：
{{
    "entries": [
        {{"pattern": "重复模式", "frequency": "high/medium/low", "chapter_detected": N}}
    ],
    "fatigue_score": 0.0-1.0,
    "summary": "本章风格疲劳摘要"
}}""",
        }

        template = prompts.get(ledger_type, prompts["reader_promise"])
        return template.format(
            previous=json.dumps(previous_data, ensure_ascii=False)[:500],
            chapter=chapter_content,
        )

    @staticmethod
    def _compute_patch(previous: dict, new: dict) -> dict:
        """Compute diff between previous and new ledger data.

        Returns a simple patch with added/modified entries.
        """
        prev_entries = {e.get("id", i): e for i, e in enumerate(previous.get("entries", []))}
        new_entries = {e.get("id", i): e for i, e in enumerate(new.get("entries", []))}

        added = {k: v for k, v in new_entries.items() if k not in prev_entries}
        modified = {k: v for k, v in new_entries.items() if k in prev_entries and prev_entries[k] != v}

        return {
            "added": list(added.values()),
            "modified": list(modified.values()),
            "chapter": new.get("chapter_number"),
        }
