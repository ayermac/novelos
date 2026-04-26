"""v4.2 Style Sample Proposal generator.

Generates Style Evolution Proposals from analyzed style samples.
Does NOT auto-apply proposals to Style Bible.
Does NOT call LLM.
Does NOT imitate any author.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.style_gate import ProposalType

logger = logging.getLogger(__name__)


def propose_style_from_samples(
    project_id: str,
    sample_ids: list[str],
    repo: Any,
    strategy: str = "conservative",
) -> dict[str, Any]:
    """Generate Style Evolution Proposals from analyzed style samples.

    Reads sample metrics/analysis, aggregates averages, and generates
    pending style_evolution_proposals. Does NOT modify Style Bible.

    Args:
        project_id: Project identifier.
        sample_ids: List of sample IDs to analyze.
        repo: Repository instance.
        strategy: Proposal strategy (conservative|moderate|aggressive).

    Returns:
        Envelope with proposal_ids and proposals_created.
    """
    from ..db.repository import Repository

    if not isinstance(repo, Repository):
        return {"ok": False, "error": "Invalid repository instance", "data": {}}

    if not sample_ids:
        return {
            "ok": False,
            "error": "No sample IDs provided",
            "data": {},
        }

    # Check Style Bible exists
    bible_record = repo.get_style_bible(project_id)
    if not bible_record:
        return {
            "ok": False,
            "error": f"No Style Bible found for project '{project_id}'",
            "data": {},
        }

    # Fetch samples
    samples = repo.get_style_samples_by_ids(project_id, sample_ids)
    if not samples:
        return {
            "ok": False,
            "error": "No valid (non-deleted) samples found for given IDs",
            "data": {},
        }

    # Check all samples are analyzed
    unanalyzed = [s for s in samples if s.get("status") != "analyzed"]
    if unanalyzed:
        return {
            "ok": False,
            "error": f"Samples not yet analyzed: {[s['id'][:8] for s in unanalyzed]}",
            "data": {},
        }

    # Aggregate metrics
    aggregated = _aggregate_metrics(samples)

    # Generate proposals based on strategy
    proposals = _generate_sample_proposals(
        project_id, aggregated, samples, strategy
    )

    if not proposals:
        return {
            "ok": True,
            "error": None,
            "data": {
                "proposals_created": 0,
                "proposal_ids": [],
                "message": "No style adjustments suggested from samples",
            },
        }

    # Save proposals — any failure is a hard error
    proposal_ids = []
    failed_proposals = []
    for proposal in proposals:
        try:
            pid = repo.create_style_evolution_proposal(
                project_id=project_id,
                proposal_type=proposal["proposal_type"],
                proposal_json=proposal["proposal_json"],
                rationale=proposal["rationale"],
                source="style_samples",
            )
            proposal_ids.append(pid)
        except Exception as e:
            logger.error("Failed to save sample proposal: %s", e)
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


def _aggregate_metrics(samples: list[dict]) -> dict[str, Any]:
    """Aggregate metrics from multiple samples by averaging."""
    if not samples:
        return {}

    numeric_keys = [
        "char_count", "paragraph_count", "sentence_count",
        "avg_sentence_length", "avg_paragraph_length",
        "dialogue_ratio", "action_ratio", "description_ratio",
        "psychology_ratio", "punctuation_density",
        "short_sentence_ratio", "long_sentence_ratio",
    ]

    sums: dict[str, float] = {k: 0.0 for k in numeric_keys}
    counts = 0

    all_tone_keywords: list[str] = []
    all_rhythm_notes: list[str] = []

    for sample in samples:
        metrics = sample.get("metrics", {})
        if not metrics:
            continue
        counts += 1
        for key in numeric_keys:
            val = metrics.get(key, 0)
            if isinstance(val, (int, float)):
                sums[key] += val
        all_tone_keywords.extend(metrics.get("tone_keywords", []))
        all_rhythm_notes.extend(metrics.get("rhythm_notes", []))

    if counts == 0:
        return {}

    averages = {k: round(sums[k] / counts, 3) for k in numeric_keys}

    # Top tone keywords
    kw_counter = Counter(all_tone_keywords)
    averages["tone_keywords"] = [kw for kw, _ in kw_counter.most_common(5)]

    # Unique rhythm notes
    averages["rhythm_notes"] = list(dict.fromkeys(all_rhythm_notes))[:5]

    # AI trace risk (use worst)
    risks = [s.get("metrics", {}).get("ai_trace_risk", "low") for s in samples]
    risk_order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    worst_risk = max(risks, key=lambda r: risk_order.get(r, 0))
    averages["ai_trace_risk"] = worst_risk

    return averages


def _generate_sample_proposals(
    project_id: str,
    aggregated: dict[str, Any],
    samples: list[dict],
    strategy: str,
) -> list[dict[str, Any]]:
    """Generate proposals from aggregated sample metrics."""
    proposals = []
    sample_ids = [s["id"] for s in samples]

    avg_sent = aggregated.get("avg_sentence_length", 0)
    avg_para = aggregated.get("avg_paragraph_length", 0)
    dialogue = aggregated.get("dialogue_ratio", 0)
    action = aggregated.get("action_ratio", 0)
    long_ratio = aggregated.get("long_sentence_ratio", 0)
    short_ratio = aggregated.get("short_sentence_ratio", 0)
    tone_kws = aggregated.get("tone_keywords", [])
    ai_risk = aggregated.get("ai_trace_risk", "low")

    # Thresholds by strategy
    if strategy == "aggressive":
        sent_thresh, para_thresh = 25, 150
    elif strategy == "moderate":
        sent_thresh, para_thresh = 30, 200
    else:  # conservative
        sent_thresh, para_thresh = 40, 300

    # Sentence rule proposal
    if avg_sent > sent_thresh or long_ratio > 0.2:
        proposals.append({
            "proposal_type": ProposalType.ADD_SENTENCE_RULE.value,
            "proposal_json": {
                "action": "calibrate_from_samples",
                "sample_ids": sample_ids,
                "suggested_updates": {
                    "sentence_rules": {
                        "avg_sentence_length_target": round(avg_sent * 0.85, 1),
                        "long_sentence_ratio_max": round(min(long_ratio + 0.05, 0.15), 2),
                    },
                },
                "safety_note": "Derived from user-provided samples; not author imitation.",
            },
            "rationale": (
                f"样本平均句长{avg_sent:.0f}字，超长句占比{long_ratio:.0%}，"
                f"建议调整句式规则"
            ),
        })

    # Paragraph rule proposal
    if avg_para > para_thresh:
        proposals.append({
            "proposal_type": ProposalType.ADD_PARAGRAPH_RULE.value,
            "proposal_json": {
                "action": "calibrate_from_samples",
                "sample_ids": sample_ids,
                "suggested_updates": {
                    "paragraph_rules": {
                        "avg_paragraph_length_target": round(avg_para * 0.85, 1),
                    },
                },
                "safety_note": "Derived from user-provided samples; not author imitation.",
            },
            "rationale": (
                f"样本平均段长{avg_para:.0f}字，建议调整段落规则"
            ),
        })

    # Pacing proposal
    if short_ratio > 0.3 and dialogue > 0.2:
        proposals.append({
            "proposal_type": ProposalType.ADJUST_PACING.value,
            "proposal_json": {
                "action": "calibrate_from_samples",
                "sample_ids": sample_ids,
                "suggested_updates": {
                    "pacing": {
                        "target_style": "fast",
                        "dialogue_ratio_target": round(dialogue, 2),
                    },
                },
                "safety_note": "Derived from user-provided samples; not author imitation.",
            },
            "rationale": (
                f"样本短句占比{short_ratio:.0%}，对话占比{dialogue:.0%}，"
                f"倾向快节奏风格"
            ),
        })

    # Tone keyword proposal
    if tone_kws:
        proposals.append({
            "proposal_type": ProposalType.ADD_TONE_KEYWORD.value,
            "proposal_json": {
                "action": "calibrate_from_samples",
                "sample_ids": sample_ids,
                "suggested_updates": {
                    "tone_keywords": tone_kws[:5],
                },
                "safety_note": "Derived from user-provided samples; not author imitation.",
            },
            "rationale": f"样本提取氛围关键词: {', '.join(tone_kws[:3])}",
        })

    # AI trace pattern proposal
    if ai_risk == "high":
        proposals.append({
            "proposal_type": ProposalType.ADD_AI_TRACE_PATTERN.value,
            "proposal_json": {
                "action": "calibrate_from_samples",
                "sample_ids": sample_ids,
                "suggested_updates": {
                    "ai_trace_note": (
                        "样本AI痕迹风险较高，建议加强AI去味规则"
                    ),
                },
                "safety_note": "Derived from user-provided samples; not author imitation.",
            },
            "rationale": "样本AI痕迹风险等级为high，建议强化AI去味检查",
        })

    return proposals


# Import Counter for _aggregate_metrics
from collections import Counter
