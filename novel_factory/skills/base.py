"""Skill base classes for v2.1 plugin system.

All skills must inherit from BaseSkill and implement the run() method.
Skills return unified envelope: {ok: bool, error: str|null, data: dict}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# v2.2: Whitelist of builtin skill classes
BUILTIN_SKILLS = {
    "HumanizerZhSkill": None,  # Will be imported lazily
    "AIStyleDetectorSkill": None,
    "NarrativeQualityScorer": None,
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
    "ForeshadowingDebtSkill": None,  # v6.8.0
    "OpeningHookChecker": None,  # v6.8.1
    "ExcitementDensityChecker": None,  # v6.8.1
    "CommercialViabilityChecker": None,  # v6.9.1
    "PacingProfileChecker": None,  # v6.9.1
    "CharacterVoiceChecker": None,  # v6.9.1
    "MysteryIntegrityChecker": None,  # v6.9.1
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
    elif class_name == "ForeshadowingDebtSkill":
        from .foreshadowing_debt_skill import ForeshadowingDebtSkill
        return ForeshadowingDebtSkill
    elif class_name == "OpeningHookChecker":
        from .opening_hook_checker import OpeningHookChecker
        return OpeningHookChecker
    elif class_name == "ExcitementDensityChecker":
        from .excitement_density_checker import ExcitementDensityChecker
        return ExcitementDensityChecker
    elif class_name == "CommercialViabilityChecker":
        from .commercial_viability_checker import CommercialViabilityChecker
        return CommercialViabilityChecker
    elif class_name == "PacingProfileChecker":
        from .pacing_profile_checker import PacingProfileChecker
        return PacingProfileChecker
    elif class_name == "CharacterVoiceChecker":
        from .character_voice_checker import CharacterVoiceChecker
        return CharacterVoiceChecker
    elif class_name == "MysteryIntegrityChecker":
        from .mystery_integrity_checker import MysteryIntegrityChecker
        return MysteryIntegrityChecker

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


# ── v6.9.1: Unified Skill Finding schema ──────────────────────────────


@dataclass
class SkillFinding:
    """Structured finding returned by a Skill.

    Every skill that performs validation/analysis should emit findings
    in this format.  ``parse_skill_findings()`` converts raw dicts into
    this dataclass for uniform downstream processing.
    """

    severity: str = "info"      # blocking | warning | info
    code: str = ""              # e.g. "AI_TRACE", "SEAM_BLOCKING"
    message: str = ""           # human-readable description
    suggestion: str = ""        # actionable fix advice

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
        }


def parse_skill_findings(data: dict[str, Any]) -> list[SkillFinding]:
    """Extract a list of ``SkillFinding`` from a skill's ``data`` dict.

    Accepts keys ``findings``, ``issues``, and ``warnings`` with varying
    formats and normalises them into the canonical ``SkillFinding`` shape.
    Non-conforming entries are silently skipped so callers don't break on
    unexpected skill output.
    """
    raw_findings: list[Any] = []

    # Primary key used by new skills
    for f in (data.get("findings") or []):
        if isinstance(f, dict):
            raw_findings.append(f)
        elif isinstance(f, str):
            raw_findings.append({"message": f, "severity": "info"})

    # Legacy keys from older skills / QualityHub
    for key, default_severity in [("issues", "blocking"), ("warnings", "warning")]:
        for f in (data.get(key) or []):
            if isinstance(f, dict):
                raw_findings.append(f)
            elif isinstance(f, str):
                raw_findings.append({"message": f, "severity": default_severity})

    result: list[SkillFinding] = []
    for f in raw_findings:
        message = str(f.get("message", f.get("text", "")))
        if not message:
            continue
        result.append(SkillFinding(
            severity=str(f.get("severity", "info")),
            code=str(f.get("code", "")),
            message=message,
            suggestion=str(f.get("suggestion", "")),
        ))

    return result


# Severity ordering for sorting: lower number = higher priority
SEVERITY_ORDER: dict[str, int] = {
    "blocking": 0,
    "critical": 0,
    "high": 1,
    "medium": 2,
    "warning": 3,
    "info": 4,
}


def sort_findings_by_severity(findings: list[SkillFinding]) -> list[SkillFinding]:
    """Sort findings by severity (blocking first)."""
    return sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 5))
