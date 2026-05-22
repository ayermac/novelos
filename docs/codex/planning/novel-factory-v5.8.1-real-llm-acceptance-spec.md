# v5.8.1 Real LLM Acceptance Retrospective Spec

Status: retrospective planning note reconstructed from the accepted implementation and `../reports/novel-factory-v5.8.1-real-llm-acceptance-report.md`.

## Goal

Prove that a human-created project can run chapter production in real LLM mode without requiring approved Genesis, and close the runtime defects discovered during that acceptance run.

## Scope

- Real-mode API startup with `config/local.yaml`.
- Onboarding project creation with serial plan support.
- Manual project context readiness without approved Genesis.
- Real chapter generation from manual instruction.
- Workflow timeline polling while a real provider run is active.
- Real-mode stop at `awaiting_publish` instead of auto-publish.
- Provider/runtime failure handling for Genesis, Author, Editor, and MemoryCurator.

## Constraints

- Do not rewrite the workflow topology.
- Do not require users to approve Genesis when they have manually supplied enough context.
- Do not make real LLM failures look like successful generated content.
- Keep real LLM smoke small enough to be safe and cheap.

## Acceptance

1. A real-mode project can be created from onboarding.
2. `create_serial_plan=true` does not throw a repository contract error.
3. A project with manual world settings, character, outline, and chapter instruction can pass `production-next` with `manual_context_ready=true`.
4. `POST /api/run/chapter` in real mode can reach `reviewed`.
5. The real workflow stops at `awaiting_publish`.
6. `production-next` recommends review/publish after completion.
7. Genesis real LLM work does not block unrelated status APIs.
8. Genesis uses a bounded JSON token budget.
9. Author real mode can prefer plain prose when structured JSON is brittle.
10. Editor timeout degrades to rule-based review instead of blocking the workflow.
11. MemoryCurator timeout degrades to no-op memory extraction instead of breaking graph routing.

## Delivered Fixes

- Fixed onboarding serial-plan repository call.
- Offloaded real Genesis provider calls to avoid blocking the API event loop.
- Added bounded `max_tokens` support for JSON provider calls.
- Added `novelos llm smoke`.
- Fixed API subcommand config argument precedence.
- Allowed manual context to bypass Genesis.
- Fixed failed planned-chapter retry behavior.
- Prioritized the running target workflow in `production-next`.
- Hardened JSON sanitizer for unquoted prose scalar values.
- Added Author prose-first real-mode generation.
- Respected explicit short word targets.
- Added compact Editor review and rule fallback on timeout.
- Added MemoryCurator timeout no-op degradation and defensive graph route.

## Verification Source

See `../reports/novel-factory-v5.8.1-real-llm-acceptance-report.md` for the exact targeted regression commands, full verification result, and live acceptance project summary.

## Follow-Up

- Real Genesis should be backgrounded and resumable.
- Memory extraction should gain a retry path after degraded no-op.
- Editor timeout fallback should remain observable to users.

