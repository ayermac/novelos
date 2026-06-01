# Novel Factory v6.8.3 — Plot Hole Resolution Integrity Completion Report

**Version**: v6.8.3
**Branch**: v6.8.3-plot-resolution-integrity
**Date**: 2026-06-01
**Status**: COMPLETED

---

## Problem

User reported plot holes that should be resolved in a chapter were not marked
resolved. DB forensics on burn-in project (6 published chapters) confirmed:
- 18/19 plot holes stuck in `planted`, 0 resolved
- PH-002: resolved_chapter=4 but status=planted (contradiction)
- Root cause: a `resolve` patch (status=resolved) overwritten by a same-batch
  `update` patch carrying stale status="planted"; apply loop had zero ordering,
  no terminal protection.

## Six Defects Fixed (A-F)

| ID | Defect | Fix |
|----|--------|-----|
| A | update_plot_hole no terminal protection | protect_terminal kwarg (Phase 1.1) |
| B | update branch copies LLM status | strip status from plain update (Phase 1.2) |
| C | apply loop zero ordering | _order_items_for_apply (Phase 1.3) |
| D | insertion-order apply | ordering helper neutralizes (Phase 1.3) |
| E | Planner empty plot fields | context injection + self-check (Phase 2.1) |
| F | no deterministic fallback | reconcile_plot_resolution (Phase 2.2) |

Plus: data-repair migration 035 (Phase 3.1) and repository status guard (Phase 3.2).

## Implementation

- Phase 1.1: `db/repositories/plot_hole.py` — TERMINAL_PLOT_STATUSES,
  protect_terminal guard (only strips on explicit regressive status).
- Phase 1.2: `api/routes/memory_updates.py` — update pops status/resolved_chapter;
  resolve assigns status.
- Phase 1.3: `_order_items_for_apply` shared helper in both apply functions.
- Phase 2.1: `agents/planner.py` — pending plot codes in context + plot_resolve_gap
  self-check warning.
- Phase 2.2: `workflow/reconciliation.py::reconcile_plot_resolution` +
  memory_curator_node integration (plot_resolution_reconciled event). Evidence =
  code in plots_to_resolve AND code in chapter prose.
- Phase 3.1: `migrations/035_v6_8_3_plot_hole_status_repair.sql` (idempotent) +
  `_plot_hole_status_repaired` detector in migration_registry.
- Phase 3.2: `_normalize_plot_status` guard in create/update_plot_hole.

## Testing

- test_v683_plot_resolution_integrity.py: 9 (terminal protection, ordering,
  PH-002 same-batch regression)
- test_v683_plot_reconciliation.py: 10 (parse, resolve/skip cases)
- test_v683_plot_status_migration.py: 8 (repair SQL, idempotency, detector, guard)
- Total: 27 new tests
- Direct verification: detector False on dirty / True on clean; SQL repairs
  PH-002 planted->resolved (keeps resolved_chapter=4), validated->planted; idempotent.

## Commits

- 91a300a feat(v6.8.3): Phase 1 plot resolution integrity (P0 core fix)
- a410672 feat(v6.8.3): Phase 2 deterministic plot reconciliation (P1)
- (Phase 3 + docs pending commit)

## Migration Note

On first upgrade, the burn-in project's PH-002 (resolved_chapter=4, status=planted)
and PH-010 (validated) will be auto-repaired by migration 035. Back up before
running on production desktop DB.

---

**Author**: Claude (Opus 4.8)
**Status**: Ready for full-suite verification and merge
