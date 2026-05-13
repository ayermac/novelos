# v3.1 LLM Profiles & Agent Routing 规划

## Summary

v3.1 的目标是支持不同 Agent 使用不同的大模型 API、key、base_url 和 model。

当前系统主要是一个全局 LLM 配置：

```yaml
llm:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  api_key: ...
  model: gpt-4o-mini
```

这会导致 Planner、Author、Polisher、Editor、Scout、Architect 等 Agent 全部共用同一个模型。小说生产工厂进入批次生产后，不同 Agent 的模型需求会明显分化：

- Planner 需要结构规划能力。
- Author 需要长文本创作能力。
- Polisher 需要中文表达与风格能力。
- Editor 需要严谨审核与结构化输出能力。
- Scout / Secretary 可使用更便宜的模型。
- Architect 可使用更强推理模型。

因此 v3.1 必须引入 LLM profile 与 Agent 路由。

## Goals

v3.1 必须支持：

- 项目内 `.env` 文件维护 API key。
- YAML 配置默认 LLM profile。
- YAML 配置各 Agent 使用哪个 LLM profile。
- Agent 未单独配置时回退默认 LLM。
- `stub` 模式下所有 Agent 使用 StubLLM。
- `real` 模式下按 Agent 路由真实 Provider。
- CLI 可诊断 LLM 路由配置，但不得泄露 key。

## Non-Goals

v3.1 不做：

- 多 Provider fallback。
- Provider 健康检查。
- token 成本统计。
- 预算控制。
- 自动降级。
- 模型测速。
- Web UI。
- Redis / Celery / Kafka。
- 云端 secret manager。

这些能力放到后续生产治理版本。

## Configuration Design

### .env

项目根目录可以维护一个本地 `.env` 文件：

```bash
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

OPENROUTER_API_KEY=sk-or-xxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

DEEPSEEK_API_KEY=sk-ds-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

要求：

- `.env` 只存 secret 和本地 endpoint。
- `.env` 不应提交到 git。
- 可以提供 `.env.example`，但必须使用占位值。
- `config show` / `doctor` / JSON 输出不得打印明文 key。

### llm profiles

建议在项目配置文件中新增：

```yaml
llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4o-mini
    temperature: 0.7
    max_tokens: 4096

  planner:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4.1
    temperature: 0.5
    max_tokens: 4096

  author:
    provider: openai_compatible
    base_url_env: OPENROUTER_BASE_URL
    api_key_env: OPENROUTER_API_KEY
    model: anthropic/claude-3.7-sonnet
    temperature: 0.8
    max_tokens: 12000

  polisher:
    provider: openai_compatible
    base_url_env: DEEPSEEK_BASE_URL
    api_key_env: DEEPSEEK_API_KEY
    model: deepseek-chat
    temperature: 0.6
    max_tokens: 6000

  editor:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4.1-mini
    temperature: 0.2
    max_tokens: 4096
```

也允许直接写 `base_url`，但不建议直接写 `api_key`：

```yaml
llm_profiles:
  default:
    provider: openai_compatible
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-4o-mini
```

### agent routing

新增 Agent 到 profile 的映射：

```yaml
default_llm: default

agent_llm:
  planner: planner
  screenwriter: planner
  author: author
  polisher: polisher
  editor: editor
  scout: default
  secretary: default
  continuity_checker: editor
  architect: planner
```

规则：

- 如果 Agent 在 `agent_llm` 中有配置，使用对应 profile。
- 如果 Agent 没有配置，使用 `default_llm`。
- 如果 `default_llm` 缺失，使用 `default` profile。
- 如果 profile 不存在，`real` 模式必须清晰失败。
- 如果 profile 缺 key，`real` 模式必须清晰失败。
- `stub` 模式忽略 profile 和 key，所有 Agent 使用 StubLLM。

## Runtime Design

新增：

```text
novel_factory/llm/router.py
novel_factory/llm/profiles.py
```

核心接口：

```python
class LLMRouter:
    def for_agent(self, agent_id: str) -> LLMProvider:
        ...
```

行为：

1. 读取 `llm_profiles`。
2. 读取 `default_llm`。
3. 读取 `agent_llm`。
4. 根据 Agent 找到 profile。
5. 从 `.env` / 环境变量读取 `api_key_env` 和 `base_url_env`。
6. 构造 `OpenAICompatibleProvider`。
7. 缓存 provider，避免重复创建。

Dispatcher 不应再只持有一个全局 `llm`。建议改为：

```python
dispatcher = Dispatcher(repo=repo, llm_router=router)
```

在执行 Agent 时：

```python
llm = llm_router.for_agent("author")
agent = AuthorAgent(repo, llm)
```

为了兼容现有测试，可以保留：

```python
Dispatcher(repo, llm=stub_llm)
```

兼容策略：

- 如果传入单个 `llm`，则所有 Agent 使用该 llm。
- 如果传入 `llm_router`，则按 Agent 路由。
- 二者都传时，优先 `llm_router`，或直接报配置冲突；具体策略需在实现规格中明确。

## .env Loading

v3.1 可以使用 `python-dotenv`，也可以实现一个极简 `.env` loader。

加载优先级建议：

```text
OS 环境变量 > 项目根目录 .env > --config YAML > package 默认配置
```

注意：

- `.env` 中的变量只进入运行时，不写回配置文件。
- 不要把 `.env` 内容打印到日志。
- `.env.example` 只放变量名和占位值。

## CLI Design

保留：

```bash
--llm-mode stub|real
```

新增诊断命令可在后续实现：

```bash
novelos llm profiles --json
novelos llm route --agent author --json
novelos llm validate --json
```

输出必须隐藏 key：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "agent": "author",
    "profile": "author",
    "provider": "openai_compatible",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": "***",
    "model": "anthropic/claude-3.7-sonnet"
  }
}
```

## Example Config

推荐创建：

```text
config/local.yaml
.env
.env.example
```

`config/local.yaml`：

```yaml
default_llm: default

llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4o-mini

  author:
    provider: openai_compatible
    base_url_env: OPENROUTER_BASE_URL
    api_key_env: OPENROUTER_API_KEY
    model: anthropic/claude-3.7-sonnet

agent_llm:
  author: author
  planner: default
  screenwriter: default
  polisher: default
  editor: default
```

`.env.example`：

```bash
OPENAI_API_KEY=replace-me
OPENAI_BASE_URL=https://api.openai.com/v1

OPENROUTER_API_KEY=replace-me
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

## Test Plan

v3.1 实现时至少覆盖：

1. `.env` 可加载 API key。
2. OS 环境变量优先于 `.env`。
3. Agent 有单独配置时使用专属 profile。
4. Agent 无单独配置时使用 default profile。
5. profile 不存在时 real 模式失败。
6. api key 缺失时 real 模式失败。
7. stub 模式忽略真实 key。
8. Dispatcher 为 Author/Editor 等 Agent 获取不同 LLMProvider。
9. `config show` / `llm route` 不泄露 key。
10. 旧测试中传单个 StubLLM 仍兼容。

## Acceptance Criteria

v3.1 通过必须满足：

- 不同 Agent 可以配置不同 `base_url`、`api_key_env`、`model`。
- Agent 未单独配置时使用默认 LLM。
- `.env` 可以维护本地 API key。
- `.env.example` 存在且不含真实 key。
- `real` 模式缺 key 清晰失败。
- `stub` 模式无需 key。
- 所有 JSON 输出稳定为 `{ok,error,data}`。
- 不引入 fallback、健康检查、成本统计等 v4 能力。

