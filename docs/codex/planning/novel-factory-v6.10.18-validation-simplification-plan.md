# Novelos v6.10.18 验证体系简化计划

> **版本**: v6.10.18
> **主题**: 验证体系简化 — 字段精简与验证逻辑合并
> **状态**: Planned
> **创建日期**: 2026-07-07
> **依赖版本**: v6.10.17 (Code Slimming)
> **预估工期**: 10 周（原估 2-3 个月/6-8 周均偏乐观；实际含审计+迁移+前端+Skill适配）
> **风险等级**: 高（字段删除不可逆；涉及前端、Skill、CLI 三层）

---

## 1. 背景与动机

### 1.1 当前问题

```markdown
验证字段过多：
  - Tier 1: 7 个字段
  - Tier 2: 17 个字段
  - 总计: 24 个字段

验证文件分散：
  - Quality 模块: 19 个文件
  - Validators 模块: 10 个文件
  - 验证相关总计: 29 个文件
```

### 1.2 对比 ainovel-cli

| 维度 | ainovel-cli | novelos v6.10.17 | 差距 |
|------|-------------|-------------------|------|
| **字段数量** | 10 个 | 24 个 | +140% |
| **验证文件** | 3 个 | 29 个 | +867% |
| **验证逻辑复杂度** | 低 | 高 | - |

### 1.3 设计目标

1. **字段精简**：从 24 个字段 → 10-12 个字段（-50%~-58%）
2. **文件合并**：验证文件从 29 个 → 15-20 个（-31%~-48%）
3. **验证简化**：双层验证 → 单层统一验证（保留插件扩展点）
4. **零破坏**：不改变核心功能；**采用渐进式弃用（3 阶段）**，而非直接删除
5. **数据安全**：所有字段删除前必须完成数据迁移方案，确保已有项目数据不丢失
6. **前端同步**：验证简化必须同步评估前端表单组件影响

---

## 2. 字段审计与使用频率分析（前置条件，必须先执行）

### 2.1 审计方法

在删除任何字段之前，必须先完成全量引用审计。这是 **v6.10.18 的 P0 前置条件**，没有审计结果，不得进入后续阶段。

```bash
# 统计 24 个字段在 backend 中的引用频率
for field in chapter_goal reader_payoff protagonist_agency forbidden_moves core_loop_target primary_payoff payoff_evidence_plan pressure_budget payoff_budget upgrade_or_skill_use character_arc_moves mystery_actions conflict_actions ledger_debts_to_pay new_debts_allowed scene_count_target opening_hook ending_hook quality_threshold_overrides supporting_mechanisms_used new_mechanisms_allowed drift_risks contract_checklist; do
  echo "=== $field ==="
  grep -rn "\"$field\"\|'"$field"'" novel_factory/ frontend/ tests/ --include="*.py" --include="*.ts" --include="*.tsx" | wc -l
done
```

**重点排查领域**：
1. `novel_factory/skills/` 下的 27 个 skill 文件（`chapter_seam_skill.py`、`foreshadowing_debt_skill.py`、`fact_lock_skill.py` 等可能直接依赖 Tier 2 字段）
2. `novel_factory/agents/` 的 planner、author、editor、polisher（上下文构建可能读取 Tier 2 字段）
3. `novel_factory/api/routes/` 的 genesis、production、project（API 请求/响应模型）
4. `frontend/src/components/project/` 的表单组件（`CreativeContractsModule.tsx`、`GenesisModule.tsx` 等）
5. `tests/` 中的验证测试（`test_quality.py`、`test_validators.py` 等）

### 2.2 审计输出物（必须产出的文档）

| 字段 | backend 引用 | frontend 引用 | tests 引用 | Skill 引用 | 结论 |
|------|-------------|--------------|-----------|-----------|------|
| `chapter_goal` | 45 | 12 | 8 | 3 | 保留 |
| `reader_payoff` | 23 | 6 | 4 | 2 | 合并到 `payoff_points` |
| `protagonist_agency` | 18 | 5 | 3 | 1 | 合并到 `notes` |
| `pressure_budget` | 3 | 0 | 1 | 0 | 删除（低引用） |
| `payoff_budget` | 2 | 0 | 1 | 0 | 删除（低引用） |
| `ledger_debts_to_pay` | 12 | 4 | 3 | 5 | **Skill 高依赖，需 Skill 适配后删除** |
| `contract_checklist` | 8 | 3 | 2 | 1 | 合并到 `notes`（结构化内容丢失风险） |
| ... | ... | ... | ... | ... | ... |

**产出物**：`docs/codex/research/v6.10.18-field-audit-report.md`（独立文档，必须经过代码审查）

---

## 3. 字段简化方案

### 3.1 当前字段（24 个）

```python
# Tier 1（必需）
TIER1_FIELDS = [
    "chapter_goal",
    "reader_payoff",
    "protagonist_agency",
    "forbidden_moves",
    "core_loop_target",
    "primary_payoff",
    "payoff_evidence_plan",
]

# Tier 2（可选）
TIER2_FIELDS = [
    "pressure_budget",
    "payoff_budget",
    "upgrade_or_skill_use",
    "character_arc_moves",
    "mystery_actions",
    "conflict_actions",
    "ledger_debts_to_pay",
    "new_debts_allowed",
    "scene_count_target",
    "opening_hook",
    "ending_hook",
    "quality_threshold_overrides",
    "supporting_mechanisms_used",
    "new_mechanisms_allowed",
    "drift_risks",
    "contract_checklist",
]
```

### 3.2 简化后字段（10-12 个）

```python
class ChapterBrief(BaseModel):
    """简化后的章节概要"""

    # 核心 6 字段（必需）
    chapter_goal: str = ""        # 章节目标
    conflict: str = ""          # 核心冲突（新增）
    ending_hook: str = ""        # 章末钩子
    emotion_tone: str = ""      # 情感基调（新增）
    notes: str = ""            # 自由备忘（合并多个字段）

    # 契约 4 字段（可选）
    forbidden_moves: list[str] = []   # 禁止推进
    required_beats: list[str] = []    # 必需推进（替代原多个字段）
    emotion_target: str = ""          # 目标情绪
    payoff_points: list[str] = []     # 兑现点（合并 reader_payoff + primary_payoff）
```

### 3.3 字段映射表（含处理方式与风险等级）

| 原字段 | 新方案 | 处理方式 | 风险等级 | 备注 |
|--------|--------|----------|----------|------|
| `chapter_goal` | `chapter_goal` | 保留 | 低 | 核心字段 |
| `reader_payoff` | `payoff_points` | 合并 | 中 | 需确认 planner 上下文构建逻辑 |
| `protagonist_agency` | `notes` | 合并 | 高 | 内容丢失风险；需数据迁移填充 |
| `forbidden_moves` | `forbidden_moves` | 保留 | 低 | 契约核心字段 |
| `core_loop_target` | `chapter_goal` | 合并 | 中 | 与 `chapter_goal` 语义相近 |
| `primary_payoff` | `payoff_points` | 合并 | 中 | 与 `reader_payoff` 合并到同一列表 |
| `payoff_evidence_plan` | `notes` | 合并 | 高 | 内容丢失风险；需数据迁移 |
| `conflict` | `conflict` | 新增 | 低 | 无迁移风险 |
| `ending_hook` | `ending_hook` | 保留 | 低 | 核心字段 |
| `emotion_tone` | `emotion_tone` | 新增 | 低 | 无迁移风险 |
| `emotion_target` | `emotion_target` | 保留 | 低 | 契约字段 |
| `pressure_budget` | - | 删除 | 高 | **Skill 可能依赖**；需审计 `skills/` 引用 |
| `payoff_budget` | - | 删除 | 高 | **Skill 可能依赖**；需审计 |
| `upgrade_or_skill_use` | `notes` | 合并 | 高 | 内容丢失风险 |
| `character_arc_moves` | `notes` | 合并 | 高 | 内容丢失风险 |
| `mystery_actions` | `notes` | 合并 | 高 | 内容丢失风险 |
| `conflict_actions` | `conflict` | 合并 | 中 | 语义相近，合并到 `conflict` |
| `ledger_debts_to_pay` | `forbidden_moves` / `required_beats` | 合并 | 高 | **Skill 高依赖**；需 `foreshadowing_debt_skill.py` 适配 |
| `new_debts_allowed` | `notes` | 合并 | 高 | 内容丢失风险 |
| `scene_count_target` | `notes` | 合并 | 中 | 低引用字段 |
| `opening_hook` | `notes` | 合并 | 中 | 低引用字段 |
| `quality_threshold_overrides` | `notes` | 合并 | 中 | 配置类字段 |
| `supporting_mechanisms_used` | `notes` | 合并 | 中 | 低引用字段 |
| `new_mechanisms_allowed` | `notes` | 合并 | 中 | 低引用字段 |
| `drift_risks` | `notes` | 合并 | 中 | 低引用字段 |
| `contract_checklist` | `notes` | 合并 | 高 | 结构化内容丢失风险；需审计 |

### 3.4 渐进式弃用策略（3 阶段）

**直接删除字段风险极高。** 改为以下三阶段策略：

```python
# 阶段 1（v6.10.18）：标记 deprecated，保留兼容
class ChapterBrief(BaseModel):
    chapter_goal: str = ""
    # ... 新字段 ...
    
    # 旧字段保留，但标记为 deprecated
    pressure_budget: str = Field("", deprecated=True)
    payoff_budget: str = Field("", deprecated=True)
    # ... 其他待删除字段 ...
    
    @model_validator(mode='after')
    def warn_deprecated(self):
        if self.pressure_budget:
            logger.warning("pressure_budget is deprecated, use notes instead")
        return self

# 阶段 2（v6.10.19）：限制写入，允许读取
# - 前端表单不再展示 deprecated 字段
# - API 写入时忽略 deprecated 字段
# - 数据库读取时仍兼容

# 阶段 3（v6.11.0+）：完全移除
# - 数据库 migration 删除列
# - 模型定义完全移除 deprecated 字段
```

---

## 4. 验证逻辑简化

### 4.1 当前验证体系

```markdown
多层验证：
  1. Schema 验证（Pydantic）
  2. Tier 1 必需字段验证
  3. Tier 2 可选字段填充
  4. Style Bible 约束验证
  5. Quality Gate 验证
  6. Editor 策略验证
```

### 4.2 简化方案（单层验证 + 保留扩展点）

```python
class ChapterBriefValidator:
    """单层验证器 — 保留扩展点，支持插件式检查器注册"""

    REQUIRED_FIELDS = [
        "chapter_goal",
        "conflict",
        "ending_hook",
    ]
    
    # 扩展点：检查器注册表
    _checkers: list[Callable] = []
    
    @classmethod
    def register_checker(cls, checker: Callable):
        """允许 Skill 和外部模块注册自定义检查器"""
        cls._checkers.append(checker)

    def validate(self, brief: dict) -> ValidationResult:
        """单次验证 + 插件扩展"""
        errors = []

        # 1. 必需字段检查
        for field in self.REQUIRED_FIELDS:
            if not brief.get(field):
                errors.append(f"Missing required field: {field}")

        # 2. 契约一致性检查
        if brief.get("forbidden_moves") and brief.get("required_beats"):
            conflicts = self._check_conflicts(
                brief["forbidden_moves"],
                brief["required_beats"]
            )
            errors.extend(conflicts)
        
        # 3. 插件扩展检查（Skill 注册的检查器）
        for checker in self._checkers:
            result = checker(brief)
            if result.errors:
                errors.extend(result.errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors
        )
```

---

## 5. 文件合并方案

### 5.1 合并后文件结构（15-20 个）

```
quality/
  __init__.py
  validator.py              # 统一验证器（含插件扩展点）
  contracts.py              # 契约验证
  continuity.py             # 连续性检查
  style.py                  # 风格检查
  genesis.py                # 创世质量门
  editor_strategy.py        # Editor 策略
  hub.py                    # 质量中心
  # 从 19 个 → 8 个

validators/
  __init__.py
  revision.py               # 修订验证
  numeric_state.py          # 数值状态验证
  # 从 10 个 → 3 个
```

---

## 6. 数据迁移方案

### 6.1 迁移范围

所有现有项目的 `ChapterBrief` 数据（存储于 SQLite 的 `chapter` / `instruction` / `outline` 表）需要迁移。

### 6.2 迁移策略

```sql
-- db/migrations/039_v6_10_18_chapter_brief_simplification.sql

-- 阶段 1：添加新字段
ALTER TABLE instruction ADD COLUMN conflict TEXT DEFAULT '';
ALTER TABLE instruction ADD COLUMN emotion_tone TEXT DEFAULT '';
ALTER TABLE instruction ADD COLUMN required_beats TEXT DEFAULT '[]';
ALTER TABLE instruction ADD COLUMN payoff_points TEXT DEFAULT '[]';

-- 阶段 2：数据迁移（将旧字段内容合并到新字段）
UPDATE instruction SET
    notes = COALESCE(notes, '') || 
            '\n--- protagonist_agency ---\n' || COALESCE(protagonist_agency, '') ||
            '\n--- payoff_evidence_plan ---\n' || COALESCE(payoff_evidence_plan, '') ||
            '\n--- upgrade_or_skill_use ---\n' || COALESCE(upgrade_or_skill_use, '') ||
            '\n--- character_arc_moves ---\n' || COALESCE(character_arc_moves, '') ||
            '\n--- mystery_actions ---\n' || COALESCE(mystery_actions, '') ||
            '\n--- new_debts_allowed ---\n' || COALESCE(new_debts_allowed, '') ||
            '\n--- scene_count_target ---\n' || COALESCE(scene_count_target, '') ||
            '\n--- opening_hook ---\n' || COALESCE(opening_hook, '') ||
            '\n--- quality_threshold_overrides ---\n' || COALESCE(quality_threshold_overrides, '') ||
            '\n--- supporting_mechanisms_used ---\n' || COALESCE(supporting_mechanisms_used, '') ||
            '\n--- new_mechanisms_allowed ---\n' || COALESCE(new_mechanisms_allowed, '') ||
            '\n--- drift_risks ---\n' || COALESCE(drift_risks, '') ||
            '\n--- contract_checklist ---\n' || COALESCE(contract_checklist, ''),
    payoff_points = '[' || COALESCE(reader_payoff, '') || ',' || COALESCE(primary_payoff, '') || ']';
```

### 6.3 迁移验证

- [ ] 迁移前后数据完整性校验（记录行数、字段非空率）
- [ ] 随机抽样 10 个项目，人工验证 `notes` 合并内容正确
- [ ] 迁移脚本支持 `--dry-run` 模式，先预览再执行
- [ ] 提供回滚脚本（`rollback_039.sql`），支持迁移失败时恢复

---

## 7. 前端影响评估

### 7.1 受影响组件

| 组件 | 路径 | 影响字段 | 修改方式 |
|------|------|----------|----------|
| CreativeContractsModule | `frontend/src/components/project/CreativeContractsModule.tsx` | `forbidden_moves`, `required_beats` | 保留，改为新字段名 |
| GenesisModule | `frontend/src/components/project/GenesisModule.tsx` | 多个 Tier 1/2 字段 | 字段减少，表单简化 |
| AuthorWritingSurface | `frontend/src/components/project/AuthorWritingSurface.tsx` | `chapter_goal`, `ending_hook` | 保留，可能 UI 调整 |
| ChapterWorkspace | `frontend/src/components/project/ChapterWorkspace.tsx` | 多个 | 验证错误提示更新 |

### 7.2 前端修改策略

- 与后端同步采用渐进式弃用：前端表单先隐藏 deprecated 字段（而非删除），保留数据展示
- 新增字段（`conflict`, `emotion_tone`）需要设计新的表单输入组件
- 需要更新 `frontend/src/lib/i18n.ts` 中的字段翻译

---

## 8. Skill 体系依赖审计（P0 前置条件）

### 8.1 审计范围

`novel_factory/skills/` 下 27 个 skill 文件必须逐一排查：

| Skill 文件 | 可能依赖字段 | 审计结果 |
|-----------|-------------|----------|
| `foreshadowing_debt_skill.py` | `ledger_debts_to_pay`, `new_debts_allowed` | 待审计 |
| `fact_lock_skill.py` | `contract_checklist` | 待审计 |
| `chapter_seam_skill.py` | `scene_count_target` | 待审计 |
| `death_penalty_skill.py` | `quality_threshold_overrides` | 待审计 |
| `continuity_gate_skill.py` | `drift_risks` | 待审计 |
| ... | ... | ... |

### 8.2 审计输出物

产出 `docs/codex/research/v6.10.18-skill-dependency-audit.md`：
- 每个 Skill 文件对 24 个字段的引用列表
- 字段删除对 Skill 功能的影响评估
- 需要修改的 Skill 清单和修改方案

**此审计必须在字段简化之前完成。**

---

## 9. 实施计划（修正：10 周，含审计前置阶段）

### 9.1 阶段 0：字段与 Skill 全量审计（2 周）← P0 前置条件

- [ ] 全量字段引用频率分析（backend + frontend + tests + skills）
- [ ] Skill 体系依赖分析（`skills/` 27 个文件逐一排查）
- [ ] 确认前端受影响组件清单
- [ ] 完成数据迁移脚本设计（含 `--dry-run`）
- [ ] 回滚脚本设计
- [ ] 确定渐进式弃用时间表（v6.10.18 标记 deprecated → v6.10.19 限制写入 → v6.11.0+ 移除）
- [ ] **产出审计报告（`v6.10.18-field-audit-report.md` + `v6.10.18-skill-dependency-audit.md`）**

### 9.2 阶段 1：风险评估 + 迁移方案设计（2 周）

- [ ] 基于审计结果，确定最终可删除字段清单
- [ ] 完成数据迁移脚本（SQL + Python）
- [ ] 完成前端适配方案
- [ ] 完成 Skill 适配方案（如需修改）
- [ ] 代码审查：审计报告 + 迁移方案

### 9.3 阶段 2：字段简化 + 模型更新（3 周）

- [ ] 更新 `ChapterBrief` 模型定义（保留 deprecated 字段）
- [ ] 实现统一验证器（含插件扩展点）
- [ ] 前端表单同步更新（隐藏 deprecated 字段，新增字段输入）
- [ ] 数据迁移脚本执行（开发环境 → 测试环境 → 生产环境）
- [ ] Skill 体系适配（如有 Skill 依赖删除字段，需同步修改）

### 9.4 阶段 3：验证 + 文件合并（3 周）

- [ ] 合并 Quality 模块文件（19 → 8）
- [ ] 合并 Validators 模块文件（10 → 3）
- [ ] 更新导入路径
- [ ] 全量 pytest（3748 个测试）
- [ ] 前端 typecheck + build + vitest
- [ ] version.py bump → 6.10.18
- [ ] CHANGELOG.md 更新

---

## 10. 预期收益

### 10.1 量化目标（修正）

| 指标 | 当前 | 目标 | 改进 |
|------|------|------|------|
| 字段数量 | 24 个 | 10-12 个 | -50%~-58% |
| 验证文件 | 29 个 | 15-20 个 | -31%~-48% |
| 验证层级 | 6 层 | 2 层（含插件扩展点） | -67% |
| 验证代码量 | ~5000 行 | ~2500 行 | -50% |

### 10.2 质量提升（修正）

- 字段错误率降低（无具体基准，移除拍脑袋指标）
- 验证速度提升（待审计后提供基准测试数据）
- 文档维护成本降低（字段减少 → 文档减少）

---

## 11. 风险与缓解（扩充）

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 前置审计缺失导致删除关键字段 | 高 | **High** | **阶段 0 为 P0 前置条件；审计报告必须经过代码审查** |
| 字段缺失影响功能 | 高 | High | 渐进式弃用（3 阶段）；保留数据库列 1-2 版本 |
| 数据迁移丢失 | 中 | High | `--dry-run` + 回滚脚本 + 抽样验证 |
| Skill 体系失效 | 中 | High | 字段审计时排查 `skills/` 引用；必要时保留字段或修改 Skill |
| 前端表单破坏 | 中 | Medium | 同步更新前端；隐藏 deprecated 字段而非删除 |
| 验证逻辑遗漏 | 中 | Medium | 全量回归测试（3748 个测试）；保留插件扩展点 |
| 文件合并破坏导入 | 低 | Low | 统一更新导入路径；提供兼容层 |
| 用户已有项目数据损坏 | 低 | High | 数据迁移脚本 + 备份 + 回滚方案 |

---

## 12. 执行清单

### 12.1 阶段 0：字段与 Skill 全量审计（P0 前置条件）
- [ ] 字段引用频率统计（backend / frontend / tests / skills）
- [ ] Skill 依赖分析（`skills/` 27 个文件逐一排查）
- [ ] 前端影响组件清单
- [ ] 数据迁移脚本设计（含 `--dry-run`）
- [ ] 回滚脚本设计
- [ ] 渐进式弃用时间表确认
- [ ] **产出审计报告（`v6.10.18-field-audit-report.md` + `v6.10.18-skill-dependency-audit.md`）**

### 12.2 阶段 1：风险评估 + 迁移方案设计
- [ ] 基于审计结果确定最终删除字段清单
- [ ] 数据迁移脚本（SQL + Python）
- [ ] 前端适配方案
- [ ] Skill 适配方案
- [ ] 代码审查

### 12.3 阶段 2：字段简化 + 模型更新
- [ ] 更新 `ChapterBrief` 模型（保留 deprecated 字段）
- [ ] 实现统一验证器（含插件扩展点）
- [ ] 前端表单同步更新
- [ ] 数据迁移脚本执行（开发 → 测试 → 生产）
- [ ] Skill 适配（如有需要）

### 12.4 阶段 3：验证 + 文件合并
- [ ] Quality 模块合并（19 → 8）
- [ ] Validators 模块合并（10 → 3）
- [ ] 更新导入路径
- [ ] 全量 pytest（3748 个测试）
- [ ] 前端 typecheck + build + vitest
- [ ] version.py bump → 6.10.18
- [ ] CHANGELOG.md 更新
