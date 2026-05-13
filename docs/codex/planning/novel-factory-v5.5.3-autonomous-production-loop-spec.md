# v5.5.3 Autonomous Production Loop 规格

## 目标

将系统从"用户手动补资料的工作台"推进到"AI 自动补齐、用户审核发布的生产工厂"。

## 产品责任边界

### 用户只应负责
1. 创建项目
2. 审核/编辑 AI 生成内容
3. 发布/拒绝/返修
4. 必要时手动修订

### 系统 AI 应负责
- 创世生成项目底盘
- 自动补齐缺失资料
- 生成章节批次规划
- 生成章节指令
- 执行章节生产
- 提取记忆更新
- 更新事实账本
- 维护伏笔/角色/世界观状态
- 发现缺口后提出 AI 补齐动作

## 实现范围

### 一、后端：Autonomous Next Action API

**新增 API**：`GET /api/projects/{project_id}/production-next`

返回当前项目的下一步生产建议，结构如下：

```json
{
  "project_id": "...",
  "current_chapter": 1,
  "next_action": {
    "key": "generate_genesis",
    "label": "生成项目设定",
    "description": "...",
    "primary": true,
    "action_url": "...",
    "method": "POST",
    "requires_confirmation": true
  },
  "health": {
    "has_project": true,
    "has_genesis": true,
    "has_approved_genesis": true,
    "has_world_settings": true,
    "has_characters": true,
    "has_outlines": true,
    "has_instructions_for_current_chapter": true,
    "has_pending_memory_updates": true,
    "has_blocking_chapter": true,
    "has_stuck_run": true
  },
  "missing": [
    {
      "key": "world_settings",
      "label": "世界观",
      "severity": "blocking",
      "manual_url": "...",
      "ai_action": {
        "key": "generate_missing_context",
        "label": "让 AI 补齐世界观"
      }
    }
  ],
  "actions": []
}
```

**决策规则**：
1. 项目不存在 → PROJECT_NOT_FOUND
2. 如果有 stuck run 或 blocking/revision chapter → recover_blocked_run
3. 如果没有 approved genesis：
   - 如果没有 genesis draft → generate_genesis
   - 如果有 pending genesis draft → review_genesis
4. 如果缺世界观/角色/大纲/章节指令 → generate_missing_context
5. 如果当前章节 planned 且上下文就绪 → generate_chapter
6. 如果当前章节 reviewed/awaiting_publish → review_chapter
7. 如果有 pending/partial memory update → apply_memory_updates
8. 如果当前批次已完成 → generate_arc_plan / continue_next_chapter

### 二、后端：AI 自动补齐入口

**新增 API**：`POST /api/projects/{project_id}/production/auto-fill`

根据项目当前缺口，让 AI 自动补齐缺失资料。

请求：
```json
{
  "scope": "missing_context",
  "chapter_start": 1,
  "chapter_end": 10,
  "confirm": true
}
```

返回：
```json
{
  "filled": true,
  "scope": "...",
  "created": {
    "world_settings": 3,
    "characters": 5,
    "outlines": 10,
    "instructions": 10,
    "plot_holes": 4
  },
  "warnings": []
}
```

**实现策略**：
- 优先复用已有 Genesis 能力和 repository 方法
- stub 模式下使用确定性生成实现闭环
- 接口和数据结构为 real LLM 留好位置
- 不覆盖用户已有内容
- 缺什么补什么

### 三、后端：章节批次规划 Arc Planning

**新增 API**：`POST /api/projects/{project_id}/production/arc-plan`

请求：
```json
{
  "chapter_start": 11,
  "chapter_end": 20,
  "confirm": true
}
```

行为：
- 读取项目设定、角色、事实账本、记忆更新、已有章节状态
- 为指定章节范围生成：大纲 outline、每章 chapter instruction、必要伏笔 plot holes
- 不重新创世
- 不重写已确认的基础设定

本期先做确定性 stub 版本，重点打通生产循环。

### 四、前端：项目工作台"下一步生产动作"

在 `ProjectOverviewModule` 增加醒目的 Production Next Panel。

显示：
- 当前下一步：例如"生成项目设定""审核创世草案""生成第 1 章""应用记忆更新""恢复阻塞运行"
- 一个主按钮
- 缺口列表（每个缺口提供"让 AI 补齐"和"手动编辑"）
- 当前项目生产健康状态

用户进入项目后，不应该不知道点哪里。这个面板成为项目首页最明显的操作入口。

### 五、前端：缺口提示从"请手动新增"改为"AI 可补齐"

已有 context status / readiness / chapter workspace 中，如果显示缺 world_settings / characters / outlines / instructions：
- 保留缺口提示
- 新增"让 AI 补齐缺失资料"按钮
- 点击调用 `/production/auto-fill`
- 成功后刷新项目工作台和章节状态

### 六、前端：创世文案调整

把"创世"定位为：
- "项目初始化"
- "整本书底盘"
- "只需一次，后续用章节批次规划"

避免用户误解成每 10 章都要创世。

## 测试要求

新增测试文件：`tests/test_v553_autonomous_production_loop.py`

至少覆盖：
1. GET production-next 对新项目返回 generate_genesis
2. 有 pending genesis draft 返回 review_genesis
3. approved genesis 但缺章节指令返回 generate_missing_context 或 generate_arc_plan
4. 当前章节 planned 且上下文就绪返回 generate_chapter
5. 有 blocking chapter 返回 recover_blocked_run
6. 有 pending memory updates 返回 apply_memory_updates
7. POST auto-fill missing_context 会创建缺失 world_settings / characters / outlines / instructions
8. auto-fill 不覆盖已有用户内容
9. POST arc-plan 生成 11-20 章 instructions
10. 前端源码测试：ProjectOverviewModule 或 ProductionNextPanel 包含"下一步""让 AI 补齐""生成章节计划"等关键文案

## 验证命令

```bash
python3 -m pytest tests/test_v553_autonomous_production_loop.py -q
python3 -m pytest -q

cd frontend
npm run typecheck
npm run lint
npm run build
```

## 文档更新

- 新增：`docs/codex/planning/novel-factory-v5.5.3-autonomous-production-loop-spec.md`
- 更新：`README.md`、`README.zh-CN.md`、`docs/codex/README.md`、`AGENTS.md`、`CLAUDE.md`

## 接口兼容性

- 不破坏现有 API envelope 模式：`{ ok, error, data }`
- 不破坏现有章节工作流
- 不删除用户内容
- 不把世界观/角色/大纲等模块移除，它们从"主录入入口"转为"查看/编辑/审核入口"
