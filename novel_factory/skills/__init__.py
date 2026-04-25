"""Skills module for v2.1 quality plugin system."""

from .base import BaseSkill, ContextSkill, ReportSkill, TransformSkill, ValidatorSkill
from .registry import SkillRegistry
from .ai_style_detector import AIStyleDetectorSkill
from .humanizer_zh import HumanizerZhSkill
from .narrative_quality_scorer import NarrativeQualityScorer

__all__ = [
    "BaseSkill",
    "TransformSkill",
    "ValidatorSkill",
    "ContextSkill",
    "ReportSkill",
    "SkillRegistry",
    "AIStyleDetectorSkill",
    "HumanizerZhSkill",
    "NarrativeQualityScorer",
]
