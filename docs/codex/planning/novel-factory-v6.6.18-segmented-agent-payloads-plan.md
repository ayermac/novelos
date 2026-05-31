# v6.6.18 Segmented Agent Payloads Implementation Plan

Status: proposed next implementation plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn real-LLM long-output agents from one-shot large requests into bounded segmented generation, validation, and merge flows.

**Architecture:** Keep Genesis as the reference pattern: focused segment prompts, small output budgets, deterministic merge, and explicit failure when the provider truly fails. Add a small shared segmentation helper for repeated chunking/telemetry, then migrate Author, Polisher, and MemoryCurator in risk order. Planner and Screenwriter stay mostly unchanged because they are single-chapter structured planners unless future multi-chapter planning is introduced.

**Tech Stack:** Python 3.9+, FastAPI routes, LangGraph workflow nodes, existing `LLMProvider.invoke_json/invoke_text`, pytest.

---

## Version Scope

Target version: `6.6.18`

Working title: **Segmented Agent Payloads & Real LLM Reliability**

Primary acceptance rule:

- Real-mode agents that process long content must not rely on one large request when the output can naturally be split into independent sections.

Out of scope:

- Replacing the LLM provider stack.
- Adding a new UI design surface.
- Reworking Planner/Screenwriter unless tests show they are producing multi-chapter oversized payloads.

## Risk Map From Current Code

- Genesis: already segmented in `novel_factory/api/routes/genesis.py`; keep as baseline and harden tests.
- Author: `novel_factory/agents/author.py` uses prose-first generation, but `_try_plain_text_draft()` still asks for a whole chapter in one call.
- Polisher: `novel_factory/agents/polisher.py` uses prose-first polishing, but `_try_plain_text_polish()` still asks for a whole chapter in one call.
- MemoryCurator: `novel_factory/agents/memory_curator.py` still extracts from the whole context in one JSON call, then falls back on timeout/empty output.
- Editor: `novel_factory/agents/editor.py` already uses compact review with `max_tokens=700`; keep it in monitor-only scope.

## Files

- Create: `novel_factory/agent_runtime/segmented_generation.py`
- Modify: `novel_factory/api/routes/genesis.py`
- Modify: `novel_factory/agents/author.py`
- Modify: `novel_factory/agents/polisher.py`
- Modify: `novel_factory/agents/memory_curator.py`
- Modify: `novel_factory/workflow/execution_events.py`
- Modify: `novel_factory/version.py`
- Create: `tests/test_v6618_segmented_agent_payloads.py`
- Modify: `tests/test_v532_project_genesis.py`
- Modify: `tests/test_v6617_memory_curator_fallback.py`
- Create: `docs/codex/specs/novel-factory-v6.6.18-segmented-agent-payloads-spec.md`
- Create: `docs/codex/reports/novel-factory-v6.6.18-completion-report.md`

---

## Task 1: Shared Segmentation Helper

**Files:**
- Create: `novel_factory/agent_runtime/segmented_generation.py`
- Test: `tests/test_v6618_segmented_agent_payloads.py`

- [ ] **Step 1: Write failing tests for chunk boundaries**

Add:

```python
from novel_factory.agent_runtime.segmented_generation import chunk_items, chunk_text_by_paragraphs


def test_chunk_items_preserves_order_and_size():
    chunks = list(chunk_items([1, 2, 3, 4, 5], size=2))
    assert chunks == [[1, 2], [3, 4], [5]]


def test_chunk_text_by_paragraphs_keeps_paragraphs_under_soft_limit():
    text = "甲" * 10 + "\n\n" + "乙" * 10 + "\n\n" + "丙" * 10
    chunks = list(chunk_text_by_paragraphs(text, soft_limit=25))
    assert chunks == ["甲" * 10 + "\n\n" + "乙" * 10, "丙" * 10]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py::test_chunk_items_preserves_order_and_size tests/test_v6618_segmented_agent_payloads.py::test_chunk_text_by_paragraphs_keeps_paragraphs_under_soft_limit -q
```

Expected: fails because `novel_factory.agent_runtime.segmented_generation` does not exist.

- [ ] **Step 3: Implement helper**

Create `novel_factory/agent_runtime/segmented_generation.py`:

```python
"""Utilities for bounded real-LLM segmented generation."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")


def chunk_items(items: list[T], *, size: int) -> Iterator[list[T]]:
    """Yield ordered item chunks with a positive fixed size."""
    chunk_size = max(1, int(size or 1))
    for index in range(0, len(items), chunk_size):
        yield items[index:index + chunk_size]


def chunk_text_by_paragraphs(text: str, *, soft_limit: int) -> Iterator[str]:
    """Chunk text by paragraph without splitting unless a paragraph is oversized."""
    limit = max(1, int(soft_limit or 1))
    paragraphs = [p.strip() for p in str(text or "").split("\n\n") if p.strip()]
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        next_len = len(paragraph) if not current else current_len + 2 + len(paragraph)
        if current and next_len > limit:
            yield "\n\n".join(current)
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len = next_len
    if current:
        yield "\n\n".join(current)
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py -q
```

Expected: both helper tests pass.

- [ ] **Step 5: Commit**

```bash
git add novel_factory/agent_runtime/segmented_generation.py tests/test_v6618_segmented_agent_payloads.py
git commit -m "Add segmented generation helpers"
```

---

## Task 2: Genesis Baseline Hardening

**Files:**
- Modify: `tests/test_v532_project_genesis.py`
- Modify: `novel_factory/api/routes/genesis.py`

- [ ] **Step 1: Add acceptance test for no provider-error template success**

Ensure this test exists and stays green:

```python
def test_real_genesis_api_connection_error_reports_failure_without_template_recovery(monkeypatch, tmp_path):
    from novel_factory.llm.openai_compatible import LLMConnectionError
    # A provider connection error must produce GENESIS_FAILED and a failed genesis_run.
```

- [ ] **Step 2: Add acceptance test for bounded segment calls**

Ensure this test exists and asserts:

```python
assert len(provider.calls) == 4
assert all(call["max_tokens"] <= 4500 for call in provider.calls)
assert "local_recovery" not in json.dumps(draft, ensure_ascii=False)
```

- [ ] **Step 3: Run Genesis tests**

Run:

```bash
python3 -m pytest tests/test_v532_project_genesis.py -q
```

Expected: all Genesis tests pass.

- [ ] **Step 4: Commit if tests required edits**

```bash
git add novel_factory/api/routes/genesis.py tests/test_v532_project_genesis.py
git commit -m "Harden genesis segmented generation tests"
```

---

## Task 3: Author Segmented Drafting

**Files:**
- Modify: `novel_factory/agents/author.py`
- Test: `tests/test_v6618_segmented_agent_payloads.py`

- [ ] **Step 1: Write failing test for segmented Author calls**

Add a fake provider and assert Author drafts by scene-beat chunks:

```python
def test_author_real_mode_generates_scene_beat_segments(monkeypatch, tmp_path):
    # Build a repo chapter with 6 scene beats and instruction.
    # Fake LLM returns one text segment per call.
    # Assert at least 2 invoke_text calls, each prompt contains "【正文分段】".
    # Assert final content contains segment 1 and segment 2 in order.
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py::test_author_real_mode_generates_scene_beat_segments -q
```

Expected: fails because Author still drafts the whole chapter in one long call.

- [ ] **Step 3: Implement Author segment path**

Modify `AuthorAgent._try_plain_text_draft()`:

- Load scene beats with `self._get_scene_beats(state)`.
- If real mode and `len(beats) >= 4`, call a new private method `_try_segmented_plain_text_draft()`.
- Chunk beats by 2 or 3 beats using `chunk_items`.
- For each chunk, prompt for only that part:

```text
【正文分段】{segment_index}/{segment_count}
本段只写 scene beat {start}-{end}。
前文摘要: ...
本段输出纯正文，不要 JSON，不要解释。
```

- Merge segments with blank lines.
- Keep existing `_sanitize_output()`, word-count gate, scene-beat coverage repair, and death-penalty checks.

- [ ] **Step 4: Run Author tests**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py::test_author_real_mode_generates_scene_beat_segments tests/test_v6617_memory_curator_fallback.py -q
```

Expected: new Author test passes; existing fallback tests remain green.

- [ ] **Step 5: Commit**

```bash
git add novel_factory/agents/author.py tests/test_v6618_segmented_agent_payloads.py
git commit -m "Segment author long-form drafting"
```

---

## Task 4: Polisher Segmented Polishing

**Files:**
- Modify: `novel_factory/agents/polisher.py`
- Test: `tests/test_v6618_segmented_agent_payloads.py`

- [ ] **Step 1: Write failing test for long polish chunking**

Add:

```python
def test_polisher_real_mode_polishes_long_text_in_chunks(monkeypatch, tmp_path):
    # Seed a drafted chapter with 8 paragraphs.
    # Fake LLM returns "润色段 N".
    # Assert multiple invoke_text calls and final content preserves all chunk outputs.
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py::test_polisher_real_mode_polishes_long_text_in_chunks -q
```

Expected: fails because `_try_plain_text_polish()` still sends the whole context once.

- [ ] **Step 3: Implement Polisher chunk path**

Modify `_try_plain_text_polish()`:

- Extract current draft body from state/chapter.
- Use `chunk_text_by_paragraphs(content, soft_limit=2800)`.
- For one chunk, keep existing behavior.
- For multiple chunks, call a new `_polish_text_chunk()` per chunk with:

```text
【润色分段】{index}/{total}
只润色本段，保留事实、顺序、人物关系。
前一段尾句: ...
后一段首句: ...
```

- Merge chunks.
- Re-run existing fact-risk, word-count, and warning checks.

- [ ] **Step 4: Run Polisher tests**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py::test_polisher_real_mode_polishes_long_text_in_chunks tests/test_v64_editor_quality_gates.py -q
```

Expected: segmented polishing passes and editor gates remain stable.

- [ ] **Step 5: Commit**

```bash
git add novel_factory/agents/polisher.py tests/test_v6618_segmented_agent_payloads.py
git commit -m "Segment polisher long-form polishing"
```

---

## Task 5: MemoryCurator Segmented Extraction

**Files:**
- Modify: `novel_factory/agents/memory_curator.py`
- Modify: `tests/test_v6617_memory_curator_fallback.py`
- Test: `tests/test_v6618_segmented_agent_payloads.py`

- [ ] **Step 1: Write failing test for chunked extraction**

Add:

```python
def test_memory_curator_extracts_long_chapter_in_chunks():
    # Long chapter content contains two facts in distant paragraphs.
    # Fake LLM returns one patch per chunk.
    # Assert multiple invoke_json calls and merged memory_items_count == 2.
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py::test_memory_curator_extracts_long_chapter_in_chunks -q
```

Expected: fails because MemoryCurator still runs a single extraction call.

- [ ] **Step 3: Implement chunked MemoryCurator extraction**

Modify `_execute()`:

- Build context as today for short chapters.
- For long chapter content, split the chapter body by paragraphs.
- Run `invoke_json()` per chunk using the existing schema prompt.
- Merge all patches through `_robust_extract_patches()` and `_validate_patches()`.
- Only use fallback model when all chunks fail or the primary times out before producing any valid patch.
- Preserve state-card fallback as degraded/low-confidence, not as trusted success.

- [ ] **Step 4: Run MemoryCurator tests**

Run:

```bash
python3 -m pytest tests/test_v6617_memory_curator_fallback.py tests/test_v6618_segmented_agent_payloads.py::test_memory_curator_extracts_long_chapter_in_chunks -q
```

Expected: existing timeout/fallback behavior remains intact and chunked extraction passes.

- [ ] **Step 5: Commit**

```bash
git add novel_factory/agents/memory_curator.py tests/test_v6617_memory_curator_fallback.py tests/test_v6618_segmented_agent_payloads.py
git commit -m "Segment memory curator extraction"
```

---

## Task 6: Observability For Segments

**Files:**
- Modify: `novel_factory/workflow/execution_events.py`
- Modify: `novel_factory/workflow/nodes.py`
- Test: `tests/test_v6618_segmented_agent_payloads.py`

- [ ] **Step 1: Add event constants**

Add:

```python
EVENT_SEGMENT_STARTED = "segment_started"
EVENT_SEGMENT_COMPLETED = "segment_completed"
EVENT_SEGMENT_FAILED = "segment_failed"
```

- [ ] **Step 2: Add test for segment events**

Add:

```python
def test_segmented_author_logs_segment_events(...):
    # Run fake Author segmented path.
    # Assert workflow execution events include segment_started and segment_completed.
```

- [ ] **Step 3: Emit events from segmented agents**

When an agent executes segmented work, append `_exec_events` entries with:

```python
{
    "event_type": "segment_completed",
    "message": "Author 分段生成完成：2/4",
    "payload": {"agent": "author", "segment_index": 2, "segment_count": 4},
}
```

- [ ] **Step 4: Run workflow event tests**

Run:

```bash
python3 -m pytest tests/test_v6618_segmented_agent_payloads.py tests/test_v6616_real_project_burnin.py -q
```

Expected: segment events appear without breaking existing burn-in observability.

- [ ] **Step 5: Commit**

```bash
git add novel_factory/workflow/execution_events.py novel_factory/workflow/nodes.py tests/test_v6618_segmented_agent_payloads.py
git commit -m "Add segmented generation observability"
```

---

## Task 7: Version, Spec, And Regression Closure

**Files:**
- Modify: `novel_factory/version.py`
- Create: `docs/codex/specs/novel-factory-v6.6.18-segmented-agent-payloads-spec.md`
- Create: `docs/codex/reports/novel-factory-v6.6.18-completion-report.md`

- [ ] **Step 1: Bump runtime version**

Change:

```python
__version__: str = "6.6.18"
```

- [ ] **Step 2: Add version spec**

Create the spec with:

```markdown
# v6.6.18 Segmented Agent Payloads Spec

## Goal
Reduce real-LLM long request failures by splitting long generation/extraction tasks.

## Acceptance
- Genesis uses bounded segmented calls.
- Author segments long real-mode drafting by scene beats.
- Polisher segments long real-mode polishing by paragraphs.
- MemoryCurator segments long extraction by content chunks.
- Provider connection failures are not reported as successful generated content.
```

- [ ] **Step 3: Run targeted regression**

Run:

```bash
python3 -m pytest tests/test_v532_project_genesis.py tests/test_v6617_memory_curator_fallback.py tests/test_v6618_segmented_agent_payloads.py -q
```

Expected: all targeted segmented-agent tests pass.

- [ ] **Step 4: Run broader backend regression**

Run:

```bash
python3 -m pytest tests/test_v6616_real_project_burnin.py tests/test_workflow.py tests/test_agents.py -q
```

Expected: all selected workflow/agent tests pass.

- [ ] **Step 5: Optional full verification**

Run:

```bash
python3 -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 6: Commit**

```bash
git add novel_factory/version.py docs/codex/specs/novel-factory-v6.6.18-segmented-agent-payloads-spec.md docs/codex/reports/novel-factory-v6.6.18-completion-report.md
git commit -m "Prepare v6.6.18 segmented agent payloads"
```

---

## Execution Order

Recommended order:

1. Shared helper.
2. Genesis hardening.
3. Author segmented drafting.
4. Polisher segmented polishing.
5. MemoryCurator segmented extraction.
6. Segment observability.
7. Version/spec/report.

Rationale: Author and Polisher create the largest user-visible payloads and should inherit the same bounded-call discipline as Genesis first. MemoryCurator follows with chunked extraction so long chapters do not silently lose facts.

## Verification Checklist

- [ ] No real-mode Genesis provider connection failure is converted into successful template content.
- [ ] Author long real-mode drafting uses more than one call when scene beats exceed the configured chunk size.
- [ ] Polisher long real-mode polishing uses paragraph chunks and preserves paragraph order.
- [ ] MemoryCurator long extraction merges valid patches from multiple chunks.
- [ ] Segment events are visible in workflow run details.
- [ ] Existing stuck-run, secure-key, and Genesis tests remain green.
- [ ] `git diff --check` is clean.

## Self-Review

Spec coverage:

- Genesis is covered by Task 2.
- Author is covered by Task 3.
- Polisher is covered by Task 4.
- MemoryCurator is covered by Task 5.
- Observability is covered by Task 6.
- Versioning is covered by Task 7.

Placeholder scan:

- No placeholder markers are used.
- Each task has file targets and test commands.

Type consistency:

- The helper names `chunk_items` and `chunk_text_by_paragraphs` are introduced in Task 1 and reused consistently.
- Event names use the same `EVENT_SEGMENT_*` constants throughout the plan.
