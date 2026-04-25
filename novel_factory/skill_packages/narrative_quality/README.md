# NarrativeQualityScorer Package

## 概述

NarrativeQualityScorer 是一个叙事质量评分工具，用于评估文本的叙事质量，提供多维度评分和改进建议。

## 功能特性

- **冲突强度评分**: 检测文本中的冲突元素密度
- **钩子强度评分**: 检测章末悬念、转折等钩子
- **信息密度评分**: 检测文本中的信息量
- **节奏控制评分**: 检测文本的节奏变化
- **对话自然度评分**: 检测对话的比例和自然程度
- **场景沉浸感评分**: 检测场景描写的丰富程度
- **人物动机清晰度评分**: 检测人物动机的表达
- **综合评分**: 提供综合叙事质量评分
- **等级评定**: 提供S/A/B/C/D/F等级
- **改进建议**: 生成针对性的改进建议

## 目录结构

```
narrative_quality/
├── manifest.yaml          # Skill清单文件
├── handler.py             # Skill处理器
├── rules/                 # 规则配置
│   └── scoring_rules.yaml # 评分规则
├── tests/                 # 测试
│   └── fixtures.yaml     # 测试用例
└── README.md             # 说明文档
```

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `min_conflict_score` | number | 40 | 最低冲突分要求 |
| `min_hook_score` | number | 50 | 最低钩子分要求 |
| `min_dialogue_ratio` | number | 0.1 | 最低对话比例 |
| `pass_score` | number | 75 | 及格分数 |

## 使用示例

### CLI

```bash
# 基本使用
novelos skills run narrative-quality --text "章节文本..."

# 自测
novelos skills test narrative-quality
```

### Python API

```python
from novel_factory.skills.registry import SkillRegistry

registry = SkillRegistry()
result = registry.run_skill(
    "narrative-quality",
    {"text": "章节文本..."},
    agent="editor",
    stage="final_gate"
)

print(f"Overall Score: {result['data']['scores']['overall_score']}")
print(f"Grade: {result['data']['grade']}")
```

## 输出格式

```json
{
  "ok": true,
  "error": null,
  "data": {
    "scores": {
      "conflict_intensity": 65.5,
      "hook_strength": 70.0,
      "information_density": 55.3,
      "pacing_control": 68.2,
      "dialogue_naturalness": 72.1,
      "scene_immersion": 48.6,
      "character_motivation": 52.4,
      "overall_score": 61.7
    },
    "issues": [
      {
        "type": "low_scene",
        "severity": "info",
        "score": 48.6,
        "message": "场景描写较少，可增加感官细节"
      }
    ],
    "suggestions": [
      "建议增加视觉、听觉、嗅觉等感官描写，增强沉浸感"
    ],
    "grade": "B"
  }
}
```

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 冲突强度 | 14.3% | 检测冲突元素密度 |
| 钩子强度 | 14.3% | 检测章末钩子 |
| 信息密度 | 14.3% | 检测信息量 |
| 节奏控制 | 14.3% | 检测节奏变化 |
| 对话自然度 | 14.3% | 检测对话质量 |
| 场景沉浸感 | 14.3% | 检测场景描写 |
| 人物动机 | 14.3% | 检测动机表达 |

## 等级评定

- **S**: 90分以上，优秀
- **A**: 80-89分，良好
- **B**: 70-79分，中等
- **C**: 60-69分，及格
- **D**: 50-59分，不及格
- **F**: 50分以下，失败

## 适用场景

- **Editor**: 在最终审核时评估叙事质量
- **QualityHub**: 质量检查入口
- **Manual**: 手动调用评估

## 版本历史

- v2.3.0: Package化，新增rules/fixtures
- v2.2.0: Manifest化，新增权限声明
- v2.1.0: 初始版本，实现基本叙事质量评分功能
