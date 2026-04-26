"""Acceptance matrix API endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/acceptance")
async def get_acceptance_matrix(request: Request) -> EnvelopeResponse:
    """Get acceptance matrix with all capabilities.

    Returns capability list with status, routes, and notes.
    """
    try:
        from ..acceptance import CAPABILITIES

        capabilities = []
        for cap in CAPABILITIES:
            capabilities.append({
                "capability_id": cap.capability_id,
                "label": cap.label,
                "web_route": cap.web_route,
                "cli_command": cap.cli_command,
                "success_test": cap.success_test,
                "status": cap.status,
                "notes": cap.notes,
            })

        # Summary
        total = len(capabilities)
        passed = sum(1 for c in capabilities if c["status"] == "pass")
        failed = sum(1 for c in capabilities if c["status"] == "fail")

        return envelope_response({
            "capabilities": capabilities,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "0%",
            },
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取验收矩阵失败: {str(e)}")
