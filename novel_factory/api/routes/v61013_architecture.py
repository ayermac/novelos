"""API routes for v6.10.13 architecture hardening features.

Exposes diagnosis, budget, steer, and signal management endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v61013", tags=["v6.10.13 Architecture"])


# ── Request/Response Models ──


class DiagnosisRequest(BaseModel):
    project_id: str


class DiagnosisFinding(BaseModel):
    dimension: str
    severity: str
    confidence: str
    message: str
    evidence: str = ""
    suggestion: str = ""
    auto_level: str = "none"


class DiagnosisResponse(BaseModel):
    project_id: str
    findings: list[DiagnosisFinding]
    total: int


class BudgetStatusResponse(BaseModel):
    state: str
    total_cost: float
    limit_usd: float
    remaining_usd: float
    usage_percent: float
    zero_streak: int


class BudgetUpdateRequest(BaseModel):
    limit_usd: float


class SteerRequest(BaseModel):
    project_id: str
    text: str


class SteerResponse(BaseModel):
    status: str
    message: str


class SignalStatusResponse(BaseModel):
    project_id: str
    signals: list[str]


class StyleStatsRequest(BaseModel):
    project_id: str
    chapter_limit: int = 100


class StyleStatsResponse(BaseModel):
    project_id: str
    chapter_count: int
    ai_tic_counts: dict[str, Any] = {}
    high_freq_phrases: list[dict[str, Any]] = []
    repeated_sentences: list[dict[str, Any]] = []
    ending_patterns: dict[str, Any] = {}
    opening_time_words: dict[str, Any] = {}
    title_format: dict[str, Any] = {}


# ── Endpoints ──


@router.post("/diagnosis", response_model=DiagnosisResponse)
async def run_diagnosis(request: DiagnosisRequest):
    """Run diagnosis on a project."""
    from ...db.repository import Repository
    from ...diag.diagnosis import DiagnosisSystem, Snapshot

    repo = Repository()
    diag = DiagnosisSystem()

    # Build snapshot
    snapshot = Snapshot(project_id=request.project_id)

    try:
        project = repo.get_project(request.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        snapshot.phase = project.get("phase", "")

        # Load progress
        progress = repo.get_progress(request.project_id)
        if progress:
            snapshot.current_chapter = progress.get("current_chapter", 0)
            snapshot.total_chapters = progress.get("total_chapters", 0)
            snapshot.completed_chapters = progress.get("completed_chapters", [])

        # Load characters
        snapshot.characters = repo.get_characters(request.project_id) or []

        # Load world settings
        snapshot.world_settings = repo.list_world_settings(request.project_id) or []

        # Load foreshadows
        snapshot.foreshadows = repo.list_plot_holes(request.project_id) or []

    except Exception as e:
        logger.error("Diagnosis: failed to load data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Run diagnosis
    findings = diag.diagnose(snapshot)

    return DiagnosisResponse(
        project_id=request.project_id,
        findings=[f.to_dict() for f in findings],
        total=len(findings),
    )


@router.get("/budget/{project_id}", response_model=BudgetStatusResponse)
async def get_budget_status(project_id: str):
    """Get budget status for a project."""
    # This would integrate with the actual budget system
    # For now, return a placeholder
    return BudgetStatusResponse(
        state="normal",
        total_cost=0.0,
        limit_usd=100.0,
        remaining_usd=100.0,
        usage_percent=0.0,
        zero_streak=0,
    )


@router.put("/budget/{project_id}")
async def update_budget(project_id: str, request: BudgetUpdateRequest):
    """Update budget limit for a project."""
    # This would integrate with the actual budget system
    return {"status": "ok", "limit_usd": request.limit_usd}


@router.post("/steer", response_model=SteerResponse)
async def submit_steer(request: SteerRequest):
    """Submit user intervention."""
    from ...db.repository import Repository
    from ...steer.steer_manager import SteerManager

    repo = Repository()
    manager = SteerManager(repo)

    result = manager.steer(
        project_id=request.project_id,
        text=request.text,
        is_running=False,
    )

    return SteerResponse(
        status=result.get("status", "error"),
        message=result.get("message", "Unknown error"),
    )


@router.get("/signals/{project_id}", response_model=SignalStatusResponse)
async def list_signals(project_id: str):
    """List active signals for a project."""
    from ...dispatch.signal_store import SignalStore

    store = SignalStore(".")
    signals = store.list_signals(project_id)

    return SignalStatusResponse(
        project_id=project_id,
        signals=signals,
    )


@router.delete("/signals/{project_id}")
async def clear_signals(project_id: str):
    """Clear all signals for a project."""
    from ...dispatch.signal_store import SignalStore

    store = SignalStore(".")
    store.clear_all_signals(project_id)

    return {"status": "ok", "project_id": project_id}


@router.post("/style-stats", response_model=StyleStatsResponse)
async def compute_style_stats(request: StyleStatsRequest):
    """Compute style statistics for a project."""
    from ...db.repository import Repository
    from ...stats.style_stats import StyleStats

    repo = Repository()
    stats = StyleStats()

    try:
        # Load chapters
        chapters = []
        outlines = repo.list_outlines(request.project_id) or []

        for outline in outlines[:request.chapter_limit]:
            chapter_num = outline.get("chapter_number")
            if chapter_num:
                chapter = repo.get_chapter(request.project_id, chapter_num)
                if chapter and chapter.get("content"):
                    chapters.append(chapter["content"])

        if not chapters:
            return StyleStatsResponse(
                project_id=request.project_id,
                chapter_count=0,
            )

        # Load titles
        titles = [o.get("title", "") for o in outlines[:request.chapter_limit]]

        # Compute stats
        result = stats.compute(chapters, titles)

        if not result:
            return StyleStatsResponse(
                project_id=request.project_id,
                chapter_count=len(chapters),
            )

        return StyleStatsResponse(
            project_id=request.project_id,
            chapter_count=len(chapters),
            **result.to_dict(),
        )

    except Exception as e:
        logger.error("StyleStats: failed to compute: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
