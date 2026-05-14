# v5.8.1 Real LLM Acceptance Report

Date: 2026-05-14

## Scope

This acceptance run simulated a human author starting a new novel from scratch with real-mode API configuration and manually entered project context.

Acceptance project:

- Final project ID: `real_acceptance_mist_echo_noop_memory_20260514`
- Title: `雾城回声`
- Genre: `悬疑科幻`
- Mode: `real`

Final result:

- Chapter 1 generated with live LLMs.
- Workflow reached `reviewed`.
- Real mode stopped at `awaiting_publish`.
- `production-next` returned `review_chapter`.
- Timeline displayed completed nodes from `health_check` through `awaiting_publish`.

## Flow Attempted

1. Start API in real mode with `config/local.yaml`.
2. Create a new project through `/api/onboarding/projects`.
3. Add a manual chapter instruction with explicit `word_target=400`.
4. Confirm `/production-next` can proceed via `manual_context_ready=true` without approved genesis.
5. Run `POST /api/run/chapter` with `llm_mode=real`.
6. Poll `/workflow-timeline` while the real workflow runs.
7. Confirm `/production-next` recommends review/publish after completion.

## Findings

### Fixed: onboarding serial-plan creation returned 500

Creating a project with `create_serial_plan=true` failed because the onboarding route called `repo.create_serial_plan(total_chapters=...)`, but the repository API expects `name`, `start_chapter`, and `target_chapter`.

Resolution:

- `onboarding.py` now calls `repo.create_serial_plan(...)` with the repository contract.
- Added an API smoke regression for onboarding with serial-plan creation.

### Fixed: real genesis blocked the API event loop

The real genesis route was declared `async`, but called the synchronous LLM provider directly. During a long provider call, unrelated APIs such as `genesis/latest` and `production-next` timed out.

Resolution:

- `_generate_real_draft(...)` now offloads the blocking provider call through `asyncio.to_thread(...)`.
- Added a regression test proving the event loop remains responsive while a blocking provider call is running.

### Fixed: genesis inherited oversized max_tokens

`config/local.yaml` uses large profile-level token limits for long-form chapter generation. Genesis only needs a bounded JSON planning object, but inherited the same high ceiling.

Resolution:

- `LLMProvider.invoke_json(...)` now accepts `max_tokens`.
- `OpenAICompatibleProvider.invoke_json(...)` passes `max_tokens` through to the model call.
- `StubProvider.invoke_json(...)` accepts the same argument for interface compatibility.
- Genesis now caps JSON output at `max_tokens=5000`.

### Fixed: live LLM smoke command added

`novelos llm smoke` now performs a tiny routed live completion and reports provider/model/latency/error classification.

Observed live smoke:

- `GLM-5.1`: returned empty output in smoke.
- `DeepSeek-V3.2`: returned `OK` quickly and completed author short-form prose.
- `Kimi-K2.6`: usable for routing but slow for editor review under the current endpoint.

### Fixed: API command dropped global config arguments

`novelos --config config/local.yaml --llm-mode real api ...` previously started the API with default config because API subcommand defaults overwrote global parser values. This made the service silently use `gpt-4o-mini`.

Resolution:

- API subcommand now uses independent `api_config`, `api_db_path`, and `api_llm_mode` destinations.
- `cmd_api` resolves API-specific values first, then global values.
- Added parser regressions for both global-before-subcommand and subcommand-local forms.

### Fixed: manual context can bypass genesis

For human-created projects, approved genesis is no longer mandatory when the author has already provided enough context.

The following are now sufficient for chapter generation:

- world settings
- at least one character
- outline
- current chapter instruction
- aligned title contract

`production-next` reports `manual_context_ready=true` and returns `generate_chapter`.

### Fixed: planned chapters can retry after failed runs

A failed run on a still-`planned` chapter no longer forces `recover_blocked_run`. Failed/blocked runs are treated as stuck only when chapter status is `blocking` or `revision`.

### Fixed: running target workflow has priority

When the current target chapter has a non-stale running workflow, `production-next` now returns `view_running_workflow` instead of misclassifying it as a blocked recovery action.

### Fixed: real JSON sanitizer handles unquoted prose values

DeepSeek sometimes emitted almost-valid JSON such as unquoted Chinese prose scalar values in screenwriter output. The JSON sanitizer now wraps those values before parsing.

### Fixed: Author long-form JSON fragility

Real author generation repeatedly produced usable prose wrapped in incomplete/invalid JSON or Markdown fences. The author node now uses prose-first generation for live OpenAI-compatible providers and derives metadata deterministically.

Final live result:

- `screenwriter`: 28s
- `author`: 29s
- author artifact: `draft`

### Fixed: explicit short word targets were ignored

`derive_word_target(...)` forced even explicit instruction targets below 2000 up to 2000. This broke short-form acceptance and short creative tests.

Resolution:

- Explicit instruction `word_target` is respected with a low safety floor of 300.
- Project-derived targets still keep the web-serial minimum of 2000.

### Fixed: Editor review timeout blocks

Editor review could exceed the provider timeout and block the workflow. Real-mode editor now uses compact review context with a bounded token budget and falls back to rule-based review when structured LLM review times out or returns invalid JSON.

Final live result:

- `editor`: completed
- review artifact: `review`
- chapter advanced to `reviewed`

### Fixed: MemoryCurator timeout broke graph routing

MemoryCurator timeout previously returned `requires_human`, but the graph route after `memory_curator` did not include `human_review`, producing `KeyError: human_review`.

Resolution:

- MemoryCurator LLM timeout / JSON failure degrades to no-op memory extraction.
- Graph includes a defensive `human_review` branch after memory curator.
- Final live workflow reached `awaiting_publish` instead of blocking.

## Verification

Targeted regression:

```text
python3 -m pytest \
  tests/test_v3_1_cli.py::TestLLMCLICommands::test_api_command_preserves_global_config_and_llm_mode \
  tests/test_v3_1_cli.py::TestLLMCLICommands::test_api_command_accepts_subcommand_config_and_llm_mode \
  tests/test_agents.py::TestAuthorAgent::test_author_real_openai_provider_uses_plain_text_primary \
  tests/test_agents.py::TestEditorAgent::test_editor_real_mode_timeout_degrades_to_rule_review \
  tests/test_agents.py::TestMemoryCuratorAgent::test_memory_curator_timeout_degrades_to_noop \
  tests/test_v530_trusted_generation_chain.py::TestDeriveWordTarget::test_explicit_short_instruction_word_target_is_respected \
  tests/test_v530_trusted_generation_chain.py::TestDeriveWordTarget::test_project_derived_word_target_keeps_web_serial_minimum \
  -q

7 passed
```

Final full verification after cleanup and review:

```text
python3 scripts/verify.py full
pytest: 1892 passed
frontend typecheck: passed
frontend lint: passed
frontend build: passed
vitest: 130 passed
```

Live acceptance:

```text
Project: real_acceptance_mist_echo_noop_memory_20260514
POST /api/run/chapter
Result: workflow_status=completed, chapter_status=reviewed, awaiting_publish=true
production-next: review_chapter
```

The temporary `real_acceptance_mist_echo*` projects used during acceptance were deleted from the shared acceptance database after the run.

## Residual Risks

1. Editor still depends on live provider latency before fallback can engage.
2. Memory extraction is now non-blocking; users may need a later retry action for richer project memory updates.
3. Real genesis remains slower and should become a background job rather than blocking project creation.
