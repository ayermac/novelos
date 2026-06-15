"""Project integrity checking layer.

v6.10.7: Centralized data-integrity guards so the system can detect and block
operations when critical project assets are missing or corrupted.
"""

from .project_integrity import IntegrityViolation, ProjectIntegrityChecker

__all__ = ["IntegrityViolation", "ProjectIntegrityChecker"]
