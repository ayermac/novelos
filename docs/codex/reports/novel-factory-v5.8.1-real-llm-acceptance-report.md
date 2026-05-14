# v5.8.1 Real LLM Acceptance Report

Date: 2026-05-14

## Scope

This acceptance run simulated a human author starting a new novel from scratch with real-mode API configuration.

Acceptance project:

- Project ID: `real_acceptance_mist_echo_20260514`
- Title: `雾城回声`
- Genre: `悬疑科幻 / 都市奇谈`
- Mode: `real`

The project was deleted after the run to avoid leaving a stale `running` genesis record in the shared acceptance database.

## Flow Attempted

1. Start API in real mode with `config/local.yaml`.
2. Create a new project through `/api/onboarding/projects`.
3. Request project genesis generation through `/api/projects/{project_id}/genesis/generate`.
4. Poll `/genesis/latest` and `/production-next` while the real LLM call is running.
5. Attempt a minimal real LLM smoke call.

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

### Blocked: current real provider did not return in time

Even after the event-loop and token-cap fixes, real genesis still did not complete promptly. A separate minimal real LLM smoke call also exceeded 70 seconds and eventually entered timeout retry.

Conclusion:

- The current real provider configuration passes static validation, but the live call path is not reliable enough for full real-mode chapter acceptance.
- This run did not validate chapter generation quality, chapter workflow completion, or real-mode publication flow.

## Verification

Targeted regression:

```text
python3 -m pytest \
  tests/test_v51_api_e2e_smoke.py::TestAPIE2ESmoke::test_onboarding_create_project_with_serial_plan \
  tests/test_v532_project_genesis.py::test_real_genesis_generation_does_not_block_event_loop \
  tests/test_v5512_llm_runtime_reliability.py \
  -q

6 passed
```

## Next Actions

Before another real-mode creative acceptance run:

1. Add a live LLM smoke endpoint or CLI command that performs a tiny `max_tokens=32` completion and reports latency, provider, model, and classified failure reason.
2. Add user-visible cancel/timeout handling for long-running genesis jobs.
3. Consider making genesis a background job rather than a request/response API.
4. Re-run acceptance only after the configured provider returns a minimal smoke response within the expected timeout.

