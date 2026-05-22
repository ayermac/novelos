# Novel Factory Planning Coverage Audit

Status: documentation audit; remediated by `novel-factory-version-planning-index.md`, retrospective specs, and versioned planning aliases for v6.4.x/v6.5.x.

## Purpose

This file records which shipped/reviewed versions have an obvious planning or spec source. It exists because `planning/` is not only "large"; it is also uneven: some versions have standalone planning files, while others are covered only by umbrella plans or by later `specs/` files.

## Coverage Rule

A version is considered planned if either of these exists:

- a matching file under `docs/codex/planning/`
- a matching file under `docs/codex/specs/`

Reports and reviews are not counted as planning sources.

## Findings

Before this cleanup, the following versions had a report or review but did not have a matching standalone planning/spec file:

| Version | Existing evidence | Planning coverage | Assessment |
| --- | --- | --- | --- |
| v5.8.1 | report | `planning/novel-factory-v5.8.1-real-llm-acceptance-spec.md` | Remediated with a retrospective spec. |
| v6.2 | report + review | `planning/novel-factory-v6.2-desktop-client-foundation-spec.md` and `planning/novel-factory-cross-platform-desktop-client-plan.md` | Remediated with a versioned planning alias. |
| v6.4.0 | report + review | `planning/novel-factory-v6.4.0-quality-diagnosis-baseline-spec.md` and umbrella v6.4 spec | Remediated with a versioned alias. |
| v6.4.1 | report + review | `planning/novel-factory-v6.4.1-author-drafting-contract-spec.md` and umbrella v6.4 spec | Remediated with a versioned alias. |
| v6.4.2 | report + review | `planning/novel-factory-v6.4.2-dialogue-scene-texture-spec.md` and umbrella v6.4 spec | Remediated with a versioned alias. |
| v6.4.3 | report + review | `planning/novel-factory-v6.4.3-antiai-skills-spec.md` and umbrella v6.4 spec | Remediated with a versioned alias. |
| v6.4.4 | report + review | `planning/novel-factory-v6.4.4-editor-quality-gates-spec.md` and umbrella v6.4 spec | Remediated with a versioned alias. |
| v6.4.5 | report + review | `planning/novel-factory-v6.4.5-real-llm-acceptance-spec.md` and umbrella v6.4 spec | Remediated with a versioned alias. |
| v6.4.6 | report + review | `planning/novel-factory-v6.4.6-chapter-quality-closure-spec.md` and umbrella v6.4 spec | Remediated with a versioned alias. |
| v6.5.1 | report + review | `planning/novel-factory-v6.5.1-interaction-primitives-spec.md` and umbrella v6.5 spec | Remediated with a versioned alias. |
| v6.5.2 | report + review | `planning/novel-factory-v6.5.2-project-overview-workbench-spec.md` and umbrella v6.5 spec | Remediated with a versioned alias. |
| v6.5.3 | report + review | `planning/novel-factory-v6.5.3-chapter-writing-surface-spec.md` and umbrella v6.5 spec | Remediated with a versioned alias. |
| v6.5.4 | report + review | `planning/novel-factory-v6.5.4-agent-process-narrative-spec.md` and umbrella v6.5 spec | Remediated with a versioned alias. |
| v6.5.5 | report + review | `planning/novel-factory-v6.5.5-settings-desktop-runtime-polish-spec.md` and umbrella v6.5 spec | Remediated with a versioned alias. |
| v6.5.6 | report + review | `planning/novel-factory-v6.5.6-interaction-excellence-closure-spec.md` and umbrella v6.5 spec | Remediated with a versioned alias. |
| v6.5.7 | report + review | `planning/novel-factory-v6.5.7-visual-polish-pass-spec.md` and umbrella v6.5 spec | Remediated with a versioned alias. |

## Actual Problem

The main gap was not that every listed version lacked planning context. The problem was discoverability:

- v6.4.x and v6.5.x subversions were implemented as sections inside umbrella specs.
- v6.2 was inside the desktop client plan, whose filename did not mention the version.
- v5.8.1 was a real-LLM acceptance/hotfix run with no standalone planning artifact.
- v6.6+ moved newer specs into `docs/codex/specs/`, while older version specs remain in `planning/`.

## Recommended Fix

1. Keep existing files where they are; do not move old documents only to make names symmetrical.
2. Maintain `novel-factory-version-planning-index.md` as the version-to-source lookup table.
3. For umbrella specs, list the covered subversions explicitly.
4. For acceptance/hotfix versions without a plan, add a short "retrospective planning note" only when it helps future maintenance.
5. For future versions, require one of:
   - approved spec in `docs/codex/specs/`
   - explicit entry in the planning coverage index explaining why no standalone spec exists
