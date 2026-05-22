# Novelos Documentation Information Architecture Plan

Status: proposed cleanup plan.

## Goal

Make `docs/` usable as a working knowledge base instead of a long historical pile, without breaking traceability for older version documents.

## Current Problems

1. `docs/codex/planning/` contains both evergreen architecture notes and dozens of old version specs.
2. Several shipped versions have reports/reviews but no standalone planning/spec file because they are covered by umbrella specs (`v6.4.x`, `v6.5.x`) or by differently named plans (`v6.2`).
3. v6.6+ specs are split between `planning/` and `specs/`, so the current convention is not obvious.
4. `docs/codex/README.md` has grown into a long version ledger and key-link dump, making the true current baseline hard to scan.
5. Local agent scratch plans previously appeared under `docs/superpowers/`, even though release tests require that path to stay out of git.
6. There is no per-directory README explaining where a new document should go.

## Cleanup Already Applied

- Added `docs/README.md` as the repository documentation entrance.
- Added README files under `docs/codex/{planning,specs,reports,reviews,next,release}`.
- Promoted the v6.6.18 segmented-agent plan from local scratch space to `docs/codex/next/`.
- Updated `docs/codex/README.md` to reflect v6.6.17 and the v6.6.18 candidate plan.
- Added `docs/codex/planning/novel-factory-planning-coverage-audit.md` to record versions with reports/reviews but no standalone planning/spec file.
- Added `docs/codex/planning/novel-factory-version-planning-index.md` as the version-to-plan/report/review lookup table.
- Added retrospective/versioned planning entries for v5.8.1 and v6.2.
- Added v6.6.17 spec and completion report.

## Proposed Follow-Up Work

### Phase 1: Make Current Truth Easy To Find

- Create `docs/codex/current.md` with:
  - runtime version
  - stable baseline
  - active candidate version
  - required verification commands
  - links to current spec/report/review
- Trim `docs/codex/README.md` so it points to `current.md`, directory READMEs, roadmap, and release docs instead of listing every historical report inline.

### Phase 2: Split Historical Version Index From Main README

- Create `docs/codex/history.md`.
- Move the long version report/review/spec link list from `docs/codex/README.md` into `history.md`.
- Keep `docs/codex/planning/novel-factory-roadmap.md` as the deep historical roadmap, not the everyday entry point.
- Include planning coverage columns in `history.md`: planning/spec source, report, review, and umbrella coverage. Use `planning/novel-factory-version-planning-index.md` as the source.

### Phase 3: Normalize Version Spec Placement

- Leave old specs in `planning/` to avoid massive link churn.
- For v6.6+ and later:
  - approved specs live in `docs/codex/specs/`
  - exploratory plans live in `docs/codex/next/`
  - completion facts live in `docs/codex/reports/`
  - reviews live in `docs/codex/reviews/`
- Add a lightweight index file in `specs/` listing v6.6+ specs by version.
- For v6.4.x and v6.5.x, either keep umbrella coverage with explicit index entries or add short retrospective spec notes only where future maintenance needs them.

### Phase 4: Add Documentation Hygiene Checks

- Add a test that verifies:
  - `docs/superpowers/` is not tracked
  - every new docs subdirectory has a README
  - every v6.6+ report references either a spec or an explicit reason why no spec exists
- Keep the check advisory or targeted first to avoid blocking unrelated development.

## Acceptance

- A new contributor can find the current baseline from `docs/README.md` in two clicks.
- A future Agent can tell where to place a plan, spec, report, and review without reading old release docs.
- `git status --short docs` does not show local scratch directories after moving project-relevant plans into `docs/codex/next/`.
- Existing historical links remain valid.
