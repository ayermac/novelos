"""Production queue routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Form

from ..deps import get_repo, render, safe_error_message, build_dispatcher_for_web

router = APIRouter()


@router.get("")
async def queue_status(request: Request):
    """Show queue status."""
    try:
        repo = get_repo(request)
        items = repo.list_queue_items(limit=50)
        return render(request, "queue.html", {"items": items})
    except Exception as e:
        return render(request, "queue.html", {"error": safe_error_message(e)})


@router.post("/enqueue")
async def queue_enqueue(
    request: Request,
    project_id: str = Form(...),
    from_chapter: int = Form(...),
    to_chapter: int = Form(...),
    priority: int = Form(100),
):
    """Enqueue a batch production request."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.enqueue_batch(
            project_id=project_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            priority=priority,
        )
        return render(request, "queue.html", {"result": result})
    except Exception as e:
        return render(request, "queue.html", {"error": safe_error_message(e)})


@router.post("/run")
async def queue_run(request: Request, limit: int = Form(1)):
    """Execute pending queue items."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.run_queue(limit=limit)
        return render(request, "queue.html", {"result": result})
    except Exception as e:
        return render(request, "queue.html", {"error": safe_error_message(e)})


@router.post("/pause")
async def queue_pause(request: Request, queue_id: str = Form(...)):
    """Pause a queue item."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.pause_queue_item(queue_id=queue_id)
        return render(request, "queue.html", {"result": result})
    except Exception as e:
        return render(request, "queue.html", {"error": safe_error_message(e)})


@router.post("/resume")
async def queue_resume(request: Request, queue_id: str = Form(...)):
    """Resume a paused queue item."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.resume_queue_item(queue_id=queue_id)
        return render(request, "queue.html", {"result": result})
    except Exception as e:
        return render(request, "queue.html", {"error": safe_error_message(e)})


@router.post("/retry")
async def queue_retry(request: Request, queue_id: str = Form(...)):
    """Retry a failed queue item."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.retry_queue_item(queue_id=queue_id)
        return render(request, "queue.html", {"result": result})
    except Exception as e:
        return render(request, "queue.html", {"error": safe_error_message(e)})


@router.post("/recover")
async def queue_recover(request: Request, queue_id: str = Form(...)):
    """Recover a stuck queue item."""
    try:
        dispatcher = build_dispatcher_for_web(request)
        result = dispatcher.recover_queue_item(queue_id=queue_id)
        return render(request, "queue.html", {"result": result})
    except Exception as e:
        return render(request, "queue.html", {"error": safe_error_message(e)})
