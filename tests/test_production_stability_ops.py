from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from novel_factory.ops.memory_governance import audit_project_memory
from novel_factory.ops.quality_acceptance import evaluate_chapter_quality
from novel_factory.ops.recovery_drill import inspect_chapter_recovery


REPO_ROOT = Path(__file__).resolve().parent.parent


class FakeRepo:
    def __init__(self):
        self.characters = []
        self.world_settings = []
        self.story_facts = []
        self.memory_items = []
        self.chapter = {}
        self.latest_run = None
        self.running_tasks = []

    def list_characters(self, project_id, include_inactive=False):
        return self.characters

    def list_world_settings(self, project_id):
        return self.world_settings

    def list_story_facts(self, project_id):
        return self.story_facts

    def list_memory_items_by_project(self, project_id):
        return self.memory_items

    def get_chapter(self, project_id, chapter_number):
        return self.chapter

    def get_latest_workflow_run(self, project_id, chapter_number):
        return self.latest_run

    def _conn(self):
        class _Conn:
            def execute(self, *args, **kwargs):
                return self

            def fetchall(self):
                return []

            def close(self):
                pass

        return _Conn()


def test_quality_acceptance_passes_terminal_complete_chapter():
    chapter = {
        "status": "published",
        "content": "场景推进。" * 900 + "最后，他听见门外传来新的敲门声？",
    }
    beats = [
        {"scene_goal": "推进调查", "conflict": "入口危险", "turn": "发现压印", "hook": "门响"},
        {"scene_goal": "进入缓冲区", "conflict": "拖拽声逼近", "turn": "纸页出现", "hook": "编号暴露"},
    ]

    result = evaluate_chapter_quality(chapter, beats)

    assert result["ok"] is True
    assert result["failed_count"] == 0
    assert result["word_count"] >= 2500


def test_quality_acceptance_reports_actionable_failures():
    result = evaluate_chapter_quality(
        {"status": "drafted", "content": "太短"},
        [{"scene_goal": "目标", "conflict": "", "turn": "", "hook": ""}],
    )

    assert result["ok"] is False
    failed_names = {check["name"] for check in result["checks"] if not check["passed"]}
    assert "terminal_status" in failed_names
    assert "word_count" in failed_names
    assert "scene_beats_complete" in failed_names
    assert result["next_actions"]


def test_memory_governance_detects_duplicates_and_pressure():
    repo = FakeRepo()
    repo.characters = [{"name": "陆澈"}, {"name": "陆澈"}]
    repo.world_settings = [{"title": "七号残段"}, {"title": "七号残段"}]
    repo.story_facts = [
        {"fact_key": "H-Y-2092", "content": "七分钟窗口"},
        {"fact_key": "H-Y-2092", "content": "七分钟窗口"},
    ]
    repo.memory_items = [{"content": "记忆"} for _ in range(3)]

    result = audit_project_memory(
        repo,
        "novel",
        limits={"characters": 1, "story_facts": 1, "memory_items": 2, "context_chars": 10},
    )

    assert result["ok"] is False
    assert "duplicates" in result["warnings"]
    assert "context_pressure" in result["warnings"]
    assert result["duplicate_group_count"] >= 3
    assert result["duplicates"]["world_settings"][0]["value"] == "七号残段"


def test_recovery_drill_marks_stale_running_run():
    repo = FakeRepo()
    now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    repo.chapter = {"status": "drafted"}
    repo.latest_run = {
        "id": "run-1",
        "status": "running",
        "started_at": "2026-05-24 10:00:00",
        "current_node": "author",
    }

    result = inspect_chapter_recovery(repo, "novel", 1, stale_minutes=30, now=now)

    assert result["state"] == "stale_running"
    assert result["recommended_action"] == "mark_stuck_blocked"
    assert "mark_stuck_blocked" in result["safe_actions"]


def test_recovery_drill_accepts_terminal_chapter():
    repo = FakeRepo()
    repo.chapter = {"status": "published"}
    repo.latest_run = {"id": "run-1", "status": "completed", "started_at": "2026-05-24 10:00:00"}

    result = inspect_chapter_recovery(repo, "novel", 1)

    assert result["ok"] is True
    assert result["state"] == "terminal"
    assert result["recommended_action"] == "publish_or_archive"


def test_production_stability_suite_safe_json_mode_without_db_or_real_llm():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "production_stability_suite.py"),
            "--no-release-smoke",
            "--no-soak",
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["ok"] is True
    assert body["real_soak"] is False
    assert any(gate["name"] == "project_gates" and gate.get("skipped") for gate in body["gates"])


def test_production_stability_suite_rejects_empty_chapter_range():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "production_stability_suite.py"),
            "--chapters",
            "0",
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "must be >= 1" in result.stderr
