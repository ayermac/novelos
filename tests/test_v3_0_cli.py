"""Tests for v3.0 CLI commands."""

import json
import pytest
from pathlib import Path

from novel_factory.cli import cmd_batch_run, cmd_batch_status, cmd_batch_review, cmd_batch_continuity
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


class TestV30CLI:
    """Test v3.0 CLI commands."""

    @pytest.fixture
    def tmp_db(self, tmp_path):
        db_path = tmp_path / "test_v30_cli.db"
        init_db(db_path)
        return str(db_path)

    @pytest.fixture
    def repo(self, tmp_db):
        return Repository(tmp_db)

    def _seed_project(self, repo, project_id="demo", num_chapters=3):
        """Seed a project with chapters."""
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            (project_id, "Demo Novel", "urban"),
        )
        for i in range(1, num_chapters + 1):
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status) "
                "VALUES (?, ?, ?, ?)",
                (project_id, i, f"第{i}章", "planned"),
            )
        conn.commit()
        conn.close()

    def test_batch_run_json(self, tmp_db, repo, monkeypatch):
        """Test 'novelos batch run --json'."""
        import sys
        from io import StringIO
        
        self._seed_project(repo, num_chapters=3)
        
        class Args:
            project_id = "demo"
            from_chapter = 1
            to_chapter = 3
            llm_mode = "stub"
            json = True
            config = None
            db_path = tmp_db
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_run(Args())
            output = sys.stdout.getvalue()
            
            # Parse JSON output
            result = json.loads(output)
            
            assert result["ok"] is True
            assert result["error"] is None
            assert "run_id" in result["data"]
            assert result["data"]["project_id"] == "demo"
            assert result["data"]["from_chapter"] == 1
            assert result["data"]["to_chapter"] == 3
        finally:
            sys.stdout = old_stdout

    def test_batch_run_invalid_range_json(self, tmp_db, repo, monkeypatch):
        """Test 'novelos batch run' with invalid range returns JSON error."""
        import sys
        from io import StringIO
        
        self._seed_project(repo, num_chapters=3)
        
        class Args:
            project_id = "demo"
            from_chapter = 3
            to_chapter = 1
            llm_mode = "stub"
            json = True
            config = None
            db_path = tmp_db
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_run(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"] is False
            assert result["error"] is not None
            assert "from_chapter" in result["error"]
        finally:
            sys.stdout = old_stdout

    def test_batch_status_json(self, tmp_db, repo, monkeypatch):
        """Test 'novelos batch status --json'."""
        import sys
        from io import StringIO
        
        self._seed_project(repo, num_chapters=2)
        
        # First run a batch
        class RunArgs:
            project_id = "demo"
            from_chapter = 1
            to_chapter = 2
            llm_mode = "stub"
            json = True
            config = None
            db_path = tmp_db
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_run(RunArgs())
            output = sys.stdout.getvalue()
            run_result = json.loads(output)
            run_id = run_result["data"]["run_id"]
        finally:
            sys.stdout = old_stdout
        
        # Now check status
        sys.stdout = StringIO()
        
        try:
            args = type('StatusArgs', (), {
                'run_id': run_id,
                'json': True,
                'config': None,
                'db_path': tmp_db
            })()
            
            cmd_batch_status(args)
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"] is True
            assert result["error"] is None
            assert result["data"]["run_id"] == run_id
            assert result["data"]["project_id"] == "demo"
            assert len(result["data"]["items"]) == 2
        finally:
            sys.stdout = old_stdout

    def test_batch_status_not_found_json(self, tmp_db, monkeypatch):
        """Test 'novelos batch status' with non-existent run returns JSON error."""
        import sys
        from io import StringIO
        
        class Args:
            run_id = "nonexistent_run"
            json = True
            config = None
            db_path = tmp_db
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_status(Args())
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"] is False
            assert "not found" in result["error"]
        finally:
            sys.stdout = old_stdout

    def test_batch_review_approve_json(self, tmp_db, repo, monkeypatch):
        """Test 'novelos batch review --decision approve --json'."""
        import sys
        from io import StringIO
        
        self._seed_project(repo, num_chapters=2)
        
        # First run a batch
        class RunArgs:
            project_id = "demo"
            from_chapter = 1
            to_chapter = 2
            llm_mode = "stub"
            json = True
            config = None
            db_path = tmp_db
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_run(RunArgs())
            output = sys.stdout.getvalue()
            run_result = json.loads(output)
            run_id = run_result["data"]["run_id"]
        finally:
            sys.stdout = old_stdout
        
        # Now run continuity gate (v3.3: required before approve)
        sys.stdout = StringIO()
        
        try:
            gate_args = type('GateArgs', (), {
                'run_id': run_id,
                'llm_mode': "stub",
                'json': True,
                'config': None,
                'db_path': tmp_db,
                'llm_api_key': None,
                'llm_base_url': None,
                'llm_model': None,
            })()
            
            cmd_batch_continuity(gate_args)
            output = sys.stdout.getvalue()
            gate_result = json.loads(output)
            assert gate_result["ok"]
        finally:
            sys.stdout = old_stdout
        
        # Now review
        sys.stdout = StringIO()
        
        try:
            args = type('ReviewArgs', (), {
                'run_id': run_id,
                'decision': "approve",
                'notes': None,
                'json': True,
                'config': None,
                'db_path': tmp_db
            })()
            
            cmd_batch_review(args)
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"] is True
            assert result["error"] is None
            assert result["data"]["run_id"] == run_id
            assert result["data"]["decision"] == "approve"
        finally:
            sys.stdout = old_stdout

    def test_batch_review_request_changes_with_notes_json(self, tmp_db, repo, monkeypatch):
        """Test 'novelos batch review --decision request_changes --notes ... --json'."""
        import sys
        from io import StringIO
        
        self._seed_project(repo, num_chapters=2)
        
        # First run a batch
        class RunArgs:
            project_id = "demo"
            from_chapter = 1
            to_chapter = 2
            llm_mode = "stub"
            json = True
            config = None
            db_path = tmp_db
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_run(RunArgs())
            output = sys.stdout.getvalue()
            run_result = json.loads(output)
            run_id = run_result["data"]["run_id"]
        finally:
            sys.stdout = old_stdout
        
        # Now review with notes
        sys.stdout = StringIO()
        
        try:
            args = type('ReviewArgs', (), {
                'run_id': run_id,
                'decision': "request_changes",
                'notes': "第 3 章节奏太快",
                'json': True,
                'config': None,
                'db_path': tmp_db
            })()
            
            cmd_batch_review(args)
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"] is True
            assert result["data"]["decision"] == "request_changes"
        finally:
            sys.stdout = old_stdout

    def test_batch_review_invalid_decision_json(self, tmp_db, repo, monkeypatch):
        """Test 'novelos batch review' with invalid decision returns JSON error."""
        import sys
        from io import StringIO
        
        self._seed_project(repo, num_chapters=2)
        
        # First run a batch
        class RunArgs:
            project_id = "demo"
            from_chapter = 1
            to_chapter = 2
            llm_mode = "stub"
            json = True
            config = None
            db_path = tmp_db
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_run(RunArgs())
            output = sys.stdout.getvalue()
            run_result = json.loads(output)
            run_id = run_result["data"]["run_id"]
        finally:
            sys.stdout = old_stdout
        
        # Try invalid decision
        sys.stdout = StringIO()
        
        try:
            args = type('ReviewArgs', (), {
                'run_id': run_id,
                'decision': "invalid_decision",
                'notes': None,
                'json': True,
                'config': None,
                'db_path': tmp_db
            })()
            
            cmd_batch_review(args)
            output = sys.stdout.getvalue()
            
            result = json.loads(output)
            
            assert result["ok"] is False
            assert "Invalid decision" in result["error"]
        finally:
            sys.stdout = old_stdout

    def test_batch_cli_envelope_stability(self, tmp_db, repo, monkeypatch):
        """Test that all batch CLI commands return stable {ok, error, data} envelope."""
        import sys
        from io import StringIO
        
        self._seed_project(repo, num_chapters=2)
        
        # Test batch run
        class RunArgs:
            project_id = "demo"
            from_chapter = 1
            to_chapter = 2
            llm_mode = "stub"
            json = True
            config = None
            db_path = tmp_db
            llm_api_key = None
            llm_base_url = None
            llm_model = None
        
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            cmd_batch_run(RunArgs())
            output = sys.stdout.getvalue()
            result = json.loads(output)
            
            assert "ok" in result
            assert "error" in result
            assert "data" in result
            
            run_id = result["data"]["run_id"]
        finally:
            sys.stdout = old_stdout
        
        # Test batch status
        sys.stdout = StringIO()
        
        try:
            args = type('StatusArgs', (), {
                'run_id': run_id,
                'json': True,
                'config': None,
                'db_path': tmp_db
            })()
            
            cmd_batch_status(args)
            output = sys.stdout.getvalue()
            result = json.loads(output)
            
            assert "ok" in result
            assert "error" in result
            assert "data" in result
        finally:
            sys.stdout = old_stdout
        
        # Test batch review
        sys.stdout = StringIO()
        
        try:
            args = type('ReviewArgs', (), {
                'run_id': run_id,
                'decision': "approve",
                'notes': None,
                'json': True,
                'config': None,
                'db_path': tmp_db
            })()
            
            cmd_batch_review(args)
            output = sys.stdout.getvalue()
            result = json.loads(output)
            
            assert "ok" in result
            assert "error" in result
            assert "data" in result
        finally:
            sys.stdout = old_stdout
