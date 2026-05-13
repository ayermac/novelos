# v5.6.1 Workbench Stabilization Review

## Scope

This review validates the v5.6.1 stabilization goals:

- Navigation stability (module switching, chapter context preservation, sidebar collapse/expand)
- Chapter overflow menu correctness (target chapter, conditional actions, no mis-clicks)
- Writing area clarity (content isolation, workflow containment, human-readable artifacts)
- Workflow refresh & recovery (auto-refresh, stuck-run detection, contradiction warning)
- Dialog & error feedback (no native browser dialogs, inline confirmations, visible errors)
- Visual stability (no color-only patches, three-layer hierarchy, no text clipping)

## Review Checklist

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| 1 | `/projects/:id` defaults to author workbench | Pass | `activeModule` defaults to `chapters` in `ProjectDetail.tsx` |
| 2 | Module switching preserves `chapter` query param | Pass | `buildProjectModuleSearchParams` retains `chapter` for non-workbench modules |
| 3 | "工作台" routes to overview, "写章节" returns to workbench | Pass | `overview` module renders `ProjectOverviewModule`; `chapters` renders `AuthorWorkbench` |
| 4 | Chapter overflow menu does not switch chapter on open | Pass | `stopPropagation` on menu button click; `div role="button"` for chapter row |
| 5 | Menu actions target the clicked chapter | Pass | `ChapterMenu` receives the specific `chapter` object and calls `onGenerateChapter(chapter.chapter_number)` etc. |
| 6 | `blocking` menu shows reset, not generate | Pass | Test: `blocking chapter menu shows reset recovery and not generate` |
| 7 | `revision` menu shows reset + continue generate | Pass | Test: `revision chapter menu shows reset recovery and continue generate` |
| 8 | `published` menu shows generate-next, not regenerate | Pass | Test: `published chapter menu shows generate-next and not generate` |
| 9 | `reviewed + real` menu shows publish, not generate | Pass | Test: `reviewed + real mode menu shows confirm publish` |
| 10 | Content tab does not display workflow timeline | Pass | `activeTab === 'content'` renders `ContentBody` only |
| 11 | Artifacts use human-readable labels | Pass | `getArtifactTitle` maps `screenwriter→分场大纲`, `author→正文初稿`, etc.; `formatArtifactSummary` normalizes raw tokens |
| 12 | Workflow auto-refreshes when on workflow tab | Pass | `useEffect` polling at 5s interval when `activeTab === 'workflow'` and status is `running` |
| 13 | Stale run (>30 min) shows "疑似卡住" with recovery | Pass | `isStaleRunning` triggers warning headline and "标记为阻塞" button |
| 14 | Terminal chapter with running workflow warns contradiction | Pass | `isContradictory` detects `published`/`reviewed`/`awaiting_publish` + `running` + not stale |
| 15 | No native `confirm`/`alert`/`prompt` in workbench | Pass | `useAppDialog` used for all confirmations; grep finds zero matches for `window.confirm`/`alert`/`prompt` |
| 16 | POST actions have pending state and disable duplicates | Pass | `generating` state disables buttons; SSE `isStreaming` shows spinners |

## Findings

### Round 1 — Missing reset action in chapter menu for blocking/revision

The chapter overflow menu did not expose the "清除阻塞并重置" action for `blocking` or `revision` chapters. Users had to first select the chapter, switch to the workflow tab, and then click the reset button in the workflow body.

Impact:

- Inefficient for projects with multiple blocked chapters.
- Menu completeness did not match the workflow body action set.

Fix:

- Added `onResetRunRecoveryForChapter` prop chain from `ProjectDetail` → `AuthorWorkbench` → `AuthorChapterRail` → `ChapterMenu`.
- `ChapterMenu` now shows "清除阻塞并重置" for `blocking` and `revision` statuses.
- `ProjectDetail.handleResetRunRecoveryForChapter` finds the latest running/blocked run for the target chapter and invokes the existing `handleResetRunRecovery` with a dialog confirmation.

### Round 2 — Terminal chapter with lingering running workflow showed normal progress

If a chapter reached a terminal state (`published`, `reviewed`, `awaiting_publish`) but still had a `running` workflow (e.g., due to a race condition or manual state edit), the UI showed "工作流正在推进" as if everything were normal.

Impact:

- Users might wait for a workflow that should not be running.
- No guidance to clean up the inconsistent state.

Fix:

- `WorkflowBody` now checks `isContradictory = isTerminalChapter && isRunning && !isStaleRunning`.
- When contradictory, the alert shows "状态矛盾：终态章节仍有运行中工作流" and explains that the state is out of sync, recommending mark-stuck + reset.

## Fix Verification

Verified behavior:

- `novel_3v2o` Chapter 3 (`published`) overflow menu shows "生成下一章", not "生成本章".
- A simulated `blocking` Chapter 5 overflow menu shows "清除阻塞并重置", not generate.
- A simulated `revision` Chapter 5 overflow menu shows both "继续生成" and "清除阻塞并重置".
- A simulated `published` + `running` workflow shows the contradiction warning instead of "工作流正在推进".
- All workbench confirmations use the inline dialog system; no native browser dialogs.

## Outcome

Review passed. v5.6.1 is accepted as the current stable web UI baseline. The author workbench is ready to support v5.7 in-chapter editing and version management.
