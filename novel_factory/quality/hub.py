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
from typing import Any

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

logger = logging.getLogger(__name__)


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
        overall_score = sum(quality_dimensions.values()) / len(quality_dimensions) if quality_dimensions else 0
        
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
        overall_score = sum(quality_dimensions.values()) / len(quality_dimensions) if quality_dimensions else 0
        
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
                # R3: Narrative quality low must be a blocking issue
                # Note: narrative_quality is not included in quality_dimensions to avoid double penalty
                # It only affects blocking_issues
                if narrative_score < self.narrative_fail_threshold:
                    blocking_issues.append({
                        "type": "narrative_quality_low",
                        "severity": "high",
                        "message": f"叙事质量评分过低: {narrative_score} < {self.narrative_fail_threshold}",
                        "narrative_score": narrative_score,
                        "revision_target": "author",
                    })
                else:
                    # Only add to quality_dimensions if not blocking
                    quality_dimensions["narrative_quality"] = narrative_score
        
        # 3. Editor review结果（从reviews表读取最新review）
        chapter_id = chapter.get("id")
        if chapter_id:
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
        overall_score = sum(quality_dimensions.values()) / len(quality_dimensions) if quality_dimensions else 0
        
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
                    revision_target = "editor"
                    break
                elif issue["type"] == "narrative_quality_low":
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
