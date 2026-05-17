"""Projects API endpoints."""

from __future__ import annotations

import io
import re
from enum import Enum
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ...agent_runtime.chapter_text import is_chapter_heading

router = APIRouter()


class ChapterRegenerateResetRequest(BaseModel):
    """Explicitly allow regenerating a planned chapter that already has text."""

    confirm: bool = False


def _chapter_quality_score(repo, project_id: str, chapter: dict) -> int | float | None:
    """Return the user-facing quality score for a chapter.

    `chapters` does not currently persist a quality_score column. The workbench
    read model derives it from the latest editor review first, then falls back
    to QualityHub reports.
    """
    chapter_number = chapter.get("chapter_number")
    try:
        chapter_id = chapter.get("id")
        if chapter_id:
            review = repo.get_latest_review(project_id, chapter_id)
            if review and review.get("score") is not None:
                return review.get("score")
    except Exception:
        pass

    try:
        for stage in ("final", "polished", "draft"):
            report = repo.get_latest_quality_report(project_id, chapter_number, stage)
            if report and report.get("overall_score") is not None:
                score = report.get("overall_score")
                return round(score, 1) if isinstance(score, float) else score
    except Exception:
        pass

    return None


def _is_bare_chapter_title(title: str | None, chapter_number: int) -> bool:
    text = re.sub(r"\s+", "", str(title or "").strip())
    return text in {f"第{chapter_number}章", f"第{chapter_number}章节"} or bool(
        re.fullmatch(r"第[一二三四五六七八九十百千零〇两]+章节?", text)
    )


def _clean_title_suffix(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[\"'“”‘’《》【】\s]+|[\"'“”‘’《》【】\s]+$", "", text)
    text = re.split(r"[。！？!?；;，,\n\r]", text, maxsplit=1)[0].strip()
    text = re.sub(r"\s+", "", text)
    if len(text) < 2:
        return ""
    return text[:14]


def _chapter_display_title(chapter: dict) -> str:
    """Return a readable chapter title for API consumers.

    Older generated chapters may have stored only "第N章". For display, derive a
    short suffix from the first prose line while leaving the stored record intact.
    """
    chapter_number = int(chapter.get("chapter_number") or 0)
    title = str(chapter.get("title") or "").strip()
    if not chapter_number or not _is_bare_chapter_title(title, chapter_number):
        return title

    lines = [line.strip() for line in str(chapter.get("content") or "").splitlines() if line.strip()]
    for line in lines:
        if is_chapter_heading(line, chapter_number):
            continue
        suffix = _clean_title_suffix(line)
        if suffix:
            return f"第{chapter_number}章 {suffix}"

    return title or f"第{chapter_number}章"


def _chapter_display_content(chapter: dict, display_title: str) -> str:
    content = str(chapter.get("content") or "")
    chapter_number = int(chapter.get("chapter_number") or 0)
    stored_title = str(chapter.get("title") or "").strip()
    if not content.strip() or display_title == stored_title:
        return content

    lines = content.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if is_chapter_heading(line.strip(), chapter_number):
            lines[index] = display_title
            return "\n".join(lines)
        return content
    return content


class CreateProjectRequest(BaseModel):
    """Create project request."""

    project_id: str
    name: str
    genre: str | None = None
    description: str | None = None
    total_chapters_planned: int = 500
    target_words: int = 1500000
    style_template: str = "default_web_serial"
    start_chapter: int = 1
    initial_chapter_count: int = 10


class UpdateProjectRequest(BaseModel):
    """Update project request (v5.2 Phase C)."""

    name: str | None = None
    description: str | None = None
    genre: str | None = None
    target_words: int | None = None
    total_chapters_planned: int | None = None


@router.get("/projects")
async def list_projects(request: Request) -> EnvelopeResponse:
    """List all projects."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        projects = repo.list_projects()

        # Add chapter counts
        result = []
        for p in projects:
            chapters = repo.list_chapters(p["project_id"])
            result.append({
                **p,
                "chapter_count": len(chapters),
            })

        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目列表失败: {str(e)}")


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str) -> EnvelopeResponse:
    """Get a single project by ID."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)

        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if hasattr(repo, "reconcile_latest_blocked_runs_with_chapters"):
            repo.reconcile_latest_blocked_runs_with_chapters(project_id=project_id)

        # Get chapters
        chapters = repo.list_chapters(project_id)

        return envelope_response({
            **project,
            "chapters": chapters,
            "chapter_count": len(chapters),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目失败: {str(e)}")


@router.put("/projects/{project_id}")
async def update_project(
    request: Request, project_id: str, body: UpdateProjectRequest
) -> EnvelopeResponse:
    """Update project settings (v5.2 Phase C).

    Allows updating name, description, genre, target_words, total_chapters_planned.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Build update data (only include non-None fields)
        update_data = {}
        if body.name is not None:
            update_data["name"] = body.name
        if body.description is not None:
            update_data["description"] = body.description
        if body.genre is not None:
            update_data["genre"] = body.genre
        if body.target_words is not None:
            update_data["target_words"] = body.target_words
        if body.total_chapters_planned is not None:
            update_data["total_chapters_planned"] = body.total_chapters_planned

        if not update_data:
            return error_response("NO_UPDATES", "没有提供需要更新的字段")

        # Update project
        updated = repo.update_project(project_id, **update_data)
        if not updated:
            return error_response("UPDATE_FAILED", "更新项目失败")

        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新项目失败: {str(e)}")


@router.get("/projects/{project_id}/chapters/{chapter_number}")
async def get_chapter_detail(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """Get a single chapter's full detail including content.

    This is the author reader endpoint — content is included.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Get chapter
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        display_title = _chapter_display_title(chapter)

        # Return clean chapter data (no internal DB fields)
        return envelope_response({
            "project_id": project_id,
            "project_name": project.get("name", ""),
            "chapter_number": chapter.get("chapter_number", chapter_number),
            "title": display_title,
            "status": chapter.get("status", ""),
            "word_count": chapter.get("word_count", 0),
            "quality_score": _chapter_quality_score(repo, project_id, chapter),
            "content": _chapter_display_content(chapter, display_title),
            "created_at": chapter.get("created_at", ""),
            "updated_at": chapter.get("updated_at", ""),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取章节详情失败: {str(e)}")


@router.get("/projects/{project_id}/workspace")
async def get_project_workspace(request: Request, project_id: str) -> EnvelopeResponse:
    """Get project workspace with chapters and recent runs."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)

        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        if hasattr(repo, "reconcile_latest_blocked_runs_with_chapters"):
            repo.reconcile_latest_blocked_runs_with_chapters(project_id=project_id)

        # Get chapters
        chapters = repo.list_chapters(project_id)
        chapters = [
            {
                **chapter,
                "title": _chapter_display_title(chapter),
                "quality_score": _chapter_quality_score(repo, project_id, chapter),
            }
            for chapter in chapters
        ]

        # Get recent runs
        runs = repo.get_workflow_runs_for_project(project_id, limit=10)

        # Get stats
        total_words = sum(ch.get("word_count", 0) for ch in chapters)
        status_counts = {}
        for ch in chapters:
            status = ch.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return envelope_response({
            "project": project,
            "chapters": chapters,
            "recent_runs": runs,
            "stats": {
                "total_chapters": len(chapters),
                "total_words": total_words,
                "status_counts": status_counts,
            },
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目工作台失败: {str(e)}")


@router.delete("/projects/{project_id}")
async def delete_project(request: Request, project_id: str) -> EnvelopeResponse:
    """Delete a project and all associated data."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_project(project_id)
        if not deleted:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        if "database is locked" in str(e).lower():
            return error_response(
                "DATABASE_LOCKED",
                "数据库正在被运行任务或后台服务占用，请稍后重试；如果仍失败，请先停止正在运行的工作流或重启本地 API 服务。",
            )
        return error_response("INTERNAL_ERROR", f"删除项目失败: {str(e)}")


@router.post("/projects/{project_id}/chapters/{chapter_number}/reset")
async def reset_chapter(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """Reset a chapter to planned status for re-processing.

    Only works for chapters in 'blocking' or 'revision' status.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        # Check if reset is allowed
        current_status = chapter.get("status", "")
        if current_status not in ("blocking", "revision", "planned"):
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'blocking'、'revision' 或 'planned' 状态可重置"
            )

        retry_count_before = repo.get_chapter_retry_count(project_id, chapter_number)

        # Reset the chapter and mark a new retry window.
        if current_status in ("blocking", "revision"):
            reset = repo.reset_chapter(project_id, chapter_number)
            if not reset:
                return error_response("RESET_FAILED", "重置章节失败")
        # For planned: no state reset needed, already at planned

        recovered_blocked_runs = 0
        if hasattr(repo, "mark_blocked_workflow_runs_recovered_for_chapter"):
            recovered_blocked_runs = repo.mark_blocked_workflow_runs_recovered_for_chapter(
                project_id,
                chapter_number,
            )

        invalidated_runs = repo.invalidate_running_workflow_runs_for_chapter(
            project_id,
            chapter_number,
            "章节已重置，旧运行已作废，请重新开始新的工作流。",
        )

        from ...workflow.checkpoint import delete_checkpoint_thread
        checkpoint_cleared = delete_checkpoint_thread(
            repo.db_path, project_id, chapter_number
        )
        retry_count_after = repo.get_chapter_retry_count(project_id, chapter_number)

        return envelope_response({
            "reset": True,
            "previous_status": current_status,
            "new_status": "planned",
            "retry_count_before": retry_count_before,
            "retry_count_after": retry_count_after,
            "retries_cleared": max(0, retry_count_before - retry_count_after),
            "recovered_blocked_runs": recovered_blocked_runs,
            "invalidated_runs": invalidated_runs,
            "checkpoint_cleared": checkpoint_cleared,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"重置章节失败: {str(e)}")


@router.post("/projects/{project_id}/chapters/{chapter_number}/regenerate-reset")
async def confirm_chapter_regeneration(
    request: Request,
    project_id: str,
    chapter_number: int,
    body: ChapterRegenerateResetRequest,
) -> EnvelopeResponse:
    """Mark a planned chapter with preserved text as explicitly regenerable.

    This does not delete the existing text immediately. It records the user's
    explicit confirmation so the run guard can allow the next generation to
    overwrite the preserved draft intentionally.
    """
    from ..deps import get_repo
    from ...workflow.checkpoint import delete_checkpoint_thread

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认覆盖已有正文并重新生成")

        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        current_status = chapter.get("status", "")
        content = (chapter.get("content") or "").strip()
        word_count = chapter.get("word_count") or 0
        if current_status != "planned" or not (content or word_count > 0):
            return error_response(
                "INVALID_STATUS",
                "仅 planned 且已有正文的章节需要确认覆盖重新生成",
                details={"current_status": current_status, "word_count": word_count},
            )

        run_id = repo.create_workflow_run(project_id, chapter_number)
        repo.update_workflow_run(
            run_id,
            status="completed",
            current_node="reset_recovery",
            clear_error=True,
        )
        recovered_blocked_runs = 0
        if hasattr(repo, "mark_blocked_workflow_runs_recovered_for_chapter"):
            recovered_blocked_runs = repo.mark_blocked_workflow_runs_recovered_for_chapter(
                project_id,
                chapter_number,
            )

        conn = repo._conn()
        try:
            conn.execute(
                "INSERT INTO task_status "
                "(project_id, chapter_number, task_type, agent_id, status, "
                "started_at, completed_at, error_message, workflow_run_id) "
                "VALUES (?, ?, 'reset', 'human', 'completed', "
                "datetime('now','+8 hours'), datetime('now','+8 hours'), ?, ?)",
                (
                    project_id,
                    chapter_number,
                    "人工确认：已有正文可被下一次生成覆盖。",
                    run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        invalidated_runs = repo.invalidate_running_workflow_runs_for_chapter(
            project_id,
            chapter_number,
            "用户已确认覆盖已有正文，旧运行已作废。",
        )
        checkpoint_cleared = delete_checkpoint_thread(repo.db_path, project_id, chapter_number)

        return envelope_response({
            "reset": True,
            "run_id": run_id,
            "previous_status": current_status,
            "new_status": "planned",
            "word_count": word_count,
            "recovered_blocked_runs": recovered_blocked_runs,
            "invalidated_runs": invalidated_runs,
            "checkpoint_cleared": checkpoint_cleared,
            "message": "已确认覆盖已有正文，下一次生成将重新执行本章工作流。",
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"确认重新生成失败: {str(e)}")


@router.delete("/projects/{project_id}/chapters/{chapter_number}")
async def delete_chapter(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """Delete a chapter.

    Only allowed for chapters in 'planned' status.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        # Check if deletion is allowed (only planned status)
        current_status = chapter.get("status", "")
        if current_status != "planned":
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'planned' 状态可删除"
            )

        # Delete the chapter
        deleted = repo.delete_chapter(project_id, chapter_number)
        if not deleted:
            return error_response("DELETE_FAILED", "删除章节失败")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除章节失败: {str(e)}")


@router.get("/projects/{project_id}/runs")
async def get_project_runs(request: Request, project_id: str) -> EnvelopeResponse:
    """Get all workflow runs for a project.

    Returns run list with id, chapter_number, status, current_node,
    error_message, token usage, duration, and timestamps.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        runs = repo.get_workflow_runs_for_project(project_id, limit=50)

        return envelope_response(runs)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行记录失败: {str(e)}")


class ExportFormat(str, Enum):
    txt = "txt"
    markdown = "markdown"


@router.get("/projects/{project_id}/export")
async def export_project(
    request: Request,
    project_id: str,
    format: ExportFormat = Query(ExportFormat.txt, description="导出格式: txt 或 markdown"),
) -> StreamingResponse:
    """Export all chapters of a project as a downloadable text file.

    Only chapters with content are included. Chapters are ordered by chapter_number.
    """
    from ..deps import get_repo

    repo = get_repo(request)

    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目 '{project_id}' 不存在")

    chapters = repo.list_chapters(project_id)
    project_name = project.get("name", project_id)

    # Filter chapters that have content
    chapters_with_content = [
        ch for ch in chapters
        if ch.get("content") and ch["content"].strip()
    ]

    if not chapters_with_content:
        raise HTTPException(status_code=400, detail="该项目没有可导出的章节内容")

    # Build output
    buf = io.StringIO()

    if format == ExportFormat.markdown:
        buf.write(f"# {project_name}\n\n")
        for ch in chapters_with_content:
            content = ch["content"].strip()
            if not is_chapter_heading(content.splitlines()[0] if content else "", ch["chapter_number"]):
                chapter_title = ch.get("title") or f"第{ch['chapter_number']}章"
                buf.write(f"## {chapter_title}\n\n")
            buf.write(ch["content"])
            buf.write("\n\n---\n\n")
    else:
        buf.write(f"{project_name}\n{'=' * 40}\n\n")
        for ch in chapters_with_content:
            content = ch["content"].strip()
            if not is_chapter_heading(content.splitlines()[0] if content else "", ch["chapter_number"]):
                chapter_title = ch.get("title") or f"第{ch['chapter_number']}章"
                buf.write(f"{chapter_title}\n{'-' * 40}\n\n")
            buf.write(ch["content"])
            buf.write("\n\n")

    content = buf.getvalue()
    buf.close()

    suffix = "md" if format == ExportFormat.markdown else "txt"
    filename = f"{project_name}.{suffix}"
    fallback_stem = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in "-_.") else "_"
        for ch in project_id
    ).strip("._") or "project"
    fallback_filename = f"{fallback_stem}.{suffix}"
    encoded_filename = quote(filename.encode("utf-8"))

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{fallback_filename}"; '
                f"filename*=UTF-8''{encoded_filename}"
            ),
        },
    )
