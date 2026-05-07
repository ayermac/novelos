# Novelos

AI-powered novel production workbench for long-form fiction projects.

Novelos combines a FastAPI backend, LangGraph chapter workflow, SQLite project storage, a React author workspace, and CLI tools for chapter generation, review, style, project context, and operational checks.

## What It Does

- Creates and manages novel projects, chapters, world settings, characters, and outlines.
- Runs chapter production through a LangGraph workflow.
- Supports stub mode for local demos and real mode for OpenAI-compatible LLM providers.
- Tracks workflow runs, artifacts, token usage, errors, and review state.
- Provides a React author workspace for day-to-day writing and project context editing.
- Keeps CLI access for automation, batch operations, review tools, style tools, and diagnostics.

## Architecture

```text
frontend/              React + Vite author workspace
novel_factory/api/     FastAPI app, route dependencies, API models
novel_factory/db/      SQLite schema, migrations, repositories
novel_factory/workflow LangGraph chapter workflow and checkpointing
novel_factory/llm/     Stub and OpenAI-compatible LLM providers
novel_factory/cli_app/ CLI command implementation
tests/                 Python regression and acceptance tests
docs/codex/            Product specs, roadmap, and project history
```

The main production path is now LangGraph-based. `Dispatcher` and `dispatch/` are still retained as compatibility paths for older CLI capabilities and historical workflows.

## Requirements

- Python 3.9+
- Node.js 18+
- npm

Optional but recommended:

- `uv` for reproducible Python dependency management via `uv.lock`

## Setup

Install Python package and dependencies:

```bash
python3 -m pip install -e .
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

Initialize a local database:

```bash
novelos init-db --db-path acceptance_novel_factory.db
```

## Run Locally

Use the service helper for day-to-day development:

```bash
scripts/novelos-service.sh start      # start API + WebUI
scripts/novelos-service.sh stop       # stop API + WebUI
scripts/novelos-service.sh restart    # restart API + WebUI
scripts/novelos-service.sh status     # show service status
scripts/novelos-service.sh logs       # show recent logs
```

By default it uses `acceptance_novel_factory.db`, `config/local.yaml`, `LLM_MODE=real`, API port `8765`, and WebUI port `5173`.
Override with environment variables, for example:

```bash
LLM_MODE=stub scripts/novelos-service.sh restart api
WEB_PORT=5174 scripts/novelos-service.sh start web
```

Start the API server in demo mode:

```bash
novelos api \
  --host 127.0.0.1 \
  --port 8765 \
  --db-path acceptance_novel_factory.db \
  --llm-mode stub
```

Start the frontend:

```bash
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Common CLI Commands

Create demo data:

```bash
novelos --db-path acceptance_novel_factory.db seed-demo --project-id demo
```

Generate a chapter in demo mode:

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

## Real LLM Mode

Real mode uses OpenAI-compatible providers. Novelos never needs raw API keys in YAML; keep secrets in OS environment variables or the project-root `.env` file.

Environment loading priority:

1. OS environment variables
2. Project-root `.env`
3. YAML defaults

Create or edit `.env`:

```bash
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# Optional alternatives:
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

Create a local config file, for example `config/local.yaml`:

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

For OpenRouter or DeepSeek, keep the same shape and change the env var names and model:

```yaml
llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: OPENROUTER_BASE_URL
    api_key_env: OPENROUTER_API_KEY
    model: openai/gpt-4o-mini
```

Validate the configuration before starting real generation:

```bash
novelos --config config/local.yaml --llm-mode real config validate --json
```

If the `novelos` command is not installed yet, use the source entry:

```bash
python3 -m novel_factory.cli --config config/local.yaml --llm-mode real config validate --json
```

Start the API in real mode:

```bash
novelos api \
  --host 127.0.0.1 \
  --port 8765 \
  --db-path acceptance_real_novel_factory.db \
  --config config/local.yaml \
  --llm-mode real
```

Generate a chapter from the CLI in real mode:

```bash
novelos --config config/local.yaml --llm-mode real run-chapter \
  --project-id demo \
  --chapter 1 \
  --json
```

Real mode makes paid API calls. Start with a small test project and confirm the model, base URL, and key are correct before running longer workflows.

Do not commit real API keys. `.env` is ignored by Git.

## Testing

Run the full Python test suite:

```bash
python3 -m pytest -q
```

Run frontend checks:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

## Documentation

Primary project planning documentation lives under:

```text
docs/codex/
```

Start with:

- `docs/codex/README.md`
- `docs/codex/novel-factory-roadmap.md`

## Repository Notes

- `openclaw-agents/` is treated as a local-only legacy workspace and is ignored by Git.
- Local SQLite databases, WAL files, build output, Python caches, and frontend dependencies are ignored.
- `uv.lock` is committed for reproducibility.

## License

No license file is currently included.
