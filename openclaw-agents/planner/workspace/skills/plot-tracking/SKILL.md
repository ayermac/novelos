---
name: plot-tracking
description: |
  追踪和管理小说伏笔系统，确保每个坑都有计划填上。
  
  TRIGGER when:
  - 总编更新伏笔状态
  - 需要添加、兑现、查询伏笔
  - 任务消息包含"伏笔"、"挖坑"、"填坑"
  
  DO NOT trigger when:
  - 简单的数据查询（使用 db.py 直接查询）
  - 与伏笔无关的章节规划
---

# 伏笔追踪 Skill

## 第一步：获取项目上下文

```bash
python3 tools/db.py current_project
```

## 重要：定期同步数据

**每次操作伏笔后，应执行同步命令确保数据一致！**

```bash
# 同步伏笔追踪数据
python3 tools/db.py sync_plots <project>

# 仅检查不修复
python3 tools/db.py sync_plots <project> --dry-run
```

**同步时机**：添加伏笔后、兑现伏笔后、发布新章节后、每日工作结束时

---

## 工作流程

```
1. 获取项目上下文
   python3 tools/db.py current_project

2. 【可选】同步检查数据完整性
   python3 tools/db.py sync_plots <project> --dry-run

3. 查看待兑现伏笔
   python3 tools/db.py pending_plots <project>

4. 添加新伏笔
   python3 tools/db.py add_plot ...

5. 兑现伏笔
   python3 tools/db.py resolve_plot ...

6. 【必须】同步数据
   python3 tools/db.py sync_plots <project>
```

---

## 高质量伏笔规约

详见 `skills/plot-tracking/references/design_rules.md`

**三大铁律**：
1. **谜底必须前置**：description 必须包含【表象】和【真相/底牌】
2. **契诃夫的枪**：每个伏笔必须能引发危机/升级/反转
3. **闭环情绪释放**：兑现时必须有爆发性情绪

---

## 命令速查

详见 `skills/plot-tracking/references/commands.md`

| 命令 | 用途 |
|------|------|
| `sync_plots <project>` | 同步数据 |
| `pending_plots <project>` | 查看待兑现 |
| `plots_by_chapter <project> <start> <end>` | 查询章节范围 |
| `add_plot ...` | 添加伏笔 |
| `resolve_plot <project> <code> <chapter>` | 兑现伏笔 |

---

## 添加伏笔格式

```bash
python3 tools/db.py add_plot <project> <code> <type> "<title>" "<description>" \
  <planted_chapter> <planned_resolve_chapter>
```

**参数**：
- `code`: P=长线, L=中线, S=短线
- `type`: `long` / `mid` / `short`
- `description`: **必须包含【表象】和【真相/底牌】**

**示例**：
```bash
python3 tools/db.py add_plot novel_002 L001 long "黑刀的来历" \
  "【表象】主角捡到一把沾血就发烫的生锈断刀。【真相/底牌】这其实是开启高塔终极控制室的唯一物理钥匙。" \
  1 150
```

---

## 检查清单

```
□ 真相前置：description 是否写出了【真相/底牌】？
□ 逻辑闭环：兑现章节是否与剧情进度匹配？
□ 填坑质量：长期伏笔是否超100章未回收？
□ 数据一致：是否执行了 sync_plots？
```
