# Novelos v5.6 WebUI Author Workbench Rework Spec

## Status

- Type: executable planning spec
- Baseline: v5.5.15 Production Readiness Closure
- Previous stable commits:
  - `fb984df`: unified run guard, SSE guard, runner reviewed semantics, test cleanup
  - `c3db226`: v5.5.15 final baseline documentation
- Target: rebuild the project WebUI around a personal author workbench experience

## Goal

Rework the WebUI from a production-control-console feel into a daily-use personal writing workbench.

The author should be able to open one project, immediately see the current writing task, inspect or edit the current chapter, understand what the AI agents are doing, and take the next safe action without jumping across many modules.

## Non-Goals

- Do not add multi-tenant account management.
- Do not add role-based permissions.
- Do not redesign backend workflow semantics.
- Do not replace the v5.5.15 run guards.
- Do not introduce a large UI framework or component library.
- Do not make a marketing landing page.
- Do not build enterprise administration surfaces.

## Current Frontend Audit

### Existing Structure

Current project UI is centered on:

- `frontend/src/pages/ProjectDetail.tsx`
  - owns project workspace data fetching,
  - owns query params for `module`, `chapter`, `view`, and `auto_generate`,
  - loads chapter details,
  - starts SSE generation,
  - routes each project module.
- `frontend/src/components/project/ProjectShell.tsx`
  - wraps project header, project side nav, and project main content.
- `frontend/src/components/project/ProjectSideNav.tsx`
  - module navigation grouped as author tasks, novel settings, and system state.
- `frontend/src/components/project/ChapterWorkspace.tsx`
  - chapter three-column layout,
  - left chapter list,
  - center content/workflow/artifacts/history tabs,
  - right run detail sidebar.
- `frontend/src/components/project/ProjectOverviewModule.tsx`
  - production-next,
  - health summary,
  - auto-run controls,
  - active sessions,
  - stale/obsolete recovery actions.
- Additional modules:
  - genesis,
  - world settings,
  - characters,
  - factions,
  - outlines,
  - plot holes,
  - instructions,
  - memory updates,
  - fact ledger,
  - style guide,
  - review,
  - runs,
  - settings.

### What Should Be Kept

- Existing backend API contracts.
- `useApiQuery`, `useSSEStream`, and current `get` / `post` API helpers.
- Query param compatibility:
  - `module=chapters`
  - `chapter=N`
  - `view=content|workflow|artifacts|history`
  - `auto_generate=1`
- v5.5.15 behavior:
  - no duplicate generation while a workflow is running,
  - no generation entry for `reviewed`, `awaiting_publish`, or `published`,
  - `reviewed + real mode` means awaiting human publish,
  - obsolete session cleanup must not present reconnect as the primary CTA.
- Existing module components can remain reachable through secondary panels or module routes.

### Current UX Problems

1. The UI has too many navigation layers.
   The global app sidebar, project side nav, chapter nav, tabs, and right run panel compete for attention.

2. The author loop is split across modules.
   A writer must move between overview, chapters, review, memory, settings, and runs to answer simple questions like "what should I do next?" or "why can I not continue?"

3. The primary screen still feels like an operations console.
   Auto-run controls, session recovery, health items, and workflow internals dominate the first impression.

4. Chapter content is not the visual center.
   The current chapter exists inside a tabbed panel, while operational UI occupies similar or higher visual priority.

5. AI agent status is visible but not framed as author assistance.
   The right panel reports workflow state, recent runs, and artifacts, but it does not yet feel like an assistant panel focused on next action, quality, and recoverability.

6. CSS is scattered.
   A large `WorkspaceStyles` block inside `ProjectDetail.tsx` mixes layout, module styling, tabs, cards, chapter content, and responsive rules. This makes full UI iteration fragile.

## Product Model

The new project page should be:

```text
Author Workbench = Chapter Navigator + Writing Surface + Agent Panel
```

### Left: Chapter Navigator

Purpose: orient the author in the book.

Required:

- chapter list with status, title, word count, and running indicator,
- current chapter highlighted,
- quick access to blocked, reviewed, and published chapters,
- compact progress summary,
- no deep module list as the primary left rail.

Optional:

- filters for all, active, blocked, awaiting publish, published,
- collapsed project settings and reference links.

### Center: Writing Surface

Purpose: make the current chapter the main object.

Required:

- current chapter title and status,
- readable chapter content as the default state,
- empty state for planned chapters,
- generate, continue, publish, and reset actions only when valid,
- tabs or segmented controls for:
  - 正文,
  - 指令,
  - 分场/产物,
  - 审稿,
  - 历史.

The writing surface must not feel like a card inside another card. It should be the main full-height surface.

### Right: Agent Panel

Purpose: explain what the AI can do now and what just happened.

Required:

- next recommended action,
- active workflow status,
- node-level progress while streaming,
- latest run status,
- error/blocking reason,
- publish prompt for `reviewed + real mode`,
- health issues that affect the current chapter,
- links to detailed run records only as secondary actions.

The right panel should use author-facing language first and technical terms second.

## Information Architecture

### Primary Route

Keep:

```text
/projects/:id
```

Default project screen should become the author workbench, not the old overview module.

Recommended query behavior:

```text
/projects/:id?chapter=5
/projects/:id?chapter=5&view=workflow
/projects/:id?chapter=5&auto_generate=1
```

Keep `module=` compatibility for old links, but route the most important author tasks back into the workbench when possible.

### Secondary Surfaces

The following should become secondary drawers, panels, or less prominent module routes:

- 创世设定
- 大纲篇章
- 章节指令
- 人物
- 势力
- 世界资料
- 伏笔
- 事实账本
- 风格规范
- 运行记录
- 项目设置

Do not remove these modules in v5.6. The rework should reorganize priority first.

## Visual Direction

Target feel:

```text
quiet writing software + inspectable AI agent console
```

Use:

- restrained neutral surfaces,
- strong text readability,
- clear three-column workbench,
- subtle status color only where it carries meaning,
- compact controls,
- 8px or smaller card radius unless an existing token already constrains it,
- lucide icons in action buttons.

Avoid:

- hero sections,
- marketing copy,
- decorative gradients as the main identity,
- oversized cards,
- nested cards,
- purple/blue gradient-heavy themes,
- one-note teal/blue palette,
- in-app text explaining features or keyboard shortcuts,
- visible AI/engineering jargon as primary labels.

## Layout Contract

### Desktop

Recommended layout:

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Project top bar: project name, current chapter, mode, primary action │
├───────────────┬───────────────────────────────────────┬─────────────┤
│ Chapter list   │ Writing surface                       │ Agent panel │
│ 260-320px      │ flexible, readable width              │ 320-400px   │
└───────────────┴───────────────────────────────────────┴─────────────┘
```

Desktop constraints:

- left column: `clamp(240px, 18vw, 320px)`,
- right column: `clamp(300px, 22vw, 420px)`,
- center min width: `minmax(0, 1fr)`,
- chapter body max width: `760-920px`,
- avoid horizontal overflow at 1366px.

### Mobile

Recommended layout:

- top compact project header,
- chapter selector as a horizontal drawer or select-like control,
- writing surface first,
- agent panel below writing surface,
- module links hidden behind a "资料" or "项目" menu.

## Implementation Scope for v5.6 Phase 1

Phase 1 should implement the new shell and main workbench without changing backend behavior.

Required files likely to change:

- `frontend/src/pages/ProjectDetail.tsx`
- `frontend/src/components/project/ProjectShell.tsx`
- `frontend/src/components/project/ProjectSideNav.tsx`
- `frontend/src/components/project/ChapterWorkspace.tsx`
- `frontend/src/components/ChapterNav.tsx`
- `frontend/src/styles/design-system.css`
- relevant frontend tests under `frontend/src/components/project/__tests__/`

Recommended new files:

- `frontend/src/components/project/AuthorWorkbench.tsx`
- `frontend/src/components/project/AuthorChapterRail.tsx`
- `frontend/src/components/project/AuthorWritingSurface.tsx`
- `frontend/src/components/project/AuthorAgentPanel.tsx`
- `frontend/src/components/project/AuthorWorkbench.css`

The new components may initially wrap and reuse existing logic from `ChapterWorkspace.tsx`, then gradually shrink the old component.

## Behavior Requirements

1. Opening `/projects/:id` should show the author workbench.
2. If no chapter query is provided, select the first available chapter.
3. Selecting a chapter updates `chapter=N` in the URL.
4. `view=workflow`, `view=artifacts`, and `view=history` remain supported.
5. `auto_generate=1` still starts generation only after workspace data is loaded and only when no workflow is running.
6. Generation button is hidden or disabled for:
   - `reviewed`,
   - `awaiting_publish`,
   - `published`,
   - any chapter with a running workflow.
7. Published chapters show a valid continue-next action.
8. `reviewed + real mode` shows publish as the primary action.
9. Stale and obsolete session handling remains available, but not as the main first-screen object unless it blocks the current task.
10. Agent panel must display structured failure or blocking reasons when available.

## Test Requirements

Add or update frontend tests for:

- `/projects/:id` default workbench rendering,
- chapter rail renders statuses and current chapter,
- generated content remains readable in center surface,
- reviewed real-mode chapter shows publish action, not generate action,
- published chapter shows continue-next action, not generate action,
- running workflow disables generation,
- `auto_generate=1` still respects running-workflow guard,
- obsolete disconnected sessions do not render reconnect as primary CTA,
- mobile layout does not hide the current chapter action.

Run:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test
```

Recommended backend smoke test if no backend code changes:

```bash
python3 -m pytest tests/test_v5515_production_readiness.py -q
```

## Acceptance Criteria

The implementation is acceptable when:

1. The project page reads visually as a writing workbench, not a production dashboard.
2. The current chapter is the dominant visual object.
3. The left side is for chapter navigation, not a long module menu.
4. The right side explains AI/agent status and next action.
5. Existing v5.5.15 guard behavior remains intact.
6. Existing module capabilities remain reachable.
7. Frontend typecheck, lint, build, and tests pass.
8. A human can start from `/projects/:id`, understand what to do next, and reach the current chapter content in one screen.

## Development Prompt for Implementation Agent

Use this prompt for the agent that will implement phase 3:

```text
You are working in /Users/chenchao/Workspace/AI-Project/novelos.

Implement v5.6 Phase 1 WebUI rework according to:
docs/codex/planning/novel-factory-v5.6-webui-author-workbench-rework-spec.md

Goal:
Rebuild the project page from a production-control-console feel into a personal author workbench. The first screen for /projects/:id should be a three-zone authoring experience: left chapter navigator, center writing surface, right AI agent panel.

Hard constraints:
- Do not change backend workflow behavior.
- Preserve v5.5.15 generation guards and frontend behavior:
  - do not start generation when a chapter has a running workflow,
  - do not show generation for reviewed, awaiting_publish, or published chapters,
  - reviewed + real mode should present publish as the primary action,
  - auto_generate=1 must still wait for workspace data and respect running workflow guards.
- Preserve URL compatibility:
  - /projects/:id
  - ?chapter=N
  - ?view=content|workflow|artifacts|history
  - ?auto_generate=1
  - old module links should remain usable or gracefully route into reachable secondary surfaces.
- Keep existing backend API contracts.
- Use React, TypeScript, existing CSS, and lucide-react only. Do not add a UI framework.
- Do not create a marketing page or hero layout.
- Do not bury the chapter content behind operational dashboard cards.

Suggested implementation approach:
1. Audit ProjectDetail.tsx, ProjectShell.tsx, ProjectSideNav.tsx, ChapterWorkspace.tsx, ChapterNav.tsx, and ProjectOverviewModule.tsx.
2. Introduce an AuthorWorkbench component layer:
   - AuthorWorkbench.tsx
   - AuthorChapterRail.tsx
   - AuthorWritingSurface.tsx
   - AuthorAgentPanel.tsx
   - AuthorWorkbench.css if useful.
3. Reuse existing ProjectDetail data loading, SSE startStream logic, publish/reset/generate handlers, and run detail loading.
4. Make /projects/:id default to the new workbench.
5. Keep secondary project modules reachable but make them secondary to the authoring screen.
6. Move large workbench-specific CSS out of the inline WorkspaceStyles block where practical.
7. Add/update frontend tests for rendering, guarded generation controls, reviewed real-mode publish, published continue-next, and running workflow disabled state.

Verification:
Run these commands and report results:
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test
python3 -m pytest tests/test_v5515_production_readiness.py -q

Deliverable:
- Code changes implementing the new workbench UI.
- Updated or added frontend tests.
- A short summary of changed files and verification results.
```
