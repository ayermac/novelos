"""v6.10.19: Store aggregation layer over Repository facade.

Provides cross-repo aggregation queries. Store holds a single Repository
instance and combines multiple repo methods into unified query APIs.
Does NOT replace Repository - dual-track coexistence.
"""

from .base import BaseStore
from .progress import ProgressStore
from .drafts import DraftStore
from .world import WorldStore

__all__ = ["BaseStore", "ProgressStore", "DraftStore", "WorldStore"]
