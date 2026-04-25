# 伏笔命令速查

## 数据同步

```bash
# 检查并修复数据一致性
python3 tools/db.py sync_plots <project>

# 仅检查不修复
python3 tools/db.py sync_plots <project> --dry-run
```

**同步时机**：添加伏笔后、兑现伏笔后、发布新章节后、每日工作结束时

---

## 查询命令

```bash
# 获取当前项目
python3 tools/db.py current_project

# 查看待兑现伏笔
python3 tools/db.py pending_plots <project>

# 查询章节范围的伏笔
python3 tools/db.py plots_by_chapter <project> <start> <end>
```

---

## 添加伏笔

```bash
python3 tools/db.py add_plot <project> <code> <type> "<title>" "<description>" \
  <planted_chapter> <planned_resolve_chapter>
```

**参数**：
- `code`: 伏笔编号（P=长线, L=中线, S=短线）
- `type`: `long` / `mid` / `short`
- `description`: **必须包含【表象】和【真相/底牌】**

---

## 兑现伏笔

```bash
python3 tools/db.py resolve_plot <project> <code> <resolved_chapter>
```
