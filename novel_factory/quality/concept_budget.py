"""Single-chapter concept budget guidance and diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


CONCEPT_BUDGET_CONTRACT = """【单章概念预算】
- 本章只能引入 1 个核心新概念；核心新概念包括新的规则、新组织、新能力、新系统机制、新神秘物品或新势力。
- 允许复用前文已出现概念，但禁止在同一章同时解释第二个新概念。
- 本章新增专有名词不超过 2 个；如必须铺垫新线索，只能作为章末钩子一句带出，不得展开解释。
- 新概念必须被主角当章使用一次：用于决策、反击、获利、解谜或制造爽点。
- 章节结尾只能延伸本章核心概念的后果，不要再开启另一套设定。"""


_QUOTED_TERM_RE = re.compile(r"[「『“\"]([^」』”\"]{2,18})[」』”\"]")
_LATIN_CODE_RE = re.compile(r"\b[A-Z]{2,}[A-Z0-9_-]{1,12}\b")
_PERCENT_RE = re.compile(r"\d{2,3}(?:\.\d+)?%")
_CONCEPT_MARKERS = (
    "新规则",
    "新机制",
    "第一次",
    "首次",
    "从未标记",
    "未知",
    "陌生",
    "未记录",
    "新生",
    "权限",
    "节点",
    "特征码",
    "徽记",
    "请柬",
    "门票",
    "信标",
    "拍卖",
    "利息",
    "喂养",
)


@dataclass
class ConceptBudgetReport:
    """Advisory report for single-chapter concept load."""

    score: int
    introduced_terms: list[str] = field(default_factory=list)
    marker_count: int = 0
    overload: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "introduced_terms": self.introduced_terms,
            "marker_count": self.marker_count,
            "overload": self.overload,
        }


def diagnose_concept_budget(text: str) -> ConceptBudgetReport:
    """Return an advisory concept-budget signal for a chapter."""
    if not text:
        return ConceptBudgetReport(score=100)

    quoted_terms = [m.group(1).strip() for m in _QUOTED_TERM_RE.finditer(text)]
    latin_codes = [m.group(0).strip() for m in _LATIN_CODE_RE.finditer(text)]
    percentages = [m.group(0).strip() for m in _PERCENT_RE.finditer(text)]
    marker_count = sum(text.count(marker) for marker in _CONCEPT_MARKERS)

    seen: set[str] = set()
    introduced_terms: list[str] = []
    for term in quoted_terms + latin_codes + percentages:
        if term not in seen:
            seen.add(term)
            introduced_terms.append(term)

    overload = len(introduced_terms) > 6 or marker_count > 10
    score = 100
    score -= max(0, len(introduced_terms) - 2) * 8
    score -= max(0, marker_count - 4) * 4
    score = max(35, min(100, score))

    return ConceptBudgetReport(
        score=score,
        introduced_terms=introduced_terms[:12],
        marker_count=marker_count,
        overload=overload,
    )
