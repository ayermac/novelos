# v5.6.1 Workbench Stabilization Completion Report

## Summary

v5.6.1 stabilizes the personal author workbench introduced in v5.6. No large UI rewrites, no multi-tenant features, and no v5.7 editing capabilities were introduced. The focus is on making real usage paths reliable: navigation, chapter context preservation, overflow menu targeting, workflow refresh, stuck-run recovery, loading states, inline dialogs, and human-readable artifact labels.

## Changes

### Frontend

| File | Change |
| --- | --- |
| `frontend/src/components/project/AuthorChapterRail.tsx` | Added `onResetRunRecoveryForChapter` prop; `ChapterMenu` now shows "清除阻塞并重置" for `blocking`/`revision` chapters; `blocking` no longer shows generate actions |
| `frontend/src/components/project/AuthorWorkbench.tsx` | Added `onResetRunRecoveryForChapter` prop forwarding to `AuthorChapterRail`; **Fix: also forwards `publishPending`/`markStuckPending`/`resetRecoveryPending` to `AuthorAgentPanel`** |
| `frontend/src/pages/ProjectDetail.tsx` | Added `handleResetRunRecoveryForChapter` — finds the latest **run for a chapter (any status)** and resets it via dialog confirmation; **Fix: added `try/catch/finally` to publish/mark-stuck/reset handlers to prevent stuck pending states on exceptions** |
| `frontend/src/components/project/AuthorWritingSurface.tsx` | `WorkflowBody` now detects contradictory state when a terminal chapter (`published`/`reviewed`/`awaiting_publish`) still has a `running` workflow; **Fix: contradiction now takes priority over stale running, and recovery buttons show pending spinners** |
| `frontend/src/components/project/AuthorAgentPanel.tsx` | Publish and recovery buttons now show spinners and are disabled while pending |
| `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx` | Added 8 tests total: blocking menu reset, revision menu reset+generate, menu reset targets clicked chapter, contradictory terminal+running warning, **contradiction priority over stale, agent panel publish pending, agent panel recovery pending** |

### Behavior Changes

1. **Chapter overflow menu correctness**
   - `blocking`: shows "清除阻塞并重置" only; no generate action.
   - `revision`: shows both "清除阻塞并重置" and "继续生成".
   - `planned/scripted/drafted/polished`: shows generate action.
   - `reviewed + real`: shows "确认发布".
   - `published`: shows "生成下一章".
   - `running workflow`: shows "已有运行中工作流" hint.

2. **Contradictory workflow state warning**
   - If a terminal-status chapter has a `running` workflow, the workflow tab warns: "状态矛盾：终态章节仍有运行中工作流" and guides the user to mark stuck and reset.
   - **Fix**: Contradiction now takes priority over stale-running; even if the workflow has been running for >30 min, the contradiction headline is shown.

3. **Recovery via chapter menu**
   - Users can now reset a blocked/revision chapter directly from the chapter rail overflow menu, without needing to first select that chapter.
   - **Fix**: The handler now finds the latest run for the chapter regardless of run status, so completed review runs that left the chapter in `revision` can also be reset.

4. **Pending state safety**
   - Publish, mark-stuck, and reset-recovery POST actions now have `try/catch/finally` protection, ensuring the pending flag is always cleared even if the network request or follow-up refresh throws.

5. **AI agent panel pending spinners**
   - The right-side AI assistant panel now shows spinner text and disables buttons during publish, mark-stuck, and reset-recovery operations, matching the writing surface behavior.

## Real Project Acceptance: `novel_3v2o`

| Acceptance Item | Result |
| --- | --- |
| `/projects/novel_3v2o` defaults to author workbench | Pass |
| `/projects/novel_3v2o?chapter=4&view=workflow` keeps chapter 4 selected | Pass |
| "工作台" menu routes to project overview | Pass |
| "写章节" menu returns to chapter workbench | Pass |
| Switching to "大纲篇章"/"伏笔"/"事实账本"/"风格规范" preserves `chapter=4` | Pass |
| Returning to "写章节" restores chapter 4 | Pass |
| Chapter overflow menu opens without switching chapter | Pass |
| Menu actions target the clicked chapter, not the current selection | Pass |
| Content tab shows only text/empty state; no workflow timeline | Pass |
| Workflow tab shows node progress, run status, recovery actions | Pass |
| Artifacts tab shows human-readable labels (分场大纲/正文初稿/润色稿/审稿意见) | Pass |
| No raw artifact keys like `scene_plan (screenwriter)` exposed as primary labels | Pass |
| Workflow auto-refreshes while on workflow tab | Pass |
| Stale run (>30 min) shows "疑似卡住" with recovery buttons | Pass |
| Terminal chapter with running workflow shows contradiction warning | Pass |
| No `window.confirm`/`window.alert`/`window.prompt` in workbench flows | Pass |
| POST actions show pending state and disable duplicate clicks | Pass |

## Test Baseline

- pytest: 1847/1847 passed
- vitest: 115/115 passed
- frontend typecheck: passed
- frontend lint: passed
- frontend production build: passed

## Commits

- `4f1e05b`: 基线 — "工作台"菜单路由到项目 overview
- `b787cfa` 至 `c76ac75`: 后续修复（弹窗、产物标签、导航、侧边栏）
- v5.6.1 稳定化提交（本报告）:
  - `fix(v5.6.1): stabilize author workbench flows`
  - `fix(v5.6.1): add pending states to publish, mark-stuck and reset-recovery actions`
  - `fix(v5.6.1): review fixes — pending props, exception safety, contradiction priority, menu run lookup`

## Conclusion

v5.6.1 passes all acceptance paths on `novel_3v2o`. The author workbench is now stable enough to serve as the foundation for v5.7 (in-chapter editing, save, version comparison, and localized revision).
