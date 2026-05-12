# v4.2: Style Sample Analyzer & Calibration

## 背景

v4.1 将 Style Bible 从"可检查"升级为"可治理"，支持 Style Gate、版本记录和人工确认的风格演进提案。v4.2 在此基础上新增"风格样本分析与校准"能力——用户可导入本地样本文本，系统提取结构化风格特征，并基于样本特征生成 Style Bible 演进提案。

## 目标

- 支持导入本地文本样本，提取结构化风格指标
- 基于样本指标生成 Style Evolution Proposals
- QualityHub 轻集成：用样本风格基线作为 warning 维度
- 不模仿作者、不联网、不训练模型、不保存全文、不自动修改 Style Bible

## 安全边界

1. **禁止联网** — 不抓取网络小说、作者作品、付费内容
2. **禁止模仿作者** — 不出现 author_name、imitate_author、"模仿某某"等字段
3. **禁止训练模型** — 不微调、不训练任何模型
4. **禁止保存全文** — 只保存 preview(≤500字符)、hash、metrics
5. **禁止自动修改 Style Bible** — proposal 须人工 approve，且 approve 也不自动应用
6. **禁止自动覆盖现有 Style Bible**
7. **禁止自动挂载到 Agent 主流程**
8. **禁止新增 Web UI**
9. **禁止新增真实 LLM 调用**
10. **禁止引入 Redis/Celery/Kafka/PostgreSQL**

## 数据结构

### style_samples 表 (migration 014)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| project_id | TEXT NOT NULL | 项目ID, FK projects |
| name | TEXT NOT NULL | 样本名称 |
| source_type | TEXT NOT NULL | local_text / manual |
| content_hash | TEXT NOT NULL | SHA-256 |
| content_preview | TEXT | ≤500字符预览 |
| metrics_json | TEXT | 结构化指标 |
| analysis_json | TEXT | 分析摘要 |
| status | TEXT | imported/analyzed/deleted |
| created_at | TEXT NOT NULL | 创建时间 |
| analyzed_at | TEXT | 分析完成时间 |

UNIQUE(project_id, content_hash) — 避免重复导入

### StyleSampleMetrics 指标

- char_count: 字符数
- paragraph_count: 段落数
- sentence_count: 句子数
- avg_sentence_length: 平均句长
- avg_paragraph_length: 平均段长
- dialogue_ratio: 对话占比
- action_ratio: 动作描写占比
- description_ratio: 描写占比
- psychology_ratio: 心理描写占比
- punctuation_density: 标点密度
- short_sentence_ratio: 短句占比
- long_sentence_ratio: 超长句占比
- ai_trace_risk: AI痕迹风险(low/medium/high)
- tone_keywords: 氛围关键词列表
- rhythm_notes: 节奏描述列表

## 分析规则

纯规则分析，不调用 LLM：

- 句子按 `。！？!?` 切分
- 段落按空行或换行切分
- 对话按中文/英文引号估算
- 动作词、心理词、描写词用内置小词表估算
- AI trace risk 基于模式匹配
- tone_keywords 从高频氛围词提取，排除作者名/作品名

## CLI 命令

```
novelos style sample-import   --project-id ID --file PATH [--name NAME] --json
novelos style sample-analyze  --sample-id ID --json
novelos style sample-list     --project-id ID --json
novelos style sample-show     --sample-id ID --json
novelos style sample-delete   --sample-id ID --json
novelos style sample-propose  --project-id ID --sample-id ID|--sample-ids IDS --json
```

所有输出稳定 envelope: `{ok, error, data}`

### 约束

- import 文件不存在/空/二进制/超200KB → 错误 envelope
- show 默认不输出全文，只输出 preview + metrics + analysis
- delete 软删除 (status=deleted)
- propose 成功返回 proposal_ids
- proposal 保存失败返回 ok=false

## Proposal 行为

- 读取样本 metrics/analysis
- 聚合平均值
- 生成 pending style_evolution_proposals
- proposal_type 使用已有类型: ADJUST_PACING, ADD_SENTENCE_RULE, ADD_PARAGRAPH_RULE, ADD_TONE_KEYWORD 等
- 不自动修改 Style Bible
- 不把样本文本全文写入 proposal
- proposal rationale 只写统计结果和风格建议，不写"模仿某作者"
- 每条 proposal_json 包含 `safety_note: "Derived from user-provided samples; not author imitation."`

## QualityHub 轻集成

- `_apply_style_sample_alignment()` 方法
- 读取项目 analyzed 样本的 metrics 基线
- 分析当前内容的 avg_sentence_length
- 计算 alignment 分数 (0-100)
- 添加 `quality_dimensions["style_sample_alignment"]`
- alignment < 60 时添加 warning
- 不阻塞主流程
- 没有样本时静默跳过

## 测试计划

1. migration 014 幂等
2. save/list/show/delete style sample
3. 重复 content_hash 不重复导入
4. analyze 正常文本生成 metrics
5. analyze 空文本返回错误
6. import 文件不存在返回 envelope
7. import 超大文件返回 envelope
8. import 不保存全文
9. CLI 全部可用
10. propose 从样本生成 pending proposals
11. proposal approve 不自动修改 Style Bible
12. QualityHub 没有样本时不报错
13. QualityHub 有样本时加入 alignment 维度
14. 不出现作者模仿字段
15. 所有错误路径无 traceback
16. 全量测试通过
17. 文件大小策略通过

## 禁止范围

- 不实现 style_sample_events 审计表（本轮可选，未实现）
- 不实现嵌套 sample 子命令组（使用扁平 sample-import/sample-list 等命令名）
- 不实现 Web UI
- 不修改主 Agent 编排顺序
