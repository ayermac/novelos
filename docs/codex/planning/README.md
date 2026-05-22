# Planning Documents

This directory contains historical roadmap material and older implementation specs. It is intentionally retained for traceability, but it should not be treated as the default place for new v6.6+ work.

Important: this directory does not have one standalone file for every shipped version. Some shipped subversions are covered by umbrella specs, and newer v6.6+ specs live in `../specs/`. See `novel-factory-planning-coverage-audit.md` before assuming a planning document is missing.

## Use This Directory For

- Long-running roadmap history.
- Older version plans that predate the current `specs/` split.
- Architecture notes that are still useful as historical context.

## Current Convention

- Approved v6.6+ version specs go in `../specs/`.
- Proposed next work goes in `../next/`.
- Completion facts go in `../reports/`.
- Review findings go in `../reviews/`.

Key files:

- `novel-factory-roadmap.md` - historical version roadmap.
- `novel-factory-version-planning-index.md` - version-to-plan/report/review lookup table.
- `novel-factory-planning-coverage-audit.md` - audit of versions with reports/reviews but no standalone planning/spec file.
- `novel-factory-v5.8.1-real-llm-acceptance-spec.md` - retrospective spec for the real LLM acceptance pass.
- `novel-factory-v6.2-desktop-client-foundation-spec.md` - versioned entry point for the desktop client foundation work.
