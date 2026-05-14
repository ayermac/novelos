# Personal Author Workbench Direction

## Purpose

This document captures the next product direction after v5.5.15. It is a direction document, not an executable version spec. Development agents should not treat it as implementation scope until a concrete version spec is created under `docs/codex/planning/`.

## Product Positioning

Novelos should next focus on becoming:

```text
A personal AI Agent long-form authoring workbench.
```

The priority is not multi-tenant SaaS, enterprise role permissions, or commercial administration. Those may become useful later, but they are not the next bottleneck.

## Current Baseline

v5.5.15 completed the production-readiness closure line:

- duplicate generation protection,
- workflow/chapters contradiction visibility,
- obsolete session cleanup behavior,
- real-project acceptance,
- short-term usable stable baseline.

v5.6 introduced the personal author workbench as the default project experience. v5.6.1 then stabilized the workbench with routing, chapter context preservation, readable artifacts, non-native dialogs, loading states, stuck-run recovery, and terminal-workflow contradiction handling.

The immediate next step is to turn the stable workbench into a daily writing loop: editing, saving, versioning, diff, rollback, and local AI revision.

## Product Principles

1. The author must be able to use Novelos daily without fighting the workflow.
2. AI autonomy should remain bounded, inspectable, and reversible.
3. Long-form consistency is a core product moat.
4. Review and revision should feel like editing, not rerunning a black box.
5. AgentOps exists to help the author understand and improve the system, not to become the main product surface.
6. Enterprise platform features should wait until the personal author loop is genuinely strong.

## Near-Term Priority Areas

### 1. Daily Writing Workbench

Goal: make the core writing loop comfortable and obvious.

Candidate capabilities:

- project overview focused on today's writing task,
- current chapter workspace with draft, instruction, state card, review, and revision in one place,
- one-click continue to next chapter,
- manual editing of AI outputs,
- accept/reject/regenerate/local-revise controls,
- draft version comparison.

### 2. Longform Memory and Consistency

Goal: make the story more stable as it gets longer.

Candidate capabilities:

- character state cards,
- world fact ledger,
- plot thread and foreshadowing management,
- timeline management,
- chapter summary extraction,
- setting conflict detection,
- human-reviewed memory updates,
- pre-generation context readiness for the next chapter.

### 3. Review and Local Revision Studio

Goal: turn review from "pass/fail" into an editing workflow.

Candidate capabilities:

- grouped review issues: setting, logic, pacing, prose, AI trace,
- issue-to-revision-target mapping,
- local revision for selected paragraphs or scenes,
- user-authored revision notes,
- before/after diff,
- review score trend.

### 4. Creator Knowledge Base / RAG

Goal: let the author bring reference materials into generation safely and visibly.

Candidate capabilities:

- upload setting documents, character notes, reference material, and prior chapters,
- chunking and embedding pipeline,
- metadata filters by character, location, event, plot thread, chapter range,
- visible retrieval results,
- citations or source references in Agent context summaries,
- prompt-injection protection for retrieved documents.

### 5. AgentOps Replay and Evaluation

Goal: make runs explainable and improvements measurable.

Candidate capabilities:

- run timeline,
- per-Agent input and output summaries,
- token and latency tracking,
- failure reason classification,
- revision chain visualization,
- artifact version chain,
- replay or retry from safe points,
- eval cases for Planner, Editor, memory extraction, and RAG retrieval.

### 6. Export and Publishing Pipeline

Goal: make authored content deliverable outside the app.

Candidate capabilities:

- Markdown export,
- DOCX / EPUB export,
- chapter collection export,
- publication readiness checklist,
- title, synopsis, chapter summary generation,
- final archive and version locking.

## Suggested Next Version Sequence

Do not open a broad "v6" by default. Keep the next steps narrow and author-facing.

Recommended sequence:

```text
v5.7 Daily Writing Editing and Versioning              (completed)
v5.7.1 Internal Hardening                              (completed)
v5.8 Workflow Observability and Recovery               (completed)
v5.9 Writing Skills and Prompt Template System         (next candidate, Pi-inspired)
v6.0 Longform Context Engineering and Memory Governance
```

Rationale:

- It moves the product from "AI can generate chapters" to "authors can safely write with AI every day."
- It makes human edits, AI edits, and publication decisions traceable and reversible.
- It avoids premature multi-tenant or enterprise scope.
- It creates a better foundation for memory, revision, RAG, and evaluation work.

The latest completed executable planning spec is:

```text
docs/codex/planning/novel-factory-v5.8-workflow-observability-recovery-spec.md
```

The next candidate planning line is:

```text
docs/codex/planning/novel-factory-v5.9-writing-skills-prompt-template-spec.md
```

Pi-inspired Agent engineering direction:

```text
docs/codex/next/pi-inspired-agent-engineering-roadmap.md
```

Later candidate lines remain useful, but should wait until workflow observability and writing skills are stable:

- `Creator Knowledge Base / RAG`
- `Export and Publishing Pipeline`
- `Advanced Evaluation and AgentOps Replay`
