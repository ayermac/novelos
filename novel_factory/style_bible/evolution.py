"""v4.1 Style Evolution Proposal generator.

Analyzes quality reports and skill runs to propose Style Bible adjustments.
Does NOT auto-apply proposals. Does NOT call LLM.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from ..models.style_gate import ProposalType

logger = logging.getLogger(__name__)


def propose_style_evolution(
    project_id: str,
    repo: Any,
    limit: int = 20,
) -> dict[str, Any]:
    """Analyze recent quality data and propose Style Bible adjustments.

    Reads quality_reports, skill_runs, and reviews to find recurring
    style issues. Generates proposals but does NOT modify the Style Bible.

    Args:
        project_id: Project identifier.
        repo: Repository instance.
        limit: Max quality reports to analyze.

    Returns:
        Envelope with list of created proposal IDs.
    """
    from ..db.repository import Repository

    if not isinstance(repo, Repository):
        return {"ok": False, "error": "Invalid repository instance", "data": {}}

    # Check that a Style Bible exists
    bible_record = repo.get_style_bible(project_id)
    if not bible_record:
        return {
            "ok": False,
            "error": f"No Style Bible found for project '{project_id}'",
            "data": {},
        }

    # Gather style check results from quality_reports
    style_issues = _gather_style_issues(project_id, repo, limit)

    if not style_issues:
        return {
            "ok": True,
            "error": None,
            "data": {
                "proposals_created": 0,
                "proposal_ids": [],
                "message": "No recurring style issues found",
            },
        }

    # Aggregate and generate proposals
    proposals = _generate_proposals(project_id, style_issues)

    # Save proposals — any save failure is a hard error
    proposal_ids = []
    failed_proposals = []
    for proposal in proposals:
        try:
            pid = repo.create_style_evolution_proposal(
                project_id=project_id,
                proposal_type=proposal["proposal_type"],
                proposal_json=proposal["proposal_json"],
                rationale=proposal["rationale"],
                source="quality_reports",
            )
            proposal_ids.append(pid)
        except Exception as e:
            logger.error("Failed to save proposal: %s", e)
            failed_proposals.append({
                "proposal_type": proposal["proposal_type"],
                "rationale": proposal["rationale"],
                "error": str(e),
            })

    if failed_proposals:
        return {
            "ok": False,
            "error": f"{len(failed_proposals)} proposal(s) failed to save",
            "data": {
                "proposals_created": len(proposal_ids),
                "proposal_ids": proposal_ids,
                "failed_proposals": failed_proposals,
            },
        }

    return {
        "ok": True,
        "error": None,
        "data": {
            "proposals_created": len(proposal_ids),
            "proposal_ids": proposal_ids,
        },
    }


def _gather_style_issues(
    project_id: str,
    repo: Any,
    limit: int,
) -> list[dict[str, Any]]:
    """Gather style check issues from quality_reports and skill_runs."""
    issues = []

    # Try quality_reports table
    try:
        conn = repo._conn()
        try:
            rows = conn.execute(
                "SELECT skill_results_json "
                "FROM quality_reports "
                "WHERE project_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()

            for row in rows:
                skill_results_json = row["skill_results_json"]
                if not skill_results_json:
                    continue

                if isinstance(skill_results_json, str):
                    try:
                        skill_results = json.loads(skill_results_json)
                    except (json.JSONDecodeError, TypeError):
                        continue
                elif isinstance(skill_results_json, list):
                    skill_results = skill_results_json
                else:
                    continue

                for sr in skill_results:
                    if not isinstance(sr, dict):
                        continue
                    if sr.get("skill") != "style_bible_checker":
                        continue
                    data = sr.get("data", {})
                    if isinstance(data, str):
                        try:
                            data = json.loads(data)
                        except (json.JSONDecodeError, TypeError):
                            continue
                    for issue in data.get("issues", []):
                        if isinstance(issue, dict):
                            issues.append(issue)
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Could not read quality_reports: %s", e)

    # Try skill_runs table
    try:
        conn = repo._conn()
        try:
            rows = conn.execute(
                "SELECT output_json FROM skill_runs "
                "WHERE project_id=? AND skill_id='style-bible-checker' "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()

            for row in rows:
                output_json = row["output_json"]
                if not output_json:
                    continue
                if isinstance(output_json, str):
                    try:
                        data = json.loads(output_json)
                    except (json.JSONDecodeError, TypeError):
                        continue
                elif isinstance(output_json, dict):
                    data = output_json
                else:
                    continue

                for issue in data.get("issues", []):
                    if isinstance(issue, dict):
                        issues.append(issue)
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Could not read skill_runs: %s", e)

    return issues


def _generate_proposals(
    project_id: str,
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate proposals from aggregated style issues."""
    proposals = []

    # Count by rule_type
    rule_counts = Counter()
    rule_details: dict[str, list[dict]] = {}

    for issue in issues:
        rule_type = issue.get("rule_type", "unknown")
        rule_counts[rule_type] += 1
        if rule_type not in rule_details:
            rule_details[rule_type] = []
        rule_details[rule_type].append(issue)

    # Generate proposals for recurring issues (count >= 2)
    if rule_counts.get("forbidden_expression", 0) >= 2:
        # Find most common forbidden patterns
        forbidden_patterns = Counter()
        for issue in rule_details.get("forbidden_expression", []):
            desc = issue.get("description", "")
            # Extract pattern from description like "禁用表达 'XXX' 出现"
            if "'" in desc or "「" in desc:
                start = desc.find("'") if "'" in desc else desc.find("「")
                end = desc.rfind("'") if "'" in desc else desc.rfind("」")
                if start < end:
                    pattern = desc[start + 1:end]
                    forbidden_patterns[pattern] += 1

        for pattern, count in forbidden_patterns.most_common(3):
            if count >= 2:
                proposals.append({
                    "proposal_type": ProposalType.ADD_FORBIDDEN_EXPRESSION.value,
                    "proposal_json": {
                        "action": "add_forbidden_expression",
                        "pattern": pattern,
                        "severity": "warning",
                        "reason": f"出现{count}次，建议加入禁用列表",
                    },
                    "rationale": f"禁用表达 '{pattern}' 在最近{count}次检查中反复出现",
                })

    if rule_counts.get("ai_trace", 0) >= 2:
        ai_patterns = Counter()
        for issue in rule_details.get("ai_trace", []):
            desc = issue.get("description", "")
            if "'" in desc:
                start = desc.find("'")
                end = desc.rfind("'")
                if start < end:
                    pattern = desc[start + 1:end]
                    ai_patterns[pattern] += 1

        for pattern, count in ai_patterns.most_common(3):
            if count >= 2:
                proposals.append({
                    "proposal_type": ProposalType.ADD_AI_TRACE_PATTERN.value,
                    "proposal_json": {
                        "action": "add_ai_trace_pattern",
                        "pattern": pattern,
                    },
                    "rationale": f"AI味表达 '{pattern}' 反复出现{count}次",
                })

    if rule_counts.get("rule_violation", 0) >= 3:
        sentence_issues = [i for i in rule_details.get("rule_violation", [])
                          if "超长句" in i.get("description", "")]
        paragraph_issues = [i for i in rule_details.get("rule_violation", [])
                          if "超长段落" in i.get("description", "")]

        if len(sentence_issues) >= 2:
            proposals.append({
                "proposal_type": ProposalType.ADD_SENTENCE_RULE.value,
                "proposal_json": {
                    "action": "add_sentence_rule",
                    "description": "单句不超过80字",
                    "severity": "warning",
                },
                "rationale": f"超长句问题在最近{len(sentence_issues)}次检查中出现",
            })

        if len(paragraph_issues) >= 2:
            proposals.append({
                "proposal_type": ProposalType.ADD_PARAGRAPH_RULE.value,
                "proposal_json": {
                    "action": "add_paragraph_rule",
                    "description": "段落不超过500字",
                    "severity": "warning",
                },
                "rationale": f"超长段落问题在最近{len(paragraph_issues)}次检查中出现",
            })

    return proposals
