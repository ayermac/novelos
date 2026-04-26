"""Acceptance Matrix route for Web UI."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import render
from ..acceptance_matrix import get_acceptance_matrix

router = APIRouter()


@router.get("")
async def acceptance_page(request: Request):
    """Display the acceptance matrix page.
    
    Shows all capabilities with their acceptance status,
    test coverage, and safety checks.
    """
    matrix = get_acceptance_matrix()
    
    return render(
        request,
        "acceptance.html",
        {
            "capabilities": matrix["capabilities"],
            "summary": matrix["summary"],
        },
    )
