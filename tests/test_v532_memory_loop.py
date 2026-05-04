"""Tests for v5.3.2 Memory Updates loop — batch apply/ignore via canonical routes."""

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from tests.conftest import seed_context_for_chapter


@pytest.fixture()
def client():
    """Create test client with initialized database."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    test_client = TestClient(app)
    yield test_client
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture()
def project_id(client):
    """Create a project and return its ID."""
    resp = client.post("/api/onboarding/projects", json={
        "project_id": "test-memory",
        "name": "Test Memory",
        "genre": "奇幻",
        "description": "A test novel",
        "total_chapters_planned": 10,
        "target_words": 30000,
    })
    assert resp.status_code == 200
    data = resp.json()
    pid = data.get("data", {}).get("project", {}).get("project_id")
    assert pid, f"Expected project ID, got: {data}"
    return pid


@pytest.fixture()
def batch_with_items(client, project_id):
    """Create a memory batch with pending items via repository."""
    from novel_factory.db.repository import Repository

    db_path = client.app.state.db_path
    repo = Repository(db_path)

    batch = repo.create_memory_batch(
        project_id,
        chapter_number=1,
        run_id=None,
        summary="测试批次 (2项)",
    )

    repo.create_memory_item(
        batch_id=batch["id"],
        project_id=project_id,
        target_table="characters",
        operation="create",
        target_id=None,
        before_json=None,
        after_json=json.dumps(
            {"name": "新角色", "role": "supporting", "description": "测试角色"},
            ensure_ascii=False,
        ),
        confidence=0.9,
        evidence_text="第1章出现",
        rationale="新角色提取",
    )

    repo.create_memory_item(
        batch_id=batch["id"],
        project_id=project_id,
        target_table="story_facts",
        operation="create",
        target_id=None,
        before_json=None,
        after_json=json.dumps(
            {
                "fact_key": "mc.level",
                "fact_type": "power_level",
                "subject": "主角",
                "attribute": "level",
                "value": 1,
            },
            ensure_ascii=False,
        ),
        confidence=0.8,
        evidence_text="第1章描述",
        rationale="实力等级提取",
    )

    return batch


class TestMemoryBatchList:
    """v5.3.2: Memory batch list API."""

    def test_list_empty(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/memory-batches")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert isinstance(body["data"], list)

    def test_list_nonexistent_project(self, client):
        resp = client.get("/api/projects/nonexistent/memory-batches")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False


class TestMemoryApplyCanonical:
    """v5.3.2: Memory apply uses canonical body-style route."""

    def test_apply_batch_canonical(self, client, project_id, batch_with_items):
        """POST /api/memory/apply with project_id and batch_id in body."""
        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch_with_items["id"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["batch_id"] == batch_with_items["id"]
        assert data["items_processed"] == 2
        assert data["status"] in ("applied", "partial")

    def test_apply_creates_characters(self, client, project_id, batch_with_items):
        """Applying batch with character create should add to characters table."""
        client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch_with_items["id"],
        })

        # Verify character was created
        resp = client.get(f"/api/projects/{project_id}/characters")
        body = resp.json()
        assert body["ok"] is True
        names = [c["name"] for c in body["data"]]
        assert "新角色" in names

    def test_apply_story_fact_creates_traceable_event(self, client, project_id, batch_with_items):
        """Applying a story_facts patch should create fact history event."""
        apply_resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch_with_items["id"],
        })
        assert apply_resp.status_code == 200
        assert apply_resp.json()["ok"] is True

        history_resp = client.get(
            f"/api/facts/mc.level/history?project_id={project_id}"
        )
        assert history_resp.status_code == 200
        body = history_resp.json()
        assert body["ok"] is True
        events = body["data"]["events"]
        memory_events = [
            event for event in events
            if event["event_type"] == "created" and event["agent_id"] == "memory_curator"
        ]
        assert len(memory_events) == 1
        event = memory_events[0]
        assert event["chapter_number"] == 1
        assert event["evidence_text"] == "第1章描述"
        assert event["rationale"] == "实力等级提取"
        assert event["validation_status"] == "validated"

    def test_stub_workflow_creates_pending_memory_batch_and_apply_fact_history(self, client, project_id):
        """Full stub generation path should create reviewable memory patches."""
        seed_context_for_chapter(client.app.state.db_path, project_id, 1)

        run_resp = client.post("/api/run/chapter", json={
            "project_id": project_id,
            "chapter": 1,
            "llm_mode": "stub",
        })
        assert run_resp.status_code == 200
        run_body = run_resp.json()
        assert run_body["ok"] is True
        assert run_body["data"]["workflow_status"] == "completed"
        assert run_body["data"]["chapter_status"] == "published"

        batches_resp = client.get(f"/api/projects/{project_id}/memory-batches")
        assert batches_resp.status_code == 200
        batches_body = batches_resp.json()
        assert batches_body["ok"] is True
        batches = batches_body["data"]
        assert len(batches) == 1
        batch = batches[0]
        assert batch["status"] == "pending"
        assert batch["chapter_number"] == 1

        detail_resp = client.get(
            f"/api/projects/{project_id}/memory-batches/{batch['id']}"
        )
        assert detail_resp.status_code == 200
        detail_body = detail_resp.json()
        assert detail_body["ok"] is True
        items = detail_body["data"]["items"]
        target_tables = {item["target_table"] for item in items}
        assert {"story_facts", "plot_holes", "instructions"}.issubset(target_tables)

        facts_before = client.get(f"/api/facts?project_id={project_id}&status=active")
        assert facts_before.status_code == 200
        assert facts_before.json()["ok"] is True
        assert facts_before.json()["data"] == []

        apply_resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })
        assert apply_resp.status_code == 200
        apply_body = apply_resp.json()
        assert apply_body["ok"] is True
        assert apply_body["data"]["status"] == "applied"

        facts_after = client.get(f"/api/facts?project_id={project_id}&status=active")
        assert facts_after.status_code == 200
        facts_body = facts_after.json()
        assert facts_body["ok"] is True
        fact_keys = {fact["fact_key"] for fact in facts_body["data"]}
        assert "chapter_1.artifact" in fact_keys

        history_resp = client.get(
            f"/api/facts/chapter_1.artifact/history?project_id={project_id}"
        )
        assert history_resp.status_code == 200
        history_body = history_resp.json()
        assert history_body["ok"] is True
        events = history_body["data"]["events"]
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "created"
        assert event["agent_id"] == "memory_curator"
        assert event["chapter_number"] == 1
        assert event["validation_status"] == "validated"

    def test_apply_upserts_existing_plot_hole_and_instruction(self, client, project_id):
        """Memory apply should not go partial when create patches target existing rows."""
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        existing_plot = repo.create_plot_hole(
            project_id,
            code="PH-001",
            type="mystery",
            title="旧伏笔",
            description="旧描述",
            planted_chapter=1,
            planned_resolve_chapter=5,
            status="planted",
        )
        existing_instruction_id = repo.create_instruction(
            project_id,
            chapter_number=2,
            objective="旧目标",
            key_events="旧事件",
            emotion_tone="平静",
            word_target=2500,
        )
        batch = repo.create_memory_batch(
            project_id,
            chapter_number=1,
            summary="重复目标测试",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="plot_holes",
            operation="create",
            after_json=json.dumps({
                "code": "PH-001",
                "type": "mystery",
                "title": "更新后的伏笔",
                "description": "新描述",
                "planted_chapter": 1,
                "planned_resolve_chapter": 6,
                "status": "planted",
            }, ensure_ascii=False),
            confidence=0.9,
            evidence_text="重复伏笔证据",
            rationale="应更新而不是唯一键失败",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="instructions",
            operation="create",
            after_json=json.dumps({
                "chapter_number": 2,
                "objective": "更新后的目标",
                "key_events": "新事件",
                "emotion_tone": "紧张",
                "word_target": 3000,
            }, ensure_ascii=False),
            confidence=0.9,
            evidence_text="下一章承接",
            rationale="应替换章节指令",
        )

        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "applied"
        assert body["data"]["items_processed"] == 2
        assert all(item["success"] is True for item in body["data"]["results"])

        updated_plot = repo.get_plot_hole(project_id, existing_plot["id"])
        assert updated_plot["title"] == "更新后的伏笔"
        updated_instruction = repo.get_instruction_by_chapter(project_id, 2)
        assert updated_instruction["id"] != existing_instruction_id
        assert updated_instruction["objective"] == "更新后的目标"

    def test_apply_structured_character_traits_and_instruction_events(self, client, project_id):
        """Structured LLM memory fields should be serialized for text DB columns."""
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        character = repo.create_character(
            project_id,
            name="林砾",
            role="protagonist",
            description="旧描述",
            traits="旧特征",
        )
        batch = repo.create_memory_batch(
            project_id,
            chapter_number=4,
            summary="结构化字段测试",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="characters",
            target_id=str(character["id"]),
            operation="update",
            after_json=json.dumps({
                "traits": ["右掌冻裂至前臂", "骨腔序列血钥持有者"],
            }, ensure_ascii=False),
            confidence=0.98,
            evidence_text="身体变化",
            rationale="角色状态更新",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="instructions",
            operation="create",
            after_json=json.dumps({
                "chapter_number": 5,
                "objective": "制造迫降与被捕的二选一张力",
                "key_events": ["燃料耗尽", "回收网逼近"],
                "word_target": 2800,
            }, ensure_ascii=False),
            confidence=0.94,
            evidence_text="推进器燃料3%",
            rationale="下一章承接",
        )

        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "applied"
        assert all(item["success"] is True for item in body["data"]["results"])

        updated_character = repo.get_character(project_id, character["id"])
        assert "右掌冻裂至前臂" in updated_character["traits"]
        instruction = repo.get_instruction_by_chapter(project_id, 5)
        assert instruction["objective"] == "制造迫降与被捕的二选一张力"
        assert "燃料耗尽" in instruction["key_events"]

    def test_apply_nonexistent_batch(self, client, project_id):
        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": "nonexistent",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False

    def test_apply_wrong_project(self, client, batch_with_items):
        resp = client.post("/api/memory/apply", json={
            "project_id": "wrong-project",
            "batch_id": batch_with_items["id"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False

    def test_apply_already_applied_batch(self, client, project_id, batch_with_items):
        """Cannot apply an already-applied batch."""
        # Apply first
        client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch_with_items["id"],
        })

        # Try again
        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch_with_items["id"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False

    def test_apply_partial_batch_without_pending_items_returns_refresh_error(self, client, project_id):
        """Partial batches with no pending items should not become applied by an empty apply."""
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(
            project_id=project_id,
            chapter_number=1,
            summary="No pending items",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="characters",
            operation="create",
            after_json=json.dumps({"name": "已失败角色"}, ensure_ascii=False),
        )
        items = repo.list_memory_items(batch["id"])
        repo.update_memory_item(items[0]["id"], {"status": "failed"})
        repo.update_memory_batch(batch["id"], {"status": "partial"})

        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "NO_PENDING_MEMORY_ITEMS"
        assert repo.get_memory_batch(batch["id"])["status"] == "partial"


class TestMemoryIgnoreCanonical:
    """v5.3.2: Memory ignore uses canonical body-style route."""

    def test_ignore_item_canonical(self, client, project_id, batch_with_items):
        """POST /api/memory/ignore with project_id and item_id in body."""
        # Get items
        resp = client.get(
            f"/api/projects/{project_id}/memory-batches/{batch_with_items['id']}"
        )
        items = resp.json()["data"]["items"]
        assert len(items) > 0

        # Ignore first item
        resp = client.post("/api/memory/ignore", json={
            "project_id": project_id,
            "item_id": items[0]["id"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "ignored"

    def test_ignore_nonexistent_item(self, client, project_id):
        resp = client.post("/api/memory/ignore", json={
            "project_id": project_id,
            "item_id": "nonexistent",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False

    def test_ignore_already_applied_item(self, client, project_id, batch_with_items):
        """Cannot ignore an already-applied item."""
        # Apply batch first
        client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch_with_items["id"],
        })

        # Get items (now applied)
        resp = client.get(
            f"/api/projects/{project_id}/memory-batches/{batch_with_items['id']}"
        )
        items = resp.json()["data"]["items"]

        # Try to ignore applied item
        resp = client.post("/api/memory/ignore", json={
            "project_id": project_id,
            "item_id": items[0]["id"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False  # Cannot ignore non-pending items


class TestMemoryErrorVisibility:
    """v5.3.5: Failed memory items should expose error_message."""

    def test_apply_invalid_after_json_records_error_message(self, client, project_id):
        """Invalid after_json should produce a failed item with visible error."""
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(
            project_id,
            chapter_number=1,
            summary="Invalid JSON test",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="characters",
            operation="create",
            after_json="not valid json",
            confidence=0.9,
            evidence_text="broken",
            rationale="should fail",
        )

        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "partial"

        results = body["data"]["results"]
        assert len(results) == 1
        assert results[0]["success"] is False
        assert "error" in results[0]

        # error_message should be persisted on the item
        item = repo.get_memory_item(results[0]["item_id"])
        assert item["status"] == "failed"
        assert item["error_message"] is not None
        assert len(item["error_message"]) > 0


class TestMemoryBatchStatusRecalculation:
    """v5.3.5: Batch status must reflect all items, not just the latest apply."""

    def test_batch_all_applied(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="All applied")
        item1 = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json=json.dumps({"name": "A", "role": "supporting"}, ensure_ascii=False),
        )
        item2 = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json=json.dumps({"name": "B", "role": "supporting"}, ensure_ascii=False),
        )
        repo.update_memory_item(item1["id"], {"status": "applied"})
        repo.update_memory_item(item2["id"], {"status": "applied"})

        resp = client.post("/api/memory/apply", json={
            "project_id": project_id, "batch_id": batch["id"],
        })
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "NO_PENDING_MEMORY_ITEMS"
        # Status recalculation via helper should be applied
        from novel_factory.api.routes.memory_updates import _compute_batch_status
        assert _compute_batch_status(batch["id"], repo) == "applied"

    def test_batch_partial_with_failed(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="Has failed")
        item1 = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json=json.dumps({"name": "A", "role": "supporting"}, ensure_ascii=False),
        )
        item2 = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json="bad json",
        )
        repo.update_memory_item(item1["id"], {"status": "applied"})
        repo.update_memory_item(item2["id"], {"status": "failed"})

        from novel_factory.api.routes.memory_updates import _compute_batch_status
        assert _compute_batch_status(batch["id"], repo) == "partial"

    def test_batch_ignored(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="All ignored")
        item1 = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json=json.dumps({"name": "A", "role": "supporting"}, ensure_ascii=False),
        )
        repo.update_memory_item(item1["id"], {"status": "ignored"})

        from novel_factory.api.routes.memory_updates import _compute_batch_status
        assert _compute_batch_status(batch["id"], repo) == "ignored"

    def test_batch_mixed_applied_ignored(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="Mixed")
        item1 = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json=json.dumps({"name": "A", "role": "supporting"}, ensure_ascii=False),
        )
        item2 = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json=json.dumps({"name": "B", "role": "supporting"}, ensure_ascii=False),
        )
        repo.update_memory_item(item1["id"], {"status": "applied"})
        repo.update_memory_item(item2["id"], {"status": "ignored"})

        from novel_factory.api.routes.memory_updates import _compute_batch_status
        assert _compute_batch_status(batch["id"], repo) == "mixed"


class TestMemoryRetryFailed:
    """v5.3.5: Retry-failed should reset failed items to pending."""

    def test_retry_failed_resets_items_and_status(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="Retry test")
        item = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json="bad json",
        )
        repo.update_memory_item(item["id"], {"status": "failed", "error_message": "oops"})
        repo.update_memory_batch(batch["id"], {"status": "partial"})

        resp = client.post("/api/memory/retry-failed", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["reset_count"] == 1
        assert body["data"]["status"] == "pending"

        updated_item = repo.get_memory_item(item["id"])
        assert updated_item["status"] == "pending"
        assert updated_item["error_message"] == ""

    def test_retry_non_partial_batch_rejected(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="Applied batch")
        repo.update_memory_batch(batch["id"], {"status": "applied"})

        resp = client.post("/api/memory/retry-failed", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_BATCH_STATUS"

    def test_retry_no_failed_items_returns_error(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="No failed")
        item = repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="characters", operation="create",
            after_json=json.dumps({"name": "A"}, ensure_ascii=False),
        )
        repo.update_memory_item(item["id"], {"status": "pending"})
        repo.update_memory_batch(batch["id"], {"status": "partial"})

        resp = client.post("/api/memory/retry-failed", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "NO_FAILED_MEMORY_ITEMS"


class TestMemoryStructuredFieldNormalization:
    """v5.3.5: Structured fields must be serialized before DB writes."""

    def test_apply_plots_to_plant_and_resolve_lists(self, client, project_id):
        from novel_factory.db.repository import Repository

        repo = Repository(client.app.state.db_path)
        batch = repo.create_memory_batch(project_id, chapter_number=3, summary="Plots list test")
        repo.create_memory_item(
            batch_id=batch["id"], project_id=project_id,
            target_table="instructions", operation="create",
            after_json=json.dumps({
                "chapter_number": 4,
                "objective": "推进剧情",
                "plots_to_plant": ["伏笔A", "伏笔B"],
                "plots_to_resolve": ["旧伏笔1"],
                "key_events": ["事件1"],
                "word_target": 2500,
            }, ensure_ascii=False),
        )

        resp = client.post("/api/memory/apply", json={
            "project_id": project_id, "batch_id": batch["id"],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "applied"

        instruction = repo.get_instruction_by_chapter(project_id, 4)
        assert instruction is not None
        assert "伏笔A" in instruction["plots_to_plant"]
        assert "旧伏笔1" in instruction["plots_to_resolve"]


class TestMemoryCuratorRouting:
    """v5.3.2: Memory curator failure routing in workflow conditions."""

    def test_stub_mode_no_error_goes_to_publish(self):
        from novel_factory.workflow.conditions import route_after_memory_curator

        state = {"llm_mode": "stub"}
        assert route_after_memory_curator(state) == "publish"

    def test_real_mode_no_error_goes_to_awaiting_publish(self):
        from novel_factory.workflow.conditions import route_after_memory_curator

        state = {"llm_mode": "real"}
        assert route_after_memory_curator(state) == "awaiting_publish"

    def test_error_routes_to_human_review(self):
        from novel_factory.workflow.conditions import route_after_memory_curator

        state = {"llm_mode": "real", "error": "extraction failed"}
        assert route_after_memory_curator(state) == "human_review"

    def test_requires_human_routes_to_human_review(self):
        from novel_factory.workflow.conditions import route_after_memory_curator

        state = {"llm_mode": "real", "requires_human": True}
        assert route_after_memory_curator(state) == "human_review"

    def test_requires_human_in_stub_also_blocks(self):
        from novel_factory.workflow.conditions import route_after_memory_curator

        state = {"llm_mode": "stub", "requires_human": True}
        assert route_after_memory_curator(state) == "human_review"
