"""Memory update batches and items API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class MemoryItemUpdateRequest(BaseModel):
    """Request to update a memory update item."""

    status: str | None = None
    after_json: str | None = None
    rationale: str | None = None
    evidence_text: str | None = None


class MemoryApplyRequest(BaseModel):
    """Canonical body for memory apply action."""

    project_id: str
    batch_id: str


class MemoryIgnoreRequest(BaseModel):
    """Canonical body for memory ignore action."""

    project_id: str
    item_id: str


def _json_text(value) -> str:
    """Normalize structured memory values for text columns."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _normalize_text_fields(data: dict, fields: tuple[str, ...]) -> dict:
    """Return a copy with structured fields serialized for DB text columns."""
    normalized = dict(data)
    for field in fields:
        if field in normalized:
            normalized[field] = _json_text(normalized[field])
    return normalized


def _apply_memory_item(
    repo,
    project_id: str,
    item: dict,
    chapter_number: int = 0,
    batch_id: str | None = None,
) -> dict:
    """Apply a single memory update item to its target table.

    Returns a result dict with operation details.
    """
    target_table = item.get("target_table", "")
    operation = item.get("operation", "")
    target_id = item.get("target_id")
    after_data = {}

    try:
        after_data = json.loads(item.get("after_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        pass

    result = {"target_table": target_table, "operation": operation, "success": False}

    try:
        if target_table == "world_settings":
            if operation == "create":
                ws = repo.create_world_setting(
                    project_id,
                    category=after_data.get("category", ""),
                    title=after_data.get("title", ""),
                    content=after_data.get("content", ""),
                )
                result["success"] = True
                result["created_id"] = ws["id"] if ws else None
            elif operation == "update" and target_id:
                repo.update_world_setting(project_id, target_id, after_data)
                result["success"] = True

        elif target_table == "characters":
            character_data = _normalize_text_fields(
                after_data, ("traits", "description", "alias", "role", "status")
            )
            if operation == "create":
                ch = repo.create_character(
                    project_id,
                    name=character_data.get("name", ""),
                    role=character_data.get("role", "supporting"),
                    description=character_data.get("description", ""),
                    traits=character_data.get("traits", ""),
                )
                result["success"] = True
                result["created_id"] = ch["id"] if ch else None
            elif operation == "update" and target_id:
                repo.update_character(project_id, target_id, character_data)
                result["success"] = True

        elif target_table == "factions":
            if operation == "create":
                f = repo.create_faction(
                    project_id,
                    name=after_data.get("name", ""),
                    type=after_data.get("type", ""),
                    description=after_data.get("description", ""),
                    relationship_with_protagonist=after_data.get(
                        "relationship_with_protagonist", ""
                    ),
                )
                result["success"] = True
                result["created_id"] = f["id"] if f else None
            elif operation == "update" and target_id:
                repo.update_faction(project_id, target_id, after_data)
                result["success"] = True

        elif target_table == "outlines":
            if operation == "create":
                o = repo.create_outline(
                    project_id,
                    level=after_data.get("level", "arc"),
                    sequence=after_data.get("sequence", 1),
                    title=after_data.get("title", ""),
                    content=after_data.get("content", ""),
                    chapters_range=after_data.get("chapters_range", ""),
                )
                result["success"] = True
                result["created_id"] = o["id"] if o else None
            elif operation == "update" and target_id:
                repo.update_outline(project_id, target_id, after_data)
                result["success"] = True

        elif target_table == "plot_holes":
            if operation == "create":
                code = after_data.get("code", "")
                existing = next(
                    (
                        plot
                        for plot in repo.list_plot_holes(project_id)
                        if plot.get("code") == code
                    ),
                    None,
                )
                if existing:
                    ph = repo.update_plot_hole(project_id, existing["id"], after_data)
                    result["operation"] = "update"
                    result["success"] = ph is not None
                    result["created_id"] = existing["id"]
                else:
                    ph = repo.create_plot_hole(
                        project_id,
                        code=code,
                        type=after_data.get("type", ""),
                        title=after_data.get("title", ""),
                        description=after_data.get("description", ""),
                        planted_chapter=after_data.get("planted_chapter"),
                        planned_resolve_chapter=after_data.get("planned_resolve_chapter"),
                        status=after_data.get("status", "planted"),
                    )
                    result["success"] = True
                    result["created_id"] = ph["id"] if ph else None
            elif operation == "update" and target_id:
                repo.update_plot_hole(project_id, target_id, after_data)
                result["success"] = True

        elif target_table == "instructions":
            instruction_data = _normalize_text_fields(
                after_data,
                (
                    "key_events",
                    "plots_to_resolve",
                    "plots_to_plant",
                    "emotion_tone",
                    "ending_hook",
                    "objective",
                ),
            )
            if operation == "create":
                inst = repo.create_instruction(
                    project_id,
                    chapter_number=instruction_data.get("chapter_number", 0),
                    objective=instruction_data.get("objective", ""),
                    key_events=instruction_data.get("key_events", ""),
                    plots_to_resolve=instruction_data.get("plots_to_resolve", ""),
                    plots_to_plant=instruction_data.get("plots_to_plant", ""),
                    emotion_tone=instruction_data.get("emotion_tone", ""),
                    ending_hook=instruction_data.get("ending_hook", ""),
                    word_target=instruction_data.get("word_target"),
                )
                result["success"] = True
                result["created_id"] = inst
            elif operation == "update" and target_id:
                repo.update_instruction(project_id, target_id, instruction_data)
                result["success"] = True

        elif target_table == "story_facts":
            fact_key = after_data.get("fact_key", "")
            if fact_key:
                # Check if fact exists before upsert (for event type)
                existing_fact = repo.get_story_fact_by_key(project_id, fact_key)
                is_update = existing_fact is not None

                fact = repo.upsert_story_fact(
                    project_id,
                    fact_key=fact_key,
                    fact_type=after_data.get("fact_type", "character_state"),
                    value_json=json.dumps(
                        after_data.get("value", {}), ensure_ascii=False
                    ),
                    source_chapter=after_data.get("source_chapter"),
                    source_agent=after_data.get("source_agent"),
                    subject=after_data.get("subject"),
                    attribute=after_data.get("attribute"),
                    unit=after_data.get("unit"),
                )
                result["success"] = True
                result["created_id"] = fact["id"] if fact else None

                # Create fact event for traceability
                if fact:
                    event_type = "updated" if is_update else "created"
                    event_chapter = (
                        after_data.get("source_chapter")
                        or chapter_number
                    )
                    try:
                        repo.create_fact_event(
                            project_id,
                            chapter_number=event_chapter,
                            agent_id="memory_curator",
                            event_type=event_type,
                            fact_id=fact["id"],
                            run_id=batch_id,
                            after_json=json.dumps(
                                after_data, ensure_ascii=False
                            ),
                            rationale=item.get(
                                "rationale",
                                f"Memory patch {event_type}",
                            ),
                            evidence_text=item.get("evidence_text", ""),
                            validation_status="validated",
                        )
                    except Exception:
                        pass  # Event creation is non-blocking

        elif target_table == "project":
            if after_data:
                repo.update_project(project_id, **after_data)
                result["success"] = True

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


@router.get("/projects/{project_id}/memory-batches")
async def list_memory_batches(
    request: Request, project_id: str, status: str | None = None
) -> EnvelopeResponse:
    """List memory update batches for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        batches = repo.list_memory_batches(project_id, status=status)
        return envelope_response(batches)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取记忆批次列表失败: {str(e)}")


@router.get("/projects/{project_id}/memory-batches/{batch_id}")
async def get_memory_batch(
    request: Request, project_id: str, batch_id: str
) -> EnvelopeResponse:
    """Get a memory update batch with its items."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        batch = repo.get_memory_batch(batch_id)
        if not batch:
            return error_response("BATCH_NOT_FOUND", f"批次 {batch_id} 不存在")

        if batch["project_id"] != project_id:
            return error_response("BATCH_NOT_FOUND", "批次不属于该项目")

        items = repo.list_memory_items(batch_id)
        result = {**batch, "items": items}
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取批次详情失败: {str(e)}")


@router.post("/projects/{project_id}/memory-batches/{batch_id}/apply")
async def apply_memory_batch(
    request: Request, project_id: str, batch_id: str
) -> EnvelopeResponse:
    """Apply all pending items in a memory update batch."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        batch = repo.get_memory_batch(batch_id)
        if not batch:
            return error_response("BATCH_NOT_FOUND", f"批次 {batch_id} 不存在")

        if batch["project_id"] != project_id:
            return error_response("BATCH_NOT_FOUND", "批次不属于该项目")

        if batch["status"] not in ("pending", "partial"):
            return error_response(
                "INVALID_BATCH_STATUS",
                f"只能应用待处理的批次，当前状态: {batch['status']}",
            )

        items = repo.list_memory_items(batch_id, status="pending")
        if not items:
            return error_response(
                "NO_PENDING_MEMORY_ITEMS",
                "该批次没有待应用的记忆项，请刷新后查看最新状态",
            )
        results = []

        for item in items:
            apply_result = _apply_memory_item(
                repo, project_id, item,
                chapter_number=batch.get("chapter_number", 0),
                batch_id=batch_id,
            )
            if apply_result["success"]:
                repo.update_memory_item(item["id"], {"status": "applied"})
            else:
                repo.update_memory_item(item["id"], {"status": "failed"})
            results.append({**apply_result, "item_id": item["id"]})

        # Update batch status
        all_success = all(r["success"] for r in results)
        new_status = "applied" if all_success else "partial"
        repo.update_memory_batch(batch_id, {"status": new_status})

        return envelope_response({
            "batch_id": batch_id,
            "status": new_status,
            "items_processed": len(results),
            "results": results,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"应用批次失败: {str(e)}")


@router.post("/projects/{project_id}/memory-items/{item_id}/ignore")
async def ignore_memory_item(
    request: Request, project_id: str, item_id: str
) -> EnvelopeResponse:
    """Ignore a memory update item."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        item = repo.get_memory_item(item_id)
        if not item:
            return error_response("ITEM_NOT_FOUND", f"项目 {item_id} 不存在")

        if item["project_id"] != project_id:
            return error_response("ITEM_NOT_FOUND", "更新项不属于该项目")

        if item["status"] != "pending":
            return error_response(
                "INVALID_ITEM_STATUS",
                f"只能忽略待处理的项目，当前状态: {item['status']}",
            )

        updated = repo.update_memory_item(item_id, {"status": "ignored"})
        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"忽略更新项失败: {str(e)}")


@router.put("/projects/{project_id}/memory-items/{item_id}")
async def update_memory_item(
    request: Request, project_id: str, item_id: str, body: MemoryItemUpdateRequest
) -> EnvelopeResponse:
    """Update a memory update item (e.g., edit before applying)."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        item = repo.get_memory_item(item_id)
        if not item:
            return error_response("ITEM_NOT_FOUND", f"项目 {item_id} 不存在")

        if item["project_id"] != project_id:
            return error_response("ITEM_NOT_FOUND", "更新项不属于该项目")

        data = {}
        if body.status is not None:
            data["status"] = body.status
        if body.after_json is not None:
            data["after_json"] = body.after_json
        if body.rationale is not None:
            data["rationale"] = body.rationale
        if body.evidence_text is not None:
            data["evidence_text"] = body.evidence_text

        if not data:
            return envelope_response(item)

        updated = repo.update_memory_item(item_id, data)
        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新记忆项失败: {str(e)}")


# ---------------------------------------------------------------------------
# Canonical body-style routes (API Contract §4)
# ---------------------------------------------------------------------------


@router.post("/memory/apply")
async def apply_memory_batch_canonical(
    request: Request, body: MemoryApplyRequest
) -> EnvelopeResponse:
    """Canonical body-style route for memory batch apply."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        batch = repo.get_memory_batch(body.batch_id)
        if not batch:
            return error_response("BATCH_NOT_FOUND", f"批次 {body.batch_id} 不存在")

        if batch["project_id"] != body.project_id:
            return error_response("BATCH_NOT_FOUND", "批次不属于该项目")

        if batch["status"] not in ("pending", "partial"):
            return error_response(
                "INVALID_BATCH_STATUS",
                f"只能应用待处理的批次，当前状态: {batch['status']}",
            )

        items = repo.list_memory_items(body.batch_id, status="pending")
        if not items:
            return error_response(
                "NO_PENDING_MEMORY_ITEMS",
                "该批次没有待应用的记忆项，请刷新后查看最新状态",
            )
        results = []

        for item in items:
            apply_result = _apply_memory_item(
                repo, body.project_id, item,
                chapter_number=batch.get("chapter_number", 0),
                batch_id=body.batch_id,
            )
            if apply_result["success"]:
                repo.update_memory_item(item["id"], {"status": "applied"})
            else:
                repo.update_memory_item(item["id"], {"status": "failed"})
            results.append({**apply_result, "item_id": item["id"]})

        all_success = all(r["success"] for r in results)
        new_status = "applied" if all_success else "partial"
        repo.update_memory_batch(body.batch_id, {"status": new_status})

        return envelope_response({
            "batch_id": body.batch_id,
            "status": new_status,
            "items_processed": len(results),
            "results": results,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"应用批次失败: {str(e)}")


@router.post("/memory/ignore")
async def ignore_memory_item_canonical(
    request: Request, body: MemoryIgnoreRequest
) -> EnvelopeResponse:
    """Canonical body-style route for memory item ignore."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        item = repo.get_memory_item(body.item_id)
        if not item:
            return error_response("ITEM_NOT_FOUND", f"项目 {body.item_id} 不存在")

        if item["project_id"] != body.project_id:
            return error_response("ITEM_NOT_FOUND", "更新项不属于该项目")

        if item["status"] != "pending":
            return error_response(
                "INVALID_ITEM_STATUS",
                f"只能忽略待处理的项目，当前状态: {item['status']}",
            )

        updated = repo.update_memory_item(body.item_id, {"status": "ignored"})
        return envelope_response(updated)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"忽略更新项失败: {str(e)}")
