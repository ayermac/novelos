"""Chapter editing and version management API endpoints (v5.7)."""

from __future__ import annotations

import json
from enum import Enum

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ..contracts import success, failed

router = APIRouter()


# ── Source display labels ──────────────────────────────────

SOURCE_LABELS = {
    "ai_generation": "AI 生成",
    "manual_edit": "人工编辑",
    "local_revision": "局部返修",
    "rollback": "回滚",
    "publish_snapshot": "发布快照",
}

# Chapters that allow direct editing
EDITABLE_STATUSES = {"drafted", "polished", "revision", "scripted", "blocking"}
# Chapters that are read-only and need revision-draft first
PUBLISHED_STATUSES = {"published", "awaiting_publish"}


def _source_label(source: str | None) -> str:
    return SOURCE_LABELS.get(source or "", source or "未知")


# ── Request/Response models ────────────────────────────────


class SaveContentRequest(BaseModel):
    """Save human-edited chapter content."""

    content: str
    summary: str | None = None
    base_version_id: int | None = None
    confirm: bool = False
    is_local_edit: bool = False  # v6.6.6: Flag for local edit context


class LocalRevisionMode(str, Enum):
    rewrite = "rewrite"
    polish = "polish"
    shorten = "shorten"
    expand = "expand"
    tone = "tone"


class LocalRevisionRequest(BaseModel):
    """Request AI local revision for selected text."""

    selected_text: str = Field(..., min_length=1)
    selection_start: int = Field(..., ge=0)
    selection_end: int = Field(..., ge=0)
    instruction: str | None = None
    base_version_id: int | None = None
    mode: LocalRevisionMode = LocalRevisionMode.polish


class RestoreVersionRequest(BaseModel):
    """Restore a previous version."""

    confirm: bool = False


class RevisionDraftRequest(BaseModel):
    """Create a revision draft for a published chapter."""

    confirm: bool = False


def _is_deletion_revision_request(instruction: str | None) -> bool:
    """Return true when an empty local-revision replacement is intentional."""
    text = (instruction or "").strip().lower()
    if not text:
        return False
    deletion_markers = (
        "去掉",
        "删掉",
        "删除",
        "删去",
        "移除",
        "去除",
        "拿掉",
        "裁掉",
        "这一段不要",
        "这段不要",
        "不要这段",
        "remove",
        "delete",
        "omit",
        "drop",
        "cut this",
        "cut it",
    )
    return any(marker in text for marker in deletion_markers)


# ── 1. Editor state ────────────────────────────────────────


@router.get("/projects/{project_id}/chapters/{chapter_number}/editor")
async def get_editor_state(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """Get chapter editor state: content, editability, current version, recent versions."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        status = chapter.get("status", "planned")
        content = chapter.get("content", "") or ""
        word_count = chapter.get("word_count", 0) or 0

        # Editability
        if status in PUBLISHED_STATUSES:
            editable = False
            edit_restriction = "章节已发布，需创建修订版后才能编辑"
        elif status == "planned" and not content:
            editable = True
            edit_restriction = None
        elif status in EDITABLE_STATUSES:
            editable = True
            edit_restriction = None
        elif status == "reviewed":
            editable = True
            edit_restriction = "保存后章节将回到待审核状态"
        else:
            editable = False
            edit_restriction = f"章节状态 '{status}' 不可编辑"

        # Current version info
        latest_version_id = repo.get_latest_version_id(project_id, chapter_number)
        versions = repo.list_chapter_versions(project_id, chapter_number)
        recent_versions = [
            {
                "version_id": v["id"],
                "version": v.get("version"),
                "source": v.get("source"),
                "source_label": _source_label(v.get("source")),
                "created_by": v.get("created_by"),
                "word_count": v.get("word_count", 0),
                "summary": v.get("summary"),
                "created_at": v.get("created_at"),
                "is_current": v["id"] == latest_version_id if latest_version_id else False,
            }
            for v in versions[:10]
        ]

        return envelope_response({
            "project_id": project_id,
            "chapter_number": chapter_number,
            "title": chapter.get("title", ""),
            "content": content,
            "word_count": word_count,
            "status": status,
            "editable": editable,
            "edit_restriction": edit_restriction,
            "current_version_id": latest_version_id,
            "recent_versions": recent_versions,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取编辑器状态失败: {str(e)}")


# ── 2. Save content ────────────────────────────────────────


@router.post("/projects/{project_id}/chapters/{chapter_number}/content")
async def save_chapter_content(
    request: Request,
    project_id: str,
    chapter_number: int,
    body: SaveContentRequest,
) -> EnvelopeResponse:
    """Save human-edited chapter content, creating a manual_edit version."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        status = chapter.get("status", "")

        # Guard: protected chapters require explicit confirmation before they are
        # converted back into an editable, review-required draft.
        if status in PUBLISHED_STATUSES and not body.confirm:
            return error_response(
                "PUBLISHED_PROTECTED",
                "已发布或待发布章节不能直接保存，请先创建修订版",
            )

        # Validate content
        if not body.content or len(body.content.strip()) < 10:
            return error_response("CONTENT_TOO_SHORT", "正文内容过短，至少需要 10 个字符")

        # Stale base_version check
        if body.base_version_id is not None:
            latest_vid = repo.get_latest_version_id(project_id, chapter_number)
            if latest_vid is not None and body.base_version_id != latest_vid:
                return error_response(
                    "VERSION_CONFLICT",
                    "基于的版本已过期，请刷新后重试",
                    details={
                        "base_version_id": body.base_version_id,
                        "latest_version_id": latest_vid,
                    },
                )

        # Save content to chapters table
        repo.save_chapter_content(project_id, chapter_number, body.content)

        # Create manual_edit version
        version_id = repo.save_version(
            project_id=project_id,
            chapter=chapter_number,
            content=body.content,
            created_by="author",
            source="manual_edit",
            base_version_id=body.base_version_id,
            summary=body.summary or "人工编辑保存",
        )

        # Status transition: human edits after review/blocking/revision need re-review.
        # v6.6.6: Local edit protection - don't pollute main workflow blocking state
        new_status = status
        status_changed = False
        from ...workflow.state_integrity import should_protect_from_blocking

        # Check if this is a protected local edit
        is_protected_local_edit = should_protect_from_blocking(status, body.is_local_edit)

        if status in PUBLISHED_STATUSES:
            if is_protected_local_edit:
                # v6.6.6: Local edit on published/awaiting_publish - don't change status
                # Just save the content and version, keep terminal status
                new_status = status
                status_changed = False
            else:
                # Explicit edit with confirmation - transition to polished for re-review
                new_status = "polished"
                repo.update_chapter_status(project_id, chapter_number, "polished")
                status_changed = True
        elif status in {"reviewed", "awaiting_publish"}:
            if is_protected_local_edit:
                # v6.6.6: Local edit on reviewed/awaiting_publish - don't enter main workflow
                new_status = status
                status_changed = False
            else:
                new_status = "polished"
                repo.update_chapter_status(project_id, chapter_number, "polished")
                status_changed = True
        elif status in {"blocking", "revision"}:
            new_status = "polished"
            repo.update_chapter_status(project_id, chapter_number, "polished")
            status_changed = True
            reset_task_id = repo.start_task(
                project_id,
                chapter_number,
                "reset",
                "human",
            )
            repo.complete_task(
                reset_task_id,
                success=True,
                error="人工编辑保存：清空本轮自动返修计数。",
            )

        return envelope_response({
            "saved": True,
            "version_id": version_id,
            "word_count": len(body.content),
            "status": new_status,
            "status_changed": status_changed,
            "previous_status": status if status_changed else None,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"保存正文失败: {str(e)}")


# ── 3. Version list ────────────────────────────────────────


@router.get("/projects/{project_id}/chapters/{chapter_number}/versions")
async def list_versions(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """List all versions for a chapter."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        latest_version_id = repo.get_latest_version_id(project_id, chapter_number)
        versions = repo.list_chapter_versions(project_id, chapter_number)

        items = []
        for v in versions:
            items.append({
                "version_id": v["id"],
                "version": v.get("version"),
                "source": v.get("source"),
                "source_label": _source_label(v.get("source")),
                "created_by": v.get("created_by"),
                "word_count": v.get("word_count", 0),
                "summary": v.get("summary"),
                "created_at": v.get("created_at"),
                "is_current": v["id"] == latest_version_id if latest_version_id else False,
            })

        return envelope_response({
            "project_id": project_id,
            "chapter_number": chapter_number,
            "current_version_id": latest_version_id,
            "versions": items,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取版本列表失败: {str(e)}")


# ── 4. Version detail ──────────────────────────────────────


@router.get("/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}")
async def get_version_detail(
    request: Request, project_id: str, chapter_number: int, version_id: int
) -> EnvelopeResponse:
    """Get full version detail including content."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        v = repo.get_version_by_id(project_id, version_id)
        if not v or v.get("chapter") != chapter_number:
            return error_response("VERSION_NOT_FOUND", f"版本 {version_id} 不存在")

        latest_vid = repo.get_latest_version_id(project_id, chapter_number)

        return envelope_response({
            "version_id": v["id"],
            "version": v.get("version"),
            "project_id": v.get("project_id"),
            "chapter": v.get("chapter"),
            "content": v.get("content", ""),
            "word_count": v.get("word_count", 0),
            "source": v.get("source"),
            "source_label": _source_label(v.get("source")),
            "created_by": v.get("created_by"),
            "base_version_id": v.get("base_version_id"),
            "summary": v.get("summary"),
            "metadata": v.get("metadata"),
            "created_at": v.get("created_at"),
            "is_current": v["id"] == latest_vid if latest_vid else False,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取版本详情失败: {str(e)}")


# ── 5. Version diff ────────────────────────────────────────


@router.get(
    "/projects/{project_id}/chapters/{chapter_number}/versions/{left_version_id}/diff/{right_version_id}"
)
async def get_version_diff(
    request: Request,
    project_id: str,
    chapter_number: int,
    left_version_id: int,
    right_version_id: int,
) -> EnvelopeResponse:
    """Get structured diff between two versions.

    Both versions must belong to the same project and chapter_number.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        left = repo.get_version_by_id(project_id, left_version_id)
        right = repo.get_version_by_id(project_id, right_version_id)

        if not left or not right:
            return error_response("VERSION_NOT_FOUND", "版本不存在")

        # Validate both versions belong to the requested chapter
        if left.get("chapter") != chapter_number or right.get("chapter") != chapter_number:
            return error_response("VERSION_NOT_FOUND", "版本不属于该章节")

        diff = repo.get_version_diff(project_id, left_version_id, right_version_id)
        if not diff:
            return error_response("VERSION_NOT_FOUND", "版本对比失败")

        return envelope_response(diff)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取版本对比失败: {str(e)}")


# ── 6. Restore version ─────────────────────────────────────


@router.post("/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}/restore")
async def restore_version(
    request: Request,
    project_id: str,
    chapter_number: int,
    version_id: int,
    body: RestoreVersionRequest,
) -> EnvelopeResponse:
    """Restore a previous version, creating a rollback version."""
    from ..deps import get_repo

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认回滚操作")

        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        status = chapter.get("status", "")
        if status in PUBLISHED_STATUSES:
            return error_response(
                "PUBLISHED_PROTECTED",
                "已发布章节不能直接回滚，请先创建修订版",
            )

        # Get target version
        target = repo.get_version_by_id(project_id, version_id)
        if not target or target.get("chapter") != chapter_number:
            return error_response("VERSION_NOT_FOUND", f"版本 {version_id} 不存在")

        # Update chapter content
        content = target.get("content", "") or ""
        repo.save_chapter_content(project_id, chapter_number, content)

        # Create rollback version
        new_version_id = repo.save_version(
            project_id=project_id,
            chapter=chapter_number,
            content=content,
            created_by="author",
            source="rollback",
            base_version_id=version_id,
            summary=f"回滚到版本 {version_id}",
        )

        return envelope_response({
            "restored": True,
            "target_version_id": version_id,
            "new_version_id": new_version_id,
            "content_restored": True,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"回滚版本失败: {str(e)}")


# ── 7. Revision draft ──────────────────────────────────────


@router.post("/projects/{project_id}/chapters/{chapter_number}/revision-draft")
async def create_revision_draft(
    request: Request,
    project_id: str,
    chapter_number: int,
    body: RevisionDraftRequest,
) -> EnvelopeResponse:
    """Create a revision draft for a published chapter."""
    from ..deps import get_repo

    try:
        if not body.confirm:
            return error_response("CONFIRM_REQUIRED", "请确认创建修订版")

        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        status = chapter.get("status", "")
        if status not in PUBLISHED_STATUSES and status != "reviewed":
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{status}'，仅已发布或待发布章节可创建修订版",
            )

        # Save current content as publish_snapshot before editing
        content = chapter.get("content", "") or ""
        repo.save_version(
            project_id=project_id,
            chapter=chapter_number,
            content=content,
            created_by="author",
            source="publish_snapshot",
            summary=f"发布快照（修订前保存）",
        )

        return envelope_response({
            "revision_draft_created": True,
            "previous_status": status,
            "new_status": status,
            "status_changed": False,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建修订版失败: {str(e)}")


# ── 8. Local revision ──────────────────────────────────────


@router.post("/projects/{project_id}/chapters/{chapter_number}/local-revision")
async def local_revision(
    request: Request,
    project_id: str,
    chapter_number: int,
    body: LocalRevisionRequest,
) -> EnvelopeResponse:
    """AI local revision: returns candidate replacement without overwriting content."""
    from ..deps import get_repo, get_llm_mode, get_settings
    from ...workflow.runner import _build_llm_router

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        content = chapter.get("content", "") or ""

        # Validate selection bounds
        if body.selection_end > len(content) or body.selection_start < 0:
            return error_response("INVALID_SELECTION", "选区范围超出正文边界")

        # Validate selected text matches
        actual_selected = content[body.selection_start:body.selection_end]
        if actual_selected != body.selected_text:
            return error_response(
                "SELECTION_MISMATCH",
                "选区文本与正文不匹配，请刷新后重试",
            )

        # Selection length check
        if len(body.selected_text) > 5000:
            return error_response(
                "SELECTION_TOO_LONG",
                "选中文本过长（超过 5000 字），请缩小范围",
            )

        # Build LLM prompt
        context_before = content[max(0, body.selection_start - 500):body.selection_start]
        context_after = content[body.selection_end:min(len(content), body.selection_end + 500)]

        messages = [
            {
                "role": "system",
                "content": (
                    f"你是一个小说写作助手。用户选中了一段文本，请你根据指令进行局部返修。\n"
                    f"章节标题：{chapter.get('title', '')}\n"
                    f"返修模式：{body.mode.value}\n"
                    f"硬性约束：\n"
                    f"1. 只修改选中的文本，不能改动选区以外的任何内容。\n"
                    f"2. 保持与上下文的衔接自然。\n"
                    f"3. 输出必须是 JSON 格式，包含 replacement_text、change_summary 和 risk_notes。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"上下文（前）：{context_before}\n"
                    f"【选中文本】：{body.selected_text}\n"
                    f"上下文（后）：{context_after}\n"
                    f"用户指令：{body.instruction or '请根据返修模式处理'}\n"
                    f"返修模式：{body.mode.value}"
                ),
            },
        ]

        settings = get_settings(request)
        llm_mode = get_llm_mode(request)
        provider = _build_llm_router(settings, llm_mode).for_agent("author")
        result = provider.invoke_json(messages, schema=LocalRevisionOutput)
        deletion_requested = _is_deletion_revision_request(body.instruction)
        replacement_text = ""
        if result and result.get("replacement_text") is not None:
            replacement_text = str(result.get("replacement_text", ""))

        if not result or (not replacement_text.strip() and not deletion_requested):
            return error_response(
                "REVISION_FAILED",
                "AI 返修返回为空，请重试",
                details={
                    "domain_result": failed(
                        "AI 返修返回为空",
                        user_message="AI 返修返回为空，请重试",
                        retryable=True,
                        next_action="retry_local_revision",
                        action_label="重试局部返修",
                        details={
                            "mode": body.mode.value,
                            "selection_length": len(body.selected_text),
                        },
                        flags={"local_revision_failed": True},
                    ).to_dict(),
                },
            )
        if deletion_requested and not replacement_text.strip():
            replacement_text = ""

        # Normalize output: ensure risk_notes is always a list of strings
        raw_notes = result.get("risk_notes", [])
        if not isinstance(raw_notes, list):
            raw_notes = [str(raw_notes)] if raw_notes else []
        normalized_notes = [str(n) for n in raw_notes]

        return envelope_response({
            "replacement_text": replacement_text,
            "change_summary": str(result.get("change_summary", "")) or (
                "按指令删除选中文本" if deletion_requested and not replacement_text else ""
            ),
            "risk_notes": normalized_notes,
            "selection_start": body.selection_start,
            "selection_end": body.selection_end,
            "mode": body.mode.value,
            "domain_result": success(
                "局部返修候选已生成",
                user_message="局部返修候选已生成，请确认是否应用",
                details={
                    "mode": body.mode.value,
                    "selection_length": len(body.selected_text),
                    "replacement_length": len(replacement_text),
                },
                flags={"local_revision_candidate": True},
            ).to_dict(),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"局部返修失败: {str(e)}")


class LocalRevisionOutput(BaseModel):
    """Structured output for local revision AI response."""

    replacement_text: str = ""
    change_summary: str = ""
    risk_notes: list[str] = Field(default_factory=list)
