# v5.5.10 Bounded Autonomy Guardrails / 有界自动生产护栏

## 目标

把自动生产从“能连续跑”升级为“**有预算、有停机条件、有人工边界**”：
1. 自动生产不能无限自循环
2. token / 步数 / 时间必须可见、可配、可上限
3. 连续无进展时自动停机，避免看不见的 token 消耗
4. 真正需要人拍板的节点才进入人工介入
5. 用户能明确看到“为什么停、停了多少、下一步该做什么”

## 背景

v5.5.9 已经实现：
- session 持久化
- 刷新恢复
- SSE 断线重连
- 失败步重试
- active-session 续接

但产品上仍有一个核心缺口：**自动生产可以被配置得太“聪明”**，如果没有严格边界，就会在用户看不见的地方持续烧 token，却没有明显产出。

因此 v5.5.10 不再增加新自动动作，而是给现有自动能力加护栏。

## 产品原则

### 1. 自动化只负责推进，不负责无限试错

自动生产可以：
- 自动补缺失资料
- 自动生成章节指令
- 自动生成正文
- 自动重试可恢复错误

自动生产不可以：
- 无限制循环重试
- 在没有任何新内容时继续烧 token
- 在同一状态上反复空转

### 2. 人工只介入关键判断，不介入机械执行

人工应只处理：
- 创世批准
- 弧线/批次确认
- 重大冲突或题材偏离
- 最终发布

不应默认介入：
- 每章缺资料的机械补齐
- 每章重复的指令生成
- 已知模式下的稳定返修

### 3. 停机要可解释

任何自动停机都必须明确告诉用户：
- 停止原因
- 已执行步骤数
- 已消耗 token / 时间（如果可得）
- 当前卡在哪个章节或哪类动作
- 下一步建议的人工作业

## 范围

### 本期要覆盖

- 自动生产入口收敛（单一入口 + dry-run 开关）
- 自动生产预算上限与可见性
- 无进展停机（连续无有效产出）
- 重复状态停机（同一章节/动作连续失败）
- 同一章节/同一动作的重试上限
- 前端“停止原因”与“预算状态”展示
- 旧 session 清理能力

### 本期不做

- 不引入新的自动发布
- 不把所有阻塞都改成自动修复
- 不让 runner 无休止自愈
- 不替代人工审核节点
- 不做 `max_tokens` / `max_duration` 的精确统计（留待后续）

## 规则定义

### 预算护栏

自动生产必须支持以下上限：
- `max_steps`（已存在）
- `max_consecutive_no_progress`（新增，默认 3 步）
- `max_retries_per_step`（新增，默认 2 次）

任意一个触发，都必须停机。

### 无进展判定

定义为至少满足以下之一：
- 连续多步没有新增内容（`skipped`、`failed`、`dry_run`、`blocked`）
- 连续多步没有推进 chapter 状态
- 连续多步只产生相同警告或相同错误

当连续 `max_consecutive_no_progress` 步（默认 3）无进展时，触发停机，stop_reason=`consecutive_no_progress`。

### 重复判定

定义为：
- 同一 action 在同一目标章节连续失败
- 同一错误连续出现

当同一 (action, target_chapter) 组合连续失败达到 `max_retries_per_step` 次（默认 2）时，触发停机，stop_reason=`repeated_failure`。

### 人工闸门

以下情况必须停机并等待人工：
- 创世未批准
- 题材与书名契约不一致
- 章节范围已完成
- 需要重新定义 arc 或批次边界
- LLM 输出无法恢复且没有新信息

## API 变更

### 后端

1. `_auto_run_generator` 增加空转检测：
   - 每步完成后扫描最近 `max_consecutive_no_progress` 步
   - 如果全部为 `skipped`/`failed`/`blocked`/`dry_run`，则停机

2. `_auto_run_generator` 增加重复失败检测：
   - 每步失败后检查同一 `(action, target_chapter)` 的连续失败次数
   - 达到 `max_retries_per_step` 则停机

3. 新增 stop_reason：
   - `consecutive_no_progress`
   - `repeated_failure`

4. 新增 session 清理端点：
   - `DELETE /projects/{pid}/production/run-auto/sessions/{sid}` — 删除单个 session
   - `POST /projects/{pid}/production/run-auto/cleanup` — 清理已完成/失败/取消的旧 session

5. `RunAutoRequest` 增加可选字段：
   - `max_consecutive_no_progress: int = 3`
   - `max_retries_per_step: int = 2`

### 前端

1. 自动生产入口收敛：
   - 移除独立的“预览自动生产”和“开始自动生产”按钮
   - 保留一个主按钮，文案根据 dry-run checkbox 切换
   - 配置区增加 `dry_run` checkbox

2. 预算状态面板：
   - 显示当前 session 的 `current_step / max_steps`
   - 显示章节范围
   - 显示停止原因（中文映射）
   - 显示下一步建议操作

3. Session 历史增强：
   - 每个历史 session 显示删除按钮
   - 增加“清理已完成 session”批量操作

4. 停止原因中文映射扩展：
   - `consecutive_no_progress` → "连续无进展"
   - `repeated_failure` → "同一错误多次失败"

## 产品交互

### 自动生产控制台

控制台需要清晰显示：
- 当前 session
- 当前步骤 / 最大步数（进度条）
- 章节范围
- 停止原因
- 下一步建议

### 停机反馈

停机后必须给出：
- `stop_reason`
- `spent_steps`
- `last_progress_step`
- `next_manual_action`

### 继续按钮语义

“继续”不是无脑重跑，而是：
- 先检查预算是否还允许
- 先确认上次停机原因是否已被处理
- 再从安全点恢复

## 评估与监控

### 运行时指标

需要统计：
- 每次 session 的总步数
- 每次 session 的有效产出数
- 每次 session 的停机原因分布
- 每次 session 的无进展连续次数

### 体验指标

需要验证：
- 用户能看懂为什么停
- 用户能看懂这次跑了什么
- 用户不会误以为系统“还在干活”
- 用户能主动结束一个无效 session

## 验收标准

- 自动生产不会在无进展状态下无限循环
- 预算上限触发时，前端明确显示停机原因
- 用户能看到步数、章节范围、持续时间等消耗信息
- 同一错误不会被无限重试
- 人工只介入真正需要判断的点
- 自动生产不会悄悄烧 token 而没有可见结果
- 旧 session 可被清理
- 所有 v5.5.9 测试继续通过

