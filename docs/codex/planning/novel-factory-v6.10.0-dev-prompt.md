# v6.10.0 Skill 知识化与 LLM Function Calling 重构

## 版本目标

将 Skill 架构从"Python 代码执行器"重构为**双层体系**：

1. **知识层（Knowledge Skills）**：Markdown 领域知识文档，LLM 可主动咨询
2. **执行层（Code Skills）**：Python 确定性检查器，保持现有 validator 模式

通过 Function Calling 让 LLM 在规划、写作、审核时**按需获取领域知识**，实现"Skill 即规范"。

核心原则：
- **Skill 是领域知识的载体**：不只是检查器，而是告诉 LLM "应该怎么写"的规范
- **知识共享**：同一个"爽文规范"被 Planner/Screenwriter/Author/Editor 共同使用
- **不替换现有架构**：Code Skills（validator）保持不变，新增 Knowledge Skills 层
- **渐进式**：先创建 1-2 个知识 Skill 试点，验证后扩展

## 当前架构问题

### 1. Skill 只是代码执行器，不是领域知识

当前所有 Skill 是 Python 类：
```python
class ExcitementDensityChecker(BaseSkill):
    def run(self, payload):
        # 代码逻辑检测爽点密度
        if density < threshold:
            return {"ok": False, "data": {"issues": [...]}}
```

**问题**：爽文应该怎么写的规则藏在 Python 代码的 `if/else` 中，LLM 看不到，无法在写作时参考。

### 2. Skill 无法跨 Agent 共享

```yaml
# skills.yaml — 同一个 skill 要手动挂到每个 Agent
agent_skills:
  author:
    after_llm: [excitement-density-checker]   # Author 用
  editor:
    before_review: [excitement-density-checker] # Editor 要重新挂
  planner:
    after_llm: []  # Planner 根本没挂，看不到爽文规则
```

**问题**：知识被锁死在特定 Agent 的特定 stage 里，无法流动。

### 3. LLM 无法主动获取知识

当前模式：Agent 代码 → 跑 skill → 结果注入 prompt → LLM 一次性输出

LLM 不能说"我现在需要参考爽文规范"，它只能被动接收注入的结果。

### 4. LLM 配置页面缺少 Agentic 控制

当前 Settings > LLM 配置只有：
- LLM 模板管理（provider、model、api_key、max_tokens、temperature）
- Agent 路由（agent → template 映射）

缺少：
- Agentic 模式开关（per agent）
- Tool calling 轮次限制
- 知识 Skill 的管理界面

## 数据模型定义

### 知识层数据类

```python
# novel_factory/skills/knowledge_manager.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class KnowledgeSkill:
    """知识 Skill 数据模型"""
    skill_id: str                          # "webnovel-excitement"
    name: str                              # "网文爽感写作规范"
    description: str                       # 供 LLM 理解的描述
    content: str                           # Markdown 正文
    tags: list[str] = field(default_factory=list)           # ["genre:webnovel", "pacing"]
    applicable_agents: list[str] = field(default_factory=list)  # ["planner", "author", ...]
    applicable_genres: list[str] = field(default_factory=list)  # ["xuanhuan", "urban", ...]
    version: str = "1.0"
    source: str = "builtin"                # "builtin" | "user"

@dataclass
class KnowledgeToolResult:
    """知识 Tool 执行结果"""
    content: str                           # Markdown 内容
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Function Calling 数据类

```python
# novel_factory/llm/types.py（新增文件）

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolDefinition:
    """LLM Tool 定义（传给 LLM 的 function schema）"""
    name: str                              # "webnovel-excitement"
    description: str                       # LLM 理解的描述
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema

@dataclass
class ToolCall:
    """LLM 返回的工具调用请求"""
    id: str                                # "call_abc123"
    name: str                              # "webnovel-excitement"
    arguments: dict[str, Any]              # {"context": "当前在写第3章"}

@dataclass
class ToolCallResponse:
    """LLM 带 tool calling 的响应"""
    content: str | None = None             # LLM 文本响应（可能为 None）
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_tokens: int = 0
    rounds_used: int = 0

@dataclass
class AgentToolResponse:
    """Agent 层的 tool calling 最终结果"""
    content: str | None = None             # 最终文本输出
    tool_results: list[dict] = field(default_factory=list)  # 所有 tool 执行记录
    total_tokens: int = 0
    rounds_used: int = 0
    exceeded_rounds: bool = False
```

## 设计方案：双层 Skill 架构

### 架构总览

```text
┌─────────────────────────────────────────────────────┐
│                    Agent 执行流程                     │
│                                                     │
│  ┌──────────────┐    ┌──────────────┐               │
│  │  知识层        │    │  执行层        │               │
│  │  (Markdown)   │    │  (Python)     │               │
│  │              │    │              │               │
│  │  爽文规范.md   │    │  death-penalty│               │
│  │  角色塑造指南.md│    │  word-count   │               │
│  │  对白规范.md   │    │  continuity   │               │
│  │              │    │              │               │
│  │  ↓           │    │  ↓           │               │
│  │  Function     │    │  代码强制执行   │               │
│  │  Calling      │    │  (不变)       │               │
│  │  LLM 主动咨询  │    │  结果注入 msg  │               │
│  └──────────────┘    └──────────────┘               │
└─────────────────────────────────────────────────────┘
```

### Layer 1: 知识层（Knowledge Skills）

**载体**：Markdown 文件 + 元数据 YAML

**目录结构**：
```
novel_factory/skills/knowledge/
├── _index.yaml                    # 知识 Skill 注册表
├── webnovel-excitement/
│   ├── SKILL.md                   # 爽文写作规范（Markdown）
│   └── meta.yaml                  # 元数据
├── character-building/
│   ├── SKILL.md
│   └── meta.yaml
├── dialogue-naturalness/
│   ├── SKILL.md
│   └── meta.yaml
└── pacing-rhythm/
    ├── SKILL.md
    └── meta.yaml
```

**meta.yaml 结构**：
```yaml
skill_id: webnovel-excitement
name: 网文爽感写作规范
description: |
  爽文题材的核心写作规范：钩子密度、节奏曲线、付费点设计、
  读者情绪管理。适用于玄幻、都市、修仙等网文类型。
tags: [genre:webnovel, writing, pacing]
applicable_agents: [planner, screenwriter, author, editor]
applicable_genres: [xuanhuan, urban, xianxia, system]
version: "1.0"
```

**SKILL.md 示例（爽文规范）**：
```markdown
# 网文爽感写作规范

## 核心原则
爽文的本质是"情绪过山车"——持续制造低谷→蓄力→爆发的循环。

## 钩子密度
- 每 500 字至少一个微型钩子（疑问、威胁、反转）
- 每章结尾必须有悬念钩子（未解决的冲突、新信息揭露）
- 付费章前 3 章必须累积足够悬念

## 节奏曲线
- 压抑-爆发比例：3:7（压抑不超过 30%）
- 连续平淡不超过 2 段（每段约 300 字）
- 高潮场景后必须有短暂喘息（读者情绪重置）

## 爽点类型
1. **打脸爽**：反派轻视 → 主角展现实力 → 围观震惊
2. **升级爽**：突破瓶颈 → 获得新能力 → 立即验证
3. **捡漏爽**：别人看不上 → 主角获得 → 后来证明价值连城
4. **装逼爽**：低调出场 → 逐步展露 → 全场震撼

## 付费点设计
- 付费墙前 3 章：密集埋钩子，累积悬念
- 付费墙第 1 章：必须是大爽点或大反转
- 章末最后 100 字：必须留下"不看下一章会死"的悬念

## 禁忌
- 主角连续吃瘪超过 1 章
- 连续 3 个场景没有冲突
- 解决问题太容易（没有代价）
- 反派智商突然下线
```

### Layer 2: 执行层（Code Skills）

**保持不变**，现有 Python validator 继续工作：

```python
class ExcitementDensityChecker(BaseSkill):
    """代码执行器：检测爽点密度是否达标"""
    def run(self, payload):
        # 确定性检查逻辑，不变
        ...
```

执行层 Skill 继续通过 `run_agent_skills()` 在固定 stage 强制执行。

### 两层的关系

```text
知识层（指导）          执行层（验证）
     │                      │
     │  "爽文应该这样写"      │  "你写的爽点密度不够"
     │                      │
     ▼                      ▼
  LLM 写作前参考          LLM 写作后检查
  (Function Calling)      (代码强制执行)
     │                      │
     └──────────┬───────────┘
                │
                ▼
         更高质量的输出
```

## Function Calling 集成

### 知识 Skill → Tool 定义

每个知识 Skill 自动生成一个 Tool 定义：

```python
@dataclass
class KnowledgeToolDefinition:
    name: str          # "webnovel-excitement"
    description: str   # meta.yaml 中的 description
    parameters: dict   # {"genre": {"type": "string", "description": "小说类型"}}
```

LLM 调用时返回该知识 Skill 的完整 Markdown 内容。

### Agent 执行流程（增强后）

```python
class EnhancedAgent(BaseAgent):
    def _execute(self, state):
        # 1. 执行层：强制检查（不变）
        blocking_results = self._run_blocking_skills(state)
        if blocking_results.has_failure:
            return self._handle_blocking(blocking_results)

        # 2. 构建 messages
        messages = self._build_messages(state)
        if blocking_results:
            messages.append({
                "role": "system",
                "content": f"质量检查结果: {blocking_results}"
            })

        # 3. 知识层：LLM 按需咨询
        if self.use_agentic_mode:
            knowledge_tools = self._get_knowledge_tools()
            response = self._invoke_with_tools(
                messages=messages,
                tools=knowledge_tools,
                max_tool_rounds=3,
            )
            return self._process_agentic_response(response)

        # 4. 默认模式：将相关知识直接注入 prompt
        knowledge_context = self._get_relevant_knowledge()
        messages.append({
            "role": "system",
            "content": f"写作规范参考:\n{knowledge_context}"
        })
        return self._process_with_llm(messages)
```

### 知识咨询流程

```text
Author 写作中...
  │
  ├─ 模式 A（agentic_mode=false）：
  │    将所有 applicable 知识 Skill 内容注入 prompt
  │    LLM 一次性输出
  │
  └─ 模式 B（agentic_mode=true）：
       LLM 收到可用知识 Tool 列表
       LLM 自主决定：
         ├─ 调用 "webnovel-excitement" → 获取爽文规范 → 参考写作
         ├─ 调用 "character-building" → 获取角色塑造指南 → 参考写作
         └─ 不调用，直接输出（LLM 认为不需要额外参考）
```

## Phase 分解

### Phase 1: 知识 Skill 基础设施

**目标**: 建立知识 Skill 的存储、加载和注册机制

**新增文件**:
- `novel_factory/skills/knowledge/_index.yaml` — 知识 Skill 注册表
- `novel_factory/skills/knowledge/webnovel-excitement/SKILL.md` — 试点：爽文规范
- `novel_factory/skills/knowledge/webnovel-excitement/meta.yaml` — 元数据
- `novel_factory/skills/knowledge_manager.py` — 知识 Skill 管理器

**_index.yaml 内容**:
```yaml
# novel_factory/skills/knowledge/_index.yaml
skills:
  - webnovel-excitement
  # 后续扩展:
  # - character-building
  # - dialogue-naturalness
  # - pacing-rhythm
```

**KnowledgeManager 核心逻辑**:
```python
class KnowledgeManager:
    """管理知识 Skill 的加载和查询"""

    def __init__(self, knowledge_dir: str):
        self.knowledge_dir = knowledge_dir
        self._skills: dict[str, KnowledgeSkill] = {}
        self._load_all()

    def _load_all(self):
        """扫描目录，加载所有知识 Skill"""
        index_path = os.path.join(self.knowledge_dir, "_index.yaml")
        with open(index_path) as f:
            index = yaml.safe_load(f)

        for skill_id in index.get("skills", []):
            skill_dir = os.path.join(self.knowledge_dir, skill_id)
            meta_path = os.path.join(skill_dir, "meta.yaml")
            skill_path = os.path.join(skill_dir, "SKILL.md")

            if os.path.exists(meta_path) and os.path.exists(skill_path):
                with open(meta_path) as f:
                    meta = yaml.safe_load(f)
                with open(skill_path) as f:
                    content = f.read()

                self._skills[skill_id] = KnowledgeSkill(
                    skill_id=skill_id,
                    name=meta.get("name", skill_id),
                    description=meta.get("description", ""),
                    tags=meta.get("tags", []),
                    applicable_agents=meta.get("applicable_agents", []),
                    applicable_genres=meta.get("applicable_genres", []),
                    content=content,
                )

    def get_for_agent(self, agent_id: str, genre: str = None) -> list[KnowledgeSkill]:
        """获取指定 Agent 可用的知识 Skill"""
        results = []
        for skill in self._skills.values():
            if agent_id not in skill.applicable_agents:
                continue
            if genre and skill.applicable_genres:
                if genre not in skill.applicable_genres:
                    continue
            results.append(skill)
        return results

    def to_tool_definitions(self, skills: list[KnowledgeSkill]) -> list[ToolDefinition]:
        """将知识 Skill 转换为 LLM Tool 定义"""
        return [
            ToolDefinition(
                name=s.skill_id,
                description=s.description,
                parameters={
                    "context": {
                        "type": "string",
                        "description": "当前写作上下文（可选），用于获取更有针对性的建议",
                    }
                },
            )
            for s in skills
        ]

    def execute_tool(self, skill_id: str, arguments: dict) -> ToolResult:
        """执行知识 Tool：返回 Markdown 内容"""
        skill = self._skills.get(skill_id)
        if not skill:
            return ToolResult(content=f"知识 Skill '{skill_id}' 不存在")

        # 可选：根据 context 参数做简单过滤
        context = arguments.get("context", "")
        return ToolResult(
            content=skill.content,
            metadata={"skill_id": skill_id, "name": skill.name},
        )
```

**验证清单**:
- [ ] `_index.yaml` 正确注册知识 Skill
- [ ] `KnowledgeManager` 能加载所有知识 Skill
- [ ] `get_for_agent()` 按 agent 和 genre 过滤
- [ ] `to_tool_definitions()` 生成正确的 Tool 定义
- [ ] `execute_tool()` 返回完整 Markdown 内容

### Phase 1.5: KnowledgeManager 注入与配置

**KnowledgeManager 初始化位置**:

```python
# novel_factory/api/app.py（或 runner 初始化处）

from novel_factory.skills.knowledge_manager import KnowledgeManager

# 在应用启动时创建
knowledge_manager = KnowledgeManager(
    knowledge_dir=os.path.join(os.path.dirname(__file__), "..", "skills", "knowledge")
)

# 注入到需要的地方（通过依赖注入或全局单例）
app.state.knowledge_manager = knowledge_manager
```

**BaseAgent 接收 KnowledgeManager**:

```python
# novel_factory/agent_runtime/base.py

class BaseAgent:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        repo: Any = None,
        skill_registry: Any = None,
        knowledge_manager: KnowledgeManager = None,  # 新增
        agent_config: dict = None,                     # 新增：含 agentic 配置
    ):
        self.llm = llm
        self.repo = repo
        self.skill_registry = skill_registry
        self.knowledge_manager = knowledge_manager
        self.agent_config = agent_config or {}

    @property
    def use_agentic_mode(self) -> bool:
        """是否启用 agentic 模式（从配置读取）"""
        return self.agent_config.get("agentic_mode", False)

    @property
    def max_tool_rounds(self) -> int:
        """最大 tool calling 轮次"""
        return self.agent_config.get("max_tool_rounds", 3)
```

**settings.py 配置变更**:

```python
# novel_factory/config/settings.py

class AgenticAgentConfig(BaseModel):
    """单个 Agent 的 Agentic 配置"""
    agentic_mode: bool = False
    max_tool_rounds: int = 3

class AgenticConfig(BaseModel):
    """全局 Agentic 配置"""
    enabled: bool = False
    agents: dict[str, AgenticAgentConfig] = {
        "planner": AgenticAgentConfig(),
        "screenwriter": AgenticAgentConfig(),
        "author": AgenticAgentConfig(),
        "polisher": AgenticAgentConfig(),
        "editor": AgenticAgentConfig(),
        "memory_curator": AgenticAgentConfig(),
    }

class Settings(BaseModel):
    # ... 现有字段 ...
    llm_profiles: dict[str, LLMProfile] = {}
    agent_llm: dict[str, str] = {}
    agentic: AgenticConfig = AgenticConfig()  # 新增
```

**config/local.yaml 配置示例**:

```yaml
# config/local.yaml
agentic:
  enabled: true
  agents:
    planner:
      agentic_mode: false
      max_tool_rounds: 3
    screenwriter:
      agentic_mode: false
      max_tool_rounds: 3
    author:
      agentic_mode: true       # 试点开启
      max_tool_rounds: 3
    polisher:
      agentic_mode: false
      max_tool_rounds: 3
    editor:
      agentic_mode: false
      max_tool_rounds: 3
```

**配置加载到 Agent 的流程**:

```python
# novel_factory/workflow/nodes.py（或 agent factory 处）

def create_agent(agent_id: str, settings: Settings, ...) -> BaseAgent:
    agent_config = settings.agentic.agents.get(agent_id, AgenticAgentConfig())

    return AgentClass(
        llm=llm_provider,
        repo=repo,
        skill_registry=skill_registry,
        knowledge_manager=knowledge_manager,
        agent_config={
            "agentic_mode": settings.agentic.enabled and agent_config.agentic_mode,
            "max_tool_rounds": agent_config.max_tool_rounds,
        },
    )
```

### Phase 2: LLM Provider Function Calling 支持

**目标**: 让 LLM Provider 支持 tool calling

**修改文件**:
- `novel_factory/llm/provider.py` — 扩展抽象接口
- `novel_factory/llm/openai_compatible.py` — 实现 function calling
- `novel_factory/llm/stub_provider.py` — stub 模式 tool calling

**新增接口**:
```python
class LLMProvider(ABC):
    # 现有接口保持不变
    def invoke_json(messages, schema, ...) -> dict
    def invoke_text(messages, ...) -> str

    # 新增: 支持 tools 的调用
    def invoke_with_tools(
        messages: list,
        tools: list[ToolDefinition],
        tool_choice: str = "auto",
        max_tool_rounds: int = 3,
        **kwargs
    ) -> ToolCallResponse
```

**ToolDefinition**:
```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema
```

**ToolCallResponse**:
```python
@dataclass
class ToolCallResponse:
    content: str | None       # LLM 文本响应
    tool_calls: list[ToolCall] # 工具调用请求
    total_tokens: int         # 总 token 消耗
    rounds_used: int          # 实际使用的轮次

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
```

**StubProvider 实现**:
```python
class StubLLMProvider(LLMProvider):
    def invoke_with_tools(self, messages, tools, **kwargs):
        # Stub 模式：调用所有提供的 tools
        tool_calls = []
        for tool in tools:
            tool_calls.append(ToolCall(
                id=f"stub_{tool.name}",
                name=tool.name,
                arguments={},
            ))
        return ToolCallResponse(
            content=None,
            tool_calls=tool_calls,
            total_tokens=0,
            rounds_used=1,
        )
```

**OpenAICompatibleProvider 实现**:
```python
# novel_factory/llm/openai_compatible.py

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: dict):
        self.config = config
        self._llm = ChatOpenAI(
            model=config.get("model", "gpt-4o"),
            base_url=config.get("base_url"),
            api_key=config.get("api_key"),
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 4096),
        )

    def invoke_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        tool_choice: str = "auto",
        **kwargs
    ) -> ToolCallResponse:
        """带 function calling 的 LLM 调用"""

        # 1. 将 ToolDefinition 转为 LangChain StructuredTool
        lc_tools = []
        for td in tools:
            lc_tools.append(StructuredTool.from_function(
                func=lambda **kwargs: "",  # 占位，实际不执行
                name=td.name,
                description=td.description,
                args_schema=td.parameters,
            ))

        # 2. 绑定 tools 到 LLM
        llm_with_tools = self._llm.bind_tools(lc_tools, tool_choice=tool_choice)

        # 3. 转换 messages 格式
        lc_messages = self._convert_messages(messages)

        # 4. 调用
        response = llm_with_tools.invoke(lc_messages)

        # 5. 解析响应
        tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_{tc['name']}"),
                    name=tc["name"],
                    arguments=tc.get("args", {}),
                ))

        total_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            total_tokens = response.usage_metadata.get("total_tokens", 0)

        return ToolCallResponse(
            content=response.content if not tool_calls else None,
            tool_calls=tool_calls,
            total_tokens=total_tokens,
            rounds_used=1,
        )

    def _convert_messages(self, messages: list[dict]) -> list:
        """将 dict messages 转为 LangChain 消息格式"""
        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                lc_messages.append(SystemMessage(content=msg["content"]))
            elif role == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif role == "assistant":
                if "tool_calls" in msg:
                    # 带 tool_calls 的 assistant 消息
                    lc_messages.append(AIMessage(
                        content=msg.get("content", ""),
                        tool_calls=[
                            {"id": tc.id, "name": tc.name, "args": tc.arguments}
                            for tc in msg["tool_calls"]
                        ],
                    ))
                else:
                    lc_messages.append(AIMessage(content=msg["content"]))
            elif role == "tool":
                lc_messages.append(ToolMessage(
                    content=msg["content"],
                    tool_call_id=msg["tool_call_id"],
                ))
        return lc_messages
```

**验证清单**:
- [ ] `LLMProvider.invoke_with_tools()` 接口定义
- [ ] `OpenAICompatibleProvider` 支持 function calling
- [ ] `StubLLMProvider` 支持 tool calling 响应
- [ ] Token 使用量正确统计

### Phase 3: Agent 集成（知识 + Function Calling）

**目标**: 在 Agent 中集成知识 Skill 和 function calling 循环

**修改文件**:
- `novel_factory/agent_runtime/base.py` — 新增知识管理和 tool calling 方法

**新增方法**:
```python
class BaseAgent:
    def _invoke_with_tools(
        self,
        messages: list,
        tools: list[ToolDefinition],
        tool_executor: callable,
        max_tool_rounds: int = 3,
        **kwargs
    ) -> AgentToolResponse:
        """带 tool calling 的 LLM 调用循环

        1. 调用 LLM (with tools)
        2. 如果 LLM 返回 tool_calls → 执行工具 → 结果加入 messages → 回到 1
        3. 如果 LLM 返回文本响应 → 结束
        """
        messages = list(messages)
        total_tokens = 0

        for round_num in range(max_tool_rounds):
            response = self.llm.invoke_with_tools(
                messages=messages,
                tools=tools,
                **kwargs
            )
            total_tokens += response.total_tokens

            if not response.tool_calls:
                return AgentToolResponse(
                    content=response.content,
                    tool_results=[],
                    total_tokens=total_tokens,
                    rounds_used=round_num + 1,
                )

            # 执行工具调用
            messages.append({"role": "assistant", "tool_calls": response.tool_calls})

            for tc in response.tool_calls:
                result = tool_executor(tc.name, tc.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.content,
                })

        return AgentToolResponse(
            content=None,
            tool_results=[],
            exceeded_rounds=True,
            total_tokens=total_tokens,
            rounds_used=max_tool_rounds,
        )

    def _get_knowledge_context(self, agent_id: str, genre: str = None) -> str:
        """获取所有相关知识 Skill 内容（非 agentic 模式用）"""
        if not self.knowledge_manager:
            return ""

        skills = self.knowledge_manager.get_for_agent(agent_id, genre)
        parts = []
        for s in skills:
            parts.append(f"## {s.name}\n\n{s.content}")
        return "\n\n---\n\n".join(parts)
```

**Author.py 具体集成（与 run_agent_skills 共存）**:

```python
# novel_factory/agents/author.py

class AuthorAgent(BaseAgent):
    agent_id = "author"

    def _execute(self, state):
        # ===== Layer 1: 执行层（Code Skills，强制检查）=====
        # 保持不变，这些是确定性检查
        skill_payload = self._build_skill_payload(state)
        blocking_result = run_agent_skills(
            repo=self.repo,
            skill_registry=self.skill_registry,
            project_id=state.project_id,
            chapter_number=state.chapter_number,
            agent=self.agent_id,
            stage="after_llm",
            payload=skill_payload,
            fail_closed_ids={"death-penalty", "word-count-gate"},
        )
        if blocking_result.has_failure:
            return self._handle_blocking(blocking_result)

        # ===== 构建 messages =====
        messages = self._build_messages(state)

        # 注入阻断性检查结果
        if blocking_result.warnings:
            messages.append({
                "role": "system",
                "content": f"质量检查警告:\n{blocking_result.summary}",
            })

        # ===== Layer 2: 知识层 =====
        genre = self._get_project_genre(state.project_id)

        if self.use_agentic_mode:
            # Agentic 模式：LLM 主动咨询知识 Skill
            knowledge_skills = self.knowledge_manager.get_for_agent(
                self.agent_id, genre
            )
            tool_definitions = self.knowledge_manager.to_tool_definitions(knowledge_skills)

            response = self._invoke_with_tools(
                messages=messages,
                tools=tool_definitions,
                tool_executor=self.knowledge_manager.execute_tool,
                max_tool_rounds=self.max_tool_rounds,
            )
            return self._process_output(response.content, state)

        else:
            # 默认模式：知识内容注入 prompt
            knowledge_context = self._get_knowledge_context(self.agent_id, genre)
            if knowledge_context:
                messages.append({
                    "role": "system",
                    "content": f"写作规范参考（请在创作时遵循以下规范）:\n\n{knowledge_context}",
                })

            # 正常 LLM 调用（单轮）
            llm_response = self.llm.invoke_text(messages=messages)
            return self._process_output(llm_response, state)
```

**与现有 run_agent_skills() 的共存关系**:

```text
Author._execute() 执行流程:

  ┌─────────────────────────────────────────────────────┐
  │ 1. run_agent_skills(stage="after_llm")              │ ← 执行层，不变
  │    ├─ event-coverage-checker (代码检查)              │
  │    ├─ death-penalty (代码检查)                        │
  │    ├─ word-count-gate (代码检查)                      │
  │    ├─ opening-hook-checker (代码检查)                 │
  │    └─ excitement-density-checker (代码检查)           │
  │    → 结果: warnings/failed                           │
  ├─────────────────────────────────────────────────────┤
  │ 2. 知识层注入                                        │
  │    ├─ agentic_mode=false:                            │
  │    │   knowledge_context → 注入 messages             │
  │    └─ agentic_mode=true:                             │
  │        knowledge_tools → 传给 invoke_with_tools()    │
  ├─────────────────────────────────────────────────────┤
  │ 3. LLM 调用                                         │
  │    ├─ agentic_mode=false: invoke_text() 单轮         │
  │    └─ agentic_mode=true: invoke_with_tools() 多轮    │
  └─────────────────────────────────────────────────────┘
```

**项目 genre 获取**:

```python
# BaseAgent 中新增辅助方法
def _get_project_genre(self, project_id: str) -> str | None:
    """从项目配置获取 genre"""
    if not self.repo:
        return None
    try:
        project = self.repo.get_project(project_id)
        return project.genre if project else None
    except Exception:
        return None
```

**验证清单**:
- [ ] `_invoke_with_tools()` 正确执行多轮调用
- [ ] `_get_knowledge_context()` 返回相关知识内容
- [ ] Token 使用量正确统计
- [ ] 超过最大轮次时正确返回

### Phase 4: 前端配置调整

**目标**: 让用户能配置知识 Skill 和 Agentic 模式

#### 4.1 Settings > Skill 管理 — 新增"知识库"子视图

**修改文件**:
- `frontend/src/components/settings/SkillVisibilityPanel.tsx`

**新增子视图**: `knowledge`

```
┌─────────────────────────────────────────────────┐
│  Skill 管理                                      │
│  [概览] [能力库] [编排] [测试] [目录] [知识库] ← 新增 │
│                                                  │
│  ┌─ 知识库 ─────────────────────────────────────┐│
│  │                                              ││
│  │  网文爽感写作规范          [编辑] [预览]       ││
│  │  tags: genre:webnovel, pacing                ││
│  │  适用: planner, screenwriter, author, editor  ││
│  │                                              ││
│  │  角色塑造指南              [编辑] [预览]       ││
│  │  tags: character, writing                    ││
│  │  适用: screenwriter, author, editor          ││
│  │                                              ││
│  │  [+ 新建知识 Skill]                           ││
│  │                                              ││
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**功能**:
- 列出所有知识 Skill（从 `GET /knowledge-skills` 获取）
- 每个 Skill 可查看/编辑 Markdown 内容
- 管理元数据（description、tags、applicable_agents）
- 新建/删除知识 Skill

#### 4.2 Settings > LLM 配置 — 新增 Agentic 控制

**修改文件**:
- `frontend/src/components/settings/SettingsConsoleSections.tsx`（`LlmSettingsSection`）

**新增配置项**:

```
┌─ Agentic 模式 ──────────────────────────────────┐
│                                                  │
│  全局开关: [✓] 启用 Agentic 模式                  │
│                                                  │
│  Agent 级配置:                                    │
│  ┌──────────────┬────────┬──────────────┐        │
│  │ Agent        │ 模式    │ Tool 轮次限制 │        │
│  ├──────────────┼────────┼──────────────┤        │
│  │ planner      │ [关闭 ▾]│ 3            │        │
│  │ screenwriter │ [关闭 ▾]│ 3            │        │
│  │ author       │ [开启 ▾]│ 3            │        │
│  │ polisher     │ [关闭 ▾]│ 3            │        │
│  │ editor       │ [关闭 ▾]│ 3            │        │
│  └──────────────┴────────┴──────────────┘        │
│                                                  │
│  每个 Agent 可选:                                 │
│  - 关闭: 使用默认硬性调用模式                       │
│  - 开启: LLM 可主动咨询知识 Skill                  │
│                                                  │
└──────────────────────────────────────────────────┘
```

#### 4.3 Agent 编排矩阵 — 新增知识列

**修改文件**:
- `frontend/src/components/settings/SkillVisibilityPanel.tsx`（mounts 视图）

**变化**: Agent 编排矩阵新增"知识"列，显示每个 Agent 可用的知识 Skill：

```
┌──────────────┬─────────────────────────┬──────────────────┐
│ Agent        │ 执行层 Skills (stage)    │ 知识层 Skills     │
├──────────────┼─────────────────────────┼──────────────────┤
│ planner      │ after_llm: 2 skills     │ 爽文规范, 节奏指南  │
│ author       │ after_llm: 5 skills     │ 爽文规范, 角色指南  │
│ editor       │ before_review: 17 skills │ 爽文规范, 角色指南  │
└──────────────┴─────────────────────────┴──────────────────┘
```

#### 4.4 API 新增端点

**新增文件**:
- `novel_factory/api/routes/knowledge.py`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/knowledge-skills` | 列出所有知识 Skill |
| GET | `/knowledge-skills/{id}` | 获取单个知识 Skill（含 Markdown 内容） |
| POST | `/knowledge-skills` | 创建知识 Skill |
| PUT | `/knowledge-skills/{id}` | 更新知识 Skill（内容 + 元数据） |
| DELETE | `/knowledge-skills/{id}` | 删除知识 Skill |
| GET | `/knowledge-skills/agent/{agent_id}` | 获取指定 Agent 可用的知识 Skill |

**验证清单**:
- [ ] 知识库子视图可列出/编辑/预览知识 Skill
- [ ] LLM 配置页面可设置 Agentic 模式和轮次限制
- [ ] Agent 编排矩阵显示知识层信息
- [ ] API 端点功能正确

#### 4.5 前端 TypeScript 类型定义

**新增文件**: `frontend/src/types/knowledge.ts`

```typescript
export interface KnowledgeSkillMeta {
  skill_id: string;
  name: string;
  description: string;
  tags: string[];
  applicable_agents: string[];
  applicable_genres: string[];
  version: string;
  source: 'builtin' | 'user';
}

export interface KnowledgeSkillDetail extends KnowledgeSkillMeta {
  content: string;  // Markdown 正文
}

export interface KnowledgeSkillCreateRequest {
  skill_id: string;
  name: string;
  description: string;
  content: string;
  tags?: string[];
  applicable_agents?: string[];
  applicable_genres?: string[];
}

export interface KnowledgeSkillUpdateRequest {
  name?: string;
  description?: string;
  content?: string;
  tags?: string[];
  applicable_agents?: string[];
  applicable_genres?: string[];
}

export interface AgenticAgentConfig {
  agentic_mode: boolean;
  max_tool_rounds: number;
}

export interface AgenticConfig {
  enabled: boolean;
  agents: Record<string, AgenticAgentConfig>;
}
```

**API 调用封装**: `frontend/src/api/knowledge.ts`

```typescript
import { KnowledgeSkillMeta, KnowledgeSkillDetail, KnowledgeSkillCreateRequest } from '../types/knowledge';

const API_BASE = '/api';

export async function listKnowledgeSkills(): Promise<KnowledgeSkillMeta[]> {
  const res = await fetch(`${API_BASE}/knowledge-skills`);
  return res.json();
}

export async function getKnowledgeSkill(id: string): Promise<KnowledgeSkillDetail> {
  const res = await fetch(`${API_BASE}/knowledge-skills/${id}`);
  return res.json();
}

export async function createKnowledgeSkill(data: KnowledgeSkillCreateRequest): Promise<KnowledgeSkillDetail> {
  const res = await fetch(`${API_BASE}/knowledge-skills`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function updateKnowledgeSkill(id: string, data: Partial<KnowledgeSkillCreateRequest>): Promise<KnowledgeSkillDetail> {
  const res = await fetch(`${API_BASE}/knowledge-skills/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteKnowledgeSkill(id: string): Promise<void> {
  await fetch(`${API_BASE}/knowledge-skills/${id}`, { method: 'DELETE' });
}
```

#### 4.6 项目级知识 Skill 覆盖

**现有机制**: 项目已有 `skill-overrides` API（`GET/PUT/DELETE /projects/{id}/skill-overrides`），用于覆盖全局 Skill 配置。

**扩展**: 在项目覆盖中支持知识 Skill 的选择和排除。

```json
// PUT /projects/{id}/skill-overrides
{
  "knowledge_skills": {
    "enabled": ["webnovel-excitement", "character-building"],
    "disabled": ["pacing-rhythm"]
  },
  "existing_fields": "..."
}
```

**项目 Settings UI 扩展**:

```
┌─ 项目知识 Skill ────────────────────────────────┐
│                                                  │
│  基于项目 genre 自动匹配的知识 Skill:              │
│  [✓] 网文爽感写作规范 (auto: genre=xuanhuan)     │
│  [✓] 角色塑造指南 (auto: 通用)                    │
│  [ ] 节奏指南 (手动启用)                          │
│                                                  │
│  说明: 自动匹配基于项目的 genre 设置              │
│  手动覆盖会优先于自动匹配                          │
│                                                  │
└──────────────────────────────────────────────────┘
```

**KnowledgeManager 支持项目覆盖**:

```python
class KnowledgeManager:
    def get_for_agent(
        self,
        agent_id: str,
        genre: str = None,
        project_overrides: dict = None,
    ) -> list[KnowledgeSkill]:
        """获取指定 Agent 可用的知识 Skill（支持项目覆盖）"""
        results = []
        for skill in self._skills.values():
            # 项目级禁用
            if project_overrides:
                disabled = project_overrides.get("knowledge_skills", {}).get("disabled", [])
                if skill.skill_id in disabled:
                    continue

                enabled = project_overrides.get("knowledge_skills", {}).get("enabled", [])
                # 如果有显式启用列表，只使用列表中的
                if enabled and skill.skill_id not in enabled:
                    continue

            if agent_id not in skill.applicable_agents:
                continue
            if genre and skill.applicable_genres:
                if genre not in skill.applicable_genres:
                    continue
            results.append(skill)
        return results
```

### Phase 5: 试点验证

**目标**: 创建 1-2 个知识 Skill，在 Author Agent 上试点

**试点知识 Skill**:
1. `webnovel-excitement` — 网文爽感写作规范
2. `character-building` — 角色塑造指南（可选）

**试点 Agent**: Author
- 原因：Author 直接产出正文，知识 Skill 的价值最直观

**两种模式对比测试**:

| 模式 | 配置 | 预期效果 |
|------|------|---------|
| 旧模式 | `agentic_mode=false` | 知识内容注入 prompt，LLM 一次性输出 |
| 新模式 | `agentic_mode=true` | LLM 可主动咨询知识 Skill，多轮修正 |

**验证清单**:
- [ ] Author（旧模式）正常完成章节，知识内容已注入 prompt
- [ ] Author（新模式）可调用知识 Tool 并利用结果
- [ ] 章节质量对比：新模式 ≥ 旧模式
- [ ] 向后兼容：`agentic_mode=false` 时行为完全不变
- [ ] Token 消耗在可接受范围内

## Agent × Skill 完整映射

### 总览表

| Agent | 职责 | 执行层 (Code Skills) | 知识层 (Knowledge Skills) | 使用方式 |
|-------|------|---------------------|-------------------------|---------|
| **Planner** | 生成章节写作指令 | `chapter-objective-checker`, `foreshadowing-debt` | 爽文规范、节奏指南 | 规划前参考知识，规划后执行检查 |
| **Screenwriter** | 指令拆解为场景 beat | `scene-conflict-checker` | 爽文规范、场景设计指南 | 编剧前参考知识，beat 完成后检查 |
| **Author** | 创作正文 | `event-coverage-checker`, `death-penalty`, `word-count-gate`, `opening-hook-checker`, `excitement-density-checker` | 爽文规范、角色塑造、对白规范 | 写作前参考知识，写完后执行检查 |
| **Polisher** | 清理 AI 味 | `humanizer-zh`(after_llm), `ai-style-detector`, `fact-lock`, `death-penalty`(before_save) | 对白规范 | 润色前参考知识，保存前执行检查 |
| **Editor** | 五层审校 | 17 个 validator（见下表） | 爽文规范、角色塑造、对白规范、节奏指南 | 审核前参考知识，审核中执行全部检查 |
| **Memory Curator** | 记忆抽取 | `memory-patch-validator` | 无 | 仅执行层 |

### Planner（总编/策划）

```text
输入: 项目大纲、上一章记忆、世界设定
输出: 章节写作指令（目标、事件、伏笔、节奏要求）

执行流程:
  ┌─────────────────────────────────────────────────┐
  │ 1. 知识层（写作前参考）                          │
  │    ├─ 爽文规范 → 规划钩子密度和爽点分布           │
  │    └─ 节奏指南 → 规划章节节奏曲线                │
  │    agentic_mode=false: 注入 prompt               │
  │    agentic_mode=true: LLM 按需调用               │
  ├─────────────────────────────────────────────────┤
  │ 2. LLM 生成写作指令                              │
  ├─────────────────────────────────────────────────┤
  │ 3. 执行层（写后检查）                            │
  │    ├─ chapter-objective-checker → 指令是否具体    │
  │    └─ foreshadowing-debt → 伏笔债务检查          │
  └─────────────────────────────────────────────────┘
```

**知识 Skill 价值**: Planner 在规划章节时就知道"爽文需要每 500 字一个钩子"，而不是规划完再被 checker 指出问题。

### Screenwriter（编剧）

```text
输入: 章节写作指令
输出: 场景 beat（目标、冲突、转折、钩子）

执行流程:
  ┌─────────────────────────────────────────────────┐
  │ 1. 知识层（编剧前参考）                          │
  │    ├─ 爽文规范 → 设计场景冲突和钩子              │
  │    └─ 场景设计指南 → beat 结构和节奏              │
  ├─────────────────────────────────────────────────┤
  │ 2. LLM 生成场景 beat                             │
  ├─────────────────────────────────────────────────┤
  │ 3. 执行层（beat 后检查）                         │
  │    └─ scene-conflict-checker → beat 是否有冲突   │
  └─────────────────────────────────────────────────┘
```

### Author（执笔）— 试点 Agent

```text
输入: 场景 beat、写作风格指南、世界设定、角色档案
输出: 章节正文

执行流程:
  ┌─────────────────────────────────────────────────┐
  │ 1. 执行层（写后强制检查）                        │
  │    ├─ event-coverage-checker → 事件覆盖          │
  │    ├─ death-penalty → AI 套话检测（阻断性）       │
  │    ├─ word-count-gate → 字数检查（阻断性）        │
  │    ├─ opening-hook-checker → 开局钩子             │
  │    └─ excitement-density-checker → 爽点密度       │
  ├─────────────────────────────────────────────────┤
  │ 2. 知识层（写作时参考）                          │
  │    ├─ 爽文规范 → 钩子密度、爽点类型、禁忌        │
  │    ├─ 角色塑造指南 → 角色口吻、行为逻辑          │
  │    └─ 对白规范 → 对白自然度、潜台词              │
  │    agentic_mode=false: 全部注入 prompt           │
  │    agentic_mode=true: LLM 自主选择调用           │
  ├─────────────────────────────────────────────────┤
  │ 3. LLM 生成正文                                  │
  │    agentic_mode=true 时可多轮:                   │
  │    写一段 → 调用爽文规范自查 → 修正 → 继续写     │
  └─────────────────────────────────────────────────┘
```

**知识 Skill 价值最大**: Author 是唯一直接产出正文的 Agent。写作前参考"爽文规范"比写完后被 checker 指出问题效率高得多。

### Polisher（润色）

```text
输入: 章节正文
输出: 润色后正文

执行流程:
  ┌─────────────────────────────────────────────────┐
  │ 1. 知识层（润色前参考）                          │
  │    └─ 对白规范 → 润色对白自然度                  │
  ├─────────────────────────────────────────────────┤
  │ 2. 执行层 after_llm                              │
  │    └─ humanizer-zh → 中文去 AI 味                │
  ├─────────────────────────────────────────────────┤
  │ 3. LLM 润色                                      │
  ├─────────────────────────────────────────────────┤
  │ 4. 执行层 before_save                            │
  │    ├─ ai-style-detector → AI 味检测              │
  │    ├─ fact-lock → 事实保留检查                    │
  │    └─ death-penalty → AI 套话检测                 │
  └─────────────────────────────────────────────────┘
```

### Editor（质检）

```text
输入: 润色后正文
输出: 评审报告（通过/退回 + 评分 + issues）

执行流程:
  ┌─────────────────────────────────────────────────┐
  │ 1. 知识层（审核前参考）                          │
  │    ├─ 爽文规范 → 审核爽点密度是否达标            │
  │    ├─ 角色塑造指南 → 审核角色一致性              │
  │    ├─ 对白规范 → 审核对白质量                    │
  │    └─ 节奏指南 → 审核节奏曲线                    │
  ├─────────────────────────────────────────────────┤
  │ 2. 执行层 before_review（17 个 Code Skills）     │
  │    阻断性:                                       │
  │    ├─ death-penalty → AI 套话                    │
  │    ├─ continuity-gate → 叙事连续性               │
  │    ├─ word-count-gate → 字数                     │
  │    └─ chapter-seam → 章节衔接                    │
  │    建议性:                                       │
  │    ├─ ai-style-detector → AI 味                  │
  │    ├─ narrative-quality → 叙事质量               │
  │    ├─ style-bible-checker → 风格合规             │
  │    ├─ show-dont-tell → 展示而非讲述              │
  │    ├─ info-dump-detector → 设定灌输              │
  │    ├─ scene-texture → 场景质感                   │
  │    ├─ dialogue-naturalness → 对白自然度          │
  │    ├─ foreshadowing-debt → 伏笔债务              │
  │    ├─ opening-hook-checker → 开局钩子            │
  │    ├─ excitement-density-checker → 爽点密度      │
  │    ├─ commercial-viability-check → 商业可行性    │
  │    ├─ pacing-profile-check → 节奏配置            │
  │    ├─ character-voice-check → 角色口吻           │
  │    └─ mystery-integrity-check → 悬疑完整性       │
  ├─────────────────────────────────────────────────┤
  │ 3. LLM 五维评分 + 综合评审                       │
  └─────────────────────────────────────────────────┘
```

**知识 Skill 价值**: Editor 审核时不只是看 checker 的数据结果，还能参考"爽文应该怎么写"的规范来给出更专业的评审意见。

### Memory Curator（记忆管理）

```text
输入: 章节正文
输出: 记忆 patch

执行流程:
  ┌─────────────────────────────────────────────────┐
  │ 1. LLM 抽取记忆                                  │
  ├─────────────────────────────────────────────────┤
  │ 2. 执行层                                        │
  │    └─ memory-patch-validator → patch 结构完整    │
  └─────────────────────────────────────────────────┘

知识层: 无（记忆管理不涉及写作规范）
```

## 测试策略

### 测试文件清单

| 文件 | 测试内容 |
|------|---------|
| `tests/test_v610_knowledge_manager.py` | KnowledgeManager 加载、查询、过滤、tool 转换 |
| `tests/test_v610_knowledge_types.py` | KnowledgeSkill、ToolDefinition、ToolCallResponse 数据类 |
| `tests/test_v610_function_calling.py` | LLMProvider.invoke_with_tools() 接口和 StubProvider |
| `tests/test_v610_openai_tool_calling.py` | OpenAICompatibleProvider function calling 集成 |
| `tests/test_v610_agent_tool_loop.py` | _invoke_with_tools() 多轮循环 |
| `tests/test_v610_author_agentic.py` | Author Agent agentic 模式端到端 |
| `tests/test_v610_author_knowledge_inject.py` | Author 非 agentic 模式知识注入 |
| `tests/test_v610_project_knowledge_overrides.py` | 项目级知识 Skill 覆盖 |
| `tests/test_v610_knowledge_api.py` | /knowledge-skills API 端点 |

### 关键测试用例

```python
# tests/test_v610_knowledge_manager.py

def test_load_knowledge_skills():
    """KnowledgeManager 能加载 _index.yaml 中注册的所有知识 Skill"""
    km = KnowledgeManager(knowledge_dir="novel_factory/skills/knowledge")
    assert len(km._skills) >= 1
    assert "webnovel-excitement" in km._skills

def test_get_for_agent_filters():
    """get_for_agent 按 agent 过滤"""
    km = KnowledgeManager(...)
    author_skills = km.get_for_agent("author")
    assert all("author" in s.applicable_agents for s in author_skills)

def test_get_for_agent_genre_filter():
    """get_for_agent 按 genre 过滤"""
    km = KnowledgeManager(...)
    # webnovel-excitement 适用于 xuanhuan
    skills = km.get_for_agent("author", genre="xuanhuan")
    assert any(s.skill_id == "webnovel-excitement" for s in skills)

    # genre=romance 不匹配
    skills = km.get_for_agent("author", genre="romance")
    assert not any(s.skill_id == "webnovel-excitement" for s in skills)

def test_to_tool_definitions():
    """to_tool_definitions 生成正确的 Tool 定义"""
    km = KnowledgeManager(...)
    skills = km.get_for_agent("author")
    tools = km.to_tool_definitions(skills)
    assert len(tools) > 0
    assert tools[0].name == "webnovel-excitement"
    assert tools[0].description  # description 非空

def test_execute_tool_returns_markdown():
    """execute_tool 返回完整 Markdown 内容"""
    km = KnowledgeManager(...)
    result = km.execute_tool("webnovel-excitement", {})
    assert "钩子" in result.content or "爽" in result.content

def test_execute_tool_nonexistent():
    """execute_tool 对不存在的 skill 返回错误提示"""
    km = KnowledgeManager(...)
    result = km.execute_tool("nonexistent", {})
    assert "不存在" in result.content

def test_project_overrides_disable():
    """项目覆盖可以禁用特定知识 Skill"""
    km = KnowledgeManager(...)
    overrides = {"knowledge_skills": {"disabled": ["webnovel-excitement"]}}
    skills = km.get_for_agent("author", project_overrides=overrides)
    assert not any(s.skill_id == "webnovel-excitement" for s in skills)

def test_project_overrides_enable_whitelist():
    """项目覆盖启用白名单模式"""
    km = KnowledgeManager(...)
    overrides = {"knowledge_skills": {"enabled": ["webnovel-excitement"]}}
    skills = km.get_for_agent("author", project_overrides=overrides)
    assert len(skills) == 1
    assert skills[0].skill_id == "webnovel-excitement"


# tests/test_v610_function_calling.py

def test_stub_provider_invoke_with_tools():
    """StubProvider 正确返回 tool_calls"""
    provider = StubLLMProvider()
    tools = [ToolDefinition(name="test-tool", description="test", parameters={})]
    response = provider.invoke_with_tools(messages=[], tools=tools)
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "test-tool"
    assert response.total_tokens == 0

def test_stub_provider_multiple_tools():
    """StubProvider 多个 tool 全部返回"""
    provider = StubLLMProvider()
    tools = [
        ToolDefinition(name="tool-a", description="a", parameters={}),
        ToolDefinition(name="tool-b", description="b", parameters={}),
    ]
    response = provider.invoke_with_tools(messages=[], tools=tools)
    assert len(response.tool_calls) == 2

def test_tool_call_response_dataclass():
    """ToolCallResponse 数据类正确构造"""
    resp = ToolCallResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="t1", arguments={"x": 1})],
        total_tokens=100,
        rounds_used=1,
    )
    assert resp.tool_calls[0].name == "t1"
    assert resp.total_tokens == 100


# tests/test_v610_agent_tool_loop.py

def test_invoke_with_tools_single_round():
    """单轮：LLM 返回文本，不调用 tool"""
    mock_llm = MockLLMProvider(text_response="最终输出")
    agent = create_test_agent(llm=mock_llm)
    response = agent._invoke_with_tools(
        messages=[{"role": "user", "content": "test"}],
        tools=[ToolDefinition(name="t1", description="test")],
        tool_executor=lambda name, args: ToolResult(content="result"),
    )
    assert response.content == "最终输出"
    assert response.rounds_used == 1
    assert response.total_tokens == 0

def test_invoke_with_tools_multi_round():
    """多轮：LLM 第一轮调 tool，第二轮返回文本"""
    mock_llm = MockLLMProvider(
        rounds=[
            ToolCallResponse(tool_calls=[ToolCall(id="c1", name="t1", arguments={})]),
            ToolCallResponse(content="最终输出"),
        ]
    )
    agent = create_test_agent(llm=mock_llm)
    response = agent._invoke_with_tools(
        messages=[{"role": "user", "content": "test"}],
        tools=[ToolDefinition(name="t1", description="test")],
        tool_executor=lambda name, args: ToolResult(content="知识内容"),
    )
    assert response.content == "最终输出"
    assert response.rounds_used == 2

def test_invoke_with_tools_max_rounds_exceeded():
    """超过最大轮次时返回 exceeded_rounds=True"""
    mock_llm = MockLLMProvider(
        always_tool_call=ToolCall(id="c1", name="t1", arguments={})
    )
    agent = create_test_agent(llm=mock_llm)
    response = agent._invoke_with_tools(
        messages=[{"role": "user", "content": "test"}],
        tools=[ToolDefinition(name="t1", description="test")],
        tool_executor=lambda name, args: ToolResult(content="知识内容"),
        max_tool_rounds=2,
    )
    assert response.exceeded_rounds is True
    assert response.rounds_used == 2


# tests/test_v610_author_agentic.py

def test_author_agentic_mode_calls_knowledge():
    """Author agentic 模式下 LLM 可调用知识 Skill"""
    # 设置 agentic_mode=True
    # mock LLM 返回 tool_call（调用 webnovel-excitement）
    # 验证知识内容被传回 LLM
    ...

def test_author_default_mode_injects_knowledge():
    """Author 默认模式下知识内容注入 prompt"""
    # 设置 agentic_mode=False
    # 验证 messages 中包含知识内容
    ...

def test_author_backward_compatible():
    """agentic_mode=False 时行为完全不变（不考虑知识注入的额外 system message）"""
    # mock LLM，对比有无知识注入的输出
    ...
```

## 文件清单

### 新增文件
| 文件 | 用途 |
|------|------|
| `novel_factory/skills/knowledge/_index.yaml` | 知识 Skill 注册表 |
| `novel_factory/skills/knowledge/webnovel-excitement/SKILL.md` | 爽文写作规范 |
| `novel_factory/skills/knowledge/webnovel-excitement/meta.yaml` | 元数据 |
| `novel_factory/skills/knowledge_manager.py` | KnowledgeManager + KnowledgeSkill 数据类 |
| `novel_factory/llm/types.py` | ToolDefinition、ToolCall、ToolCallResponse、AgentToolResponse |
| `novel_factory/api/routes/knowledge.py` | 知识 Skill API |
| `frontend/src/types/knowledge.ts` | 前端 TypeScript 类型定义 |
| `frontend/src/api/knowledge.ts` | 前端 API 调用封装 |
| `tests/test_v610_knowledge_manager.py` | KnowledgeManager 测试 |
| `tests/test_v610_knowledge_types.py` | 数据类测试 |
| `tests/test_v610_function_calling.py` | Function calling 测试 |
| `tests/test_v610_openai_tool_calling.py` | OpenAI provider 测试 |
| `tests/test_v610_agent_tool_loop.py` | Agent tool 循环测试 |
| `tests/test_v610_author_agentic.py` | Author agentic 端到端测试 |
| `tests/test_v610_author_knowledge_inject.py` | Author 知识注入测试 |
| `tests/test_v610_project_knowledge_overrides.py` | 项目覆盖测试 |
| `tests/test_v610_knowledge_api.py` | API 端点测试 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `novel_factory/llm/provider.py` | 新增 `invoke_with_tools()` 抽象接口 |
| `novel_factory/llm/openai_compatible.py` | 实现 function calling（LangChain bind_tools） |
| `novel_factory/llm/stub_provider.py` | 支持 stub 模式 tool calling |
| `novel_factory/agent_runtime/base.py` | 新增 `_invoke_with_tools()`、`_get_knowledge_context()`、`_get_project_genre()`、`knowledge_manager` 属性、`use_agentic_mode` 属性 |
| `novel_factory/agents/author.py` | 试点集成知识 Skill（双模式） |
| `novel_factory/config/settings.py` | 新增 `AgenticConfig`、`AgenticAgentConfig` |
| `novel_factory/config/local.yaml` | 新增 `agentic` 配置段 |
| `novel_factory/workflow/nodes.py` | Agent 创建时注入 knowledge_manager 和 agent_config |
| `novel_factory/api/app.py` | 注册 knowledge 路由 |
| `frontend/src/components/settings/SkillVisibilityPanel.tsx` | 新增"知识库"子视图 |
| `frontend/src/components/settings/SettingsConsoleSections.tsx` | LLM 配置新增 Agentic 控制 |
| `frontend/src/components/project/ProjectSettingsModule.tsx` | 项目设置新增知识 Skill 覆盖 |

## 验收标准

### P0: 知识 Skill 基础设施
- [ ] KnowledgeManager 能加载和查询知识 Skill
- [ ] 知识 Skill 有完整的 Markdown 内容和元数据
- [ ] `_index.yaml` 正确注册所有知识 Skill

### P1: Function Calling 基础设施
- [ ] `LLMProvider.invoke_with_tools()` 接口定义
- [ ] `OpenAICompatibleProvider` 支持 function calling
- [ ] `StubLLMProvider` 支持 tool calling 响应
- [ ] 多轮 tool calling 循环正确执行

### P2: Agent 集成
- [ ] Author（旧模式）知识内容注入 prompt 正常工作
- [ ] Author（新模式）LLM 可主动调用知识 Tool
- [ ] 阻断性 Code Skill 仍由代码强制执行（不受影响）
- [ ] Token 使用量正确统计

### P3: 前端配置
- [ ] 知识库子视图可列出/编辑/预览知识 Skill
- [ ] LLM 配置页面可设置 Agentic 模式
- [ ] Agent 编排矩阵显示知识层信息

### P4: 试点验证
- [ ] Author 使用知识 Skill 完成章节
- [ ] 向后兼容：旧模式行为不变
- [ ] 章节质量 ≥ 硬性调用模式

## 风险和缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 不参考知识内容 | 质量无提升 | 旧模式将知识注入 prompt 作为保底 |
| 知识 Skill 内容质量差 | 误导 LLM | 人工审核 + 版本管理 |
| Token 消耗增加 | 成本上升 | 限制 `max_tool_rounds`，按需加载 |
| 前端改造范围大 | 开发周期长 | Phase 4 可延后，先用 API 验证 |
| 两层架构复杂度 | 维护成本 | 知识层是纯文件，无代码依赖 |

## 成本预估

**当前模式（每章）**:
- LLM 调用: 5 次（Planner + Screenwriter + Author + Polisher + Editor）
- Token 消耗: ~10K tokens

**知识注入模式（每章，agentic_mode=false）**:
- LLM 调用: 5 次（不变）
- Token 消耗: ~13K tokens（知识内容注入 prompt，增加 30%）

**Agentic 模式（每章，Author 试点）**:
- LLM 调用: 5 + K 次（Author 增加 K 轮 tool calling，K≤3）
- Token 消耗: ~15K tokens（增加 50%）

## 后续演进

v6.10.0 建立双层架构后，后续可以：

1. **扩充知识库**：添加更多领域知识 Skill（悬疑写作、科幻世界观、言感情感线等）
2. **Genre 自动匹配**：根据项目 genre 自动加载对应知识 Skill
3. **知识 Skill 版本管理**：支持 A/B 测试不同版本的写作规范
4. **用户自定义知识**：用户上传自己的写作规范作为知识 Skill
5. **全 Agent 启用 Agentic**：验证 Author 后扩展到 Planner/Screenwriter/Editor
6. **知识 Skill 间引用**：一个知识 Skill 可以引用另一个（如"爽文规范"引用"节奏指南"）

## 实施记录

### 已完成的额外工作

**实时事件队列（EventQueue）**:
- 新增 `novel_factory/workflow/event_queue.py` — 线程安全内存队列
- 替代 DB 轮询，SSE 端点优先使用 EventQueue，降级到 DB 轮询
- `log_execution_event()` 同时写 DB 和 EventQueue

**正文流式输出**:
- 新增 `novel_factory/llm/openai_streaming.py` — 流式调用实现
- `LLMProvider.invoke_text_stream()` 接口
- Author Agent 通过 `on_text_chunk` 回调推送 `text_chunk` 事件
- 前端 `WorkflowTimeline` 实时渲染流式文本

**日志清理**:
- EventQueue 过滤 `started`/`completed` 重复事件
- timeline API 过滤 `node_message` 和 `task_log` 噪音
- 时间戳统一为 ISO 8601 格式

**legacy 清理**:
- 删除 `skill_packages/` 整个目录
- 删除 `import_bridge.py`、`import_models.py`、`openclaw_readiness.py`
- 删除 `cli_app/commands/skill_import.py`
- 清理 `skills/registry.py` 死代码
- 删除 5 个失效测试文件

**前端增强**:
- `WorkflowTimeline` 事件分组（LLM 调用合并、Function Calling 合并）
- 质量问题高亮（黄色）、知识事件高亮（绿色）
- `text_chunk` 流式文本实时渲染
- `useSSEStream` 重写（统一事件处理、断线重连）
- 新增事件标签（5 个 v6.10.0 事件类型）
