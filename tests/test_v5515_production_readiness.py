"""v5.5.15 Production Readiness Closure tests.

Covers:
1. reviewed/published chapter not overridden by paused disconnected auto-run session
2. stale running workflow reported by health-summary
3. running target chapter cannot be re-started via /run/chapter
4. pending memory updates surface in health-summary
5. obsolete session action points to session cleanup
6. chapter/workflow contradiction detected by health-summary
"""

from __future__ import annotations

import json
import os
import tempfile

from fastapi.testclient import TestClient


def _client_with_repo():
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path), db_path


def test_reviewed_chapter_not_overridden_by_disconnected_session():
    """A paused+disconnected auto-run session whose target chapter is already
    reviewed must be identified as obsolete, and the health-summary must
    NOT treat the session as the source of truth."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-reviewed"
        repo.create_project(
            project_id=project_id,
            name="Reviewed Override Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        # Chapter is reviewed
        repo.add_chapter(project_id, 1, "第一章", status="published")
        repo.add_chapter(project_id, 2, "第二章", status="reviewed")

        # Create a disconnected session that was targeting chapter 2
        session = repo.create_auto_run_session(
            project_id,
            chapter_start=2,
            chapter_end=10,
            max_steps=5,
            dry_run=False,
            stop_on_review=True,
        )
        repo.create_auto_run_step(
            session["id"],
            step_number=1,
            action="generate_chapter",
            label="生成第 2 章",
            target_chapter=2,
        )
        repo.update_auto_run_session_status(
            session["id"],
            "paused",
            stop_reason="client_disconnected",
            last_event="step_started",
        )

        # The active-session endpoint should mark it as obsolete
        resp = client.get(f"/api/projects/{project_id}/production/run-auto/active-session")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["active"] is False
        assert data.get("obsolete_session_id") == session["id"]

        # After active-session marks it as stopped, the health-summary won't
        # find it as an active session anymore. The key v5.5.15 behavior is
        # that the active-session endpoint correctly identifies and auto-stops
        # the obsolete session, so it no longer shows as "可重新接入".
        # The health-summary obsolete_sessions count is 0 because the session
        # was already stopped by the active-session detection.
        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        health = resp.json()["data"]
        # The obsolete session is already cleaned up by active-session detection
        assert health["summary"]["obsolete_sessions"] == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_stale_running_workflow_reported_by_health_summary():
    """A running workflow that exceeded the timeout must be reported
    as a stale run in the health summary."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-stale-run"
        repo.create_project(
            project_id=project_id,
            name="Stale Run Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="drafted")

        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="polisher")
        # Backdate started_at to 2 hours ago
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_runs SET started_at=datetime('now','-2 hours','+8 hours') WHERE id=?",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["stale_runs"] >= 1
        stale_item = next(
            item for item in data["items"] if item["key"].startswith("stale_run:")
        )
        assert stale_item["severity"] == "blocking"
        assert "处理卡住运行" in stale_item["action_label"]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_running_chapter_cannot_be_restarted():
    """POST /run/chapter must be rejected if the target chapter already
    has a running workflow run."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-duplicate-guard"
        repo.create_project(
            project_id=project_id,
            name="Duplicate Guard Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="drafted")

        # Create a running workflow run for chapter 1
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="author")

        # Attempt to start another generation for the same chapter
        resp = client.post("/api/run/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "WORKFLOW_ALREADY_RUNNING"
        assert "不能重复启动" in data["error"]["message"]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_running_project_workflow_blocks_other_chapter_generation():
    """Only one chapter production workflow should run per project at a time."""
    _, repo, db_path = _client_with_repo()
    try:
        project_id = "v6623-project-workflow-lock"
        repo.create_project(
            project_id=project_id,
            name="Project Workflow Lock Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=20,
        )
        repo.add_chapter(project_id, 17, "第十七章", status="drafted")
        repo.add_chapter(project_id, 18, "第十八章", status="planned")

        run_id = repo.create_workflow_run(project_id, 17)
        repo.update_workflow_run(run_id, status="running", current_node="author")

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        err, _preflight = check_chapter_run_guard(repo, project_id, 18)
        assert err is not None
        assert err.code == "PROJECT_WORKFLOW_ALREADY_RUNNING"
        assert err.details["chapter_number"] == 17
        assert err.details["run_id"] == run_id
        assert "第 17 章已有正在运行的工作流" in err.message
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_planned_chapter_with_existing_content_cannot_be_generated():
    """A recovered planned chapter with preserved content must not be treated
    as an empty chapter generation slot."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v571-planned-with-content"
        repo.create_project(
            project_id=project_id,
            name="Planned Existing Content Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="planned")
        repo.save_chapter(project_id, 1, "第一章", "已有正文内容" * 20, 120, "planned")

        resp = client.post("/api/run/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "CHAPTER_HAS_EXISTING_CONTENT"
        assert data["error"]["details"]["hint"] == "review_existing_content"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_planned_chapter_with_existing_content_can_run_after_explicit_reset():
    """A completed reset_recovery marker is the explicit reset required before
    regenerating a planned chapter that still has preserved text."""
    _, repo, db_path = _client_with_repo()
    try:
        project_id = "v611-reset-planned-with-content"
        repo.create_project(
            project_id=project_id,
            name="Reset Existing Content Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="planned")
        repo.save_chapter(project_id, 1, "第一章", "恢复后保留的正文" * 20, 160, "planned")

        # v6.3: context completeness guard requires approved genesis + world + characters + outlines + instructions
        repo.create_genesis_run(project_id, input_json='{"title":"test"}', status="approved")
        repo.create_world_setting(project_id, category="世界观", title="背景", content="test")
        repo.create_character(project_id, name="主角", role="protagonist", description="test", traits="", first_appearance=1)
        repo.create_outline(project_id, level="volume", sequence=1, title="第一卷", content="test", chapters_range="1-10")
        repo.create_instruction(project_id, chapter_number=1, objective="test", key_events="test")

        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="blocked", current_node="human_review")
        repo.mark_blocked_workflow_runs_recovered_for_chapter(project_id, 1, run_id=run_id)

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        err, _preflight = check_chapter_run_guard(repo, project_id, 1)
        assert err is None
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_regenerate_reset_endpoint_confirms_planned_existing_content():
    """The API exposes an explicit confirmation path for planned chapters that
    preserve text after recovery, so the UI does not dead-end on the run guard."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v656-confirm-regenerate"
        repo.create_project(
            project_id=project_id,
            name="Confirm Regenerate Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="planned")
        repo.save_chapter(project_id, 1, "第一章", "恢复后保留的正文" * 20, 160, "planned")

        repo.create_genesis_run(project_id, input_json='{"title":"test"}', status="approved")
        repo.create_world_setting(project_id, category="世界观", title="背景", content="test")
        repo.create_character(project_id, name="主角", role="protagonist", description="test", traits="", first_appearance=1)
        repo.create_outline(project_id, level="volume", sequence=1, title="第一卷", content="test", chapters_range="1-10")
        repo.create_instruction(project_id, chapter_number=1, objective="test", key_events="test")

        blocked_run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(blocked_run_id, status="blocked", current_node="human_review")

        missing_confirm = client.post(
            f"/api/projects/{project_id}/chapters/1/regenerate-reset",
            json={"confirm": False},
        )
        assert missing_confirm.status_code == 200
        assert missing_confirm.json()["ok"] is False
        assert missing_confirm.json()["error"]["code"] == "CONFIRM_REQUIRED"

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        before, _preflight = check_chapter_run_guard(repo, project_id, 1)
        assert before is not None
        assert before.code == "CHAPTER_HAS_EXISTING_CONTENT"

        confirmed = client.post(
            f"/api/projects/{project_id}/chapters/1/regenerate-reset",
            json={"confirm": True},
        )
        assert confirmed.status_code == 200
        data = confirmed.json()["data"]
        assert data["reset"] is True
        assert data["recovered_blocked_runs"] == 1
        assert data["new_status"] == "planned"

        err, _preflight = check_chapter_run_guard(repo, project_id, 1)
        assert err is None
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_pending_memory_updates_surface_in_health_summary():
    """Pending memory items must appear in the health summary with
    an action that navigates to the memory inbox."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-memory"
        repo.create_project(
            project_id=project_id,
            name="Memory Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="new facts")
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="characters",
            operation="update",
            after_json='{"name":"NewChar"}',
            target_id="1",
        )

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["pending_memory_items"] >= 1
        memory_item = next(
            item for item in data["items"] if item["key"] == "pending_memory_updates"
        )
        assert memory_item["action_label"] == "打开记忆收件箱"
        assert "module=memory" in memory_item["action_url"]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_ignored_memory_batch_items_do_not_surface_in_health_summary():
    """Items left pending inside ignored batches are historical, not actionable."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "ignored-memory"
        repo.create_project(
            project_id=project_id,
            name="Ignored Memory",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="old fallback")
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="story_facts",
            operation="create",
            after_json='{"fact_key":"old","value":"ignored"}',
        )
        repo.update_memory_batch(batch["id"], {"status": "ignored"})

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["pending_memory_items"] == 0
        assert all(item["key"] != "pending_memory_updates" for item in data["items"])

        next_resp = client.get(f"/api/projects/{project_id}/production-next")
        assert next_resp.status_code == 200
        assert next_resp.json()["data"]["health"]["has_pending_memory_updates"] is False
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_publish_chapter_auto_applies_trusted_memory_batch():
    """Manual publish should apply trusted same-chapter memory before publishing."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "publish-auto-memory"
        repo.create_project(
            project_id=project_id,
            name="Publish Auto Memory",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        content = (
            "林辰把锚点密匙扣进掌心，秦伯在旁低声确认权限已经稳定。"
            "锚点密匙的纹路亮起后，走廊尽头的防护门缓缓打开。"
        ) * 30
        repo.save_chapter(
            project_id,
            1,
            "第1章 锚点密匙",
            content,
            1200,
            "awaiting_publish",
        )
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="第1章可信记忆")
        item = repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="story_facts",
            operation="create",
            after_json=json.dumps({
                "fact_key": "ch1.anchor_key",
                "fact_type": "plot",
                "subject": "林辰",
                "attribute": "道具",
                "value": "获得锚点密匙",
                "source_chapter": 1,
                "source_agent": "memory_curator",
            }, ensure_ascii=False),
            confidence=0.95,
            evidence_text="林辰把锚点密匙扣进掌心。",
            rationale="第1章可信记忆提取",
        )

        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["chapter_status"] == "published"
        assert data["memory_apply"]["memory_apply_processed"] is True
        assert data["memory_apply"]["items_processed"] == 1
        assert repo.get_chapter(project_id, 1)["status"] == "published"
        assert repo.get_memory_item(item["id"])["status"] == "applied"
        assert repo.get_memory_batch(batch["id"])["status"] == "applied"
        fact = repo.get_story_fact_by_key(project_id, "ch1.anchor_key")
        assert fact is not None
        assert fact["source_agent"] == "memory_curator"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_publish_self_heals_memory_lock_dedupes_and_applies_before_publish():
    """Manual publish should close zombie memory runs, dedupe batches, then apply memory."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "publish-memory-zombie-dedupe"
        repo.create_project(
            project_id=project_id,
            name="Publish Memory Zombie Dedupe",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        content = (
            "陆恒把黑市铭牌扣进掌心，赵莽在旁确认赤蝎盘口已经转向。"
            "黑市杀机被他反手压住，401室外的走廊重新安静下来。"
        ) * 30
        repo.save_chapter(
            project_id,
            2,
            "第二章 黑市杀机",
            content,
            1200,
            "awaiting_publish",
        )
        run_id = repo.create_workflow_run(project_id, 2)
        repo.update_workflow_run(run_id, status="running", current_node="memory_curator")
        repo.acquire_memory_curator_lock(project_id, 2, run_id=run_id)

        payload = {
            "fact_key": "ch2.black_market_badge",
            "fact_type": "plot",
            "subject": "陆恒",
            "attribute": "道具",
            "value": "获得黑市铭牌",
            "source_chapter": 2,
            "source_agent": "memory_curator",
        }
        batch_ids = []
        item_ids = []
        for batch_run_id in (run_id, "duplicate-memory-run"):
            batch = repo.create_memory_batch(
                project_id,
                chapter_number=2,
                run_id=batch_run_id,
                summary="第2章记忆提取 (1项)",
            )
            item = repo.create_memory_item(
                batch_id=batch["id"],
                project_id=project_id,
                target_table="story_facts",
                operation="create",
                after_json=json.dumps(payload, ensure_ascii=False),
                confidence=0.95,
                evidence_text="陆恒把黑市铭牌扣进掌心。",
                rationale="第2章可信记忆提取",
            )
            batch_ids.append(batch["id"])
            item_ids.append(item["id"])

        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 2,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["chapter_status"] == "published"
        assert data["memory_apply"]["memory_apply_processed"] is True
        assert data["memory_apply"]["items_processed"] == 1
        assert data["memory_apply"]["dedupe"]["ignored_count"] == 1
        batch_statuses = [repo.get_memory_batch(batch_id)["status"] for batch_id in batch_ids]
        item_statuses = [repo.get_memory_item(item_id)["status"] for item_id in item_ids]
        assert sorted(batch_statuses) == ["applied", "ignored"]
        assert sorted(item_statuses) == ["applied", "ignored"]
        run = repo.get_workflow_runs_for_project(project_id, chapter_number=2, limit=1)[0]
        assert run["status"] == "completed"
        assert run["current_node"] == "publish"
        assert repo.get_memory_curator_lock(project_id, 2) is None
        assert repo.get_chapter(project_id, 2)["status"] == "published"
        fact = repo.get_story_fact_by_key(project_id, "ch2.black_market_badge")
        assert fact is not None
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_obsolete_session_action_points_to_cleanup():
    """When a paused+disconnected session is obsolete and NOT yet detected
    by the active-session endpoint, the health-summary must report it
    with a cleanup action."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-obsolete-action"
        repo.create_project(
            project_id=project_id,
            name="Obsolete Action Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="published")
        repo.add_chapter(project_id, 2, "第二章", status="reviewed")

        session = repo.create_auto_run_session(
            project_id,
            chapter_start=2,
            chapter_end=10,
            max_steps=5,
            dry_run=False,
            stop_on_review=True,
        )
        repo.create_auto_run_step(
            session["id"],
            step_number=1,
            action="generate_chapter",
            label="生成第 2 章",
            target_chapter=2,
        )
        repo.update_auto_run_session_status(
            session["id"],
            "paused",
            stop_reason="client_disconnected",
        )

        # Query health-summary BEFORE the active-session endpoint
        # auto-stops the obsolete session
        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # The health-summary should detect the obsolete session
        obsolete_items = [
            item for item in data["items"] if item["key"].startswith("obsolete_session:")
        ]
        assert len(obsolete_items) >= 1
        obsolete_item = obsolete_items[0]
        assert obsolete_item["action_label"] == "清理旧会话"
        assert obsolete_item["session_id"] == session["id"]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_terminal_chapter_running_workflow_is_reconciled_by_health_summary():
    """When a terminal chapter still has a running workflow_run, health-summary
    must reconcile the stale run instead of keeping a phantom running state."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-contradiction"
        repo.create_project(
            project_id=project_id,
            name="Contradiction Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        # Chapter is "reviewed" but still has a running workflow
        repo.add_chapter(project_id, 1, "第一章", status="reviewed")

        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="editor")
        # Make the run recent (not stale), so we only get the contradiction
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_runs SET started_at=datetime('now','-1 minutes','+8 hours') WHERE id=?",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["contradictions"] == 0
        assert not [
            item for item in data["items"]
            if item["key"].startswith("chapter_workflow_contradiction:")
        ]

        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT status, current_node, completed_at FROM workflow_runs WHERE id=?",
                (run_id,),
            ).fetchone()
            assert row["status"] == "completed"
            assert row["current_node"] == "awaiting_publish"
            assert row["completed_at"]
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_stream_endpoint_rejects_terminal_chapter():
    """GET /run/chapter/stream must return an error event for terminal-status
    chapters, just like POST /run/chapter returns CHAPTER_ALREADY_COMPLETED."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-stream-terminal"
        repo.create_project(
            project_id=project_id,
            name="Stream Terminal Guard Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        # Test reviewed status (the most risky — it was not short-circuited before)
        repo.add_chapter(project_id, 1, "第一章", status="reviewed")

        resp = client.get(f"/api/run/chapter/stream?project_id={project_id}&chapter=1")
        assert resp.status_code == 200
        # SSE response — parse the event
        body = resp.text
        assert "run_error" in body
        assert "CHAPTER_ALREADY_COMPLETED" in body or "终态" in body
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_stream_endpoint_rejects_running_workflow():
    """GET /run/chapter/stream must return an error event when a workflow
    is already running for the target chapter."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-stream-running"
        repo.create_project(
            project_id=project_id,
            name="Stream Running Guard Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="drafted")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="editor")

        resp = client.get(f"/api/run/chapter/stream?project_id={project_id}&chapter=1")
        assert resp.status_code == 200
        body = resp.text
        assert "run_error" in body
        assert "WORKFLOW_ALREADY_RUNNING" in body or "运行的工作流" in body
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_run_detail_reconciles_terminal_running_workflow_and_tasks():
    """Opening run detail for a terminal chapter must not keep showing
    a stale running workflow or running node."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-run-detail-reconcile"
        repo.create_project(
            project_id=project_id,
            name="Run Detail Reconcile Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="published")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="polisher")
        task_id = repo.start_task(
            project_id,
            1,
            "write",
            "polisher",
            workflow_run_id=run_id,
        )

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["workflow_status"] == "completed"
        assert data["chapter_status"] == "published"
        assert data["current_node"] == "publish"
        assert data["reconciled_terminal_run"] is True
        assert data["reconciled_running_tasks"] == 1
        assert all(step["status"] != "running" for step in data["steps"])

        conn = repo._conn()
        try:
            run = conn.execute(
                "SELECT status, current_node FROM workflow_runs WHERE id=?",
                (run_id,),
            ).fetchone()
            task = conn.execute(
                "SELECT status, completed_at FROM task_status WHERE id=?",
                (task_id,),
            ).fetchone()
            assert run["status"] == "completed"
            assert run["current_node"] == "publish"
            assert task["status"] == "completed"
            assert task["completed_at"]
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_unified_guard_covers_all_entry_points():
    """All three generation entry points must import the shared guard module."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    guard_module = os.path.join(base, "novel_factory", "api", "routes", "_run_guards.py")
    run_py = os.path.join(base, "novel_factory", "api", "routes", "run.py")
    runs_py = os.path.join(base, "novel_factory", "api", "routes", "runs.py")
    prod_py = os.path.join(base, "novel_factory", "api", "routes", "production.py")

    assert os.path.exists(guard_module), "_run_guards.py must exist"

    for path, name in [(run_py, "run.py"), (runs_py, "runs.py"), (prod_py, "production.py")]:
        content = open(path).read()
        assert "check_chapter_run_guard" in content, f"{name} must import check_chapter_run_guard"


def test_published_chapter_with_stale_workflow_is_auto_closed():
    """A published chapter with a stale running workflow should be closed
    automatically so it does not appear as still running."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-published-stale"
        repo.create_project(
            project_id=project_id,
            name="Published Stale Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo.add_chapter(project_id, 1, "第一章", status="published")

        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="polisher")
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_runs SET started_at=datetime('now','-2 hours','+8 hours') WHERE id=?",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.get(f"/api/projects/{project_id}/production/health-summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        keys = [item["key"].split(":")[0] for item in data["items"]]
        assert "stale_run" not in keys
        assert "chapter_workflow_contradiction" not in keys
        assert data["summary"]["stale_runs"] == 0
        assert data["summary"]["contradictions"] == 0

        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT status, current_node, completed_at FROM workflow_runs WHERE id=?",
                (run_id,),
            ).fetchone()
            assert row["status"] == "completed"
            assert row["current_node"] == "publish"
            assert row["completed_at"]
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_terminal_chapter_cannot_be_regenerated():
    """POST /run/chapter must be rejected if the chapter is already in
    a terminal state (reviewed / awaiting_publish / published)."""
    client, repo, db_path = _client_with_repo()
    try:
        project_id = "v5515-terminal-guard"
        repo.create_project(
            project_id=project_id,
            name="Terminal Guard Test",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        # Test all three terminal statuses
        for status in ("reviewed", "awaiting_publish", "published"):
            ch_num = {"reviewed": 1, "awaiting_publish": 2, "published": 3}[status]
            repo.add_chapter(project_id, ch_num, f"第{ch_num}章", status=status)

        stale_run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(stale_run_id, status="running", current_node="editor")

        for status, ch_num in [("reviewed", 1), ("awaiting_publish", 2), ("published", 3)]:
            resp = client.post("/api/run/chapter", json={
                "project_id": project_id,
                "chapter": ch_num,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is False, f"Expected error for {status} chapter {ch_num}"
            assert data["error"]["code"] == "CHAPTER_ALREADY_COMPLETED"
            assert "终态" in data["error"]["message"] or status in data["error"]["message"]

        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT status, current_node FROM workflow_runs WHERE id=?",
                (stale_run_id,),
            ).fetchone()
            assert row["status"] == "completed"
            assert row["current_node"] == "awaiting_publish"
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
