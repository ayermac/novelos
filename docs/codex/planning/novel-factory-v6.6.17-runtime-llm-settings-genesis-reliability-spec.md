# v6.6.17 Runtime LLM Settings & Genesis Reliability Spec

## Goal

Close the real-project runtime issues found after v6.6.16 by improving LLM configuration ergonomics, key handling, workflow recovery, MemoryCurator reliability, and Genesis long-payload behavior.

## Scope

### 1. LLM Settings And Key Management

- Add `request_timeout_seconds` to LLM profile editing.
- Remove template-level `max_tokens` from the user-facing LLM profile editor; output budget is handled by agent/runtime code instead of per-template UI.
- Separate API key environment-name selection from actual API key value storage.
- Allow LLM templates to select an existing API key environment name instead of re-entering key metadata for every profile.
- Hide unused built-in key presets that the user does not want surfaced.
- Fix template-name editing so typing does not lose focus after every character.
- Preserve secure-key behavior: desktop config must not return plaintext API keys.

### 2. Runtime And Workflow Recovery

- Improve blocked/revision recovery semantics so unsafe direct regeneration is not offered from states that require recovery.
- Clear stale run/task records when reset recovery is explicitly chosen.
- Avoid treating healthy running workflows as stale recovery targets.
- Preserve memory context audit when Planner is skipped by pre-existing chapter instructions.
- Route structural chapter defects back to Author when revision requires actual writing repair.
- Preserve editor feedback through state hydration and Author to Polisher handoff.

### 3. MemoryCurator Reliability

- Add fallback LLM support for MemoryCurator extraction.
- Keep no-fallback behavior compatible with previous runtime.
- Preserve request timeout settings in fallback routing metadata.
- Do not report degraded memory extraction as trusted success.

### 4. Genesis Recovery And Real Provider Semantics

- Mark stale running Genesis runs failed so users can retry.
- Let `production-next` recover stale Genesis instead of waiting forever.
- Poll active running Genesis state from the UI.
- Treat true provider connection failures as failures, not successful template/recovery content.
- Keep invalid/incomplete JSON repairable when enough local project context exists.

### 5. Genesis Segmented Generation

- Replace one oversized real Genesis request with bounded segment calls:
  - foundation: project updates and world settings
  - cast: characters and factions
  - plot: outlines and plot holes
  - instructions: chapter instruction chunks
- Keep per-call output budgets bounded.
- Merge segments deterministically.
- Preserve explicit failure when every provider call fails.

## Acceptance

- LLM settings can save `request_timeout_seconds` without exposing template-level `max_tokens`.
- API keys are managed separately from profile templates and plaintext keys do not leak through desktop config APIs.
- Unwanted built-in presets such as unused provider keys do not stay pinned in the UI.
- Editing a template name keeps focus while typing.
- Healthy running workflows and running Genesis jobs are shown as active, not stale failures.
- Stale Genesis runs can be recovered/retried.
- Provider connection failures return failed Genesis status and do not masquerade as generated content.
- Real Genesis generation uses multiple bounded calls instead of one large request.
- Targeted Genesis, secure-key, desktop runtime, and MemoryCurator fallback tests pass.

## Out Of Scope

- Full Author/Polisher/MemoryCurator segmented long-output migration; planned for v6.6.18.
- A new provider stack.
- New frontend IA beyond fixing the settings and Genesis runtime issues.
- Reintroducing retired sidecar agents.

## Verification Plan

Run:

```bash
python3 -m pytest tests/test_v532_project_genesis.py tests/test_v663_genesis_quality_gate.py tests/test_v65_desktop_runtime.py tests/test_v66_desktop_secure_keys.py -q
python3 -m pytest tests/test_v6617_memory_curator_fallback.py tests/test_v6618_genesis_stale_recovery.py -q
```

Frontend targeted checks:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Use full backend/frontend verification before declaring a new stable baseline.

