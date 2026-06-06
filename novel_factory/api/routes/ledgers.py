"""Creative ledgers API endpoints for v6.9.0.

Provides endpoints for retrieving creative ledger snapshots:
- Reader promise ledger
- Power growth ledger
- Character arc ledger
- Mystery reveal ledger
- Conflict ledger
- Payoff ledger
- Style fatigue ledger
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request, HTTPException

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ...db.repository import Repository

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Helper Functions ──────────────────────────────────────────────────────


def _get_repo(request: Request) -> Repository:
    """Get repository from request state."""
    return request.state.repo


# ── Ledger types ─────────────────────────────────────────────────────────

LEDGER_TYPES = [
    "reader_promise",
    "power_growth",
    "character_arc",
    "mystery_reveal",
    "conflict",
    "payoff",
    "style_fatigue",
]


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/ledgers")
async def get_all_ledgers(
    project_id: str,
    request: Request,
) -> EnvelopeResponse:
    """Get latest snapshot for all creative ledger types.

    Returns a summary of all 7 ledger types for the project,
    showing the current state of narrative tracking.

    Args:
        project_id: Project identifier

    Returns:
        Dict with all ledger summaries
    """
    repo = _get_repo(request)

    try:
        ledgers = {}
        for ledger_type in LEDGER_TYPES:
            try:
                # Get latest snapshot
                snapshot = repo.get_latest_creative_ledger(project_id, ledger_type)
                if snapshot:
                    ledger_data = _parse_ledger_data(snapshot.get("ledger_data", "{}"))
                    ledgers[ledger_type] = {
                        "chapter_number": snapshot.get("chapter_number"),
                        "entries_count": len(ledger_data.get("entries", [])),
                        "summary": ledger_data.get("summary", ""),
                        "updated_at": snapshot.get("created_at"),
                    }
                else:
                    ledgers[ledger_type] = {
                        "chapter_number": None,
                        "entries_count": 0,
                        "summary": "无数据",
                        "updated_at": None,
                    }
            except Exception as e:
                logger.warning(f"Failed to load {ledger_type}: {e}")
                ledgers[ledger_type] = {
                    "chapter_number": None,
                    "entries_count": 0,
                    "summary": f"加载失败: {str(e)}",
                    "updated_at": None,
                }

        return envelope_response({
            "project_id": project_id,
            "ledgers": ledgers,
            "ledger_types": LEDGER_TYPES,
        })

    except Exception as e:
        logger.error(f"Failed to get ledgers: {e}")
        return error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to retrieve ledgers: {str(e)}",
        )


@router.get("/projects/{project_id}/ledgers/{ledger_type}")
async def get_ledger_history(
    project_id: str,
    ledger_type: str,
    request: Request,
) -> EnvelopeResponse:
    """Get history for a specific ledger type.

    Returns all snapshots for the specified ledger type,
    showing how the ledger evolved over chapters.

    Args:
        project_id: Project identifier
        ledger_type: Ledger type (e.g., reader_promise, power_growth)

    Returns:
        List of ledger snapshots
    """
    if ledger_type not in LEDGER_TYPES:
        return error_response(
            code="INVALID_REQUEST",
            message=f"Invalid ledger type: {ledger_type}. Must be one of: {', '.join(LEDGER_TYPES)}",
        )

    repo = _get_repo(request)

    try:
        # Get all snapshots for this ledger type
        snapshots = repo.get_creative_ledger_history(project_id, ledger_type)

        history = []
        for snapshot in snapshots:
            ledger_data = _parse_ledger_data(snapshot.get("ledger_data", "{}"))
            history.append({
                "chapter_number": snapshot.get("chapter_number"),
                "entries_count": len(ledger_data.get("entries", [])),
                "summary": ledger_data.get("summary", ""),
                "entries": ledger_data.get("entries", []),
                "patch_from_previous": snapshot.get("patch_from_previous"),
                "created_at": snapshot.get("created_at"),
            })

        return envelope_response({
            "project_id": project_id,
            "ledger_type": ledger_type,
            "history": history,
            "total_snapshots": len(history),
        })

    except Exception as e:
        logger.error(f"Failed to get ledger history: {e}")
        return error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to retrieve ledger history: {str(e)}",
        )


@router.get("/projects/{project_id}/ledgers/{ledger_type}/chapters/{chapter_number}")
async def get_ledger_at_chapter(
    project_id: str,
    ledger_type: str,
    chapter_number: int,
    request: Request,
) -> EnvelopeResponse:
    """Get ledger snapshot at a specific chapter.

    Returns the ledger state after the specified chapter was processed.

    Args:
        project_id: Project identifier
        ledger_type: Ledger type
        chapter_number: Chapter number

    Returns:
        Ledger snapshot at the specified chapter
    """
    if ledger_type not in LEDGER_TYPES:
        return error_response(
            code="INVALID_REQUEST",
            message=f"Invalid ledger type: {ledger_type}",
        )

    repo = _get_repo(request)

    try:
        snapshot = repo.get_creative_ledger(project_id, chapter_number, ledger_type)
        if not snapshot:
            return envelope_response({
                "project_id": project_id,
                "ledger_type": ledger_type,
                "chapter_number": chapter_number,
                "snapshot": None,
                "note": f"No {ledger_type} ledger snapshot at chapter {chapter_number}",
            })

        ledger_data = _parse_ledger_data(snapshot.get("ledger_data", "{}"))

        return envelope_response({
            "project_id": project_id,
            "ledger_type": ledger_type,
            "chapter_number": chapter_number,
            "snapshot": {
                "entries": ledger_data.get("entries", []),
                "summary": ledger_data.get("summary", ""),
                "patch_from_previous": snapshot.get("patch_from_previous"),
                "created_at": snapshot.get("created_at"),
            },
        })

    except Exception as e:
        logger.error(f"Failed to get ledger snapshot: {e}")
        return error_response(
            code="INTERNAL_ERROR",
            message=f"Failed to retrieve ledger snapshot: {str(e)}",
        )


# ── Helper functions ─────────────────────────────────────────────────────


def _parse_ledger_data(data: str | dict) -> dict:
    """Parse ledger data from string or dict."""
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {}
    return {}