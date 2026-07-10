"""v6.10.19: Store aggregation layer over Repository facade.

8 Stores providing cross-repo aggregation queries:
  Phase A: ProgressStore, DraftStore, WorldStore (v6.10.19)
  Phase B: SummaryStore, CharacterStore, OutlineStore, SignalStore, CheckpointStore (v6.10.19)
"""

from .base import BaseStore
from .progress import ProgressStore
from .drafts import DraftStore
from .world import WorldStore
from .summaries import SummaryStore
from .characters import CharacterStore
from .outline import OutlineStore
from .signals import SignalStore
from .checkpoints import CheckpointStore

__all__ = [
    "BaseStore",
    "ProgressStore",
    "DraftStore",
    "WorldStore",
    "SummaryStore",
    "CharacterStore",
    "OutlineStore",
    "SignalStore",
    "CheckpointStore",
]
