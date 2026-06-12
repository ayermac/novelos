# Novel Factory v6.10.6 Genesis Hardening Plan

Status: implementation plan  
Branch: `feature/v6.10.6-genesis-hardening`  
Date: 2026-06-11

## Problem

Genesis can produce strong worldbuilding, cast, factions, outlines, and foreshadowing while still failing approval because chapter instructions are too abstract. The observed blocker is `SHALLOW_INSTRUCTION`: multiple chapter instructions lack concrete character, location, action chain, or result/state change.

This is not primarily a model-quality issue. The system currently has a contract mismatch:

- The quality gate expects executable chapter instructions with concrete character, location, action, and result signals.
- The segmented Genesis `instructions` prompt only asks for `objective/key_events` in broad language.
- The existing Genesis repair step only fills missing sections; it does not repair quality failures such as shallow instructions.
- The UI fallback is "regenerate or manually fill", which causes repeated full regeneration rather than targeted correction.

## Root Cause

v6.6.4 introduced strict Genesis depth checks. Later segmented generation reduced payload size but weakened the `instructions` prompt. The strong full-draft instruction contract was not fully carried into the per-segment prompt. As a result, generation and validation no longer share the same contract.

## Goals

1. Restore a strict instruction-generation contract inside segmented Genesis.
2. Make chapter instructions executable enough for downstream authoring, not just approval.
3. Add a targeted LLM repair loop for instruction-quality failures.
4. Keep storage/API backward compatible with existing `instructions` table fields.
5. Recover from Genesis LLM timeout without discarding completed sections.
6. Avoid weakening quality gates to hide the problem.

## Non-Goals

- Do not remove `SHALLOW_INSTRUCTION` or lower Genesis quality standards.
- Do not require a database migration for v6.10.6.
- Do not redesign the full Genesis UI in this patch.
- Do not make Story Contract governance responsible for Genesis instruction depth.

## Scope

### Backend

- Strengthen `_build_genesis_segment_prompt(..., segment="instructions")` to require a structured Chapter Instruction Contract:
  - `chapter_number`
  - `objective`
  - `protagonist`
  - `primary_location`
  - `opposing_force`
  - `action_chain` with at least 3 concrete actions
  - `visible_result`
  - `state_change`
  - `key_events`
  - `emotion_tone`
  - `ending_hook`
  - `continuity_seed`
  - `word_target`
- Preserve extra structured fields in draft JSON.
- Serialize structured fields into `key_events` on approval so existing chapter-writing context can consume them without schema changes.
- Update the Genesis quality gate to read structured fields before falling back to regex heuristics over `objective/key_events`.
- Add quality repair after real LLM generation:
  - Evaluate draft quality.
  - If repairable instruction blockers exist, ask LLM to return only revised `instructions`.
  - Merge repaired instructions into the existing draft and re-evaluate.
  - Keep original world/cast/factions/outlines/plot holes unchanged.
- Add timeout recovery for segmented generation:
  - If a Genesis segment times out, preserve completed LLM sections.
  - Fill missing sections from local editable recovery content.
  - Keep pure connection failures as failures instead of silently masquerading as successful LLM output.

### Frontend

- v6.10.6 does not require a new UI surface, but quality issue wording should remain compatible with current `GenesisModule`.
- A future version can expose a dedicated "只修章节指令" button if manual control is needed.

### Tests

- Prompt contains required structured instruction fields and anti-abstract rules.
- Old shallow instructions still fail.
- Structured concrete instructions pass depth checks without relying on brittle regex alone.
- Targeted repair merges only `instructions` and preserves other Genesis sections.
- Repair is attempted only for instruction-quality failures, not scaffold or unrelated blockers.
- Segment timeout recovery preserves completed sections and returns a reviewable local recovery draft.

## Acceptance Criteria

- A Genesis draft like "第5章在月度实战考核中打破F班必败定律" is no longer considered sufficient unless it also includes a concrete scene/location/action/result contract.
- A structured instruction with concrete protagonist, location, opposing force, action chain, result, and continuity seed passes `SHALLOW_INSTRUCTION`.
- A real-mode draft blocked only by shallow instructions receives a targeted instruction repair attempt before being returned for review.
- If targeted repair fails, the draft remains blocked with the original quality report; generation should not crash.
- If an LLM segment times out after earlier segments succeeded, the generated draft keeps the successful sections and locally fills the missing sections.
- Existing approval and instruction-table persistence remain backward compatible.

## Risks

- Stronger prompts increase token usage in the instructions segment.
- Some providers may ignore extra fields; the quality repair loop mitigates but cannot guarantee success.
- Without a UI edit surface, users still need full regenerate or manual instruction module editing when all repair attempts fail.

## Follow-Up

- Add a frontend "修复章节指令" action for already generated blocked Genesis drafts.
- Consider a database field for structured instruction metadata if chapter authoring benefits from non-flattened action chains.
- Surface a compact Genesis Doctor explaining which section failed and why.
