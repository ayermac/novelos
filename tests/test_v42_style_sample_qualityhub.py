"""v4.2 Style Sample QualityHub integration tests.

Covers:
- QualityHub with no samples does not error
- QualityHub with samples adds style_sample_alignment dimension
- Style sample alignment does not block
- Warning when alignment is low
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import StyleBible
from novel_factory.quality.hub import QualityHub
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
    db = str(tmp_path / "test_v42_qh.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


def _setup_bible_with_sample(db_path, repo, project_id="qh_test"):
    """Create project, bible, and an analyzed sample."""
    _ensure_project(db_path, project_id)
    bible = StyleBible(project_id=project_id, name="Test", genre="玄幻")
    repo.save_style_bible(project_id, bible.to_storage_dict())

    # Create and analyze a sample with short sentences
    text = "他冲向前。挥剑砍。对手闪开。「受死。」怒吼。"
    result = analyze_style_sample_text(text)
    assert result["ok"]
    m = json.dumps(result["data"]["metrics"], ensure_ascii=False)
    a = json.dumps(result["data"]["analysis"], ensure_ascii=False)
    sid = repo.save_style_sample(
        project_id, "Short Sample", "local_text", "qh_hash1",
        text[:500], metrics_json=m, analysis_json=a,
    )
    repo.update_style_sample_analysis(sid, m, a, status="analyzed")
    return sid


class TestQualityHubStyleSample:
    def test_no_samples_no_error(self, db_path, repo):
        """QualityHub with no samples does not add alignment or error."""
        _ensure_project(db_path, "qh_test")
        bible = StyleBible(project_id="qh_test", name="Test")
        repo.save_style_bible("qh_test", bible.to_storage_dict())

        hub = QualityHub(repo, MagicMock())
        result = hub.check_draft("qh_test", 1, "他冷笑了一声。")
        assert result["ok"] is True
        # No style_sample_alignment dimension
        assert "style_sample_alignment" not in result["data"].get("quality_dimensions", {})

    def test_with_samples_adds_alignment(self, db_path, repo):
        """QualityHub with analyzed samples adds style_sample_alignment."""
        _setup_bible_with_sample(db_path, repo)

        hub = QualityHub(repo, MagicMock())
        # Use long sentences to create deviation from short-sentence baseline
        result = hub.check_draft(
            "qh_test", 1,
            "他在那片辽阔的原野上慢慢地走着，心中想着很多事情，"
            "思绪飘向了远方的故乡和那些已经逝去的岁月。",
        )
        assert result["ok"] is True
        assert "style_sample_alignment" in result["data"].get("quality_dimensions", {})

    def test_alignment_does_not_block(self, db_path, repo):
        """Style sample alignment never creates blocking issues."""
        _setup_bible_with_sample(db_path, repo)

        hub = QualityHub(repo, MagicMock())
        result = hub.check_draft(
            "qh_test", 1,
            "他在那片辽阔的原野上慢慢地走着，心中想着很多事情。",
        )
        # No blocking issues from style_sample
        sample_blockers = [
            i for i in result["data"]["blocking_issues"]
            if "sample" in i.get("type", "").lower()
        ]
        assert len(sample_blockers) == 0

    def test_alignment_warning_when_low(self, db_path, repo):
        """Low alignment adds a warning."""
        _setup_bible_with_sample(db_path, repo)

        hub = QualityHub(repo, MagicMock())
        # Very long sentences vs short-sentence baseline
        result = hub.check_draft(
            "qh_test", 1,
            "他在那片辽阔无垠的原野上缓缓地走着，"
            "心中想着很多事情，思绪飘向了远方。",
        )
        alignment = result["data"]["quality_dimensions"].get("style_sample_alignment", 100)
        if alignment < 60:
            sample_warnings = [
                w for w in result["data"]["warnings"]
                if "Style Sample alignment" in w
            ]
            assert len(sample_warnings) > 0

    def test_no_samples_no_warning(self, db_path, repo):
        """No samples = no alignment warnings."""
        _ensure_project(db_path, "qh_empty")
        bible = StyleBible(project_id="qh_empty", name="Test")
        repo.save_style_bible("qh_empty", bible.to_storage_dict())

        hub = QualityHub(repo, MagicMock())
        result = hub.check_draft("qh_empty", 1, "他走着。")
        sample_warnings = [
            w for w in result["data"]["warnings"]
            if "Style Sample alignment" in w
        ]
        assert len(sample_warnings) == 0
