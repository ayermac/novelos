# v6.10.0 LLM Function Calling 重构开发提示

## 版本目标

将 Skill 架构从"代码硬性调用"重构为"LLM 可调用的工具"，实现 Agentic Skill 模式。

## 当前架构问题

### 1. Skill 是被动的
- 当前所有 Skill 由 Agent 代码在固定阶段硬性调用
- LLM 无法感知 Skill 的存在，无法主动选择调用
- 无法根据上下文动态决定使用哪些 Skill

### 2. LLM Provider 不支持 Function Calling
- `LLMProvider` 接口仅有 `invoke_json()` 和 `invoke_text()`
- 无 `tools`、`bind_tools`、`tool_choice` 参数
- `OpenAICompatibleProvider` 底层使用 LangChain 但未启用 tool calling

### 3. 单轮 Prompt-Response 模式
- Agent 发送完整 prompt → LLM 返回完整响应
- 无中间 tool-calling 循环
- 无法实现"LLM 思考 → 调用工具 → 基于结果继续思考"

## 重构方案

### Phase 1: LLM Provider 扩展（基础设施）

**目标**: 让 LLM Provider 支持 function calling

**修改文件**:
- `novel_factory/llm/provider.py` - 扩展抽象接口
- `novel_factory/llm/openai_compatible.py` - 实现 function calling
- `novel_factory/llm/router.py` - 支持 tool 路由

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
        **kwargs
    ) -> ToolCallResponse
```

**ToolDefinition 结构**:
```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema
```

**ToolCallResponse 结构**:
```python
@dataclass
class ToolCallResponse:
    content: str | None  # LLM 文本响应
    tool_calls: list[ToolCall]  # 工具调用请求
    
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
```

### Phase 2: Skill Tool 包装层

**目标**: 将现有 Skill 包装成 LLM 可调用的 Tool

**新增文件**:
- `novel_factory/skills/tool_adapter.py` - Skill → Tool 适配器

**核心逻辑**:
```python
class SkillToolAdapter:
    """将 BaseSkill 包装成 LLM Tool"""
    
    def __init__(self, skill: BaseSkill):
        self.skill = skill
    
    def to_tool_definition(self) -> ToolDefinition:
        """生成 Tool 定义（name, description, parameters）"""
        return ToolDefinition(
            name=self.skill.skill_id,
            description=self.skill.description,
            parameters=self._infer_parameters()
        )
    
    def execute(self, arguments: dict) -> ToolResult:
        """执行 Skill 并返回结果"""
        result = self.skill.run(arguments)
        return ToolResult(
            content=json.dumps(result),
            metadata={"skill_id": self.skill.skill_id}
        )
```

**参数推断策略**:
- 从 `BaseSkill.run(payload)` 的文档字符串推断
- 从 Skill 的 `input_schema` 类属性获取（新增）
- 从 `skills.yaml` 的 `parameters` 配置获取

### Phase 3: Agent Agentic Loop

**目标**: 实现 Agent 的 tool-calling 循环

**修改文件**:
- `novel_factory/agent_runtime/base.py` - 扩展 BaseAgent

**新增方法**:
```python
class BaseAgent:
    def _invoke_with_tools(
        self,
        messages: list,
        tools: list[SkillToolAdapter],
        max_tool_rounds: int = 5,
        **kwargs
    ) -> AgentToolResponse:
        """带 tool calling 的 LLM 调用
        
        实现循环:
        1. 调用 LLM (with tools)
        2. 如果 LLM 返回 tool_calls → 执行工具 → 将结果加入 messages → 回到 1
        3. 如果 LLM 返回文本响应 → 结束循环
        """
        tool_registry = {t.skill.skill_id: t for t in tools}
        messages = list(messages)
        
        for round in range(max_tool_rounds):
            response = self.llm_provider.invoke_with_tools(
                messages=messages,
                tools=[t.to_tool_definition() for t in tools],
                **kwargs
            )
            
            if not response.tool_calls:
                # LLM 返回文本响应，循环结束
                return AgentToolResponse(
                    content=response.content,
                    tool_results=[]
                )
            
            # 执行工具调用
            messages.append({"role": "assistant", "tool_calls": response.tool_calls})
            
            for tc in response.tool_calls:
                adapter = tool_registry.get(tc.name)
                if adapter:
                    result = adapter.execute(tc.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.content
                    })
        
        # 达到最大轮次
        return AgentToolResponse(content=None, tool_results=[], exceeded_rounds=True)
```

### Phase 4: Agent 迁移（渐进式）

**策略**: 逐个 Agent 迁移，保持向后兼容

**迁移顺序**（按复杂度递增）:
1. **Planner** - 最简单，2 个技能
2. **Screenwriter** - 1 个技能
3. **Author** - 5 个技能，有阻断逻辑
4. **Polisher** - 复杂，有 transform 和多阶段
5. **Editor** - 最复杂，18 个技能，动态调度

**迁移模式**:
```python
class PlannerAgent(BaseAgent):
    def _execute(self, state):
        # 旧模式: 硬编码调用
        # skill_result = run_agent_skills(...)
        
        # 新模式: LLM 决定调用
        tools = self._get_available_tools()  # 获取可用 Skill Tools
        response = self._invoke_with_tools(
            messages=self._build_messages(state),
            tools=tools
        )
        
        # 处理 LLM 响应和 tool 结果
        return self._process_response(response, state)
```

### Phase 5: Skill 增强

**目标**: 让 Skill 提供更丰富的元数据供 LLM 决策

**修改文件**:
- `novel_factory/skills/base.py` - 扩展 BaseSkill

**新增属性**:
```python
class BaseSkill(ABC):
    # 现有属性
    skill_id: str
    skill_type: str
    version: str
    
    # 新增: LLM Tool 相关
    description: str = ""  # 技能描述，供 LLM 理解
    input_schema: dict = {}  # 输入参数 JSON Schema
    output_schema: dict = {}  # 输出结果 JSON Schema
    usage_examples: list[dict] = []  # 使用示例
    tags: list[str] = []  # 标签，用于分类
```

## 文件清单

### 新增文件
| 文件 | 用途 |
|------|------|
| `novel_factory/skills/tool_adapter.py` | Skill → Tool 适配器 |
| `novel_factory/agent_runtime/tool_loop.py` | Tool calling 循环实现 |
| `tests/test_v610_tool_adapter.py` | Tool 适配器测试 |
| `tests/test_v610_tool_loop.py` | Tool 循环测试 |
| `tests/test_v610_planner_agentic.py` | Planner Agentic 模式测试 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `novel_factory/llm/provider.py` | 新增 `invoke_with_tools()` 接口 |
| `novel_factory/llm/openai_compatible.py` | 实现 function calling |
| `novel_factory/llm/router.py` | 支持 tool 路由配置 |
| `novel_factory/skills/base.py` | 新增 Tool 元数据属性 |
| `novel_factory/agent_runtime/base.py` | 新增 `_invoke_with_tools()` |
| `novel_factory/agents/planner.py` | 首个迁移 Agent |
| `novel_factory/config/skills.yaml` | 新增 Tool 配置 |

## 验收标准

### P0: 基础设施
- [ ] `LLMProvider.invoke_with_tools()` 接口定义
- [ ] `OpenAICompatibleProvider` 支持 function calling
- [ ] `SkillToolAdapter` 能将 Skill 包装成 Tool
- [ ] Tool calling 循环能正确执行多轮调用

### P1: 首个 Agent 迁移
- [ ] Planner 使用 Agentic 模式调用技能
- [ ] 向后兼容：旧模式仍可工作
- [ ] 测试覆盖 tool calling 全流程

### P2: 文档和配置
- [ ] 更新 AGENTS.md 架构说明
- [ ] 更新 CHANGELOG.md
- [ ] skills.yaml 支持 Tool 配置

## 风险和注意事项

1. **LLM 可靠性**: LLM 可能不调用必要的 Skill，需要兜底机制
2. **成本控制**: 多轮 tool calling 增加 API 调用次数
3. **向后兼容**: 旧模式必须保留，渐进式迁移
4. **性能**: Tool calling 循环可能增加延迟
5. **测试复杂度**: 需要 mock LLM 的 tool calling 响应

## 参考实现

- LangChain Tool Calling: https://python.langchain.com/docs/modules/agents/
- OpenAI Function Calling: https://platform.openai.com/docs/guides/function-calling
- Anthropic Tool Use: https://docs.anthropic.com/claude/docs/tool-use
