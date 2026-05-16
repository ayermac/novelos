# v6.4.0 Quality Diagnosis Baseline 完成报告

## 总体 verdict：PASS

## 改动文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `novel_factory/quality/hub.py` | 修改 | 新增 `diagnose` 方法，聚合 death_penalty、ai_style_detector、narrative_quality、show_dont_tell、info_dump |
| `novel_factory/api/routes/quality_diagnosis.py` | 新增 | `GET /projects/{pid}/chapters/{n}/quality-diagnosis` API |
| `novel_factory/api/routes/__init__.py` | 修改 | 导出新路由 |
| `novel_factory/api_app.py` | 修改 | 注册质量诊断路由 |
| `novel_factory/workflow/execution_events.py` | 修改 | 新增 `EVENT_QUALITY_DIAGNOSED` 常量 |
| `frontend/src/components/project/QualityDiagnosisPanel.tsx` | 新增 | 质量诊断折叠面板 |
| `frontend/src/components/project/AuthorWritingSurface.tsx` | 修改 | ContentBody 中接入 QualityDiagnosisPanel |
| `tests/test_v64_quality_diagnosis.py` | 新增 | 10 个测试覆盖 diagnose 逻辑和 API |
| `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md` | 修改 | v6.4.0 状态更新为已实现 |

## diagnose 方法输出结构

```json
{
  "overall_score": 62.5,
  "dimensions": {
    "death_penalty": 100,
    "ai_trace": 85,
    "narrative_quality": 55.3,
    "conflict_intensity": 40,
    "hook_strength": 60,
    "information_density": 50,
    "pacing_control": 70,
    "dialogue_naturalness": 65,
    "scene_immersion": 45,
    "character_motivation": 55,
    "show_dont_tell": 35,
    "info_density": 70
  },
  "findings": [
    {
      "severity": "medium",
      "code": "SHOW_DONT_TELL_STRAIGHT_EMOTION",
      "message": "检测到 5 处直白情绪表达（每千字约 3.2 处）",
      "evidence": {"count": 5, "per_1000_words": 3.2},
      "suggestion": "建议将'感到/觉得/意识到'等改为动作、神态或对话展现"
    }
  ],
  "metrics": {
    "word_count": 1560,
    "paragraph_count": 12,
    "sentence_count": 48,
    "avg_sentence_length": 32.5,
    "dialogue_ratio": 0.15,
    "dialogue_count": 8
  }
}
```

## 测试结果

| 命令 | 结果 |
|---|---|
| `python3 -m pytest tests/test_v64_quality_diagnosis.py -q` | **10 passed** |
| `python3 scripts/verify.py smoke` | **27 passed** |
| `python3 -m pytest -q` | **1990 passed, 0 failed** |
| `cd frontend && npm run typecheck` | **通过** |
| `cd frontend && npm run lint` | **通过** |
| `cd frontend && npm run build` | **通过** |
| `cd frontend && npm run test -- --run` | **169 passed** |

## 已知限制

- `diagnose` 方法目前只在 API 调用时执行，尚未自动接入 workflow 节点（v6.4.1+ 计划）
- show-dont-tell 和 info-dump 检测基于简单正则，v6.4.3 将升级为更精准的 deterministic validator
- 前端面板只在有正文的章节显示，空章节隐藏
- 质量诊断不触发 LLM，所有分数均为 deterministic 计算

## 安全继续开发：是
