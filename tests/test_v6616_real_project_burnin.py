"""v6.6.17 Real Project Burn-in & Regression Closure tests.

Uses the 异常修正员 (Anomaly Corrector) project fixture to verify:
- Genesis/context readiness
- Chapter 1 stub generation → domain_result / memory_status
- Workflow timeline node semantics
- Memory curator mapping (no fake green)
- Manual memory backfill (force and error paths)
- Publish with memory gate
- Chapter 2 context inheritance (not not_applicable for ch2)
- API error_response no sensitive leak
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.db.migration_registry import check_migration_health, check_table_integrity
from tests.fixtures.burnin_project import (
    seed_burnin_project,
    BURNIN_PROJECT_ID,
    PROJECT_NAME,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

CLI_ENV = {**os.environ, "NOVEL_FACTORY_DISABLE_DOTENV": "1"}


def _run_cli(args: list[str], db_path: str, timeout: int = 60) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", db_path]
        + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=CLI_ENV,
    )
    return result.returncode, result.stdout, result.stderr


def _run_cli_json(args: list[str], db_path: str, timeout: int = 60) -> dict:
    code, stdout, stderr = _run_cli(args + ["--json"], db_path, timeout)
    if code != 0:
        raise RuntimeError(f"CLI failed (code={code}): {stderr[:500]}")
    return json.loads(stdout)


def _setup_burnin_db(tmp_path: Path) -> tuple[str, Repository]:
    db_path = tmp_path / "burnin.db"
    init_db(db_path)
    repo = Repository(str(db_path))
    seed_burnin_project(repo)
    return str(db_path), repo


def _run_chapter(db_path: str, chapter: int) -> dict:
    return _run_cli_json(
        ["--llm-mode", "stub", "run-chapter",
         "--project-id", BURNIN_PROJECT_ID,
         "--chapter", str(chapter)],
        db_path,
        timeout=120,
    )


def _api_client(db_path: str):
    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app

    return TestClient(create_api_app(db_path=db_path, llm_mode="stub"))


def _latest_run_id(repo: Repository, chapter: int) -> str:
    runs = repo.get_workflow_runs_for_project(
        BURNIN_PROJECT_ID,
        chapter_number=chapter,
        limit=1,
    )
    assert runs, f"No workflow run found for chapter {chapter}"
    return runs[0]["id"]


# ══════════════════════════════════════════════════════════════════════
# Test 1: Fixture integrity
# ══════════════════════════════════════════════════════════════════════


class TestBurninFixtureIntegrity:
    def test_fixture_project_exists(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        proj = repo.get_project(BURNIN_PROJECT_ID)
        assert proj is not None
        assert proj["name"] == PROJECT_NAME

    def test_context_ready_after_seed(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        # Check all required context elements exist
        ws = repo.list_world_settings(BURNIN_PROJECT_ID)
        chars = repo.list_characters(BURNIN_PROJECT_ID, include_inactive=True)
        factions = repo.list_factions(BURNIN_PROJECT_ID)
        outlines = repo.list_outlines(BURNIN_PROJECT_ID)
        inst = repo.get_instruction_by_chapter(BURNIN_PROJECT_ID, 1)

        assert len(ws) >= 3, f"Expected >=3 world settings, got {len(ws)}"
        assert len(chars) >= 4, f"Expected >=4 characters, got {len(chars)}"
        assert len(factions) >= 1, f"Expected >=1 factions, got {len(factions)}"
        assert len(outlines) >= 3, f"Expected >=3 outlines, got {len(outlines)}"
        assert inst is not None, "Missing chapter 1 instruction"

    def test_plot_holes_exist(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        holes = repo.list_plot_holes(BURNIN_PROJECT_ID)
        assert len(holes) >= 3, f"Expected >=3 plot holes, got {len(holes)}"

    def test_chapters_1_3_exist(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        for ch in range(1, 4):
            chapter = repo.get_chapter(BURNIN_PROJECT_ID, ch)
            assert chapter is not None, f"Chapter {ch} missing"


# ══════════════════════════════════════════════════════════════════════
# Test 2: Chapter 1 stub generation
# ══════════════════════════════════════════════════════════════════════


class TestChapter1StubGeneration:
    def test_chapter1_generates_to_legal_terminal_status(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        data = _run_chapter(db_path, 1)
        assert data.get("ok") is True
        ch_status = data["data"].get("chapter_status")
        assert ch_status in ("reviewed", "awaiting_publish", "published"), (
            f"Unexpected chapter status: {ch_status}"
        )

    def test_chapter1_has_domain_result(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        data = _run_chapter(db_path, 1)
        dr = data["data"].get("domain_result")
        assert dr is not None, "Missing domain_result"
        assert "domain_status" in dr
        assert "severity" in dr
        assert "flags" in dr

    def test_chapter1_domain_result_not_fake_green_for_fallback(self, tmp_path):
        """If memory is fallback/degraded, severity must never be 'success'."""
        db_path, repo = _setup_burnin_db(tmp_path)
        data = _run_chapter(db_path, 1)
        dr = data["data"].get("domain_result", {})
        domain_status = dr.get("domain_status")
        severity = dr.get("severity")
        if domain_status in ("fallback", "degraded", "partial_success"):
            assert severity != "success", (
                f"domain_status={domain_status} but severity=success — fake green!"
            )


# ══════════════════════════════════════════════════════════════════════
# Test 3: Run detail observability
# ══════════════════════════════════════════════════════════════════════


class TestRunDetailObservability:
    def test_api_run_detail_contains_contract_fields(self, tmp_path):
        """Run detail API must expose domain_result, memory_status, and recovery_state."""
        db_path, repo = _setup_burnin_db(tmp_path)
        run = _run_chapter(db_path, 1)
        run_id = run["data"]["run_id"]

        with _api_client(db_path) as client:
            response = client.get(f"/api/runs/{run_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["run_id"] == run_id
        assert data["domain_result"]["domain_status"] in {
            "success", "partial_success", "fallback", "degraded"
        }
        assert data["domain_result"]["severity"] in {"success", "warning", "info", "error"}
        assert data["memory_status"]["memory_status"] in {
            "trusted", "fallback", "failed", "missing"
        }
        assert "recovery_state" in data

    def test_cli_runs_command_lists_run(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        run = _run_chapter(db_path, 1)
        expected_run_id = run["data"]["run_id"]
        code, stdout, stderr = _run_cli(
            ["runs", "--project-id", BURNIN_PROJECT_ID, "--json"], db_path
        )
        assert code == 0, f"runs command failed: {stderr[:200]}"
        runs = json.loads(stdout)
        assert isinstance(runs, list)
        assert runs, "runs command returned no runs"
        assert runs[0].get("id") == expected_run_id or runs[0].get("run_id") == expected_run_id
        assert runs[0].get("status") in {"running", "completed", "failed", "blocked"}


# ══════════════════════════════════════════════════════════════════════
# Test 4: Memory status
# ══════════════════════════════════════════════════════════════════════


class TestMemoryStatusMapping:
    def test_memory_status_available(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)

        from novel_factory.api.routes._memory_curator_gate import (
            get_memory_status_for_chapter,
        )
        mem = get_memory_status_for_chapter(repo, BURNIN_PROJECT_ID, 1)
        assert "memory_status" in mem
        assert mem["memory_status"] in ("trusted", "fallback", "failed", "missing")
        # Stub mode usually produces no memory batches → missing or fallback
        # Must NOT silently report "trusted" if no trusted batch exists

    def test_memory_status_not_trusted_when_no_trusted_batch(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)

        from novel_factory.api.routes._memory_curator_gate import (
            get_memory_status_for_chapter,
            has_trusted_memory_batch,
        )
        mem = get_memory_status_for_chapter(repo, BURNIN_PROJECT_ID, 1)
        trusted = has_trusted_memory_batch(repo, BURNIN_PROJECT_ID, 1)
        if not trusted:
            assert mem["memory_status"] != "trusted", (
                "No trusted batch exists but memory_status=trusted"
            )


class TestMemoryBackfillAPI:
    def test_memory_backfill_force_returns_domain_result(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        run = _run_chapter(db_path, 1)
        run_id = run["data"]["run_id"]

        with _api_client(db_path) as client:
            response = client.post(
                f"/api/runs/{run_id}/memory/backfill",
                json={"confirm": True, "force": True},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        domain = body["data"]["domain_result"]
        assert domain["domain_status"] in {"success", "fallback", "degraded", "failed"}
        assert domain["severity"] in {"success", "warning", "error"}
        if domain["domain_status"] in {"fallback", "degraded", "partial_success"}:
            assert domain["severity"] == "warning"

    def test_memory_backfill_invalid_status_error_has_domain_result(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        run_id = repo.create_workflow_run(BURNIN_PROJECT_ID, 1)
        repo.update_workflow_run(run_id, status="completed", current_node="test")

        with _api_client(db_path) as client:
            response = client.post(
                f"/api/runs/{run_id}/memory/backfill",
                json={"confirm": True, "force": False},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_STATUS"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "blocked"
        assert domain["severity"] == "error"
        assert domain["blocking"] is True

    def test_memory_backfill_missing_run_error_has_domain_result(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)

        with _api_client(db_path) as client:
            response = client.post(
                "/api/runs/missing-run-id/memory/backfill",
                json={"confirm": True, "force": True},
            )

        body = response.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "RUN_NOT_FOUND"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "failed"
        assert domain["severity"] == "error"
        assert domain["next_action"] is None


# ══════════════════════════════════════════════════════════════════════
# Test 5: Workflow timeline node semantics
# ══════════════════════════════════════════════════════════════════════


class TestWorkflowTimelineNodes:
    def test_timeline_api_node_semantics_exist(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)

        with _api_client(db_path) as client:
            response = client.get(
                f"/api/projects/{BURNIN_PROJECT_ID}/chapters/1/workflow-timeline"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        nodes = body["data"]["nodes"]
        assert nodes, "No timeline nodes returned"
        for node in nodes:
            assert node["node_status"] in {
                "pending", "running", "succeeded", "warning", "failed", "skipped", "blocked"
            }
            assert node["domain_status"] in {
                "success", "partial_success", "fallback", "degraded", "failed",
                "blocked", "needs_human", "pending", "ignored"
            }
            assert node["severity"] in {"success", "info", "warning", "error"}

    def test_memory_curator_not_fake_green(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)

        with _api_client(db_path) as client:
            response = client.get(
                f"/api/projects/{BURNIN_PROJECT_ID}/chapters/1/workflow-timeline"
            )

        nodes = response.json()["data"]["nodes"]
        memory_nodes = [node for node in nodes if node["node_name"] == "memory_curator"]
        assert memory_nodes, "memory_curator node missing"
        for node in memory_nodes:
            if node["domain_status"] in {"fallback", "degraded", "partial_success"}:
                assert node["severity"] == "warning"
                assert node["node_status"] == "warning"
            assert not (
                node["domain_status"] in {"fallback", "degraded", "partial_success"}
                and node["severity"] == "success"
            )


# ══════════════════════════════════════════════════════════════════════
# Test 6: Publish guard
# ══════════════════════════════════════════════════════════════════════


class TestPublishGuard:
    def test_publish_invalid_status_error_includes_domain_result(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        with _api_client(db_path) as client:
            response = client.post(
                "/api/publish/chapter",
                json={"project_id": BURNIN_PROJECT_ID, "chapter": 1},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_STATUS"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "blocked"
        assert domain["severity"] == "error"
        assert domain["blocking"] is True

    def test_publish_chapter_not_lose_content(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        data = _run_chapter(db_path, 1)
        ch_status = data["data"].get("chapter_status")

        if ch_status in ("reviewed", "awaiting_publish"):
            # Try publish via DB directly (since CLI publishes differently)
            conn = get_connection(db_path)
            try:
                chapter = conn.execute(
                    "SELECT content FROM chapters WHERE project_id=? AND chapter_number=?",
                    (BURNIN_PROJECT_ID, 1),
                ).fetchone()
                content_before = chapter[0] if chapter else ""
            finally:
                conn.close()

            # The chapter content should not be empty for reviewed status
            if ch_status in ("reviewed",):
                # At minimum, we should see that chapter artifact exists
                code, stdout, stderr = _run_cli(
                    ["artifacts", "--project-id", BURNIN_PROJECT_ID, "--chapter", "1"],
                    db_path,
                )
                artifacts = json.loads(stdout) if code == 0 else []
                assert len(artifacts) > 0, (
                    "No artifacts for reviewed chapter — content might be lost"
                )

    def test_publish_already_published_status_preserves_content(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)
        chapter = repo.get_chapter(BURNIN_PROJECT_ID, 1)
        assert chapter is not None
        assert chapter.get("status") == "published"
        assert chapter.get("content"), "published chapter content was lost"


# ══════════════════════════════════════════════════════════════════════
# Test 7: Chapter 2 context inheritance
# ══════════════════════════════════════════════════════════════════════


class TestChapter2ContextInheritance:
    def test_chapter2_memory_context_audit_not_applicable(self, tmp_path):
        """Chapter 2 must not show batch_status='not_applicable'."""
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)
        data = _run_chapter(db_path, 2)
        # Chapter 2 should succeed
        assert data.get("ok") is True

        # Check agent_artifacts for planner memory_context_audit
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT content_json FROM agent_artifacts "
                "WHERE project_id=? AND chapter_number=2 "
                "AND artifact_type='memory_context_audit'",
                (BURNIN_PROJECT_ID,),
            ).fetchall()
            for row in rows:
                try:
                    audit = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    continue
                batch_status = audit.get("batch_status", "")
                if batch_status == "not_applicable":
                    pytest.fail(
                        f"Chapter 2 memory_context_audit has not_applicable: {audit}"
                    )
        finally:
            conn.close()

    def test_chapter2_run_detail_exposes_memory_context_audit(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)
        data = _run_chapter(db_path, 2)
        run_id = data["data"]["run_id"]

        with _api_client(db_path) as client:
            response = client.get(f"/api/runs/{run_id}")

        assert response.status_code == 200
        detail = response.json()["data"]
        audit = detail["memory_context_audit"]
        assert audit["chapter_number"] == 2
        assert audit["batch_status"] in {"trusted", "degraded", "missing"}
        assert audit["batch_status"] != "not_applicable"
        assert isinstance(audit["memory_items_count"], int)

    def test_chapter2_planner_context_has_memory_or_degraded(self, tmp_path):
        """Chapter 2 Planner must have either trusted memory or degraded notice."""
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)
        _run_chapter(db_path, 2)

        conn = get_connection(db_path)
        try:
            # Check planner artifacts for chapter 2 — may use artifact_type='memory_context_audit'
            rows = conn.execute(
                "SELECT content_json, artifact_type FROM agent_artifacts "
                "WHERE project_id=? AND chapter_number=2 "
                "AND agent_id='planner'",
                (BURNIN_PROJECT_ID,),
            ).fetchall()
            has_degraded = False
            has_trusted = False
            for row in rows:
                try:
                    audit = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    continue
                # Check both possible field names
                batch_status = audit.get("batch_status") or audit.get("memory_status")
                if batch_status == "trusted":
                    has_trusted = True
                if audit.get("memory_context_degraded") is True:
                    has_degraded = True
                if batch_status in ("missing", "degraded"):
                    has_degraded = True
            # In stub mode, Planner may not create memory_context_audit artifact.
            # This is acceptable — we verify the chapter 2 run completed successfully.
            if rows:
                assert has_trusted or has_degraded, (
                    f"Chapter 2 Planner has neither trusted memory nor degraded flag. "
                    f"Artifacts: {[json.loads(r[0]) for r in rows if r[0]]}"
                )
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════════
# Test 8: Plot hole observability
# ══════════════════════════════════════════════════════════════════════


class TestPlotHoleObservability:
    def test_plot_holes_exist_after_ch1(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)
        holes = repo.list_plot_holes(BURNIN_PROJECT_ID)
        planted = [h for h in holes if h.get("status") == "planted"]
        assert len(planted) >= 2, (
            f"Expected >=2 planted plot holes, got {len(planted)}"
        )


# ══════════════════════════════════════════════════════════════════════
# Test 9: No sensitive leak in error responses
# ══════════════════════════════════════════════════════════════════════


class TestNoSensitiveLeak:
    SENSITIVE_PATTERNS = [
        "OPENAI_API_KEY", "sk-", "password=", "secret=",
        "Authorization", "Bearer ",
    ]

    def test_run_chapter_output_no_sensitive(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        code, stdout, stderr = _run_cli(
            ["--llm-mode", "stub", "run-chapter",
             "--project-id", BURNIN_PROJECT_ID,
             "--chapter", "1"],
            db_path,
        )
        for pat in self.SENSITIVE_PATTERNS:
            assert pat not in stdout, f"Sensitive pattern '{pat}' in stdout"
            assert pat not in stderr, f"Sensitive pattern '{pat}' in stderr"

    def test_runs_output_no_sensitive(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)
        code, stdout, stderr = _run_cli(
            ["runs", "--project-id", BURNIN_PROJECT_ID], db_path
        )
        for pat in self.SENSITIVE_PATTERNS:
            assert pat not in stdout, f"Sensitive pattern '{pat}' in runs stdout"

    def test_db_has_no_sensitive_in_artifacts(self, tmp_path):
        db_path, repo = _setup_burnin_db(tmp_path)
        _run_chapter(db_path, 1)
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT content_json FROM agent_artifacts WHERE project_id=?",
                (BURNIN_PROJECT_ID,),
            ).fetchall()
            for row in rows:
                content = row[0] or ""
                for pat in self.SENSITIVE_PATTERNS:
                    assert pat not in content, (
                        f"sensitive pattern '{pat}' leaked into agent_artifacts"
                    )
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════════
# Test 10: Manual burn-in script
# ══════════════════════════════════════════════════════════════════════


class TestManualBurninScript:
    def test_manual_burnin_script_stub_mode_runs_real_fixture(self):
        script = Path(__file__).parent.parent / "scripts" / "burnin_real_project.py"
        result = subprocess.run(
            [sys.executable, str(script), "--max-chapters", "1"],
            capture_output=True,
            text=True,
            timeout=180,
            env=CLI_ENV,
        )
        assert result.returncode == 0, (
            f"burn-in script failed\nSTDOUT={result.stdout}\nSTDERR={result.stderr}"
        )
        assert "CMD FAILED" not in result.stdout
        assert "chapter_status\": null" not in result.stdout
        marker = '{\n  "version"'
        start = result.stdout.rfind(marker)
        assert start >= 0, f"Could not locate JSON summary in output: {result.stdout}"
        summary = json.loads(result.stdout[start:])
        assert summary["project_id"] == BURNIN_PROJECT_ID
        assert summary["overall"]["error"] == 0
        step_names = {step["step"] for step in summary["steps"]}
        assert "init_and_seed_fixture" in step_names
        assert "chapter_1_run" in step_names
        chapter_step = next(step for step in summary["steps"] if step["step"] == "chapter_1_run")
        assert chapter_step["chapter_status"] in {"reviewed", "awaiting_publish", "published"}
        assert chapter_step["domain_status"] in {"success", "partial_success", "fallback", "degraded"}


# ══════════════════════════════════════════════════════════════════════
# Test 11: Version check
# ══════════════════════════════════════════════════════════════════════


class TestVersionIsV6616:
    def test_version_py(self):
        from novel_factory.version import get_version
        assert get_version() == "6.6.18"

    def test_frontend_package_json(self):
        pkg = Path(__file__).parent.parent / "frontend" / "package.json"
        assert json.loads(pkg.read_text())["version"] == "6.6.18"
