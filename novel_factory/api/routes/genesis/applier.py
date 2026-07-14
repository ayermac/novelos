"""Genesis applier — apply approved draft to project context tables.

v6.11.0 refactor: Extracted from _endpoints.py for modular organization.
Contains the core logic for persisting genesis drafts to the database.
"""

from __future__ import annotations

import logging

from .utils import _as_text, _as_list
from .coercer import (
    _coerce_world_setting,
    _coerce_character,
    _coerce_named_item,
    _coerce_outline,
    _coerce_plot_hole,
    _coerce_instruction,
    _format_instruction_contract_details,
    _normalize_character_role,
    _normalize_plot_status,
)

logger = logging.getLogger(__name__)


def _apply_genesis_to_project(repo, project_id: str, draft: dict, chapter_cleanup_mode: str | None = None) -> dict:
    """Apply an approved genesis draft to formal tables.

    v6.8.5: Added chapter_cleanup_mode for re-genesis protection.

    Args:
        repo: Repository instance.
        project_id: Project identifier.
        draft: Genesis draft data.
        chapter_cleanup_mode: How to handle existing chapters:
            - "keep_published": Keep published/reviewed/awaiting_publish, reset others
            - "reset_all": Reset ALL chapters including terminal ones
            - "delete_all": Delete ALL chapters
            - None: No chapter cleanup (default, preserves all chapters)

    Returns:
        A summary of what was applied.
    """
    if not isinstance(draft, dict):
        raise ValueError("创世草案必须是 JSON 对象")

    applied = {
        "project_updated": False,
        "context_replaced": False,
        "world_settings_deleted": 0,
        "characters_deleted": 0,
        "factions_deleted": 0,
        "outlines_deleted": 0,
        "plot_holes_deleted": 0,
        "instructions_deleted": 0,
        "story_facts_deleted": 0,
        "story_fact_events_deleted": 0,
        "memory_items_deleted": 0,
        "memory_batches_deleted": 0,
        "agent_memories_deleted": 0,
        "chapter_states_deleted": 0,
        "state_history_deleted": 0,
        "world_settings_created": 0,
        "characters_created": 0,
        "factions_created": 0,
        "outlines_created": 0,
        "plot_holes_created": 0,
        "instructions_created": 0,
    }

    has_prior_approved_genesis = any(
        run.get("status") == "approved" for run in repo.list_genesis_runs(project_id)
    )

    # v6.8.5: Chapter cleanup before applying new genesis
    chapter_cleanup_summary = {"mode": chapter_cleanup_mode, "chapters_affected": 0}
    if chapter_cleanup_mode:
        if chapter_cleanup_mode == "keep_published":
            # Keep published/reviewed/awaiting_publish, reset others to planned
            chapter_cleanup_summary["chapters_affected"] = repo.reset_non_terminal_chapters(project_id)
            # Reset current_chapter to 1
            repo.update_project(project_id, current_chapter=1)
            chapter_cleanup_summary["current_chapter_reset"] = True
        elif chapter_cleanup_mode == "reset_all":
            # Reset ALL chapters including terminal ones
            chapter_cleanup_summary["chapters_affected"] = repo.reset_all_chapters(project_id)
            repo.update_project(project_id, current_chapter=1)
            chapter_cleanup_summary["current_chapter_reset"] = True
        elif chapter_cleanup_mode == "delete_all":
            # Delete ALL chapters
            chapter_cleanup_summary["chapters_affected"] = repo.delete_all_chapters(project_id)
            repo.update_project(project_id, current_chapter=1)
            chapter_cleanup_summary["current_chapter_reset"] = True
        logger.info("Re-genesis chapter cleanup: %s", chapter_cleanup_summary)
    applied["chapter_cleanup"] = chapter_cleanup_summary

    applied["memory_items_deleted"] = repo.delete_memory_items_by_project(project_id)
    applied["memory_batches_deleted"] = repo.delete_memory_batches_by_project(project_id)
    applied["story_fact_events_deleted"] = repo.delete_fact_events_by_project(project_id)
    applied["story_facts_deleted"] = repo.delete_story_facts_by_project(project_id)
    applied["world_settings_deleted"] = repo.delete_world_settings_by_project(project_id)
    applied["characters_deleted"] = repo.delete_characters_by_project(project_id)
    applied["factions_deleted"] = repo.delete_factions_by_project(project_id)
    applied["outlines_deleted"] = repo.delete_outlines_by_project(project_id)
    applied["plot_holes_deleted"] = repo.delete_plot_holes_by_project(project_id)
    applied["instructions_deleted"] = repo.delete_instructions_by_project(project_id)
    if hasattr(repo, "delete_agent_memories_by_project"):
        applied["agent_memories_deleted"] = repo.delete_agent_memories_by_project(project_id)
    if hasattr(repo, "delete_chapter_states_by_project"):
        applied["chapter_states_deleted"] = repo.delete_chapter_states_by_project(project_id)
    if hasattr(repo, "delete_state_history_by_project"):
        applied["state_history_deleted"] = repo.delete_state_history_by_project(project_id)
    applied["context_replaced"] = has_prior_approved_genesis or any(
        applied[key] > 0
        for key in (
            "memory_items_deleted",
            "memory_batches_deleted",
            "story_fact_events_deleted",
            "story_facts_deleted",
            "world_settings_deleted",
            "characters_deleted",
            "factions_deleted",
            "outlines_deleted",
            "plot_holes_deleted",
            "instructions_deleted",
            "agent_memories_deleted",
            "chapter_states_deleted",
            "state_history_deleted",
        )
    )

    # Update project description
    project_updates = draft.get("project_updates", {})
    if not isinstance(project_updates, dict):
        project_updates = {"description": _as_text(project_updates)}
    if project_updates.get("description"):
        repo.update_project(project_id, description=project_updates["description"])
        applied["project_updated"] = True

    # World settings - upsert by title
    existing_ws = repo.list_world_settings(project_id)
    ws_by_title = {w["title"]: w for w in existing_ws}
    for idx, raw_ws in enumerate(_as_list(draft.get("world_settings", [])), start=1):
        ws = _coerce_world_setting(raw_ws, idx)
        if not ws:
            continue
        title = ws.get("title", "")
        if title in ws_by_title:
            repo.update_world_setting(project_id, ws_by_title[title]["id"], ws)
        else:
            repo.create_world_setting(
                project_id,
                category=ws.get("category", ""),
                title=title,
                content=ws.get("content", ""),
            )
            applied["world_settings_created"] += 1

    # Characters - upsert by name
    existing_chars = repo.list_characters(project_id)
    char_by_name = {c["name"]: c for c in existing_chars}
    for idx, raw_ch in enumerate(_as_list(draft.get("characters", [])), start=1):
        ch = _coerce_character(raw_ch, idx)
        if not ch:
            continue
        name = ch.get("name", "")
        char_data = {
            **ch,
            "role": _normalize_character_role(ch.get("role", "supporting")),
            "description": _as_text(ch.get("description", "")),
            "traits": _as_text(ch.get("traits", "")),
        }
        if name in char_by_name:
            repo.update_character(project_id, char_by_name[name]["id"], char_data)
        else:
            repo.create_character(
                project_id,
                name=name,
                role=char_data["role"],
                description=char_data["description"],
                traits=char_data["traits"],
            )
            applied["characters_created"] += 1

    # Factions - upsert by name
    existing_factions = repo.list_factions(project_id)
    fac_by_name = {f["name"]: f for f in existing_factions}
    for idx, raw_f in enumerate(_as_list(draft.get("factions", [])), start=1):
        f = _coerce_named_item(raw_f, idx, "势力")
        if not f:
            continue
        name = f.get("name", "")
        if name in fac_by_name:
            repo.update_faction(project_id, fac_by_name[name]["id"], f)
        else:
            repo.create_faction(
                project_id,
                name=name,
                type=f.get("type", ""),
                description=f.get("description", ""),
                relationship_with_protagonist=f.get("relationship_with_protagonist", ""),
            )
            applied["factions_created"] += 1

    # Outlines - upsert by (level, sequence)
    existing_outlines = repo.list_outlines(project_id)
    outline_by_key = {(o.get("level", ""), o.get("sequence", 0)): o for o in existing_outlines}
    for idx, raw_o in enumerate(_as_list(draft.get("outlines", [])), start=1):
        o = _coerce_outline(raw_o, idx)
        if not o:
            continue
        key = (o.get("level", "arc"), o.get("sequence", 0))
        if key in outline_by_key:
            repo.update_outline(project_id, outline_by_key[key]["id"], o)
        else:
            repo.create_outline(
                project_id,
                level=o.get("level", "arc"),
                sequence=o.get("sequence", 1),
                title=o.get("title", ""),
                content=o.get("content", ""),
                chapters_range=o.get("chapters_range", ""),
            )
            applied["outlines_created"] += 1

    # Plot holes - upsert by code
    existing_phs = repo.list_plot_holes(project_id)
    ph_by_code = {p["code"]: p for p in existing_phs if p.get("code")}
    for idx, raw_ph in enumerate(_as_list(draft.get("plot_holes", [])), start=1):
        ph = _coerce_plot_hole(raw_ph, idx)
        if not ph:
            continue
        code = ph.get("code", "")
        plot_data = {
            **ph,
            "type": _as_text(ph.get("type", "")),
            "title": _as_text(ph.get("title", "")),
            "description": _as_text(ph.get("description", "")),
            "status": _normalize_plot_status(ph.get("status", "planted")),
        }
        if code in ph_by_code:
            repo.update_plot_hole(project_id, ph_by_code[code]["id"], plot_data)
        else:
            repo.create_plot_hole(
                project_id,
                code=code,
                type=plot_data["type"],
                title=plot_data["title"],
                description=plot_data["description"],
                planted_chapter=plot_data.get("planted_chapter"),
                planned_resolve_chapter=plot_data.get("planned_resolve_chapter"),
                status=plot_data["status"],
            )
            applied["plot_holes_created"] += 1

    # Instructions - upsert by chapter_number
    for idx, raw_inst in enumerate(_as_list(draft.get("instructions", [])), start=1):
        inst = _coerce_instruction(raw_inst, idx)
        if not inst:
            continue
        ch_num = inst.get("chapter_number")
        if ch_num is None:
            continue
        # v6.6.4: Merge ending_hook/continuity_seed into key_events/emotion_tone if DB lacks columns
        objective = _as_text(inst.get("objective", ""))
        key_events = _as_text(inst.get("key_events", ""))
        emotion_tone = _as_text(inst.get("emotion_tone", ""))
        ending_hook = _as_text(inst.get("ending_hook", ""))
        continuity_seed = _as_text(inst.get("continuity_seed", ""))
        contract_details = _format_instruction_contract_details(inst)
        if contract_details and contract_details not in key_events:
            key_events = f"{key_events}\n{contract_details}".strip()
        if ending_hook and ending_hook not in key_events:
            key_events = f"{key_events}\n结尾钩子: {ending_hook}".strip()
        if continuity_seed and continuity_seed not in emotion_tone:
            emotion_tone = f"{emotion_tone}\n继承点: {continuity_seed}".strip()
        instruction_data = {
            **inst,
            "objective": objective,
            "key_events": key_events,
            "emotion_tone": emotion_tone,
        }
        existing_inst = repo.get_instruction_by_chapter(project_id, ch_num)
        if existing_inst:
            repo.update_instruction(project_id, existing_inst["id"], instruction_data)
        else:
            repo.create_instruction(
                project_id,
                chapter_number=ch_num,
                objective=instruction_data["objective"],
                key_events=instruction_data["key_events"],
                emotion_tone=instruction_data["emotion_tone"],
                word_target=instruction_data.get("word_target"),
            )
            applied["instructions_created"] += 1

    return applied
