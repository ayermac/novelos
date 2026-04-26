"""v4.1 Style Evolution tests.

Covers:
- build_style_revision_advice output structure
- propose_style_evolution creates pending proposals
- proposal approve/reject only changes status
- proposal approve does NOT modify Style Bible
- No author imitation fields
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import (
    StyleBible,
    StyleCheckReport,
    StyleCheckIssue,
    ForbiddenExpression,
)
from novel_factory.models.style_gate import StyleRevisionAdvice, ProposalType


def _ensure_project(db_path: str, project_id: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name) VALUES (?, ?)",
            (project_id, "Test Project"),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path):
    db = str(tmp_path / "test_v41_evolution.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


# ── Style Revision Advice ─────────────────────────────────────


class TestStyleRevisionAdvice:
    def test_advice_from_report(self):
        from novel_factory.style_bible.advice import build_style_revision_advice

        report = StyleCheckReport(
            total_issues=3,
            blocking_issues=1,
            warning_issues=2,
            issues=[
                StyleCheckIssue(
                    rule_type="forbidden_expression",
                    severity="blocking",
                    description="禁用表达 '冷笑' 出现: AI味",
                    location="他冷笑了一声",
                    suggestion="替换或删除该表达",
                ),
                StyleCheckIssue(
                    rule_type="rule_violation",
                    severity="warning",
                    description="超长句（85字）",
                    suggestion="拆分为短句",
                ),
            ],
            score=80.0,
        )
        bible = StyleBible(
            project_id="test",
            name="Test Bible",
            preferred_expressions=[
                {"pattern": "目光一凝", "context": "战斗"},
            ],
        )

        result = build_style_revision_advice(
            report.model_dump(), bible.to_storage_dict(), "polished"
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["priority"] == "high"  # Has blocking issues
        assert len(data["forbidden_expression_fixes"]) > 0
        assert len(data["sentence_suggestions"]) > 0
        assert data["revision_target"] in ("author", "polisher")

    def test_advice_no_issues(self):
        from novel_factory.style_bible.advice import build_style_revision_advice

        report = StyleCheckReport(score=100.0)
        bible = StyleBible(project_id="test", name="Test")

        result = build_style_revision_advice(
            report.model_dump(), bible.to_storage_dict()
        )
        assert result["ok"] is True
        assert result["data"]["priority"] == "low"
        assert result["data"]["rewrite_guidance"] == "风格合规良好。"

    def test_advice_draft_stage_targets_author(self):
        from novel_factory.style_bible.advice import build_style_revision_advice

        report = StyleCheckReport(
            total_issues=1, blocking_issues=1,
            issues=[StyleCheckIssue(
                rule_type="forbidden_expression", severity="blocking",
                description="禁用表达 '冷笑' 出现",
                suggestion="替换",
            )],
            score=80.0,
        )
        bible = StyleBible(project_id="test", name="Test")

        result = build_style_revision_advice(
            report.model_dump(), bible.to_storage_dict(), stage="draft"
        )
        assert result["data"]["revision_target"] == "author"

    def test_advice_invalid_bible(self):
        from novel_factory.style_bible.advice import build_style_revision_advice

        report = StyleCheckReport()
        result = build_style_revision_advice(
            report.model_dump(), "not_a_dict"
        )
        assert result["ok"] is False


# ── Style Evolution Proposal ──────────────────────────────────


class TestStyleEvolutionProposal:
    def test_propose_no_bible(self, repo):
        from novel_factory.style_bible.evolution import propose_style_evolution

        result = propose_style_evolution("nonexistent", repo)
        assert result["ok"] is False

    def test_propose_no_issues(self, db_path, repo):
        from novel_factory.style_bible.evolution import propose_style_evolution

        _ensure_project(db_path, "evo_test")
        bible = StyleBible(project_id="evo_test", name="Test")
        repo.save_style_bible("evo_test", bible.to_storage_dict())

        result = propose_style_evolution("evo_test", repo)
        assert result["ok"] is True
        assert result["data"]["proposals_created"] == 0

    def test_propose_from_quality_reports(self, db_path, repo):
        """Proposals generated from quality_reports with recurring issues."""
        from novel_factory.style_bible.evolution import propose_style_evolution

        _ensure_project(db_path, "evo_test")
        bible = StyleBible(
            project_id="evo_test", name="Test",
            forbidden_expressions=[ForbiddenExpression(pattern="冷笑", severity="blocking")],
        )
        repo.save_style_bible("evo_test", bible.to_storage_dict())

        # Insert quality reports with style_bible_checker results
        conn = get_connection(db_path)
        try:
            skill_results = json.dumps([{
                "skill": "style_bible_checker",
                "ok": True,
                "data": {
                    "score": 60,
                    "blocking_issues": 1,
                    "issues": [
                        {"rule_type": "forbidden_expression", "description": "禁用表达 '冷笑' 出现"},
                        {"rule_type": "ai_trace", "description": "AI味表达 '不禁' 出现"},
                    ],
                },
            }])

            for _ in range(3):
                conn.execute(
                    "INSERT INTO quality_reports "
                    "(project_id, chapter_number, stage, overall_score, pass, "
                    "skill_results_json, quality_dimensions_json) "
                    "VALUES (?, 1, 'final', 60, 0, ?, '{}')",
                    ("evo_test", skill_results),
                )
            conn.commit()
        finally:
            conn.close()

        result = propose_style_evolution("evo_test", repo)
        assert result["ok"] is True
        assert result["data"]["proposals_created"] > 0


# ── Proposal Decision ─────────────────────────────────────────


class TestProposalDecision:
    def test_approve_proposal(self, db_path, repo):
        _ensure_project(db_path, "evo_test")
        bible = StyleBible(project_id="evo_test", name="Test")
        repo.save_style_bible("evo_test", bible.to_storage_dict())

        pid = repo.create_style_evolution_proposal(
            "evo_test",
            "add_forbidden_expression",
            {"pattern": "冷笑", "severity": "blocking"},
            "Recurring issue",
        )

        ok = repo.decide_style_evolution_proposal(pid, "approved", notes="Looks good")
        assert ok is True

        proposal = repo.get_style_evolution_proposal(pid)
        assert proposal["status"] == "approved"
        assert proposal["decision_notes"] == "Looks good"

    def test_reject_proposal(self, db_path, repo):
        _ensure_project(db_path, "evo_test")
        bible = StyleBible(project_id="evo_test", name="Test")
        repo.save_style_bible("evo_test", bible.to_storage_dict())

        pid = repo.create_style_evolution_proposal(
            "evo_test",
            "adjust_pacing",
            {"pacing": "slow"},
            "Test",
        )

        ok = repo.decide_style_evolution_proposal(pid, "rejected")
        assert ok is True

        proposal = repo.get_style_evolution_proposal(pid)
        assert proposal["status"] == "rejected"

    def test_approve_does_not_modify_style_bible(self, db_path, repo):
        """v4.1: approving a proposal does NOT change the Style Bible."""
        _ensure_project(db_path, "evo_test")
        bible = StyleBible(project_id="evo_test", name="Test", genre="玄幻")
        repo.save_style_bible("evo_test", bible.to_storage_dict())

        pid = repo.create_style_evolution_proposal(
            "evo_test",
            "add_forbidden_expression",
            {"pattern": "不禁", "severity": "warning"},
            "AI味表达",
        )

        repo.decide_style_evolution_proposal(pid, "approved")

        # Verify Style Bible is unchanged
        current = repo.get_style_bible("evo_test")
        current_bible = current["bible"]
        # "不禁" should NOT be in forbidden expressions
        forbidden_patterns = [f["pattern"] for f in current_bible.get("forbidden_expressions", [])]
        assert "不禁" not in forbidden_patterns

    def test_cannot_decide_already_decided(self, db_path, repo):
        _ensure_project(db_path, "evo_test")
        bible = StyleBible(project_id="evo_test", name="Test")
        repo.save_style_bible("evo_test", bible.to_storage_dict())

        pid = repo.create_style_evolution_proposal(
            "evo_test", "adjust_pacing", {}, "Test"
        )

        repo.decide_style_evolution_proposal(pid, "approved")
        # Second decision should fail (status is no longer 'pending')
        ok = repo.decide_style_evolution_proposal(pid, "rejected")
        assert ok is False

    def test_invalid_decision_raises(self, repo):
        with pytest.raises(ValueError, match="Invalid decision"):
            repo.decide_style_evolution_proposal("any", "maybe")

    def test_list_proposals_by_status(self, db_path, repo):
        _ensure_project(db_path, "evo_test")
        bible = StyleBible(project_id="evo_test", name="Test")
        repo.save_style_bible("evo_test", bible.to_storage_dict())

        p1 = repo.create_style_evolution_proposal("evo_test", "adjust_pacing", {}, "Test 1")
        p2 = repo.create_style_evolution_proposal("evo_test", "add_sentence_rule", {}, "Test 2")

        repo.decide_style_evolution_proposal(p1, "approved")

        pending = repo.list_style_evolution_proposals("evo_test", status="pending")
        approved = repo.list_style_evolution_proposals("evo_test", status="approved")

        assert len(pending) == 1
        assert len(approved) == 1


class TestProposeSaveFailure:
    """Test that propose_style_evolution reports failure when proposal DB write fails."""

    def test_propose_returns_error_on_save_failure(self, db_path, repo):
        """If the proposals table is missing, propose_style_evolution
        returns ok=False with failed_proposals instead of ok=True."""
        from novel_factory.style_bible.evolution import propose_style_evolution

        _ensure_project(db_path, "evo_fail")
        bible = StyleBible(
            project_id="evo_fail", name="Test",
            forbidden_expressions=[ForbiddenExpression(pattern="冷笑", severity="blocking")],
        )
        repo.save_style_bible("evo_fail", bible.to_storage_dict())

        # Insert quality reports that will trigger proposals
        skill_results = json.dumps([{
            "skill": "style_bible_checker",
            "ok": True,
            "data": {
                "score": 60,
                "blocking_issues": 1,
                "issues": [
                    {"rule_type": "forbidden_expression", "description": "禁用表达 '冷笑' 出现"},
                    {"rule_type": "ai_trace", "description": "AI味表达 '不禁' 出现"},
                ],
            },
        }])

        conn = get_connection(db_path)
        try:
            for _ in range(3):
                conn.execute(
                    "INSERT INTO quality_reports "
                    "(project_id, chapter_number, stage, overall_score, pass, "
                    "skill_results_json, quality_dimensions_json) "
                    "VALUES (?, 1, 'final', 60, 0, ?, '{}')",
                    ("evo_fail", skill_results),
                )
            conn.commit()
        finally:
            conn.close()

        # Drop the proposals table to force save failure
        conn = get_connection(db_path)
        conn.execute("DROP TABLE style_evolution_proposals")
        conn.commit()
        conn.close()

        result = propose_style_evolution("evo_fail", repo)
        assert result["ok"] is False
        assert "failed_proposals" in result["data"]
        assert len(result["data"]["failed_proposals"]) > 0
