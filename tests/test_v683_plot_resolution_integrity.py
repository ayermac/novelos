"""v6.8.3 Phase 1: Plot hole resolution integrity tests.

Covers the three P0 defects that left plot holes stuck in `planted`:
- 1.1 Terminal status protection in update_plot_hole
- 1.2 Plain update patches stripped of status/resolved_chapter
- 1.3 Operation-priority ordering so resolve applies after update

Includes a regression reproduction of the exact PH-002 scenario
(resolve then update in the same batch -> must stay resolved).
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


@pytest.fixture()
def repo(tmp_path):
    db_path = tmp_path / "v683_plot.db"
    init_db(db_path)
    r = Repository(str(db_path))
    r.create_project(project_id="p", name="P", genre="fantasy")
    return r


# ── Phase 1.1: Terminal status protection ────────────────────────────


class TestTerminalStatusProtection:
    def test_plain_update_cannot_revert_resolved_to_planted(self, repo):
        ph = repo.create_plot_hole("p", code="PH-002", title="模糊身影", status="resolved")
        repo.update_plot_hole("p", ph["id"], {"resolved_chapter": 4})

        # A description-only update that carries a stale status="planted"
        updated = repo.update_plot_hole(
            "p", ph["id"],
            {"description": "深化描述", "status": "planted"},
        )

        assert updated["status"] == "resolved"
        assert updated["description"] == "深化描述"
        assert updated["resolved_chapter"] == 4

    def test_update_without_status_keeps_resolved(self, repo):
        ph = repo.create_plot_hole("p", code="PH-001", title="t", status="resolved")
        updated = repo.update_plot_hole("p", ph["id"], {"description": "new"})
        assert updated["status"] == "resolved"

    def test_explicit_terminal_status_still_passes(self, repo):
        ph = repo.create_plot_hole("p", code="PH-003", title="t", status="resolved")
        # Explicitly moving resolved -> abandoned is a legitimate terminal change.
        updated = repo.update_plot_hole("p", ph["id"], {"status": "abandoned"})
        assert updated["status"] == "abandoned"

    def test_planted_update_to_resolved_works(self, repo):
        ph = repo.create_plot_hole("p", code="PH-004", title="t", status="planted")
        updated = repo.update_plot_hole(
            "p", ph["id"], {"status": "resolved", "resolved_chapter": 5}
        )
        assert updated["status"] == "resolved"
        assert updated["resolved_chapter"] == 5

    def test_protect_terminal_false_allows_override(self, repo):
        ph = repo.create_plot_hole("p", code="PH-005", title="t", status="resolved")
        updated = repo.update_plot_hole(
            "p", ph["id"], {"status": "planted"}, protect_terminal=False
        )
        assert updated["status"] == "planted"


# ── Phase 1.3: Operation-priority ordering ───────────────────────────


class TestOperationOrdering:
    def test_resolve_sorts_after_update_and_create(self):
        from novel_factory.api.routes.memory_updates import _order_items_for_apply

        items = [
            {"operation": "resolve", "id": "a"},
            {"operation": "update", "id": "b"},
            {"operation": "create", "id": "c"},
            {"operation": "deprecate", "id": "d"},
        ]
        ordered = [it["operation"] for it in _order_items_for_apply(items)]
        assert ordered.index("create") < ordered.index("resolve")
        assert ordered.index("update") < ordered.index("resolve")
        assert ordered.index("update") < ordered.index("deprecate")

    def test_stable_within_priority_group(self):
        from novel_factory.api.routes.memory_updates import _order_items_for_apply

        items = [
            {"operation": "update", "id": "u1"},
            {"operation": "create", "id": "c1"},
            {"operation": "update", "id": "u2"},
            {"operation": "create", "id": "c2"},
        ]
        ordered = [it["id"] for it in _order_items_for_apply(items)]
        # creates first (insertion order preserved), then updates (insertion order)
        assert ordered == ["c1", "c2", "u1", "u2"]


# ── Phase 1.2 + integration: same-batch resolve+update (PH-002 repro) ──


class TestApplyMemoryItemPlotResolution:
    def _make_item(self, operation, after, target_id=None, before=None):
        return {
            "target_table": "plot_holes",
            "operation": operation,
            "target_id": target_id,
            "after_json": json.dumps(after, ensure_ascii=False),
            "before_json": json.dumps(before, ensure_ascii=False) if before else None,
            "rationale": "",
            "evidence_text": "",
        }

    def test_update_patch_does_not_revert_resolve(self, repo):
        """Exact PH-002 regression: resolve then update in same chapter.

        Even applied in insertion order, the update must not revert the resolve
        because update patches are stripped of status (1.2) and terminal status
        is protected (1.1).
        """
        from novel_factory.api.routes.memory_updates import _apply_memory_item

        ph = repo.create_plot_hole(
            "p", code="PH-002", title="酒店监控中的模糊身影",
            planted_chapter=2, planned_resolve_chapter=4, status="planted",
        )

        resolve_item = self._make_item(
            "resolve",
            {"code": "PH-002", "status": "resolved", "description": "在信号塔回收"},
            target_id=ph["id"],
        )
        update_item = self._make_item(
            "update",
            {"code": "PH-002", "status": "planted", "description": "影像再次出现"},
            target_id=ph["id"],
        )

        # Apply resolve first, then the (stale) update — simulating insertion order
        r1 = _apply_memory_item(repo, "p", resolve_item, chapter_number=4)
        r2 = _apply_memory_item(repo, "p", update_item, chapter_number=4)
        assert r1["success"] and r2["success"]

        final = repo.get_plot_hole("p", ph["id"])
        assert final["status"] == "resolved"
        assert final["resolved_chapter"] == 4
        # The descriptive change from the update still landed.
        assert final["description"] == "影像再次出现"

    def test_resolve_assigns_status_even_with_stray_planted(self, repo):
        """resolve must win even if after_data carries status=planted."""
        from novel_factory.api.routes.memory_updates import _apply_memory_item

        ph = repo.create_plot_hole("p", code="PH-006", title="t", status="planted")
        item = self._make_item(
            "resolve",
            {"code": "PH-006", "status": "planted"},  # stray planted
            target_id=ph["id"],
        )
        result = _apply_memory_item(repo, "p", item, chapter_number=7)
        assert result["success"]
        final = repo.get_plot_hole("p", ph["id"])
        assert final["status"] == "resolved"
        assert final["resolved_chapter"] == 7
