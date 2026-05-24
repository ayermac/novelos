"""Health check API endpoint."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request

from ..envelope import envelope_response, EnvelopeResponse
from ...version import get_version

router = APIRouter()

_START_TIME = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _get_startup_metadata() -> dict:
    """Return non-sensitive process startup metadata for mismatch diagnosis."""
    return {
        "started_at": _START_TIME,
        "python": sys.executable,
        "source_root": str(Path(__file__).resolve().parents[3]),
        "cwd": os.getcwd(),
    }


@router.get("/health")
async def health_check(request: Request) -> EnvelopeResponse:
    """Health check endpoint.

    Returns basic system status plus startup metadata for production mismatch diagnosis.
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
        "startup": _get_startup_metadata(),
    })
