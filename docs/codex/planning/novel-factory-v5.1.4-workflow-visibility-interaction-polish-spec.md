# Novel Factory v5.1.4 - Workflow Visibility & Interaction Polish

## 版本信息
- **版本**: v5.1.4
- **发布日期**: 2026-04-27
- **状态**: ✅ 已验收
- **测试基线**: 1311/1311 通过

## 背景

### v5.1.3 遗留问题
v5.1.3 实现了作者主流程闭环，用户可以生成章节并查看正文。但用户不理解为什么章节直接变成 `published` 状态，看不到中间的工作流步骤（编剧、执笔、润色、审核、发布）。

### 演示模式困惑
用户不清楚当前是演示模式还是真实模式，不理解为什么生成速度很快但内容质量不高。演示模式说明分散，缺乏统一提示。

### 生成交互粗糙
生成过程中缺乏进度反馈，成功/失败/阻塞状态显示不清晰，用户无法快速理解结果并采取下一步行动。

## 目标

### 核心目标
1. **演示模式说明清楚**: 全局提示演示模式，解释 stub 生成机制
2. **工作流可视化**: 显示 5 个 Agent 步骤的时间线和状态
3. **生成交互优化**: Loading 状态、步骤 skeleton、结果卡片、下一步引导

### 非目标
- 不涉及真实 LLM 调用（v5.1.5）
- 不涉及工作流实时事件流（未来版本）
- 不涉及多用户协作

## 后端实现

### 1. 运行详情 API

**端点**: `GET /api/runs/{run_id}`

**响应**:
```json
{
  "ok": true,
  "data": {
    "run_id": "run_abc123",
    "project_id": "dpcq",
    "project_name": "斗破苍穹",
    "chapter_number": 1,
    "workflow_status": "completed",
    "chapter_status": "published",
    "llm_mode": "stub",
    "started_at": "2026-04-27T10:00:00Z",
    "completed_at": "2026-04-27T10:00:05Z",
    "error_message": null,
    "steps": [
      {
        "key": "screenwriter",
        "label": "编剧",
        "description": "规划章节场景和情节",
        "status": "completed",
        "error_message": null
      },
      {
        "key": "author",
        "label": "执笔",
        "description": "撰写章节正文",
        "status": "completed",
        "error_message": null
      },
      {
        "key": "polisher",
        "label": "润色",
        "description": "优化文字表达",
        "status": "completed",
        "error_message": null
      },
      {
        "key": "editor",
        "label": "审核",
        "description": "检查内容质量",
        "status": "completed",
        "error_message": null
      },
      {
        "key": "publish",
        "label": "发布",
        "description": "发布章节内容",
        "status": "completed",
        "error_message": null
      }
    ]
  }
}
```

**实现要点**:
- 从 `workflow_runs` 表读取运行元数据
- 从 `chapter.status` 推导步骤状态
- 当前 timeline 是推导的，不是实时事件流
- 步骤状态映射：
  - `pending`: 章节状态 < 步骤对应状态
  - `running`: 章节状态 = 步骤对应状态
  - `completed`: 章节状态 > 步骤对应状态
  - `failed`: 运行状态 = failed
  - `blocked`: 运行状态 = blocked

**状态路由表**:
```python
STATUS_ROUTE = {
    "planned": "screenwriter",
    "scripted": "author",
    "drafted": "polisher",
    "polished": "editor",
    "review": "editor",
    "published": "publish",
}

STATUS_TO_AGENT = {v: k for k, v in STATUS_ROUTE.items()}
```

### 2. Agent 步骤定义

**5 个 Agent 步骤**:
1. **编剧 (screenwriter)**: 规划章节场景和情节
2. **执笔 (author)**: 撰写章节正文
3. **润色 (polisher)**: 优化文字表达
4. **审核 (editor)**: 检查内容质量
5. **发布 (publish)**: 发布章节内容

**步骤常量**:
```python
AGENT_STEPS = [
    {"key": "screenwriter", "label": "编剧", "description": "规划章节场景和情节"},
    {"key": "author", "label": "执笔", "description": "撰写章节正文"},
    {"key": "polisher", "label": "润色", "description": "优化文字表达"},
    {"key": "editor", "label": "审核", "description": "检查内容质量"},
    {"key": "publish", "label": "发布", "description": "发布章节内容"},
]
```

## 前端实现

### 1. RunDetail 页面

**路由**: `/runs/:runId`

**功能**:
- 显示运行基本信息（项目、章节、状态、时间）
- 显示工作流步骤时间线
- 显示演示模式提示（stub 模式）
- 操作按钮（查看正文、继续生成、返回项目）

**布局**:
```
┌─────────────────────────────────────┐
│ 运行详情                             │
├─────────────────────────────────────┤
│ [演示模式提示]                       │
├─────────────────────────────────────┤
│ 基本信息                             │
│ 项目: XXX | 章节: X | 状态: 已完成   │
│ 开始时间: XXX | 完成时间: XXX        │
├─────────────────────────────────────┤
│ 工作流步骤                           │
│ ✓ 编剧 - 规划章节场景和情节          │
│ ✓ 执笔 - 撰写章节正文                │
│ ✓ 润色 - 优化文字表达                │
│ ✓ 审核 - 检查内容质量                │
│ ✓ 发布 - 发布章节内容                │
├─────────────────────────────────────┤
│ [查看正文] [继续生成下一章] [返回]   │
└─────────────────────────────────────┘
```

**步骤状态图标**:
- `completed`: ✓ (绿色)
- `running`: ● (蓝色，动画)
- `failed`: ✗ (红色)
- `blocked`: ! (黄色)
- `pending`: ○ (灰色)

### 2. Run 页面增强

**演示模式提示**:
```
┌─────────────────────────────────────┐
│ ⚠️ 当前为演示模式                    │
│ 生成速度快，内容由本地 Stub 模板生成 │
│ 不代表真实创作质量。如需真实生成，   │
│ 请在配置中心配置 LLM 并以            │
│ --llm-mode real 启动。               │
└─────────────────────────────────────┘
```

**Loading Skeleton**:
```
┌─────────────────────────────────────┐
│ 正在生成第 X 章...                  │
├─────────────────────────────────────┤
│ ● 编剧 - 处理中...                  │
│ ● 执笔 - 等待中...                  │
│ ○ 润色 - 等待中...                  │
│ ○ 审核 - 等待中...                  │
│ ○ 发布 - 等待中...                  │
└─────────────────────────────────────┘
```

**结果卡片**:
- 成功: 绿色边框，显示"演示生成完成"
- 失败: 红色边框，显示"生成失败"
- 阻塞: 黄色边框，显示"生成阻塞"

**操作按钮**:
- 已发布: "查看正文" + "查看工作流" + "继续生成下一章"
- 需审核: "进入审核"
- 失败/阻塞: "重新运行"

**预选下一章**:
- 点击"继续生成下一章"自动预选下一章
- 跳转到 `/run?project_id=xxx&chapter=next`

### 3. ProjectDetail 页面增强

**最近运行表**:
- 新增"查看工作流"操作列
- 点击跳转到 RunDetail 页面

### 4. ChapterReader 页面增强

**演示正文提示**:
```
┌─────────────────────────────────────┐
│ ℹ️ 演示正文                         │
│ 本章为演示模式生成内容，由本地 Stub  │
│ 模板生成，不代表真实创作质量。       │
└─────────────────────────────────────┘
```

**来源标签**:
- 演示模式: "演示"
- 真实模式: "真实"

**导航增强**:
- "查看工作流"按钮（有运行记录时）
- "上一章"/"下一章"导航
- "生成下一章"按钮（下一章未发布时）

### 5. Layout 全局提示

**顶部状态栏**:
- 演示模式: 显示"演示模式"徽章（黄色）
- 真实模式: 显示"真实模式"徽章（绿色）

**动态获取**:
```typescript
useEffect(() => {
  get<{ llm_mode: string }>('/health').then((res) => {
    if (res.ok && res.data) {
      setLlmMode(res.data.llm_mode)
    }
  })
}, [])
```

### 6. Settings 配置体验优化

**复制反馈**:
- 点击"复制草案"按钮
- 显示"已复制到剪贴板"提示
- 按钮文字临时变为"已复制"

**切换指引**:
- 配置项下方显示使用说明
- 提供 CLI 启动命令示例

## 交互优化

### 1. Loading 状态

**步骤 Skeleton**:
- 显示 5 个步骤的骨架屏
- 当前步骤显示"处理中..."
- 后续步骤显示"等待中..."
- 动画延迟错开（0.5s 间隔）

### 2. 结果卡片

**状态区分**:
- 成功: 绿色边框，"演示生成完成"
- 失败: 红色边框，"生成失败"，显示错误信息
- 阻塞: 黄色边框，"生成阻塞"，显示阻塞原因

**信息展示**:
- 工作流状态（已完成/失败/阻塞）
- 章节状态（已发布/审核中）
- 章节号
- 生成模式（演示/真实）

### 3. 下一步引导

**已发布**:
- 主要操作: "查看正文"
- 次要操作: "查看工作流" + "继续生成下一章"

**需审核**:
- 主要操作: "进入审核"

**失败/阻塞**:
- 主要操作: "重新运行"

### 4. 页面交互统一

**按钮文字**:
- 中文化: "生成章节"、"查看正文"、"查看工作流"
- 状态文字: "生成中..."、"加载中..."

**错误状态**:
- 统一使用 ErrorState 组件
- 提供"重试"按钮

**空状态**:
- 统一使用 EmptyState 组件
- 提供操作引导

## 验收标准

### 1. 单元测试

**v5.1.4 专项测试**: `tests/test_v514_workflow_visibility.py`

**测试覆盖**:
- API 端点存在性
- API 返回 5 个步骤
- API 返回运行元数据
- Run 页面演示模式提示
- Run 页面工作流链接
- ChapterReader 演示正文提示
- ProjectDetail 工作流链接
- RunDetail 页面存在性
- RunDetail 渲染步骤逻辑
- RunDetail 路由注册
- Run 页面使用翻译状态
- ChapterReader 使用翻译状态
- Settings 复制反馈
- Smoke 脚本存在性
- 双 /api 前缀检测（4 项）

**测试数量**: 18/18 通过

### 2. 全量测试

**基线**: 1311/1311 通过

**命令**:
```bash
python3 -m pytest -q
```

### 3. TypeScript 检查

**命令**:
```bash
cd frontend && npm run typecheck
```

**期望**: 0 错误

### 4. 前端构建

**命令**:
```bash
cd frontend && npm run build
```

**期望**: 成功

### 5. Smoke 测试

**命令**:
```bash
./scripts/v51_smoke_acceptance.sh
```

**期望**: 全部通过

### 6. 浏览器验收

**验收流程**:
1. 打开 `/run`
2. 验证演示模式提示显示
3. 选择项目和章节，点击"生成章节"
4. 验证 loading skeleton 显示
5. 验证成功结果卡片显示
6. 点击"查看工作流"
7. 验证 RunDetail 页面显示 5 个步骤
8. 验证步骤状态正确
9. 点击"查看正文"
10. 验证 ChapterReader 显示演示正文提示
11. 验证顶部状态栏显示"演示模式"

**验收结果**: ✅ 通过

## P1/P2 修复

### [P1] 前端 API path 双 /api 问题

**问题**:
- `frontend/src/lib/api.ts` 已有 `API_BASE='/api'`
- 页面代码调用时又加了 `/api` 前缀
- 导致实际请求变成 `/api/api/projects`、`/api/api/health`、`/api/api/runs/{runId}`

**修复**:
- `Run.tsx`: `get('/api/health')` → `get('/health')`, `get('/api/projects')` → `get('/projects')`
- `RunDetail.tsx`: `get('/api/runs/${runId}')` → `get('/runs/${runId}')`
- `Layout.tsx`: `get('/api/health')` → `get('/health')`
- `ChapterReader.tsx`: `get('/api/health')` → `get('/health')`

### [P2] 测试覆盖不足

**问题**: 现有测试没有抓住双 /api 问题

**修复**:
- 新增 `TestNoDoubleApiPrefix` 测试类
- 4 个测试覆盖所有页面
- 使用正则表达式检测 `get` 调用中的 `/api` 前缀

## 技术债务

### 已解决
- ✅ 工作流不可见
- ✅ 演示模式说明不足
- ✅ 生成交互粗糙
- ✅ API path 双 /api 问题

### 遗留问题
- ⚠️ 真实 LLM 未配置（v5.1.5 解决）
- ⚠️ 工作流非实时（未来版本）
- ⚠️ 步骤详情不可见（未来版本）

## 变更文件

### 新增文件
- `frontend/src/pages/RunDetail.tsx` - 运行详情页面
- `novel_factory/api/routes/runs.py` - 运行详情 API
- `tests/test_v514_workflow_visibility.py` - v5.1.4 专项测试

### 修改文件
- `frontend/src/App.tsx` - 添加 RunDetail 路由
- `frontend/src/components/Layout.tsx` - 动态 LLM 模式显示
- `frontend/src/pages/Run.tsx` - 演示模式提示、loading skeleton、工作流链接
- `frontend/src/pages/ChapterReader.tsx` - 演示正文提示、导航优化
- `frontend/src/pages/ProjectDetail.tsx` - 工作流链接
- `novel_factory/api/routes/__init__.py` - 注册 runs_router
- `novel_factory/api_app.py` - 版本号更新、注册 runs_router
- `scripts/v51_smoke_acceptance.sh` - 添加 runs 端点测试

## 后续规划

### v5.1.5 - Real LLM Configuration & First Real Generation
- 真实 LLM 配置
- 首次真实生成
- 质量对比验证
- 成本控制

### v5.2.0 - Multi-Project Management
- 多项目管理
- 项目切换
- 批量操作

### v5.3.0 - Advanced Workflow Control
- 工作流实时事件流
- 步骤详情查看
- 手动干预点
