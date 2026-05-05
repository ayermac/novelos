"""Run detail API endpoints."""

from __future__ import annotations

import json
import time
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class RunRecoveryResetRequest(BaseModel):
    """Run recovery reset request."""

    confirm: bool = False


class RunRecoveryMarkStuckRequest(BaseModel):
    """Mark a confirmed stuck run as blocked."""

    confirm: bool = False


# Agent step configuration
AGENT_STEPS = [
    {"key": "screenwriter", "label": "编剧", "description": "规划章节场景和情节"},
    {"key": "author", "label": "执笔", "description": "撰写章节正文"},
    {"key": "polisher", "label": "润色", "description": "优化文字表达"},
    {"key": "editor", "label": "审核", "description": "检查内容质量"},
    {"key": "publish", "label": "发布", "description": "发布章节内容"},
]

# Status to agent mapping (reverse of STATUS_ROUTE)
STATUS_TO_AGENT = {
    "planned": None,  # Initial state
    "scripted": "screenwriter",
    "drafted": "author",
    "polished": "polisher",
    "reviewed": "editor",
    "published": "publish",
}


def _generate_stub_artifacts(step_key: str, chapter_number: int) -> dict | None:
    """Generate mock artifacts for stub mode.

    Different chapters produce different content using chapter_number as seed.
    """
    # Scene templates for different chapters
    scene_templates = [
        ["修炼突破", "危机降临", "转机出现"],
        ["故人重逢", "恩怨化解", "新的征程"],
        ["探寻秘境", "意外收获", "暗流涌动"],
        ["强敌来袭", "背水一战", "绝地反击"],
        ["真相揭露", "命运抉择", "风云再起"],
    ]

    # Character names for variety
    characters = ["萧炎", "林动", "牧尘", "唐三", "叶凡"]
    char = characters[chapter_number % len(characters)]
    scenes = scene_templates[chapter_number % len(scene_templates)]

    base_word_count = 2800 + (chapter_number % 5) * 200  # 2800-3600 range

    if step_key == "screenwriter":
        return {
            "summary": f"本章规划了 {len(scenes)} 个场景：{char}{scenes[0]}、{scenes[1]}、{scenes[2]}",
            "scenes": len(scenes),
            "word_count_hint": f"{base_word_count}-{base_word_count + 400}",
            "output_preview": f"场景一：{char}{scenes[0]}…\n场景二：{scenes[1]}…\n场景三：{scenes[2]}…"
        }
    elif step_key == "author":
        draft_words = base_word_count + (chapter_number % 3) * 100
        return {
            "summary": f"基于编剧大纲完成正文，初稿 {draft_words} 字",
            "draft_word_count": draft_words,
            "output_preview": f"第{chapter_number}章开篇，{char}正面临前所未有的挑战…"
        }
    elif step_key == "polisher":
        polished_words = base_word_count + 150 + (chapter_number % 3) * 50
        changes = 8 + (chapter_number % 8)
        return {
            "summary": f"润色后 {polished_words} 字，优化了 {changes} 处表达",
            "polished_word_count": polished_words,
            "changes": changes,
            "output_preview": f"主要修改：1) 开篇节奏调整；2) 对话细节润色；3) 结尾情感升华"
        }
    elif step_key == "editor":
        score = 80 + (chapter_number % 15)
        return {
            "summary": f"审核通过，质量评分 {score}/100",
            "quality_score": score,
            "issues_found": 0,
            "output_preview": "角色一致性：✓\n情节连贯性：✓\n风格匹配度：✓"
        }
    elif step_key == "publish":
        final_words = base_word_count + 150 + (chapter_number % 3) * 50
        return {
            "summary": f"章节已发布，最终字数 {final_words}",
            "final_word_count": final_words,
            "output_preview": f"第 {chapter_number} 章已发布到项目"
        }

    return None


@router.get("/runs/{run_id}")
async def get_run_detail(request: Request, run_id: str) -> EnvelopeResponse:
    """Get detailed information about a workflow run.

    Returns run metadata and step timeline.
    """
    from ..deps import get_repo, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        # Get workflow run
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?",
                (run_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        run_data = dict(row)

        # Get project info
        project = repo.get_project(run_data["project_id"])
        project_name = project.get("name", "") if project else ""

        # Get chapter info
        chapter = repo.get_chapter(run_data["project_id"], run_data["chapter_number"])
        error_message = _resolve_run_error_message(repo, run_data, chapter)
        if error_message and not run_data.get("error_message"):
            run_data = dict(run_data)
            run_data["error_message"] = error_message

        # Build steps timeline (with observability data from task_status and agent_artifacts)
        steps = _build_steps_timeline(run_data, chapter, llm_mode, repo=repo)

        return envelope_response({
            "run_id": run_id,
            "project_id": run_data["project_id"],
            "project_name": project_name,
            "chapter_number": run_data["chapter_number"],
            "workflow_status": run_data.get("status", "unknown"),
            "chapter_status": chapter.get("status", "unknown") if chapter else "unknown",
            "llm_mode": llm_mode,
            "started_at": run_data.get("started_at", ""),
            "completed_at": run_data.get("completed_at", ""),
            "error_message": error_message,
            "steps": steps,
            # v5.2: Token usage statistics
            "prompt_tokens": run_data.get("prompt_tokens", 0),
            "completion_tokens": run_data.get("completion_tokens", 0),
            "total_tokens": run_data.get("total_tokens", 0),
            "duration_ms": run_data.get("duration_ms", 0),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行详情失败: {str(e)}")


@router.get("/runs/{run_id}/recovery")
async def get_run_recovery(request: Request, run_id: str) -> EnvelopeResponse:
    """Return safe recovery options for a workflow run."""
    from ..deps import get_repo, get_settings

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        run_data = _get_run_by_id(repo, run_id)
        if not run_data:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        return envelope_response(_build_recovery_state(
            repo,
            run_data,
            max_retries=settings.quality_gate.max_retries,
            timeout_minutes=settings.workflow.task_timeout_minutes,
        ))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行恢复状态失败: {str(e)}")


@router.post("/runs/{run_id}/recovery/reset")
async def reset_run_chapter(
    request: Request,
    run_id: str,
    body: RunRecoveryResetRequest,
) -> EnvelopeResponse:
    """Reset a blocked/revision chapter from a run detail page.

    This is a run-scoped facade over chapter reset. It never deletes content or
    artifacts; it only moves the chapter back to planned, inserts an audit task,
    and clears stale LangGraph checkpoints.
    """
    from ..deps import get_repo, get_settings
    from ...workflow.checkpoint import delete_checkpoint_thread

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认恢复操作")

        repo = get_repo(request)
        settings = get_settings(request)
        run_data = _get_run_by_id(repo, run_id)
        if not run_data:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        project_id = run_data["project_id"]
        chapter_number = run_data["chapter_number"]
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        current_status = chapter.get("status", "")
        if current_status not in ("blocking", "revision"):
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'blocking' 或 'revision' 状态可恢复",
                details={"current_status": current_status},
            )

        retry_count_before = repo.get_chapter_retry_count(project_id, chapter_number)
        checkpoint_before = _checkpoint_exists(repo, project_id, chapter_number)

        reset = repo.reset_chapter(project_id, chapter_number, workflow_run_id=run_id)
        if not reset:
            return error_response("RESET_FAILED", "恢复章节失败")

        checkpoint_cleared = delete_checkpoint_thread(repo.db_path, project_id, chapter_number)
        retry_count_after = repo.get_chapter_retry_count(project_id, chapter_number)
        recovery = _build_recovery_state(
            repo,
            run_data,
            max_retries=settings.quality_gate.max_retries,
            timeout_minutes=settings.workflow.task_timeout_minutes,
        )

        return envelope_response({
            "recovered": True,
            "run_id": run_id,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "previous_status": current_status,
            "new_status": "planned",
            "retry_count_before": retry_count_before,
            "retry_count_after": retry_count_after,
            "retries_cleared": max(0, retry_count_before - retry_count_after),
            "checkpoint_before": checkpoint_before,
            "checkpoint_cleared": checkpoint_cleared,
            "recovery": recovery,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"恢复运行失败: {str(e)}")


@router.post("/runs/{run_id}/recovery/mark-stuck")
async def mark_stuck_run(
    request: Request,
    run_id: str,
    body: RunRecoveryMarkStuckRequest,
) -> EnvelopeResponse:
    """Mark a confirmed stuck running run as blocked.

    This does not delete content or artifacts. It converts a stale running run
    into an explicit blocked state and moves the chapter to blocking so the
    normal recovery reset path can take over.
    """
    from ..deps import get_repo, get_settings

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认标记卡住运行")

        repo = get_repo(request)
        settings = get_settings(request)
        timeout_minutes = settings.workflow.task_timeout_minutes
        run_data = _get_run_by_id(repo, run_id)
        if not run_data:
            return error_response("RUN_NOT_FOUND", f"运行记录 '{run_id}' 不存在")

        recovery = _build_recovery_state(
            repo,
            run_data,
            max_retries=settings.quality_gate.max_retries,
            timeout_minutes=timeout_minutes,
        )
        if not recovery.get("stuck", False):
            return error_response(
                "RUN_NOT_STUCK",
                "运行尚未超过卡住阈值，不能标记为阻塞",
                details={
                    "elapsed_minutes": recovery.get("elapsed_minutes"),
                    "timeout_minutes": timeout_minutes,
                },
            )

        project_id = run_data["project_id"]
        chapter_number = run_data["chapter_number"]
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")
        current_status = chapter.get("status", "") if chapter else ""
        if current_status in ("reviewed", "published"):
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，不能从卡住运行标记为阻塞",
                details={"current_status": current_status},
            )

        message = (
            f"运行疑似卡住：超过 {timeout_minutes} 分钟仍为 running。"
            f" current_node={run_data.get('current_node') or '-'}"
        )

        repo.update_workflow_run(run_id, status="blocked", error_message=message)
        closed_running_tasks = _fail_running_tasks_for_run(
            repo,
            project_id,
            chapter_number,
            workflow_run_id=run_id,
            message=message,
        )
        _set_chapter_status_unchecked(repo, project_id, chapter_number, "blocking")
        _insert_recovery_audit(
            repo,
            project_id,
            chapter_number,
            workflow_run_id=run_id,
            message=message,
            task_type="recover",
            agent_id="system",
        )

        refreshed = _get_run_by_id(repo, run_id) or run_data
        return envelope_response({
            "marked": True,
            "run_id": run_id,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "previous_chapter_status": current_status,
            "new_chapter_status": "blocking",
            "workflow_status": "blocked",
            "message": message,
            "closed_running_tasks": closed_running_tasks,
            "recovery": _build_recovery_state(
                repo,
                refreshed,
                max_retries=settings.quality_gate.max_retries,
                timeout_minutes=timeout_minutes,
            ),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"标记卡住运行失败: {str(e)}")


def _get_run_by_id(repo, run_id: str) -> dict | None:
    """Fetch workflow_run by id."""
    conn = repo._conn()
    try:
        row = conn.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _checkpoint_exists(repo, project_id: str, chapter_number: int) -> bool:
    """Best-effort checkpoint existence probe."""
    try:
        from ...workflow.checkpoint import checkpoint_thread_exists

        return checkpoint_thread_exists(repo.db_path, project_id, chapter_number)
    except Exception:
        return False


def _build_recovery_state(
    repo,
    run_data: dict,
    max_retries: int = 3,
    timeout_minutes: int = 30,
) -> dict:
    """Build user-facing recovery state for a run."""
    project_id = run_data["project_id"]
    chapter_number = run_data["chapter_number"]
    chapter = repo.get_chapter(project_id, chapter_number)
    chapter_status = chapter.get("status", "unknown") if chapter else "unknown"
    retry_count = repo.get_chapter_retry_count(project_id, chapter_number)
    stuck_info = _detect_stuck_run(repo, run_data, timeout_minutes)
    can_mark_stuck = bool(stuck_info.get("stuck", False)) and chapter_status not in (
        "reviewed",
        "published",
        "unknown",
    )
    can_reset = chapter_status in ("blocking", "revision")
    reason = None
    if not chapter:
        reason = "章节不存在"
    elif can_reset:
        reason = "可清除阻塞/返修状态并回到 planned，重新开始工作流。"
    else:
        reason = f"章节状态为 '{chapter_status}'，无需或不可执行恢复。"

    return {
        "run_id": run_data.get("id"),
        "project_id": project_id,
        "chapter_number": chapter_number,
        "workflow_status": run_data.get("status", "unknown"),
        "chapter_status": chapter_status,
        "error_message": _resolve_run_error_message(repo, run_data, chapter),
        "retry_count": retry_count,
        "max_retries": max_retries,
        "timeout_minutes": timeout_minutes,
        "elapsed_minutes": stuck_info.get("elapsed_minutes"),
        "stuck": stuck_info.get("stuck", False),
        "stuck_reason": stuck_info.get("reason"),
        "running_tasks": stuck_info.get("running_tasks", []),
        "checkpoint_exists": _checkpoint_exists(repo, project_id, chapter_number),
        "can_reset": can_reset,
        "actions": {
            "reset_to_planned": {
                "enabled": can_reset,
                "label": "清除阻塞并回到 planned",
                "reason": reason,
            },
            "mark_stuck_blocked": {
                "enabled": can_mark_stuck,
                "label": "标记为阻塞",
                "reason": (
                    stuck_info.get("reason")
                    if can_mark_stuck
                    else "运行未达到卡住阈值或章节状态不可标记。"
                ),
            },
        },
    }


def _parse_db_datetime(value: str | None) -> datetime | None:
    """Parse DB datetime strings written as UTC+8 wall-clock time."""
    if not value:
        return None
    try:
        normalized = value.replace("T", " ").replace("Z", "")
        return datetime.fromisoformat(normalized).replace(tzinfo=timezone(timedelta(hours=8)))
    except Exception:
        return None


def _elapsed_minutes_since(value: str | None) -> float | None:
    started = _parse_db_datetime(value)
    if not started:
        return None
    now = datetime.now(tz=timezone(timedelta(hours=8)))
    return max(0.0, (now - started).total_seconds() / 60)


def _detect_stuck_run(repo, run_data: dict, timeout_minutes: int) -> dict:
    """Detect whether a workflow run or its running tasks are stale."""
    if run_data.get("status") != "running":
        return {"stuck": False, "reason": None, "running_tasks": []}

    elapsed = _elapsed_minutes_since(run_data.get("started_at"))
    run_stuck = elapsed is not None and elapsed >= timeout_minutes

    project_id = run_data.get("project_id")
    chapter_number = run_data.get("chapter_number")
    running_tasks = []
    task_stuck = False
    try:
        conn = repo._conn()
        try:
            rows = conn.execute(
                "SELECT id, task_type, agent_id, started_at FROM task_status "
                "WHERE project_id=? AND chapter_number=? AND status='running' "
                "AND workflow_run_id=? "
                "ORDER BY started_at DESC",
                (project_id, chapter_number, run_data.get("id")),
            ).fetchall()
            for row in rows:
                task_elapsed = _elapsed_minutes_since(row["started_at"])
                task = {
                    "id": row["id"],
                    "task_type": row["task_type"],
                    "agent_id": row["agent_id"],
                    "started_at": row["started_at"],
                    "elapsed_minutes": task_elapsed,
                    "stuck": task_elapsed is not None and task_elapsed >= timeout_minutes,
                }
                if task["stuck"]:
                    task_stuck = True
                running_tasks.append(task)
        finally:
            conn.close()
    except Exception:
        running_tasks = []

    stuck = run_stuck or task_stuck
    reason = None
    if stuck:
        reason = (
            f"运行已超过 {timeout_minutes} 分钟仍处于 running，"
            "可先标记为阻塞再执行恢复。"
        )
    return {
        "stuck": stuck,
        "reason": reason,
        "elapsed_minutes": elapsed,
        "running_tasks": running_tasks,
    }


def _set_chapter_status_unchecked(
    repo,
    project_id: str,
    chapter_number: int,
    status: str,
) -> None:
    """Set chapter status for system recovery audit paths."""
    conn = repo._conn()
    try:
        conn.execute(
            "UPDATE chapters SET status=?, updated_at=datetime('now','+8 hours') "
            "WHERE project_id=? AND chapter_number=?",
            (status, project_id, chapter_number),
        )
        conn.commit()
    finally:
        conn.close()


def _fail_running_tasks_for_run(
    repo,
    project_id: str,
    chapter_number: int,
    workflow_run_id: str,
    message: str,
) -> int:
    """Close run-scoped running task rows when a run is marked stuck."""
    conn = repo._conn()
    try:
        cursor = conn.execute(
            "UPDATE task_status SET status='failed', completed_at=datetime('now','+8 hours'), "
            "error_message=? "
            "WHERE project_id=? AND chapter_number=? AND workflow_run_id=? "
            "AND status='running'",
            (message, project_id, chapter_number, workflow_run_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def _insert_recovery_audit(
    repo,
    project_id: str,
    chapter_number: int,
    workflow_run_id: str,
    message: str,
    task_type: str,
    agent_id: str,
) -> None:
    """Insert a run-scoped recovery audit row."""
    conn = repo._conn()
    try:
        conn.execute(
            "INSERT INTO task_status "
            "(project_id, chapter_number, task_type, agent_id, status, "
            "started_at, completed_at, error_message, workflow_run_id) "
            "VALUES (?, ?, ?, ?, 'completed', datetime('now','+8 hours'), "
            "datetime('now','+8 hours'), ?, ?)",
            (project_id, chapter_number, task_type, agent_id, message, workflow_run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _resolve_run_error_message(repo, run_data: dict, chapter: dict | None) -> str | None:
    """Resolve a user-facing error for historical blocked runs with empty errors."""
    error_message = run_data.get("error_message")
    if error_message:
        return error_message

    if run_data.get("status") != "blocked":
        return None

    chapter_status = chapter.get("status") if chapter else None
    if chapter_status != "blocking":
        return None

    project_id = run_data.get("project_id", "")
    chapter_number = run_data.get("chapter_number", 0)
    started_at = run_data.get("started_at", "")

    previous_error = None
    try:
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT error_message FROM workflow_runs "
                "WHERE project_id=? AND chapter_number=? "
                "AND error_message IS NOT NULL AND error_message != '' "
                "AND started_at <= ? AND id != ? "
                "ORDER BY started_at DESC LIMIT 1",
                (project_id, chapter_number, started_at, run_data.get("id")),
            ).fetchone()
            if row:
                previous_error = row["error_message"]
        finally:
            conn.close()
    except Exception:
        previous_error = None

    message = "章节已处于阻塞状态，请先解除阻塞后再重新执行工作流。"
    if previous_error:
        message += f" 历史阻塞原因: {previous_error}"
    return message


def _build_steps_timeline(
    run_data: dict,
    chapter: dict | None,
    llm_mode: str,
    repo=None,
) -> list[dict]:
    """Build steps timeline from run data and chapter status.

    Derives step status from:
    1. workflow_runs.current_node (last running agent)
    2. chapter.status (final status)
    3. STATUS_ROUTE (expected flow)
    4. task_status table (per-agent error messages)
    5. agent_artifacts table (per-agent artifact summaries)
    """
    workflow_status = run_data.get("status", "unknown")
    current_node = run_data.get("current_node")
    error_message = run_data.get("error_message")
    chapter_number = run_data.get("chapter_number", 1)
    project_id = run_data.get("project_id", "")

    # Determine final chapter status
    final_status = chapter.get("status", "planned") if chapter else "planned"

    # Fetch task_status for per-agent error info
    # P1: Prefer run-isolated rows; fallback to chapter-level for legacy data.
    task_errors: dict[str, str] = {}
    task_errors_legacy: dict[str, str] = {}
    if repo:
        try:
            conn = repo._conn()
            try:
                run_id = run_data.get("id")
                # Try run-isolated query first
                if run_id:
                    rows = conn.execute(
                        "SELECT agent_id, status, error_message FROM task_status "
                        "WHERE project_id=? AND chapter_number=? AND status='failed' "
                        "AND workflow_run_id=?",
                        (project_id, chapter_number, run_id),
                    ).fetchall()
                    for r in rows:
                        agent_id = r["agent_id"]
                        if r["error_message"]:
                            task_errors[agent_id] = r["error_message"]
                # Legacy fallback: rows without workflow_run_id
                legacy_rows = conn.execute(
                    "SELECT agent_id, status, error_message FROM task_status "
                    "WHERE project_id=? AND chapter_number=? AND status='failed' "
                    "AND workflow_run_id IS NULL",
                    (project_id, chapter_number),
                ).fetchall()
                for r in legacy_rows:
                    agent_id = r["agent_id"]
                    if r["error_message"]:
                        task_errors_legacy[agent_id] = r["error_message"]
            finally:
                conn.close()
        except Exception:
            pass  # Graceful degradation

    # Fetch agent_artifacts for per-agent artifact summaries
    # P1 fix: Prefer run-level isolation; fallback to chapter-level for legacy data
    agent_artifacts: dict[str, list[dict]] = {}
    artifacts_source = "run"  # 'run' | 'chapter_fallback'
    if repo:
        try:
            run_id = run_data.get("id")
            if run_id:
                artifacts = repo.get_artifacts_for_chapter(
                    project_id, chapter_number, workflow_run_id=run_id
                )
                if not artifacts:
                    # Fallback: legacy artifacts without run_id
                    artifacts = repo.get_artifacts_for_chapter(project_id, chapter_number)
                    artifacts_source = "chapter_fallback"
            else:
                artifacts = repo.get_artifacts_for_chapter(project_id, chapter_number)
                artifacts_source = "chapter_fallback"
            for a in artifacts:
                aid = a.get("agent_id", "")
                if aid not in agent_artifacts:
                    agent_artifacts[aid] = []
                agent_artifacts[aid].append(a)
        except Exception:
            pass  # Graceful degradation

    # Determine which steps completed
    # Based on STATUS_ROUTE: planned -> screenwriter -> author -> polisher -> editor -> publish
    completed_agents = []
    if final_status in ("scripted", "drafted", "polished", "reviewed", "published"):
        completed_agents.append("screenwriter")
    if final_status in ("drafted", "polished", "reviewed", "published"):
        completed_agents.append("author")
    if final_status in ("polished", "reviewed", "published"):
        completed_agents.append("polisher")
    if final_status in ("reviewed", "published"):
        completed_agents.append("editor")
    if final_status == "published":
        completed_agents.append("publish")
    for key in ("screenwriter", "author", "polisher", "editor", "publish"):
        if key in agent_artifacts and key not in completed_agents:
            completed_agents.append(key)

    blocked_agent = current_node
    if workflow_status == "blocked" and current_node == "human_review":
        if "editor" in agent_artifacts or final_status in ("blocking", "revision"):
            blocked_agent = "editor"
        elif "polisher" in agent_artifacts:
            blocked_agent = "polisher"
        elif "author" in agent_artifacts:
            blocked_agent = "author"
        elif "screenwriter" in agent_artifacts:
            blocked_agent = "screenwriter"

    # Build steps
    steps = []
    for step_config in AGENT_STEPS:
        key = step_config["key"]
        is_completed = key in completed_agents
        is_running = (current_node == key) and workflow_status == "running"
        is_failed = (current_node == key) and workflow_status == "failed"
        is_blocked = (blocked_agent == key) and workflow_status == "blocked"

        if is_failed:
            step_status = "failed"
        elif is_blocked:
            step_status = "blocked"
        elif is_running:
            step_status = "running"
        elif is_completed:
            step_status = "completed"
        else:
            step_status = "pending"

        step = {
            "key": key,
            "label": step_config["label"],
            "description": step_config["description"],
            "status": step_status,
            "agent_id": key,
        }

        # Add error message for failed step
        if (is_failed or is_blocked) and error_message:
            step["error_message"] = error_message
        elif key in task_errors:
            step["error_message"] = task_errors[key]
        elif key in task_errors_legacy:
            step["error_message"] = task_errors_legacy[key]
            step["error_is_legacy"] = True

        # Add artifacts for completed steps
        if is_completed and llm_mode == "stub":
            step["artifacts"] = _generate_stub_artifacts(key, chapter_number)
        elif key in agent_artifacts and agent_artifacts[key]:
            # Build artifacts summary from DB
            artifacts_list = agent_artifacts[key]
            summary_parts = []
            for a in artifacts_list:
                atype = a.get("artifact_type", "")
                aid = a.get("agent_id", "")
                summary_parts.append(f"{atype} ({aid})")
            step["artifacts"] = {
                "summary": ", ".join(summary_parts) if summary_parts else "Agent 产物",
                "artifact_count": len(artifacts_list),
                "artifact_types": [a.get("artifact_type", "") for a in artifacts_list],
                # P1: indicate if artifacts came from legacy fallback (not run-isolated)
                "is_legacy_fallback": artifacts_source == "chapter_fallback",
            }
        else:
            step["artifacts"] = None

        steps.append(step)

    return steps


@router.get("/run/chapter/stream")
async def run_chapter_stream(
    request: Request,
    project_id: str,
    chapter: int,
) -> StreamingResponse:
    """Run chapter with SSE streaming (v5.2 Phase C).

    Streams real-time progress events during chapter generation.

    Event types:
    - step_start: Agent started processing
    - step_complete: Agent finished with timing info
    - run_complete: Workflow finished successfully
    - run_error: Workflow failed with error
    """
    from ..deps import get_repo, get_settings, get_llm_mode
    from ...workflow.runner import run_with_graph_stream

    try:
        repo = get_repo(request)
        settings = get_settings(request)
        llm_mode = get_llm_mode(request)

        def next_stream_event(iterator):
            try:
                return False, next(iterator)
            except StopIteration:
                return True, None

        async def event_generator():
            """Generate SSE events from runner stream."""
            iterator = run_with_graph_stream(
                project_id=project_id,
                chapter_number=chapter,
                settings=settings,
                repo=repo,
                llm_mode=llm_mode,
            )
            while True:
                done, event = await asyncio.to_thread(next_stream_event, iterator)
                if done:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    except Exception as e:
        # For SSE, errors are returned as error events
        async def error_event():
            yield f"data: {json.dumps({'type': 'run_error', 'error': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            error_event(),
            media_type="text/event-stream",
        )
