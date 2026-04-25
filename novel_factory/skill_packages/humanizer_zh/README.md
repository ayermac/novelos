# HumanizerZhSkill Package

## 概述

HumanizerZhSkill 是一个中文AI去味工具，用于检测和修复中文文本中的AI写作风格，使其更自然、更像人类写作。

## 功能特性

- **模板连接词替换**: 替换AI常用的模板化连接词
- **空泛心理描写替换**: 替换空泛的心理描写
- **夸张情绪词替换**: 替换夸张的情绪表达
- **高频套话替换**: 替换陈词滥调
- **机械解释替换**: 替换机械化的解释方式
- **三段式排比检测**: 检测三段式排比结构
- **同质句式重复检测**: 检测相似句式的重复使用
- **事实保护**: 保护文本中的关键事实信息

## 目录结构

```
humanizer_zh/
├── manifest.yaml          # Skill清单文件
├── handler.py             # Skill处理器
├── prompts/               # Prompt模板
│   ├── system.md         # 系统提示
│   └── rewrite.md        # 改写指南
├── rules/                 # 规则配置
│   ├── replacements.yaml # 替换规则
│   └── protected_patterns.yaml # 事实保护模式
├── tests/                 # 测试
│   └── fixtures.yaml     # 测试用例
└── README.md             # 说明文档
```

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `preserve_facts` | boolean | true | 是否保护事实 |
| `max_change_ratio` | number | 0.35 | 最大修改比例 |
| `fail_on_fact_risk` | boolean | true | 事实风险时是否失败 |

## 使用示例

### CLI

```bash
# 基本使用
novelos skills run humanizer-zh --text "然而，这是一个测试。"

# 使用配置
novelos skills run humanizer-zh --text "..." --config '{"preserve_facts": false}'

# 自测
novelos skills test humanizer-zh
```

### Python API

```python
from novel_factory.skills.registry import SkillRegistry

registry = SkillRegistry()
result = registry.run_skill(
    "humanizer-zh",
    {
        "text": "然而，这是一个测试。",
        "fact_lock": {"key_events": ["重要事件"]}
    },
    agent="polisher",
    stage="after_llm"
)

print(result["data"]["humanized_text"])
```

## 输出格式

```json
{
  "ok": true,
  "error": null,
  "data": {
    "humanized_text": "但这是一个测试。",
    "changes": [
      {
        "type": "template_connector",
        "original": "然而，",
        "replacement": "但",
        "position": 0
      }
    ],
    "change_ratio": 0.1,
    "risk_level": "low",
    "preserved_facts": []
  }
}
```

## 风险等级

- `none`: 无风险
- `low`: 改动比例低于70%阈值
- `medium`: 改动比例在70%-100%阈值之间
- `high`: 改动比例超过阈值
- `critical`: 检测到事实破坏

## 注意事项

1. 三段式排比和同质句式重复只检测不自动修复，建议人工审核
2. 事实保护功能依赖fact_lock参数提供的关键事件列表
3. 改写比例过高时会标记为高风险

## 版本历史

- v2.3.0: Package化，新增rules/prompts/fixtures
- v2.2.0: Manifest化，新增权限声明
- v2.1.0: 初始版本，实现基本AI去味功能
