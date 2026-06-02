# Novel Factory v6.8.3 — Plot Hole Resolution Integrity

**Version**: v6.8.3
**Type**: Bug Fix + Data Integrity Hardening
**Priority**: HIGH
**Target Date**: 2026-06-02
**Status**: Planning

---

## Overview

v6.8.3 fixes a systemic bug where plot hole (伏笔) resolution status is never persisted. Despite the MemoryCurator correctly generating `resolve` patches, the resolved status is silently overwritten by subsequent `update` patches in the same batch, leaving every plot hole stuck in `planted` state.

**Problem Statement**: User reported "某个章节要回收的伏笔，伏笔状态没有被改成回收".

**Diagnosis (verified against novel_7wn9 production DB, 6 published chapters)**:
- 18/19 plot holes stuck in `planted`, 0 in `resolved`
- PH-002 smoking gun: `resolved_chapter=4` but `status=planted` (contradiction)
- A `resolve` patch (rowid 2785, status=resolved) is overwritten by a later `update` patch (rowid 2786, status=planted) in the same chapter-4 batch

---

## Root Cause Analysis

### The Bug Chain (line-verified)

```
1. MemoryCurator (LLM) generates 4 patches for PH-002 in one chapter:
   - 1x resolve (status=resolved)
   - 3x update (data carries status="planted")
            v
2. Patches stored with near-identical created_at
            v
3. list_memory_items -> "ORDER BY created_at" -> insertion order
   (memory_update.py:241,247)
            v
4. for item in items: bare loop, zero sort/dedup/merge
   (memory_updates.py:1239, 1377)
            v
5. _apply_memory_item -> plot_holes/update: plot_data = dict(after_data)
   (memory_updates.py:838)
            v
6. update_plot_hole: blindly UPDATEs all fields incl. status
   (plot_hole.py:132-146)
            v
RESULT: resolve sets resolved -> update overwrites back to planted
```

### Six Defects (all must be fixed)

| ID | Defect | Location | Severity |
|----|--------|----------|----------|
| A | update_plot_hole blindly writes status, no terminal protection | db/repositories/plot_hole.py:132-146 | P0 |
| B | update branch directly copies LLM after_data (incl. status) | api/routes/memory_updates.py:838 | P0 |
| C | Apply loop zero ordering/dedup across same-target patches | api/routes/memory_updates.py:1239,1377 | P0 |
| D | Item retrieval = insertion order (ORDER BY created_at) | db/repositories/memory_update.py:241,247 | P1 |
| E | Planner never populates structured plots_to_resolve/plant | agents/planner.py, instruction table | P1 |
| F | No deterministic resolution fallback (used_plot_refs unused) | whole pipeline | P1 |

### Additional Data Issues
- PH-010 has illegal status `validated` (standard: planted/resolved/abandoned)
- Schema has no CHECK constraint on plot_holes.status

---

## Goals

- G1: resolve/deprecate is terminal, survives same-batch updates
- G2: plain update can never silently revert a terminal status
- G3: Patch application is deterministic (operation-priority ordered)
- G4: Planner populates structured plots_to_resolve/plots_to_plant
- G5: Deterministic resolution fallback via plots_to_resolve ∩ used_plot_refs
- G6: Clean up legacy bad data + repository-layer status guard

---

## Technical Design

### Phase 1: Terminal Status Protection (P0 — core fix)

#### 1.1 update_plot_hole: protect terminal status

**File**: novel_factory/db/repositories/plot_hole.py

Add terminal protection: when existing row is resolved/abandoned, a non-terminal
update must not regress status/resolved_chapter.

```python
TERMINAL_PLOT_STATUSES = ("resolved", "abandoned")

def update_plot_hole(self, project_id, plot_id, data, *, protect_terminal=True):
    conn = self._conn()
    try:
        current = self.get_plot_hole(project_id, plot_id)
        if current is None:
            return None
        data = dict(data)
        if protect_terminal and current.get("status") in TERMINAL_PLOT_STATUSES:
            incoming = data.get("status")
            if incoming is None or incoming not in TERMINAL_PLOT_STATUSES:
                data.pop("status", None)
                data.pop("resolved_chapter", None)
        fields, values = [], []
        for key in ("code","type","title","description","planted_chapter",
                    "planned_resolve_chapter","resolved_chapter","status","notes"):
            if key in data:
                fields.append(f"{key}=?"); values.append(data[key])
        if not fields:
            return current
        values.extend([project_id, plot_id])
        cursor = conn.execute(
            f"UPDATE plot_holes SET {', '.join(fields)} WHERE project_id=? AND id=?", values)
        conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_plot_hole(project_id, plot_id)
    finally:
        conn.close()
```

Last line of defense — a resolved plot can never be silently reverted.

#### 1.2 memory_updates: strip status from plain update patches

**File**: novel_factory/api/routes/memory_updates.py (plot_holes branch ~829-848)

For operation=="update", drop status/resolved_chapter. Status changes only via
resolve/deprecate. resolve uses assignment (not setdefault) so a stray status
field cannot weaken it.

```python
if operation == "update":
    plot_data.pop("status", None)
    plot_data.pop("resolved_chapter", None)
elif operation == "resolve":
    plot_data["status"] = "resolved"
    plot_data.setdefault("resolved_chapter", chapter_number or None)
elif operation == "deprecate":
    plot_data["status"] = "abandoned"
```

#### 1.3 Operation-priority ordering in apply loop

**File**: novel_factory/api/routes/memory_updates.py (both apply functions)

Stable-sort items so terminal ops apply last. Extract shared helper
_order_items_for_apply(items) to avoid drift.

```python
_OP_PRIORITY = {"create": 0, "update": 1, "resolve": 2, "deprecate": 2}
items = sorted(items, key=lambda it: _OP_PRIORITY.get(it.get("operation","update"), 1))
```

Defense-in-depth: ordering guarantees resolve wins even without 1.1/1.2.

### Phase 2: Deterministic Reconciliation (P1)

#### 2.1 Planner populates structured plot fields

**File**: novel_factory/agents/planner.py

- Strengthen PLANNER_SYSTEM_PROMPT to require plots_to_plant/plots_to_resolve
  contain actual plot codes (PH-002), not prose
- Ensure save path writes plots_to_resolve/plots_to_plant to instruction row
- Self-check: brief references resolving a plot but plots_to_resolve empty -> warn

#### 2.2 Deterministic resolution reconciliation

**File**: new helper in novel_factory/workflow/reconciliation.py, called from memory_curator_node

```python
def reconcile_plot_resolution(repo, project_id, chapter_number, used_plot_refs):
    instruction = repo.get_instruction_by_chapter(project_id, chapter_number)
    if not instruction:
        return {"resolved": []}
    planned = _parse_codes(instruction.get("plots_to_resolve"))
    confirmed = set(used_plot_refs or [])
    resolved = []
    for code in [c for c in planned if c in confirmed]:
        plot = _find_plot_by_code(repo, project_id, code)
        if plot and plot.get("status") not in ("resolved", "abandoned"):
            repo.update_plot_hole(project_id, plot["id"],
                {"status": "resolved", "resolved_chapter": chapter_number})
            resolved.append(code)
    return {"resolved": resolved}
```

Integration: call from memory_curator_node after batch applied, emit exec_event
plot_resolution_reconciled. used_plot_refs read from author artifact/chapter metadata.

### Phase 3: Data Cleanup & Schema Guard (P2)

#### 3.1 Migration: fix legacy plot hole data

**File**: new migration novel_factory/db/migrations/0XX_plot_hole_status_repair.sql

```sql
UPDATE plot_holes SET status = 'resolved'
WHERE resolved_chapter IS NOT NULL AND status NOT IN ('resolved','abandoned');

UPDATE plot_holes SET status = 'planted' WHERE status = 'validated';
```

Idempotent, project-agnostic, no hardcoded codes.

#### 3.2 Schema integrity (forward-looking)

Document canonical status set in schema comments. SQLite CHECK requires table
rebuild (high risk) — enforce at repository layer via _validate_plot_status()
guard in create_plot_hole/update_plot_hole instead.

---

## Implementation Plan

### Sprint 1: P0 Core Fix (Day 1)
- [ ] 1.1 Terminal status protection in update_plot_hole
- [ ] 1.2 Strip status from plain update patches
- [ ] 1.3 Operation-priority ordering (both apply functions, shared helper)
- [ ] Unit tests incl. exact PH-002 scenario

### Sprint 2: P1 Reconciliation (Day 2)
- [ ] 2.1 Planner structured plot fields + prompt + self-check
- [ ] 2.2 reconcile_plot_resolution + memory_curator_node integration
- [ ] Unit tests

### Sprint 3: P2 Data & Schema (Day 3)
- [ ] 3.1 Migration for legacy data repair (idempotent)
- [ ] 3.2 Repository-layer status validation guard
- [ ] Migration + idempotency tests

### Sprint 4: Validation (Day 4)
- [ ] Full test suite (2640+)
- [ ] Manual: re-run chapter, confirm resolve persists
- [ ] Verify migration on novel_7wn9 copy
- [ ] Docs: CHANGELOG, completion report, spec status -> Completed

---

## Testing Strategy

### New Test Files
- tests/test_v683_plot_resolution_integrity.py
- tests/test_v683_plot_reconciliation.py
- tests/test_v683_plot_status_migration.py

### Critical Test Cases (regression reproduction)
1. Same-batch resolve+update -> final status MUST be resolved
2. Terminal protection: resolved + plain update -> stays resolved
3. Operation ordering: shuffled order -> resolve still wins
4. Reconciliation: plots_to_resolve ∩ used_plot_refs -> auto-resolved
5. No false resolution: planned but NOT used -> stays planted
6. Migration idempotency: run twice -> same; PH-002 contradiction repaired

### Acceptance Criteria
- [ ] All 2640+ existing tests pass
- [ ] New tests verify fix for exact PH-002 scenario
- [ ] Manual: freshly run chapter resolves planned plots, persists status=resolved
- [ ] Migration repairs contradiction without touching unrelated rows

---

## Risks & Mitigations

- R1 Terminal protection blocks legit re-open: resolve/deprecate + explicit terminal
  status still pass; only non-terminal plain update blocked.
- R2 Ordering changes other-table semantics: stable sort preserves intra-group order;
  verify story_facts (only other resolve/deprecate user) unharmed.
- R3 Migration corrupts data: idempotent, conservative WHERE, test on copy, backup first.
- R4 Reconciliation double-resolves: guard status not in (resolved,abandoned); no-op if
  LLM already resolved.

---

## Rollback Plan
- Code: revert v6.8.3 commits.
- Migration: keep pre-migration plot_holes backup; status repairs are forward-only.

---

## Success Criteria
1. All 6 defects (A-F) fixed
2. Full suite passes (2640+ incl. new tests)
3. PH-002-style contradiction cannot recur (regression test)
4. Legacy data repaired (PH-002 status, PH-010 validated)
5. Freshly run chapter persists plot resolution

---

## References
- Diagnosis: novel_7wn9 DB forensics
- Affected code: plot_hole.py, memory_updates.py, memory_update.py, planner.py,
  memory_curator.py, reconciliation.py (new)
- Related: v6.8.2 revision reliability hardening

---

**Spec Author**: Claude (Opus 4.8)
**Status**: Approved for implementation
**Next Step**: Branch v6.8.3-plot-resolution-integrity, begin Sprint 1
