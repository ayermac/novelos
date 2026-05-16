# v6.4.5 Real LLM Quality Acceptance Report

## Verdict

**PASS WITH REAL-LLM SKIP**

v6.4.5 delivered a repeatable real-LLM quality acceptance harness. The current execution environment has no configured real LLM API key, so the real run is correctly reported as `skipped`. The same harness was validated in stub mode to prove the project seeding, workflow execution, and `QualityHub.diagnose()` report path.

## Scope

v6.4.5 does not change chapter generation behavior. It adds an acceptance harness and tests so future real-model checks use the same scenario and output schema.

## Files

| File | Change |
|---|---|
| `scripts/verify_v64_real_llm.py` | New Python harness for optional real-LLM acceptance |
| `scripts/verify_v64_real_llm.sh` | New shell wrapper with env-based options |
| `tests/test_v645_real_llm_acceptance.py` | New tests for real-mode SKIP and stub-mode harness execution |
| `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md` | v6.4.5 status and scope |

## Acceptance Scenario

The harness creates an isolated project:

- Genre: urban mystery
- Title: `雨巷里的旧钟`
- Planned chapters: 3
- Target chapter: 1
- Context: approved genesis, world setting, protagonist, supporting character, chapter outline, and active writing instruction

It then runs one chapter through the existing workflow and diagnoses the generated chapter with `QualityHub.diagnose()`.

## Report Shape

The JSON report contains:

- `run`: workflow status, error, and step list
- `chapter`: title, status, word count, and content presence
- `acceptance`: heuristic pass/fail checks
- `diagnosis`: overall score, dimensions, metrics, and finding counts

The report intentionally excludes full chapter text.

## Current Local Results

| Command | Result |
|---|---|
| `python3 scripts/verify_v64_real_llm.py --mode real` | `skipped` because no real API key is configured |
| `python3 scripts/verify_v64_real_llm.py --mode stub` | `passed` |
| `python3 -m pytest tests/test_v645_real_llm_acceptance.py -q` | `2 passed` |

## Real LLM Re-run

Use one of:

```bash
OPENAI_API_KEY=... MODE=real OUTPUT=/tmp/v645-real.json bash scripts/verify_v64_real_llm.sh
CONFIG_PATH=config/local.yaml MODE=real OUTPUT=/tmp/v645-real.json bash scripts/verify_v64_real_llm.sh
```

For harness-only verification:

```bash
MODE=stub OUTPUT=/tmp/v645-stub.json bash scripts/verify_v64_real_llm.sh
```

## Known Limits

- The acceptance checks are heuristic and advisory, not release-blocking CI gates.
- Real LLM results are not checked into the repository because they are provider-, model-, and prompt-temperature-dependent.
- The script verifies one controlled chapter; broader genre and multi-chapter acceptance should be part of v6.5+ quality work.
