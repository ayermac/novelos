# 网文工厂生产级就绪评估报告

## 评估日期：2026-04-06

---

## 一、当前系统成熟度评估

### 已完成的基础设施 ✅

| 层级 | 组件 | 成熟度 |
|------|------|--------|
| 数据层 | 数据库设计、表结构、索引 | 90% |
| 工具层 | db_common.py、命令封装 | 85% |
| 流程层 | 状态机、任务调度、熔断 | 80% |
| 质量层 | 五层审校、伏笔验证、问题模式 | 75% |
| 安全层 | 权限边界、消息队列 | 70% |

### 核心缺失（生产级必需）

| 缺失项 | 严重程度 | 影响范围 |
|--------|----------|----------|
| **LLM Prompt 工程** | 🔴 致命 | 所有 Agent 的输出质量 |
| **上下文组装器** | 🔴 致命 | 长篇创作的一致性 |
| **测试框架** | 🟠 严重 | 系统稳定性 |
| **监控告警** | 🟠 严重 | 生产运维 |
| **数据备份** | 🟡 中等 | 数据安全 |
| **配置管理** | 🟡 中等 | 灵活部署 |

---

## 二、核心缺失分析

### 1. 🔴 LLM Prompt 工程（最关键）

**问题**：当前 SKILL.md 只是"操作手册"，不是"Prompt 模板"。

**现状**：
```
SKILL.md 内容 = 工作流程 + 命令列表 + 禁止事项
```

**应该**：
```
Prompt = 角色设定 + 能力边界 + 工作流程 + 输出格式 + 示例
```

**影响**：
- Agent 无法像真人一样思考和决策
- 输出质量高度不稳定
- 依赖 LLM 自己理解工作流程

**解决方案**：为每个 Agent 创建结构化 Prompt 模板

```python
# 示例：Editor 的 Prompt 结构
EDITOR_PROMPT = """
## 角色定义
你是一个极其苛刻的网文质检编辑。你的职责是找出章节中的逻辑漏洞、人物降智、设定矛盾。
默认态度：不信任，而不是"差不多就行"。

## 核心原则
1. 必须在每章中至少找到一个逻辑问题
2. 找不到任何问题 = 检查不够严格 = 任务失败
3. 伏笔验证是强制步骤，不执行 = 任务失败

## 五层审校流程
[详细流程...]

## 输出格式
{
  "pass": true/false,
  "score": 0-100,
  "scores": {
    "setting": 0-25,
    "logic": 0-25,
    ...
  },
  "issues": [...],
  "suggestions": [...]
}

## 示例
[高质量输出示例...]
"""
```

---

### 2. 🔴 上下文组装器（Context Builder）

**问题**：长篇创作时，LLM 无法记住前文细节。

**现状**：
- Author 读取上一章状态卡
- Author 读取世界观、角色设定
- 但这些信息可能超过 LLM 的有效窗口

**应该**：
```python
class ContextBuilder:
    """按优先级组装上下文，确保核心信息不丢失"""
    
    def build_context(self, project, chapter, token_limit=8000):
        context = []
        
        # 1. 必须包含（优先级最高）
        context.append(self.get_writing_instruction(project, chapter))
        context.append(self.get_state_card(project, chapter - 1))
        context.append(self.get_plots_to_resolve(project, chapter))
        
        # 2. 重要包含
        context.append(self.get_death_penalty_rules())  # 死刑红线
        context.append(self.get_anti_patterns())        # 问题模式
        context.append(self.get_character_summary(project))
        
        # 3. 动态压缩（根据 token 限制）
        remaining_tokens = token_limit - self.count_tokens(context)
        if remaining_tokens > 1000:
            context.append(self.get_recent_chapters(project, chapter - 1, n=1))
        
        return self.compress_to_limit(context, token_limit)
```

**实现要点**：
- 优先级队列：死刑红线 > 写作指令 > 状态卡 > 问题模式 > 设定
- 动态压缩：根据 token 限制智能截断
- 关键实体提取：只保留本章涉及的角色的精简版设定

---

### 3. 🟠 测试框架

**问题**：没有自动化测试，任何改动都可能破坏系统。

**需要的测试**：

```python
# tests/test_workflow.py

def test_chapter_creation_flow():
    """测试完整的章节创作流程"""
    # 1. Planner 创建指令
    instruction = create_instruction(project, chapter, ...)
    assert instruction['status'] == 'pending'
    
    # 2. Author 创作草稿
    draft = save_draft(project, chapter, content)
    assert draft['word_count'] >= 2000
    
    # 3. Editor 质检
    review = add_review(project, chapter, ...)
    assert review['score'] >= 0

def test_fuse_mechanism():
    """测试熔断机制"""
    # 模拟 3 次退回
    for i in range(3):
        update_chapter(project, chapter, 'revision')
    
    # 第 4 次应该触发熔断
    result = consistency_check(project, chapter)
    assert result['action'] == 'abandon'

def test_plot_verification():
    """测试伏笔验证"""
    # 创建伏笔
    add_plot(project, "P001", "long", ...)
    
    # 指令要求兑现但内容未兑现
    verify_result = verify_plots(project, chapter)
    assert verify_result['plot_score_deduction'] >= 20
```

---

### 4. 🟠 监控告警

**问题**：系统运行时无法知道是否正常。

**需要监控的指标**：

| 指标 | 阈值 | 告警级别 |
|------|------|----------|
| 任务失败率 | > 10% | 🟡 Warning |
| 平均质检分数 | < 80 | 🟡 Warning |
| 伏笔兑现率 | < 70% | 🟠 Error |
| 熔断触发次数 | > 0 | 🔴 Critical |
| 任务超时率 | > 5% | 🟡 Warning |
| 平均创作时间 | > 10min | 🟡 Warning |

**实现**：
```python
# shared/tools/monitoring.py

class SystemMonitor:
    def collect_metrics(self, project):
        return {
            "task_failure_rate": self.calc_failure_rate(project),
            "avg_review_score": self.calc_avg_score(project),
            "plot_resolution_rate": self.calc_plot_rate(project),
            "fuse_count": self.count_fuses(project),
            # ...
        }
    
    def check_alerts(self, metrics):
        alerts = []
        if metrics["avg_review_score"] < 80:
            alerts.append({
                "level": "warning",
                "message": f"平均质检分数过低: {metrics['avg_review_score']}"
            })
        # ...
        return alerts
```

---

### 5. 🟡 数据备份

**问题**：没有备份机制，数据丢失风险。

**解决方案**：
```bash
# 定时备份脚本
# scripts/backup.sh

#!/bin/bash
BACKUP_DIR="/backups/novel_factory"
DATE=$(date +%Y%m%d_%H%M%S)

# 完整备份
sqlite3 shared/data/novel_factory.db ".backup ${BACKUP_DIR}/novel_factory_${DATE}.db"

# 保留最近 7 天的备份
find ${BACKUP_DIR} -name "*.db" -mtime +7 -delete

# 导出关键数据为 JSON（用于版本控制）
python3 scripts/export_data.py --output ${BACKUP_DIR}/export_${DATE}.json
```

---

### 6. 🟡 配置管理

**问题**：硬编码的阈值、参数分散在各处。

**解决方案**：
```yaml
# config/factory.yaml

production:
  quality:
    pass_score: 90
    score_weights:
      setting: 25
      logic: 25
      poison: 20
      text: 15
      pacing: 15
  
  fuse:
    max_revision_count: 3
    task_timeout_minutes: 30
    max_retry_count: 3
  
  plot:
    missing_resolve_penalty: 20
    missing_plant_penalty: 10
    extra_record_penalty: 5
  
  monitoring:
    alert_thresholds:
      task_failure_rate: 0.1
      avg_review_score: 80
      plot_resolution_rate: 0.7
```

---

## 三、Agent 能力评估

### 真人工作水平要求

| 能力维度 | 真人水平 | 当前系统 | 差距 |
|----------|----------|----------|------|
| **逻辑推理** | 能发现复杂逻辑漏洞 | 能检测简单模式 | 🔴 大 |
| **创造性** | 能设计创新情节 | 需要明确指令 | 🔴 大 |
| **一致性维护** | 记住前文细节 | 依赖状态卡 | 🟡 中 |
| **质量判断** | 有主观审美 | 有规则引擎 | 🟢 小 |
| **异常处理** | 能应对意外情况 | 熔断机制 | 🟡 中 |

### 各 Agent 能力差距

#### Planner (总编)

| 能力 | 真人 | 当前 | 差距分析 |
|------|------|------|----------|
| 宏观规划 | 500章大纲一气呵成 | 需要逐章规划 | 🔴 缺乏长线规划能力 |
| 伏笔设计 | 自然的伏笔呼应 | 机械式填坑 | 🔴 缺乏情感设计 |
| 节奏控制 | 张弛有度 | 需要显式指令 | 🟡 需要节奏模板 |

**解决方案**：
- 创建大纲规划 Prompt 模板
- 添加"情感曲线"规划工具
- 引入节奏控制模板（高潮-低谷-高潮）

#### Author (执笔)

| 能力 | 真人 | 当前 | 差距分析 |
|------|------|------|----------|
| 文字表现力 | 风格多变 | AI 痕迹明显 | 🔴 需要去 AI 化训练 |
| 场景描写 | 细节丰富 | 容易空洞 | 🟡 需要场景模板 |
| 对话设计 | 角色性格鲜明 | 容易脸谱化 | 🟡 需要角色声音库 |

**解决方案**：
- 建立"去 AI 化"写作指南
- 创建场景描写模板库
- 为每个角色建立"声音档案"

#### Editor (质检)

| 能力 | 真人 | 当前 | 差距分析 |
|------|------|------|----------|
| 逻辑审查 | 能发现深层矛盾 | 能检测显性问题 | 🟡 需要深层逻辑规则 |
| 审美判断 | 有主观偏好 | 规则引擎 | 🟢 已有反模式库 |
| 建议给出 | 具体可行 | 需要改进 | 🟡 需要修复模板库 |

**解决方案**：
- 深化逻辑检查规则（因果关系、时间线）
- 建立问题修复模板库
- 添加"优秀示例"参考库

---

## 四、数据表角色管理评估

### 当前表结构分析

| 表类别 | 表数量 | 维护者 | 是否需要细分 |
|--------|--------|--------|-------------|
| 核心业务 | 8 | 多角色 | ❌ 不需要 |
| 任务调度 | 1 | Dispatcher | ❌ 不需要 |
| 高级功能 | 6 | 系统/Planner | ⚠️ 可考虑 |
| 问题模式 | 2 | 系统 | ❌ 不需要 |
| 消息队列 | 1 | 多角色 | ❌ 不需要 |

### 建议的调整

#### 1. 不需要细分角色管理

**理由**：
- 当前权限边界已清晰（Planner 管规划，Author 只读，Editor 只写质检）
- `agent_messages` 已解决跨 Agent 异步通信
- 数据隔离通过 `project_id` 实现

#### 2. 可优化的点

**创建角色表**（可选）：
```sql
CREATE TABLE agent_roles (
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    role_type TEXT NOT NULL,  -- 'planner', 'author', 'editor', 'dispatcher', 'scout', 'secretary', 'architect'
    permissions TEXT,  -- JSON: ["read:chapters", "write:chapters", ...]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**但不是必需的**，因为：
- Agent 角色是固定的，不需要动态分配
- 权限已经通过各 Agent 的 `tools/db.py` 硬编码
- 引入角色表会增加复杂度但收益有限

#### 3. 建议的数据治理

**问题**：`learned_patterns` 和 `best_practices` 表数据未激活

**解决方案**：
```python
# 在 Editor 质检完成后自动记录问题
def add_review(...):
    # 现有逻辑...
    
    # 自动记录问题模式
    for issue in issues:
        if issue.get('category'):
            PatternLearner().record_pattern(
                project, chapter, 
                issue['category'], 
                issue['description']
            )
    
    # 高分章节记录最佳实践
    if score >= 95:
        BestPracticeManager().record_practice(
            project, chapter, 
            "high_score_pattern",
            summary
        )
```

---

## 五、生产级就绪路线图

### Phase 1：核心补强（必须）

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 创建 LLM Prompt 模板 | P0 | 高 | 🔴 致命 |
| 实现 Context Builder | P0 | 中 | 🔴 致命 |
| 添加基础测试 | P0 | 中 | 🟠 严重 |

### Phase 2：稳定性提升

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 监控告警系统 | P1 | 中 | 🟠 严重 |
| 数据备份机制 | P1 | 低 | 🟡 中等 |
| 配置管理 | P1 | 低 | 🟡 中等 |

### Phase 3：能力增强

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 角色"声音档案" | P2 | 高 | 🟡 中等 |
| 场景模板库 | P2 | 中 | 🟡 中等 |
| 问题修复模板库 | P2 | 中 | 🟡 中等 |

### Phase 4：高级功能

| 任务 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| 长线大纲规划 | P3 | 高 | 🟡 中等 |
| 情感曲线规划 | P3 | 中 | 🟡 中等 |
| 多风格写作 | P3 | 高 | 🟡 中等 |

---

## 六、结论

### 当前系统定位

**不是一个"生产级网文工厂"，而是一个"可运行的网文原型系统"**

差距在于：
1. **LLM Prompt 缺失**：Agent 无法像真人一样工作
2. **上下文管理不足**：长篇创作会丢失细节
3. **无测试保障**：任何改动都可能破坏系统

### 优先级建议

```
立即（本周）：
  ├── 为每个 Agent 创建结构化 Prompt 模板
  ├── 实现 Context Builder
  └── 添加核心流程测试

短期（2周内）：
  ├── 添加监控告警
  └── 实现数据备份

中期（1月内）：
  ├── 配置管理
  ├── 激活 learned_patterns
  └── 创建写作模板库

长期（按需）：
  ├── 角色声音档案
  ├── 长线规划能力
  └── 多风格支持
```

### 角色管理建议

**不需要细分角色管理表**。理由：
1. 当前权限边界已清晰
2. 角色是固定的，不需要动态分配
3. 引入角色表会增加复杂度但收益有限

**但需要**：
1. 激活现有的 `learned_patterns` 和 `best_practices` 表
2. 为每个 Agent 创建高质量的 Prompt 模板
3. 建立写作模板库和修复模板库
