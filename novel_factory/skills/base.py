"""Skill base classes for v2.1 plugin system.

All skills must inherit from BaseSkill and implement the run() method.
Skills return unified envelope: {ok: bool, error: str|null, data: dict}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# v2.2: Whitelist of builtin skill classes
BUILTIN_SKILLS = {
    "HumanizerZhSkill": None,  # Will be imported lazily
    "AIStyleDetectorSkill": None,
    "NarrativeQualityScorer": None,
    "ImportedInstructionSkill": None,  # v3.8: imported skill handler
    "StyleBibleCheckerSkill": None,  # v4.0: style bible checker
    "ChapterObjectiveCheckerSkill": None,
    "SceneConflictCheckerSkill": None,
    "EventCoverageCheckerSkill": None,
    "MemoryPatchValidatorSkill": None,
    "ShowDontTellValidator": None,  # v6.4.3
    "InfoDumpDetector": None,  # v6.4.3
    "SceneTextureChecker": None,  # v6.4.3
    "DialogueNaturalnessChecker": None,  # v6.4.3
    "ContinuityGateSkill": None,  # v6.8.0
    "ChapterSeamSkill": None,  # v6.8.0
    "DeathPenaltySkill": None,  # v6.8.0
    "WordCountGateSkill": None,  # v6.8.0
    "FactLockSkill": None,  # v6.8.0
}


def _get_skill_class(class_name: str):
    """Get skill class by name (lazy import)."""
    if class_name not in BUILTIN_SKILLS:
        return None
    
    # Lazy import to avoid circular dependencies
    if class_name == "HumanizerZhSkill":
        from .humanizer_zh import HumanizerZhSkill
        return HumanizerZhSkill
    elif class_name == "AIStyleDetectorSkill":
        from .ai_style_detector import AIStyleDetectorSkill
        return AIStyleDetectorSkill
    elif class_name == "NarrativeQualityScorer":
        from .narrative_quality_scorer import NarrativeQualityScorer
        return NarrativeQualityScorer
    elif class_name == "ImportedInstructionSkill":
        from .import_bridge import ImportedInstructionSkill
        return ImportedInstructionSkill
    elif class_name == "StyleBibleCheckerSkill":
        from .style_bible_checker import StyleBibleCheckerSkill
        return StyleBibleCheckerSkill
    elif class_name == "ChapterObjectiveCheckerSkill":
        from .agent_validators import ChapterObjectiveCheckerSkill
        return ChapterObjectiveCheckerSkill
    elif class_name == "SceneConflictCheckerSkill":
        from .agent_validators import SceneConflictCheckerSkill
        return SceneConflictCheckerSkill
    elif class_name == "EventCoverageCheckerSkill":
        from .agent_validators import EventCoverageCheckerSkill
        return EventCoverageCheckerSkill
    elif class_name == "MemoryPatchValidatorSkill":
        from .agent_validators import MemoryPatchValidatorSkill
        return MemoryPatchValidatorSkill
    elif class_name == "ShowDontTellValidator":
        from .show_dont_tell_validator import ShowDontTellValidator
        return ShowDontTellValidator
    elif class_name == "InfoDumpDetector":
        from .info_dump_detector import InfoDumpDetector
        return InfoDumpDetector
    elif class_name == "SceneTextureChecker":
        from .scene_texture_checker import SceneTextureChecker
        return SceneTextureChecker
    elif class_name == "DialogueNaturalnessChecker":
        from .dialogue_naturalness_checker import DialogueNaturalnessChecker
        return DialogueNaturalnessChecker
    elif class_name == "ContinuityGateSkill":
        from .continuity_gate_skill import ContinuityGateSkill
        return ContinuityGateSkill
    elif class_name == "ChapterSeamSkill":
        from .chapter_seam_skill import ChapterSeamSkill
        return ChapterSeamSkill
    elif class_name == "DeathPenaltySkill":
        from .death_penalty_skill import DeathPenaltySkill
        return DeathPenaltySkill
    elif class_name == "WordCountGateSkill":
        from .word_count_gate_skill import WordCountGateSkill
        return WordCountGateSkill
    elif class_name == "FactLockSkill":
        from .fact_lock_skill import FactLockSkill
        return FactLockSkill

    return None


class BaseSkill(ABC):
    """Base class for all skills.
    
    Every skill must have:
    - skill_id: unique identifier
    - skill_type: one of transform/validator/context/report
    - version: skill version
    - enabled: whether the skill is active
    """
    
    skill_id: str
    skill_type: str
    version: str = "1.0.0"
    enabled: bool = True
    
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize skill with optional config.
        
        Args:
            config: Skill-specific configuration from skills.yaml
        """
        self.config = config or {}
    
    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the skill.
        
        Args:
            payload: Input data for the skill
            
        Returns:
            Unified envelope: {ok: bool, error: str|null, data: dict}
        """
        pass
    
    def validate_payload(self, payload: dict[str, Any]) -> bool:
        """Validate input payload.
        
        Override this method to add custom validation.
        
        Args:
            payload: Input data to validate
            
        Returns:
            True if valid, False otherwise
        """
        return True


class TransformSkill(BaseSkill):
    """Skill for text transformation (e.g., Humanizer).
    
    Transform skills modify content while preserving facts.
    
    Input payload should contain:
    - content: str - the text to transform
    - context: dict - additional context
    - fact_lock: list - facts that must not be changed
    
    Output data should contain:
    - content: str - transformed text
    - changes: list - list of changes made
    - risk: str - risk level (none/low/medium/high)
    """
    
    skill_type = "transform"
    
    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Transform the content.
        
        Must preserve fact_lock and return risk assessment.
        """
        pass


class ValidatorSkill(BaseSkill):
    """Skill for quality validation (e.g., AIStyleDetector).
    
    Validator skills check content quality without modifying it.
    
    Input payload should contain:
    - content: str - the text to validate
    - context: dict - additional context
    
    Output data should contain:
    - score: int - quality score (0-100)
    - issues: list - blocking issues
    - warnings: list - non-blocking warnings
    - suggestions: list - improvement suggestions
    - blocking: bool - whether to block the content
    """
    
    skill_type = "validator"
    
    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the content.
        
        Returns quality assessment without modifying content.
        """
        pass


class ContextSkill(BaseSkill):
    """Skill for context building (e.g., platform-style-guide).
    
    Context skills generate context fragments for agents.
    
    Output data should contain:
    - fragment_name: str - name of the context fragment
    - content: str - the context content
    - priority: int - priority for context ordering
    - mandatory: bool - whether this context is mandatory
    """
    
    skill_type = "context"
    
    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Build context fragment.
        
        Returns context information for agent use.
        """
        pass


class ReportSkill(BaseSkill):
    """Skill for report generation.
    
    Report skills generate quality reports or summaries.
    
    Output is written to reports or quality_reports table.
    """
    
    skill_type = "report"
    
    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate report.
        
        Returns report data to be saved.
        """
        pass
