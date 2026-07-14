"""Genesis API Pydantic models for request/response bodies."""

from __future__ import annotations

from pydantic import BaseModel


class GenesisGenerateRequest(BaseModel):
    """Input for project genesis generation."""

    project_id: str = ""
    title: str = ""
    genre: str = ""
    premise: str = ""
    target_chapters: int = 10
    target_words: int = 30000
    target_audience: str = ""
    style_preference: str = ""
    constraints: str = ""


class GenesisApproveRequest(BaseModel):
    """Canonical body for genesis approve action."""

    project_id: str
    genesis_id: str


class GenesisRejectRequest(BaseModel):
    """Canonical body for genesis reject action."""

    project_id: str
    genesis_id: str


class GenesisApproveWithForceRequest(BaseModel):
    """Canonical body for genesis approve with optional force flag."""

    project_id: str
    genesis_id: str
    force_apply: bool = False
    confirm_quality_risk: bool = False
    # v6.8.5: Chapter cleanup mode for re-genesis
    chapter_cleanup_mode: str | None = None


class GenesisForceApplyBody(BaseModel):
    """Body for path-style approve route with optional force flag."""

    force_apply: bool = False
    confirm_quality_risk: bool = False
    # v6.8.5: Chapter cleanup mode for re-genesis
    # "keep_published" - Keep published/reviewed/awaiting_publish chapters, reset others
    # "reset_all" - Reset ALL chapters including terminal ones
    # "delete_all" - Delete ALL chapters
    # None - No chapter cleanup (default, preserves all chapters)
    chapter_cleanup_mode: str | None = None