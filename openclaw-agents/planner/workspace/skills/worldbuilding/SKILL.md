---
name: worldbuilding
description: |
  构建完整的小说世界观体系：世界设定、角色档案、势力分布、大纲规划。
  
  TRIGGER when:
  - 总编创建新项目
  - 需要添加或完善设定（角色、势力、世界观）
  - 任务消息包含"世界观"、"角色创建"、"势力"、"大纲"
  
  DO NOT trigger when:
  - 简单的数据查询（使用 db.py 直接查询）
  - 章节规划或伏笔管理
---

# 世界观构建 Skill

## 🚨 创建新项目（第一步！）

```bash
python3 tools/db.py add_project <project_id> <name> <genre> [description] [total_chapters]
```

**参数**：
- `project_id`: 项目ID（如 `novel_001`）
- `name`: 项目名称
- `genre`: 题材
- `description`: 项目简介（可选）
- `total_chapters`: 计划总章节数（可选，默认500）

⚠️ 注意：正确命令是 `add_project`，不是 `create_project`

---

## 获取项目上下文（现有项目）

```bash
python3 tools/db.py current_project
python3 tools/db.py projects  # 列出所有项目
```

---

## 工作流程

```
1. 创建设定（按顺序）
   - world_overview: 世界总纲（核心矛盾点）
   - power_system: 力量体系（等级、升级、限制）
   - geography: 地理设定
   - history: 历史背景（可选）
   - rules: 世界规则（初始数值状态）

2. 创建角色档案（核心动机+底线）

3. 创建势力分布（核心诉求+冲突点）

4. 创建大纲（爽点+目标+反转）
```

---

## 命令速查

详见 `skills/worldbuilding/references/commands.md`

| 命令 | 用途 |
|------|------|
| `add_project ...` | 创建项目 |
| `add_world_setting ...` | 添加世界观 |
| `add_character ...` | 创建角色 |
| `update_character ...` | 更新角色 |
| `delete_character ...` | 删除角色 |
| `add_faction ...` | 创建势力 |
| `create_outline ...` | 创建大纲 |

---

## 内容生成规范

详见 `skills/worldbuilding/references/content_rules.md`

### 世界观设定铁律

- **力量体系**：必须有战力天花板、升级条件、能力限制
- **初始状态**：必须明确主角开局属性、资源、物品

### 角色描述三要素

1. **表层人设**：外在形象
2. **核心动机**：利益诉求
3. **致命弱点**：行为底线

> 目的：防止执笔写出"降智"角色

### 势力描述规范

不能只写"邪恶组织"，必须写明**核心资源冲突**。

### 大纲内容规范

必须包含：阶段目标、核心冲突、爽点分布、关键伏笔

---

## 完整示例

```bash
# 获取项目
python3 tools/db.py current_project

# 创建世界观
python3 tools/db.py add_world_setting novel_002 world_overview "废土种田总纲" \
  "大崩坏后，净水成为唯一硬通货..."

# 创建力量体系（含初始状态）
python3 tools/db.py add_world_setting novel_002 power_system "种田系统与变异等级" \
  "系统需消耗生命力加速作物生长。主角开局：Lv1，生命力30/100，持有1颗变异白菜种子。"

# 创建主角（三要素）
python3 tools/db.py add_character novel_002 "林禾" protagonist \
  "表层：废土拾荒者。动机：寻找失踪的妹妹。弱点：涉及妹妹线索时容易冲动。" "" 1

# 创建反派
python3 tools/db.py add_character novel_002 "李建国" antagonist \
  "表层：高塔区收粮官。动机：还清赌债。弱点：害怕上级查账。" "" 1

# 创建势力
python3 tools/db.py add_faction novel_002 "高塔议会" government \
  "垄断净水技术，禁止民间研发滤水器" enemy

# 创建大纲
python3 tools/db.py create_outline novel_002 volume 1 "卷一：初入废土" --chapters_range "1-50" --file /tmp/outline.md
```

---

## 检查清单

```
□ 基准校验：是否设定了主角初始数值/资源状态？
□ 战力收敛：力量体系是否有天花板、代价、限制？
□ 反派智商：反派是否有合理的利益动机和专业能力？
□ 势力自洽：各势力是否有实质性资源冲突？
□ 大纲钩子：大纲是否规划了"高潮爽点"与"悬念反转"？
```
