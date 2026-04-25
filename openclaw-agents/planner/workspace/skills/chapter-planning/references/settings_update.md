# 设定变化规划

作为总编，你负责规划**重大设定变化**。这些变化需要在创建指令时明确规划。

---

## 变化类型

| 变化类型 | 示例 | 更新时机 |
|---------|------|---------|
| 角色状态 | 死亡、失踪、复活、觉醒 | 规划时决定 |
| 角色关系 | 敌人→友军、陌生→盟友 | 规划时决定 |
| 势力关系 | 敌对→同盟、中立→敌对 | 规划时决定 |
| 势力状态 | 灭亡、崛起、分裂 | 规划时决定 |
| 新角色 | 新登场角色 | 创建指令时 |
| 新设定 | 世界观扩展 | 规划时决定 |

---

## 更新命令

### 角色状态

```bash
# 角色死亡
python3 tools/db.py update_character <project> <name> --status deceased

# 角色失踪
python3 tools/db.py update_character <project> <name> --status missing

# 角色觉醒
python3 tools/db.py update_character <project> <name> --description "觉醒后：..."

# 角色背景丰富
python3 tools/db.py update_character <project> <name> --background "新增背景信息..."
```

### 势力关系

```bash
# 势力关系变化
python3 tools/db.py update_faction <project> <name> --relationship ally

# 势力目标更新
python3 tools/db.py update_faction <project> <name> --goals "新目标..."
```

### 新角色

```bash
# 在 create_instruction 时通过 new_characters 参数创建
python3 tools/db.py create_instruction <project> <chapter> \
  "目标" "事件" "钩子" \
  '[]' '[]' "紧张" \
  '[{"name":"新角色名","role":"minor","description":"描述"}]'
```

### 世界观设定

```bash
python3 tools/db.py add_world_setting <project> <category> "<title>" "<content>"

# 类别：world_overview, power_system, geography, history, rules, other
python3 tools/db.py add_world_setting novel_001 power_system "新能力规则" "觉醒者可以..."
```

---

## 完整示例

```bash
# Step 1: 读取当前设定
python3 tools/db.py characters novel_001
python3 tools/db.py factions novel_001

# Step 2: 读取上一章状态卡
python3 tools/db.py chapter_state novel_001 5

# Step 3: 规划本章设定变化（假设第6章反派死亡）

# Step 4: 更新角色状态
python3 tools/db.py update_character novel_001 林默 --status deceased

# Step 5: 更新势力关系
python3 tools/db.py update_faction novel_001 系统宿主联盟 --relationship weakened

# Step 6: 创建指令（包含状态卡和新角色）
python3 tools/db.py create_instruction novel_001 6 \
  "【状态卡】主角Lv3，XP:250/500，技能：职场洞察Lv2..." \
  "林默被击败死亡；主角获得新技能；新角色登场" \
  "主角发现更大的阴谋" \
  '["L001"]' '["L005"]' "紧张/热血" \
  '[{"name":"神秘女子","role":"supporting","description":"身份不明，救走主角"}]'
```

---

## 注意事项

- **重大设定变化必须在规划时决定**，不要留给执笔自由发挥
- **设定变化后立即更新数据库**，确保后续章节能读取正确状态
- **新角色尽量在 create_instruction 时创建**，确保 first_appearance 正确
- **世界观设定尽量提前规划**，避免后期打补丁
