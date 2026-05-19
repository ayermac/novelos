# v6.6.8 Editor Refactor & Review Semantics Closure — Spec

## Problem

Editor's `_execute()` was a monolithic 530-line method mixing LLM calls, quality diagnosis, strategy decisions, artifact persistence, and state transitions. Review semantics (advisory/priority/blocking/death penalty) were determined ad-hoc, creating latent risks:
- High-score advisory-only reviews could auto-revise (deadloop)
- Quality diagnosis score could implicitly replace review score
- `revision_target` could be empty for revision decisions
- Retry/max-retries routing lacked a single decision point

## Goals

1. Refactor Editor into clear pipeline steps with typed data classes
2. Establish a single policy decision point (`classify_editor_result`)
3. Unify review score and quality diagnosis semantics
4. Ensure advisory-only never triggers auto revision
5. All rules testable via pure functions

## Design

### A. Pipeline Steps

`_execute()` now calls 7 steps in order:

1. `_load_editor_inputs(state) -> EditorInputs`
2. `_call_editor_llm(inputs, state) -> (EditorOutput, exec_events)`
3. `_run_quality_diagnosis(inputs, output) -> QualityDiagnosisResult`
4. `_run_chapter_seam_check(inputs, output) -> SeamCheckResult`
5. `_apply_review_strategy(output, quality, seam, inputs) -> (EditorDecision, word_gate_details)`
6. `_persist_editor_artifacts(...)`
7. `_build_editor_state_updates(...)`

### B. EditorPolicyInput & classify_editor_result

```python
@dataclass
class EditorPolicyInput:
    score: float
    pass_: bool
    death_penalty: bool = False
    blocking_issue_count: int = 0
    priority_issue_count: int = 0
    advisory_issue_count: int = 0
    quality_priority_count: int = 0
    quality_advisory_count: int = 0
    seam_blocking_count: int = 0
    seam_advisory_count: int = 0
    retry_count: int = 0
    max_retries: int = 3
```

Classification rules:
1. death_penalty/blocking > 0 → `blocking`
2. retry_count >= max_retries → `human_review`
3. score >= 85, no blocking → `advisory` (decision_type=`advisory_pass`)
4. score 80-84, no priority → `advisory` (NOT auto revision)
5. score 80-84, priority > 0 → `revision`
6. score < 80 → `revision`
7. quality_advisory alone must NOT cause revision

### C. determine_revision_target

Rules:
- death penalty → `author`
- planner-level issues → `planner`
- author-level issues → `author`
- polisher-level issues → `polisher`
- seam blocking → `author`
- quality priority → `polisher`
- default → `polisher` (never empty)

### D. Artifact Observability

Artifacts now include:
- `_strategy_decision`: category, decision_type, reason, recommended_action
- `_seam_check`: passed, blocking_count, advisory_count
- `_quality_feedback`: priority/advisory findings

## Hard Constraints

- No new LangGraph nodes
- No deleted API fields
- Quality diagnosis score never replaces review score
- advisory-only never triggers auto revision
- death penalty / blocking must still hard-block
- score >= 85 + advisory only → pass
- score 80-84 + no priority → advisory pass (not revision)
- retry_count >= max_retries → human_review

## Testing

36 tests in `tests/test_v668_editor_semantics.py` covering:
- All 6 classification rules
- Revision target defaults
- count_issue_types heuristic
- Legacy backward compatibility
- 80-84 score boundary conditions
- Integration with EditorAgent
