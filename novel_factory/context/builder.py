"""ContextBuilder — assembles context fragments for each agent.

v1.2 implements:
- Per-agent context with different fragments and priorities.
- Token budget with mandatory (P0-P2) and trimmable (P3-P9) segments.
- Integration with learned_patterns and best_practices.
- v4.0: Style Bible injection for all agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..db.repository import Repository
from ..validators.death_penalty import format_death_penalty_for_prompt

logger = logging.getLogger(__name__)


# ── Token estimation ───────────────────────────────────────────

# Rough estimate: 1 Chinese character ≈ 1.5 tokens
# Conservative default budget
DEFAULT_TOKEN_BUDGET = 4000


def _estimate_tokens(text: str) -> int:
    """Estimate token count for Chinese text."""
    return int(len(text) * 1.5)


# ── Context fragment ───────────────────────────────────────────

class ContextFragment:
    """A named context fragment with priority for budget trimming."""

    def __init__(
        self,
        name: str,
        content: str,
        priority: int,
        mandatory: bool = False,
    ) -> None:
        self.name = name
        self.content = content
        self.priority = priority  # lower = higher priority
        self.mandatory = mandatory
        self.tokens = _estimate_tokens(content)

    def __repr__(self) -> str:
        return f"Fragment({self.name}, P{self.priority}, {self.tokens}tok)"


# ── ContextBuilder ─────────────────────────────────────────────


class ContextBuilder:
    """v1.2 context builder with token budget and priority-based trimming."""

    def __init__(self, repo: Repository, token_budget: int = DEFAULT_TOKEN_BUDGET) -> None:
        self.repo = repo
        self.token_budget = token_budget

    # ── Fragment builders by priority ───────────────────────

    def _frag_death_penalty(self) -> ContextFragment:
        """P0: Death penalty / quality red lines — always mandatory."""
        return ContextFragment(
            name="death_penalty",
            content=format_death_penalty_for_prompt(),
            priority=0,
            mandatory=True,
        )

    def _frag_instruction(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P1: Current chapter instruction."""
        instruction = self.repo.get_instruction(project_id, chapter_number)
        if not instruction:
            return ContextFragment("instruction", "", 1, mandatory=True)

        content = (
            f"【写作指令】\n"
            f"目标: {instruction.get('objective', '')}\n"
            f"关键事件: {instruction.get('key_events', '')}\n"
            f"情绪基调: {instruction.get('emotion_tone', '')}\n"
            f"章末钩子: {instruction.get('ending_hook', '')}\n"
            f"字数目标: {instruction.get('word_target', 2500)}"
        )
        return ContextFragment("instruction", content, 1, mandatory=True)

    def _frag_prev_state_card(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P2: Previous chapter state card."""
        prev_state = self.repo.get_chapter_state(project_id, chapter_number - 1)
        if not prev_state:
            return ContextFragment("prev_state_card", "", 2, mandatory=True)

        state_data = prev_state.get("state_data", prev_state)
        content = f"【上一章状态卡】\n{json.dumps(state_data, ensure_ascii=False, indent=2)}"
        return ContextFragment("prev_state_card", content, 2, mandatory=True)

    def _frag_scene_beats(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P3: Scene beats for this chapter."""
        beats = self.repo.get_scene_beats(project_id, chapter_number)
        if not beats:
            return ContextFragment("scene_beats", "", 3)

        beats_str = "\n".join(
            f"  {b['sequence']}. 目标: {b.get('scene_goal', '')} | "
            f"冲突: {b.get('conflict', '')} | 钩子: {b.get('hook', '')}"
            for b in beats
        )
        return ContextFragment("scene_beats", f"【场景 Beat】\n{beats_str}", 3)

    def _frag_plot_requirements(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P4: Plot requirements for this chapter."""
        instruction = self.repo.get_instruction(project_id, chapter_number)
        if not instruction:
            return ContextFragment("plot_requirements", "", 4)

        parts = []
        if instruction.get("plots_to_plant"):
            parts.append(f"埋设伏笔: {instruction['plots_to_plant']}")
        if instruction.get("plots_to_resolve"):
            parts.append(f"兑现伏笔: {instruction['plots_to_resolve']}")

        if not parts:
            return ContextFragment("plot_requirements", "", 4)

        return ContextFragment("plot_requirements", "【伏笔要求】\n" + "\n".join(parts), 4)

    def _frag_characters(self, project_id: str) -> ContextFragment:
        """P5: Relevant characters and factions."""
        characters = self.repo.get_characters(project_id)
        if not characters:
            return ContextFragment("characters", "", 5)

        char_str = "\n".join(
            f"- {c['name']}({c['role']}): {c.get('description', '')}"
            for c in characters[:10]
        )
        return ContextFragment("characters", f"【角色设定】\n{char_str}", 5)

    def _frag_world_rules(self, project_id: str) -> ContextFragment:
        """P6: World-building key rules."""
        settings = self.repo.get_world_settings(project_id)
        if not settings:
            return ContextFragment("world_rules", "", 6)

        rules_str = "\n".join(
            f"- [{s.get('category', '')}] {s.get('title', '')}: {s.get('content', '')[:200]}"
            for s in settings[:5]
        )
        return ContextFragment("world_rules", f"【世界观关键规则】\n{rules_str}", 6)

    def _frag_outlines(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P6: Outline context for current chapter phase (v5.2)."""
        outlines = self.repo.list_outlines(project_id)
        if not outlines:
            return ContextFragment("outlines", "", 6)

        # Find outlines that cover this chapter
        relevant = []
        for o in outlines:
            chapters_range = o.get("chapters_range", "")
            if chapters_range:
                # Parse range like "1-10" or "5-15"
                try:
                    parts = chapters_range.split("-")
                    if len(parts) == 2:
                        start, end = int(parts[0]), int(parts[1])
                        if start <= chapter_number <= end:
                            relevant.append(o)
                except (ValueError, AttributeError):
                    pass

        if not relevant:
            # Fall back to all outlines if none match the range
            relevant = outlines[:3]

        outline_str = "\n".join(
            f"- [{o.get('level', '')}] {o.get('title', '')}: {o.get('content', '')[:300]}"
            for o in relevant[:3]
        )
        return ContextFragment("outlines", f"【大纲阶段】\n{outline_str}", 6)

    def _frag_recent_summaries(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P7: Recent chapter summaries."""
        summaries = self.repo.get_recent_chapter_summaries(project_id, chapter_number, limit=3)
        if not summaries:
            return ContextFragment("recent_summaries", "", 7)

        summary_str = "\n".join(
            f"- 第{s['chapter_number']}章 {s.get('title', '')}: {s.get('summary', '无摘要')[:100]}"
            for s in summaries
        )
        return ContextFragment("recent_summaries", f"【近章摘要】\n{summary_str}", 7)

    def _frag_learned_patterns(self, project_id: str) -> ContextFragment:
        """P8: Learned patterns (high-frequency issues to avoid)."""
        patterns = self.repo.get_learned_patterns(
            project_id, enabled_only=True, min_frequency=2, limit=10,
        )
        if not patterns:
            return ContextFragment("learned_patterns", "", 8)

        pat_str = "\n".join(
            f"- [{p['category']}] {p['pattern']} (出现{p['frequency']}次)"
            for p in patterns
        )
        return ContextFragment("learned_patterns", f"【历史问题模式（避免重复）】\n{pat_str}", 8)

    def _frag_best_practices(self, project_id: str) -> ContextFragment:
        """P9: Best practices (high-score techniques to follow)."""
        practices = self.repo.get_best_practices(
            project_id, min_score=85.0, limit=5,
        )
        if not practices:
            return ContextFragment("best_practices", "", 9)

        bp_str = "\n".join(
            f"- [{p['category']}] {p['practice']} (均分{p.get('avg_score', 0):.0f})"
            for p in practices
        )
        return ContextFragment("best_practices", f"【最佳实践（参考）】\n{bp_str}", 9)

    def _frag_story_facts(self, project_id: str) -> ContextFragment:
        """P5: Accumulated story facts from memory curator (v5.3.2)."""
        facts = self.repo.list_story_facts(project_id, status="active")
        if not facts:
            return ContextFragment("story_facts", "", 5)

        fact_lines = []
        for f in facts[:15]:  # Limit to avoid context overflow
            subject = f.get("subject", "")
            attribute = f.get("attribute", "")
            value = f.get("value_json", "{}")
            # Truncate long values
            if len(value) > 100:
                value = value[:100] + "..."
            fact_lines.append(f"- {f['fact_key']}: {subject}.{attribute} = {value}")

        return ContextFragment(
            "story_facts",
            f"【故事事实追踪】\n" + "\n".join(fact_lines),
            5,
        )

    # ── v2 Sidecar Agent fragments ───────────────────────────────

    def _frag_market_report(self, project_id: str) -> ContextFragment:
        """P6: Recent market report from Scout agent."""
        reports = self.repo.get_market_reports(project_id, limit=1)
        if not reports:
            return ContextFragment("market_report", "", 6)

        report = reports[0]
        content_json = report.get("content_json", {})
        
        parts = []
        if content_json.get("trends"):
            parts.append("市场趋势: " + ", ".join(content_json["trends"][:3]))
        if content_json.get("opportunities"):
            parts.append("市场机会: " + ", ".join(content_json["opportunities"][:2]))
        if content_json.get("reader_preferences"):
            parts.append("读者偏好: " + ", ".join(content_json["reader_preferences"][:3]))
        
        if not parts:
            return ContextFragment("market_report", "", 6)
        
        return ContextFragment(
            "market_report",
            f"【市场洞察（Scout报告）】\n" + "\n".join(parts),
            6,
        )

    def _frag_continuity_warning(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P3: Continuity warnings from ContinuityChecker agent."""
        reports = self.repo.get_continuity_reports(project_id, limit=3)
        if not reports:
            return ContextFragment("continuity_warning", "", 3)

        # Filter reports that cover current chapter
        relevant_reports = [
            r for r in reports
            if r.get("from_chapter", 0) <= chapter_number <= r.get("to_chapter", 999)
        ]
        
        if not relevant_reports:
            return ContextFragment("continuity_warning", "", 3)

        # Extract issues
        issues = []
        for report in relevant_reports:
            content = report.get("content_json", {})
            report_issues = content.get("issues", [])
            for issue in report_issues[:5]:
                if issue.get("severity") in ("error", "warning"):
                    issues.append(f"- [{issue.get('severity')}] {issue.get('description', '')[:100]}")
        
        if not issues:
            return ContextFragment("continuity_warning", "", 3)
        
        return ContextFragment(
            "continuity_warning",
            f"【连续性警告（ContinuityChecker）】\n" + "\n".join(issues[:5]),
            3,
        )

    # ── Review notes fragment (v3.2) ─────────────────────────────

    def _frag_review_notes(self, project_id: str, chapter_number: int) -> ContextFragment:
        """P2: Review notes from human review sessions for this chapter."""
        notes = self.repo.get_chapter_review_notes(project_id, chapter_number)
        if not notes:
            return ContextFragment("review_notes", "", 2)

        # Get the most recent note
        latest_note = notes[0]
        notes_str = f"【人工审核意见】\n{latest_note['notes']}"
        return ContextFragment("review_notes", notes_str, 2)

    # ── Fact lock fragment (Q8 Polisher) ───────────────────

    def _frag_fact_lock(self, project_id: str, chapter_number: int) -> ContextFragment:
        """Fact lock list for Polisher — events, plot refs, state values."""
        parts = []

        # Key events from instruction
        instruction = self.repo.get_instruction(project_id, chapter_number)
        if instruction and instruction.get("key_events"):
            parts.append(f"关键事件: {instruction['key_events']}")

        # Plot refs from instruction
        if instruction:
            if instruction.get("plots_to_plant"):
                parts.append(f"伏笔埋设: {instruction['plots_to_plant']}")
            if instruction.get("plots_to_resolve"):
                parts.append(f"伏笔兑现: {instruction['plots_to_resolve']}")

        # State card values
        prev_state = self.repo.get_chapter_state(project_id, chapter_number - 1)
        if prev_state:
            state_data = prev_state.get("state_data", prev_state)
            if isinstance(state_data, dict):
                # Extract key numeric values
                for key in ("level", "等级", "lv", "Lv"):
                    if key in state_data:
                        parts.append(f"等级/数值: {key}={state_data[key]}")
                        break
                assets = state_data.get("assets", {})
                if isinstance(assets, dict):
                    for k, v in list(assets.items())[:5]:
                        parts.append(f"  {k}={v}")

        if not parts:
            return ContextFragment("fact_lock", "", 0, mandatory=True)

        return ContextFragment(
            "fact_lock",
            "【事实锁定清单 — 润色时不可删除/改变】\n" + "\n".join(parts),
            0,  # P0 for Polisher
            mandatory=True,
        )

    # ── v4.0 Style Bible fragment ────────────────────────────────

    def _frag_style_bible(self, project_id: str, agent_id: str) -> ContextFragment:
        """P3: Style Bible rules for the given agent (v4.0)."""
        try:
            from ..style_bible.loader import get_style_context_for_agent
            style_text = get_style_context_for_agent(project_id, agent_id, self.repo)
            if not style_text:
                return ContextFragment("style_bible", "", 3)
            return ContextFragment("style_bible", style_text, 3)
        except Exception:
            logger.debug("Style Bible fragment unavailable for project=%s agent=%s", project_id, agent_id)
            return ContextFragment("style_bible", "", 3)

    # ── Agent-specific build methods ────────────────────────

    def build_for_author(self, project_id: str, chapter_number: int) -> str:
        """Build context for Author: instruction, scene_beats, state_card,
        characters, plot requirements, death_penalty, review_notes (v3.2),
        world_rules, outlines (v5.2)."""
        fragments = [
            self._frag_death_penalty(),        # P0
            self._frag_instruction(project_id, chapter_number),     # P1
            self._frag_review_notes(project_id, chapter_number),    # P2 (v3.2)
            self._frag_prev_state_card(project_id, chapter_number), # P2
            self._frag_style_bible(project_id, "author"),            # P3 (v4.0)
            self._frag_scene_beats(project_id, chapter_number),     # P3
            self._frag_plot_requirements(project_id, chapter_number), # P4
            self._frag_characters(project_id),                      # P5
            self._frag_story_facts(project_id),                    # P5 (v5.3.2)
            self._frag_world_rules(project_id),                     # P6 (v5.2)
            self._frag_outlines(project_id, chapter_number),        # P6 (v5.2)
            self._frag_learned_patterns(project_id),                # P8
            self._frag_best_practices(project_id),                  # P9
        ]
        return self._assemble(fragments)

    def build_for_polisher(self, project_id: str, chapter_number: int) -> str:
        """Build context for Polisher: original draft, instruction,
        fact lock list, death_penalty, review_notes (v3.2)."""
        # Original draft
        chapter = self.repo.get_chapter(project_id, chapter_number)
        draft_content = ""
        if chapter and chapter.get("content"):
            draft_content = f"【当前草稿】\n{chapter['content'][:8000]}"

        fragments = [
            self._frag_fact_lock(project_id, chapter_number),       # P0 for Polisher
            self._frag_death_penalty(),                              # P0
            ContextFragment("original_draft", draft_content, 1, mandatory=True),  # P1
            self._frag_instruction(project_id, chapter_number),     # P1
            self._frag_review_notes(project_id, chapter_number),    # P2 (v3.2)
            self._frag_style_bible(project_id, "polisher"),          # P3 (v4.0)
            self._frag_learned_patterns(project_id),                # P8
            self._frag_best_practices(project_id),                  # P9
        ]
        return self._assemble(fragments)

    def build_for_editor(self, project_id: str, chapter_number: int) -> str:
        """Build context for Editor: content, instruction, state_card,
        plot requirements, anti_patterns, learned_patterns, continuity_warning."""
        # Chapter content
        chapter = self.repo.get_chapter(project_id, chapter_number)
        content_text = ""
        if chapter and chapter.get("content"):
            content_text = f"【本章正文】\n{chapter['content'][:6000]}"

        # Anti-patterns from DB
        anti_patterns = self.repo.get_anti_patterns(enabled_only=True)
        anti_pat_text = ""
        if anti_patterns:
            anti_pat_text = "【反模式规则】\n" + "\n".join(
                f"- [{ap.get('severity', '')}] {ap.get('pattern', '')}: {ap.get('description', '')}"
                for ap in anti_patterns[:10]
            )

        fragments = [
            self._frag_death_penalty(),                              # P0
            ContextFragment("chapter_content", content_text, 1, mandatory=True),  # P1
            self._frag_instruction(project_id, chapter_number),     # P1
            self._frag_prev_state_card(project_id, chapter_number), # P2
            self._frag_style_bible(project_id, "editor"),            # P3 (v4.0)
            self._frag_continuity_warning(project_id, chapter_number),  # P3 (v2)
            self._frag_plot_requirements(project_id, chapter_number), # P4
            ContextFragment("anti_patterns", anti_pat_text, 7),     # P7-like
            self._frag_learned_patterns(project_id),                # P8
        ]
        return self._assemble(fragments)

    def build_for_planner(self, project_id: str, chapter_number: int) -> str:
        """Build context for Planner: state_card, characters, plots, messages,
        market_report, continuity_warning, review_notes (v3.2),
        world_rules, outlines (v5.2)."""
        fragments = [
            self._frag_review_notes(project_id, chapter_number),    # P2 (v3.2)
            self._frag_prev_state_card(project_id, chapter_number),  # P2
            self._frag_style_bible(project_id, "planner"),           # P3 (v4.0)
            self._frag_continuity_warning(project_id, chapter_number),  # P3 (v2)
            self._frag_plot_requirements(project_id, chapter_number), # P4
            self._frag_characters(project_id),                       # P5
            self._frag_story_facts(project_id),                     # P5 (v5.3.2)
            self._frag_world_rules(project_id),                      # P6 (v5.2)
            self._frag_outlines(project_id, chapter_number),         # P6 (v5.2)
            self._frag_market_report(project_id),                    # P6 (v2)
        ]

        # Pending messages
        messages = self.repo.get_pending_messages(project_id, "planner")
        if messages:
            msg_str = "\n".join(
                f"- [{m['from_agent']}] {m['type']}: {m['content'][:200]}"
                for m in messages[:5]
            )
            fragments.append(ContextFragment("pending_messages", f"【待处理异议】\n{msg_str}", 5))

        return self._assemble(fragments)

    # ── Assembly with token budget ──────────────────────────

    def _assemble(self, fragments: list[ContextFragment]) -> str:
        """Assemble fragments respecting token budget.

        Mandatory fragments are always included regardless of budget.
        Optional fragments are included by priority (lower number = higher priority)
        until the budget is exhausted.
        """
        # Separate mandatory and optional
        mandatory = [f for f in fragments if f.mandatory and f.content]
        optional = [f for f in fragments if not f.mandatory and f.content]

        # Sort optional by priority
        optional.sort(key=lambda f: f.priority)

        # Calculate mandatory token usage
        mandatory_tokens = sum(f.tokens for f in mandatory)
        remaining = self.token_budget - mandatory_tokens

        # Add optional fragments by priority until budget exhausted
        included_optional: list[ContextFragment] = []
        for frag in optional:
            if remaining <= 0:
                break
            if frag.tokens <= remaining:
                included_optional.append(frag)
                remaining -= frag.tokens
            else:
                # Try to include a truncated version
                ratio = remaining / max(frag.tokens, 1)
                if ratio > 0.3:  # Only include if we can show > 30%
                    truncated = frag.content[:int(len(frag.content) * ratio)]
                    included_optional.append(ContextFragment(
                        frag.name, truncated + "\n...(已裁剪)", frag.priority,
                    ))
                remaining = 0
                break

        # Combine all fragments
        all_frags = mandatory + included_optional
        return "\n\n---\n\n".join(f.content for f in all_frags if f.content)
