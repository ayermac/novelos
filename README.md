<div align="center">

# Novelos

**AI-Powered Novel Production Workbench**

English | [中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5+-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Workflow-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

An end-to-end workbench for long-form fiction: plan arcs, generate chapters through a LangGraph pipeline, review and polish prose, and manage project context — from CLI and web workspace.

[Features](#features) | [Architecture](#architecture) | [Quick Start](#quick-start) | [CLI Reference](#cli-reference) | [Configuration](#configuration) | [Testing](#testing) | [Documentation](#documentation)

</div>

---

## Features

- **Chapter Production Pipeline** — LangGraph workflow with planner, screenwriter, author, polisher, editor, and publisher nodes
- **Project Context Management** — World settings, characters, factions, outlines, foreshadowing, and chapter instructions
- **Dual LLM Modes** — Stub mode for local development and demos; real mode for OpenAI-compatible providers (OpenAI, OpenRouter, DeepSeek)
- **Author Workspace** — React + Vite web UI for day-to-day writing, chapter browsing, and project context editing
- **Autonomous Production Loop** — AI-driven batch chapter generation with step-by-step control, pause/resume, and budget guardrails
- **Token Budget Guardrails** — Per-chapter, per-project, and per-session token limits with explicit shutdown on overage
- **LLM Reliability** — Exponential backoff retry for rate limits and timeouts; configurable retry and timeout parameters
- **Workflow Observability** — Run tracking, artifact logging, token usage, error state, and review status
- **CLI Toolkit** — Automation, batch operations, review tools, style tools, config validation, and diagnostics
- **One-Command Deploy** — Service script for starting/stopping API + WebUI together

## Architecture

```
                        ┌──────────────────────┐
                        │   Author Workspace   │
                        │   React + Vite SPA   │
                        └──────────┬───────────┘
                                   │ REST / SSE
                        ┌──────────▼───────────┐
                        │     FastAPI Server    │
                        │   Routes / Services   │
                        └───┬────────┬────┬─────┘
                            │        │    │
               ┌────────────┘        │    └────────────┐
               ▼                     ▼                 ▼
    ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐
    │  LangGraph       │  │   LLM Providers  │  │    CLI      │
    │  Chapter Workflow │  │  Stub / OpenAI   │  │   Toolkit   │
    │  (StateGraph)    │  │  Compatible      │  │             │
    └────────┬─────────┘  └──────────────────┘  └─────────────┘
             │
    ┌────────▼─────────┐
    │   SQLite + WAL   │
    │  Projects, Runs, │
    │  Chapters, etc.  │
    └──────────────────┘
```

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18 + TypeScript + Vite | Author workspace SPA |
| Backend | FastAPI (async) | REST API, SSE streaming, dependency injection |
| Workflow | LangGraph StateGraph | Chapter production pipeline orchestration |
| LLM | Stub / OpenAI-compatible | Pluggable LLM providers with retry and budget |
| Database | SQLite + WAL | Project storage, workflow checkpoints |
| CLI | Python entry point | Automation, batch ops, diagnostics |

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- npm

Optional: [`uv`](https://github.com/astral-sh/uv) for reproducible Python dependency management via `uv.lock`.

### Installation

```bash
# Clone the repository
git clone https://github.com/<your-org>/novelos.git
cd novelos

# Install Python package
python3 -m pip install -e .

# Install frontend dependencies
cd frontend && npm install && cd ..

# Initialize a local database
novelos init-db --db-path acceptance_novel_factory.db
```

### Launch

```bash
# Start API + WebUI together (recommended)
scripts/novelos-service.sh start
```

| Service | URL | Notes |
|---------|-----|-------|
| WebUI | http://127.0.0.1:5173 | Author workspace |
| API Server | http://127.0.0.1:8765 | FastAPI backend |
| API Docs | http://127.0.0.1:8765/docs | Swagger UI |

Override defaults with environment variables:

```bash
LLM_MODE=stub scripts/novelos-service.sh restart api   # switch to stub mode
WEB_PORT=5174 scripts/novelos-service.sh start web      # custom WebUI port
```

### Manual Launch

Start the API server independently:

```bash
novelos api \
  --host 127.0.0.1 \
  --port 8765 \
  --db-path acceptance_novel_factory.db \
  --llm-mode stub
```

Start the frontend independently:

```bash
cd frontend
npm run dev
```

## CLI Reference

Seed demo data:

```bash
novelos --db-path acceptance_novel_factory.db seed-demo --project-id demo
```

Generate a chapter (stub mode):

```bash
novelos --db-path acceptance_novel_factory.db run-chapter \
  --project-id demo \
  --chapter 1 \
  --llm-mode stub \
  --json
```

Check chapter status:

```bash
novelos --db-path acceptance_novel_factory.db status \
  --project-id demo \
  --chapter 1 \
  --json
```

List workflow runs:

```bash
novelos --db-path acceptance_novel_factory.db runs \
  --project-id demo \
  --json
```

Validate configuration:

```bash
novelos --config config/local.yaml config validate --json
```

## Configuration

### LLM Modes

| Mode | Use Case | API Calls |
|------|----------|-----------|
| `stub` | Local demos, testing, development | None — deterministic output |
| `real` | Production generation with real LLM | Paid — requires API key |

### Environment Variables

Novelos reads secrets from OS environment variables or a project-root `.env` file (already gitignored).

Priority: OS env > `.env` > YAML defaults.

```bash
# OpenAI
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# Alternatives
OPENROUTER_API_KEY=your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

### YAML Config

Create `config/local.yaml`:

```yaml
db_path: ./acceptance_real_novel_factory.db
default_llm: default

llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4o-mini
  author:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4o-mini
  editor:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4o-mini

agent_llm:
  planner: default
  screenwriter: default
  author: author
  polisher: default
  editor: editor
  scout: default
  continuity_checker: default
  architect: default
```

Validate before running real generation:

```bash
novelos --config config/local.yaml --llm-mode real config validate --json
```

> **Warning:** Real mode makes paid API calls. Test with a small project first. Never commit real API keys.

## Testing

### Python Backend

```bash
python3 -m pytest -q
```

### Frontend

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test
```

## Documentation

Primary project planning and version documentation lives under `docs/codex/`.

Start with:

- [`docs/codex/README.md`](docs/codex/README.md) — Documentation index
- [`docs/codex/planning/novel-factory-roadmap.md`](docs/codex/planning/novel-factory-roadmap.md) — Product roadmap
- [`docs/codex/next/personal-author-workbench-direction.md`](docs/codex/next/personal-author-workbench-direction.md) — Next product direction

## Repository Notes

- `openclaw-agents/` is a local-only legacy workspace, ignored by Git.
- SQLite databases, WAL files, build output, Python caches, and `node_modules` are gitignored.
- `uv.lock` is committed for reproducible dependency resolution.

## License

No license file is currently included.
