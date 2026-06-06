"""v6.9.0: Specialized editor lenses for multi-perspective chapter review.

Each lens focuses on one dimension of quality and produces an EditorLensReport.
The ChiefEditor aggregates all lens reports into a final pass/fail decision.
"""

from .type_editor import TypeEditorLens
from .continuity_editor import ContinuityEditorLens
from .commercial_editor import CommercialEditorLens
from .pacing_editor import PacingEditorLens
from .character_editor import CharacterEditorLens
from .mystery_editor import MysteryEditorLens
from .style_editor import StyleEditorLens
from .chief_editor import ChiefEditor

__all__ = [
    "TypeEditorLens",
    "ContinuityEditorLens",
    "CommercialEditorLens",
    "PacingEditorLens",
    "CharacterEditorLens",
    "MysteryEditorLens",
    "StyleEditorLens",
    "ChiefEditor",
]
