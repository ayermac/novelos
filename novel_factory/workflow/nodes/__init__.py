"""LangGraph node functions for the chapter production workflow.

Each node takes a FactoryState and returns a dict of updates to merge.
v1.1: Nodes now track workflow_runs lifecycle and update current_node.
v5.1.6: Added create_node_runners for LLMRouter-based dependency injection.
"""

from __future__ import annotations

import logging
import json
import time
from typing import Any, Callable

from ...db.repository import Repository
from ...llm.provider import LLMProvider
from ...llm.openai_compatible import ContentFilterError, OutputValidationError
from ...models.state import ChapterStatus, FactoryState
from ..conditions import hydrate_revision_state, revision_target_from_state
from ...agents.planner import PlannerAgent
from ...agents.planner import build_memory_context_audit
from ...quality.chapter_brief_validator import validate_chapter_brief, fill_missing_tier2_fields
from ...agents.screenwriter import ScreenwriterAgent
from ...agents.author import AuthorAgent
from ...agents.polisher import PolisherAgent
from ...agents.editor import EditorAgent
from ...agents.memory_curator import MemoryCuratorAgent
from ...agent_runtime.context_builder import AgentContextBuilder
from ..execution_events import (
    log_execution_event,
    CONTEXT_SUMMARIZERS,
    build_context_loaded_message,
    verify_agent_completion_evidence,
    EVENT_CONTEXT_LOADED,
    EVENT_LLM_STARTED,
    EVENT_LLM_REQUEST_DETAIL,
    EVENT_LLM_RESPONSE_DETAIL,
    EVENT_LLM_COMPLETED,
    EVENT_LLM_FAILED,
    EVENT_NODE_TIMEOUT,
    EVENT_EVIDENCE_VERIFIED,
    EVENT_FALLBACK_USED,
    EVIDENCE_STATUS_FAIL,
    EVIDENCE_STATUS_WARN,
)

logger = logging.getLogger(__name__)

# Import all helper functions from helpers module
from .helpers import (
    # Public helpers
    _node_message,
    _node_timeout_seconds,
    _redact_trace_value,
    _log_llm_trace_events,
    _log_node_event,
    _retryable_quality_gate_message,
    _log_agent_node_outcome,
    _update_run_node,
    _guard_blocking_db_status,
    _finalize_run,
    _append_step,
    _save_memory_context_audit_if_missing,
    _accumulate_tokens,
    _enforce_token_budget,
    _handle_retryable_quality_gate,
    _memory_curator_real_mode_error,
    _ensure_skill_registry,
    _ensure_tool_registry,
    _ensure_trace_store,
    _previous_agent_in_steps,
    _latest_artifact_content,
    create_node_runners,
    # Constants
    _NODE_TIMEOUT_FLOORS,
    _NODE_MESSAGES,
    MAX_INTERNAL_REPAIR_ATTEMPTS,
)

# Node implementations continue below...
def flow_control_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Flow control node using FlowRouter for deterministic routing.

    v6.10.13: Uses FlowRouter to determine routing before task_discovery.
    If FlowRouter returns an instruction, it's added to state for downstream use.
    """
    from ...dispatch.flow_router import route
    from ...dispatch.state_loader import StateLoader

    project_id = state.get("project_id", "")
    if not project_id:
        return {}

    try:
        # Load router state
        loader = StateLoader(repo)
        router_state = loader.load(project_id)

        # Get routing instruction
        instruction = route(router_state)

        if instruction:
            logger.info(
                "FlowControl: action=%s chapter=%d reason=%s",
                instruction.action.value,
                instruction.chapter,
                instruction.reason,
            )
            # Store instruction in state for downstream nodes
            return {
                "_flow_action": instruction.action.value,
                "_flow_chapter": instruction.chapter,
                "_flow_agent": instruction.agent,
                "_flow_task": instruction.task,
                "_flow_reason": instruction.reason,
            }
    except Exception as e:
        logger.warning("FlowControl: failed, falling back to default routing: %s", e)

    return {}


def health_check_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Check database health and ensure workflow_run_id exists.

    Creates a new workflow_run if state does not already have one.
    This is the entry point of the graph.
    """
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    run_id = state.get("workflow_run_id")

    updates: dict[str, Any] = {}

    if not run_id:
        run_id = repo.create_workflow_run(project_id, chapter_number)
        updates["workflow_run_id"] = run_id
        logger.info("Created workflow_run %s for project=%s chapter=%s", run_id, project_id, chapter_number)
    else:
        updates["workflow_run_id"] = run_id

    event_state = {**state, "workflow_run_id": run_id}
    _update_run_node(event_state, repo, "health_check")
    _log_node_event(event_state, repo, "health_check", "started", status="running")
    _log_node_event(event_state, repo, "health_check", "completed", status="completed")

    return updates


def task_discovery_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Discover what needs to be done based on chapter status.

    Reads the current chapter status from DB (source of truth).
    If DB status differs from FactoryState, uses DB status.
    If chapter does not exist in DB, returns error with requires_human=True.

    v5.3.0: Also checks if instruction exists for Planner 必经 routing.
    """
    _update_run_node(state, repo, "task_discovery")
    _log_node_event(state, repo, "task_discovery", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    if not project_id or not chapter_number:
        _log_node_event(state, repo, "task_discovery", "failed", status="failed", error_message="Missing project_id or chapter_number")
        _finalize_run(state, repo, "failed", "Missing project_id or chapter_number")
        return {"error": "Missing project_id or chapter_number"}

    db_status = repo.get_chapter_status(project_id, chapter_number)
    if not db_status:
        _log_node_event(state, repo, "task_discovery", "failed", status="failed", error_message="Chapter not found in DB")
        _finalize_run(state, repo, "blocked", "Chapter not found in DB")
        return {"error": "Chapter not found in DB", "requires_human": True, "chapter_status": "blocking"}

    # v5.3.0: Check if instruction exists for Planner 必经 routing
    instruction = repo.get_instruction(project_id, chapter_number)
    has_instruction = instruction is not None and bool(instruction.get("objective"))

    state_status = state.get("chapter_status", "")
    if db_status == ChapterStatus.REVISION.value:
        base_state = {
            **state,
            "chapter_status": db_status,
            "has_instruction": has_instruction,
        }
        hydrated = hydrate_revision_state(base_state, repo)
        hydrated_updates = {
            key: value
            for key, value in hydrated.items()
            if key not in state or state.get(key) != value
        }
        hydrated_updates["chapter_status"] = db_status
        hydrated_updates["has_instruction"] = has_instruction
        _log_node_event(state, repo, "task_discovery", "completed", status="completed")
        return hydrated_updates

    if db_status != state_status:
        logger.info(
            "task_discovery: DB status '%s' overrides state status '%s'",
            db_status, state_status,
        )
        _log_node_event(state, repo, "task_discovery", "completed", status="completed")
        return {"chapter_status": db_status, "has_instruction": has_instruction}

    _log_node_event(state, repo, "task_discovery", "completed", status="completed")
    return {"has_instruction": has_instruction}


def _v6_agent_kwargs(
    repo: Repository,
    skill_registry: Any | None = None,
    knowledge_manager: Any | None = None,
    agent_config: dict[str, Any] | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    """v6.0: Build shared kwargs for core agent instantiation in legacy mode.
    v6.10.13: Added checkpoint_dir for step-level crash recovery."""
    kwargs: dict[str, Any] = {
        "skill_registry": _ensure_skill_registry(skill_registry),
        "tool_registry": _ensure_tool_registry(),
        "trace_store": _ensure_trace_store(repo),
    }
    # v6.10.0: Inject knowledge manager and agentic config
    if knowledge_manager is not None:
        kwargs["knowledge_manager"] = knowledge_manager
    if agent_config is not None:
        kwargs["agent_config"] = agent_config
    if checkpoint_dir is not None:
        kwargs["checkpoint_dir"] = checkpoint_dir
    return kwargs


def planner_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Planner agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    # v6.10.7: Protagonist integrity gate — do not plan without a protagonist.
    project_id = state.get("project_id")
    if project_id:
        try:
            protagonist = repo.get_protagonist(project_id)
            if not protagonist:
                error = {
                    "error": "PROJECT_INTEGRITY_VIOLATION: 项目缺少主角（protagonist），无法生成章节规划。请先创建或恢复主角。",
                    "chapter_status": state.get("chapter_status"),
                    "requires_human": True,
                }
                _log_agent_node_outcome(state, repo, "planner", error)
                return error
            if not protagonist.get("name"):
                error = {
                    "error": "PROJECT_INTEGRITY_VIOLATION: 主角记录存在但名字为空，无法生成章节规划。请先修复主角名字。",
                    "chapter_status": state.get("chapter_status"),
                    "requires_human": True,
                }
                _log_agent_node_outcome(state, repo, "planner", error)
                return error
        except Exception as e:
            logger.warning("Planner protagonist check failed: %s", e, exc_info=True)
    _update_run_node(state, repo, "planner")
    _log_node_event(state, repo, "planner", "started", status="running")
    agent = PlannerAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "planner", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "planner", result)
    return result


def screenwriter_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Screenwriter agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "screenwriter")
    _log_node_event(state, repo, "screenwriter", "started", status="running")
    audit = _save_memory_context_audit_if_missing(
        state,
        repo,
        built_at_node="screenwriter_node",
    )
    agent = ScreenwriterAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    if audit:
        result.setdefault("memory_context_audit", audit)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "screenwriter", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "screenwriter", result)
    return result


def author_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Author agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "author")
    _log_node_event(state, repo, "author", "started", status="running")
    # v6.10.13: Pass checkpoint_dir if available in state for step-level recovery
    checkpoint_dir = state.get("checkpoint_dir")
    agent = AuthorAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry, checkpoint_dir=checkpoint_dir))
    result = _handle_retryable_quality_gate(state, repo, agent.run(state))
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "author", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "author", result)
    return result


def polisher_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Polisher agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "polisher")
    _log_node_event(state, repo, "polisher", "started", status="running")
    agent = PolisherAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = _handle_retryable_quality_gate(state, repo, agent.run(state))
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "polisher", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "polisher", result)
    return result


def promote_to_polished_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """v6.10.9: Lightweight node to promote chapter status from 'drafted' to 'polished'.

    When the Polisher is skipped (revision target is author/screenwriter),
    the chapter status must still be promoted so the Editor's precondition
    (requires 'polished') is satisfied.  This node does the minimum DB update
    without calling any LLM.
    """
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)

    try:
        db_status = repo.get_chapter_status(project_id, chapter_number)
        if db_status == ChapterStatus.DRAFTED.value:
            repo.update_chapter_status(project_id, chapter_number, ChapterStatus.POLISHED.value)
            logger.info(
                "promote_to_polished: %s ch%d status drafted → polished (Polisher skipped)",
                project_id, chapter_number,
            )
            return {"chapter_status": ChapterStatus.POLISHED.value}
    except Exception:
        logger.warning(
            "promote_to_polished: failed to update status for %s ch%d",
            project_id, chapter_number, exc_info=True,
        )
    return {}


# v6.8.5: Quality Gate 独立节点
def _check_death_penalty(content: str) -> dict[str, Any]:
    """检查死刑红线"""
    from ...validators.death_penalty import check_death_penalty_structured
    from ...quality.issue_codes import IssueCode

    dp_result = check_death_penalty_structured(content)
    return {
        "check_name": "death_penalty",
        "passed": not dp_result.has_critical,
        "blocking_issues": [f"CRITICAL 死刑红线: {v}" for v in dp_result.violations] if dp_result.has_critical else [],
        "score_penalty": 50 if dp_result.has_critical else 0,
        "issue_codes": [IssueCode.DEATH_PENALTY] if dp_result.has_critical else [],
        "diagnostics": {
            "has_critical": dp_result.has_critical,
            "violations": dp_result.violations,
        },
    }


def _check_word_count(content: str, repo: Repository, project_id: str, chapter_number: int) -> dict[str, Any]:
    """检查字数门禁"""
    from ...validators.chapter_checker import count_words, check_word_count_quality_gate, derive_word_target
    from ...quality.issue_codes import IssueCode

    instruction = repo.get_instruction(project_id, chapter_number)
    project = repo.get_project(project_id)
    word_target = derive_word_target(instruction, project)
    word_gate_passed, word_gate_msg = check_word_count_quality_gate(
        content, word_target, "quality_gate"
    )

    issue_codes = []
    if not word_gate_passed:
        issue_codes.append(IssueCode.WORD_COUNT_BELOW_MIN)

    return {
        "check_name": "word_count_gate",
        "passed": word_gate_passed,
        "blocking_issues": [word_gate_msg] if not word_gate_passed else [],
        "score_penalty": 30 if not word_gate_passed else 0,
        "issue_codes": issue_codes,
        "diagnostics": {
            "passed": word_gate_passed,
            "message": word_gate_msg,
            "actual_word_count": count_words(content),
            "word_target": word_target,
        },
    }


def _check_chapter_seam(repo: Repository, project_id: str, chapter_number: int, content: str) -> dict[str, Any]:
    """检查章间衔接"""
    from ...quality.chapter_seam import evaluate_chapter_seam
    from ...quality.issue_codes import IssueCode

    seam_gate = evaluate_chapter_seam(repo, project_id, chapter_number, content)
    passed = seam_gate.get("pass", True)

    issue_codes = []
    if not passed:
        issue_codes.append(IssueCode.CHAPTER_SEAM_BREAK)

    return {
        "check_name": "chapter_seam",
        "passed": passed,
        "blocking_issues": seam_gate.get("blocking_issues", [])[:3] if not passed else [],
        "advisory_issues": seam_gate.get("advisory_issues", [])[:2],
        "score_penalty": 21 if not passed else 0,
        "issue_codes": issue_codes,
        "diagnostics": {
            "passed": passed,
            "blocking_issues": seam_gate.get("blocking_issues", []),
            "advisory_issues": seam_gate.get("advisory_issues", []),
        },
    }


def _check_continuity_gate(repo: Repository, project_id: str, chapter_number: int, content: str, title: str = None) -> dict[str, Any]:
    """检查叙事连续性"""
    from ...quality.continuity_gate import evaluate_chapter_continuity, SEVERITY_BLOCKING
    from ...quality.issue_codes import IssueCode

    continuity_result = evaluate_chapter_continuity(
        repo, project_id, chapter_number, content,
        title=title,
    )
    should_block = continuity_result.should_block_publish or continuity_result.severity == SEVERITY_BLOCKING

    issue_codes = []
    if should_block:
        # 根据具体问题类型确定 issue_code（映射表驱动，便于维护与扩展）
        # 顺序敏感：更具体的匹配项排在前面。未命中任何关键词时回退到
        # CONTINUITY_TIME_REGRESSION 以保持与历史路由行为一致。
        continuity_issue_map = (
            (("时间", "回归", "倒计时", "时间线"), IssueCode.CONTINUITY_TIME_REGRESSION),
            (("事件", "重播", "重复", "重演"), IssueCode.CONTINUITY_EVENT_REPLAY),
            (("标题", "截断", "章名", "衔接"), IssueCode.CONTINUITY_TITLE_TRUNCATION),
        )
        for issue in continuity_result.issues:
            matched = next(
                (
                    code
                    for keywords, code in continuity_issue_map
                    if any(keyword in issue for keyword in keywords)
                ),
                None,
            )
            issue_codes.append(matched if matched is not None else IssueCode.CONTINUITY_TIME_REGRESSION)

    return {
        "check_name": "continuity_gate",
        "passed": not should_block,
        "blocking_issues": [f"[连续性阻断] {i}" for i in continuity_result.issues[:3]] if should_block else [],
        "advisory_issues": [f"[连续性建议] {i}" for i in continuity_result.issues[:2]] if not should_block else [],
        "score_penalty": 30 if should_block else 0,
        "issue_codes": issue_codes,
        "diagnostics": {
            "should_block": continuity_result.should_block_publish,
            "severity": continuity_result.severity,
            "issues": continuity_result.issues,
        },
    }


def _check_quality_diagnosis(content: str, repo: Repository, project_id: str, chapter_number: int, skill_registry) -> dict[str, Any]:
    """检查质量诊断"""
    from ...quality.hub import QualityHub
    from ...quality.feedback_bridge import build_compact_feedback
    from ...quality.issue_codes import IssueCode

    hub = QualityHub(repo, skill_registry)
    diagnose_result = hub.diagnose(content, context={
        "project_id": project_id,
        "chapter_number": chapter_number,
    })
    qf = build_compact_feedback(diagnose_result)

    issue_codes = []
    if qf.priority_findings:
        for f in qf.priority_findings[:3]:
            code = f.get("code", "")
            if "ai_trace" in code.lower() or "ai-style" in code.lower():
                issue_codes.append(IssueCode.QUALITY_AI_TRACE)
            elif "narrative" in code.lower():
                issue_codes.append(IssueCode.QUALITY_NARRATIVE_LOW)
            else:
                issue_codes.append(IssueCode.QUALITY_STYLE_ISSUE)

    return {
        "check_name": "quality_diagnosis",
        "passed": True,  # 质量诊断不阻塞，只提供优先级信息
        "priority_issues": [f"[诊断] [{f['code']}] {f['message']}" for f in qf.priority_findings[:3]],
        "advisory_issues": [f"[诊断建议] [{f['code']}] {f['message']}" for f in qf.advisory_findings[:2]],
        "score_penalty": 0,
        "issue_codes": issue_codes,
        "diagnostics": {
            "priority_count": len(qf.priority_findings),
            "advisory_count": len(qf.advisory_findings),
        },
    }


def _check_core_loop_compliance(repo: Repository, project_id: str, chapter_number: int, content: str) -> dict[str, Any]:
    """v6.10.5: 检查核心循环合规性（Story Contract compliance）"""
    from ...quality.core_loop_checker import check_core_loop_compliance, derive_fallback_story_contract
    from ...models.creative_contracts import StoryContract
    from ...models.chapter_contracts import ChapterBrief
    from ...models.creative_ledgers import ChapterContractMetrics
    from ...quality.issue_codes import IssueCode

    # Load or derive story contract
    row = repo.get_creative_contract(project_id, "story_contract")
    if row:
        data_str = row.get("contract_data", "{}")
        import json as _json
        try:
            contract_data = _json.loads(data_str) if isinstance(data_str, str) else data_str
            story_contract = StoryContract(**contract_data)
        except Exception:
            lp_row = repo.get_creative_contract(project_id, "launch_profile")
            gc_row = repo.get_creative_contract(project_id, "genre_contract")
            lp = _json.loads(lp_row["contract_data"]) if lp_row and isinstance(lp_row.get("contract_data"), str) else (lp_row.get("contract_data") if lp_row else None)
            gc = _json.loads(gc_row["contract_data"]) if gc_row and isinstance(gc_row.get("contract_data"), str) else (gc_row.get("contract_data") if gc_row else None)
            story_contract = derive_fallback_story_contract(project_id, lp, gc)
    else:
        lp_row = repo.get_creative_contract(project_id, "launch_profile")
        gc_row = repo.get_creative_contract(project_id, "genre_contract")
        import json as _json
        lp = _json.loads(lp_row["contract_data"]) if lp_row and isinstance(lp_row.get("contract_data"), str) else (lp_row.get("contract_data") if lp_row else None)
        gc = _json.loads(gc_row["contract_data"]) if gc_row and isinstance(gc_row.get("contract_data"), str) else (gc_row.get("contract_data") if gc_row else None)
        story_contract = derive_fallback_story_contract(project_id, lp, gc)

    # Load chapter brief
    brief_row = repo.get_chapter_brief(project_id, chapter_number)
    chapter_brief = None
    if brief_row:
        import json as _json
        brief_data = brief_row.get("brief_data", {})
        if isinstance(brief_data, str):
            try:
                brief_data = _json.loads(brief_data)
            except Exception:
                brief_data = {}
        try:
            chapter_brief = ChapterBrief(**brief_data)
        except Exception:
            chapter_brief = None

    # Load recent contract metrics
    metrics_raw = repo.get_chapter_contract_metrics(project_id, limit=5, before_chapter=chapter_number)
    recent_metrics = []
    for m in metrics_raw:
        if isinstance(m, dict):
            try:
                recent_metrics.append(ChapterContractMetrics(**m))
            except Exception:
                pass

    # Run compliance check
    result = check_core_loop_compliance(
        project_id=project_id,
        chapter_number=chapter_number,
        content=content,
        story_contract=story_contract,
        chapter_brief=chapter_brief,
        recent_contract_metrics=recent_metrics,
    )

    # Store contract metrics in ledger for future trend checking
    if result.contract_metrics:
        try:
            repo.upsert_creative_ledger(
                project_id=project_id,
                chapter_number=chapter_number,
                ledger_type="contract_metrics",
                ledger_data=result.contract_metrics.model_dump(),
            )
        except Exception:
            logger.debug("Failed to store contract metrics for ch%d", chapter_number, exc_info=True)

    # Build result — default advisory; blocking only if contract is confirmed AND consecutive violations exceed threshold
    advisory = []
    priority = []
    blocking = []
    issue_codes = []

    if not result.core_payoff_present:
        advisory.append(f"[核心循环] 未检测到核心兑现证据（score={result.score:.0f}）")
        issue_codes.append(IssueCode.CORE_LOOP_PAYOFF_MISSING)

    for w in result.warnings:
        advisory.append(f"[核心循环] {w}")

    contract_allows_blocking = story_contract.status in {"active", "confirmed"}
    for ds in result.drift_signals:
        if ds.severity == "blocking" and contract_allows_blocking:
            blocking.append(f"[核心循环阻断] {ds.description}")
            issue_codes.append(IssueCode.CORE_LOOP_DRIFT_WARNING)
        elif ds.severity == "warning":
            priority.append(f"[核心循环漂移] {ds.description}")
            issue_codes.append(IssueCode.CORE_LOOP_DRIFT_WARNING)

    return {
        "check_name": "core_loop_compliance",
        "passed": len(blocking) == 0,
        "advisory_issues": advisory,
        "priority_issues": priority,
        "blocking_issues": blocking,
        "score_penalty": max(0, (100 - result.score) * 0.2),  # penalty proportional to gap
        "issue_codes": issue_codes,
        "diagnostics": {
            "score": result.score,
            "core_payoff_present": result.core_payoff_present,
            "supporting_mechanism_dominance": result.supporting_mechanism_dominance,
            "new_mechanism_count": result.new_mechanism_count,
            "protagonist_agency_present": result.protagonist_agency_present,
            "reward_acquired": result.reward_acquired,
            "reward_used": result.reward_used,
            "enemy_consequence": result.enemy_consequence,
            "required_payoff_present": result.required_payoff_present,
            "missing_evidence": result.missing_evidence,
            "evidence_spans": result.evidence_spans,
            "tracked_states": result.tracked_states,
            "state_deltas": result.state_deltas,
            "warnings": result.warnings,
            "drift_signals": [{"type": s.drift_type, "severity": s.severity, "message": s.description} for s in result.drift_signals],
            "contract_status": story_contract.status,
        },
    }


def _determine_revision_target(issue_codes: list, scene_beats: list[dict] | None = None) -> str | None:
    """根据结构化问题代码确定返修目标

    v6.10.9: CORE_LOOP 问题根据 beat 设计层判断路由：
    - scene_beats 有 is_reward_beat=true → "author"（beat 已设计，内容未体现）
    - scene_beats 无 is_reward_beat=true → "screenwriter"（beat 设计层缺失）

    优先级：非 CORE_LOOP 的 author 级问题 > CORE_LOOP beat-aware 路由 > polisher
    """
    from ...quality.issue_codes import IssueCode, ISSUE_CODE_TO_REVISION_TARGET

    if not issue_codes:
        return None

    # 非 CORE_LOOP 的 author 级问题（最高优先级，不受 beat 设计影响）
    critical_author_codes = {
        IssueCode.DEATH_PENALTY, IssueCode.CHAPTER_SEAM_BREAK,
        IssueCode.CONTINUITY_TIME_REGRESSION, IssueCode.CONTINUITY_EVENT_REPLAY,
        IssueCode.CONTINUITY_TITLE_TRUNCATION, IssueCode.STORY_FACTS_CONTRADICTION,
    }
    for code in issue_codes:
        if code in critical_author_codes:
            return "author"

    # 字数门禁类（高优先级，内容结构性问题）
    word_count_codes = {IssueCode.WORD_COUNT_BELOW_MIN, IssueCode.WORD_COUNT_ABOVE_MAX}
    has_word_count_issue = any(code in word_count_codes for code in issue_codes)
    if has_word_count_issue:
        return "polisher"

    # v6.10.9: CORE_LOOP 问题根据 beat 设计层路由
    core_loop_codes = {IssueCode.CORE_LOOP_PAYOFF_MISSING, IssueCode.CORE_LOOP_DRIFT_WARNING}
    has_core_loop_issue = any(code in core_loop_codes for code in issue_codes)

    if has_core_loop_issue:
        has_reward_beat = bool(scene_beats) and any(b.get("is_reward_beat") for b in scene_beats)
        if has_reward_beat:
            return "author"  # beat 已设计 reward，内容未体现
        if scene_beats:
            # v6.10.9-fix: beats 存在但无 is_reward_beat → beats 已设计，问题在内容层
            # 路由到 author 让其在现有 beat 框架内修复兑现证据
            return "author"
        return "screenwriter"  # 无 beat 数据，需要从设计层修复

    # 质量诊断类 → polisher
    return "polisher"


def _run_quality_checker_safely(checker_name: str, checker_fn):
    """Run a quality checker with unified error handling.

    Returns (result, error) tuple. Exactly one element is None.
    On success: (result_dict, None)
    On failure: (None, error_dict) where error_dict carries checker/error_type/message/diag.

    This helper eliminates the 4-way try/except boilerplate (CheckerConfigError,
    CheckerTimeoutError, CheckerTemporaryFailure, Exception) that was previously
    duplicated across 6 checkers in quality_gate_node.
    """
    from ...quality.issue_codes import (
        CheckerConfigError,
        CheckerTemporaryFailure,
        CheckerTimeoutError,
    )
    try:
        return checker_fn(), None
    except CheckerConfigError as e:
        logger.error("QualityGate: %s config error: %s", checker_name, e)
        return None, {
            "checker": checker_name,
            "error_type": "config",
            "message": str(e),
            "diag": {"error": "config_error", "message": str(e)},
        }
    except CheckerTimeoutError as e:
        logger.warning("QualityGate: %s timeout: %s", checker_name, e)
        return None, {
            "checker": checker_name,
            "error_type": "timeout",
            "message": str(e),
            "diag": {"error": "timeout", "message": str(e)},
        }
    except CheckerTemporaryFailure as e:
        logger.warning("QualityGate: %s temporary failure: %s", checker_name, e)
        return None, {
            "checker": checker_name,
            "error_type": "temporary",
            "message": str(e),
            "diag": {"error": "temporary_failure", "message": str(e)},
        }
    except Exception as e:
        logger.warning("QualityGate: %s check failed", checker_name, exc_info=True)
        return None, {
            "checker": checker_name,
            "error_type": "unknown",
            "message": str(e),
            "diag": {"error": "check failed"},
        }


def _record_checker_error(error: dict, diagnostics: dict, checker_errors: list) -> None:
    """Record a checker error into diagnostics and checker_errors lists."""
    checker_errors.append({
        "checker": error["checker"],
        "error_type": error["error_type"],
        "message": error["message"],
    })
    diagnostics[error["checker"]] = error["diag"]


def _aggregate_checker_result(
    result: dict,
    *,
    blocking_issues: list,
    priority_issues: list,
    advisory_issues: list,
    all_issue_codes: list,
    diagnostics: dict,
    checks_run: list,
    score: float,
    mode: str = "blocking_on_fail",
) -> float:
    """Aggregate a successful checker result into the gate accumulators.

    Returns the updated score. Modes:
    - ``blocking_on_fail``: extend blocking_issues + apply score penalty when
      ``not result["passed"]`` (used by death_penalty, word_count, chapter_seam,
      continuity_gate).
    - ``conditional_blocking``: extend blocking_issues only when present, no
      score penalty (used by core_loop_compliance).
    - ``advisory_only``: no blocking/score handling (used by quality_diagnosis).

    advisory_issues/priority_issues are always extended with ``result.get(..., [])``
    which is a no-op when the checker does not populate them.
    """
    check_name = result["check_name"]
    checks_run.append(check_name)
    diagnostics[check_name] = result["diagnostics"]
    if mode == "blocking_on_fail" and not result["passed"]:
        blocking_issues.extend(result["blocking_issues"])
        score = min(score, score - result["score_penalty"])
    elif mode == "conditional_blocking" and result.get("blocking_issues"):
        blocking_issues.extend(result["blocking_issues"])
    advisory_issues.extend(result.get("advisory_issues", []))
    priority_issues.extend(result.get("priority_issues", []))
    all_issue_codes.extend(result["issue_codes"])
    return score


def quality_gate_node(state: FactoryState, repo: Repository, skill_registry=None) -> dict[str, Any]:
    """独立质检节点：运行所有确定性质量检查

    v6.8.5: 将确定性质检从 Editor 中剥离，实现：
    - 确定性检查与 LLM 审校解耦
    - 质量检查结果可复用（Publisher 直接读取）
    - 快速失败：确定性检查不过时跳过 LLM 调用

    输出：
    - quality_gate.pass — 通过/失败
    - quality_gate.score — 确定性检查综合分
    - quality_gate.revision_target — 失败时的返修目标
    - quality_gate.issues — 问题列表
    - quality_gate.diagnostics — 各检查器详细结果
    """
    from datetime import datetime, timezone
    from ...quality.issue_codes import IssueCode, CheckerConfigError, CheckerTemporaryFailure, CheckerTimeoutError

    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard

    _update_run_node(state, repo, "quality_gate")
    _log_node_event(state, repo, "quality_gate", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    llm_mode = state.get("llm_mode", "stub")

    # 加载章节内容
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter:
        error_msg = f"Chapter not found: {project_id}/{chapter_number}"
        _log_node_event(state, repo, "quality_gate", "failed", status="failed", error_message=error_msg)
        return {"error": error_msg, "requires_human": True}

    content = chapter.get("content", "")
    if not content.strip():
        error_msg = "Chapter content is empty"
        _log_node_event(state, repo, "quality_gate", "failed", status="failed", error_message=error_msg)
        return {"error": error_msg, "requires_human": True}

    # 初始化结果
    blocking_issues = []
    priority_issues = []
    advisory_issues = []
    diagnostics = {}
    checks_run = []
    all_issue_codes = []
    score = 100.0  # 从满分开始扣分
    checker_errors = []  # 记录检查器错误
    mandatory_checkers = {"death_penalty", "word_count_gate", "chapter_seam", "continuity_gate"}

    # ── 检查 1: Death Penalty（死刑红线）────────────────────────────
    result, error = _run_quality_checker_safely(
        "death_penalty", lambda: _check_death_penalty(content)
    )
    if error:
        _record_checker_error(error, diagnostics, checker_errors)
    else:
        score = _aggregate_checker_result(
            result, blocking_issues=blocking_issues, priority_issues=priority_issues,
            advisory_issues=advisory_issues, all_issue_codes=all_issue_codes,
            diagnostics=diagnostics, checks_run=checks_run, score=score,
        )

    # ── 检查 2: Word Count Gate（字数门禁）────────────────────────
    result, error = _run_quality_checker_safely(
        "word_count_gate", lambda: _check_word_count(content, repo, project_id, chapter_number)
    )
    if error:
        _record_checker_error(error, diagnostics, checker_errors)
    else:
        score = _aggregate_checker_result(
            result, blocking_issues=blocking_issues, priority_issues=priority_issues,
            advisory_issues=advisory_issues, all_issue_codes=all_issue_codes,
            diagnostics=diagnostics, checks_run=checks_run, score=score,
        )

    # ── 检查 3: Chapter Seam Check（章间衔接）────────────────────
    result, error = _run_quality_checker_safely(
        "chapter_seam", lambda: _check_chapter_seam(repo, project_id, chapter_number, content)
    )
    if error:
        _record_checker_error(error, diagnostics, checker_errors)
    else:
        score = _aggregate_checker_result(
            result, blocking_issues=blocking_issues, priority_issues=priority_issues,
            advisory_issues=advisory_issues, all_issue_codes=all_issue_codes,
            diagnostics=diagnostics, checks_run=checks_run, score=score,
        )

    # ── 检查 4: Continuity Gate（叙事连续性）────────────────────
    result, error = _run_quality_checker_safely(
        "continuity_gate",
        lambda: _check_continuity_gate(repo, project_id, chapter_number, content, title=chapter.get("title")),
    )
    if error:
        _record_checker_error(error, diagnostics, checker_errors)
    else:
        score = _aggregate_checker_result(
            result, blocking_issues=blocking_issues, priority_issues=priority_issues,
            advisory_issues=advisory_issues, all_issue_codes=all_issue_codes,
            diagnostics=diagnostics, checks_run=checks_run, score=score,
        )

    # ── 检查 5: QualityHub.diagnose()（质量诊断聚合）────────────
    if skill_registry:
        result, error = _run_quality_checker_safely(
            "quality_diagnosis",
            lambda: _check_quality_diagnosis(content, repo, project_id, chapter_number, skill_registry),
        )
        if error:
            _record_checker_error(error, diagnostics, checker_errors)
        else:
            score = _aggregate_checker_result(
                result, blocking_issues=blocking_issues, priority_issues=priority_issues,
                advisory_issues=advisory_issues, all_issue_codes=all_issue_codes,
                diagnostics=diagnostics, checks_run=checks_run, score=score,
                mode="advisory_only",
            )

    # ── 检查 6: Core Loop Compliance（核心循环合规，v6.10.5）────
    result, error = _run_quality_checker_safely(
        "core_loop_compliance",
        lambda: _check_core_loop_compliance(repo, project_id, chapter_number, content),
    )
    if error:
        _record_checker_error(error, diagnostics, checker_errors)
    else:
        score = _aggregate_checker_result(
            result, blocking_issues=blocking_issues, priority_issues=priority_issues,
            advisory_issues=advisory_issues, all_issue_codes=all_issue_codes,
            diagnostics=diagnostics, checks_run=checks_run, score=score,
            mode="conditional_blocking",
        )

    # ── 综合判定 ─────────────────────────────────────────────────
    mandatory_checker_errors = [
        item for item in checker_errors
        if item.get("checker") in mandatory_checkers
    ]
    if mandatory_checker_errors:
        blocking_issues.extend([
            f"[门禁降级] 必需检查器 {item.get('checker')} 执行失败：{item.get('message') or item.get('error_type')}"
            for item in mandatory_checker_errors
        ])
        all_issue_codes.append(IssueCode.QUALITY_STYLE_ISSUE)
        diagnostics["checker_health"] = {
            "mandatory_failed": mandatory_checker_errors,
            "advisory_failed": [
                item for item in checker_errors
                if item.get("checker") not in mandatory_checkers
            ],
            "policy": "mandatory_checker_failure_blocks_quality_gate",
        }

    has_blocking = len(blocking_issues) > 0
    passed = not has_blocking

    # 使用结构化错误码确定返修目标
    # v6.10.9: 加载 scene_beats 用于 CORE_LOOP 问题的 beat 设计层路由判断
    scene_beats_for_routing = None
    if not passed:
        try:
            scene_beats_for_routing = repo.get_scene_beats(project_id, chapter_number) or []
        except Exception:
            scene_beats_for_routing = []
    revision_target = _determine_revision_target(all_issue_codes, scene_beats=scene_beats_for_routing) if not passed else None

    # 构建质量门禁结果
    quality_gate_result = {
        "passed": passed,
        "pass": passed,  # v6.8.5: 兼容现有路由逻辑（route_by_review_result 检查 "pass" 字段）
        "score": score,
        "blocking_issues": blocking_issues,
        "priority_issues": priority_issues,
        "advisory_issues": advisory_issues,
        "diagnostics": diagnostics,
        "checks_run": checks_run,
        "issue_codes": [code.value for code in all_issue_codes],
        "revision_target": revision_target,
        "checker_errors": checker_errors,  # v6.8.5: 记录检查器错误
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 记录日志
    if passed:
        _log_node_event(state, repo, "quality_gate", "passed", status="completed")
    else:
        # v6.10.0: quality_gate failure is a routing decision, not an error
        first_issue = str(blocking_issues[0]) if blocking_issues else ""
        detail_suffix = f"，首个阻断: {first_issue[:160]}" if first_issue else ""
        _log_node_event(
            state, repo, "quality_gate", "failed",
            status="warning",
            error_message=f"Quality gate failed: {len(blocking_issues)} blocking issues{detail_suffix}",
        )

    # 记录检查器错误警告
    if checker_errors:
        logger.warning("QualityGate: %d checker errors occurred: %s", len(checker_errors), checker_errors)

    return {
        "quality_gate": quality_gate_result,
    }


def editor_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Editor agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "editor")
    _log_node_event(state, repo, "editor", "started", status="running")
    # v6.10.13: Pass checkpoint_dir if available in state for step-level recovery
    checkpoint_dir = state.get("checkpoint_dir")
    agent = EditorAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry, checkpoint_dir=checkpoint_dir))
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "editor", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "editor", result)
    return result


def memory_curator_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Memory Curator agent to extract story facts from reviewed chapter.

    v5.3.2 closure: In real mode, failure is blocking (requires_human=True).
    In stub mode, failure is non-blocking (log and continue).
    """
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "memory_curator")
    _log_node_event(state, repo, "memory_curator", "started", status="running")
    agent = MemoryCuratorAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    memory_error = _memory_curator_real_mode_error(state, result)
    if memory_error and "error" not in result:
        result["error"] = memory_error
        result["requires_human"] = True
    # Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        llm_mode = state.get("llm_mode", "stub")
        if llm_mode == "real":
            # Real mode: memory extraction failure blocks publish
            logger.error("MemoryCurator failed (real mode): %s", result["error"])
            _log_node_event(state, repo, "memory_curator", "failed", status="failed", error_message=result["error"])
            _finalize_run(state, repo, "failed", result["error"])
            result["requires_human"] = True
        else:
            # Stub mode: non-blocking, log and continue
            logger.warning("MemoryCurator failed (stub mode): %s", result["error"])
            _log_node_event(state, repo, "memory_curator", "failed", status="failed", error_message=result["error"])
            result.pop("error", None)
            result["requires_human"] = False
    else:
        # v6.8.3: Deterministic plot resolution reconciliation. Auto-resolve
        # plots the chapter planned to resolve whose code appears in the prose,
        # independent of the LLM curator's resolve patches.
        try:
            from .reconciliation import reconcile_plot_resolution
            recon = reconcile_plot_resolution(
                repo,
                state.get("project_id", ""),
                int(state.get("chapter_number", 0) or 0),
            )
            resolved_codes = recon.get("resolved") or []
            if resolved_codes:
                log_execution_event(
                    repo, state, "memory_curator", "plot_resolution_reconciled",
                    message=f"确定性回收伏笔 {len(resolved_codes)} 项：{', '.join(resolved_codes)}",
                    agent_id="memory_curator",
                    status="info",
                    payload={"resolved": resolved_codes},
                )
        except Exception:
            logger.debug("plot resolution reconciliation failed (best-effort)", exc_info=True)
        _log_node_event(state, repo, "memory_curator", "completed", status="completed")
    return result


def publisher_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Publish a reviewed chapter.

    v6.7.9: Runs narrative continuity gate before publishing.
    v6.8.5: Reuses quality_gate results from upstream quality_gate_node.
    Blocking continuity issues prevent auto-publish.
    """
    _update_run_node(state, repo, "publisher")
    _log_node_event(state, repo, "publisher", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    chapter = repo.get_chapter(project_id, chapter_number)

    if chapter:
        from ...quality.title_guard import repair_publish_title, validate_publish_title

        title_guard = validate_publish_title(chapter.get("title"), chapter.get("content"))
        if not title_guard.passed:
            title_repair = repair_publish_title(chapter.get("title"), chapter.get("content"), chapter_number)
            if title_repair.repaired and title_repair.title is not None:
                repo.save_chapter_content(
                    project_id,
                    chapter_number,
                    title_repair.content if title_repair.content is not None else chapter.get("content", ""),
                    title=title_repair.title,
                )
                chapter = repo.get_chapter(project_id, chapter_number) or chapter
                title_guard = title_repair.guard or validate_publish_title(chapter.get("title"), chapter.get("content"))
        if not title_guard.passed:
            warning_msg = "发布前标题检查提醒：" + "; ".join(title_guard.issues[:3])
            _log_node_event(
                state, repo, "publisher", "title_warning",
                status="warning", message=warning_msg,
            )
            state["title_guard_warning"] = title_guard.to_dict()

    # v6.8.5: Reuse quality_gate results if available (continuity already checked)
    quality_gate = state.get("quality_gate", {}) or {}
    quality_gate_passed = quality_gate.get("passed", False)

    if not quality_gate_passed:
        # Quality gate failed upstream — should not reach publisher, but safety check
        error_msg = "质量门禁未通过，无法发布"
        _log_node_event(
            state, repo, "publisher", "failed",
            status="failed", error_message=error_msg,
        )
        _finalize_run(state, repo, "failed", error_msg)
        return {"error": error_msg, "requires_human": True}

    # v6.8.5: Check continuity from quality_gate diagnostics (already computed)
    continuity_diag = quality_gate.get("diagnostics", {}).get("continuity_gate", {})
    if continuity_diag.get("should_block") or continuity_diag.get("severity") == "blocking":
        error_msg = (
            "发布前连续性检查未通过：" + "; ".join(continuity_diag.get("issues", [])[:3])
        )
        _log_node_event(
            state, repo, "publisher", "failed",
            status="failed", error_message=error_msg,
        )
        _finalize_run(state, repo, "failed", error_msg)
        return {
            "error": error_msg,
            "requires_human": True,
            "continuity_gate": continuity_diag,
        }

    # Fallback: re-run continuity check if quality_gate diagnostics missing
    if not continuity_diag:
        # v6.8.5: Log warning when quality_gate diagnostics are missing
        logger.warning(
            "Publisher: quality_gate continuity diagnostics missing, falling back to re-check. "
            "This may indicate upstream quality_gate_node did not run or failed. "
            "project_id=%s, chapter_number=%s",
            project_id, chapter_number,
        )
        _log_node_event(
            state, repo, "publisher", "fallback_continuity_check",
            status="warning",
            error_message="质量门禁连续性诊断缺失，回退到重新检查",
        )

        try:
            from ...quality.continuity_gate import evaluate_publish_continuity, SEVERITY_BLOCKING
            continuity_result = evaluate_publish_continuity(repo, project_id, chapter_number)
            if continuity_result.should_block_publish or continuity_result.severity == SEVERITY_BLOCKING:
                error_msg = (
                    "发布前连续性检查未通过：" + "; ".join(continuity_result.issues[:3])
                )
                _log_node_event(
                    state, repo, "publisher", "failed",
                    status="failed", error_message=error_msg,
                )
                _finalize_run(state, repo, "failed", error_msg)
                return {
                    "error": error_msg,
                    "requires_human": True,
                    "continuity_gate": continuity_result.to_dict(),
                }
            if continuity_result.issues:
                _log_node_event(
                    state, repo, "publisher", "completed",
                    status="warning",
                    error_message="发布通过，但存在连续性建议：" + "; ".join(continuity_result.issues[:2]),
                )
        except Exception:
            logger.warning("Publisher: continuity gate failed (best-effort)", exc_info=True)

    ok = repo.publish_chapter(project_id, chapter_number)
    if not ok:
        _log_node_event(state, repo, "publisher", "failed", status="failed", error_message="Failed to publish chapter")
        _finalize_run(state, repo, "failed", "Failed to publish chapter")
        return {"error": "Failed to publish chapter"}

    _log_node_event(state, repo, "publisher", "completed", status="completed")
    return {
        "chapter_status": ChapterStatus.PUBLISHED.value,
        "current_stage": "published",
    }


def awaiting_publish_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """v5.3.0: Real mode - stop at reviewed status, await manual publish confirmation.

    This node is used when llm_mode == "real" to prevent auto-publishing.
    The chapter stays in 'reviewed' status until manually published.
    """
    _update_run_node(state, repo, "awaiting_publish")
    _log_node_event(state, repo, "awaiting_publish", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)

    logger.info(
        "AwaitingPublish: project=%s chapter=%s reviewed, awaiting manual publish",
        project_id, chapter_number,
    )

    # Mark workflow run as completed (review done, but not published)
    _finalize_run(state, repo, "completed")
    _log_node_event(state, repo, "awaiting_publish", "completed", status="completed")

    return {
        "chapter_status": ChapterStatus.REVIEWED.value,
        "current_stage": "reviewed",
        "awaiting_publish": True,
    }


def revision_router_node(state: FactoryState, repo: Repository | None = None) -> dict[str, Any]:
    """Determine where to route revision based on review result.

    v6.2: Added mid-run hydration to protect against state corruption
    during long-running revision flows.
    v6.8.2: Enhanced hydration to include retry_count and force-load _revision_review from DB.
    """
    if repo is not None:
        _update_run_node(state, repo, "revision_router")
        _log_node_event(state, repo, "revision_router", "started", status="running")

        # Mid-run protection: re-hydrate revision state if needed. Return any
        # recovered fields so LangGraph merges them before conditional routing.
        from ..conditions import hydrate_revision_state
        hydrated = hydrate_revision_state(state, repo)
        updates = {
            key: hydrated[key]
            for key in ("quality_gate", "_revision_review", "retry_count")
            if hydrated.get(key) != state.get(key)
        }

        # v6.10.1: QualityGate can route directly to revision_router before
        # Editor writes a review row. Convert deterministic gate findings into
        # the same _revision_review contract Author/Polisher already consume.
        if not updates.get("_revision_review") and not state.get("_revision_review"):
            quality_gate_review = _revision_review_from_quality_gate(state)
            if quality_gate_review:
                updates["_revision_review"] = quality_gate_review

        quality_gate_retry_updates = _prepare_quality_gate_revision_retry(state, repo)
        updates.update(quality_gate_retry_updates)

        # v6.8.2: Force-load _revision_review from DB if still missing after hydration
        if not updates.get("_revision_review"):
            project_id = state.get("project_id")
            chapter_number = state.get("chapter_number")
            if project_id and chapter_number:
                try:
                    chapter = repo.get_chapter(project_id, chapter_number)
                    if chapter:
                        review = repo.get_latest_review(project_id, chapter["id"])
                        if review:
                            updates["_revision_review"] = {
                                "review_id": review.get("id"),
                                "score": review.get("score"),
                                "revision_target": review.get("revision_target"),
                                "issues": review.get("issues") or [],
                                "suggestions": review.get("suggestions") or [],
                            }
                            logger.info(
                                "revision_router: force-loaded _revision_review from DB for %s ch%d (review_id=%s)",
                                project_id, chapter_number, review.get("id"),
                            )
                except Exception:
                    logger.warning(
                        "revision_router: failed to force-load _revision_review for %s ch%d",
                        project_id, chapter_number,
                        exc_info=True,
                    )

        _log_node_event(state, repo, "revision_router", "completed", status="completed")
        return updates
    # Pass through — routing is handled by conditional edges
    return {}


def _prepare_quality_gate_revision_retry(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Mark a failed deterministic QualityGate as a counted revision retry."""
    gate = state.get("quality_gate") or {}
    if not _is_deterministic_quality_gate_failure(gate):
        return {}
    gate_marker = gate.get("timestamp") or gate.get("message") or str(gate.get("blocking_issues", [])[:1])
    if state.get("_quality_gate_revision_recorded_for") == gate_marker:
        return {}

    project_id = state.get("project_id")
    chapter_number = state.get("chapter_number")
    if not project_id or not chapter_number:
        return {}

    retry_count = repo.get_chapter_retry_count(project_id, int(chapter_number))
    max_retries = state.get("max_retries", 3)
    if retry_count >= max_retries:
        return {
            "requires_human": True,
            "retry_count": retry_count,
            "chapter_status": ChapterStatus.BLOCKING.value,
            "error": (
                f"QualityGate 阻断已达到最大返修次数 "
                f"({retry_count}/{max_retries})，需要人工检查。"
            ),
        }

    revision_target = revision_target_from_state(state)
    current_status = repo.get_chapter_status(project_id, int(chapter_number))
    if current_status not in (
        ChapterStatus.BLOCKING.value,
        ChapterStatus.PUBLISHED.value,
        ChapterStatus.REVIEWED.value,
    ):
        repo.update_chapter_status(project_id, int(chapter_number), ChapterStatus.REVISION.value)

    task_id = repo.start_task(
        project_id,
        int(chapter_number),
        "revise",
        revision_target,
        workflow_run_id=state.get("workflow_run_id"),
    )
    repo.complete_task(task_id, success=True)

    return {
        "chapter_status": ChapterStatus.REVISION.value,
        "current_stage": "revision",
        "retry_count": retry_count + 1,
        "_quality_gate_revision_recorded_for": gate_marker,
    }


def _is_deterministic_quality_gate_failure(gate: dict[str, Any]) -> bool:
    return (
        bool(gate)
        and (gate.get("passed") is False or gate.get("pass") is False)
        and bool(gate.get("blocking_issues"))
        and bool(gate.get("checks_run"))
    )


def _revision_review_from_quality_gate(state: FactoryState) -> dict[str, Any] | None:
    """Build revision feedback from a failed deterministic QualityGate result."""
    from ...agent_runtime.revision_context import revision_review_from_quality_gate

    return revision_review_from_quality_gate(
        state.get("quality_gate") or {},
        workflow_run_id=state.get("workflow_run_id"),
    )


def human_review_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Handle blocking/human intervention scenarios."""
    _update_run_node(state, repo, "human_review")
    _log_node_event(state, repo, "human_review", "started", status="running")
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    gate = state.get("quality_gate", {}) or {}
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    error = state.get("error")
    # v6.6.21: Distinguish human_review severity by root cause
    is_quality_gate_maxed = False
    is_preexisting_block = False
    if not error and gate.get("pass") is False:
        score = gate.get("score")
        target = revision_target_from_state(state)
        is_quality_gate_maxed = True
        # P1: Include quality gate details (word count, etc.) in blocking error
        error = (
            f"章节审核未通过，已达到最大返修次数 "
            f"({retry_count}/{max_retries})，建议人工检查。"
            f"退回目标: {target}"
        )
        if score is not None:
            error += f"，评分: {score}"
        if gate.get("word_count_fail"):
            actual_wc = gate.get("actual_word_count")
            word_target = gate.get("word_target")
            if actual_wc is not None and word_target is not None:
                error += f"，该次失败字数: {actual_wc} (目标 {word_target})"
        if gate.get("scene_beat_coverage_fail"):
            error += "，该次失败原因: 正文未覆盖完整场景 beat / 章末钩子"

        # v6.10.7: Surface story_facts violation details so users can judge
        # whether the block is a genuine contradiction or a false positive.
        sfc = state.get("story_facts_compliance") or {}
        if sfc.get("violations"):
            violation_lines = []
            for v in sfc["violations"]:
                fact = v.get("fact_statement", "")[:60]
                text = v.get("violation_text", "")[:80]
                sev = v.get("severity", "warning")
                violation_lines.append(f"  • [{sev}] {fact}: {text}")
            if violation_lines:
                error += "\n\n事实一致性详情:\n" + "\n".join(violation_lines)

    if not error and state.get("chapter_status") == ChapterStatus.BLOCKING.value:
        is_preexisting_block = True
        error = "章节已处于阻塞状态，请先解除阻塞后再重新执行工作流。"

    if project_id and chapter_number:
        current_status = repo.get_chapter_status(project_id, chapter_number)
        if current_status not in (ChapterStatus.PUBLISHED.value, ChapterStatus.REVIEWED.value):
            repo.update_chapter_status(project_id, chapter_number, ChapterStatus.BLOCKING.value)

    _finalize_run(state, repo, "blocked", error=error)
    # v6.6.21: human_review severity mapping
    # - quality gate maxed / pre-existing block -> expected, needs human intervention
    # - unexpected system error -> genuinely failed
    is_unexpected_error = error and not is_quality_gate_maxed and not is_preexisting_block
    if is_unexpected_error:
        # Unexpected system error: genuinely failed
        _log_node_event(state, repo, "human_review", "failed", status="failed", error_message=error)
        logger.error(
            "Human review triggered by unexpected error: project=%s chapter=%s error=%s",
            project_id, chapter_number, error,
        )
    else:
        # Expected human intervention (quality gate maxed / pre-existing block)
        _log_node_event(state, repo, "human_review", "completed", status="warning", error_message=error)
        logger.warning(
            "Human intervention required: project=%s chapter=%s",
            project_id, chapter_number,
        )
    return {
        "requires_human": True,
        "chapter_status": ChapterStatus.BLOCKING.value,
        "error": error,
    }


def archive_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Archive after publishing. Marks workflow run as completed."""
    _update_run_node(state, repo, "archive")
    _log_node_event(state, repo, "archive", "started", status="running")
    # P1 fix: Clear error_message when marking as completed
    _finalize_run(state, repo, "completed", error=None)
    _log_node_event(state, repo, "archive", "completed", status="completed")
    logger.info(
        "Archive: project=%s chapter=%s published",
        state.get("project_id"), state.get("chapter_number"),
    )
    return {}

def brief_validation_node(state: FactoryState) -> dict:
    """Validate chapter brief from planner output.
    
    Checks Tier 1 fields. If missing, routes back to planner.
    Fills missing Tier 2 fields with genre profile defaults.
    """
    logger = logging.getLogger(__name__)
    
    # Get planner output from state
    planner_output = state.get("planner_output")
    if not planner_output:
        logger.warning("No planner output found in state")
        return {"status": "revision", "revision_reason": "missing_planner_output"}
    
    # Extract chapter brief
    chapter_brief = planner_output.get("chapter_brief", {})
    if not chapter_brief:
        logger.warning("No chapter_brief found in planner output")
        return {"status": "revision", "revision_reason": "missing_chapter_brief"}
    
    # Get genre profile from project context
    project_id = state.get("project_id")
    genre_profile = None
    if project_id:
        try:
            from ...config.genre_profile_loader import get_default_genre_profile
            genre_profile = get_default_genre_profile()
        except Exception as e:
            logger.warning(f"Failed to load genre profile: {e}")
    
    # Validate Tier 1 fields
    is_valid, missing_fields = validate_chapter_brief(chapter_brief)
    
    if not is_valid:
        logger.warning(f"Chapter brief missing Tier 1 fields: {missing_fields}")
        return {
            "status": "revision",
            "revision_reason": f"missing_tier1_fields: {', '.join(missing_fields)}",
            "missing_tier1_fields": missing_fields,
        }
    
    # Fill missing Tier 2 fields
    if genre_profile:
        filled_brief = fill_missing_tier2_fields(chapter_brief, genre_profile)
    else:
        filled_brief = chapter_brief
    
    # Update state with validated brief
    return {
        "chapter_brief": filled_brief,
        "brief_validated": True,
    }


# ── Rhythm Budget Preflight Node (v6.9.0) ────────────────────────────────


def rhythm_budget_preflight_node(state: FactoryState, repo: Repository) -> dict:
    """Rhythm budget preflight check before screenwriter.

    Runs deterministic rhythm checks on the chapter brief and previous chapters.
    If blocking issues detected, routes back to planner for brief revision.
    """
    logger = logging.getLogger(__name__)

    project_id = state.get("project_id")
    chapter_number = state.get("chapter_number", 0)

    if not project_id or not chapter_number:
        logger.warning("Rhythm budget preflight: missing project_id or chapter_number")
        return {"rhythm_budget_passed": True}  # Allow to proceed

    # Get chapter brief
    chapter_brief = state.get("chapter_brief", {})
    if not chapter_brief:
        logger.warning("Rhythm budget preflight: no chapter brief found")
        return {"rhythm_budget_passed": True}  # Allow to proceed

    # Get previous chapters for rhythm analysis
    try:
        previous_chapters = []
        for i in range(max(1, chapter_number - 10), chapter_number):
            chapter = repo.get_chapter(project_id, i)
            if chapter:
                previous_chapters.append(chapter)
    except Exception as e:
        logger.warning(f"Failed to load previous chapters: {e}")
        previous_chapters = []

    # Get genre contract for custom thresholds
    genre_contract = None
    try:
        contract_data = repo.get_creative_contract(project_id, "genre_contract")
        if contract_data:
            import json
            genre_contract = json.loads(contract_data.get("contract_data", "{}"))
    except Exception:
        logger.warning("rhythm_budget_preflight: failed to load genre_contract", exc_info=True)

    # Run deterministic rhythm budget evaluation
    from ...quality.rhythm_budget import evaluate_deterministic
    result = evaluate_deterministic(
        chapters=previous_chapters,
        brief=chapter_brief,
        genre_contract=genre_contract,
    )

    # Apply genre-specific rules
    if genre_contract:
        from ...quality.rhythm_budget import apply_genre_specific_rules
        result = apply_genre_specific_rules(result, genre_contract)

    if not result.passed:
        logger.warning(f"Rhythm budget BLOCKED: {result.blocking_reasons}")
        return {
            "rhythm_budget_passed": False,
            "rhythm_budget_result": result.model_dump(),
            "revision_reason": f"rhythm_budget_blocked: {'; '.join(result.blocking_reasons)}",
        }

    if result.warnings:
        logger.info(f"Rhythm budget warnings: {result.warnings}")

    return {
        "rhythm_budget_passed": True,
        "rhythm_budget_result": result.model_dump(),
    }


# ── Creative Ledger Curator Node (v6.9.0) ────────────────────────────────


def creative_ledger_curator_node(state: FactoryState, repo: Repository) -> dict:
    """Update creative ledgers after chapter passes review.

    Runs AFTER publisher (or awaiting_publish) to record chapter
    contributions to ongoing narrative threads.
    """
    _logger = logging.getLogger(__name__)

    project_id = state.get("project_id")
    chapter_number = state.get("chapter_number", 0)

    if not project_id or not chapter_number:
        _logger.warning("CreativeLedgerCurator: missing identifiers")
        return {"ledger_update_result": {"status": "skipped"}}

    # Get chapter content and review data
    chapter = state.get("chapter", {})
    content = chapter.get("content", "") if isinstance(chapter, dict) else ""
    review_data = state.get("quality_gate", {})

    # Create curator instance
    from ...agents.creative_ledger_curator import CreativeLedgerCurator
    curator = CreativeLedgerCurator(repo=repo, llm=None)  # LLM not needed for stub mode

    # Update ledgers (synchronous call, via the public API)
    try:
        result = curator.update_for_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            content=content,
            review_data=review_data,
            workflow_run_id=state.get("workflow_run_id"),
        )
    except Exception as e:
        _logger.warning(f"CreativeLedgerCurator failed: {e}")
        result = {"ledger_update_result": {"status": "error", "error": str(e)}}

    return result
