# AIStyleDetectorSkill Package

## 概述

AIStyleDetectorSkill 是一个AI风格检测工具，用于分析文本中的AI生成痕迹，提供评分和改进建议。

## 功能特性

- **模板句式检测**: 检测AI常用的固定句式模板
- **连接词密度分析**: 分析连接词使用频率
- **空泛情绪检测**: 检测空泛的情绪描写
- **句式重复检测**: 检测句式结构的重复度
- **过度解释检测**: 检测过度解释模式
- **综合评分**: 提供综合AI痕迹评分
- **改进建议**: 生成针对性的改进建议

## 目录结构

```
ai_style_detector/
├── manifest.yaml          # Skill清单文件
├── handler.py             # Skill处理器
├── rules/                 # 规则配置
│   └── ai_patterns.yaml  # AI模式规则
├── tests/                 # 测试
│   └── fixtures.yaml     # 测试用例
└── README.md             # 说明文档
```

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `warn_threshold` | number | 45 | 警告阈值 |
| `fail_threshold` | number | 70 | 失败阈值 |

## 使用示例

### CLI

```bash
# 基本使用
novelos skills run ai-style-detector --text "然而，这是一个测试。"

# 自测
novelos skills test ai-style-detector
```

### Python API

```python
from novel_factory.skills.registry import SkillRegistry

registry = SkillRegistry()
result = registry.run_skill(
    "ai-style-detector",
    {"text": "然而，这是一个测试。"},
    agent="polisher",
    stage="before_save"
)

print(f"AI Trace Score: {result['data']['ai_trace_score']}")
print(f"Risk Level: {result['data']['risk_level']}")
```

## 输出格式

```json
{
  "ok": true,
  "error": null,
  "data": {
    "ai_trace_score": 65,
    "risk_level": "medium",
    "blocking": false,
    "template_phrase_score": 70,
    "connector_density_score": 40,
    "vague_emotion_score": 60,
    "sentence_repetition_score": 30,
    "over_explanation_score": 50,
    "issues": [
      {
        "type": "template_phrases",
        "score": 70,
        "description": "检测到较多模板句式"
      }
    ],
    "warnings": [],
    "suggestions": [
      "减少使用固定句式模板",
      "用具体细节替代空泛情绪描写"
    ]
  }
}
```

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 模板句式 | 25% | AI常用固定句式模板 |
| 连接词密度 | 20% | 连接词使用频率 |
| 空泛情绪 | 25% | 空泛的情绪描写 |
| 句式重复 | 15% | 句式结构重复度 |
| 过度解释 | 15% | 过度解释模式 |

## 风险等级

- `low`: AI痕迹较低（< 45分）
- `medium`: 存在一定AI痕迹（45-70分）
- `high`: AI痕迹明显（>= 70分），阻断发布

## 适用场景

- **Polisher**: 在润色后检测AI痕迹
- **Editor**: 在最终审核时检测AI痕迹
- **QualityHub**: 质量检查入口
- **Manual**: 手动调用检测

## 版本历史

- v2.3.0: Package化，新增rules/fixtures
- v2.2.0: Manifest化，新增权限声明
- v2.1.0: 初始版本，实现基本AI检测功能
