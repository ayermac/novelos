"""Run detail API endpoints."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


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
            "error_message": run_data.get("error_message"),
            "steps": steps,
            # v5.2: Token usage statistics
            "prompt_tokens": run_data.get("prompt_tokens", 0),
            "completion_tokens": run_data.get("completion_tokens", 0),
            "total_tokens": run_data.get("total_tokens", 0),
            "duration_ms": run_data.get("duration_ms", 0),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行详情失败: {str(e)}")


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
    task_errors: dict[str, str] = {}
    if repo:
        try:
            conn = repo._conn()
            try:
                rows = conn.execute(
                    "SELECT agent_id, status, error_message FROM task_status "
                    "WHERE project_id=? AND chapter_number=? AND status='failed'",
                    (project_id, chapter_number),
                ).fetchall()
                for r in rows:
                    agent_id = r["agent_id"]
                    if r["error_message"]:
                        task_errors[agent_id] = r["error_message"]
            finally:
                conn.close()
        except Exception:
            pass  # Graceful degradation

    # Fetch agent_artifacts for per-agent artifact summaries
    agent_artifacts: dict[str, list[dict]] = {}
    if repo:
        try:
            artifacts = repo.get_artifacts_for_chapter(project_id, chapter_number)
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

    # Build steps
    steps = []
    for step_config in AGENT_STEPS:
        key = step_config["key"]
        is_completed = key in completed_agents
        is_running = (current_node == key) and workflow_status == "running"
        is_failed = (current_node == key) and workflow_status == "failed"
        is_blocked = (current_node == key) and workflow_status == "blocked"

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
        if is_failed and error_message:
            step["error_message"] = error_message
        elif key in task_errors:
            step["error_message"] = task_errors[key]

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

        async def event_generator():
            """Generate SSE events from runner stream."""
            for event in run_with_graph_stream(
                project_id=project_id,
                chapter_number=chapter,
                settings=settings,
                repo=repo,
                llm_mode=llm_mode,
            ):
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
