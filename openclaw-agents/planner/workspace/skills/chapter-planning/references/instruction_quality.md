# 高质量指令规约

作为策划，你下发的指令是执笔（Writer）的唯一创作依据。为了防止执笔的稿件被质检打回，你的指令必须具备以下"防御性"：

---

## 四大铁律

### 1. 数值基准强制注入

必须将 `chapter_state` 完整写入 `objective` 的开头，作为执笔的数值红线。

**示例**：
```
【当前状态卡】系统Lv1，建造点数剩余5，已解锁：基础建造。
本章目标：主角使用系统建造第一座建筑...
```

### 2. 反派行为逻辑化

在 `key_events` 安排反派行动时，必须写明其**合理动机和手段**。

❌ 错误：`反派挑衅主角`
✅ 正确：`李建国为了还清赌债，利用职权压榨拾荒者，主角成为他眼中的"肥羊"`

### 3. 具象化剧情锚点

不要写抽象描述，必须写明具体动作和逻辑。

❌ 错误：`经历一番苦战最后胜利`
✅ 正确：`利用上一章获得的爆炸番茄，破坏了执法队的阵眼，完成反杀`

### 4. 去AI化提示

在 `emotion_tone` 中，必须加上禁令。

**示例**：
```
紧张转震撼（⚠️要求执笔禁用空洞辞藻，写出建筑拔地而起的物理细节）
```

---

## 伏笔规范

### 伏笔代码命名

| 前缀 | 类型 | 示例 |
|------|------|------|
| P | 长线伏笔（Primer，贯穿全书） | P001、P002 |
| L | 中线伏笔（Line，10章内兑现） | L001、L002 |
| S | 短线伏笔（Shot，5章内兑现） | S001、S002 |

### 伏笔描述格式

```
【表象】读者看到的表面现象。
【真相/底牌】实际真相或后续揭示的底牌。
```

**示例**：
```
【表象】第五章结尾沙盘显示，一个新的Lv4宿主信号在江城外围出现。
【真相/底牌】这是比林默、苏晚晴更强的高级宿主，五线围猎升级为六线围猎。
```

### ⚠️ 伏笔必须在 create_instruction 之前创建

`plots_to_plant` 和 `plots_to_resolve` 只能引用**已存在的伏笔代码**。

```bash
# 步骤1：创建新伏笔
python3 tools/db.py add_plot <project> <code> <type> "<title>" "<description>" \
  <planted_chapter> <planned_resolve>

# 步骤2：创建指令时引用
python3 tools/db.py create_instruction ... '["L002"]' '["L006"]' ...
```

---

## 常见错误

### 错误1：参数顺序错误

```bash
# ❌ 错误：把 emotion_tone 填到了 plots_to_resolve 位置
python3 tools/db.py create_instruction novel_001 1 \
  "目标" "事件" "钩子" \
  "紧张/热血" \    # ← 这应该是 JSON 数组！
  '["L001"]'

# ✅ 正确：按顺序填写
python3 tools/db.py create_instruction novel_001 1 \
  "目标" "事件" "钩子" \
  '["S001"]' \     # plots_to_resolve: JSON数组
  '["L001"]' \     # plots_to_plant: JSON数组
  "紧张/热血"      # emotion_tone: 字符串
```

### 错误2：跳过中间参数

```bash
# ❌ 错误：跳过 plots_to_resolve
python3 tools/db.py create_instruction novel_001 1 \
  "目标" "事件" "钩子" \
  '["L001"]' \     # 这会填到 plots_to_resolve 位置！
  "爽快"

# ✅ 正确：用 '[]' 填充空值
python3 tools/db.py create_instruction novel_001 1 \
  "目标" "事件" "钩子" \
  '[]' \           # plots_to_resolve: 空
  '["L001"]' \     # plots_to_plant
  "爽快"
```
