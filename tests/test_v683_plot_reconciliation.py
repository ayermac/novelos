"""v6.8.3 Phase 2: Deterministic plot reconciliation tests.

Covers reconcile_plot_resolution: a planned-and-paid-off plot (code in
plots_to_resolve AND code present in chapter prose) is auto-resolved
independent of the LLM MemoryCurator.
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.workflow.reconciliation import (
    reconcile_plot_resolution,
    _parse_plot_codes,
)


@pytest.fixture()
def repo(tmp_path):
    db_path = tmp_path / "v683_recon.db"
    init_db(db_path)
    r = Repository(str(db_path))
    r.create_project(project_id="p", name="P", genre="fantasy")
    return r


def _setup(repo, *, resolve_codes, content, plot_codes, statuses=None):
    """Create instruction (with plots_to_resolve), chapter content, and plots."""
    statuses = statuses or {}
    repo.create_instruction(
        "p", 3,
        objective="兑现伏笔",
        plots_to_resolve=json.dumps(resolve_codes, ensure_ascii=False),
    )
    repo.save_chapter("p", 3, title="第3章", content=content, word_count=len(content), status="published")
    for code in plot_codes:
        repo.create_plot_hole(
            "p", code=code, title=f"伏笔{code}",
            planted_chapter=1, planned_resolve_chapter=3,
            status=statuses.get(code, "planted"),
        )


class TestParsePlotCodes:
    def test_json_list(self):
        assert _parse_plot_codes('["PH-002", "PH-003"]') == ["PH-002", "PH-003"]

    def test_python_list(self):
        assert _parse_plot_codes(["PH-002"]) == ["PH-002"]

    def test_comma_text(self):
        assert _parse_plot_codes("PH-002, PH-003") == ["PH-002", "PH-003"]

    def test_empty(self):
        assert _parse_plot_codes("") == []
        assert _parse_plot_codes(None) == []


class TestReconcilePlotResolution:
    def test_resolves_planned_and_present_in_prose(self, repo):
        _setup(
            repo,
            resolve_codes=["PH-002"],
            content="林辰在信号塔发现了 PH-002 的线索，监控身影得到解释。",
            plot_codes=["PH-002"],
        )
        result = reconcile_plot_resolution(repo, "p", 3)
        assert result["resolved"] == ["PH-002"]
        plot = next(p for p in repo.list_plot_holes("p") if p["code"] == "PH-002")
        assert plot["status"] == "resolved"
        assert plot["resolved_chapter"] == 3

    def test_no_resolution_when_planned_but_absent_from_prose(self, repo):
        _setup(
            repo,
            resolve_codes=["PH-002"],
            content="本章完全没有提到那个伏笔代码。",
            plot_codes=["PH-002"],
        )
        result = reconcile_plot_resolution(repo, "p", 3)
        assert result["resolved"] == []
        plot = next(p for p in repo.list_plot_holes("p") if p["code"] == "PH-002")
        assert plot["status"] == "planted"

    def test_no_resolution_when_not_planned(self, repo):
        _setup(
            repo,
            resolve_codes=[],  # not planned
            content="PH-002 出现在正文里但本章没计划兑现。",
            plot_codes=["PH-002"],
        )
        result = reconcile_plot_resolution(repo, "p", 3)
        assert result["resolved"] == []

    def test_already_resolved_is_noop(self, repo):
        _setup(
            repo,
            resolve_codes=["PH-002"],
            content="PH-002 再次出现。",
            plot_codes=["PH-002"],
            statuses={"PH-002": "resolved"},
        )
        result = reconcile_plot_resolution(repo, "p", 3)
        assert result["resolved"] == []  # already terminal, skipped

    def test_multiple_codes_partial(self, repo):
        _setup(
            repo,
            resolve_codes=["PH-002", "PH-003"],
            content="只有 PH-002 在正文里出现并得到兑现，另一条线索仍未触及。",
            plot_codes=["PH-002", "PH-003"],
        )
        result = reconcile_plot_resolution(repo, "p", 3)
        assert result["resolved"] == ["PH-002"]
        by_code = {p["code"]: p for p in repo.list_plot_holes("p")}
        assert by_code["PH-002"]["status"] == "resolved"
        assert by_code["PH-003"]["status"] == "planted"

    def test_no_instruction_is_safe(self, repo):
        # No instruction for chapter 9
        result = reconcile_plot_resolution(repo, "p", 9)
        assert result["resolved"] == []
