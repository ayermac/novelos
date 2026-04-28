# Novelos

面向长篇小说创作的 AI 生产工作台。

Novelos 将 FastAPI 后端、LangGraph 章节工作流、SQLite 项目存储、React 作者工作台和 CLI 工具整合在一起，用于章节生成、审核、风格管理、项目上下文维护和运行诊断。

当前基线：**v5.2.0**，已验证 **1416/1416 pytest 通过**，前端 TypeScript 检查通过，前端生产构建通过。

## 功能概览

- 创建和管理小说项目、章节、世界观、角色和大纲。
- 使用 LangGraph 工作流执行章节生产。
- 支持本地演示用的 stub 模式，以及 OpenAI 兼容接口的 real 模式。
- 记录工作流运行、Agent 产物、Token 用量、错误和审核状态。
- 提供 React 作者工作台，用于日常创作、章节阅读和项目上下文编辑。
- 保留 CLI 能力，用于自动化、批量生产、审核、风格工具和诊断。

## 项目结构

```text
frontend/              React + Vite 作者工作台
novel_factory/api/     FastAPI 应用、路由依赖、API 模型
novel_factory/db/      SQLite schema、迁移、Repository
novel_factory/workflow LangGraph 章节工作流与 checkpoint
novel_factory/llm/     Stub 与 OpenAI 兼容 LLM Provider
novel_factory/cli_app/ CLI 命令实现
tests/                 Python 回归测试与版本验收测试
docs/codex/            产品规格、路线图和版本历史
```

当前主生产路径已经切到 LangGraph。`Dispatcher` 和 `dispatch/` 仍作为兼容路径保留，用于旧 CLI 能力和历史工作流。

## 环境要求

- Python 3.9+
- Node.js 18+
- npm

可选但推荐：

- `uv`：通过 `uv.lock` 获得更稳定的 Python 依赖复现。

## 安装

安装 Python 包和依赖：

```bash
python3 -m pip install -e .
```

安装前端依赖：

```bash
cd frontend
npm install
```

初始化本地数据库：

```bash
novelos init-db --db-path acceptance_novel_factory.db
```

## 本地运行

以演示模式启动 API：

```bash
novelos api \
  --host 127.0.0.1 \
  --port 8765 \
  --db-path acceptance_novel_factory.db \
  --llm-mode stub
```

启动前端：

```bash
cd frontend
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173
```

## 常用 CLI 命令

创建演示数据：

```bash
novelos --db-path acceptance_novel_factory.db seed-demo --project-id demo
```

用演示模式生成章节：

```bash
novelos --db-path acceptance_novel_factory.db run-chapter \
  --project-id demo \
  --chapter 1 \
  --llm-mode stub \
  --json
```

查看章节状态：

```bash
novelos --db-path acceptance_novel_factory.db status \
  --project-id demo \
  --chapter 1 \
  --json
```

查看工作流运行记录：

```bash
novelos --db-path acceptance_novel_factory.db runs \
  --project-id demo \
  --json
```

验证配置：

```bash
novelos --config config/local.yaml config validate --json
```

## 真实 LLM 模式

真实模式使用 OpenAI 兼容 Provider。Novelos 不要求把真实 API Key 写进 YAML；建议把密钥放在系统环境变量或项目根目录的 `.env` 文件中。

环境变量读取优先级：

1. 系统环境变量
2. 项目根目录 `.env`
3. YAML 默认值

创建或编辑 `.env`：

```bash
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# 可选供应商：
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

创建本地配置文件，例如 `config/local.yaml`：

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

如果使用 OpenRouter 或 DeepSeek，结构保持一致，只需要替换环境变量名和模型名：

```yaml
llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: OPENROUTER_BASE_URL
    api_key_env: OPENROUTER_API_KEY
    model: openai/gpt-4o-mini
```

启动真实生成前，先校验配置：

```bash
novelos --config config/local.yaml --llm-mode real config validate --json
```

如果还没有安装 `novelos` 命令，可以使用源码入口：

```bash
python3 -m novel_factory.cli --config config/local.yaml --llm-mode real config validate --json
```

启动真实模式 API：

```bash
novelos api \
  --host 127.0.0.1 \
  --port 8765 \
  --db-path acceptance_real_novel_factory.db \
  --config config/local.yaml \
  --llm-mode real
```

使用 CLI 真实生成章节：

```bash
novelos --config config/local.yaml --llm-mode real run-chapter \
  --project-id demo \
  --chapter 1 \
  --json
```

真实模式会产生 API 费用。建议先用小项目测试，确认模型、Base URL 和 API Key 都正确，再运行长流程。

不要提交真实 API Key。`.env` 已被 Git 忽略。

## 测试

运行完整 Python 测试：

```bash
python3 -m pytest -q
```

运行 v5.2 专项验收测试：

```bash
python3 -m pytest \
  tests/test_v52_phase_a.py \
  tests/test_v52_phase_b.py \
  tests/test_v52_phase_c.py \
  tests/test_v52_phase_d.py \
  -q
```

运行前端检查：

```bash
cd frontend
npm run typecheck
npm run build
```

当前已验证基线：

```text
pytest: 1416/1416 passed
frontend typecheck: passed
frontend build: passed
```

## 文档

主要产品规划和版本文档位于：

```text
docs/codex/
```

建议优先阅读：

- `docs/codex/README.md`
- `docs/codex/novel-factory-roadmap.md`
- `docs/codex/novel-factory-v5.2-product-completion-real-llm-closure-spec.md`

## 仓库说明

- `openclaw-agents/` 是仅保留在本地的旧 Agent 工作区，已被 Git 忽略。
- 本地 SQLite 数据库、WAL 文件、构建产物、Python 缓存和前端依赖目录都已忽略。
- `uv.lock` 已提交，用于依赖复现。

## License

当前仓库尚未包含 License 文件。
