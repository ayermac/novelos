# Novelos v5.9.3 Agent Skill Expansion Completion Report

## Summary

v5.9.3 upgrades Skill from a Polisher/Editor quality plugin layer into a broader Agent capability layer. Planner, Screenwriter, Author, Polisher, Editor, and MemoryCurator now all have runtime Skill mounts represented in configuration, API output, Skill Console coverage, and backend execution.

## Delivered

- Added shared Agent Skill hook helper at `novel_factory/agents/skill_hooks.py`.
- Added four deterministic validator Skills:
  - `chapter-objective-checker`
  - `scene-conflict-checker`
  - `event-coverage-checker`
  - `memory-patch-validator`
- Added manifests for all four new Skills under `novel_factory/config/skills/manifest/`.
- Updated `novel_factory/config/skills.yaml` to enable the new Skills and mount them by default.
- Wired runtime Skill execution into:
  - `PlannerAgent.after_llm`
  - `ScreenwriterAgent.after_llm`
  - `AuthorAgent.after_llm`
  - `MemoryCuratorAgent.after_extract`
- Refactored Polisher/Editor Skill persistence through the shared hook while preserving existing behavior.
- Review fix: ensured LangGraph router-mode node runners create/inject a default `SkillRegistry` when none is explicitly supplied, so configured Agent Skills execute in the real workflow path, not only in direct Agent tests.
- Updated Skill API legacy detection so manifest-backed built-ins are not shown as legacy/no-manifest.
- Updated Skill Console with:
  - Core Agent coverage summary
  - Missing runtime mount indicator
  - Stage explanation text
  - Matrix visibility for Planner/Screenwriter/Author/MemoryCurator default mounts

## Default Mounts

| Agent | Stage | Skill |
| --- | --- | --- |
| planner | after_llm | chapter-objective-checker |
| screenwriter | after_llm | scene-conflict-checker |
| author | after_llm | event-coverage-checker |
| memory_curator | after_extract | memory-patch-validator |
| polisher | after_llm | humanizer-zh |
| polisher | before_save | ai-style-detector |
| editor | before_review | ai-style-detector, narrative-quality, style-bible-checker |

## Validation

- `python3 -m pytest tests/test_skill_config.py tests/test_skills.py tests/test_skills_api.py tests/test_agents.py -q`: 107 passed
- `python3 -m pytest tests/test_v516_langgraph_activation.py -q`: 14 passed
- `python3 -m pytest tests/test_v40_style_bible_skill.py tests/test_skill_package.py -q`: 43 passed
- `python3 scripts/verify.py smoke`: passed
- `cd frontend && npm run typecheck`: passed
- `cd frontend && npm run lint`: passed
- `cd frontend && npm run build`: passed with existing Vite chunk-size warning
- `cd frontend && npm run test -- --run`: 148 passed

## Notes

- No workflow graph order changes were made.
- No database migrations were added.
- New Skills are deterministic/rule-based and do not call LLMs or network resources.
- Non-critical Skill failures are recorded as warnings/failed `skill_runs` and do not crash the workflow.
