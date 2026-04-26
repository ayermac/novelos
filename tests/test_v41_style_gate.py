"""v4.1 Style Gate tests.

Covers:
- StyleGateConfig serialization/deserialization
- Style Gate default (warn) does not block
- Style Gate mode=block blocks on threshold breach
- Style Gate mode=off does not add warnings
- QualityHub integration with Style Gate
- Migration 013 idempotent
"""

from __future__ import annotations

import json
import tempfile
from unittest.mock import MagicMock

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import StyleBible, ForbiddenExpression
from novel_factory.models.style_gate import StyleGateConfig, StyleGateMode, StyleGateStage


def _ensure_project(db_path: str, project_id: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name) VALUES (?, ?)",
            (project_id, "Test Project"),
        )
        conn.commit()
    finally:
        conn.close()


def _make_bible_with_gate(
    project_id: str = "gate_test",
    gate_config: dict | None = None,
) -> dict:
    """Create a Style Bible dict with optional gate config."""
    bible = StyleBible(
        project_id=project_id,
        name="Gate Test Bible",
        genre="玄幻",
        forbidden_expressions=[
            ForbiddenExpression(pattern="冷笑", reason="AI味", severity="blocking"),
            ForbiddenExpression(pattern="不禁", reason="AI味", severity="warning"),
        ],
    )
    data = bible.to_storage_dict()
    if gate_config:
        data["gate_config"] = gate_config
    return data


@pytest.fixture
def db_path(tmp_path):
    db = str(tmp_path / "test_v41_gate.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


# ── StyleGateConfig Model ─────────────────────────────────────


class TestStyleGateConfig:
    """Test StyleGateConfig model."""

    def test_defaults(self):
        config = StyleGateConfig()
        assert config.enabled is False
        assert config.mode == StyleGateMode.WARN
        assert config.blocking_threshold == 70
        assert config.max_blocking_issues == 0
        assert config.revision_target == "polisher"

    def test_serialization_roundtrip(self):
        config = StyleGateConfig(
            enabled=True,
            mode=StyleGateMode.BLOCK,
            blocking_threshold=75,
            max_blocking_issues=3,
            revision_target="author",
            apply_stages=[StyleGateStage.DRAFT, StyleGateStage.POLISHED],
        )
        data = config.to_storage_dict()
        restored = StyleGateConfig.from_storage_dict(data)
        assert restored.enabled is True
        assert restored.mode == StyleGateMode.BLOCK
        assert restored.blocking_threshold == 75
        assert restored.max_blocking_issues == 3
        assert restored.revision_target == "author"
        assert StyleGateStage.DRAFT in restored.apply_stages

    def test_from_storage_dict_string_mode(self):
        data = {"enabled": True, "mode": "block", "blocking_threshold": 80}
        config = StyleGateConfig.from_storage_dict(data)
        assert config.mode == StyleGateMode.BLOCK


# ── Style Gate Repository ─────────────────────────────────────


class TestStyleGateRepo:
    """Test Style Gate config repository methods."""

    def test_get_gate_config_no_bible(self, repo):
        result = repo.get_style_gate_config("nonexistent")
        assert result is None

    def test_get_gate_config_no_gate_set(self, db_path, repo):
        _ensure_project(db_path, "gate_test")
        bible_dict = _make_bible_with_gate()
        repo.save_style_bible("gate_test", bible_dict)
        result = repo.get_style_gate_config("gate_test")
        assert result is None  # No gate_config in bible

    def test_set_and_get_gate_config(self, db_path, repo):
        _ensure_project(db_path, "gate_test")
        bible_dict = _make_bible_with_gate()
        repo.save_style_bible("gate_test", bible_dict)

        gate_config = StyleGateConfig(
            enabled=True, mode=StyleGateMode.BLOCK, blocking_threshold=75
        ).to_storage_dict()

        ok = repo.set_style_gate_config("gate_test", gate_config)
        assert ok is True

        result = repo.get_style_gate_config("gate_test")
        assert result is not None
        assert result["mode"] == "block"
        assert result["blocking_threshold"] == 75

    def test_set_gate_config_no_bible(self, repo):
        gate_config = StyleGateConfig().to_storage_dict()
        ok = repo.set_style_gate_config("nonexistent", gate_config)
        assert ok is False


# ── QualityHub Style Gate Integration ─────────────────────────


class TestQualityHubStyleGate:
    """Test QualityHub with Style Gate integration."""

    def _setup_bible_with_gate(
        self, db_path, repo, mode="warn", threshold=70, enabled=True,
        stages="draft,polished,final_gate",
    ):
        """Setup a Style Bible with gate config."""
        _ensure_project(db_path, "gate_test")
        bible_dict = _make_bible_with_gate()
        repo.save_style_bible("gate_test", bible_dict)

        gate_config = StyleGateConfig(
            enabled=enabled,
            mode=StyleGateMode(mode),
            blocking_threshold=threshold,
            apply_stages=[StyleGateStage(s) for s in stages.split(",")],
        ).to_storage_dict()
        repo.set_style_gate_config("gate_test", gate_config)

    def test_gate_off_no_warnings(self, db_path, repo):
        """mode=off: no warnings added."""
        from novel_factory.quality.hub import QualityHub

        self._setup_bible_with_gate(db_path, repo, mode="off", enabled=True)

        hub = QualityHub(repo, MagicMock())
        # Use check_draft directly with content (no need for chapter in DB)
        result = hub.check_draft("gate_test", 1, "他冷笑了一声，不禁感叹。")
        assert result["ok"] is True
        # No style_gate warnings or blocking from the gate (off mode)
        gate_issues = [i for i in result["data"]["blocking_issues"]
                       if i.get("type") == "style_gate_blocked"]
        assert len(gate_issues) == 0

    def test_gate_warn_adds_warnings(self, db_path, repo):
        """mode=warn: adds warnings but doesn't block."""
        from novel_factory.quality.hub import QualityHub

        self._setup_bible_with_gate(db_path, repo, mode="warn", threshold=95, enabled=True)

        hub = QualityHub(repo, MagicMock())
        # Content with forbidden expression → score ~90 < 95 threshold
        result = hub.check_draft("gate_test", 1, "他冷笑了一声，不禁感叹。")
        assert result["ok"] is True  # warn mode doesn't block
        # Should have style gate warnings in quality_dimensions
        assert "style_bible_gate" in result["data"].get("quality_dimensions", {})

    def test_gate_block_can_block(self, db_path, repo):
        """mode=block: can block when score < threshold."""
        from novel_factory.quality.hub import QualityHub

        self._setup_bible_with_gate(db_path, repo, mode="block", threshold=95, enabled=True)

        hub = QualityHub(repo, MagicMock())
        result = hub.check_draft("gate_test", 1, "他冷笑了一声，不禁感叹。")
        # Should have a blocking issue from style gate
        gate_issues = [i for i in result["data"]["blocking_issues"]
                       if i.get("type") == "style_gate_blocked"]
        assert len(gate_issues) > 0
        assert gate_issues[0]["revision_target"] == "polisher"

    def test_gate_block_with_author_target(self, db_path, repo):
        """mode=block with revision_target=author."""
        from novel_factory.quality.hub import QualityHub

        self._setup_bible_with_gate(db_path, repo, mode="block", threshold=95, enabled=True)

        # Change revision_target
        gate_config = repo.get_style_gate_config("gate_test")
        gate_config["revision_target"] = "author"
        repo.set_style_gate_config("gate_test", gate_config)

        hub = QualityHub(repo, MagicMock())
        result = hub.check_draft("gate_test", 1, "他冷笑了一声，不禁感叹。")
        gate_issues = [i for i in result["data"]["blocking_issues"]
                       if i.get("type") == "style_gate_blocked"]
        assert len(gate_issues) > 0
        assert gate_issues[0]["revision_target"] == "author"

    def test_gate_not_enabled_by_default(self, db_path, repo):
        """Gate disabled by default doesn't add anything."""
        from novel_factory.quality.hub import QualityHub

        _ensure_project(db_path, "gate_test")
        bible_dict = _make_bible_with_gate()
        repo.save_style_bible("gate_test", bible_dict)
        # No gate config set — defaults to disabled

        hub = QualityHub(repo, MagicMock())
        result = hub.check_draft("gate_test", 1, "他冷笑了一声，不禁感叹。")
        # No style_gate issues
        gate_issues = [i for i in result["data"]["blocking_issues"]
                       if i.get("type") == "style_gate_blocked"]
        assert len(gate_issues) == 0


# ── Migration Idempotent ──────────────────────────────────────


class TestMigration013Idempotent:
    def test_init_db_twice(self, db_path):
        init_db(db_path)
        init_db(db_path)
        conn = get_connection(db_path)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "style_bible_versions" in tables
        assert "style_evolution_proposals" in tables
