"""Health check API endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from ..envelope import envelope_response, EnvelopeResponse
from ...version import get_version

router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> EnvelopeResponse:
    """Health check endpoint.

    Returns basic system status without exposing sensitive information.
    """
    from ..deps import get_llm_mode, get_db_path

    llm_mode = get_llm_mode(request)
    db_path = get_db_path(request)

    return envelope_response({
        "status": "ok",
        "version": get_version(),
        "llm_mode": llm_mode,
        "db_connected": bool(db_path),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
