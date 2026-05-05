# v5.4.13 Project-specific Skill Overrides

## Goal

Add a project-level override layer for Skills so each project can define its
own Skill enablement, mount plan, and parameter defaults without mutating the
global `skills.yaml`.

## Scope

- Add a per-project override document stored in SQLite.
- Expose project-level read/write/clear APIs for override documents.
- Apply project overrides at runtime when `editor` and `polisher` run Skills.
- Support three override dimensions:
  - `skills.<skill_id>.enabled`
  - `skills.<skill_id>.config`
  - `skills.<skill_id>.payload_defaults`
  - `agent_skills.<agent>.<stage>` mount replacement
- Add a project settings UI panel for editing the override JSON.
- Keep global Skills generic and reusable.

## Out of Scope

- Editing global `skills.yaml` semantics.
- Agent-specific per-project skill package migration.
- Bulk import or bulk remapping of Skills.
- Workflow routing changes unrelated to Skill selection.
- Runtime mutation of Skill manifests.

## Success Criteria

- Project A overrides do not affect Project B.
- A project can replace a stage mount list without changing global config.
- Project-level payload defaults are merged into Skill input payloads.
- Project-level config overrides affect instantiated Skill config safely.
- Full pytest, frontend typecheck, lint, and build pass.
