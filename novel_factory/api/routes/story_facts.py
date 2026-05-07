"""Story facts and events API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class StoryFactUpdateRequest(BaseModel):
    """Request to update a story fact (manual correction)."""

    value_json: str | None = None
    status: str | None = None
    confidence: float | None = None
    subject: str | None = None
    attribute: str | None = None
    unit: str | None = None
    scope: str | None = None
    correction_note: str | None = None


@router.get("/projects/{project_id}/story-facts")
async def list_story_facts(
    request: Request,
    project_id: str,
    fact_type: str | None = None,
    status: str | None = None,
) -> EnvelopeResponse:
    """List story facts for a project with optional filters."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        facts = repo.list_story_facts(project_id, fact_type=fact_type, status=status)
        return envelope_response(facts)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取故事事实列表失败: {str(e)}")


@router.get("/projects/{project_id}/story-facts/{fact_id}")
async def get_story_fact(
    request: Request, project_id: str, fact_id: str
) -> EnvelopeResponse:
    """Get a story fact with its event history."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        fact = repo.get_story_fact(fact_id)
        if not fact:
            return error_response("FACT_NOT_FOUND", f"事实 {fact_id} 不存在")

        if fact["project_id"] != project_id:
            return error_response("FACT_NOT_FOUND", "事实不属于该项目")

        events = repo.list_fact_events(project_id, fact_id=fact_id)
        result = {**fact, "events": events}
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取事实详情失败: {str(e)}")


@router.get("/projects/{project_id}/fact-events")
async def list_fact_events(
    request: Request,
    project_id: str,
    chapter_number: int | None = None,
) -> EnvelopeResponse:
    """List story fact events for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        events = repo.list_fact_events(project_id, chapter_number=chapter_number)
        return envelope_response(events)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取事实事件列表失败: {str(e)}")


@router.put("/projects/{project_id}/story-facts/{fact_id}")
async def update_story_fact(
    request: Request,
    project_id: str,
    fact_id: str,
    body: StoryFactUpdateRequest,
) -> EnvelopeResponse:
    """Update a story fact with manual correction logging."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        fact = repo.get_story_fact(fact_id)
        if not fact:
            return error_response("FACT_NOT_FOUND", f"事实 {fact_id} 不存在")

        if fact["project_id"] != project_id:
            return error_response("FACT_NOT_FOUND", "事实不属于该项目")

        update_data = {}
        for key in (
            "value_json",
            "status",
            "confidence",
            "subject",
            "attribute",
            "unit",
            "scope",
        ):
            val = getattr(body, key, None)
            if val is not None:
                update_data[key] = val

        if not update_data:
            return envelope_response(fact)

        # Capture before state for event
        before_json = json.dumps(
            {
                "value_json": fact.get("value_json"),
                "status": fact.get("status"),
                "confidence": fact.get("confidence"),
                "subject": fact.get("subject"),
                "attribute": fact.get("attribute"),
            },
            ensure_ascii=False,
        )

        updated = repo.update_story_fact(fact_id, update_data)

        # Log correction event
        after_json = json.dumps(
            {
                "value_json": updated.get("value_json") if updated else None,
                "status": updated.get("status") if updated else None,
                "confidence": updated.get("confidence") if updated else None,
                "subject": updated.get("subject") if updated else None,
                "attribute": updated.get("attribute") if updated else None,
            },
            ensure_ascii=False,
        )

        repo.create_fact_event(
            project_id,
            chapter_number=fact.get("last_changed_chapter") or 0,
            agent_id="user_correction",
            event_type="manual_correction",
            fact_id=fact_id,
            before_json=before_json,
            after_json=after_json,
            rationale=body.correction_note or "用户手动修正",
            validation_status="validated",
        )

        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新事实失败: {str(e)}")


# ---------------------------------------------------------------------------
# Canonical body-style routes (API Contract §4)
# ---------------------------------------------------------------------------


class FactCorrectRequest(BaseModel):
    """Canonical body for fact correction action."""

    project_id: str
    fact_id: str
    value_json: str | None = None
    correction_note: str | None = None


@router.get("/facts")
async def list_facts_canonical(
    request: Request,
    project_id: str,
    fact_type: str | None = None,
    status: str | None = None,
) -> EnvelopeResponse:
    """Canonical list route for story facts (project_id as query param)."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        facts = repo.list_story_facts(project_id, fact_type=fact_type, status=status)
        return envelope_response(facts)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取故事事实列表失败: {str(e)}")


@router.get("/facts/{fact_key}/history")
async def get_fact_history_canonical(
    request: Request,
    fact_key: str,
    project_id: str,
) -> EnvelopeResponse:
    """Canonical route: get fact detail + event history by fact_key."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        fact = repo.get_story_fact_by_key(project_id, fact_key)
        if not fact:
            return error_response("FACT_NOT_FOUND", f"事实 '{fact_key}' 不存在")

        events = repo.list_fact_events(project_id, fact_id=fact["id"])
        result = {**fact, "events": events}
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取事实历史失败: {str(e)}")


@router.post("/facts/correct")
async def correct_fact_canonical(
    request: Request, body: FactCorrectRequest
) -> EnvelopeResponse:
    """Canonical body-style route for fact correction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        fact = repo.get_story_fact(body.fact_id)
        if not fact:
            return error_response("FACT_NOT_FOUND", f"事实 {body.fact_id} 不存在")

        if fact["project_id"] != body.project_id:
            return error_response("FACT_NOT_FOUND", "事实不属于该项目")

        update_data = {}
        if body.value_json is not None:
            update_data["value_json"] = body.value_json

        if not update_data:
            return envelope_response(fact)

        before_json = json.dumps(
            {
                "value_json": fact.get("value_json"),
                "status": fact.get("status"),
                "confidence": fact.get("confidence"),
                "subject": fact.get("subject"),
                "attribute": fact.get("attribute"),
            },
            ensure_ascii=False,
        )

        updated = repo.update_story_fact(body.fact_id, update_data)

        after_json = json.dumps(
            {
                "value_json": updated.get("value_json") if updated else None,
                "status": updated.get("status") if updated else None,
                "confidence": updated.get("confidence") if updated else None,
                "subject": updated.get("subject") if updated else None,
                "attribute": updated.get("attribute") if updated else None,
            },
            ensure_ascii=False,
        )

        repo.create_fact_event(
            body.project_id,
            chapter_number=fact.get("last_changed_chapter") or 0,
            agent_id="user_correction",
            event_type="manual_correction",
            fact_id=body.fact_id,
            before_json=before_json,
            after_json=after_json,
            rationale=body.correction_note or "用户手动修正",
            validation_status="validated",
        )

        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"修正事实失败: {str(e)}")
