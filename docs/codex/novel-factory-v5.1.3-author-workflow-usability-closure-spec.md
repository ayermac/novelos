# Novel Factory v5.1.3 - Author Workflow Usability Closure

## 版本信息
- **版本**: v5.1.3
- **发布日期**: 2026-04-27
- **状态**: ✅ 已验收
- **测试基线**: 1293/1293 通过

## 背景

### v5.1.2 遗留问题
v5.1.2 解决了章节状态模型问题，但 WebUI 仍无法阅读生成的正文内容。用户生成章节后，只能看到状态变化，无法查看实际内容，导致作者主流程断裂。

### Stub 模式体验问题
演示模式下，每章内容完全重复（都是相同的模板内容），验收体验像"假生成"，无法演示多章节项目的真实效果。

### 历史失败误导
历史运行记录显示 `failed` 状态，但实际上可能是阻塞或需要人工审核，误导用户判断。

## 目标

### 核心目标
1. **作者主流程闭环**: 生成章节 → 查看正文 → 继续下一章
2. **Stub 内容差异化**: 让 stub 内容按章节区分，提升演示体验
3. **历史失败修复**: 修复历史失败误导，正确显示阻塞状态
4. **配置体验优化**: 配置中心改为配置草案生成器

### 非目标
- 不涉及真实 LLM 调用（v5.1.4+）
- 不涉及工作流可视化（v5.1.4）
- 不涉及多用户协作

## 后端实现

### 1. 章节详情 API

**端点**: `GET /api/projects/{project_id}/chapters/{chapter_number}`

**响应**:
```json
{
  "ok": true,
  "data": {
    "project_id": "dpcq",
    "project_name": "斗破苍穹",
    "chapter_number": 1,
    "title": "第一章 陨落的天才",
    "status": "published",
    "word_count": 3200,
    "quality_score": 85,
    "content": "正文内容...",
    "created_at": "2026-04-27T10:00:00Z",
    "updated_at": "2026-04-27T10:05:00Z"
  }
}
```

**实现要点**:
- 从 `chapters` 表读取章节元数据
- 从 `chapter_contents` 表读取正文内容
- 返回项目名称用于面包屑导航
- 计算字数和质量分

### 2. 历史运行状态修复

**修复内容**:
- 修正 `workflow_runs` 表中 `failed` 状态的判断逻辑
- 区分 `failed`（真实错误）和 `blocked`（需要人工介入）
- 更新历史运行记录显示

## 前端实现

### 1. ChapterReader 页面

**路由**: `/projects/:projectId/chapters/:chapterNumber`

**功能**:
- 显示章节元数据（项目、章节号、状态、字数、质量分）
- 显示章节正文（720px 最大宽度，1.9 行高）
- 导航按钮（上一章/下一章/返回项目）
- 生成本章按钮（无正文时）
- 演示模式提示（stub 模式）

**布局**:
```
┌─────────────────────────────────────┐
│ 第 X 章 标题              [返回项目] │
├─────────────────────────────────────┤
│ 项目: XXX | 状态: 已发布 | 字数: XXX │
├─────────────────────────────────────┤
│                                     │
│         章节正文内容                │
│         (720px 最大宽度)            │
│                                     │
├─────────────────────────────────────┤
│ [上一章] [下一章] [生成本章]        │
└─────────────────────────────────────┘
```

### 2. 项目详情页增强

**章节表操作列**:
- 已发布章节: "查看正文" 按钮
- 未发布章节: "生成本章" 按钮
- 点击跳转到对应页面

### 3. Run 页面增强

**成功结果**:
- 显示"查看正文"按钮
- 点击跳转到 ChapterReader 页面
- 支持 `?project_id=&chapter=` 预选参数

**预选逻辑**:
```typescript
// 从 URL 参数读取预选
const queryProjectId = searchParams.get('project_id')
const queryChapter = searchParams.get('chapter')

// 设置默认值
if (queryProjectId && projects.some(p => p.project_id === queryProjectId)) {
  setSelectedProject(projects.find(p => p.project_id === queryProjectId))
}
```

### 4. Onboarding 优化

**自动生成**:
- 项目 ID: 自动生成 UUID
- 默认类型: "都市"
- 默认章节数: 10

**表单简化**:
- 只需填写项目名称
- 其他字段可选

### 5. Acceptance 页面优化

**默认隐藏**:
- 隐藏内部 capability id
- 只显示用户关心的验收项
- 提供展开查看详情选项

## Stub 模式实现

### StubLLM 差异化生成

**实现逻辑**:
```python
class StubLLM:
    def generate_chapter(self, chapter_number: int, genre: str) -> dict:
        # 根据章节号生成不同标题
        title = f"第{chapter_number}章 {self._generate_title(chapter_number, genre)}"
        
        # 根据章节号生成不同内容
        content = self._generate_content(chapter_number, genre)
        
        # 计算字数
        word_count = len(content)
        
        return {
            "title": title,
            "content": content,
            "word_count": word_count,
            "quality_score": 75 + (chapter_number % 10)
        }
    
    def _generate_title(self, chapter_number: int, genre: str) -> str:
        titles = {
            "都市": ["初入职场", "意外相遇", "暗流涌动", ...],
            "玄幻": ["觉醒", "初试身手", "遭遇强敌", ...],
            "仙侠": ["入山门", "初窥门径", "师门试炼", ...],
        }
        return titles.get(genre, ["第一章", "第二章", ...])[chapter_number % len(titles)]
```

**特点**:
- 不调用真实 LLM
- 根据章节号生成不同标题和内容
- 根据类型选择不同模板
- 字数和质量分有变化

## 验收标准

### 1. 单元测试

**v5.1.3 专项测试**: `tests/test_v513_author_workflow_closure.py`
- 章节详情 API 测试
- ChapterReader 页面测试
- Run 预选参数测试
- Onboarding 自动生成测试
- Stub 差异化生成测试

**测试数量**: 15 项专项测试

### 2. 全量测试

**基线**: 1293/1293 通过

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
1. 打开 `/projects/dpcq`
2. 点击章节表的"查看正文"
3. 验证 ChapterReader 页面显示正确
4. 验证正文内容可读
5. 点击"下一章"验证导航
6. 点击"生成本章"验证生成流程

**验收结果**: ✅ 通过

## 技术债务

### 已解决
- ✅ 章节正文无法查看
- ✅ Stub 内容重复
- ✅ 历史运行状态误导
- ✅ Onboarding 表单繁琐

### 遗留问题
- ⚠️ 工作流不可见（v5.1.4 解决）
- ⚠️ 演示模式说明不足（v5.1.4 解决）
- ⚠️ 真实 LLM 未配置（v5.1.5 解决）

## 变更文件

### 新增文件
- `frontend/src/pages/ChapterReader.tsx` - 章节阅读页面
- `tests/test_v513_author_workflow_closure.py` - v5.1.3 专项测试

### 修改文件
- `frontend/src/App.tsx` - 添加 ChapterReader 路由
- `frontend/src/pages/ProjectDetail.tsx` - 章节表操作列
- `frontend/src/pages/Run.tsx` - 预选参数支持
- `frontend/src/pages/Onboarding.tsx` - 自动生成优化
- `frontend/src/pages/Acceptance.tsx` - 隐藏内部 id
- `novel_factory/api/routes/projects.py` - 章节详情 API
- `novel_factory/stub_llm.py` - 差异化生成

## 后续规划

### v5.1.4 - Workflow Visibility & Interaction Polish
- 工作流可视化
- 演示模式说明强化
- 生成交互优化

### v5.1.5 - Real LLM Configuration & First Real Generation
- 真实 LLM 配置
- 首次真实生成
- 质量对比验证
