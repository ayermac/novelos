"""Genesis API endpoints for project bible generation.

This package provides the Genesis API routes for project bible generation.
The main entry point is the FastAPI router.

Usage:
    from novel_factory.api.routes.genesis import router
"""

from __future__ import annotations

# Re-export quality evaluation function for backward compatibility with tests
from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft

# Import router from the original endpoints file (preserved for compatibility)
from ._endpoints import router

# Import models for backward compatibility
from .models import (
    GenesisApproveRequest,
    GenesisApproveWithForceRequest,
    GenesisForceApplyBody,
    GenesisGenerateRequest,
    GenesisRejectRequest,
)

# Import progress utilities
from .progress import (
    GENESIS_INSTRUCTION_CHUNK_SIZE,
    GENESIS_REPAIRABLE_INSTRUCTION_CODES,
    GENESIS_REQUIRED_SECTIONS,
    GENESIS_RUNNING_TIMEOUT_MINUTES,
    GENESIS_SEGMENT_LABELS,
    GENESIS_SEGMENT_MAX_TOKENS,
    ProgressCallback,
    _genesis_progress_queues,
    _make_progress_event,
    _push_progress,
    create_progress_queue,
    get_progress_queue,
    remove_progress_queue,
)

# Import utilities
from .utils import (
    _as_int,
    _as_list,
    _as_text,
    _merge_key_text,
    _short_title,
)

# Import normalizer
from .normalizer import (
    _dedupe_genesis_draft,
    _genesis_item_key,
    _merge_genesis_item,
    _merge_unique_genesis_list,
    _normalize_genesis_draft,
    _parse_genesis_draft_json,
    _world_setting_semantic_key,
)

# Import scaffold functions
from .scaffold import (
    _generate_genesis_scaffold,
    _generate_stub_draft,
    _fill_missing_genesis_sections,
    _missing_required_genesis_sections,
    _validate_complete_genesis_draft,
    _incomplete_genesis_message,
    _merge_genesis_drafts,
    _project_description_from_body,
    _target_word_count,
    _infer_protagonist_name,
    _is_anomaly_genesis,
    _genre_terms,
    _scaffold_seed_items,
    _clean_scaffold_entity_name,
    _pick_seed_character,
    _pick_seed_faction,
    _detect_scaffold_story_mode,
    _default_scaffold_entities,
    _build_scaffold_instruction_templates,
)

# Import coercer functions
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

# Import LLM functions
from .llm import (
    _generate_real_draft,
    _generate_real_draft_with_scaffold_fallback,
    _complete_real_genesis_draft,
    _build_genesis_segment_prompt,
    _build_genesis_completion_prompt,
    _build_genesis_llm,
    _invoke_genesis_segment,
    _instruction_repair_issue_count,
    _has_instruction_repair_target,
    _format_genesis_quality_issues_for_prompt,
    _instruction_repair_rank,
    _build_local_instruction_repair_candidate,
    _repair_genesis_instruction_quality,
    _mark_genesis_generation_fallback,
    _mark_genesis_local_recovery,
    _build_genesis_recovery_draft,
    _recover_genesis_from_partial_draft,
    _build_genesis_instruction_repair_prompt,
    _build_genesis_common_context,
)

# Import applier function
from .applier import _apply_genesis_to_project

# Re-export all public symbols from the original file
# Note: _endpoints.py still contains route handlers
from ._endpoints import (
    _fail_orphaned_running_genesis,
    _genesis_timeout_minutes,
    _parse_genesis_timestamp,
    _quality_report_for_genesis,
    _quality_report_payload,
    _recover_stale_running_genesis,
    _validate_genesis_generate_request,
    _with_project_defaults,
    _approve_genesis_run_with_quality_audit,
)

# Re-export all public symbols
__all__ = [
    # Router (main entry point)
    "router",
    # Quality evaluation (re-exported for backward compatibility)
    "evaluate_genesis_draft",
    # Models
    "GenesisGenerateRequest",
    "GenesisApproveRequest",
    "GenesisRejectRequest",
    "GenesisApproveWithForceRequest",
    "GenesisForceApplyBody",
    # Progress
    "GENESIS_RUNNING_TIMEOUT_MINUTES",
    "GENESIS_SEGMENT_LABELS",
    "GENESIS_REQUIRED_SECTIONS",
    "GENESIS_SEGMENT_MAX_TOKENS",
    "GENESIS_INSTRUCTION_CHUNK_SIZE",
    "GENESIS_REPAIRABLE_INSTRUCTION_CODES",
    "_genesis_progress_queues",
    "_push_progress",
    "_make_progress_event",
    "ProgressCallback",
    "get_progress_queue",
    "create_progress_queue",
    "remove_progress_queue",
    # Utils
    "_as_text",
    "_as_list",
    "_as_int",
    "_merge_key_text",
    "_short_title",
    # Normalizer
    "_normalize_genesis_draft",
    "_world_setting_semantic_key",
    "_genesis_item_key",
    "_merge_genesis_item",
    "_merge_unique_genesis_list",
    "_dedupe_genesis_draft",
    "_parse_genesis_draft_json",
    # Functions from _endpoints.py
    "_apply_genesis_to_project",
    "_complete_real_genesis_draft",
    "_fill_missing_genesis_sections",
    "_generate_genesis_scaffold",
    "_generate_real_draft",
    "_generate_stub_draft",
    "_invoke_genesis_segment",
    "_parse_genesis_timestamp",
    "_quality_report_for_genesis",
    "_recover_stale_running_genesis",
    "_validate_genesis_generate_request",
    "_with_project_defaults",
    "_fail_orphaned_running_genesis",
    "_genesis_timeout_minutes",
    "_quality_report_payload",
    "_approve_genesis_run_with_quality_audit",
    "_infer_protagonist_name",
    "_is_anomaly_genesis",
    "_missing_required_genesis_sections",
    # Coercion
    "_coerce_world_setting",
    "_coerce_character",
    "_coerce_named_item",
    "_coerce_outline",
    "_coerce_plot_hole",
    "_coerce_instruction",
    # Scaffold
    "_build_scaffold_instruction_templates",
    "_clean_scaffold_entity_name",
    "_default_scaffold_entities",
    "_detect_scaffold_story_mode",
    "_genre_terms",
    "_pick_seed_character",
    "_pick_seed_faction",
    "_scaffold_seed_items",
    "_target_word_count",
    # Draft handling
    "_incomplete_genesis_message",
    "_merge_genesis_drafts",
    "_project_description_from_body",
    "_validate_complete_genesis_draft",
    "_generate_real_draft_with_scaffold_fallback",
    # Prompt building
    "_build_genesis_common_context",
    "_build_genesis_segment_prompt",
    "_build_genesis_llm",
    "_build_genesis_completion_prompt",
    "_build_genesis_instruction_repair_prompt",
    # Instruction repair
    "_instruction_repair_issue_count",
    "_has_instruction_repair_target",
    "_format_genesis_quality_issues_for_prompt",
    "_instruction_repair_rank",
    "_build_local_instruction_repair_candidate",
    "_repair_genesis_instruction_quality",
    # Recovery and fallback
    "_mark_genesis_generation_fallback",
    "_mark_genesis_local_recovery",
    "_build_genesis_recovery_draft",
    "_recover_genesis_from_partial_draft",
]