"""Serial plan routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Form

from ..deps import get_repo, render, safe_error_message, build_dispatcher_for_web

router = APIRouter()


@router.get("")
async def serial_status(request: Request):
    """Show serial plans."""
    try:
        repo = get_repo(request)
        # List all serial plans (simplified - would need a repo method)
        # For now, show placeholder
        return render(request, "serial.html", {"plans": []})
    except Exception as e:
        return render(request, "serial.html", {"error": safe_error_message(e)})


@router.post("/create")
async def serial_create(
    request: Request,
    project_id: str = Form(...),
    name: str = Form(...),
    start_chapter: int = Form(...),
    target_chapter: int = Form(...),
    batch_size: int = Form(5),
):
    """Create a serial plan."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.create_serial_plan(
            project_id=project_id,
            name=name,
            start_chapter=start_chapter,
            target_chapter=target_chapter,
            batch_size=batch_size,
        )
        return render(request, "serial.html", {"result": result})
    except Exception as e:
        return render(request, "serial.html", {"error": safe_error_message(e)})


@router.post("/enqueue-next")
async def serial_enqueue_next(request: Request, serial_plan_id: str = Form(...)):
    """Enqueue next batch for serial plan."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.enqueue_serial_next(serial_plan_id=serial_plan_id)
        return render(request, "serial.html", {"result": result})
    except Exception as e:
        return render(request, "serial.html", {"error": safe_error_message(e)})


@router.post("/advance")
async def serial_advance(
    request: Request,
    serial_plan_id: str = Form(...),
    decision: str = Form(...),
    notes: str = Form(""),
):
    """Advance serial plan with decision."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.advance_serial_plan(
            serial_plan_id=serial_plan_id,
            decision=decision,
            notes=notes,
        )
        return render(request, "serial.html", {"result": result})
    except Exception as e:
        return render(request, "serial.html", {"error": safe_error_message(e)})


@router.post("/pause")
async def serial_pause(request: Request, serial_plan_id: str = Form(...)):
    """Pause a serial plan."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.pause_serial_plan(serial_plan_id=serial_plan_id)
        return render(request, "serial.html", {"result": result})
    except Exception as e:
        return render(request, "serial.html", {"error": safe_error_message(e)})


@router.post("/resume")
async def serial_resume(request: Request, serial_plan_id: str = Form(...)):
    """Resume a paused serial plan."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.resume_serial_plan(serial_plan_id=serial_plan_id)
        return render(request, "serial.html", {"result": result})
    except Exception as e:
        return render(request, "serial.html", {"error": safe_error_message(e)})


@router.post("/cancel")
async def serial_cancel(
    request: Request,
    serial_plan_id: str = Form(...),
    reason: str = Form(""),
):
    """Cancel a serial plan."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.cancel_serial_plan(serial_plan_id=serial_plan_id, reason=reason)
        return render(request, "serial.html", {"result": result})
    except Exception as e:
        return render(request, "serial.html", {"error": safe_error_message(e)})
