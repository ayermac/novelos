"""v6.10.2 Skill consolidation and governance tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from novel_factory.agents.editor import EditorAgent
from novel_factory.api_app import create_api_app
from novel_factory.skills.base import SkillFinding
from novel_factory.skills.knowledge_manager import KnowledgeManager
from novel_factory.skills.registry import SkillRegistry


def test_code_skill_manifests_have_governance_metadata():
    """All Code Skill manifests expose v6.10.2 governance metadata."""
    registry = SkillRegistry()
    validation = registry.validate_all()

    assert validation["ok"] is True
    assert validation["errors"] == []

    for skill in registry.list_skills():
        assert skill["layer"] == "code"
        assert skill["category"]
        assert skill["severity_default"] in {"blocking", "advisory", "disabled"}
        assert isinstance(skill["knowledge_skill_ids"], list)
        assert "runtime_scope" in skill


def test_knowledge_skills_have_reciprocal_code_pairings():
    """Knowledge Skill metadata loads paired Code Skill governance fields."""
    registry = SkillRegistry()
    code_skill_ids = {skill["id"] for skill in registry.list_skills()}
    knowledge = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")

    for skill in knowledge.list_all():
        assert skill.layer == "knowledge"
        assert skill.category
        assert skill.default_agents
        assert isinstance(skill.editable, bool)
        for code_skill_id in skill.paired_code_skill_ids:
            assert code_skill_id in code_skill_ids
            manifest = registry.get_manifest(code_skill_id)
            assert manifest is not None
            assert skill.skill_id in manifest.knowledge_skill_ids


def test_editor_governance_downgrades_advisory_skill_blockers():
    """Advisory Code Skills should not become hard blockers by default."""
    editor = EditorAgent.__new__(EditorAgent)
    manifest = SimpleNamespace(
        severity_default="advisory",
        dedupe_group="prose_quality",
        knowledge_skill_ids=["dialogue-naturalness"],
    )
    editor.skill_registry = MagicMock()
    editor.skill_registry.get_manifest.return_value = manifest

    findings = editor._govern_before_review_findings(
        "dialogue-naturalness",
        [
            SkillFinding(
                severity="blocking",
                code="LOW_DIALOGUE",
                message="对白口语化不足",
                suggestion="加入停顿和打断。",
            )
        ],
        set(),
    )

    assert findings[0].severity == "warning"
    assert "knowledge:dialogue-naturalness" in findings[0].suggestion


def test_editor_governance_dedupes_blocking_groups():
    """Only the first hard blocker in a dedupe group remains blocking."""
    editor = EditorAgent.__new__(EditorAgent)
    editor.skill_registry = MagicMock()
    editor.skill_registry.get_manifest.return_value = SimpleNamespace(
        severity_default="blocking",
        dedupe_group="continuity",
        knowledge_skill_ids=[],
    )
    seen_groups: set[str] = set()

    first = editor._govern_before_review_findings(
        "chapter-seam",
        [SkillFinding(severity="blocking", code="SEAM", message="章间断裂")],
        seen_groups,
    )
    second = editor._govern_before_review_findings(
        "continuity-gate",
        [SkillFinding(severity="blocking", code="CONTINUITY", message="连续性断裂")],
        seen_groups,
    )

    assert first[0].severity == "blocking"
    assert second[0].severity == "warning"


def test_editor_governance_clamps_advisory_skill_scores():
    """Advisory skill scores should not trigger low weighted-score revisions alone."""
    editor = EditorAgent.__new__(EditorAgent)
    editor.skill_registry = MagicMock()
    editor.skill_registry.get_manifest.return_value = SimpleNamespace(
        severity_default="advisory",
        dedupe_group="prose_quality",
        knowledge_skill_ids=["scene-sensory"],
    )

    assert editor._govern_before_review_score("scene-texture", 30) == 70.0

    editor.skill_registry.get_manifest.return_value = SimpleNamespace(
        severity_default="blocking",
        dedupe_group="facts_contract",
        knowledge_skill_ids=[],
    )

    assert editor._govern_before_review_score("fact-lock", 30) == 30


def test_skill_governance_api_returns_pairings(tmp_path):
    """The read-only API exposes Code/Knowledge governance metadata for UI."""
    from fastapi.testclient import TestClient

    client = TestClient(create_api_app(db_path=str(tmp_path / "gov.db"), llm_mode="stub"))
    response = client.get("/api/skill-governance")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["counts"]["code"] >= 20
    assert data["counts"]["knowledge"] == 11
    assert data["counts"]["pairings"] > 0
    assert data["validation"]["ok"] is True
    assert any(pair["knowledge_skill_id"] == "ai-style-avoidance" for pair in data["pairings"])


def test_knowledge_api_exposes_governance_fields(tmp_path):
    """Knowledge Skill list includes fields needed by the governance page."""
    from fastapi.testclient import TestClient

    client = TestClient(create_api_app(db_path=str(tmp_path / "knowledge.db"), llm_mode="stub"))
    response = client.get("/api/knowledge-skills")

    assert response.status_code == 200
    skill = next(item for item in response.json()["data"] if item["skill_id"] == "dialogue-naturalness")
    assert skill["layer"] == "knowledge"
    assert skill["category"] == "prose"
    assert "dialogue-naturalness" in skill["paired_code_skill_ids"]
    assert skill["editable"] is True
