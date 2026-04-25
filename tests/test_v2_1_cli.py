"""Tests for v2.1 CLI commands."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import os

import pytest


class TestSkillsCLI:
    """Test v2.1 skills CLI commands."""
    
    def test_skills_list_json(self):
        """Test 'novelos skills list --json' command."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "list", "--json"],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "data" in output
        assert "skills" in output["data"]
        
        # Should have at least 3 skills
        skills = output["data"]["skills"]
        assert len(skills) >= 3
        
        # Check skill structure
        for skill in skills:
            assert "id" in skill
            assert "type" in skill
            assert "enabled" in skill
    
    def test_skills_list_human_readable(self):
        """Test 'novelos skills list' human-readable output."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "skills", "list"],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "Available Skills:" in result.stdout
        assert "humanizer-zh" in result.stdout
        assert "ai-style-detector" in result.stdout
    
    def test_skills_run_humanizer_zh_json(self):
        """Test 'novelos skills run humanizer-zh --text ... --json' command."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "humanizer-zh",
                "--text", "这是一个测试文本。",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "data" in output
        assert "humanized_text" in output["data"]
    
    def test_skills_run_ai_style_detector_json(self):
        """Test 'novelos skills run ai-style-detector --text ... --json' command."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "ai-style-detector",
                "--text", "这是一个测试文本。",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "data" in output
        assert "ai_trace_score" in output["data"]
    
    def test_skills_run_narrative_quality_json(self):
        """Test 'novelos skills run narrative-quality --text ... --json' command."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "narrative-quality",
                "--text", "这是一个测试文本。" * 50,
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert "data" in output
        assert "scores" in output["data"]
    
    def test_skills_run_unknown_skill_fails(self):
        """Test 'novelos skills run unknown-skill' fails clearly."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "unknown-skill",
                "--text", "test",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Parse JSON output
        output = json.loads(result.stdout)
        
        # Should fail with ok=false
        assert output["ok"] is False
        assert "error" in output
        assert "not found" in output["error"].lower() or "disabled" in output["error"].lower()
    
    def test_skills_run_with_input_json(self):
        """Test 'novelos skills run' with --input-json parameter."""
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "skills", "run", "ai-style-detector",
                "--input-json", '{"text": "测试文本"}',
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True


class TestQualityCLI:
    """Test v2.1 quality CLI commands."""
    
    def test_quality_check_draft(self, tmp_db):
        """Test 'novelos quality check --stage draft' command."""
        # Seed test data first
        _seed_test_project(tmp_db)
        
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", tmp_db,
                "quality", "check",
                "--project-id", "test_proj",
                "--chapter", "1",
                "--stage", "draft",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should succeed
        assert result.returncode == 0
    
    def test_quality_report(self, tmp_db):
        """Test 'novelos quality report' command."""
        # Seed test data first
        _seed_test_project(tmp_db)
        
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", tmp_db,
                "quality", "report",
                "--project-id", "test_proj",
                "--chapter", "1",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should succeed
        assert result.returncode == 0
        
        # Parse JSON output
        output = json.loads(result.stdout)
        assert output["ok"] is True
    
    # R3: Regression tests for None handling
    def test_quality_check_empty_content(self, tmp_db):
        """Test quality check on chapter with empty content."""
        # Seed test project with empty content
        _seed_test_project_empty(tmp_db)
        
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", tmp_db,
                "quality", "check",
                "--project-id", "test_proj",
                "--chapter", "2",
                "--stage", "draft",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should succeed (not crash)
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["ok"] is True
    
    def test_quality_check_planned_chapter(self, tmp_db):
        """Test quality check on planned chapter (no content yet)."""
        # Seed test project with planned chapter
        _seed_test_project_planned(tmp_db)
        
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", tmp_db,
                "quality", "check",
                "--project-id", "test_proj",
                "--chapter", "3",
                "--stage", "draft",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        
        # Should succeed (not crash)
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["ok"] is True


def _seed_test_project(db_path: str):
    """Seed test project for CLI tests."""
    import sqlite3
    
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_id, name, genre) VALUES (?, ?, ?)",
        ("test_proj", "Test Project", "fantasy"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO chapters (project_id, chapter_number, title, status, content) VALUES (?, ?, ?, ?, ?)",
        ("test_proj", 1, "Chapter 1", "drafted", "测试内容" * 50),
    )
    conn.commit()
    conn.close()


def _seed_test_project_empty(db_path: str):
    """Seed test project with empty content chapter."""
    import sqlite3
    
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_id, name, genre) VALUES (?, ?, ?)",
        ("test_proj", "Test Project", "fantasy"),
    )
    # R3: Chapter with NULL content
    conn.execute(
        "INSERT OR IGNORE INTO chapters (project_id, chapter_number, title, status, content) VALUES (?, ?, ?, ?, ?)",
        ("test_proj", 2, "Chapter 2", "drafted", None),
    )
    conn.commit()
    conn.close()


def _seed_test_project_planned(db_path: str):
    """Seed test project with planned chapter (no content)."""
    import sqlite3
    
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_id, name, genre) VALUES (?, ?, ?)",
        ("test_proj", "Test Project", "fantasy"),
    )
    # R3: Planned chapter with no content and no instruction
    conn.execute(
        "INSERT OR IGNORE INTO chapters (project_id, chapter_number, title, status, content) VALUES (?, ?, ?, ?, ?)",
        ("test_proj", 3, "Chapter 3", "planned", None),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def tmp_db():
    """Create temporary database for testing."""
    from novel_factory.db.connection import init_db
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_db(db_path)
        yield db_path
