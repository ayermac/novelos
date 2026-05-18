"""v6.1: Structured execution event helpers for agent observability.

Provides best-effort logging of fine-grained agent execution evidence
and completion verification. Never breaks the main workflow.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# ── Event type constants ────────────────────────────────────────

EVENT_NODE_STARTED = "node_started"
EVENT_CONTEXT_LOADED = "context_loaded"
EVENT_LLM_STARTED = "llm_started"
EVENT_LLM_COMPLETED = "llm_completed"
EVENT_LLM_FAILED = "llm_failed"
EVENT_LONG_FORM_GENERATION = "long_form_generation"
EVENT_ARTIFACT_SAVED = "artifact_saved"
EVENT_SKILL_STARTED = "skill_started"
EVENT_SKILL_COMPLETED = "skill_completed"
EVENT_TOOL_CALLED = "tool_called"
EVENT_SELF_CHECK_COMPLETED = "self_check_completed"
EVENT_FALLBACK_USED = "fallback_used"
EVENT_DIFF_GENERATED = "diff_generated"
EVENT_EVIDENCE_VERIFIED = "evidence_verified"
EVENT_NODE_COMPLETED = "node_completed"
EVENT_NODE_FAILED = "node_failed"
EVENT_NODE_SKIPPED = "node_skipped"
EVENT_QUALITY_DIAGNOSED = "quality_diagnosed"

EVIDENCE_STATUS_PASS = "pass"
EVIDENCE_STATUS_FAIL = "fail"
EVIDENCE_STATUS_WARN = "warn"


# ── Core logging helper ─────────────────────────────────────────

def log_execution_event(
    repo: Any,
    state: dict[str, Any],
    node_name: str,
    event_type: str,
    message: str,
    agent_id: str | None = None,
    status: str = "info",
    payload: dict[str, Any] | None = None,
    artifact_refs: list[dict] | None = None,
    token_count: int | None = None,
    latency_ms: int | None = None,
) -> int | None:
    """Best-effort log a workflow execution event. Never raises.

    Returns the event id on success, None on failure.
    """
    run_id = state.get("workflow_run_id")
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    if not run_id or not project_id or not chapter_number:
        return None
    try:
        return repo.create_workflow_execution_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=chapter_number,
            node_name=node_name,
            event_type=event_type,
            agent_id=agent_id or node_name,
            status=status,
            message=message,
            payload=payload,
            artifact_refs=artifact_refs,
            token_count=token_count,
            latency_ms=latency_ms,
        )
    except Exception:
        logger.warning(
            "Failed to log execution event for %s/%s node=%s event=%s",
            project_id, chapter_number, node_name, event_type,
            exc_info=True,
        )
        return None


# ── Context summarizers ─────────────────────────────────────────

def summarize_planner_context(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any]:
    """Summarize context loaded for Planner agent."""
    summary: dict[str, Any] = {}
    try:
        inst = repo.get_instruction(project_id, chapter_number)
        summary["has_instruction"] = inst is not None and bool(inst.get("objective"))
    except Exception:
        pass
    try:
        chars = repo.get_characters(project_id)
        summary["character_count"] = len(chars) if chars else 0
    except Exception:
        pass
    try:
        plots = repo.get_pending_plots(project_id)
        summary["pending_plot_count"] = len(plots) if plots else 0
    except Exception:
        pass
    try:
        prev_ch = chapter_number - 1
        if prev_ch >= 1:
            prev_state = repo.get_chapter_state(project_id, prev_ch)
            summary["has_prev_state_card"] = prev_state is not None
        else:
            summary["has_prev_state_card"] = False
    except Exception:
        pass
    return summary


def summarize_screenwriter_context(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any]:
    """Summarize context loaded for Screenwriter agent."""
    summary: dict[str, Any] = {}
    try:
        inst = repo.get_instruction(project_id, chapter_number)
        summary["has_instruction"] = inst is not None and bool(inst.get("objective"))
    except Exception:
        pass
    try:
        chars = repo.get_characters(project_id)
        summary["character_count"] = len(chars) if chars else 0
    except Exception:
        pass
    return summary


def summarize_author_context(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any]:
    """Summarize context loaded for Author agent."""
    summary: dict[str, Any] = {}
    try:
        beats = repo.get_scene_beats(project_id, chapter_number)
        summary["scene_beat_count"] = len(beats) if beats else 0
    except Exception:
        pass
    try:
        inst = repo.get_instruction(project_id, chapter_number)
        if inst:
            summary["has_instruction"] = True
            key_events = inst.get("key_events", "")
            if key_events:
                try:
                    events = json.loads(key_events) if isinstance(key_events, str) else key_events
                    summary["required_event_count"] = len(events) if isinstance(events, list) else 0
                except Exception:
                    summary["required_event_count"] = 0
            wt = inst.get("word_target")
            summary["word_target"] = wt if wt else None
        else:
            summary["has_instruction"] = False
    except Exception:
        pass
    return summary


def summarize_polisher_context(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any]:
    """Summarize context loaded for Polisher agent."""
    summary: dict[str, Any] = {}
    try:
        from ..validators.chapter_checker import count_words
        ch = repo.get_chapter(project_id, chapter_number)
        if ch and ch.get("content"):
            summary["original_word_count"] = count_words(ch["content"])
    except Exception:
        pass
    try:
        from ..validators.fact_lock import extract_fact_lock
        inst = repo.get_instruction(project_id, chapter_number)
        prev_ch = chapter_number - 1
        prev_state = repo.get_chapter_state(project_id, prev_ch) if prev_ch >= 1 else None
        fact_lock = extract_fact_lock(inst, prev_state)
        summary["fact_lock_count"] = len(fact_lock) if fact_lock else 0
    except Exception:
        pass
    return summary


def summarize_editor_context(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any]:
    """Summarize context loaded for Editor agent."""
    summary: dict[str, Any] = {}
    try:
        from ..validators.chapter_checker import count_words
        ch = repo.get_chapter(project_id, chapter_number)
        if ch and ch.get("content"):
            summary["content_word_count"] = count_words(ch["content"])
    except Exception:
        pass
    summary["review_dimensions"] = ["设定一致性", "逻辑漏洞", "毒点检测", "文字质量", "爽点钩子"]
    return summary


def summarize_memory_curator_context(repo: Any, project_id: str, chapter_number: int) -> dict[str, Any]:
    """Summarize context loaded for MemoryCurator agent."""
    summary: dict[str, Any] = {}
    try:
        ch = repo.get_chapter(project_id, chapter_number)
        summary["has_chapter_content"] = bool(ch and ch.get("content"))
    except Exception:
        pass
    try:
        state_card = repo.get_chapter_state(project_id, chapter_number)
        summary["has_state_card"] = state_card is not None
    except Exception:
        pass
    return summary


CONTEXT_SUMMARIZERS: dict[str, Any] = {
    "planner": summarize_planner_context,
    "screenwriter": summarize_screenwriter_context,
    "author": summarize_author_context,
    "polisher": summarize_polisher_context,
    "editor": summarize_editor_context,
    "memory_curator": summarize_memory_curator_context,
}


# ── Context summary message builders ────────────────────────────

def build_context_loaded_message(agent_id: str, summary: dict[str, Any]) -> str:
    """Build a user-readable Chinese message for context_loaded event."""
    if agent_id == "planner":
        parts = []
        if summary.get("has_prev_state_card"):
            parts.append("上一章状态卡")
        if summary.get("character_count"):
            parts.append(f"{summary['character_count']} 个角色")
        if summary.get("pending_plot_count"):
            parts.append(f"{summary['pending_plot_count']} 个待处理伏笔")
        return f"读取上下文完成：{'、'.join(parts)}" if parts else "读取上下文完成"

    if agent_id == "screenwriter":
        parts = []
        if summary.get("has_instruction"):
            parts.append("章节指令")
        if summary.get("character_count"):
            parts.append(f"{summary['character_count']} 个角色")
        return f"读取上下文完成：{'、'.join(parts)}" if parts else "读取上下文完成"

    if agent_id == "author":
        parts = []
        if summary.get("scene_beat_count"):
            parts.append(f"{summary['scene_beat_count']} 个场景")
        if summary.get("required_event_count"):
            parts.append(f"{summary['required_event_count']} 个关键事件")
        if summary.get("word_target"):
            parts.append(f"字数目标 {summary['word_target']}")
        return f"读取上下文完成：{'、'.join(parts)}" if parts else "读取上下文完成"

    if agent_id == "polisher":
        parts = []
        if summary.get("original_word_count"):
            parts.append(f"章节初稿 {summary['original_word_count']} 字")
        if summary.get("fact_lock_count"):
            parts.append(f"事实锁 {summary['fact_lock_count']} 条")
        return f"读取上下文完成：{'、'.join(parts)}" if parts else "读取上下文完成"

    if agent_id == "editor":
        parts = []
        if summary.get("content_word_count"):
            parts.append(f"正文 {summary['content_word_count']} 字")
        dims = summary.get("review_dimensions", [])
        if dims:
            parts.append(f"{len(dims)} 个审校维度")
        return f"读取上下文完成：{'、'.join(parts)}" if parts else "读取上下文完成"

    if agent_id == "memory_curator":
        parts = []
        if summary.get("has_chapter_content"):
            parts.append("章节正文")
        if summary.get("has_state_card"):
            parts.append("状态卡")
        return f"读取上下文完成：{'、'.join(parts)}" if parts else "读取上下文完成（无可用数据）"

    return "读取上下文完成"


# ── Evidence verification ───────────────────────────────────────

def verify_agent_completion_evidence(
    repo: Any,
    state: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    """Verify that an agent produced required completion evidence.

    Returns a dict with:
      - ok: bool
      - severity: 'pass' | 'fail' | 'warn'
      - checks: list of check results
      - missing: list of missing items
      - warnings: list of warning strings
    """
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    run_id = state.get("workflow_run_id", "")

    checks: list[dict[str, Any]] = []
    missing: list[str] = []
    warnings: list[str] = []

    if agent_id == "planner":
        _verify_planner(repo, project_id, chapter_number, run_id, checks, missing)
    elif agent_id == "screenwriter":
        _verify_screenwriter(repo, project_id, chapter_number, run_id, checks, missing)
    elif agent_id == "author":
        _verify_author(repo, project_id, chapter_number, run_id, checks, missing)
    elif agent_id == "polisher":
        _verify_polisher(repo, project_id, chapter_number, run_id, checks, missing)
    elif agent_id == "editor":
        _verify_editor(repo, project_id, chapter_number, run_id, checks, missing, warnings)
    elif agent_id == "memory_curator":
        _verify_memory_curator(repo, project_id, chapter_number, run_id, checks, missing, warnings)

    ok = len(missing) == 0
    if not ok:
        severity = EVIDENCE_STATUS_FAIL
    elif warnings:
        severity = EVIDENCE_STATUS_WARN
    else:
        severity = EVIDENCE_STATUS_PASS

    return {
        "ok": ok,
        "severity": severity,
        "checks": checks,
        "missing": missing,
        "warnings": warnings,
    }


def _verify_planner(
    repo: Any, project_id: str, chapter_number: int, run_id: str,
    checks: list, missing: list,
) -> None:
    inst = repo.get_instruction(project_id, chapter_number)
    has_inst = inst is not None and bool(inst.get("objective"))
    checks.append({"check": "instruction_exists", "passed": has_inst})
    if not has_inst:
        missing.append("章节指令缺失")
        return

    has_obj = bool(inst.get("objective"))
    has_events = bool(inst.get("key_events"))
    has_hook = bool(inst.get("ending_hook"))
    checks.append({"check": "objective_present", "passed": has_obj})
    checks.append({"check": "key_events_present", "passed": has_events})
    checks.append({"check": "ending_hook_present", "passed": has_hook})
    if not has_obj:
        missing.append("指令目标缺失")
    if not has_events:
        missing.append("关键事件缺失")
    if not has_hook:
        missing.append("章末钩子缺失")


def _verify_screenwriter(
    repo: Any, project_id: str, chapter_number: int, run_id: str,
    checks: list, missing: list,
) -> None:
    beats = repo.get_scene_beats(project_id, chapter_number)
    beat_count = len(beats) if beats else 0
    checks.append({"check": "scene_beats_exist", "passed": beat_count > 0, "count": beat_count})
    if beat_count == 0:
        missing.append("场景 beats 缺失")
        return

    complete_beats = 0
    for beat in beats:
        has_all = all(beat.get(f) for f in ("scene_goal", "conflict", "turn", "hook"))
        if has_all:
            complete_beats += 1
    checks.append({
        "check": "beats_have_required_fields",
        "passed": complete_beats == beat_count,
        "complete": complete_beats,
        "total": beat_count,
    })
    if complete_beats < beat_count:
        missing.append(f"部分 beat 缺失必填字段 ({complete_beats}/{beat_count})")


def _verify_author(
    repo: Any, project_id: str, chapter_number: int, run_id: str,
    checks: list, missing: list,
) -> None:
    ch = repo.get_chapter(project_id, chapter_number)
    has_content = bool(ch and ch.get("content") and ch["content"].strip())
    checks.append({"check": "content_non_empty", "passed": has_content})
    if not has_content:
        missing.append("章节正文为空")

    has_heading = bool(ch and ch.get("title"))
    checks.append({"check": "heading_present", "passed": has_heading})
    if not has_heading:
        missing.append("章节标题缺失")

    try:
        versions = repo.list_chapter_versions(project_id, chapter_number)
        has_version = bool(versions)
    except Exception:
        has_version = False
    checks.append({"check": "version_saved", "passed": has_version})
    if not has_version:
        missing.append("版本记录未保存")

    try:
        artifacts = repo.get_artifacts_for_chapter(
            project_id, chapter_number, workflow_run_id=run_id,
        )
        has_draft = any(a.get("artifact_type") == "draft" for a in artifacts)
    except Exception:
        has_draft = False
    checks.append({"check": "draft_artifact_saved", "passed": has_draft})
    if not has_draft:
        missing.append("初稿产物未保存")


def _verify_polisher(
    repo: Any, project_id: str, chapter_number: int, run_id: str,
    checks: list, missing: list,
) -> None:
    ch = repo.get_chapter(project_id, chapter_number)
    has_content = bool(ch and ch.get("content") and ch["content"].strip())
    checks.append({"check": "content_saved", "passed": has_content})
    if not has_content:
        missing.append("润色后正文未保存")

    try:
        artifacts = repo.get_artifacts_for_chapter(
            project_id, chapter_number, workflow_run_id=run_id,
        )
        has_polished = any(
            a.get("artifact_type") in ("polished_draft", "polished_content")
            for a in artifacts
        )
    except Exception:
        has_polished = False
    checks.append({"check": "polished_artifact_saved", "passed": has_polished})
    if not has_polished:
        missing.append("润色稿产物未保存")


def _verify_editor(
    repo: Any, project_id: str, chapter_number: int, run_id: str,
    checks: list, missing: list, warnings: list,
) -> None:
    try:
        ch = repo.get_chapter(project_id, chapter_number)
        chapter_id = ch["id"] if ch else None
        review = repo.get_latest_review(project_id, chapter_id) if chapter_id else None
        has_review = review is not None
    except Exception:
        has_review = False
    checks.append({"check": "review_record_saved", "passed": has_review})
    if not has_review:
        missing.append("审核记录未保存")
        return

    passed = bool(review.get("pass")) if review else False
    if passed:
        try:
            state_card = repo.get_chapter_state(project_id, chapter_number)
            has_state = state_card is not None
        except Exception:
            has_state = False
        checks.append({"check": "state_card_saved", "passed": has_state})
        if not has_state:
            missing.append("通过审核但状态卡未保存")


def _verify_memory_curator(
    repo: Any, project_id: str, chapter_number: int, run_id: str,
    checks: list, missing: list, warnings: list,
) -> None:
    try:
        all_batches = repo.list_memory_batches(project_id)
        batches = [b for b in (all_batches or []) if b.get("chapter_number") == chapter_number]
        has_batch = bool(batches)
    except Exception:
        has_batch = False

    if has_batch:
        checks.append({"check": "memory_batch_created", "passed": True})
    else:
        checks.append({"check": "memory_batch_created", "passed": False})
        missing.append("未创建记忆收件箱批次")


# ── Timer context manager ───────────────────────────────────────

class ExecutionTimer:
    """Simple timer for measuring operation latency."""

    def __init__(self) -> None:
        self._start: float = 0
        self._latency_ms: int = 0

    def __enter__(self) -> ExecutionTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self._latency_ms = int((time.perf_counter() - self._start) * 1000)

    @property
    def latency_ms(self) -> int:
        return self._latency_ms
