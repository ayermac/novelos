# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Novelos is an AI-powered novel production workbench for long-form fiction projects. It combines a FastAPI backend, LangGraph chapter workflow, SQLite project storage, a React author workspace, and CLI tools for chapter generation, review, style, project context, and operational checks.

Current baseline: **v5.3.x RC**, with **1633/1633 pytest passing**, frontend typecheck passing, and frontend production build passing.

## Architecture

```text
frontend/              React + Vite author workspace
novel_factory/api/     FastAPI app, route dependencies, API models
novel_factory/db/      SQLite schema, migrations, repositories
novel_factory/workflow LangGraph chapter workflow and checkpointing
novel_factory/llm/     Stub and OpenAI-compatible LLM providers
novel_factory/cli_app/ CLI command implementation
novel_factory/agents/  AI agents (planner, screenwriter, author, polisher, editor, etc.)
novel_factory/models/  Pydantic models and state definitions
novel_factory/config/  Configuration loading and validation
tests/                 Python regression and version acceptance tests
docs/codex/            Product specs, roadmap, and version history
```

The main production path is LangGraph-based. `Dispatcher` and `dispatch/` are retained as compatibility paths for older CLI capabilities and historical workflows.

## Core Workflow

The chapter production workflow follows this pipeline:

```text
health_check → task_discovery → planner → screenwriter → author → polisher → editor → publisher → archive
```

Key state transitions:
- `planned → scripted → drafted → polished → review → reviewed → published`
- Review failures can trigger `revision` with routing back to author, polisher, or planner
- Real mode stops at `awaiting_publish` (no auto-publish)

## Development Commands

### Python Backend

```bash
# Install package and dependencies
python3 -m pip install -e .

# Initialize database
novelos init-db --db-path acceptance_novel_factory.db

# Start API server (demo mode)
novelos api --host 127.0.0.1 --port 8765 --db-path acceptance_novel_factory.db --llm-mode stub

# Start API server (real mode)
novelos api --host 127.0.0.1 --port 8765 --db-path acceptance_novel_factory.db --config config/local.yaml --llm-mode real

# Run full test suite
python3 -m pytest -q

# Run specific test file
python3 -m pytest tests/test_v52_phase_a.py -q

# Run single test
python3 -m pytest tests/test_v52_phase_a.py::test_name -q
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Type checking
npm run typecheck

# Production build
npm run build

# Lint
npm run lint
```

### CLI Commands

```bash
# Generate chapter (demo mode)
novelos --db-path acceptance_novel_factory.db run-chapter --project-id demo --chapter 1 --llm-mode stub --json

# Generate chapter (real mode)
novelos --config config/local.yaml --llm-mode real run-chapter --project-id demo --chapter 1 --json

# Check chapter status
novelos --db-path acceptance_novel_factory.db status --project-id demo --chapter 1 --json

# List workflow runs
novelos --db-path acceptance_novel_factory.db runs --project-id demo --json

# Validate configuration
novelos --config config/local.yaml config validate --json

# Seed demo data
novelos --db-path acceptance_novel_factory.db seed-demo --project-id demo
```

## LLM Modes

### Stub Mode (Default)
- Used for local demos and testing
- No real API calls
- Deterministic output for development

### Real Mode
- Uses OpenAI-compatible providers
- Requires API keys in environment or `.env` file
- Supports OpenAI, OpenRouter, DeepSeek, etc.

Environment variables for real mode:
```bash
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# Optional alternatives:
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

## Key Components

### Agents (`novel_factory/agents/`)
- **planner.py**: Controls macro-level plot, generates writing instructions, plants foreshadowing
- **screenwriter.py**: Converts instructions into scene outlines
- **author.py**: Transforms outlines into full text
- **polisher.py**: Refines and polishes prose
- **editor.py**: Five-layer review + red-line scanning
- **scout.py**: Market analysis and topic recommendations
- **continuity_checker.py**: Checks continuity across chapters
- **architect.py**: System diagnostics and optimization

### Workflow (`novel_factory/workflow/`)
- **graph.py**: LangGraph StateGraph construction and compilation
- **nodes.py**: Node implementations for each workflow step
- **runner.py**: Workflow execution and checkpoint management
- **conditions.py**: Conditional routing logic

### Database (`novel_factory/db/`)
- **connection.py**: SQLite connection management
- **repositories/**: Repository pattern implementations for each entity
- **migrations/**: Database schema migrations
- **schema/**: SQL schema definitions

### LLM (`novel_factory/llm/`)
- **provider.py**: Abstract LLM provider interface
- **openai_compatible.py**: OpenAI-compatible provider implementation
- **stub_provider.py**: Stub provider for demo mode
- **router.py**: LLM routing for agent-level configuration
- **profiles.py**: LLM profile management

## Configuration

Configuration is loaded from:
1. OS environment variables
2. Project-root `.env` file
3. YAML defaults (e.g., `config/local.yaml`)

Key configuration files:
- `config/local.yaml`: Local development configuration
- `config/acceptance.yaml`: Acceptance test configuration

## Testing

### Python Tests
- Test location: `tests/`
- Framework: pytest
- Current baseline: 1564/1564 passing
- Run full suite: `python3 -m pytest -q`
- Run specific test: `python3 -m pytest tests/test_file.py::test_name -q`

### Frontend Tests
- Framework: vitest
- Run: `npm run test`

## Documentation

Primary project planning and version documentation lives under:
```text
docs/codex/
```

Start with:
- `docs/codex/README.md`
- `docs/codex/novel-factory-roadmap.md`
- `docs/codex/novel-factory-v5.2-product-completion-real-llm-closure-spec.md`

## Development Notes

- Python 3.9+ required
- Node.js 18+ required
- `uv` recommended for reproducible Python dependency management via `uv.lock`
- SQLite databases, WAL files, build output, Python caches, and frontend dependencies are gitignored
- `uv.lock` is committed for reproducibility
- `openclaw-agents/` is treated as a local-only legacy workspace and is ignored by Git
