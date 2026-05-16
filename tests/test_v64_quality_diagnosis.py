"""v6.4.0: Quality Diagnosis Baseline tests.

Tests QualityHub.diagnose aggregation and the quality-diagnosis API.
No LLM calls. No text rewriting.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


SAMPLE_AI_HEAVY_TEXT = """李明感到一阵愤怒涌上心头。

他看着眼前的对手，心中暗想：这次一定要赢。

"你这个人，真是太可笑了。"他说道。

这个世界是一个充满魔法的世界，在这个世界里，人们可以通过修炼获得强大的力量。所谓修炼，是指通过吸收天地灵气来增强自身实力的过程。简单来说，修炼就是变强的途径。

然而，事情并没有那么简单。

张华觉得有些不安。他知道，这次的任务非常危险。他明白，如果失败，后果将不堪设想。

"我们必须小心。"张华说道。

"我明白。"李明回答。

与此同时，王芳也感到了同样的压力。她意识到，这场战斗将决定一切。

综上所述，三人都做好了准备。
"""

SAMPLE_GOOD_TEXT = """李明攥紧拳头，指节发白。

眼前的对手正冷笑着逼近，每一步都像踩在鼓点上。李明没有后退，只是微微侧头，让过对方的第一拳，反手一记肘击撞在对手肋下。

"就这点本事？"对手咧着嘴，呼吸有些急促。

李明没回答，只是脚步一错，身形如鬼魅般绕到对手身后。空气中弥漫着汗水和铁锈的气味，远处传来几声喝彩，又被更大的嘘声压了下去。

张华靠在石柱旁，手里把玩着一枚铜币。铜币在他指间翻转，发出细碎的摩擦声。他没有抬头，只是用余光扫着场中的两人。

"赌谁赢？"旁边有人低声问。

"赌命。"张华终于开口，声音轻得像叹息。

王芳站在阴影里，手指无意识地摩挲着腰间的短刀。刀柄已经被汗水浸得湿滑，但她没有松手。

场中的两人再次交错，拳脚相撞的闷响在空旷的大厅里回荡。
"""


@pytest.fixture
def client_with_repo():
    """Create a fresh TestClient with in-memory DB for each test."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    yield TestClient(app), Repository(db_path), db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestQualityHubDiagnose:
    """Test QualityHub.diagnose deterministic aggregation."""

    def test_diagnose_empty_text(self):
        """Empty text should return zero scores and no critical findings."""
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())
            result = hub.diagnose("")

            assert result["overall_score"] == 100.0  # empty text has no violations
            assert result["metrics"]["word_count"] == 0
            assert result["findings"] == []
            assert "dimensions" in result
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_diagnose_ai_heavy_text(self):
        """AI-heavy text should detect straight emotions and info dumps."""
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())
            result = hub.diagnose(SAMPLE_AI_HEAVY_TEXT)

            # Should have findings
            assert len(result["findings"]) > 0

            # Should detect show-dont-tell
            finding_codes = [f["code"] for f in result["findings"]]
            assert "SHOW_DONT_TELL_STRAIGHT_EMOTION" in finding_codes

            # Should detect info dump
            assert any("INFO_DUMP" in c for c in finding_codes)

            # Dimensions should exist
            dims = result["dimensions"]
            assert "show_dont_tell" in dims
            assert "info_dump" in dims
            assert "info_density" not in dims
            assert "death_penalty" in dims
            assert "ai_trace" in dims
            assert "narrative_quality" in dims

            # Show-dont-tell should be low for AI-heavy text
            assert dims["show_dont_tell"] < 80

            # Metrics
            assert result["metrics"]["word_count"] > 0
            assert result["metrics"]["paragraph_count"] > 0
            assert result["metrics"]["dialogue_ratio"] >= 0
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_diagnose_good_text(self):
        """Good text should have fewer findings and higher scores."""
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())
            result = hub.diagnose(SAMPLE_GOOD_TEXT)

            # Should have fewer findings than AI-heavy
            ai_result = hub.diagnose(SAMPLE_AI_HEAVY_TEXT)
            assert len(result["findings"]) < len(ai_result["findings"])

            # Show-dont-tell should be higher
            assert result["dimensions"]["show_dont_tell"] > ai_result["dimensions"]["show_dont_tell"]
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_diagnose_structure(self):
        """Diagnosis result must have the expected structure."""
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())
            result = hub.diagnose(SAMPLE_AI_HEAVY_TEXT)

            assert isinstance(result["overall_score"], float)
            assert isinstance(result["dimensions"], dict)
            assert isinstance(result["findings"], list)
            assert isinstance(result["metrics"], dict)

            for finding in result["findings"]:
                assert "severity" in finding
                assert "code" in finding
                assert "message" in finding
                assert finding["severity"] in ("critical", "high", "medium", "info", "warning")

            for key in ("word_count", "paragraph_count", "sentence_count",
                        "avg_sentence_length", "dialogue_ratio", "dialogue_count"):
                assert key in result["metrics"]
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_diagnose_no_regression_on_existing_methods(self):
        """diagnose() must not break check_draft / check_polished / final_gate."""
        from novel_factory.quality.hub import QualityHub
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            hub = QualityHub(repo, skill_registry=SkillRegistry())

            # Existing methods should still work
            draft_result = hub.check_draft("test-project", 1, "some content")
            assert draft_result["ok"] is True
            assert "data" in draft_result

            polished_result = hub.check_polished("test-project", 1, "original", "polished")
            assert polished_result["ok"] is True
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestQualityDiagnosisAPI:
    """Test GET /api/projects/{pid}/chapters/{n}/quality-diagnosis."""

    def test_api_project_not_found(self, client_with_repo):
        """Should return PROJECT_NOT_FOUND."""
        client, repo, db_path = client_with_repo
        resp = client.get("/api/projects/nonexistent/chapters/1/quality-diagnosis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "PROJECT_NOT_FOUND"

    def test_api_chapter_not_found(self, client_with_repo):
        """Should return CHAPTER_NOT_FOUND for non-existent chapter."""
        client, repo, db_path = client_with_repo
        repo.create_project(
            project_id="test-proj",
            name="Test",
            genre="fantasy",
            description="test",
            target_words=10000,
            total_chapters_planned=10,
        )
        resp = client.get("/api/projects/test-proj/chapters/999/quality-diagnosis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "CHAPTER_NOT_FOUND"

    def test_api_chapter_no_content(self, client_with_repo):
        """Should return CHAPTER_NO_CONTENT for chapter without content."""
        client, repo, db_path = client_with_repo
        repo.create_project(
            project_id="test-proj",
            name="Test",
            genre="fantasy",
            description="test",
            target_words=10000,
            total_chapters_planned=10,
        )
        repo.add_chapter("test-proj", 1, "第 1 章（待命名）", status="drafted")
        resp = client.get("/api/projects/test-proj/chapters/1/quality-diagnosis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "CHAPTER_NO_CONTENT"

    def test_api_success(self, client_with_repo):
        """Should return structured diagnosis for chapter with content."""
        client, repo, db_path = client_with_repo
        repo.create_project(
            project_id="test-proj",
            name="Test",
            genre="fantasy",
            description="test",
            target_words=10000,
            total_chapters_planned=10,
        )
        repo.add_chapter("test-proj", 1, "第 1 章（待命名）", status="drafted")
        repo.save_chapter_content("test-proj", 1, SAMPLE_AI_HEAVY_TEXT)

        resp = client.get("/api/projects/test-proj/chapters/1/quality-diagnosis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        diagnosis = data["data"]
        assert "overall_score" in diagnosis
        assert "dimensions" in diagnosis
        assert "findings" in diagnosis
        assert "metrics" in diagnosis

        # Check metrics
        assert diagnosis["metrics"]["word_count"] > 0

        # Check findings have expected codes
        codes = [f["code"] for f in diagnosis["findings"]]
        assert "SHOW_DONT_TELL_STRAIGHT_EMOTION" in codes
        assert any("INFO_DUMP" in c for c in codes)


class TestExecutionEventConstant:
    """Test that EVENT_QUALITY_DIAGNOSED constant exists."""

    def test_event_constant(self):
        from novel_factory.workflow.execution_events import EVENT_QUALITY_DIAGNOSED
        assert EVENT_QUALITY_DIAGNOSED == "quality_diagnosed"
