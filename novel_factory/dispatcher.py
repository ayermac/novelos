"""Dispatcher — runtime orchestrator for chapter production.

All production logic is encapsulated here. External code must NOT
directly orchestrate Agent calls or modify workflow state.

This module provides a backward-compatible ``Dispatcher`` class composed
from domain-specific mixin modules under ``dispatch/``.
"""

from __future__ import annotations

from .dispatch.base import BaseDispatcher, STATUS_ROUTE, REVISION_ROUTE, LEGAL_RESUME_STATUSES  # noqa: F401
from .dispatch.chapter import ChapterDispatchMixin
from .dispatch.sidecar import SidecarDispatchMixin
from .dispatch.batch import BatchDispatchMixin
from .dispatch.revision import RevisionDispatchMixin
from .dispatch.continuity_gate import ContinuityGateDispatchMixin
from .dispatch.queue import QueueDispatchMixin
from .dispatch.serial import SerialDispatchMixin
from .dispatch.review_workbench import ReviewWorkbenchDispatchMixin


class Dispatcher(
    ChapterDispatchMixin,
    SidecarDispatchMixin,
    BatchDispatchMixin,
    RevisionDispatchMixin,
    ContinuityGateDispatchMixin,
    QueueDispatchMixin,
    SerialDispatchMixin,
    ReviewWorkbenchDispatchMixin,
    BaseDispatcher,
):
    """Backward-compatible dispatcher facade combining all domain mixins."""

    pass
