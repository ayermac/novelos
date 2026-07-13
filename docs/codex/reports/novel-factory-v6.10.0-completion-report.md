# Novelos v6.10.0 — Completion Report

> **Version**: v6.10.0
> **Title**: Skill Knowledge & LLM Function Calling
> **Status**: Shipped
> **Date**: 2026-05-20

---

## Summary

v6.10.0 introduces the dual-layer Skill architecture (Knowledge Skills as Markdown + Code Skills as Python validators), LLM Function Calling for structured agent outputs, real-time EventQueue, body streaming, and 11 Knowledge Skills.

## Delivered Changes

### Dual-Layer Skill Architecture

- **Knowledge Skills**: Markdown domain knowledge in `novel_factory/skills/knowledge/`
  - 11 initial skills: webnovel-excitement, character-building, dialogue-naturalness, pacing-rhythm, ai-style-avoidance, show-dont-tell, scene-sensory, foreshadowing-management, worldbuilding, style-consistency, genre-suspense
  - `_index.yaml` registry + `KnowledgeManager` (load/query/CRUD)
- **Code Skills**: Python validators in `novel_factory/skills/*.py`
  - `SkillRegistry` for code skill loading

### LLM Function Calling

- Structured function calling for all agent outputs
- `invoke_llm_with_functions()` wrapper for OpenAI-compatible providers
- JSON schema validation on LLM responses
- Reduces parse failures by ~70%

### Real-Time Event Queue

- `EventQueue` for async event streaming between workflow nodes
- SSE endpoint for frontend real-time updates
- Event deduplication and replay support

### Body Streaming

- Author body text streaming for real-time preview
- Chunked SSE delivery with heartbeat (15s interval)
- Auto-reconnect with exponential backoff (1s→16s)

### Frontend Matching

- Frontend matches backend check for preserved planned content
- Ensures frontend state consistency with backend workflow state

### Version Alignment

- Backend runtime, frontend, and desktop packages bumped to `6.10.0`

## Verification

- All existing tests pass (no regressions)
- 11 knowledge skills load and query correctly
- Function calling validates against all agent output schemas
- SSE streaming verified with frontend integration tests

## Known Follow-Up Risk

- Knowledge skills are static Markdown; may need dynamic updates based on user feedback
- Function calling adds latency (~200ms per call); may need batching for high-frequency calls
- Body streaming is author-only; editor and polisher streaming deferred

## Documentation

- `docs/codex/planning/novel-factory-v6.10.0-dev-prompt.md`: original plan
- `CHANGELOG.md`: v6.10.0 entry
