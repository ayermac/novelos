# v4.1 Style Gate & Style Evolution Specification

## Summary

v4.1 upgrades Style Bible from "checkable" to "governable": adds configurable Style Gate (off/warn/block), structured style revision advice, Style Bible version tracking, and human-confirmed style evolution proposals.

## Goals

1. **Style Gate**: Make Style Bible check results actionable in QualityHub — configurable off/warn/block mode per project.
2. **Style Revision Advice**: Generate structured, rule-based revision suggestions when style deviates.
3. **Style Bible Versioning**: Every Style Bible update saves a version snapshot for rollback and audit.
4. **Style Evolution Proposals**: Aggregate recurring style issues from quality reports into proposals, but require human approval and never auto-apply.

## Non-Goals

- No imitation of specific authors.
- No network access for style checking.
- No automatic rewriting of chapters.
- No auto-applying proposals to Style Bible (v4.1 only records decisions).
- No Web UI / FastAPI / Redis / Celery / PostgreSQL.
- No changes to main Agent orchestration order.
- No LLM calls in Style Gate or revision advice.
- Default configuration must not block existing flows.

## Safety / Copyright Policy

- No field may reference a specific living author.
- No auto-learning from copyrighted text.
- Proposals are advisory only — human must approve.
- Approve only records the decision; does not modify Style Bible.

## DB Schema

### Migration: `013_v4_1_style_gate_evolution.sql`

#### `style_bible_versions`

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID |
| project_id | TEXT NOT NULL | FK → projects |
| style_bible_id | TEXT NOT NULL | FK → style_bibles |
| version | TEXT NOT NULL | Semantic version |
| bible_json | TEXT NOT NULL | Snapshot of bible at this version |
| change_summary | TEXT | Human-readable change description |
| created_by | TEXT | Who made the change |
| created_at | TEXT | Timestamp |

#### `style_evolution_proposals`

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID |
| project_id | TEXT NOT NULL | FK → projects |
| proposal_type | TEXT NOT NULL | Enum: add_forbidden_expression, adjust_pacing, etc. |
| source | TEXT NOT NULL | Where the proposal came from |
| status | TEXT NOT NULL | pending/approved/rejected |
| proposal_json | TEXT NOT NULL | Structured proposal data |
| rationale | TEXT | Why this proposal was generated |
| created_at | TEXT | Timestamp |
| decided_at | TEXT | When the decision was made |
| decision_notes | TEXT | Human notes on the decision |

## Style Gate Config

Stored inside `style_bibles.bible_json` under key `gate_config`:

```python
class StyleGateConfig(BaseModel):
    enabled: bool = False           # Default: disabled
    mode: StyleGateMode = WARN      # off | warn | block
    blocking_threshold: int = 70    # Score below this triggers block
    max_blocking_issues: int = 0    # 0 = use blocking_threshold only
    revision_target: str = "polisher"  # author | polisher
    apply_stages: list[StyleGateStage]  # draft | polished | final_gate
```

**Default**: `enabled=False`, `mode=warn` — ensures existing flows are not disrupted.

## QualityHub Integration

### Logic per mode:

| Mode | Score < Threshold | Effect |
|------|------------------|--------|
| off | — | Record only, no warnings/blocking |
| warn | Add warning | Warnings added, pass not affected |
| block | Add blocking issue | Can fail the gate |

### Default behavior:
- No gate config → no gate applied → existing tests pass unchanged.

## Revision Advice

Module: `novel_factory/style_bible/advice.py`

Output: `revision_target`, `priority`, `issues`, `rewrite_guidance`, `forbidden_expression_fixes`, `preferred_expression_suggestions`, `paragraph_suggestions`, `sentence_suggestions`.

Does NOT call LLM. Does NOT auto-rewrite.

## Evolution Proposal

Module: `novel_factory/style_bible/evolution.py`

Logic: Read recent quality reports → aggregate recurring issues → generate proposals → save as pending.

**Critical**: Proposals are never auto-applied. `approve` only updates the proposal status.

## CLI Design

```bash
novelos style gate --project-id demo --json
novelos style gate-set --project-id demo --mode block --threshold 75 --revision-target polisher --json
novelos style versions --project-id demo --json
novelos style version-show --version-id <id> --json
novelos style propose --project-id demo --json
novelos style proposals --project-id demo --json
novelos style proposal-show --proposal-id <id> --json
novelos style proposal-decide --proposal-id <id> --decision approve --notes "..." --json
```

## Acceptance Criteria

1. Default config does not block existing flows.
2. mode=block can actually block when score < threshold.
3. Proposals are never auto-applied to Style Bible.
4. Style Bible version snapshots are created on every update.
5. Version snapshots contain the OLD bible data (pre-update).
6. CLI error paths return stable envelope without traceback.
7. No author imitation fields anywhere.
8. All files <= 1000 lines.
9. Full test suite passes.
10. Migration 013 is idempotent.
