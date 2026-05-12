# v5.3.3 Skill Visibility Spec

## Goal

Expose the existing runtime Skill system in WebUI so users can see which Skills exist, which are enabled, and where they are mounted.

## Scope

In scope:
- Skill list API
- Skill detail API
- Skill mounts API
- Skill validation API
- Settings page Skill visibility panel

Out of scope:
- Editing `skills.yaml`
- Enabling/disabling Skills
- Running or testing Skills from WebUI
- Importing external Skills
- Runtime hot reload

## Acceptance

- WebUI shows all configured Skills
- WebUI shows agent/stage mounts
- Enabled but unmounted Skills are flagged
- Skill validation is callable from WebUI
- Backend and frontend verification pass

## Follow-Up Versions

- v5.3.4 Skill Test Bench
- v5.3.5 Skill Configuration Draft
- v5.3.6 Skill Import Workbench
- v5.4.0 Skill Runtime Governance
