<div align="center">

# Novelos

**AI 驱动的长篇小说生产工作台**

[English](README.md) | 中文

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5+-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Workflow-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

面向长篇小说创作的端到端 AI 生产工作台：规划故事弧线、通过 LangGraph 流水线生成章节、审校润色文稿、管理项目上下文 —— 同时支持 CLI 和 Web 工作台。

[功能特性](#功能特性) | [架构概览](#架构概览) | [快速开始](#快速开始) | [CLI 参考](#cli-参考) | [配置说明](#配置说明) | [测试](#测试) | [文档](#文档)

</div>

---

## 功能特性

- **章节生产流水线** — LangGraph 工作流，包含 planner、screenwriter、author、polisher、editor、publisher 节点
- **项目上下文管理** — 世界观、角色、势力、大纲、伏笔、章节指令的完整 CRUD
- **双 LLM 模式** — Stub 模式用于本地开发和演示；Real 模式支持 OpenAI 兼容供应商（OpenAI、OpenRouter、DeepSeek）
- **作者工作台** — React + Vite Web UI，用于日常创作、章节浏览和项目上下文编辑
- **自主生产循环** — AI 驱动的批量章节生成，支持逐步控制、暂停/恢复、预算护栏
- **Token 预算护栏** — 单章/项目/自动生产 session 级 token 上限，超预算显式停机
- **LLM 可靠性** — 限流和超时指数退避重试，retry/timeout 参数可配置
- **工作流可观测性** — 运行追踪、产物日志、Token 用量、错误状态、审核记录
- **CLI 工具集** — 自动化、批量操作、审核工具、风格工具、配置校验、诊断
- **一键启动** — 服务脚本统一启动/停止 API + WebUI

## 架构概览

```
                        ┌──────────────────────┐
                        │   作者工作台          │
                        │   React + Vite SPA   │
                        └──────────┬───────────┘
                                   │ REST / SSE
                        ┌──────────▼───────────┐
                        │     FastAPI 服务      │
                        │   路由 / 服务层       │
                        └───┬────────┬────┬─────┘
                            │        │    │
               ┌────────────┘        │    └────────────┐
               ▼                     ▼                 ▼
    ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐
    │  LangGraph       │  │   LLM Provider   │  │    CLI      │
    │  章节工作流       │  │  Stub / OpenAI   │  │   工具集    │
    │  (StateGraph)    │  │  兼容接口        │  │             │
    └────────┬─────────┘  └──────────────────┘  └─────────────┘
             │
    ┌────────▼─────────┐
    │   SQLite + WAL   │
    │  项目、运行、     │
    │  章节等数据       │
    └──────────────────┘
```

| 层级 | 技术栈 | 用途 |
|------|-------|------|
| 前端 | React 18 + TypeScript + Vite | 作者工作台 SPA |
| 后端 | FastAPI (async) | REST API、SSE 流式推送、依赖注入 |
| 工作流 | LangGraph StateGraph | 章节生产流水线编排 |
| LLM | Stub / OpenAI 兼容 | 可插拔 LLM Provider，内置重试和预算 |
| 数据库 | SQLite + WAL | 项目存储、工作流 checkpoint |
| CLI | Python 入口 | 自动化、批量操作、诊断 |

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 18+
- npm

可选：[`uv`](https://github.com/astral-sh/uv) 用于通过 `uv.lock` 实现可复现的 Python 依赖管理。

### 安装

```bash
# 克隆仓库
git clone https://github.com/<your-org>/novelos.git
cd novelos

# 安装 Python 包
python3 -m pip install -e .

# 安装前端依赖
cd frontend && npm install && cd ..

# 初始化本地数据库
novelos init-db --db-path acceptance_novel_factory.db
```

### 启动

```bash
# 一键启动 API + WebUI（推荐）
scripts/novelos-service.sh start
```

| 服务 | URL | 说明 |
|------|-----|------|
| WebUI | http://127.0.0.1:5173 | 作者工作台 |
| API 服务 | http://127.0.0.1:8765 | FastAPI 后端 |
| API 文档 | http://127.0.0.1:8765/docs | Swagger UI |

通过环境变量覆盖默认值：

```bash
LLM_MODE=stub scripts/novelos-service.sh restart api   # 切换到 stub 模式
WEB_PORT=5174 scripts/novelos-service.sh start web      # 自定义 WebUI 端口
```

### 手动启动

单独启动 API 服务：

```bash
novelos api \
  --host 127.0.0.1 \
  --port 8765 \
  --db-path acceptance_novel_factory.db \
  --llm-mode stub
```

单独启动前端：

```bash
cd frontend
npm run dev
```

## CLI 参考

创建演示数据：

```bash
novelos --db-path acceptance_novel_factory.db seed-demo --project-id demo
```

用 stub 模式生成章节：

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

## 配置说明

### LLM 模式

| 模式 | 用途 | API 调用 |
|------|------|---------|
| `stub` | 本地演示、测试、开发 | 无 — 确定性输出 |
| `real` | 使用真实 LLM 生产生成 | 付费 — 需要 API Key |

### 环境变量

Novelos 从系统环境变量或项目根目录的 `.env` 文件读取密钥（已被 Git 忽略）。

优先级：系统环境变量 > `.env` > YAML 默认值。

```bash
# OpenAI
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# 可选供应商
OPENROUTER_API_KEY=your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

### YAML 配置

创建 `config/local.yaml`：

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

启动真实生成前，先校验配置：

```bash
novelos --config config/local.yaml --llm-mode real config validate --json
```

> **注意：** Real 模式会产生 API 费用。建议先用小项目测试，确认模型、Base URL 和 API Key 都正确。不要提交真实 API Key。

## 测试

### Python 后端

```bash
python3 -m pytest -q
```

### 前端

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test
```

## 文档

主要产品规划和版本文档位于 `docs/codex/`。

建议优先阅读：

- [`docs/codex/README.md`](docs/codex/README.md) — 文档索引
- [`docs/codex/planning/novel-factory-roadmap.md`](docs/codex/planning/novel-factory-roadmap.md) — 产品路线图
- [`docs/codex/next/personal-author-workbench-direction.md`](docs/codex/next/personal-author-workbench-direction.md) — 下一阶段产品方向

## 仓库说明

- `openclaw-agents/` 是仅保留在本地的旧 Agent 工作区，已被 Git 忽略。
- 本地 SQLite 数据库、WAL 文件、构建产物、Python 缓存和 `node_modules` 都已忽略。
- `uv.lock` 已提交，用于可复现的依赖解析。

## 许可证

当前仓库尚未包含许可证文件。
