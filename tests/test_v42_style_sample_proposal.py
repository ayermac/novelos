"""v4.2 Style Sample Proposal tests.

Covers:
- propose_style_from_samples generates pending proposals
- Proposal approve does NOT modify Style Bible
- Unanalyzed samples rejected
- No Bible returns error
- Empty sample_ids returns error
- No author imitation in proposals
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import StyleBible
from novel_factory.style_bible.sample_proposal import propose_style_from_samples
from novel_factory.style_bible.sample_analyzer import analyze_style_sample_text


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
    db = str(tmp_path / "test_v42_proposal.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


def _setup_analyzed_sample(db_path, repo, project_id="prop_test", name="Sample A"):
    """Helper: create a project, bible, and analyzed sample."""
    _ensure_project(db_path, project_id)
    bible = StyleBible(project_id=project_id, name="Test Bible", genre="玄幻")
    repo.save_style_bible(project_id, bible.to_storage_dict())

    # Create sample with analysis
    text = "他紧张地冲向战场，猛地挥剑砍去。对手闪身躲开，反手刺来。他心中恐惧，但仍然克制住了情绪。「你逃不掉的。」他冷峻地说。"
    result = analyze_style_sample_text(text)
    assert result["ok"]

    metrics_json = json.dumps(result["data"]["metrics"], ensure_ascii=False)
    analysis_json = json.dumps(result["data"]["analysis"], ensure_ascii=False)

    sid = repo.save_style_sample(
        project_id, name, "local_text",
        f"hash_{name}", text[:500],
        metrics_json=metrics_json,
        analysis_json=analysis_json,
    )
    # Mark as analyzed
    repo.update_style_sample_analysis(sid, metrics_json, analysis_json, status="analyzed")
    return sid


class TestProposeStyleFromSamples:
    def test_no_bible_returns_error(self, repo):
        result = propose_style_from_samples("nonexistent", ["any"], repo)
        assert result["ok"] is False

    def test_empty_sample_ids(self, db_path, repo):
        result = propose_style_from_samples("any", [], repo)
        assert result["ok"] is False

    def test_invalid_sample_ids(self, db_path, repo):
        _ensure_project(db_path, "prop_test")
        bible = StyleBible(project_id="prop_test", name="Test")
        repo.save_style_bible("prop_test", bible.to_storage_dict())

        result = propose_style_from_samples("prop_test", ["nonexistent_id"], repo)
        assert result["ok"] is False

    def test_unanalyzed_samples_rejected(self, db_path, repo):
        _ensure_project(db_path, "prop_test")
        bible = StyleBible(project_id="prop_test", name="Test")
        repo.save_style_bible("prop_test", bible.to_storage_dict())

        # Save a sample but don't mark as analyzed
        sid = repo.save_style_sample(
            "prop_test", "Unanalyzed", "local_text", "uh1", "preview",
        )
        # Status is still 'imported', not 'analyzed'

        result = propose_style_from_samples("prop_test", [sid], repo)
        assert result["ok"] is False
        assert "not yet analyzed" in result["error"].lower() or "analyzed" in result["error"].lower()

    def test_propose_generates_proposals(self, db_path, repo):
        sid = _setup_analyzed_sample(db_path, repo)
        result = propose_style_from_samples("prop_test", [sid], repo)
        assert result["ok"] is True
        assert result["data"]["proposals_created"] > 0
        assert len(result["data"]["proposal_ids"]) > 0

    def test_proposals_are_pending(self, db_path, repo):
        sid = _setup_analyzed_sample(db_path, repo)
        result = propose_style_from_samples("prop_test", [sid], repo)
        for pid in result["data"]["proposal_ids"]:
            proposal = repo.get_style_evolution_proposal(pid)
            assert proposal["status"] == "pending"

    def test_proposal_approve_does_not_modify_bible(self, db_path, repo):
        sid = _setup_analyzed_sample(db_path, repo, name="ApproveTest")
        result = propose_style_from_samples("prop_test", [sid], repo)

        # Get original bible
        original_bible = repo.get_style_bible("prop_test")
        original_genre = original_bible["bible"].get("genre", "")

        # Approve all proposals
        for pid in result["data"]["proposal_ids"]:
            repo.decide_style_evolution_proposal(pid, "approved")

        # Bible should be unchanged
        current_bible = repo.get_style_bible("prop_test")
        assert current_bible["bible"].get("genre", "") == original_genre

    def test_multiple_samples(self, db_path, repo):
        _ensure_project(db_path, "multi_test")
        bible = StyleBible(project_id="multi_test", name="Test")
        repo.save_style_bible("multi_test", bible.to_storage_dict())

        # Create two analyzed samples
        sids = []
        for i, text in enumerate([
            "他冲向战场，挥剑砍去。对手闪身躲开。「受死！」他怒吼。",
            "她心中恐惧不安，犹豫不决。但仍然克制住了情绪，冷静面对。",
        ]):
            result = analyze_style_sample_text(text)
            m = json.dumps(result["data"]["metrics"], ensure_ascii=False)
            a = json.dumps(result["data"]["analysis"], ensure_ascii=False)
            sid = repo.save_style_sample(
                "multi_test", f"Sample{i}", "local_text",
                f"mhash{i}", text[:500],
                metrics_json=m, analysis_json=a,
            )
            repo.update_style_sample_analysis(sid, m, a, status="analyzed")
            sids.append(sid)

        result = propose_style_from_samples("multi_test", sids, repo)
        assert result["ok"] is True
        assert result["data"]["proposals_created"] >= 1

    def test_no_author_imitation_in_proposals(self, db_path, repo):
        sid = _setup_analyzed_sample(db_path, repo, name="SafetyTest")
        result = propose_style_from_samples("prop_test", [sid], repo)
        for pid in result["data"]["proposal_ids"]:
            proposal = repo.get_style_evolution_proposal(pid)
            p_str = json.dumps(proposal, ensure_ascii=False)
            assert "author_name" not in p_str
            assert "imitate_author" not in p_str
            assert "模仿" not in p_str
            # Should have safety_note
            p_json = proposal.get("proposal", {})
            if "safety_note" in p_json:
                assert "not author imitation" in p_json["safety_note"].lower()
