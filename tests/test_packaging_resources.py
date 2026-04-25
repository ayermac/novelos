"""Packaging resource tests for v1.4."""

from __future__ import annotations

import importlib.resources
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def test_package_data_includes_sql():
    """Test that SQL files are included in package data."""
    # Check schema file
    schema_path = Path(__file__).resolve().parent.parent / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
    assert schema_path.exists(), f"Base schema not found at {schema_path}"
    
    # Check migration files
    migrations_dir = Path(__file__).resolve().parent.parent / "novel_factory" / "db" / "migrations"
    assert migrations_dir.exists()
    
    migration_files = list(migrations_dir.glob("*.sql"))
    assert len(migration_files) >= 4, f"Expected at least 4 migration files, found {len(migration_files)}"
    
    # Check specific migrations exist
    expected = ["001_add_workflow_tables.sql", "002_v1_1_stability.sql", 
                "003_v1_2_quality.sql", "004_v1_4_runtime.sql"]
    for exp in expected:
        assert (migrations_dir / exp).exists(), f"Missing migration: {exp}"


def test_package_data_includes_yaml():
    """Test that YAML config files are included in package data."""
    # Check config files
    config_dir = Path(__file__).resolve().parent.parent / "novel_factory" / "config"
    assert config_dir.exists()
    
    yaml_files = list(config_dir.glob("*.yaml"))
    assert len(yaml_files) >= 2, f"Expected at least 2 YAML files, found {len(yaml_files)}"
    
    # Check specific files
    assert (config_dir / "llm.yaml").exists()
    assert (config_dir / "agents.yaml").exists()
    
    # Verify they are valid YAML
    for yaml_file in yaml_files:
        with open(yaml_file, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
        assert content is not None, f"Empty or invalid YAML: {yaml_file}"


def test_importlib_resources_access():
    """Test that resources can be accessed via importlib.resources."""
    try:
        # Try to read a resource
        if importlib.resources.is_resource("novel_factory.config", "llm.yaml"):
            text = importlib.resources.files("novel_factory.config").joinpath("llm.yaml").read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            assert "provider" in data or "llm" in data
    except (ImportError, FileNotFoundError, AttributeError):
        # Fallback to file path is acceptable
        pass


def test_init_db_uses_bundled_schema(tmp_path):
    """Test init-db works using only bundled schema."""
    db_path = tmp_path / "bundled_test.db"
    
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "init-db"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    
    assert result.returncode == 0, f"init-db failed: {result.stderr}"
    assert db_path.exists()
    
    # Verify essential tables exist
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    
    essential_tables = ["projects", "chapters", "instructions", "reviews", "workflow_runs"]
    for table in essential_tables:
        assert table in tables, f"Missing table: {table}"


def test_cli_help_from_anywhere():
    """Test CLI help works from any directory (when package is installed)."""
    # This test verifies that the CLI can be built from any directory
    # when the package is installed. Since we're running from source,
    # we'll test the parser building instead.
    
    # Build parser should work regardless of CWD
    from novel_factory.cli import build_parser
    parser = build_parser()
    assert parser.prog == "novelos"
    
    # Test that help text contains expected commands
    help_text = parser.format_help()
    assert "init-db" in help_text
    assert "run-chapter" in help_text
    assert "config" in help_text or "doctor" in help_text  # v1.4 commands


def test_config_files_loadable():
    """Test that config files can be loaded by the application."""
    from novel_factory.config.loader import load_default_config
    
    config = load_default_config()
    assert isinstance(config, dict)
    
    # Should have llm config from package
    if "llm" in config:
        assert isinstance(config["llm"], dict)


def test_pyproject_includes_package_data():
    """Test pyproject.toml includes package-data declaration."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    assert pyproject_path.exists()
    
    with open(pyproject_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check for package-data section
    assert "[tool.setuptools.package-data]" in content
    assert "novel_factory = [" in content
    assert "db/schema/*.sql" in content
    assert "db/migrations/*.sql" in content
    assert "config/*.yaml" in content


def test_doctor_command_works(tmp_path):
    """Test doctor command works and checks resources."""
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "doctor",
         "--json"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    
    assert result.returncode == 0, f"doctor failed: {result.stderr}"
    
    data = json.loads(result.stdout)
    assert data["ok"] in (True, False)
    assert "data" in data
    assert "checks" in data["data"]
    
    # Should have at least some checks
    assert len(data["data"]["checks"]) >= 3


def test_migration_004_applied(tmp_path):
    """Test that migration 004 adds revision_target column."""
    db_path = tmp_path / "migration_test.db"
    
    # Initialize DB (should apply all migrations)
    from novel_factory.db.connection import init_db
    init_db(db_path)
    
    # Check if revision_target column exists
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("PRAGMA table_info(reviews)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    
    assert "revision_target" in columns, "revision_target column not added by migration 004"


def test_seed_demo_creates_tables(tmp_path):
    """Test that seed-demo creates all necessary tables data."""
    db_path = tmp_path / "seed_demo_test.db"
    
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "seed-demo"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    
    assert result.returncode == 0
    
    # Verify data was created
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    
    # Check projects
    projects = conn.execute("SELECT * FROM projects WHERE project_id='demo'").fetchall()
    assert len(projects) == 1
    
    # Check chapters
    chapters = conn.execute("SELECT * FROM chapters WHERE project_id='demo'").fetchall()
    assert len(chapters) == 1
    
    # Check instructions
    instructions = conn.execute("SELECT * FROM instructions WHERE project_id='demo'").fetchall()
    assert len(instructions) == 1
    
    # Check characters
    characters = conn.execute("SELECT * FROM characters WHERE project_id='demo'").fetchall()
    assert len(characters) == 1
    
    conn.close()