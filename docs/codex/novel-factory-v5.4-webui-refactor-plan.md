# Novelos v5.4 WebUI Refactor Plan

## Goal

Refactor the WebUI from a growing collection of feature pages into a stable author workbench shell.

The product should feel like a professional AI writing control room:

- Chapter generation and recovery are always visible.
- Project knowledge modules are easy to scan and reach.
- Settings, Skills, LLM, and diagnostics are separated into focused consoles.
- Errors, pending work, and workflow state are shown near the action that needs them.
- The UI remains dense enough for repeated authoring work, without becoming visually noisy.

This plan should start after v5.3.7 Real LLM E2E Burn-in finishes, so the UI refactor does not hide unresolved workflow behavior.

## Current Problems

### 1. Page Components Carry Too Much Responsibility

`frontend/src/pages/ProjectDetail.tsx` currently handles:

- project workspace loading
- chapter detail loading
- run detail loading
- SSE generation state
- chapter tab routing
- module routing
- layout shell
- contextual sidebar wiring
- reset/publish/generate actions

This makes small workflow changes risky because state and layout are tangled.

`frontend/src/pages/Settings.tsx` has the same pattern: section navigation, LLM profiles, generation diagnostics, draft generator, validation, agent routes, and Skill management all live in one page file.

### 2. Navigation Is Flat, But The Product Is Not

Project modules are currently shown as one long horizontal tab list:

- overview
- genesis
- chapters
- worldview
- characters
- factions
- outline
- plots
- instructions
- memory
- facts
- style
- review
- runs
- settings

This is workable for early versions, but the product now has distinct work areas:

- writing
- project knowledge
- review and quality
- operations
- project configuration

The UI should reflect that hierarchy.

### 3. State Visibility Is Inconsistent

Recent backend work added better isolation and error attribution, but the UI still distributes state across several places:

- chapter status in chapter list
- workflow state in chapter tab
- run errors in run detail
- context readiness in sidebar
- memory failures in memory module
- Skill warnings in settings

Users need one clear "what needs attention" layer per workspace.

### 4. Inline Styles Limit Reuse

Many cards, nav items, panels, and status blocks are styled inline. This makes visual consistency hard to maintain and slows future redesign.

### 5. Settings Is A Control Panel, Not A Single Page

Settings now includes LLM, draft config, Skill management, validation, diagnostics, and agent route visibility. These should remain under one settings area, but each needs a focused subpage or panel contract.

## Product Design Direction

Use a restrained operational UI, not a marketing page.

Recommended structure:

```text
AppShell
  TopBar: product, environment, global actions
  LeftNav: Projects, Runs, Settings
  MainContent

ProjectShell
  ProjectHeader: project name, mode, current chapter, primary actions
  ProjectSideNav: grouped project modules
  ProjectWorkspace: active module
  InspectorPanel: context readiness, errors, latest run, actions
```

Project side navigation should be grouped:

```text
Write
  Chapters
  Outline
  Chapter Instructions

Knowledge
  Genesis
  Worldview
  Characters
  Factions
  Plot Holes
  Facts
  Memory Updates

Quality
  Style Guide
  Review
  Runs

Project
  Overview
  Settings
```

Settings should be grouped:

```text
SettingsShell
  Overview
  LLM Profiles
  Agent Routes
  Skills
  Config Draft
  Diagnostics
```

## Version Plan

### v5.4.0 WebUI Information Architecture

Deliver a new navigation and shell structure without changing backend behavior.

Scope:

- Introduce `ProjectShell`.
- Replace the flat horizontal `ProjectModuleNav` with grouped side navigation.
- Keep URL compatibility with existing `?module=` links.
- Add a compact `ProjectHeader`.
- Keep chapter workspace behavior unchanged.
- Move inline layout styles into CSS classes.

Success criteria:

- Existing project URLs continue to work.
- Module switching remains URL-addressable.
- Chapter generation, workflow tab, artifacts, history, context sidebar, and project modules still load.
- Frontend typecheck/lint/build pass.

### v5.4.1 Chapter Workspace Split

Reduce `ProjectDetail.tsx` complexity.

Scope:

- Extract `ChapterWorkspace`.
- Extract `useProjectWorkspace`.
- Extract `useChapterDetail`.
- Extract `useChapterGenerationStream`.
- Keep behavior identical.

Success criteria:

- Generating chapter N does not show workflow state on chapter M.
- Chapter tab URL behavior remains stable.
- Run detail loads latest run for the selected chapter only.

### v5.4.2 Settings Console

Turn Settings into a focused control console.

Scope:

- Introduce `SettingsShell`.
- Split sections into files:
  - `SettingsOverviewSection`
  - `LlmProfilesSection`
  - `AgentRoutesSection`
  - `SkillsSection`
  - `ConfigDraftSection`
- Preserve `?section=` routing.
- Keep SkillVisibilityPanel behavior unchanged.

Success criteria:

- `settings?section=llm`, `settings?section=skills`, and `settings?section=draft` remain valid.
- No section failure should collapse unrelated sections.

### v5.4.3 Attention And Error Layer

Create a reusable pattern for things that need user action.

Scope:

- Add `AttentionPanel`.
- Add `ErrorCallout`.
- Add `ActionHintList`.
- Surface:
  - context readiness gaps
  - blocked workflow reason
  - memory failed items
  - Skill validation warnings
  - real-mode config risks

Success criteria:

- Blocking/retry reasons are visible near the relevant action.
- Legacy run fallback errors are still marked as historical.
- Memory item failures remain visible with retry actions.

### v5.4.4 Agent Skill Matrix

After the shell is stable, expose agent-to-skill configuration.

Scope:

- Add read-only Agent Skill Matrix first.
- Show agents, stages, mounted skills, enabled status, package/legacy status.
- Show warnings for enabled unmounted skills, mounted disabled skills, missing skills, unknown stages.

Out of scope for first pass:

- Editing and saving `skills.yaml`.
- Project-specific skill overrides.
- OpenClaw bulk skill migration.

### v5.4.5 WebUI Visual QA and Polish

Close the first refactor pass with source-level visual QA focused on narrow, dense workbench panels.

Scope:

- Tighten Settings section navigation wrapping.
- Make the Skill management panel easier to scan without removing operational detail.
- Summarize Agent Skill Matrix counts and cap long warning blocks.
- Prevent long project names, skill IDs, packages, classes, and stage names from overflowing their containers.
- Preserve existing query-param navigation and frontend acceptance anchors.

Out of scope:

- New backend APIs.
- Editable skill mounting.
- Broad design-system migration.
- Browser-driven screenshot automation when the local automation toolchain is unavailable.

Success criteria:

- Frontend typecheck, lint, and production build pass.
- Skill management remains functionally equivalent.
- Long operational labels wrap inside their panels instead of forcing horizontal overflow.

## Implementation Rules

- Do not redesign the product as a landing page.
- Do not hide dense operational information inside decorative cards.
- Use full-width workbench bands and panels; avoid nested cards.
- Use lucide icons where icons are needed.
- Keep cards at 8px radius or less unless matching an existing reusable class.
- Keep text readable and avoid viewport-based font scaling.
- Preserve current query-param URLs.
- Do not change backend APIs unless a UI need cannot be met otherwise.
- Avoid unrelated styling churn.
- Add tests proportional to risk.

## Developer Agent Prompt

```text
Implement v5.4.0 WebUI Information Architecture Refactor for Novelos.

Context:
Novelos is an AI novel production workbench. The current WebUI has grown organically through v5.3.x. ProjectDetail.tsx and Settings.tsx now carry too many responsibilities. The goal is to refactor structure and navigation first, without changing backend workflow behavior.

Primary goal:
Introduce a stable author workbench shell with grouped project navigation while preserving existing project/chapter URLs and behavior.

Repository:
/Users/chenchao/Workspace/AI-Project/novelos

Read first:
- frontend/src/pages/ProjectDetail.tsx
- frontend/src/components/project/ProjectModuleNav.tsx
- frontend/src/components/ChapterNav.tsx
- frontend/src/components/ContextSidebar.tsx
- frontend/src/components/WorkflowTimeline.tsx
- frontend/src/styles/design-system.css
- frontend/src/index.css

Required changes:
1. Create a ProjectShell-oriented structure.
   Suggested files:
   - frontend/src/components/project/ProjectShell.tsx
   - frontend/src/components/project/ProjectSideNav.tsx
   - frontend/src/components/project/ProjectHeader.tsx

2. Replace the flat horizontal ProjectModuleNav with grouped project navigation.
   Groups:
   - Write: chapters, outline, instructions
   - Knowledge: genesis, worldview, characters, factions, plots, facts, memory
   - Quality: style, review, runs
   - Project: overview, settings

3. Preserve existing URL contract:
   - /projects/:id?module=chapters&chapter=N
   - /projects/:id?module=chapters&chapter=N&view=workflow
   - /projects/:id?module=style
   - /projects/:id?module=runs
   - all current module keys must still work

4. Keep chapter generation behavior unchanged.
   Do not change SSE logic, workflow routing, run detail loading, or backend APIs.
   If extracting components, keep the same state semantics:
   - generatingChapter must isolate workflow display to the selected chapter
   - run detail should load for the selected chapter only
   - current chapter should remain in the URL

5. Reduce inline layout styling where practical.
   Add reusable CSS classes in frontend/src/index.css or frontend/src/styles/design-system.css.
   Keep the design operational and dense:
   - no landing page
   - no oversized hero
   - no decorative gradients/orbs
   - no nested cards

6. Keep visual language consistent:
   - lucide icons are OK
   - stable side navigation width
   - compact project header
   - clear active state
   - good keyboard focus states
   - no horizontal overflow on narrow screens

7. Testing and verification:
   - npm run typecheck
   - npm run lint
   - npm run build
   - If possible, manually inspect:
     - /projects/novel_180v?module=chapters&chapter=1
     - /projects/novel_180v?module=chapters&chapter=2&view=workflow
     - /projects/novel_180v?module=style
     - /projects/novel_180v?module=runs

Non-goals:
- Do not implement Agent Skill Matrix in this phase.
- Do not migrate OpenClaw skills in this phase.
- Do not change backend APIs.
- Do not rewrite all project modules.
- Do not alter workflow generation behavior.

Expected deliverable:
- A narrow commit that introduces the new ProjectShell/grouped navigation and keeps existing behavior green.
- Short summary of changed files and verification commands.
```

## Follow-up Prompt For v5.4.1

```text
Implement v5.4.1 Chapter Workspace Split.

Goal:
Reduce ProjectDetail.tsx complexity by extracting chapter workspace state and UI without changing behavior.

Scope:
- Extract ChapterWorkspace component.
- Extract hooks for workspace loading, chapter detail loading, and generation stream.
- Preserve URL behavior and workflow isolation.
- Keep ProjectShell from v5.4.0 intact.

Verification:
- npm run typecheck
- npm run lint
- npm run build
- Manual browser checks for chapter content, workflow, artifacts, history, and generation error states.
```
