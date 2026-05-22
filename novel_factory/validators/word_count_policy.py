"""统一 WordCountPolicy (v6.6.0)

所有 Agent（Author/Polisher/Editor）必须使用同一套字数质量门规则。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass
class WordCountPolicy:
    hard_fail_ratio: float = 0.85
    warning_ratio: float = 0.90
    ideal_ratio: float = 1.0

    def evaluate(self, actual: int, target: int, agent: str = "author") -> Tuple[bool, str, str]:
        """
        返回: (passed, level, message)
        level: 'hard_fail' | 'warning' | 'ok'
        """
        if target <= 0:
            return True, "ok", "无目标字数"

        ratio = actual / target

        if ratio < self.hard_fail_ratio:
            return False, "hard_fail", f"字数严重不足（{actual}/{target}，{ratio:.0%}）"

        if ratio < self.warning_ratio:
            return True, "warning", f"字数偏低（{actual}/{target}，建议 ≥{int(target*self.warning_ratio)}）"

        return True, "ok", f"字数达标（{actual}/{target}）"


# 全局单例，供各 Agent 统一使用
DEFAULT_POLICY = WordCountPolicy()


def check_word_count_with_policy(actual: int, target: int, agent: str = "author") -> Tuple[bool, str]:
    """统一入口，所有 Agent 都应调用此函数"""
    passed, level, msg = DEFAULT_POLICY.evaluate(actual, target, agent)
    return passed, msg