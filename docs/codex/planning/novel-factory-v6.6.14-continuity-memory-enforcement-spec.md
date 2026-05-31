# v6.6.14 Continuity & Memory Enforcement Closure — Specification

## Goal

Close three backend gaps that allow the generation pipeline to silently ignore memory
context, accept low-quality memory into hard constraints, and produce no audit trail
of what memory each chapter consumed.

No LangGraph topology changes. No blocking on empty memory. No plot_holes blocking.
No frontend UI changes (audit trail exposed through existing run detail API only).

---

## Problem Statement

### Gap A — Silent passthrough on empty trusted memory

In `novel_factory/agent_runtime/context_builder.py`, when `_select_trusted_memory_batch()`
returns `(None, [])` (no trusted batch exists), the bundle silently contains an empty
`trusted_memory` list. Planner, Author, Editor, and Polisher receive no signal that
trusted memory is absent. They proceed as if the context is complete.

**Required:** When `trusted_memory` is empty, inject a `memory_context_degraded: True`
flag into the bundle and add a conditional notice to affected agent system prompts:
"当前没有可信记忆批次，必须以 story_facts 已确认事实和硬约束为准，不能脑补。"

Empty trusted memory must NOT block generation. The first chapter always has no memory.
Old projects and manual projects may never have memory. Blocking would be wrong.

**Hard constraint — context-only flag:** `memory_context_degraded=True` is a prompt
annotation only. It must never affect chapter status transitions, trigger revision, or
cause blocking. The workflow state machine is completely unaffected by this flag.

### Gap B — Editor has no story_facts compliance pass

The Editor's five review dimensions (setting, logic, poison, text, pacing) are prose
quality checks. None cross-reference `story_facts` confirmed facts against chapter text.
A chapter can contradict a `confirmed=True` fact (wrong character name, wrong setting,
resolved plot point reappearing) and pass Editor review.

**Required:** Add a 6th lightweight compliance dimension. Scope: only `story_facts`
rows with `confirmed=True`. NOT `plot_holes`. The check is advisory/warning by default
and does not trigger revision on its own unless the violation count is at or above a
threshold that makes the chapter factually incoherent (module constant, default = 3).

**Hard constraint — contradiction only, not absence:** A violation is only valid when
the chapter text explicitly contradicts a confirmed fact (e.g., a character whose
confirmed name is "林泽" is referred to with a different identity, faction, or status).
A fact that simply does not appear in the chapter text is NOT a violation. The LLM
prompt must make this distinction explicit.

> **Implementation note:** `story_facts` uses `status="active"` for confirmed facts
> (no `confirmed` column). Query: `repo.list_story_facts(project_id, status="active")`.

### Gap C — No memory consumption audit trail

There is no way to inspect, in run detail or state, which memory batch a chapter used,
whether it was degraded, or whether the agent context was built with trusted items.
Debugging memory-continuity issues requires reading logs.

**Required:** Write a `memory_context_audit` block to workflow state during
`planner_node` execution. Expose it in the `/runs/{run_id}` API response.

---

## Implementation Plan

### P1 — Memory Context Annotation

**Files touched:**
- `novel_factory/agent_runtime/context_builder.py` — add `memory_context_degraded` to bundle + set it + inject notice
- `novel_factory/agents/planner.py` — use flag in system prompt
- `novel_factory/agents/author.py` — use flag in system prompt
- `novel_factory/agents/editor.py` — use flag in system prompt
- `novel_factory/agents/polisher.py` — use flag in system prompt

#### 1a. `AgentContextBundle` — add field

In `context_builder.py`, class `AgentContextBundle` (around line 50), add:
```python
memory_context_degraded: bool = False
```

#### 1b. Set the flag after trusted batch lookup

In the method that calls `_select_trusted_memory_batch()` (around line 769 in
`build_for_planner`/`build_for_author`), after receiving `(batch, items)`:
```python
batch, items = _select_trusted_memory_batch(repo, project_id, chapter_number)
if not items:
    bundle.memory_context_degraded = True
```

The existing logic loading `trusted_memory` into the bundle is unchanged.

Also add:
```python
bundle.trusted_memory_batch_id = batch["id"] if batch else None
```
(needed for P3 audit).

#### 1c. Inject degraded notice into formatted prompt

In `format_context_bundle_for_prompt()` (or equivalent serializer used by each agent),
append when `bundle.memory_context_degraded is True`:

```
[记忆上下文降级]
当前章节暂无可信记忆批次。请严格以 story_facts 中已确认 (confirmed=True) 的事实
和硬约束为准，禁止脑补未在项目资料中出现的人物状态、剧情发展或世界设定细节。
```

This notice must appear in the context received by: **Planner, Author, Editor,
Polisher**. If each agent builds its own system prompt via `_build_v6_context()` or
similar, add the conditional block there instead.

**Screenwriter** and **Scout**: skip (not continuity-sensitive agents).

---

### P2 — Editor story_facts Compliance Check

**Files touched:**
- `novel_factory/agents/editor.py` — add compliance pass + integrate into result
- `novel_factory/quality/story_facts_compliance.py` *(new, only if logic > ~50 lines)*

#### 2a. Load confirmed story_facts

Before the editor's review cycle begins:
```python
confirmed_facts = repo.story_facts.list(project_id=project_id, confirmed=True)
```

If `confirmed_facts` is empty, skip the compliance pass entirely
(`checked=False, violation_count=0, violations=[]`).

#### 2b. Compliance check LLM call

Single LLM call with structured output. If `len(confirmed_facts) > 30`, pass only
the 30 most likely to be mentioned (heuristic: filter whose `name` or key tokens appear
in the chapter text; fall back to first 30 by recency).

Prompt structure:
- System: "You are a continuity reviewer. Given a list of confirmed story facts and a
  chapter text, identify any direct contradictions. Output only clear contradictions
  where the chapter text states the opposite of a confirmed fact."
- User: `confirmed_facts` (as JSON list) + chapter text (truncated to 4000 tokens)

Expected output per violation:
```python
{
    "fact_key": str,          # fact identifier / name
    "fact_statement": str,    # the confirmed fact text
    "violation_text": str,    # the contradicting passage in the chapter
    "severity": "warning" | "blocking"
}
```

**Stub mode:** Return `[]` unconditionally. Do not make LLM calls.

#### 2c. Integrate into editor result

Add to the editor result dict:
```python
"story_facts_compliance": {
    "checked": bool,
    "violation_count": int,
    "blocking_violation_count": int,
    "violations": list[dict],
}
```

**Revision trigger rule:**

Module constant in `editor.py`:
```python
FACTS_COMPLIANCE_BLOCK_THRESHOLD = 3
```

- `blocking_violation_count < FACTS_COMPLIANCE_BLOCK_THRESHOLD` → advisory only,
  no change to `quality_gate`
- `blocking_violation_count >= FACTS_COMPLIANCE_BLOCK_THRESHOLD` → set
  `quality_gate["pass"] = False` and append a `revision_target` note

**Do NOT change** the existing 5-dimension scoring logic or revision routing for the
below-threshold case.

---

### P3 — Memory Context Audit Trail

**Files touched:**
- `novel_factory/models/state.py` — add `memory_context_audit` key
- `novel_factory/workflow/nodes.py` — write audit in `planner_node`
- `novel_factory/api/routes/runs.py` — include audit in run detail response

#### 3a. `FactoryState` — add field

`FactoryState` is `TypedDict(total=False)` in `models/state.py:60`. Add:
```python
memory_context_audit: dict
```

Schema of the dict:
```python
{
    "chapter_number": int,
    "batch_id": str | None,           # trusted batch ID used, or None
    "batch_status": str,              # "trusted" | "missing" | "not_applicable"
    "memory_items_count": int,        # count of trusted items loaded
    "memory_context_degraded": bool,  # True when no trusted batch
    "built_at_node": str,             # always "planner_node"
}
```

#### 3b. `planner_node` — write audit to state

In `novel_factory/workflow/nodes.py`, inside `planner_node` (around line 764), after
`AgentContextBuilder` builds the context bundle:
```python
memory_audit = {
    "chapter_number": state.get("chapter_number"),
    "batch_id": getattr(context_bundle, "trusted_memory_batch_id", None),
    "batch_status": (
        "not_applicable" if state.get("chapter_number", 0) <= 1
        else "missing" if context_bundle.memory_context_degraded else "trusted"
    ),
    "memory_items_count": len(context_bundle.trusted_memory or []),
    "memory_context_degraded": context_bundle.memory_context_degraded,
    "built_at_node": "planner_node",
}
```

Return it from `planner_node` as part of the state update dict:
```python
return {
    "chapter_status": ...,
    "current_stage": ...,
    "_exec_events": ...,
    "memory_context_audit": memory_audit,
    # existing token fields unchanged
}
```

#### 3c. `GET /runs/{run_id}` — include audit in response

In `novel_factory/api/routes/runs.py` (around line 412), in the run detail endpoint.
`memory_status` and `recovery_state` are already populated from the run state snapshot.
Use the same pattern to add:
```python
"memory_context_audit": run_state.get("memory_context_audit") or {}
```

For runs created before v6.6.14, this field is `{}`. That is acceptable.

---

## Version Bump

- `novel_factory/version.py`: `"6.6.13"` → `"6.6.14"`
- `CHANGELOG.md`: add v6.6.14 entry

---

## Tests

New test file: `tests/test_v6614_continuity_enforcement.py`

### P1 tests

```python
def test_memory_context_degraded_flag_set_when_no_trusted_batch():
    # Build context for a project/chapter with no memory batches
    # Assert bundle.memory_context_degraded is True

def test_memory_context_degraded_flag_not_set_when_trusted_batch_exists():
    # Build context with a trusted batch present
    # Assert bundle.memory_context_degraded is False

def test_format_context_bundle_includes_degraded_notice():
    # bundle.memory_context_degraded = True
    # Assert formatted prompt contains "可信记忆批次"

def test_format_context_bundle_no_degraded_notice_when_trusted():
    # bundle.memory_context_degraded = False
    # Assert formatted prompt does NOT contain the degraded notice
```

### P2 tests

```python
def test_story_facts_compliance_skipped_when_no_confirmed_facts():
    # Project with zero confirmed story_facts
    # Assert compliance result: checked=False, violation_count=0

def test_story_facts_compliance_returns_empty_in_stub_mode():
    # Editor compliance check in stub mode
    # Assert violations == []

def test_story_facts_compliance_below_threshold_does_not_trigger_revision():
    # 2 blocking violations (below threshold of 3)
    # Assert quality_gate.pass is not changed by compliance alone

def test_story_facts_compliance_at_threshold_triggers_revision():
    # 3 blocking violations (at threshold)
    # Assert quality_gate["pass"] is False

def test_editor_result_always_includes_story_facts_compliance_field():
    # Run editor in stub mode
    # Assert "story_facts_compliance" key exists with correct schema
```

### P3 tests

```python
def test_planner_node_writes_memory_context_audit_missing():
    # planner_node with no trusted batch
    # Assert state["memory_context_audit"]["batch_status"] == "missing"
    # Assert state["memory_context_audit"]["memory_context_degraded"] is True
    # Assert state["memory_context_audit"]["batch_id"] is None

def test_planner_node_writes_memory_context_audit_trusted():
    # planner_node with trusted batch present
    # Assert state["memory_context_audit"]["batch_status"] == "trusted"
    # Assert state["memory_context_audit"]["batch_id"] is not None

def test_planner_node_writes_memory_context_audit_chapter_one_not_applicable():
    # chapter 1 has no previous chapter memory to consume
    # Assert state["memory_context_audit"]["batch_status"] == "not_applicable"
    # Assert state["memory_context_audit"]["batch_id"] is None
    # Assert state["memory_context_audit"]["memory_context_degraded"] is False

def test_run_detail_api_includes_memory_context_audit():
    # Complete a workflow run in stub mode
    # GET /runs/{run_id}
    # Assert JSON response has "memory_context_audit" key
    # For a run past planner_node, assert the dict is non-empty
```

---

## Acceptance Criteria

| # | Criterion |
|---|-----------|
| 1 | `bundle.memory_context_degraded` is `True` when no trusted batch exists |
| 2 | `bundle.memory_context_degraded` is `False` when a trusted batch exists |
| 3 | Degraded notice appears in formatted prompt for Planner/Author/Editor/Polisher when degraded |
| 4 | Degraded notice does NOT appear when trusted batch is present |
| 5 | Empty trusted memory never blocks or raises an exception in any node |
| 6 | Editor result always contains `story_facts_compliance` with correct schema |
| 7 | `story_facts_compliance.checked == False` when no confirmed story_facts |
| 8 | Violations below threshold are advisory only (no revision triggered) |
| 9 | 3+ blocking violations trigger revision via quality_gate |
| 10 | Stub mode: compliance check returns empty violations, no LLM call |
| 11 | `planner_node` state return includes `memory_context_audit` |
| 12 | `GET /runs/{run_id}` response includes `memory_context_audit` field |
| 13 | Full `python3 -m pytest -q` passes (no regressions) |

---

## Out of Scope for v6.6.14

| Item | Deferred to |
|------|-------------|
| ProjectOverview UI showing memory audit | v6.6.15 or after burn-in |
| plot_holes compliance check | v6.6.15 (false positive risk with unresolved foreshadowing) |
| Continuity gate as a LangGraph node | v6.6.16 (topology change required) |
| Blocking on empty memory | never (first-chapter/old/manual projects would break) |
| story_facts compliance in Polisher | v6.6.15 (Polisher is prose quality only) |
| Per-scene fact injection in Author | v6.6.15 (Author context already loads story_facts) |
