"""Tests for v6.6.7 Memory Curator Reliability Closure.

Ensures:
- JSON extraction resilience
- Patch validation strictness
- Trusted/fallback/failed classification
- Backfill force semantics
- Memory status in API responses
- Planner trusted memory filtering
"""

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


# ── Pure Function Tests ─────────────────────────────────────────────


def test_robust_extract_patches_from_dict():
    """Test _robust_extract_patches handles direct dict response."""
    from novel_factory.agents.memory_curator import _robust_extract_patches

    raw = {"patches": [{"target_table": "characters", "operation": "create", "confidence": 0.8}]}
    patches, warnings = _robust_extract_patches(raw)
    assert len(patches) == 1
    assert patches[0]["target_table"] == "characters"
    assert warnings == []


def test_robust_extract_patches_from_legacy_facts():
    """Test _robust_extract_patches handles legacy 'facts' key."""
    from novel_factory.agents.memory_curator import _robust_extract_patches

    raw = {"facts": [{"target_table": "story_facts", "operation": "create", "confidence": 0.8}]}
    patches, warnings = _robust_extract_patches(raw)
    assert len(patches) == 1
    assert "Legacy" in warnings[0]


def test_robust_extract_patches_unrecognized_schema():
    """Test _robust_extract_patches warns on unrecognized schema."""
    from novel_factory.agents.memory_curator import _robust_extract_patches

    raw = {"unknown_key": []}
    patches, warnings = _robust_extract_patches(raw)
    assert patches == []
    assert any("Unrecognized" in w for w in warnings)


def test_validate_patches_empty_list():
    """Test _validate_patches rejects empty list."""
    from novel_factory.agents.memory_curator import _validate_patches

    valid, issues = _validate_patches([])
    assert valid == []
    assert any("empty" in i.lower() for i in issues)


def test_validate_patches_missing_fields():
    """Test _validate_patches rejects patches missing required fields."""
    from novel_factory.agents.memory_curator import _validate_patches

    patches = [
        {"operation": "create", "confidence": 0.8, "evidence_text": "test"},  # missing target_table
        {"target_table": "characters", "confidence": 0.8, "evidence_text": "test"},  # missing operation
        {"target_table": "characters", "operation": "create", "evidence_text": "test"},  # missing confidence
    ]
    valid, issues = _validate_patches(patches)
    assert len(valid) == 0
    assert len(issues) == 3


def test_validate_patches_confidence_out_of_range():
    """Test _validate_patches rejects confidence out of [0,1]."""
    from novel_factory.agents.memory_curator import _validate_patches

    patches = [
        {"target_table": "characters", "operation": "create", "confidence": 1.5, "evidence_text": "test"},
        {"target_table": "characters", "operation": "create", "confidence": -0.1, "evidence_text": "test"},
    ]
    valid, issues = _validate_patches(patches)
    assert len(valid) == 0
    assert any("out of [0,1]" in i for i in issues)


def test_validate_patches_empty_evidence():
    """Test _validate_patches rejects empty evidence_text."""
    from novel_factory.agents.memory_curator import _validate_patches

    patches = [
        {"target_table": "characters", "operation": "create", "confidence": 0.8, "evidence_text": "   "},
    ]
    valid, issues = _validate_patches(patches)
    assert len(valid) == 0
    assert any("evidence_text is empty" in i for i in issues)


def test_validate_patches_valid():
    """Test _validate_patches accepts valid patches."""
    from novel_factory.agents.memory_curator import _validate_patches

    patches = [
        {
            "target_table": "characters",
            "operation": "create",
            "target_name": "Alice",
            "data": {"name": "Alice"},
            "confidence": 0.85,
            "evidence_text": "Alice walked into the room.",
            "rationale": "New character",
        }
    ]
    valid, issues = _validate_patches(patches, chapter_content="Alice walked into the room.")
    assert len(valid) == 1
    assert valid[0]["confidence"] == 0.85
    assert issues == []


# ── Memory Gate Classification Tests ───────────────────────────────


def test_classify_memory_batch_empty():
    """Test classify_memory_batch returns empty for no items."""
    from novel_factory.api.routes._memory_curator_gate import classify_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            return []

    batch = {"id": "b1", "status": "pending", "summary": "test"}
    assert classify_memory_batch(FakeRepo(), batch) == "empty"


def test_classify_memory_batch_fallback_by_summary():
    """Test classify_memory_batch detects fallback by summary."""
    from novel_factory.api.routes._memory_curator_gate import classify_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            return [{"rationale": "normal", "confidence": 0.8}]

    batch = {"id": "b1", "status": "pending", "summary": "状态卡兜底"}
    assert classify_memory_batch(FakeRepo(), batch) == "fallback"


def test_classify_memory_batch_fallback_by_rationale():
    """Test classify_memory_batch detects fallback by item rationale."""
    from novel_factory.api.routes._memory_curator_gate import classify_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            return [{"rationale": "状态卡兜底候选", "confidence": 0.45}]

    batch = {"id": "b1", "status": "pending", "summary": "test"}
    assert classify_memory_batch(FakeRepo(), batch) == "fallback"


def test_classify_memory_batch_trusted():
    """Test classify_memory_batch detects trusted batch."""
    from novel_factory.api.routes._memory_curator_gate import classify_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            return [{"rationale": "正常提取", "confidence": 0.85, "evidence_text": "Alice appears in ch1"}]

    batch = {"id": "b1", "status": "pending", "summary": "test"}
    assert classify_memory_batch(FakeRepo(), batch) == "trusted"


def test_classify_memory_batch_low_confidence_not_trusted():
    """Low-confidence items must not be classified as trusted."""
    from novel_factory.api.routes._memory_curator_gate import classify_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            return [{"rationale": "normal", "confidence": 0.5, "evidence_text": "something"}]

    batch = {"id": "b1", "status": "pending", "summary": "test"}
    assert classify_memory_batch(FakeRepo(), batch) == "fallback"


def test_classify_memory_batch_no_evidence_not_trusted():
    """Items without evidence_text must not be classified as trusted."""
    from novel_factory.api.routes._memory_curator_gate import classify_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            return [{"rationale": "normal", "confidence": 0.85, "evidence_text": ""}]

    batch = {"id": "b1", "status": "pending", "summary": "test"}
    assert classify_memory_batch(FakeRepo(), batch) == "fallback"


def test_classify_memory_batch_mixed_items_not_trusted():
    """A batch with mixed trusted/untrusted items must not be trusted."""
    from novel_factory.api.routes._memory_curator_gate import classify_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            return [
                {"rationale": "normal", "confidence": 0.85, "evidence_text": "ok"},
                {"rationale": "normal", "confidence": 0.5, "evidence_text": "weak"},
            ]

    batch = {"id": "b1", "status": "pending", "summary": "test"}
    assert classify_memory_batch(FakeRepo(), batch) == "fallback"


def test_get_memory_status_for_chapter_trusted():
    """Test get_memory_status_for_chapter with trusted batch."""
    from novel_factory.api.routes._memory_curator_gate import get_memory_status_for_chapter

    class FakeRepo:
        def list_memory_batches(self, project_id):
            return [
                {"id": "b1", "chapter_number": 1, "status": "pending", "summary": "test", "created_at": "2026-01-02"},
            ]

        def list_memory_items(self, batch_id):
            return [{"rationale": "正常提取", "confidence": 0.85, "evidence_text": "Alice appears"}]

    status = get_memory_status_for_chapter(FakeRepo(), "proj", 1)
    assert status["memory_status"] == "trusted"
    assert status["memory_trusted"] is True
    assert status["trusted_batch_count"] == 1


def test_get_memory_status_for_chapter_fallback():
    """Test get_memory_status_for_chapter with fallback batch."""
    from novel_factory.api.routes._memory_curator_gate import get_memory_status_for_chapter

    class FakeRepo:
        def list_memory_batches(self, project_id):
            return [
                {"id": "b1", "chapter_number": 1, "status": "pending", "summary": "状态卡兜底", "created_at": "2026-01-02"},
            ]

        def list_memory_items(self, batch_id):
            return [{"rationale": "状态卡兜底候选", "confidence": 0.45}]

    status = get_memory_status_for_chapter(FakeRepo(), "proj", 1)
    assert status["memory_status"] == "fallback"
    assert status["memory_trusted"] is False
    assert status["fallback_batch_count"] == 1


def test_get_memory_status_for_chapter_missing():
    """Test get_memory_status_for_chapter with no batches."""
    from novel_factory.api.routes._memory_curator_gate import get_memory_status_for_chapter

    class FakeRepo:
        def list_memory_batches(self, project_id):
            return []

    status = get_memory_status_for_chapter(FakeRepo(), "proj", 1)
    assert status["memory_status"] == "missing"
    assert status["memory_trusted"] is False


# ── Context Builder Trusted Memory Tests ───────────────────────────


def test_is_trusted_memory_item_confidence_threshold():
    """Test _is_trusted_memory_item requires confidence >= 0.75."""
    from novel_factory.agent_runtime.context_builder import _is_trusted_memory_item

    assert _is_trusted_memory_item({"confidence": 0.8, "evidence_text": "test", "rationale": "正常"}) is True
    assert _is_trusted_memory_item({"confidence": 0.7, "evidence_text": "test", "rationale": "正常"}) is False


def test_is_trusted_memory_item_rejects_fallback_rationale():
    """Test _is_trusted_memory_item rejects fallback rationales."""
    from novel_factory.agent_runtime.context_builder import _is_trusted_memory_item

    assert _is_trusted_memory_item({"confidence": 0.8, "evidence_text": "test", "rationale": "状态卡兜底候选"}) is False
    assert _is_trusted_memory_item({"confidence": 0.8, "evidence_text": "test", "rationale": "fallback source"}) is False


def test_is_untrusted_memory_item_detects_low_confidence():
    """Test _is_untrusted_memory_item detects confidence <= 0.45."""
    from novel_factory.agent_runtime.context_builder import _is_untrusted_memory_item

    assert _is_untrusted_memory_item({"confidence": 0.45, "evidence_text": "test", "rationale": "正常"}) is True
    assert _is_untrusted_memory_item({"confidence": 0.5, "evidence_text": "test", "rationale": "正常"}) is False


# ── Integration Tests (API) ─────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    from novel_factory.db.connection import init_db

    db_file = tmp_path / "test.db"
    init_db(str(db_file))
    yield str(db_file)


@pytest.fixture
def client(db_path):
    """Create a test client with the database."""
    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app

    app = create_api_app(db_path=db_path, llm_mode="stub")

    with TestClient(app) as test_client:
        yield test_client


def test_run_detail_returns_memory_status_for_reviewed_chapter(client, db_path):
    """Test run detail API returns memory_status for reviewed chapter."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-memory-proj", name="Test", genre="test")
    repo.add_chapter("test-memory-proj", 1, title="Ch1", status="reviewed")

    # Create a workflow run
    run_id = repo.create_workflow_run("test-memory-proj", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")

    # Get run detail
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200

    data = response.json()["data"]
    assert "memory_status" in data
    assert data["memory_status"]["memory_status"] == "missing"
    assert data["memory_status"]["memory_trusted"] is False


def test_published_chapter_timeline_displays_publish_not_awaiting_publish(client, db_path):
    """A published chapter must not keep showing the old awaiting_publish node."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-published-timeline", name="Test", genre="test")
    repo.add_chapter("test-published-timeline", 1, title="Ch1", status="published")
    run_id = repo.create_workflow_run("test-published-timeline", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")

    response = client.get("/api/projects/test-published-timeline/chapters/1/workflow-timeline")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["chapter_status"] == "published"
    assert data["current_node"] == "publish"


def test_published_chapter_timeline_normalizes_stale_running_awaiting_publish(client, db_path):
    """Published chapters should not display an old awaiting_publish run as active."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-published-running-timeline", name="Test", genre="test")
    repo.add_chapter("test-published-running-timeline", 1, title="Ch1", status="published")
    run_id = repo.create_workflow_run("test-published-running-timeline", 1)
    repo.update_workflow_run(run_id, status="running", current_node="awaiting_publish")

    response = client.get("/api/projects/test-published-running-timeline/chapters/1/workflow-timeline")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["chapter_status"] == "published"
    assert data["run_status"] == "completed"
    assert data["current_node"] == "publish"


def test_publish_sync_updates_latest_awaiting_publish_run(db_path):
    """Manual publish should advance the latest workflow run display node."""
    from novel_factory.api.routes.run import _sync_latest_publish_run
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-publish-sync", name="Test", genre="test")
    repo.add_chapter("test-publish-sync", 1, title="Ch1", status="published")
    run_id = repo.create_workflow_run("test-publish-sync", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")

    synced = _sync_latest_publish_run(repo, "test-publish-sync", 1)
    run = repo.get_workflow_runs_for_project("test-publish-sync", chapter_number=1, limit=1)[0]

    assert synced == run_id
    assert run["status"] == "completed"
    assert run["current_node"] == "publish"


def test_backfill_skips_when_trusted_exists(client, db_path):
    """Test backfill skips when trusted batch exists and force=false."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-backfill-proj", name="Test", genre="test")
    repo.add_chapter("test-backfill-proj", 1, title="Ch1", status="reviewed")

    # Create a trusted memory batch
    batch = repo.create_memory_batch("test-backfill-proj", chapter_number=1, run_id=None, summary="可信提取")
    repo.create_memory_item(
        batch_id=batch["id"],
        project_id="test-backfill-proj",
        target_table="characters",
        operation="create",
        target_id=None,
        before_json=None,
        after_json=json.dumps({"name": "Alice"}, ensure_ascii=False),
        confidence=0.85,
        evidence_text="Alice appears",
        rationale="正常提取",
    )

    # Create a workflow run
    run_id = repo.create_workflow_run("test-backfill-proj", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")

    # Backfill without force should skip
    response = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True, "force": False})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["skipped"] is True
    assert "已有可信记忆" in data["message"]


def test_backfill_should_not_skip_untrusted_batch(client, db_path):
    """Backfill must not skip when existing batch is low-confidence (not trusted)."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-untrusted-proj", name="Test", genre="test")
    repo.add_chapter("test-untrusted-proj", 1, title="Ch1", status="reviewed")

    # Create a low-confidence memory batch (not trusted)
    batch = repo.create_memory_batch("test-untrusted-proj", chapter_number=1, run_id=None, summary="低可信提取")
    repo.create_memory_item(
        batch_id=batch["id"],
        project_id="test-untrusted-proj",
        target_table="characters",
        operation="create",
        target_id=None,
        before_json=None,
        after_json=json.dumps({"name": "Alice"}, ensure_ascii=False),
        confidence=0.5,
        evidence_text="Alice appears",
        rationale="正常提取",
    )

    run_id = repo.create_workflow_run("test-untrusted-proj", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")

    # Backfill without force should NOT skip because batch is not trusted
    response = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True, "force": False})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["skipped"] is False


def test_backfill_force_ignores_fallback_and_reruns(client, db_path):
    """Test backfill force=true ignores old fallback and re-runs."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-force-proj", name="Test", genre="test")
    repo.add_chapter("test-force-proj", 1, title="Ch1", status="reviewed")

    # Create a fallback memory batch (no trusted batch)
    batch = repo.create_memory_batch("test-force-proj", chapter_number=1, run_id=None, summary="状态卡兜底")
    repo.create_memory_item(
        batch_id=batch["id"],
        project_id="test-force-proj",
        target_table="story_facts",
        operation="create",
        target_id=None,
        before_json=None,
        after_json=json.dumps({"fact_key": "test"}, ensure_ascii=False),
        confidence=0.45,
        evidence_text="test",
        rationale="状态卡兜底候选",
    )

    # Create a workflow run
    run_id = repo.create_workflow_run("test-force-proj", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")

    # Backfill with force=true should run (not skip)
    response = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True, "force": True})
    assert response.status_code == 200

    data = response.json()["data"]
    # In stub mode, extraction may succeed or create fallback
    assert data["skipped"] is False


def test_backfill_does_not_change_chapter_status(client, db_path):
    """Test backfill run does not change chapter status."""
    from novel_factory.db.repository import Repository

    repo = Repository(db_path)
    repo.create_project(project_id="test-status-proj", name="Test", genre="test")
    repo.add_chapter("test-status-proj", 1, title="Ch1", status="reviewed")

    run_id = repo.create_workflow_run("test-status-proj", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="awaiting_publish")

    response = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True, "force": True})
    assert response.status_code == 200

    # Chapter status should remain reviewed
    chapter = repo.get_chapter("test-status-proj", 1)
    assert chapter["status"] == "reviewed"


def test_memory_curator_extraction_semantics_in_result(client, db_path):
    """Test MemoryCurator result contains clear extraction semantics."""
    from novel_factory.db.repository import Repository
    from novel_factory.agents.memory_curator import MemoryCuratorAgent
    from novel_factory.llm.stub_provider import StubLLM

    repo = Repository(db_path)
    repo.create_project(project_id="test-empty-proj", name="Test", genre="test")
    repo.add_chapter("test-empty-proj", 1, title="Ch1", status="reviewed")
    repo.save_chapter_content("test-empty-proj", 1, "some test content here")

    llm = StubLLM()
    agent = MemoryCuratorAgent(repo, llm)
    result = agent.run({
        "project_id": "test-empty-proj",
        "chapter_number": 1,
        "chapter_status": "reviewed",
        "workflow_run_id": "run-1",
        "llm_mode": "stub",
    })

    # v6.6.7: Result must contain clear extraction semantics
    assert "extraction_success" in result
    assert "memory_curator_processed" in result
    assert "fallback_created" in result
    # In stub mode, extraction usually succeeds (not fallback)
    assert isinstance(result["extraction_success"], bool)


def test_old_fallback_batch_compatibility():
    """Test old fallback batches are correctly identified."""
    from novel_factory.api.routes._memory_curator_gate import is_state_card_fallback_batch, is_trusted_memory_batch

    class FakeRepo:
        def list_memory_items(self, batch_id):
            if batch_id == "old_fallback":
                return [{"rationale": "状态卡兜底候选", "confidence": 0.45}]
            if batch_id == "old_trusted":
                return [{"rationale": "正常提取", "confidence": 0.85, "evidence_text": "Alice appears"}]
            return []

    fallback_batch = {"id": "old_fallback", "status": "pending", "summary": "old batch"}
    trusted_batch = {"id": "old_trusted", "status": "pending", "summary": "old batch"}

    assert is_state_card_fallback_batch(FakeRepo(), fallback_batch) is True
    assert is_trusted_memory_batch(FakeRepo(), fallback_batch) is False
    assert is_trusted_memory_batch(FakeRepo(), trusted_batch) is True


def test_context_builder_selects_only_trusted_memory():
    """Test _select_trusted_memory_batch ignores fallback batches."""
    from novel_factory.agent_runtime.context_builder import _select_trusted_memory_batch

    class FakeRepo:
        def list_memory_batches(self, project_id):
            return [
                {"id": "b1", "chapter_number": 1, "status": "pending", "summary": "状态卡兜底"},
                {"id": "b2", "chapter_number": 1, "status": "pending", "summary": "可信提取"},
            ]

        def list_memory_items(self, batch_id):
            if batch_id == "b1":
                return [{"rationale": "状态卡兜底候选", "confidence": 0.45, "status": "pending"}]
            if batch_id == "b2":
                return [{"rationale": "正常提取", "confidence": 0.85, "status": "pending"}]
            return []

    batch, items = _select_trusted_memory_batch(FakeRepo(), "proj", 1)
    assert batch is not None
    assert batch["id"] == "b2"
    assert len(items) == 1
