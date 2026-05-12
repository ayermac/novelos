# v5.3.4 Skill Test Bench Spec

## Goal

Allow users to run Skill fixtures tests and manually invoke Skills from the WebUI Settings page.

## Scope

In scope:
- POST /api/skills/test (all fixtures or single skill)
- POST /api/skills/run (manual invocation with text/payload)
- Settings page fixtures test bench
- Settings page manual run bench

Out of scope:
- Editing `skills.yaml`
- Enabling/disabling Skills
- Importing external Skills
- Runtime hot reload

## API

### POST /api/skills/test

Request:
```json
{"all": true}
```
or
```json
{"skill_id": "humanizer-zh"}
```

Response (all):
```json
{
  "ok": true,
  "data": {
    "total": 3,
    "passed": 3,
    "failed": 0,
    "results": {
      "humanizer-zh": {"ok": true, "error": null, "data": {...}}
    }
  }
}
```

### POST /api/skills/run

Request:
```json
{
  "skill_id": "humanizer-zh",
  "text": "input text",
  "payload": {"extra": "data"}
}
```

Response:
```json
{
  "ok": true,
  "data": {
    "skill_id": "humanizer-zh",
    "result": {"ok": true, "error": null, "data": {...}}
  }
}
```

## Acceptance

- WebUI can test all Skills at once
- WebUI can test individual Skills
- WebUI can manually run a Skill with custom text
- Errors are visible and not swallowed
- Backend and frontend verification pass

## Follow-Up Versions

- v5.3.5 Skill Configuration Draft
- v5.3.6 Skill Import Workbench
- v5.4.0 Skill Runtime Governance
