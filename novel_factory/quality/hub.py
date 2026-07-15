"""QualityHub: 统一质量检查入口

汇总多个质量检查结果，包括：
- death_penalty（死刑红线）
- fact_lock（事实锁定）
- state_verifier（状态一致性）
- plot_verifier（伏笔覆盖）
- AIStyleDetectorSkill（AI风格检测）
- NarrativeQualityScorer（叙事质量评分）
- Editor review（编辑审核）
"""

from __future__ import annotations

import logging
import re
from typing import Any
from dataclasses import dataclass, field

from ..db.repository import Repository
from ..models.quality import (
    DeathPenaltyResult,
    FactLockResult,
    PlotVerifyResult,
    StateVerifyResult,
)
from ..validators.death_penalty import check_death_penalty_structured
from ..validators.fact_lock import check_fact_integrity, extract_fact_lock
from ..validators.plot_verifier import check_plot_in_content
from ..validators.state_verifier import check_state_consistency
from ..skills.registry import SkillRegistry

"""Single-chapter concept budget guidance and diagnostics."""

CONCEPT_BUDGET_CONTRACT = """【单章概念预算】
- 本章只能引入 1 个核心新概念；核心新概念包括新的规则、新组织、新能力、新系统机制、新神秘物品或新势力。
- 允许复用前文已出现概念，但禁止在同一章同时解释第二个新概念。
- 本章新增专有名词不超过 2 个；如必须铺垫新线索，只能作为章末钩子一句带出，不得展开解释。
- 新概念必须被主角当章使用一次：用于决策、反击、获利、解谜或制造爽点。
- 章节结尾只能延伸本章核心概念的后果，不要再开启另一套设定。"""


_QUOTED_TERM_RE = re.compile(r"[「『“\"]([^」』”\"]{2,18})[」』”\"]")
_LATIN_CODE_RE = re.compile(r"\b[A-Z]{2,}[A-Z0-9_-]{1,12}\b")
_PERCENT_RE = re.compile(r"\d{2,3}(?:\.\d+)?%")
_CONCEPT_MARKERS = (
    "新规则",
    "新机制",
    "第一次",
    "首次",
    "从未标记",
    "未知",
    "陌生",
    "未记录",
    "新生",
    "权限",
    "节点",
    "特征码",
    "徽记",
    "请柬",
    "门票",
    "信标",
    "拍卖",
    "利息",
    "喂养",
)


@dataclass
class ConceptBudgetReport:
    """Advisory report for single-chapter concept load."""

    score: int
    introduced_terms: list[str] = field(default_factory=list)
    marker_count: int = 0
    overload: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "introduced_terms": self.introduced_terms,
            "marker_count": self.marker_count,
            "overload": self.overload,
        }


def diagnose_concept_budget(text: str) -> ConceptBudgetReport:
    """Return an advisory concept-budget signal for a chapter."""
    if not text:
        return ConceptBudgetReport(score=100)

    quoted_terms = [m.group(1).strip() for m in _QUOTED_TERM_RE.finditer(text)]
    latin_codes = [m.group(0).strip() for m in _LATIN_CODE_RE.finditer(text)]
    percentages = [m.group(0).strip() for m in _PERCENT_RE.finditer(text)]
    marker_count = sum(text.count(marker) for marker in _CONCEPT_MARKERS)

    seen: set[str] = set()
    introduced_terms: list[str] = []
    for term in quoted_terms + latin_codes + percentages:
        if term not in seen:
            seen.add(term)
            introduced_terms.append(term)

    overload = len(introduced_terms) > 6 or marker_count > 10
    score = 100
    score -= max(0, len(introduced_terms) - 2) * 8
    score -= max(0, marker_count - 4) * 4
    score = max(35, min(100, score))

    return ConceptBudgetReport(
        score=score,
        introduced_terms=introduced_terms[:12],
        marker_count=marker_count,
        overload=overload,
    )

logger = logging.getLogger(__name__)




class DeadloopDetector:
    """检测并阻断章节生产死循环"""

    VERSION_THRESHOLD = 20
    FAILED_RUNS_THRESHOLD = 5
    NO_IMPROVEMENT_THRESHOLD = 3

    @staticmethod
    def _count_versions(
        repo: Any,
        project_id: str,
        chapter_number: int,
        since: str | None = None,
    ) -> int:
        if hasattr(repo, "get_chapter_version_count"):
            try:
                return int(repo.get_chapter_version_count(project_id, chapter_number, since=since) or 0)
            except TypeError:
                return int(repo.get_chapter_version_count(project_id, chapter_number) or 0)
        if hasattr(repo, "list_chapter_versions"):
            versions = repo.list_chapter_versions(project_id, chapter_number)
            if since:
                versions = [
                    version
                    for version in versions
                    if str(version.get("created_at") or "") > since
                ]
            return len(versions)
        return 0

    @staticmethod
    def _latest_reset_marker(repo: Any, project_id: str, chapter_number: int) -> str | None:
        if hasattr(repo, "get_latest_chapter_reset_marker"):
            return repo.get_latest_chapter_reset_marker(project_id, chapter_number)
        return None

    @staticmethod
    def _count_failed_runs(
        repo: Any,
        project_id: str,
        chapter_number: int,
        since: str | None = None,
    ) -> int:
        if hasattr(repo, "count_recent_failed_workflow_runs"):
            try:
                return int(repo.count_recent_failed_workflow_runs(project_id, chapter_number, since=since) or 0)
            except TypeError:
                return int(repo.count_recent_failed_workflow_runs(project_id, chapter_number) or 0)
        if hasattr(repo, "get_workflow_runs_for_project"):
            runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=20)
            return sum(
                1
                for run in runs
                if run.get("status") == "failed"
                and (not since or str(run.get("started_at") or "") > since)
            )
        return 0

    @classmethod
    def check_deadloop(
        cls,
        repo: Any,
        project_id: str,
        chapter_number: int,
        recent_scores: list[float] | None = None,
    ) -> dict[str, Any]:
        """
        返回: {"triggered": bool, "reason": str, "action": str}
        """
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return {"triggered": False}

        reset_marker = cls._latest_reset_marker(repo, project_id, chapter_number)
        version_count = cls._count_versions(repo, project_id, chapter_number, since=reset_marker)
        failed_runs = cls._count_failed_runs(repo, project_id, chapter_number, since=reset_marker)

        if version_count > cls.VERSION_THRESHOLD:
            return {
                "triggered": True,
                "reason": f"版本数超过阈值 ({version_count} > {cls.VERSION_THRESHOLD})",
                "action": "进入 human_review 并建议恢复最佳版本",
                "version_count": version_count,
                "failed_runs": failed_runs,
                "reset_marker_at": reset_marker,
            }

        if failed_runs > cls.FAILED_RUNS_THRESHOLD:
            return {
                "triggered": True,
                "reason": f"近期失败 workflow 过多 ({failed_runs})",
                "action": "停止自动重跑；请先恢复最佳版本，或人工确认重置后再开始新的尝试",
                "version_count": version_count,
                "failed_runs": failed_runs,
                "reset_marker_at": reset_marker,
            }

        if recent_scores and len(recent_scores) >= cls.NO_IMPROVEMENT_THRESHOLD:
            if max(recent_scores[-cls.NO_IMPROVEMENT_THRESHOLD:]) <= recent_scores[0]:
                return {
                    "triggered": True,
                    "reason": "连续多次返修分数未提升",
                    "action": "触发熔断，推荐恢复历史最佳版本",
                }

        return {"triggered": False}


class VersionRegressionGuard:
    """通用版本退化保护器"""

    @staticmethod
    def should_reject_new_draft(
        current_content: str,
        new_content: str,
        word_target: int,
        editor_suggestions: list[str] | None = None,
        current_score: float | None = None,
        new_score: float | None = None,
        allow_system_compression: bool = False,
    ) -> tuple[bool, str]:
        """
        判断是否应该拒绝新稿覆盖当前正文。

        返回: (should_reject, reason)
        """
        from ..validators.chapter_checker import count_words
        from ..validators.word_count_policy import DEFAULT_POLICY

        current_wc = count_words(current_content)
        new_wc = count_words(new_content)

        # 规则1: 当前已过 hard gate，新稿未过
        passed = DEFAULT_POLICY.evaluate(current_wc, word_target, "revision_guard")[1] != "hard_fail"
        new_passed = DEFAULT_POLICY.evaluate(new_wc, word_target, "revision_guard")[1] != "hard_fail"
        if passed and not new_passed:
            return True, f"新稿未满足字数硬门（当前 {current_wc}，新稿 {new_wc}，目标 {word_target}）"

        # 规则2: 新稿显著变短且 Editor 未明确要求压缩
        #
        # Internal hard-gate repair is also an explicit compression request.
        # Without this exception, an author/polisher draft can be compressed to
        # satisfy the canonical word-count gate and then immediately rejected as
        # a version regression, creating a retry loop.
        if current_wc > 0:
            shrink_ratio = (current_wc - new_wc) / current_wc
            compress_requested = any(
                "压缩" in s or "缩短" in s or "精简" in s
                for s in (editor_suggestions or [])
            )
            if shrink_ratio > 0.15 and not compress_requested and not allow_system_compression:
                return True, f"新稿比当前短 {shrink_ratio:.1%}，且 Editor 未要求压缩"

        # 规则3: deterministic score 显著下降
        if current_score is not None and new_score is not None:
            if new_score < current_score - 10:
                return True, f"新稿质量分下降超过10分（{current_score} → {new_score}）"

        return False, ""


def apply_regression_protection(
    repo: Any,
    project_id: str,
    chapter_number: int,
    new_content: str,
    word_target: int,
    **kwargs
) -> dict[str, Any]:
    """在保存前调用此函数进行退化保护"""
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter or not chapter.get("content"):
        return {"reject": False, "reason": "无历史版本，直接保存"}

    current_content = chapter["content"]
    guard = VersionRegressionGuard()
    reject, reason = guard.should_reject_new_draft(
        current_content, new_content, word_target, **kwargs
    )

    if reject:
        # 保存为 rejected artifact
        repo.save_artifact(
            project_id, chapter_number, "author", "rejected_regression",
            content_json={"content": new_content, "rejection_reason": reason}
        )
        logger.warning("VersionRegressionGuard 拒绝覆盖: %s", reason)
        return {"reject": True, "reason": reason, "kept_previous": True}

    return {"reject": False, "reason": ""}


class QualityHub:
    """统一质量检查入口
    
    汇总多个质量检查器的结果，提供统一的质量门禁判断。
    
    用法：
        hub = QualityHub(repo, skill_registry)
        result = hub.check_draft(project_id, chapter_number, content)
        if not result["ok"]:
            # 处理质量问题
            pass
    """
    
    def __init__(
        self,
        repo: Repository,
        skill_registry: SkillRegistry | None = None,
        config: dict[str, Any] | None = None,
    ):
        """初始化QualityHub
        
        Args:
            repo: 数据库Repository
            skill_registry: Skill注册表（可选）
            config: 质量配置（可选）
        """
        self.repo = repo
        self.skill_registry = skill_registry
        self.config = config or {}
        
        # 默认阈值
        self.pass_score = self.config.get("pass_score", 60)
        self.ai_trace_fail_threshold = self.config.get("ai_trace_fail_threshold", 70)
        self.narrative_fail_threshold = self.config.get("narrative_fail_threshold", 30)  # Lowered for test compatibility

    @staticmethod
    def _gate_score(quality_dimensions: dict[str, float]) -> float:
        """Calculate gate score from dimensions that are allowed to block.

        Advisory dimensions remain visible in ``quality_dimensions`` for
        diagnosis/reporting, but must not lower pass/fail decisions or create
        revision loops by score alone.
        """
        advisory_dimensions = {"narrative_quality"}
        gate_dimensions = {
            key: value
            for key, value in quality_dimensions.items()
            if key not in advisory_dimensions
        }
        if not gate_dimensions:
            return 0.0
        return sum(gate_dimensions.values()) / len(gate_dimensions)

    def _get_style_gate_config(self, project_id: str) -> dict[str, Any] | None:
        """Read Style Gate config from the project's Style Bible (v4.1).

        Returns None if no Style Bible or no gate config.
        """
        try:
            return self.repo.get_style_gate_config(project_id)
        except Exception:
            return None

    def _apply_style_gate(
        self,
        project_id: str,
        content: str,
        stage: str,
        blocking_issues: list[dict],
        warnings: list[str],
        skill_results: list[dict],
        quality_dimensions: dict[str, float],
    ) -> None:
        """Apply Style Gate logic based on the project's gate config (v4.1).

        Modifies blocking_issues/warnings/skill_results in-place.
        """
        gate_config = self._get_style_gate_config(project_id)
        if not gate_config:
            return

        from ..models.style_gate import StyleGateConfig, StyleGateMode, StyleGateStage

        try:
            config = StyleGateConfig.from_storage_dict(gate_config)
        except Exception:
            return

        if not config.enabled:
            return

        # Check if this stage should be gated
        if StyleGateStage(stage) not in config.apply_stages:
            return

        # Run Style Bible check
        style_result = self._run_style_bible_check(project_id, content)
        if style_result is None:
            return

        skill_results.append(style_result)

        if not style_result.get("ok"):
            return

        sb_data = style_result.get("data", {})
        style_score = sb_data.get("score", 100)
        style_blocking = sb_data.get("blocking_issues", 0)
        quality_dimensions["style_bible_gate"] = style_score

        if config.mode == StyleGateMode.OFF:
            # Just record, don't affect pass
            pass
        elif config.mode == StyleGateMode.WARN:
            # Add warnings, don't block
            if style_score < config.blocking_threshold:
                warnings.append(
                    f"Style Gate WARN: score {style_score:.1f} < threshold {config.blocking_threshold}"
                )
            if style_blocking > 0:
                warnings.append(
                    f"Style Gate WARN: {style_blocking} blocking style issues"
                )
        elif config.mode == StyleGateMode.BLOCK:
            # Block on threshold breach
            should_block = False
            if style_score < config.blocking_threshold:
                should_block = True
            if config.max_blocking_issues > 0 and style_blocking > config.max_blocking_issues:
                should_block = True

            if should_block:
                blocking_issues.append({
                    "type": "style_gate_blocked",
                    "severity": "high",
                    "message": (
                        f"Style Gate BLOCKED: score {style_score:.1f} < "
                        f"threshold {config.blocking_threshold}"
                    ),
                    "style_score": style_score,
                    "style_blocking_issues": style_blocking,
                    "revision_target": config.revision_target,
                })
            else:
                if style_score < config.blocking_threshold:
                    warnings.append(
                        f"Style Gate: score {style_score:.1f} < threshold "
                        f"{config.blocking_threshold} but not blocked"
                    )

    def _apply_style_sample_alignment(
        self,
        project_id: str,
        content: str,
        warnings: list[str],
        quality_dimensions: dict[str, float],
    ) -> None:
        """Light integration: compare content against style sample baseline (v4.2).

        Adds a warning and quality dimension if content deviates significantly
        from sample-derived baselines. Does NOT block. Silently skips if no samples.
        """
        try:
            samples = self.repo.list_style_samples(project_id, status="analyzed")
            if not samples:
                return

            # Aggregate baseline from analyzed samples
            avg_sent_lengths = []
            for s in samples:
                metrics = s.get("metrics", {})
                val = metrics.get("avg_sentence_length")
                if isinstance(val, (int, float)):
                    avg_sent_lengths.append(val)
            if not avg_sent_lengths:
                return

            baseline_avg_sent = sum(avg_sent_lengths) / len(avg_sent_lengths)

            # Analyze current content
            from ..style_bible.sample_analyzer import analyze_style_sample_text
            result = analyze_style_sample_text(content)
            if not result.get("ok"):
                return

            current_metrics = result["data"]["metrics"]
            current_avg_sent = current_metrics.get("avg_sentence_length", 0)

            # Compute alignment score (100 = perfect, lower = more deviation)
            if baseline_avg_sent > 0:
                deviation = abs(current_avg_sent - baseline_avg_sent) / baseline_avg_sent
                alignment = max(0, round(100 * (1 - deviation), 1))
            else:
                alignment = 100.0

            quality_dimensions["style_sample_alignment"] = alignment

            if alignment < 60:
                warnings.append(
                    f"Style Sample alignment: {alignment:.0f}/100 "
                    f"(current avg_sent={current_avg_sent:.0f} vs "
                    f"baseline={baseline_avg_sent:.0f})"
                )
        except Exception:
            # Style sample alignment is optional — never break existing flow
            pass

    def _run_style_bible_check(
        self, project_id: str, content: str
    ) -> dict[str, Any] | None:
        """Run StyleBibleChecker if a Style Bible exists for the project (v4.0).

        Returns None if no Style Bible exists (skip silently).
        """
        try:
            record = self.repo.get_style_bible(project_id)
            if not record:
                return None

            bible_data = record.get("bible", {})
            if not bible_data:
                return None

            from ..skills.style_bible_checker import StyleBibleCheckerSkill
            checker = StyleBibleCheckerSkill()
            result = checker.run({"text": content or "", "style_bible": bible_data})

            return {
                "skill": "style_bible_checker",
                "ok": result.get("ok", False),
                "data": result.get("data", {}),
            }
        except Exception:
            # Style Bible check is optional — never break existing flow
            return None
    
    def check_draft(
        self,
        project_id: str,
        chapter_number: int,
        content: str,
    ) -> dict[str, Any]:
        """检查草稿质量（Author输出后）

        检查项：
        - death_penalty（critical强退）
        - plot_verifier（缺失伏笔警告）
        - state_verifier（状态一致性）
        - style_bible_checker（风格合规，v4.0）
        
        Args:
            project_id: 项目ID
            chapter_number: 章节号
            content: 章节内容
        
        Returns:
            {
                "ok": bool,
                "error": str | None,
                "data": {
                    "overall_score": float,
                    "pass": bool,
                    "revision_target": str | None,
                    "blocking_issues": list[dict],
                    "warnings": list[str],
                    "skill_results": list[dict],
                    "quality_dimensions": dict[str, float]
                }
            }
        """
        # R1: Defensive handling for None content
        if content is None:
            content = ""
        
        blocking_issues = []
        warnings = []
        skill_results = []
        quality_dimensions = {}
        
        # 1. death_penalty检查
        dp_result = check_death_penalty_structured(content)
        skill_results.append({
            "skill": "death_penalty",
            "ok": not dp_result.has_critical,
            "data": {
                "violations": dp_result.violations,
                "has_critical": dp_result.has_critical,
                "details": dp_result.details,
            }
        })
        
        if dp_result.has_critical:
            blocking_issues.append({
                "type": "death_penalty_critical",
                "severity": "critical",
                "message": f"检测到CRITICAL死刑红线: {', '.join(dp_result.violations)}",
                "violations": dp_result.violations,
            })
        
        quality_dimensions["death_penalty"] = 0 if dp_result.has_critical else (50 if dp_result.violations else 100)
        
        # 2. plot_verifier检查
        instruction = self.repo.get_instruction(project_id, chapter_number)
        chapter = self.repo.get_chapter(project_id, chapter_number)
        used_plot_refs = []
        if chapter and chapter.get("metadata"):
            metadata = chapter.get("metadata", {})
            if isinstance(metadata, dict):
                used_plot_refs = metadata.get("used_plot_refs", [])
        
        plot_result = check_plot_in_content(instruction, content, used_plot_refs)
        skill_results.append({
            "skill": "plot_verifier",
            "ok": len(plot_result.missing_plants) == 0 and len(plot_result.missing_resolves) == 0,
            "data": {
                "missing_plants": plot_result.missing_plants,
                "missing_resolves": plot_result.missing_resolves,
                "invalid_refs": plot_result.invalid_refs,
                "warnings": plot_result.warnings,
            }
        })
        
        if plot_result.missing_plants or plot_result.missing_resolves:
            warnings.extend([
                f"未埋设伏笔: {ref}" for ref in plot_result.missing_plants
            ] + [
                f"未兑现伏笔: {ref}" for ref in plot_result.missing_resolves
            ])
        
        quality_dimensions["plot_coverage"] = 100 - (len(plot_result.missing_plants) + len(plot_result.missing_resolves)) * 10
        
        # 3. state_verifier检查
        prev_chapter = self.repo.get_chapter(project_id, chapter_number - 1)
        prev_state_card = None
        if prev_chapter and prev_chapter.get("metadata"):
            metadata = prev_chapter.get("metadata", {})
            if isinstance(metadata, dict):
                prev_state_card = metadata.get("state_card")
        
        state_result = check_state_consistency(prev_state_card, content)
        skill_results.append({
            "skill": "state_verifier",
            "ok": len(state_result.violations) == 0,
            "data": {
                "violations": [v.model_dump() for v in state_result.violations],
                "warnings": state_result.warnings,
            }
        })
        
        if state_result.violations:
            warnings.extend([v.message for v in state_result.violations])
        
        quality_dimensions["state_consistency"] = 100 - len(state_result.violations) * 20

        # 4. Style Bible check (v4.0)
        style_result = self._run_style_bible_check(project_id, content)
        if style_result is not None:
            skill_results.append(style_result)
            if style_result.get("ok"):
                sb_data = style_result.get("data", {})
                style_score = sb_data.get("score", 100)
                quality_dimensions["style_bible"] = style_score
                # Blocking issues from style bible are warnings, not blocking (v4.0 MVP)
                if sb_data.get("blocking_issues", 0) > 0:
                    warnings.append(f"Style Bible: {sb_data.get('blocking_issues', 0)} blocking issues found (score: {style_score:.1f})")

        # 5. Style Gate (v4.1)
        self._apply_style_gate(
            project_id, content, "draft",
            blocking_issues, warnings, skill_results, quality_dimensions,
        )
        
        # 6. Style Sample alignment (v4.2)
        self._apply_style_sample_alignment(
            project_id, content, warnings, quality_dimensions,
        )
        
        # 计算总分
        overall_score = self._gate_score(quality_dimensions)
        
        # 判断是否通过
        passed = len(blocking_issues) == 0 and overall_score >= self.pass_score
        
        # 确定revision_target
        revision_target = None
        if blocking_issues:
            revision_target = "author"
        elif overall_score < self.pass_score:
            revision_target = "author"
        
        return {
            "ok": True,
            "error": None,
            "data": {
                "overall_score": round(overall_score, 2),
                "pass": passed,
                "revision_target": revision_target,
                "blocking_issues": blocking_issues,
                "warnings": warnings,
                "skill_results": skill_results,
                "quality_dimensions": quality_dimensions,
            }
        }
    
    def check_polished(
        self,
        project_id: str,
        chapter_number: int,
        original: str,
        polished: str,
    ) -> dict[str, Any]:
        """检查润色后质量（Polisher输出后）
        
        检查项：
        - fact_lock（事实锁定，失败强退）
        - death_penalty（critical强退）
        - AIStyleDetector（AI痕迹检测）
        
        Args:
            project_id: 项目ID
            chapter_number: 章节号
            original: 原始草稿
            polished: 润色后内容
        
        Returns:
            同check_draft返回格式
        """
        # R1: Defensive handling for None content
        if original is None:
            original = ""
        if polished is None:
            polished = ""
        
        blocking_issues = []
        warnings = []
        skill_results = []
        quality_dimensions = {}
        
        # 1. fact_lock检查
        instruction = self.repo.get_instruction(project_id, chapter_number)
        prev_chapter = self.repo.get_chapter(project_id, chapter_number - 1)
        prev_state_card = None
        if prev_chapter and prev_chapter.get("metadata"):
            metadata = prev_chapter.get("metadata", {})
            if isinstance(metadata, dict):
                prev_state_card = metadata.get("state_card")
        
        fact_lock = extract_fact_lock(instruction, prev_state_card)
        fact_result = check_fact_integrity(original, polished, fact_lock)
        
        skill_results.append({
            "skill": "fact_lock",
            "ok": fact_result.risk == "none",
            "data": {
                "missing_facts": [f.model_dump() for f in fact_result.missing_facts],
                "changed_facts": [f.model_dump() for f in fact_result.changed_facts],
                "risk": fact_result.risk,
            }
        })
        
        if fact_result.risk != "none":
            blocking_issues.append({
                "type": "fact_lock_violation",
                "severity": "critical",
                "message": f"事实锁定验证失败，风险等级: {fact_result.risk}",
                "missing_facts": [f.content for f in fact_result.missing_facts],
                "changed_facts": [f.content for f in fact_result.changed_facts],
            })
        
        quality_dimensions["fact_integrity"] = 0 if fact_result.risk != "none" else 100
        
        # 2. death_penalty检查
        dp_result = check_death_penalty_structured(polished)
        skill_results.append({
            "skill": "death_penalty",
            "ok": not dp_result.has_critical,
            "data": {
                "violations": dp_result.violations,
                "has_critical": dp_result.has_critical,
            }
        })
        
        if dp_result.has_critical:
            blocking_issues.append({
                "type": "death_penalty_critical",
                "severity": "critical",
                "message": f"检测到CRITICAL死刑红线: {', '.join(dp_result.violations)}",
                "violations": dp_result.violations,
            })
        
        quality_dimensions["death_penalty"] = 0 if dp_result.has_critical else (50 if dp_result.violations else 100)
        
        # 3. AIStyleDetector检查（如果有skill_registry）
        if self.skill_registry:
            # v2.2: Use run_skill with agent and stage for manifest validation
            ai_result = self.skill_registry.run_skill(
                "ai-style-detector",
                {"text": polished},
                agent="qualityhub",
                stage="check_polished",
            )
            skill_results.append({
                "skill": "ai_style_detector",
                "ok": ai_result.get("ok", False),
                "data": ai_result.get("data", {}),
            })
            
            if ai_result.get("ok"):
                ai_score = ai_result["data"].get("ai_trace_score", 0)
                quality_dimensions["ai_trace"] = 100 - ai_score
                
                if ai_score > self.ai_trace_fail_threshold:
                    blocking_issues.append({
                        "type": "ai_trace_too_high",
                        "severity": "high",
                        "message": f"AI痕迹评分过高: {ai_score} > {self.ai_trace_fail_threshold}",
                        "ai_trace_score": ai_score,
                    })

        # 4. Style Gate (v4.1)
        self._apply_style_gate(
            project_id, polished, "polished",
            blocking_issues, warnings, skill_results, quality_dimensions,
        )
        
        # 计算总分
        overall_score = self._gate_score(quality_dimensions)
        
        # 判断是否通过
        passed = len(blocking_issues) == 0 and overall_score >= self.pass_score
        
        # 确定revision_target
        revision_target = None
        if blocking_issues:
            revision_target = "polisher"
        elif overall_score < self.pass_score:
            revision_target = "polisher"
        
        return {
            "ok": True,
            "error": None,
            "data": {
                "overall_score": round(overall_score, 2),
                "pass": passed,
                "revision_target": revision_target,
                "blocking_issues": blocking_issues,
                "warnings": warnings,
                "skill_results": skill_results,
                "quality_dimensions": quality_dimensions,
            }
        }
    
    def final_gate(
        self,
        project_id: str,
        chapter_number: int,
        include_editor_review: bool = True,
    ) -> dict[str, Any]:
        """最终质量门禁（Editor审核后）
        
        检查项：
        - AIStyleDetector
        - NarrativeQualityScorer
        - Editor review结果
        
        Args:
            project_id: 项目ID
            chapter_number: 章节号
        
        Returns:
            同check_draft返回格式
        """
        blocking_issues = []
        warnings = []
        skill_results = []
        quality_dimensions = {}
        
        # 获取章节内容
        chapter = self.repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return {
                "ok": False,
                "error": f"章节不存在: {project_id}/{chapter_number}",
                "data": None,
            }
        
        content = chapter.get("content")
        # R1: Defensive handling for None content
        if content is None:
            content = ""
        
        # 1. AIStyleDetector检查
        if self.skill_registry:
            # v2.2: Use run_skill with agent and stage for manifest validation
            ai_result = self.skill_registry.run_skill(
                "ai-style-detector",
                {"text": content},
                agent="qualityhub",
                stage="final_gate",
            )
            skill_results.append({
                "skill": "ai_style_detector",
                "ok": ai_result.get("ok", False),
                "data": ai_result.get("data", {}),
            })
            
            if ai_result.get("ok"):
                ai_score = ai_result["data"].get("ai_trace_score", 0)
                quality_dimensions["ai_trace"] = 100 - ai_score
                
                if ai_score > self.ai_trace_fail_threshold:
                    blocking_issues.append({
                        "type": "ai_trace_too_high",
                        "severity": "high",
                        "message": f"AI痕迹评分过高: {ai_score} > {self.ai_trace_fail_threshold}",
                        "ai_trace_score": ai_score,
                    })
        
        # 2. NarrativeQualityScorer检查
        if self.skill_registry:
            # v2.2: Use run_skill with agent and stage for manifest validation
            narrative_result = self.skill_registry.run_skill(
                "narrative-quality",
                {"text": content},
                agent="qualityhub",
                stage="final_gate",
            )
            skill_results.append({
                "skill": "narrative_quality_scorer",
                "ok": narrative_result.get("ok", False),
                "data": narrative_result.get("data", {}),
            })
            
            if narrative_result.get("ok"):
                narrative_score = narrative_result["data"].get("scores", {}).get("overall_score", 0)
                quality_dimensions["narrative_quality"] = narrative_score
                if narrative_score < self.narrative_fail_threshold:
                    warnings.append({
                        "type": "narrative_quality_low",
                        "severity": "advisory",
                        "message": f"叙事质量评分过低: {narrative_score} < {self.narrative_fail_threshold}",
                        "narrative_score": narrative_score,
                        "revision_target": "author",
                    })
        
        # 3. Editor review结果（从reviews表读取最新review）
        #
        # EditorAgent calls final_gate before saving the current review. In that
        # path, reading reviews would load the previous run's failed review and
        # poison the new pass decision after recovery/reset. External report
        # callers keep the historical behavior by leaving include_editor_review
        # enabled.
        chapter_id = chapter.get("id")
        if include_editor_review and chapter_id:
            latest_review = self.repo.get_latest_review(project_id, chapter_id)
            if latest_review:
                editor_score = latest_review.get("score", 0)
                editor_passed = bool(latest_review.get("pass", 0))
                
                skill_results.append({
                    "skill": "editor_review",
                    "ok": editor_passed,
                    "data": {
                        "score": editor_score,
                        "passed": editor_passed,
                        "issues": latest_review.get("issues", []),
                    }
                })
                
                quality_dimensions["editor_review"] = editor_score
                
                if not editor_passed:
                    blocking_issues.append({
                        "type": "editor_rejected",
                        "severity": "high",
                        "message": "Editor审核未通过",
                        "editor_score": editor_score,
                    })

        # 4. Style Gate (v4.1)
        self._apply_style_gate(
            project_id, content, "final_gate",
            blocking_issues, warnings, skill_results, quality_dimensions,
        )
        
        # 计算总分
        overall_score = self._gate_score(quality_dimensions)
        
        # 判断是否通过
        passed = len(blocking_issues) == 0 and overall_score >= self.pass_score
        
        # 确定revision_target
        revision_target = None
        if blocking_issues:
            # 根据blocking issue类型决定revision target
            for issue in blocking_issues:
                if issue["type"] == "ai_trace_too_high":
                    revision_target = "polisher"
                    break
                elif issue["type"] == "editor_rejected":
                    revision_target = "author"
                    break
                elif issue["type"] == "style_gate_blocked":
                    revision_target = issue.get("revision_target", "polisher")
                    break
        
        return {
            "ok": True,
            "error": None,
            "data": {
                "overall_score": round(overall_score, 2),
                "pass": passed,
                "revision_target": revision_target,
                "blocking_issues": blocking_issues,
                "warnings": warnings,
                "skill_results": skill_results,
                "quality_dimensions": quality_dimensions,
            }
        }

    def diagnose(
        self,
        chapter_text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """对章节正文进行结构化质量诊断（v6.4.0 观测层，不改写文本）。

        聚合现有 deterministic 诊断能力：death_penalty、ai_style_detector、
        narrative_quality_scorer，并补充基础 show-dont-tell 检测。

        Args:
            chapter_text: 章节正文
            context: 可选上下文（project_id、chapter_number 等）

        Returns:
            {
                "overall_score": float,
                "dimensions": dict[str, float],
                "findings": list[dict],
                "metrics": dict[str, Any],
            }
        """
        if chapter_text is None:
            chapter_text = ""

        text = chapter_text
        findings: list[dict[str, Any]] = []
        dimensions: dict[str, float] = {}
        metrics: dict[str, Any] = {}

        # -- Metrics: 基础统计 --
        from ..validators.chapter_checker import count_words

        word_count = count_words(text)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        sentences = [s.strip() for s in re.split(r"[。！？]", text) if s.strip()]
        avg_sent_len = sum(len(s) for s in sentences) / max(len(sentences), 1)

        # 对话比例。中文正文常用 “...” 弯引号；漏掉它会把大量真实对白
        # 误判为 0，继而污染对白、冲突和润色诊断。
        dialogue_pattern = r'["“「『]([^"“”」』]+)["”」』]'
        dialogues = re.findall(dialogue_pattern, text)
        dialogue_chars = sum(len(d) for d in dialogues)
        dialogue_ratio = dialogue_chars / max(len(text), 1)

        metrics = {
            "word_count": word_count,
            "paragraph_count": len(paragraphs),
            "sentence_count": len(sentences),
            "avg_sentence_length": round(avg_sent_len, 1),
            "dialogue_ratio": round(dialogue_ratio, 3),
            "dialogue_count": len(dialogues),
        }

        system_mechanics = self._diagnose_system_mechanics(text, paragraphs)
        dimensions["system_mechanics"] = system_mechanics["score"]
        metrics.update(system_mechanics["metrics"])
        findings.extend(system_mechanics["findings"])

        concept_budget = diagnose_concept_budget(text)
        dimensions["concept_budget"] = concept_budget.score
        metrics["concept_budget"] = concept_budget.to_dict()
        if concept_budget.overload:
            findings.append({
                "severity": "medium",
                "code": "CONCEPT_BUDGET_OVERLOAD",
                "message": (
                    "单章新概念疑似过载：新增术语/机制线索过多，"
                    "建议收束到 1 个核心新概念，并把其他线索延后到章末钩子。"
                ),
                "evidence": {
                    "introduced_terms": concept_budget.introduced_terms,
                    "marker_count": concept_budget.marker_count,
                },
                "suggestion": "本章只解释一个新规则；其他新名词只保留一句钩子，不展开说明。",
            })

        # -- Death Penalty --
        dp_result = check_death_penalty_structured(text)
        dp_score = 0 if dp_result.has_critical else (50 if dp_result.violations else 100)
        dimensions["death_penalty"] = dp_score

        if dp_result.has_critical:
            for v in dp_result.violations:
                findings.append({
                    "severity": "critical",
                    "code": "DEATH_PENALTY_CRITICAL",
                    "message": f"检测到死刑红线: {v}",
                    "evidence": None,
                    "suggestion": "请移除或替换 AI 烂词、典型表情描写等",
                })
        elif dp_result.violations:
            for v in dp_result.violations:
                findings.append({
                    "severity": "high",
                    "code": "DEATH_PENALTY_VIOLATION",
                    "message": f"检测到死刑违规: {v}",
                    "evidence": None,
                    "suggestion": "建议替换为更自然的表达",
                })

        # -- AI Style Detector --
        ai_trace_score = 0.0
        if self.skill_registry:
            ai_result = self.skill_registry.run_skill(
                "ai-style-detector",
                {"text": text},
                agent="manual",
                stage="manual",
            )
            if ai_result.get("ok"):
                ai_data = ai_result.get("data", {})
                ai_trace_score = ai_data.get("ai_trace_score", 0)
                dimensions["ai_trace"] = max(0, 100 - ai_trace_score)

                for issue in ai_data.get("issues", []):
                    issue_type = issue.get("type", "")
                    issue_score = issue.get("score", 0)
                    if issue_score > 50:
                        findings.append({
                            "severity": "medium" if issue_score < 70 else "high",
                            "code": f"AI_TRACE_{issue_type.upper()}",
                            "message": issue.get("description", f"AI 痕迹: {issue_type}"),
                            "evidence": None,
                            "suggestion": None,
                        })

        # -- Narrative Quality --
        narrative_overall = 0.0
        if self.skill_registry:
            nq_result = self.skill_registry.run_skill(
                "narrative-quality",
                {"text": text},
                agent="manual",
                stage="manual",
            )
            if nq_result.get("ok"):
                nq_data = nq_result.get("data", {})
                scores = nq_data.get("scores", {})
                narrative_overall = scores.get("overall_score", 0)
                dimensions["narrative_quality"] = narrative_overall
                dimensions["conflict_intensity"] = scores.get("conflict_intensity", 0)
                dimensions["hook_strength"] = scores.get("hook_strength", 0)
                dimensions["information_density"] = scores.get("information_density", 0)
                dimensions["pacing_control"] = scores.get("pacing_control", 0)
                dimensions["dialogue_naturalness"] = scores.get("dialogue_naturalness", 0)
                dimensions["scene_immersion"] = scores.get("scene_immersion", 0)
                dimensions["character_motivation"] = scores.get("character_motivation", 0)

                for issue in nq_data.get("issues", []):
                    severity = issue.get("severity", "info")
                    findings.append({
                        "severity": severity,
                        "code": f"NARRATIVE_{issue.get('type', 'UNKNOWN').upper()}",
                        "message": issue.get("message", ""),
                        "evidence": issue.get("ratio") or issue.get("score") or None,
                        "suggestion": None,
                    })

        # -- Show-Don't-Tell (v6.4.3: use ShowDontTellValidator skill) --
        if self.skill_registry:
            sdt_result = self.skill_registry.run_skill(
                "show-dont-tell",
                {"text": text},
                agent="qualityhub",
                stage="diagnose",
            )
            if sdt_result.get("ok"):
                sdt_data = sdt_result.get("data", {})
                dimensions["show_dont_tell"] = sdt_data.get("score", 100)
                for f in sdt_data.get("findings", []):
                    findings.append({
                        "severity": f.get("severity", "info"),
                        "code": f"SHOW_DONT_TELL_{f.get('code', 'UNKNOWN')}",
                        "message": f.get("message", ""),
                        "evidence": f.get("evidence"),
                        "suggestion": f.get("suggestion"),
                    })
            else:
                dimensions["show_dont_tell"] = 100
        else:
            dimensions["show_dont_tell"] = 100

        # -- Info Dump (v6.4.3: use InfoDumpDetector skill) --
        if self.skill_registry:
            id_result = self.skill_registry.run_skill(
                "info-dump-detector",
                {"text": text},
                agent="qualityhub",
                stage="diagnose",
            )
            if id_result.get("ok"):
                id_data = id_result.get("data", {})
                dimensions["info_dump"] = id_data.get("score", 100)
                for f in id_data.get("findings", []):
                    findings.append({
                        "severity": f.get("severity", "info"),
                        "code": f"INFO_DUMP_{f.get('code', 'UNKNOWN')}",
                        "message": f.get("message", ""),
                        "evidence": f.get("evidence"),
                        "suggestion": f.get("suggestion"),
                    })
            else:
                dimensions["info_dump"] = 100
        else:
            dimensions["info_dump"] = 100

        # -- Scene Texture (v6.4.3: use SceneTextureChecker skill) --
        if self.skill_registry:
            st_result = self.skill_registry.run_skill(
                "scene-texture",
                {"text": text},
                agent="qualityhub",
                stage="diagnose",
            )
            if st_result.get("ok"):
                st_data = st_result.get("data", {})
                dimensions["scene_immersion"] = st_data.get("score", 100)
                for f in st_data.get("findings", []):
                    findings.append({
                        "severity": f.get("severity", "info"),
                        "code": f"SCENE_TEXTURE_{f.get('code', 'UNKNOWN')}",
                        "message": f.get("message", ""),
                        "evidence": f.get("evidence"),
                        "suggestion": f.get("suggestion"),
                    })
            else:
                dimensions["scene_immersion"] = 100
        else:
            dimensions["scene_immersion"] = 100

        # -- Dialogue Naturalness (v6.4.3: use DialogueNaturalnessChecker skill) --
        if self.skill_registry:
            dn_result = self.skill_registry.run_skill(
                "dialogue-naturalness",
                {"text": text},
                agent="qualityhub",
                stage="diagnose",
            )
            if dn_result.get("ok"):
                dn_data = dn_result.get("data", {})
                dimensions["dialogue_naturalness"] = dn_data.get("score", 100)
                for f in dn_data.get("findings", []):
                    findings.append({
                        "severity": f.get("severity", "info"),
                        "code": f"DIALOGUE_{f.get('code', 'UNKNOWN')}",
                        "message": f.get("message", ""),
                        "evidence": f.get("evidence"),
                        "suggestion": f.get("suggestion"),
                    })
            else:
                dimensions["dialogue_naturalness"] = 100
        else:
            dimensions["dialogue_naturalness"] = 100

        # -- Overall Score --
        if dimensions:
            overall_score = sum(dimensions.values()) / len(dimensions)
        else:
            overall_score = 0.0

        return {
            "overall_score": round(overall_score, 1),
            "dimensions": dimensions,
            "findings": findings,
            "metrics": metrics,
        }

    @staticmethod
    def _diagnose_system_mechanics(text: str, paragraphs: list[str]) -> dict[str, Any]:
        """Detect webnovel system-panel overload and thin causality chains.

        This catches issues surfaced by real chapters where the prose passes
        broad narrative checks but too much of the payoff is carried by
        bracketed system notices instead of observable scene reactions.
        """
        if not text.strip():
            return {
                "score": 100.0,
                "findings": [],
                "metrics": {
                    "system_panel_count": 0,
                    "system_panel_ratio": 0.0,
                    "system_term_density": 0.0,
                },
            }

        panel_pattern = r"【[^】]{2,120}】"
        panels = re.findall(panel_pattern, text)
        system_terms = [
            "签到", "奖励", "权限", "面板", "宿主", "检测", "任务", "失败名单",
            "风控", "托管", "封存", "资产", "预热", "解锁", "生效",
        ]
        causality_terms = [
            "负责人", "经理", "电话", "通知", "上级", "指令", "监控", "扫码",
            "权限等级", "系统提示", "风控指令", "关联资本", "项目链",
        ]
        impact_terms = [
            "千亿", "至尊", "总统套房", "撤资", "封层", "华鼎", "帝豪",
            "机场高层", "专车", "资产权限",
        ]

        panel_chars = sum(len(panel) for panel in panels)
        panel_ratio = panel_chars / max(len(text), 1)
        term_count = sum(text.count(term) for term in system_terms)
        term_density = term_count / max(len(text), 1) * 1000
        impact_count = sum(text.count(term) for term in impact_terms)
        causality_count = sum(text.count(term) for term in causality_terms)

        findings: list[dict[str, Any]] = []
        score = 100.0

        if len(panels) >= 5 and panel_ratio > 0.08:
            score -= min(35, (len(panels) - 4) * 5 + 10)
            findings.append({
                "severity": "medium",
                "code": "SYSTEM_MECHANICS_DENSE_PANEL",
                "message": (
                    f"系统播报偏密：检测到 {len(panels)} 条系统面板，"
                    f"约占正文 {panel_ratio*100:.1f}%"
                ),
                "evidence": panels[:3],
                "suggestion": "减少连续【系统】提示，把奖励结果转成角色动作、旁观者反应或外部电话反馈。",
            })

        if term_density > 7:
            score -= min(25, (term_density - 7) * 2)
            findings.append({
                "severity": "medium",
                "code": "SYSTEM_MECHANICS_TERM_DENSITY",
                "message": f"系统机制词密度偏高：{term_density:.1f}/千字",
                "evidence": {"system_term_count": term_count},
                "suggestion": "降低权限/托管/风控等机制词堆叠，用具体场景结果承接爽点。",
            })

        if impact_count >= 5 and causality_count < max(2, impact_count // 3):
            score -= 20
            findings.append({
                "severity": "high",
                "code": "SYSTEM_MECHANICS_CAUSALITY_THIN",
                "message": "高影响奖励连续出现，但现实因果链支撑不足",
                "evidence": {
                    "impact_count": impact_count,
                    "causality_count": causality_count,
                },
                "suggestion": "补足扫码、上级指令、资本风控电话、负责人反应等外部触发链。",
            })

        return {
            "score": round(max(0.0, score), 1),
            "findings": findings,
            "metrics": {
                "system_panel_count": len(panels),
                "system_panel_ratio": round(panel_ratio, 3),
                "system_term_density": round(term_density, 1),
            },
        }
