# v3.9 LLM Model Catalog & Agent Recommendation — Specification

## Summary

v3.9 introduces an offline, auditable LLM Model Catalog and Agent Recommendation system. Users can view "which model suits each agent" and generate recommended configuration drafts without modifying production paths.

## Goals

- Establish a built-in LLM Model Catalog with capability tags, pricing tiers, context lengths, and recommended usage per model.
- Auto-recommend models based on Agent responsibilities (Planner → reasoning, Author → prose + long_context, Editor → editing + reasoning, etc.).
- Provide CLI commands to view catalog, recommendations, and config drafts.
- Generate `llm_profiles` + `agent_llm` configuration drafts (YAML snippets), but never auto-overwrite user configs.
- Maintain full compatibility with existing v3.1 LLMRouter.

## Non-Goals / Prohibited Scope

- No automatic online model switching or fallback.
- No provider health check or latency testing.
- No real API calls from the catalog/recommender.
- No real token cost statistics.
- No internet-based model ranking sync.
- No modification of main production pipeline (Dispatcher/Agent routing).
- No Web UI / FastAPI.
- No new DB migration.
- No writing to user config files.
- No modification of `.env`.
- No auto-overwrite of user's existing `agent_llm`.
- `config-plan` only outputs YAML draft, never persists to disk.
- Recommendation output never contains API keys or any secrets.

## Technical Design

### Data Model

All models are Pydantic `BaseModel` classes in `novel_factory/llm/catalog.py`.

#### LLMModelSpec

| Field | Type | Description |
|-------|------|-------------|
| `provider` | `str` | Provider name (openai, deepseek, anthropic-compatible, openrouter, local) |
| `model` | `str` | Model identifier (e.g., gpt-4o, deepseek-chat) |
| `display_name` | `str` | Human-readable name |
| `profile_template` | `str` | Template for profile generation (default: openai_compatible) |
| `context_window` | `int` | Context window in tokens |
| `cost_tier` | `CostTier` | low / medium / high |
| `latency_tier` | `LatencyTier` | low / medium / high |
| `quality_tier` | `QualityTier` | draft / standard / premium |
| `strengths` | `list[Strength]` | Capability tags |
| `recommended_agents` | `list[str]` | Agents this model is recommended for |
| `notes` | `str` | Free-form notes |

#### Enums

- `CostTier`: low, medium, high
- `LatencyTier`: low, medium, high
- `QualityTier`: draft, standard, premium
- `Strength`: reasoning, long_context, prose, editing, json, planning, safety, speed

#### LLMCatalog

Container for `list[LLMModelSpec]` with query methods:
- `get_by_provider_model(provider, model)` → Optional[LLMModelSpec]
- `get_by_agent(agent_id)` → list[LLMModelSpec]
- `get_by_strength(strength)` → list[LLMModelSpec]
- `get_by_cost_tier(max_tier)` → list[LLMModelSpec]
- `get_by_quality_tier(min_tier)` → list[LLMModelSpec]
- `get_by_provider(provider)` → list[LLMModelSpec]
- `all_providers()` → list[str]

### Catalog Schema

The catalog is stored in `novel_factory/config/llm_catalog.yaml`:

```yaml
catalog:
  - provider: openai
    model: gpt-4o
    display_name: GPT-4o
    profile_template: openai_compatible
    context_window: 128000
    cost_tier: high
    latency_tier: medium
    quality_tier: premium
    strengths:
      - reasoning
      - planning
      - json
      - prose
      - editing
      - long_context
    recommended_agents:
      - planner
      - screenwriter
      - author
    notes: "Flagship model"
```

### Recommendation Algorithm

Each agent has a profile mapping:

| Agent | Required Strengths | Preferred Strengths | Default Min Quality |
|-------|-------------------|--------------------|--------------------|
| planner | reasoning, planning, json | — | standard |
| screenwriter | reasoning, planning, json | prose | standard |
| author | prose, long_context | safety | standard |
| polisher | editing, prose, safety | — | standard |
| editor | editing, reasoning, json | — | standard |
| scout | speed | reasoning | draft |
| continuity_checker | long_context, reasoning, json | — | standard |
| architect | reasoning, json | planning | standard |
| secretary | — | speed | draft |

Scoring:
- +15 per matched required strength
- +8 per matched preferred strength
- +10 if model lists agent in `recommended_agents`
- +5 × quality_rank (0/1/2 for draft/standard/premium)
- -3 × cost_rank if quality requirement is low (penalize expensive models when quality isn't needed)
- +5 for low latency when `prefer_low_latency=True`
- +8 for context_window ≥ 100K when `long_context` is required
- -20 per missing required strength (heavy penalty)

Constraints:
- `cost_tier_max`: filter out models above this tier
- `quality_tier_min`: filter out models below this tier
- `provider_whitelist`: only include models from listed providers
- `require_strengths`: only include models with all listed strengths
- `prefer_low_latency`: boost low-latency models

### CLI Design

All commands use the existing `llm` subcommand group.

```bash
# List all models in catalog
novelos llm catalog --json

# Recommend for a single agent
novelos llm recommend --agent author --json

# Recommend for all agents
novelos llm recommend --all --json

# Recommend with constraints
novelos llm recommend --all --cost-tier medium --json

# Generate configuration plan
novelos llm config-plan --all --json
```

Output format (JSON mode):

```json
{"ok": true, "error": null, "data": {...}}
```

Error format:

```json
{"ok": false, "error": "error message", "data": {}}
```

### Config Plan Design

`config-plan` generates:

1. `default_llm`: Most commonly recommended profile name
2. `llm_profiles`: Deduplicated dict of profile_name → profile_config
3. `agent_llm`: Dict of agent_id → profile_name

Profile configs use environment variable references:

```yaml
llm_profiles:
  rec_author:
    provider: openai_compatible
    model: claude-3.5-sonnet
    base_url_env: ANTHROPIC_BASE_URL
    api_key_env: ANTHROPIC_API_KEY
```

Profiles with the same provider+model are deduplicated. Multiple agents may share the same profile.

### Compatibility With v3.1 LLMRouter

v3.9 does NOT modify the LLMRouter, Dispatcher, or any production path. The catalog and recommender are purely advisory tools:

- `novelos llm profiles` — unchanged
- `novelos llm route --agent author` — unchanged
- `novelos llm validate` — unchanged
- `run-chapter` — unchanged
- `batch run` — unchanged
- sidecar CLI — unchanged

The recommender's output is a configuration draft that users can manually merge into their config file. It never writes to disk.

## Test Plan

### New test files

| File | Tests |
|------|-------|
| `tests/test_v39_llm_catalog.py` | Catalog loading, schema, queries, errors |
| `tests/test_v39_llm_recommender.py` | Agent recommendations, constraints, config plan, no secrets |
| `tests/test_v39_llm_cli.py` | CLI commands, JSON envelopes, v3.1 regression |

### Test coverage

- Default catalog file loads successfully
- Model spec schema validation (valid/invalid)
- Each core agent gets a recommendation
- All 9 agents covered in `recommend --all`
- Constraints work: cost_tier, quality_tier, provider_whitelist, require_strengths, prefer_low_latency
- Unknown agent returns stable error
- `llm catalog --json` outputs envelope
- `llm recommend --agent author --json` outputs envelope
- `llm recommend --all --json` outputs all agent recommendations
- `llm config-plan --all --json` outputs usable YAML snippet
- No API keys in any recommendation output
- v3.1 llm CLI tests don't regress
- File size policy doesn't regress

## Acceptance Criteria

```bash
# v3.9 specific tests
python3 -m pytest tests/test_v39_llm_catalog.py tests/test_v39_llm_recommender.py tests/test_v39_llm_cli.py -q

# v3.1 regression
python3 -m pytest tests/test_v31_error_envelope.py -q

# File size policy
python3 -m pytest tests/test_file_size_policy.py -q

# Full suite
python3 -m pytest -q

# CLI verification
python3 -m novel_factory.cli llm catalog --json
python3 -m novel_factory.cli llm recommend --agent author --json
python3 -m novel_factory.cli llm recommend --all --json
python3 -m novel_factory.cli llm recommend --all --cost-tier medium --json
python3 -m novel_factory.cli llm config-plan --all --json
```

All tests pass. All CLI commands return valid JSON envelopes. No file exceeds 1000 lines.

## Developer Report Template

- Modified files: list
- New files: list
- New CLI commands: list
- New tests: count
- Full test count and result
- Real CLI verification results
- Compliance with prohibited scope
- File line counts (none > 1000)
- Incomplete items or risks
