"""Tests for v3.7 Review Workbench.

Covers:
- review pack run/serial/range
- decision_hint blocking and warning
- chapter preview not output full text
- timeline time ascending
- diff latest two versions and specified versions
- markdown/json export
- export not overwrite existing file
- all commands read-only
- JSON envelope error paths
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from novel_factory.db.connection import get_connection, init_db
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider


class StubLLM(LLMProvider):
    """Stub LLM that returns valid outputs for each agent type."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self._call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        # Default responses based on schema
        schema_name = getattr(schema, "__name__", "") if schema else ""
        if "Planner" in schema_name:
            return {
                "chapter_brief": {
                    "objective": "推进剧情", "required_events": ["事件1"],
                    "plots_to_plant": [], "plots_to_resolve": [],
                    "ending_hook": "悬念", "constraints": [],
                }
            }
        if "Screenwriter" in schema_name:
            return {"scene_beats": [{"sequence": 1, "scene_goal": "场景目标", "conflict": "冲突", "hook": "钩子"}]}
        if "Author" in schema_name:
            content = "测试章节内容..."
            return {
                "title": "测试章", "content": content,
                "word_count": len(content), "implemented_events": ["事件1"], "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            return {
                "content": "润色后内容", "fact_change_risk": "none",
                "changed_scope": ["sentence", "rhythm"], "summary": "微调表达",
            }
        if "Editor" in schema_name:
            return {
                "pass": True, "score": 92,
                "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 17, "pacing": 17},
                "issues": [], "suggestions": [], "revision_target": None, "state_card": {},
            }
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return "{}"


# ── Test fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary database with migrations."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    return db_path


@pytest.fixture
def repo(tmp_db: Path) -> Repository:
    """Create a repository instance."""
    return Repository(str(tmp_db))


@pytest.fixture
def dispatcher(repo: Repository) -> Dispatcher:
    """Create a dispatcher instance with stub LLM."""
    stub_llm = StubLLM()
    return Dispatcher(repo, llm=stub_llm, max_retries=3)


def _seed_project(repo: Repository) -> None:
    """Seed a test project with chapters."""
    conn = repo._conn()
    try:
        # Create project
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("test_project", "Test Project", "urban"),
        )

        # Create chapters
        for i in range(1, 11):
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test_project", i, f"第{i}章 测试", "published", datetime.now().isoformat(), datetime.now().isoformat()),
            )
            
            # Get chapter id
            row = conn.execute(
                "SELECT id FROM chapters WHERE project_id = ? AND chapter_number = ?",
                ("test_project", i)
            ).fetchone()
            chapter_db_id = row["id"]

            # Create chapter version
            content = f"Chapter {i} content..." * 100  # ~2000 chars
            conn.execute(
                "INSERT INTO chapter_versions (project_id, chapter, version, content, word_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test_project", i, 1, content, len(content.split()), datetime.now().isoformat()),
            )

            # Create quality report
            conn.execute(
                "INSERT INTO quality_reports (project_id, chapter_number, stage, overall_score, pass, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test_project", i, "final", 85.0 + i, 1, datetime.now().isoformat()),
            )

            # Create review
            conn.execute(
                "INSERT INTO reviews (project_id, chapter_id, pass, score, reviewed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("test_project", chapter_db_id, 1, 88 + i, datetime.now().isoformat()),
            )

        conn.commit()
    finally:
        conn.close()


# ── Test 1: review pack --run-id returns chapters, quality, continuity, decision_hint ─────────


def test_review_pack_run_id(dispatcher: Dispatcher, repo: Repository):
    """Test review pack for production run."""
    _seed_project(repo)

    # Create production run
    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    # Create continuity gate
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(run_id=run_id)

    assert result["ok"] is True
    data = result["data"]

    # Check scope
    assert data["scope"]["type"] == "production_run"
    assert data["scope"]["id"] == run_id
    assert data["scope"]["from_chapter"] == 1
    assert data["scope"]["to_chapter"] == 3

    # Check chapters
    assert len(data["chapters"]) == 3

    # Check decision_hint
    assert "decision_hint" in data
    assert "can_approve" in data["decision_hint"]
    assert "blocking_reasons" in data["decision_hint"]
    assert "warnings" in data["decision_hint"]

    # Check continuity_gate
    assert data["continuity_gate"]["status"] == "passed"


# ── Test 2: review pack --serial-plan-id aggregates serial plan current queue/run ─────────


def test_review_pack_serial_plan(dispatcher: Dispatcher, repo: Repository):
    """Test review pack for serial plan."""
    _seed_project(repo)

    # Create serial plan
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Enqueue next batch
    dispatcher.enqueue_serial_next(serial_plan_id)

    # Get queue item
    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    # Create production run
    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(serial_plan_id=serial_plan_id)

    assert result["ok"] is True
    data = result["data"]

    # Check scope
    assert data["scope"]["type"] == "serial_plan"
    assert data["scope"]["id"] == serial_plan_id

    # Check chapters
    assert len(data["chapters"]) == 3


# ── Test 3: review pack --project-id --from-chapter --to-chapter aggregates by range ─────────


def test_review_pack_range(dispatcher: Dispatcher, repo: Repository):
    """Test review pack for chapter range."""
    _seed_project(repo)

    result = dispatcher.build_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=5,
    )

    assert result["ok"] is True
    data = result["data"]

    # Check scope
    assert data["scope"]["type"] == "chapter_range"
    assert data["scope"]["from_chapter"] == 1
    assert data["scope"]["to_chapter"] == 5

    # Check chapters
    assert len(data["chapters"]) == 5


# ── Test 4: multi-chapter without continuity gate sets can_approve=false ─────────


def test_decision_hint_blocks_no_continuity_gate(dispatcher: Dispatcher, repo: Repository):
    """Test that multi-chapter batch without continuity gate cannot approve."""
    _seed_project(repo)

    # Create production run WITHOUT continuity gate
    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(run_id=run_id)

    assert result["ok"] is True
    hint = result["data"]["decision_hint"]

    assert hint["can_approve"] is False
    assert "continuity_gate_not_run" in hint["blocking_reasons"]


# ── Test 5: continuity gate failed/error blocks approve ─────────


def test_decision_hint_blocks_continuity_gate_failed(dispatcher: Dispatcher, repo: Repository):
    """Test that continuity gate failed/error blocks approve."""
    _seed_project(repo)

    # Create production run with failed continuity gate
    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "failed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(run_id=run_id)

    assert result["ok"] is True
    hint = result["data"]["decision_hint"]

    assert hint["can_approve"] is False
    assert any("continuity_gate_failed" in r for r in hint["blocking_reasons"])


# ── Test 6: continuity gate warning allows approve but with warning ─────────


def test_decision_hint_warning_continuity_gate(dispatcher: Dispatcher, repo: Repository):
    """Test that continuity gate warning allows approve but with warning."""
    _seed_project(repo)

    # Create production run with warning continuity gate
    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "warning", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(run_id=run_id)

    assert result["ok"] is True
    hint = result["data"]["decision_hint"]

    assert hint["can_approve"] is True
    assert "continuity_gate_warning" in hint["warnings"]


# ── Test 7: quality report pass=false blocks approve ─────────


def test_decision_hint_blocks_quality_fail(dispatcher: Dispatcher, repo: Repository):
    """Test that quality report pass=false blocks approve."""
    _seed_project(repo)

    # Update quality report to fail
    conn = repo._conn()
    conn.execute(
        "UPDATE quality_reports SET pass = 0 WHERE project_id = 'test_project' AND chapter_number = 1",
    )
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=3,
    )

    assert result["ok"] is True
    hint = result["data"]["decision_hint"]

    assert hint["can_approve"] is False
    assert any("chapter_1_quality_blocking" in r for r in hint["blocking_reasons"])


# ── Test 8: latest review passed=false blocks approve ─────────


def test_decision_hint_blocks_review_failed(dispatcher: Dispatcher, repo: Repository):
    """Test that latest review passed=false blocks approve."""
    _seed_project(repo)

    # Get chapter id for chapter 1
    conn = repo._conn()
    row = conn.execute(
        "SELECT id FROM chapters WHERE project_id = 'test_project' AND chapter_number = 1"
    ).fetchone()
    chapter_db_id = row["id"]
    
    # Update review to fail
    conn.execute(
        "UPDATE reviews SET pass = 0 WHERE chapter_id = ?",
        (chapter_db_id,),
    )
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=3,
    )

    assert result["ok"] is True
    hint = result["data"]["decision_hint"]

    assert hint["can_approve"] is False
    assert any("chapter_1_review_failed" in r for r in hint["blocking_reasons"])


# ── Test 9: queue item not completed blocks approve ─────────


def test_decision_hint_blocks_queue_not_completed(dispatcher: Dispatcher, repo: Repository):
    """Test that queue item not completed blocks approve."""
    _seed_project(repo)

    # Create serial plan
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Enqueue next batch
    dispatcher.enqueue_serial_next(serial_plan_id)

    # Queue item is pending, not completed
    result = dispatcher.build_review_pack(serial_plan_id=serial_plan_id)

    assert result["ok"] is True
    hint = result["data"]["decision_hint"]

    assert hint["can_approve"] is False
    assert "queue_item_not_completed" in hint["blocking_reasons"]


# ── Test 10: review chapter returns preview not full text ─────────


def test_review_chapter_preview_only(dispatcher: Dispatcher, repo: Repository):
    """Test that review chapter returns preview, not full text."""
    _seed_project(repo)

    result = dispatcher.get_review_chapter(project_id="test_project", chapter=1)

    assert result["ok"] is True
    data = result["data"]

    # Check content_preview is limited
    if data.get("content_preview"):
        assert len(data["content_preview"]) <= 800

    # Check word_count is present
    assert "word_count" in data
    assert data["word_count"] > 0


# ── Test 11: review timeline events are time ascending ─────────


def test_review_timeline_time_ascending(dispatcher: Dispatcher, repo: Repository):
    """Test that timeline events are sorted by time ascending."""
    _seed_project(repo)

    # Create serial plan
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Enqueue and advance
    dispatcher.enqueue_serial_next(serial_plan_id)

    result = dispatcher.get_review_timeline(serial_plan_id=serial_plan_id)

    assert result["ok"] is True
    events = result["data"]["events"]

    # Check events are sorted by time
    if len(events) > 1:
        for i in range(len(events) - 1):
            assert events[i]["time"] <= events[i + 1]["time"]


# ── Test 12: review diff compares latest two versions ─────────


def test_review_diff_latest_two_versions(dispatcher: Dispatcher, repo: Repository):
    """Test that review diff compares latest two versions."""
    _seed_project(repo)

    # Create second version for chapter 1
    conn = repo._conn()
    conn.execute(
        "INSERT INTO chapter_versions (project_id, chapter, version, content, word_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test_project", 1, 2, "Updated chapter 1 content..." * 100, 500, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.get_review_diff(project_id="test_project", chapter=1)

    assert result["ok"] is True
    data = result["data"]

    # Check diff info
    assert "from_version_id" in data
    assert "to_version_id" in data
    assert "word_count_delta" in data
    assert "changed_ratio" in data


# ── Test 13: review diff with specified versions returns envelope ─────────


def test_review_diff_specified_versions(dispatcher: Dispatcher, repo: Repository):
    """Test that review diff with specified versions returns envelope."""
    _seed_project(repo)

    # Create second version for chapter 1
    conn = repo._conn()
    conn.execute(
        "INSERT INTO chapter_versions (project_id, chapter, version, content, word_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test_project", 1, 2, "Updated chapter 1 content..." * 100, 500, datetime.now().isoformat()),
    )
    
    # Get version IDs
    v1_row = conn.execute(
        "SELECT id FROM chapter_versions WHERE project_id = 'test_project' AND chapter = 1 AND version = 1"
    ).fetchone()
    v2_row = conn.execute(
        "SELECT id FROM chapter_versions WHERE project_id = 'test_project' AND chapter = 1 AND version = 2"
    ).fetchone()
    
    conn.commit()
    conn.close()

    result = dispatcher.get_review_diff(
        project_id="test_project",
        chapter=1,
        from_version=str(v1_row["id"]),
        to_version=str(v2_row["id"]),
    )

    assert result["ok"] is True
    data = result["data"]

    assert data["from_version_id"] == v1_row["id"]
    assert data["to_version_id"] == v2_row["id"]


# ── Test 14: review export markdown writes file ─────────


def test_review_export_markdown(dispatcher: Dispatcher, repo: Repository, tmp_path: Path):
    """Test that review export markdown writes file."""
    _seed_project(repo)

    output_path = tmp_path / "review.md"

    result = dispatcher.export_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=3,
        format="markdown",
        output=str(output_path),
    )

    assert result["ok"] is True
    assert output_path.exists()

    # Check markdown content
    content = output_path.read_text()
    assert "# Review Pack" in content
    assert "Decision Hint" in content


# ── Test 15: review export json writes file ─────────


def test_review_export_json(dispatcher: Dispatcher, repo: Repository, tmp_path: Path):
    """Test that review export json writes file."""
    _seed_project(repo)

    output_path = tmp_path / "review.json"

    result = dispatcher.export_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=3,
        format="json",
        output=str(output_path),
    )

    assert result["ok"] is True
    assert output_path.exists()

    # Check json content
    content = output_path.read_text()
    data = json.loads(content)
    assert "scope" in data
    assert "decision_hint" in data


# ── Test 16: review export does not overwrite existing file ─────────


def test_review_export_no_overwrite(dispatcher: Dispatcher, repo: Repository, tmp_path: Path):
    """Test that review export does not overwrite existing file."""
    _seed_project(repo)

    output_path = tmp_path / "review.json"
    output_path.write_text("existing content")

    result = dispatcher.export_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=3,
        format="json",
        output=str(output_path),
    )

    assert result["ok"] is False
    assert "already exists" in result["error"]


# ── Test 17: review export --force overwrites existing file ─────────


def test_review_export_force_overwrite(dispatcher: Dispatcher, repo: Repository, tmp_path: Path):
    """Test that review export --force overwrites existing file."""
    _seed_project(repo)

    output_path = tmp_path / "review.json"
    output_path.write_text("existing content")

    result = dispatcher.export_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=3,
        format="json",
        output=str(output_path),
        force=True,
    )

    assert result["ok"] is True

    # Check file was overwritten
    content = output_path.read_text()
    data = json.loads(content)
    assert "scope" in data


# ── Test 18: all --json error paths return {ok,error,data} ─────────


def test_json_envelope_error_paths(dispatcher: Dispatcher, repo: Repository):
    """Test that all --json error paths return {ok,error,data}."""
    # Test missing run
    result = dispatcher.build_review_pack(run_id="nonexistent")
    assert result["ok"] is False
    assert "error" in result
    assert "data" in result
    assert isinstance(result["data"], dict)

    # Test missing chapter
    result = dispatcher.get_review_chapter(project_id="test_project", chapter=999)
    assert result["ok"] is False
    assert "error" in result
    assert "data" in result

    # Test invalid format
    result = dispatcher.export_review_pack(
        project_id="test_project",
        from_chapter=1,
        to_chapter=3,
        format="invalid",
        output="/tmp/test.json",
    )
    assert result["ok"] is False
    assert "error" in result
    assert "data" in result


# ── Test 19: all review commands are read-only ─────────


def test_review_commands_read_only(dispatcher: Dispatcher, repo: Repository):
    """Test that all review commands do not change state."""
    _seed_project(repo)

    # Get initial state
    conn = repo._conn()
    initial_chapters = conn.execute("SELECT COUNT(*) as cnt FROM chapters").fetchone()["cnt"]
    initial_versions = conn.execute("SELECT COUNT(*) as cnt FROM chapter_versions").fetchone()["cnt"]
    conn.close()

    # Execute review commands
    dispatcher.build_review_pack(project_id="test_project", from_chapter=1, to_chapter=3)
    dispatcher.get_review_chapter(project_id="test_project", chapter=1)
    dispatcher.get_review_timeline(project_id="test_project", chapter=1)
    dispatcher.get_review_diff(project_id="test_project", chapter=1)

    # Check state unchanged
    conn = repo._conn()
    final_chapters = conn.execute("SELECT COUNT(*) as cnt FROM chapters").fetchone()["cnt"]
    final_versions = conn.execute("SELECT COUNT(*) as cnt FROM chapter_versions").fetchone()["cnt"]
    conn.close()

    assert initial_chapters == final_chapters
    assert initial_versions == final_versions


# ── Test 20: full test suite passes ─────────


def test_cli_review_pack_json(tmp_db: Path):
    """Test review pack CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "review", "pack",
         "--project-id", "test_project",
         "--from-chapter", "1",
         "--to-chapter", "3",
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert "scope" in output["data"]


# ── R1: review chapter 不得泄露整章正文 ─────────


def test_review_chapter_no_content_leak(dispatcher: Dispatcher, repo: Repository):
    """R1: review chapter --json must not leak full chapter content."""
    _seed_project(repo)

    result = dispatcher.get_review_chapter("test_project", 1)

    assert result["ok"] is True
    data = result["data"]

    # chapter must not contain content
    assert "content" not in data["chapter"]
    
    # latest_version must not contain content
    assert "content" not in data["latest_version"]
    
    # content_preview must be <= 800 chars
    if data["content_preview"]:
        assert len(data["content_preview"]) <= 800


def test_review_chapter_long_content_not_in_json(dispatcher: Dispatcher, repo: Repository):
    """R1: long chapter content must not appear in JSON string."""
    _seed_project(repo)

    # Create chapter with long content
    conn = repo._conn()
    long_content = "This is a very long chapter content. " * 100  # ~3500 chars
    conn.execute(
        "UPDATE chapter_versions SET content = ? WHERE project_id = 'test_project' AND chapter = 1",
        (long_content,),
    )
    conn.commit()
    conn.close()

    result = dispatcher.get_review_chapter("test_project", 1)

    # Convert to JSON string
    import json
    json_str = json.dumps(result, ensure_ascii=False)

    # Full content must not appear in JSON
    assert long_content not in json_str
    
    # Only preview should appear
    assert result["ok"] is True
    assert result["data"]["content_preview"] == long_content[:800]


# ── R2: run-id review pack 必须正确关联 queue item ─────────


def test_review_pack_run_with_queue_item(dispatcher: Dispatcher, repo: Repository):
    """R2: review pack for run must return queue_item."""
    _seed_project(repo)

    # Create production run
    run_id = "run_queue_test"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    # Create queue item with production_run_id
    conn.execute(
        "INSERT INTO production_queue (id, project_id, from_chapter, to_chapter, status, production_run_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("queue_test", "test_project", 1, 3, "running", run_id, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    # Create continuity gate
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_queue_test", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(run_id=run_id)

    assert result["ok"] is True
    data = result["data"]

    # Must return queue_item
    assert data["queue_item"] is not None
    assert data["queue_item"]["id"] == "queue_test"


def test_decision_hint_blocks_queue_not_completed_for_run(dispatcher: Dispatcher, repo: Repository):
    """R2: decision_hint must detect queue_item_not_completed for run scope."""
    _seed_project(repo)

    # Create production run
    run_id = "run_queue_incomplete"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    # Create queue item with status != completed
    conn.execute(
        "INSERT INTO production_queue (id, project_id, from_chapter, to_chapter, status, production_run_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("queue_incomplete", "test_project", 1, 3, "running", run_id, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    # Create continuity gate
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_incomplete", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    conn.commit()
    conn.close()

    result = dispatcher.build_review_pack(run_id=run_id)

    assert result["ok"] is True
    hint = result["data"]["decision_hint"]

    assert hint["can_approve"] is False
    assert any("queue_item_not_completed" in r for r in hint["blocking_reasons"])


# ── R3: run timeline 必须聚合 queue events ─────────


def test_run_timeline_includes_queue_events(dispatcher: Dispatcher, repo: Repository):
    """R3: run timeline must include production_queue_events."""
    _seed_project(repo)

    # Create production run
    run_id = "run_timeline_test"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    # Create queue item
    conn.execute(
        "INSERT INTO production_queue (id, project_id, from_chapter, to_chapter, status, production_run_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("queue_timeline", "test_project", 1, 3, "completed", run_id, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    
    # Create queue events
    conn.execute(
        "INSERT INTO production_queue_events (id, queue_id, event_type, from_status, to_status, message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("event_1", "queue_timeline", "started", None, "running", "Queue started", datetime.now().isoformat()),
    )
    conn.execute(
        "INSERT INTO production_queue_events (id, queue_id, event_type, from_status, to_status, message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("event_2", "queue_timeline", "completed", "running", "completed", "Queue completed", datetime.now().isoformat()),
    )
    
    conn.commit()
    conn.close()

    result = dispatcher.get_review_timeline(run_id=run_id)

    assert result["ok"] is True
    events = result["data"]["events"]

    # Must include queue events
    queue_events = [e for e in events if e["source"] == "production_queue_events"]
    assert len(queue_events) >= 2

    # Check event types
    event_types = {e["type"] for e in queue_events}
    assert "started" in event_types
    assert "completed" in event_types


# ── R4: review pack scope 必须互斥 ─────────


def test_review_pack_scope_mutual_exclusion_run_and_serial(dispatcher: Dispatcher, repo: Repository):
    """R4: run_id + serial_plan_id must return error."""
    _seed_project(repo)

    result = dispatcher.build_review_pack(
        run_id="run_test",
        serial_plan_id="serial_test"
    )

    assert result["ok"] is False
    assert "only one scope" in result["error"].lower()
    assert result["data"] == {}


def test_review_pack_scope_mutual_exclusion_run_and_range(dispatcher: Dispatcher, repo: Repository):
    """R4: run_id + project range must return error."""
    _seed_project(repo)

    result = dispatcher.build_review_pack(
        run_id="run_test",
        project_id="test_project",
        from_chapter=1,
        to_chapter=3
    )

    assert result["ok"] is False
    assert "only one scope" in result["error"].lower()
    assert result["data"] == {}


def test_review_pack_scope_mutual_exclusion_serial_and_range(dispatcher: Dispatcher, repo: Repository):
    """R4: serial_plan_id + project range must return error."""
    _seed_project(repo)

    result = dispatcher.build_review_pack(
        serial_plan_id="serial_test",
        project_id="test_project",
        from_chapter=1,
        to_chapter=3
    )

    assert result["ok"] is False
    assert "only one scope" in result["error"].lower()
    assert result["data"] == {}


def test_cli_review_pack_scope_error_json(tmp_db: Path):
    """R4: CLI scope error must return {ok, error, data} JSON envelope."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "review", "pack",
         "--run-id", "run_test",
         "--serial-plan-id", "serial_test",
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "error" in output
    assert output["data"] == {}
