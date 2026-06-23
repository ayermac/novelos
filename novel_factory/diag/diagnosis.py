"""DiagnosisSystem — static analysis and runtime diagnostics.

v6.10.13: Inspired by ainovel-cli's diagnosis system.
Pure function rules that analyze project state and produce findings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    """Finding severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Confidence(str, Enum):
    """Finding confidence levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Dimension(str, Enum):
    """Diagnosis dimensions."""

    FLOW = "flow"
    QUALITY = "quality"
    PLANNING = "planning"
    MEMORY = "memory"


@dataclass
class Finding:
    """Diagnosis finding."""

    dimension: Dimension
    severity: Severity
    confidence: Confidence
    message: str
    evidence: str = ""
    suggestion: str = ""
    auto_level: str = "none"  # "none", "suggest", "safe"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dimension": self.dimension.value,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "message": self.message,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
            "auto_level": self.auto_level,
        }


@dataclass
class Snapshot:
    """Project snapshot for diagnosis."""

    project_id: str
    phase: str = ""
    current_chapter: int = 0
    total_chapters: int = 0
    completed_chapters: list[int] = field(default_factory=list)
    chapter_statuses: dict[int, str] = field(default_factory=dict)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    memory_updates: list[dict[str, Any]] = field(default_factory=list)
    foreshadows: list[dict[str, Any]] = field(default_factory=list)
    characters: list[dict[str, Any]] = field(default_factory=list)
    world_settings: list[dict[str, Any]] = field(default_factory=list)
    word_counts: dict[int, int] = field(default_factory=dict)


class DiagnosisSystem:
    """Static analysis and runtime diagnostics."""

    def diagnose(self, snapshot: Snapshot) -> list[Finding]:
        """Run all diagnosis rules."""
        findings: list[Finding] = []

        # Flow dimension
        findings.extend(self._check_flow(snapshot))

        # Quality dimension
        findings.extend(self._check_quality(snapshot))

        # Planning dimension
        findings.extend(self._check_planning(snapshot))

        # Memory dimension
        findings.extend(self._check_memory(snapshot))

        return findings

    def _check_flow(self, snapshot: Snapshot) -> list[Finding]:
        """Check flow dimension."""
        findings: list[Finding] = []

        # Check for stuck chapters
        for ch, status in snapshot.chapter_statuses.items():
            if status in ("blocking", "revision"):
                findings.append(Finding(
                    dimension=Dimension.FLOW,
                    severity=Severity.WARNING,
                    confidence=Confidence.HIGH,
                    message=f"第 {ch} 章处于 {status} 状态，可能卡住",
                    evidence=f"chapter_status={status}",
                    suggestion="检查是否有待处理的人工审核或返修",
                ))

        # Check for skipped chapters
        if snapshot.completed_chapters:
            max_ch = max(snapshot.completed_chapters)
            for ch in range(1, max_ch):
                if ch not in snapshot.completed_chapters:
                    findings.append(Finding(
                        dimension=Dimension.FLOW,
                        severity=Severity.WARNING,
                        confidence=Confidence.MEDIUM,
                        message=f"第 {ch} 章缺失，可能存在跳号",
                        evidence=f"completed={sorted(snapshot.completed_chapters)}",
                        suggestion="检查是否有意跳过或需要补写",
                    ))

        return findings

    def _check_quality(self, snapshot: Snapshot) -> list[Finding]:
        """Check quality dimension."""
        findings: list[Finding] = []

        # Check word count anomalies
        if snapshot.word_counts:
            counts = list(snapshot.word_counts.values())
            if counts:
                avg = sum(counts) / len(counts)
                for ch, count in snapshot.word_counts.items():
                    ratio = count / avg if avg > 0 else 0
                    if ratio < 0.5 or ratio > 2.0:
                        findings.append(Finding(
                            dimension=Dimension.QUALITY,
                            severity=Severity.WARNING,
                            confidence=Confidence.MEDIUM,
                            message=f"第 {ch} 章字数异常：{count} 字（平均 {avg:.0f} 字）",
                            evidence=f"ratio={ratio:.2f}",
                            suggestion="检查是否有内容截断或过度填充",
                        ))

        # Check review scores
        for review in snapshot.reviews:
            score = review.get("score", 0)
            if score < 60:
                findings.append(Finding(
                    dimension=Dimension.QUALITY,
                    severity=Severity.WARNING,
                    confidence=Confidence.HIGH,
                    message=f"第 {review.get('chapter_number', '?')} 章评审分数较低：{score}",
                    evidence=f"score={score}",
                    suggestion="考虑重写或打磨该章节",
                ))

        return findings

    def _check_planning(self, snapshot: Snapshot) -> list[Finding]:
        """Check planning dimension."""
        findings: list[Finding] = []

        # Check foreshadow aging
        if snapshot.foreshadows:
            for fs in snapshot.foreshadows:
                planted_ch = fs.get("planted_chapter", 0)
                status = fs.get("status", "")
                if status == "planted" and planted_ch > 0:
                    age = snapshot.current_chapter - planted_ch
                    if age > 30:
                        findings.append(Finding(
                            dimension=Dimension.PLANNING,
                            severity=Severity.WARNING,
                            confidence=Confidence.MEDIUM,
                            message=f"伏笔 '{fs.get('title', '?')}' 已悬挂 {age} 章未回收",
                            evidence=f"planted_at={planted_ch}, current={snapshot.current_chapter}",
                            suggestion="考虑推进或回收该伏笔",
                        ))

        # Check foundation completeness
        if not snapshot.characters:
            findings.append(Finding(
                dimension=Dimension.PLANNING,
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                message="尚未定义角色",
                suggestion="创建主角和配角设定",
            ))

        if not snapshot.world_settings:
            findings.append(Finding(
                dimension=Dimension.PLANNING,
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                message="尚未定义世界观",
                suggestion="创建世界观设定",
            ))

        return findings

    def _check_memory(self, snapshot: Snapshot) -> list[Finding]:
        """Check memory dimension."""
        findings: list[Finding] = []

        # Check for pending memory updates
        pending = [m for m in snapshot.memory_updates if m.get("status") == "pending"]
        if pending:
            findings.append(Finding(
                dimension=Dimension.MEMORY,
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                message=f"有 {len(pending)} 个待处理的记忆更新",
                evidence=f"pending_count={len(pending)}",
                suggestion="检查并应用记忆更新",
            ))

        # Check character appearances
        if snapshot.characters and snapshot.completed_chapters:
            # Simple check: if character defined but never mentioned in recent chapters
            # This is a simplified version; actual implementation would check chapter content
            pass

        return findings
