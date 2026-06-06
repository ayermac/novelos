"""v6.9.0: Real Repository integration tests.

These tests exercise the actual Repository class (not mocks) to catch
interface drift between callers and repository methods. They are the
regression tests that would have caught H1 (``data=`` kwarg name),
H2/H3 (missing ledger methods), and similar issues before merge.
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.models.creative_contracts import (
    GenreProfile,
)
from novel_factory.quality.genesis_quality_gate import (
    generate_launch_profile,
    generate_genre_contract,
    check_project_ready_for_production,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def repo(tmp_path):
    """Real SQLite Repository pointing to a tmp file."""
    db_path = tmp_path / "v690_integration.db"
    init_db(db_path)
    r = Repository(str(db_path))
    # Seed a project to satisfy FK constraints (if any) on contracts table
    r.create_project(project_id="proj1", name="Test", genre="urban", description="x")
    return r


@pytest.fixture()
def genre_profile() -> GenreProfile:
    return GenreProfile(
        profile_id="urban_sign_in_power_fantasy",
        default_payoff_loop="升级",
        chapter_rhythm_defaults={"minor_payoff_frequency": 1},
        profile_specific_rules={"avoid_patterns": ["系统流"]},
        editor_weight_profile={"logic": 25},
    )


# ── Contract CRUD round-trips (would have caught H1) ─────────────────────


class TestContractCRUDRoundTrip:
    def test_upsert_and_get_launch_profile(self, repo, genre_profile):
        """upsert_creative_contract uses ``contract_data`` keyword, not ``data``."""
        launch = generate_launch_profile("林潮觉醒灵力", genre_profile)
        # The keyword arg name must match the method signature exactly.
        repo.upsert_creative_contract(
            project_id="proj1",
            contract_type="launch_profile",
            contract_data=launch.model_dump(),
        )
        row = repo.get_creative_contract("proj1", "launch_profile")
        assert row is not None
        parsed = json.loads(row["contract_data"])
        assert parsed["market_lane"] == "urban_sign_in_power_fantasy"

    def test_upsert_with_wrong_kwarg_raises(self, repo):
        """Passing ``data=`` (the old buggy form) must raise TypeError."""
        with pytest.raises(TypeError):
            repo.upsert_creative_contract(
                project_id="proj1",
                contract_type="launch_profile",
                data={"foo": "bar"},  # wrong kwarg name
            )

    def test_full_contract_approval_flow(self, repo, genre_profile):
        """End-to-end: generate → save → check unapproved → approve → check ready."""
        launch = generate_launch_profile("idea", genre_profile)
        contract = generate_genre_contract(launch, genre_profile)

        repo.upsert_creative_contract("proj1", "launch_profile", contract_data=launch.model_dump())
        contract_dict = contract.model_dump()
        contract_dict["approved"] = False
        repo.upsert_creative_contract("proj1", "genre_contract", contract_data=contract_dict)

        assert check_project_ready_for_production("proj1", repo) is False

        # Approve
        contract_dict["approved"] = True
        repo.upsert_creative_contract("proj1", "genre_contract", contract_data=contract_dict)

        assert check_project_ready_for_production("proj1", repo) is True


# ── Creative ledger queries (would have caught H2/H3) ─────────────────────


class TestCreativeLedgerRealQueries:
    def test_get_latest_creative_ledger_exists(self, repo):
        """get_latest_creative_ledger is callable on Repository."""
        assert hasattr(repo, "get_latest_creative_ledger")

    def test_get_creative_ledger_history_exists(self, repo):
        """get_creative_ledger_history is callable on Repository."""
        assert hasattr(repo, "get_creative_ledger_history")

    def test_latest_returns_highest_chapter(self, repo):
        repo.upsert_creative_ledger(
            project_id="proj1",
            chapter_number=1,
            ledger_type="reader_promise",
            ledger_data={"entries": [], "summary": "ch1"},
        )
        repo.upsert_creative_ledger(
            project_id="proj1",
            chapter_number=3,
            ledger_type="reader_promise",
            ledger_data={"entries": [], "summary": "ch3"},
        )
        repo.upsert_creative_ledger(
            project_id="proj1",
            chapter_number=2,
            ledger_type="reader_promise",
            ledger_data={"entries": [], "summary": "ch2"},
        )

        latest = repo.get_latest_creative_ledger("proj1", "reader_promise")
        assert latest is not None
        assert latest["chapter_number"] == 3
        assert json.loads(latest["ledger_data"])["summary"] == "ch3"

    def test_latest_returns_none_when_no_data(self, repo):
        assert repo.get_latest_creative_ledger("proj1", "reader_promise") is None

    def test_history_returns_all_chapters_ascending(self, repo):
        for ch in [3, 1, 2]:
            repo.upsert_creative_ledger(
                project_id="proj1",
                chapter_number=ch,
                ledger_type="reader_promise",
                ledger_data={"entries": [], "summary": f"ch{ch}"},
            )
        history = repo.get_creative_ledger_history("proj1", "reader_promise")
        assert len(history) == 3
        chapters = [h["chapter_number"] for h in history]
        assert chapters == [1, 2, 3]

    def test_history_filters_by_ledger_type(self, repo):
        repo.upsert_creative_ledger(
            project_id="proj1",
            chapter_number=1,
            ledger_type="reader_promise",
            ledger_data={"entries": [], "summary": "rp"},
        )
        repo.upsert_creative_ledger(
            project_id="proj1",
            chapter_number=1,
            ledger_type="power_growth",
            ledger_data={"entries": [], "summary": "pg"},
        )
        rp_history = repo.get_creative_ledger_history("proj1", "reader_promise")
        assert len(rp_history) == 1
        assert json.loads(rp_history[0]["ledger_data"])["summary"] == "rp"


# ── Editor lens repository queries (would have caught M6) ────────────────


class TestEditorLensReportRealQueries:
    def test_list_recent_lens_reports_exists(self, repo):
        assert hasattr(repo, "list_recent_lens_reports")

    def test_list_recent_excludes_current_chapter(self, repo):
        for ch in [1, 2, 3, 4]:
            repo.upsert_editor_lens_report(
                project_id="proj1",
                chapter_number=ch,
                lens_type="type",
                report_data={"passed": True, "score": 100, "findings": []},
            )

        # Looking before chapter 4, expect chapters [1,2,3] (DESC: 3,2,1)
        rows = repo.list_recent_lens_reports(
            project_id="proj1",
            lens_type="type",
            before_chapter=4,
            limit=3,
        )
        chapters = [r["chapter_number"] for r in rows]
        assert chapters == [3, 2, 1]
        # Current chapter 4 must not appear
        assert 4 not in chapters


# ── Brief validator round-trip with real ChapterBrief model ──────────────


class TestBriefValidationWithRealModel:
    """Would have caught H4: nested vs flat structure mismatch."""

    def test_nested_chapter_brief_from_model_validates(self):
        from novel_factory.models.chapter_contracts import ChapterBrief, ChapterBriefTier1
        from novel_factory.quality.chapter_brief_validator import validate_chapter_brief

        brief = ChapterBrief(
            tier1=ChapterBriefTier1(
                chapter_goal="g",
                reader_payoff="p",
                protagonist_agency="a",
                forbidden_moves=["x"],
            ),
        )
        is_valid, missing = validate_chapter_brief(brief.model_dump())
        assert is_valid is True
        assert missing == []

    def test_flat_brief_also_works(self):
        from novel_factory.quality.chapter_brief_validator import validate_chapter_brief

        is_valid, missing = validate_chapter_brief({
            "chapter_goal": "g",
            "reader_payoff": "p",
            "protagonist_agency": "a",
            "forbidden_moves": ["x"],
        })
        assert is_valid is True
        assert missing == []


# ── Ledger context fallback (would have caught H2 via context path) ──────


class TestLedgerContextFallback:
    def test_load_ledgers_falls_back_to_latest(self, repo):
        """When current chapter has no snapshot, should fall back to most recent prior."""
        from novel_factory.context.ledger_context import load_ledgers_for_planner

        # Seed snapshot at chapter 2 only
        repo.upsert_creative_ledger(
            project_id="proj1",
            chapter_number=2,
            ledger_type="reader_promise",
            ledger_data={
                "entries": [{"promise": "p1", "status": "active", "chapter_introduced": 2}],
                "summary": "ch2",
            },
        )
        # Ask for context at chapter 5 (no direct ch4 snapshot)
        ctx = load_ledgers_for_planner(repo, "proj1", 5)
        rp = ctx["reader_promise"]
        # Should fall back to the chapter 2 snapshot
        assert rp["summary"] == "ch2"
        assert rp["entries_count"] == 1
