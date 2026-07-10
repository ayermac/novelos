"""v6.10.19: Store aggregation layer unit tests."""
from __future__ import annotations
import pytest
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.stores import (ProgressStore, DraftStore, WorldStore, SummaryStore, CharacterStore, OutlineStore, SignalStore, CheckpointStore)

@pytest.fixture()
def repo(tmp_path):
    db_path = tmp_path / "v61019_stores.db"
    init_db(db_path)
    r = Repository(str(db_path))
    r.create_project(project_id="proj1", name="Test", genre="urban", description="x")
    return r

class TestProgressStore:
    def test_get_project_progress(self, repo):
        r = ProgressStore(repo).get_project_progress("proj1")
        assert isinstance(r, dict) and "total_token_usage" in r
    def test_get_chapter_workflow_status(self, repo):
        r = ProgressStore(repo).get_chapter_workflow_status("proj1", 1)
        assert isinstance(r, dict) and "retry_count" in r
    def test_get_recent_events(self, repo):
        assert isinstance(ProgressStore(repo).get_recent_events("proj1", 5), list)
    def test_get_active_runs(self, repo):
        assert isinstance(ProgressStore(repo).get_active_runs("proj1"), list)

class TestDraftStore:
    def test_missing_chapter(self, repo):
        assert DraftStore(repo).get_chapter_with_drafts("proj1", 999) is None
    def test_get_latest_draft_none(self, repo):
        assert DraftStore(repo).get_latest_draft("proj1", 999) is None
    def test_get_full_context_none(self, repo):
        assert DraftStore(repo).get_chapter_full_context("proj1", 999) is None

class TestWorldStore:
    def test_get_world_state(self, repo):
        r = WorldStore(repo).get_world_state("proj1")
        assert isinstance(r, dict) and "active_plot_holes" in r
    def test_empty_plot_holes(self, repo):
        assert WorldStore(repo).get_active_plot_holes("proj1") == []
    def test_seeded_plot_hole(self, repo):
        repo.create_plot_hole(project_id="proj1", code="PH001", title="t", description="d", planted_chapter=1, status="planted")
        holes = WorldStore(repo).get_active_plot_holes("proj1")
        assert len(holes) == 1 and holes[0]["code"] == "PH001"
    def test_recent_memories(self, repo):
        assert isinstance(WorldStore(repo).get_recent_memories("proj1"), list)
    def test_get_facts_by_type(self, repo):
        assert isinstance(WorldStore(repo).get_facts_by_type("proj1", "character"), list)

class TestRemainingSmoke:
    def test_summary(self, repo): assert isinstance(SummaryStore(repo).get_project_quality_trend("proj1"), list)
    def test_character(self, repo): assert isinstance(CharacterStore(repo).get_characters_with_samples("proj1"), list)
    def test_outline(self, repo): assert isinstance(OutlineStore(repo).get_outline_progress("proj1"), dict)
    def test_signal(self, repo): assert isinstance(SignalStore(repo).get_project_signal("proj1"), dict)
    def test_checkpoint(self, repo): assert CheckpointStore(repo).get_chapter_checkpoint("proj1", 999) is None
