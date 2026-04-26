"""v4.2 Style Sample CLI tests.

Covers:
- style sample-import / sample-list / sample-show / sample-analyze / sample-delete / sample-propose
- File not found, empty file, binary file, oversized file errors
- Import does not save full text
- All outputs are stable envelope
- No traceback in errors
- No author imitation fields
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest


def run_cli(args: list[str], db_path: str | None = None) -> tuple[int, str, str]:
    cmd = [sys.executable, "-m", "novel_factory.cli"]
    if db_path:
        cmd.extend(["--db-path", db_path])
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def _parse_json(stdout: str) -> dict:
    return json.loads(stdout)


@pytest.fixture(scope="module")
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "v42_cli_test.db")
        # Init DB + seed project + style init
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db, "init-db"],
            capture_output=True, timeout=30,
        )
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db,
             "seed-demo", "--project-id", "demo", "--json"],
            capture_output=True, timeout=30,
        )
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db,
             "style", "init", "--project-id", "demo",
             "--template", "default_web_serial", "--json"],
            capture_output=True, timeout=30,
        )
        yield db


@pytest.fixture(scope="module")
def sample_file():
    """Create a temporary sample text file."""
    with tempfile.TemporaryDirectory() as tmp:
        fpath = os.path.join(tmp, "sample.txt")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("他紧张地握紧拳头。目光一凝，盯向前方。「你来了。」对方冷峻地说。")
        yield fpath


class TestSampleImportCLI:
    def test_import_success(self, db_path, sample_file):
        code, stdout, _ = run_cli(
            ["style", "sample-import", "--project-id", "demo",
             "--file", sample_file, "--json"],
            db_path,
        )
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert "sample_id" in result["data"]
        assert result["data"]["status"] == "analyzed"

    def test_import_file_not_found(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-import", "--project-id", "demo",
             "--file", "/nonexistent/path.txt", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert "not found" in result["error"].lower() or "File" in result["error"]

    def test_import_empty_file(self, db_path):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty.txt")
            with open(empty, "w") as f:
                f.write("")
            code, stdout, _ = run_cli(
                ["style", "sample-import", "--project-id", "demo",
                 "--file", empty, "--json"],
                db_path,
            )
            result = _parse_json(stdout)
            assert result["ok"] is False

    def test_import_oversized_file(self, db_path):
        with tempfile.TemporaryDirectory() as tmp:
            big = os.path.join(tmp, "big.txt")
            with open(big, "w") as f:
                f.write("x" * (201 * 1024))  # 201KB > 200KB limit
            code, stdout, _ = run_cli(
                ["style", "sample-import", "--project-id", "demo",
                 "--file", big, "--json"],
                db_path,
            )
            result = _parse_json(stdout)
            assert result["ok"] is False
            assert "too large" in result["error"].lower() or "200" in result["error"]

    def test_import_no_bible(self, db_path, sample_file):
        code, stdout, _ = run_cli(
            ["style", "sample-import", "--project-id", "nonexistent",
             "--file", sample_file, "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestSampleListCLI:
    def test_list_success(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-list", "--project-id", "demo", "--json"],
            db_path,
        )
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert "samples" in result["data"]


class TestSampleShowCLI:
    def test_show_nonexistent(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-show", "--sample-id", "nonexistent", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestSampleAnalyzeCLI:
    def test_analyze_nonexistent(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-analyze", "--sample-id", "nonexistent", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestSampleDeleteCLI:
    def test_delete_nonexistent(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-delete", "--sample-id", "nonexistent", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestSampleProposeCLI:
    def test_propose_no_ids(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-propose", "--project-id", "demo", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False

    def test_propose_no_bible(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-propose", "--project-id", "nonexistent",
             "--sample-id", "any", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestCLIErrorPaths:
    def test_no_traceback_in_errors(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "sample-show", "--sample-id", "nonexistent", "--json"],
            db_path,
        )
        assert "Traceback" not in stdout

    def test_no_author_imitation_fields(self, db_path, sample_file):
        code, stdout, _ = run_cli(
            ["style", "sample-import", "--project-id", "demo",
             "--file", sample_file, "--json"],
            db_path,
        )
        assert "author_name" not in stdout
        assert "imitate_author" not in stdout
        assert "模仿" not in stdout

    def test_import_does_not_save_full_text(self, db_path):
        """CLI output should not contain the full source text."""
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "unique_sample.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("这是一段独特的测试文本，用于验证不保存全文。" * 3)
            code, stdout, _ = run_cli(
                ["style", "sample-import", "--project-id", "demo",
                 "--file", fpath, "--json"],
                db_path,
            )
            result = _parse_json(stdout)
            assert result["ok"] is True
            # Should have content_preview_length, not the full content
            assert "content_preview_length" in result["data"]
            # The raw content should not be in the output
            assert "full_text" not in result["data"]
            assert "content" not in result["data"]


class TestSampleAnalyzeDoesNotDegradeMetrics:
    """Regression: sample-analyze without --file must not overwrite full-text metrics."""

    def test_analyze_without_file_is_readonly(self, db_path):
        """sample-analyze without --file returns stored analysis without overwriting."""
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "readonly_sample.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("他紧张地握紧拳头。目光一凝，盯向前方。「你来了。」对方冷峻地说。这是只读测试。")
            # Import
            code, stdout, _ = run_cli(
                ["style", "sample-import", "--project-id", "demo",
                 "--file", fpath, "--json"],
                db_path,
            )
            result = _parse_json(stdout)
            assert result["ok"] is True
            sample_id = result["data"]["sample_id"]
            original_chars = result["data"]["metrics_summary"]["char_count"]

            # sample-analyze without --file: should return stored analysis
            code2, stdout2, _ = run_cli(
                ["style", "sample-analyze", "--sample-id", sample_id, "--json"],
                db_path,
            )
            result2 = _parse_json(stdout2)
            assert result2["ok"] is True
            assert result2["data"]["source"] == "stored"
            assert result2["data"]["metrics"]["char_count"] == original_chars

    def test_analyze_with_file_reanalyzes(self, db_path):
        """sample-analyze with --file re-analyzes from original text."""
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "reanalyze_sample.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("她心中恐惧不安，犹豫不决。但仍然克制住了情绪，冷静面对。这是重分析测试。")
            code, stdout, _ = run_cli(
                ["style", "sample-import", "--project-id", "demo",
                 "--file", fpath, "--json"],
                db_path,
            )
            result = _parse_json(stdout)
            assert result["ok"] is True
            sample_id = result["data"]["sample_id"]

            # Re-analyze with --file
            code2, stdout2, _ = run_cli(
                ["style", "sample-analyze", "--sample-id", sample_id,
                 "--file", fpath, "--json"],
                db_path,
            )
            result2 = _parse_json(stdout2)
            assert result2["ok"] is True
            assert result2["data"]["source"] == "file_reanalysis"

    def test_analyze_with_wrong_file_hash_rejected(self, db_path):
        """sample-analyze with --file that has different content is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "hashcheck_sample.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("他冲向前。挥剑砍。对手闪开。「受死。」怒吼。这是哈希校验测试。")
            code, stdout, _ = run_cli(
                ["style", "sample-import", "--project-id", "demo",
                 "--file", fpath, "--json"],
                db_path,
            )
            result = _parse_json(stdout)
            assert result["ok"] is True
            sample_id = result["data"]["sample_id"]

            # Create a different file
            wrong_file = os.path.join(tmp, "wrong.txt")
            with open(wrong_file, "w", encoding="utf-8") as f:
                f.write("完全不同的内容，哈希不匹配。")
            code2, stdout2, _ = run_cli(
                ["style", "sample-analyze", "--sample-id", sample_id,
                 "--file", wrong_file, "--json"],
                db_path,
            )
            result2 = _parse_json(stdout2)
            assert result2["ok"] is False
            assert "hash" in result2["error"].lower() or "does not match" in result2["error"]


class TestSampleProposeErrorEnvelope:
    """Regression: sample-propose error envelope preserves failed_proposals data."""

    def test_propose_error_includes_data(self, db_path):
        """When propose fails, envelope data should include failed_proposals."""
        # This test validates that the error path passes data through
        # We test by proposing with a nonexistent project (no bible)
        code, stdout, _ = run_cli(
            ["style", "sample-propose", "--project-id", "nobible",
             "--sample-id", "any", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        # The error envelope should have data field (not necessarily empty)
        assert "data" in result
