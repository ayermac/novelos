"""Repository pattern for database access in Novel Factory.

All SQL is encapsulated here. Agents must NOT write raw SQL.

This module provides a backward-compatible ``Repository`` class composed
from domain-specific mixin modules under ``db/repositories/``.
"""

from __future__ import annotations

from .repositories.base import BaseRepository
from .repositories.project import ProjectRepositoryMixin
from .repositories.chapter import ChapterRepositoryMixin
from .repositories.workflow import WorkflowRepositoryMixin
from .repositories.artifact import ArtifactRepositoryMixin
from .repositories.quality import QualityRepositoryMixin
from .repositories.sidecar import SidecarRepositoryMixin
from .repositories.batch import BatchRepositoryMixin
from .repositories.revision import RevisionRepositoryMixin
from .repositories.continuity_gate import ContinuityGateRepositoryMixin
from .repositories.queue import QueueRepositoryMixin
from .repositories.serial import SerialRepositoryMixin
from .repositories.review_workbench import ReviewWorkbenchRepositoryMixin
from .repositories.style_bible import StyleBibleRepositoryMixin
from .repositories.style_gate import StyleGateRepositoryMixin
from .repositories.style_sample import StyleSampleRepositoryMixin
from .repositories.world_setting import WorldSettingRepositoryMixin
from .repositories.character import CharacterRepositoryMixin
from .repositories.outline import OutlineRepositoryMixin
from .repositories.faction import FactionRepositoryMixin
from .repositories.plot_hole import PlotHoleRepositoryMixin
from .repositories.instruction import InstructionRepositoryMixin
from .repositories.genesis import GenesisRepositoryMixin
from .repositories.memory_update import MemoryUpdateRepositoryMixin
from .repositories.story_fact import StoryFactRepositoryMixin

# Backward-compatible re-exports
from ..validators.chapter_checker import count_words  # noqa: F401


class Repository(
    WorldSettingRepositoryMixin,
    CharacterRepositoryMixin,
    OutlineRepositoryMixin,
    FactionRepositoryMixin,
    PlotHoleRepositoryMixin,
    InstructionRepositoryMixin,
    ProjectRepositoryMixin,
    ChapterRepositoryMixin,
    WorkflowRepositoryMixin,
    ArtifactRepositoryMixin,
    QualityRepositoryMixin,
    SidecarRepositoryMixin,
    BatchRepositoryMixin,
    RevisionRepositoryMixin,
    ContinuityGateRepositoryMixin,
    QueueRepositoryMixin,
    SerialRepositoryMixin,
    ReviewWorkbenchRepositoryMixin,
    StyleBibleRepositoryMixin,
    StyleGateRepositoryMixin,
    StyleSampleRepositoryMixin,
    GenesisRepositoryMixin,
    MemoryUpdateRepositoryMixin,
    StoryFactRepositoryMixin,
    BaseRepository,
):
    """Backward-compatible repository facade combining all domain mixins."""

    pass
