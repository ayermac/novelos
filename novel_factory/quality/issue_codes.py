"""v6.8.5: 结构化问题代码定义

用于替代字符串匹配，确保路由逻辑稳定。
"""

from __future__ import annotations

from enum import Enum


class IssueCode(str, Enum):
    """质量问题代码枚举"""

    # 死刑红线类（阻塞，返修目标：author）
    DEATH_PENALTY = "death_penalty"

    # 字数门禁类（阻塞，返修目标：polisher）
    WORD_COUNT_BELOW_MIN = "word_count_below_min"
    WORD_COUNT_ABOVE_MAX = "word_count_above_max"

    # 章间衔接类（阻塞，返修目标：author）
    CHAPTER_SEAM_BREAK = "chapter_seam_break"

    # 叙事连续性类（阻塞，返修目标：author）
    CONTINUITY_TIME_REGRESSION = "continuity_time_regression"
    CONTINUITY_EVENT_REPLAY = "continuity_event_replay"
    CONTINUITY_TITLE_TRUNCATION = "continuity_title_truncation"

    # 事实一致性类（阻塞，返修目标：author）
    STORY_FACTS_CONTRADICTION = "story_facts_contradiction"

    # 质量诊断类（优先级，返修目标：polisher）
    QUALITY_AI_TRACE = "quality_ai_trace"
    QUALITY_NARRATIVE_LOW = "quality_narrative_low"
    QUALITY_STYLE_ISSUE = "quality_style_issue"

    # 检查器错误类（非阻塞）
    CHECKER_CONFIG_ERROR = "checker_config_error"
    CHECKER_TEMPORARY_FAILURE = "checker_temporary_failure"
    CHECKER_TIMEOUT = "checker_timeout"


# 问题代码到返修目标的映射
ISSUE_CODE_TO_REVISION_TARGET: dict[IssueCode, str] = {
    # 死刑红线 → author
    IssueCode.DEATH_PENALTY: "author",

    # 字数门禁 → polisher
    IssueCode.WORD_COUNT_BELOW_MIN: "polisher",
    IssueCode.WORD_COUNT_ABOVE_MAX: "polisher",

    # 章间衔接 → author
    IssueCode.CHAPTER_SEAM_BREAK: "author",

    # 叙事连续性 → author
    IssueCode.CONTINUITY_TIME_REGRESSION: "author",
    IssueCode.CONTINUITY_EVENT_REPLAY: "author",
    IssueCode.CONTINUITY_TITLE_TRUNCATION: "author",

    # 事实一致性 → author
    IssueCode.STORY_FACTS_CONTRADICTION: "author",

    # 质量诊断 → polisher
    IssueCode.QUALITY_AI_TRACE: "polisher",
    IssueCode.QUALITY_NARRATIVE_LOW: "polisher",
    IssueCode.QUALITY_STYLE_ISSUE: "polisher",
}


def get_revision_target_for_issue_code(code: IssueCode) -> str:
    """根据问题代码获取返修目标"""
    return ISSUE_CODE_TO_REVISION_TARGET.get(code, "polisher")


class QualityCheckError(Exception):
    """质量检查错误基类"""

    def __init__(self, message: str, code: IssueCode, is_blocking: bool = False):
        super().__init__(message)
        self.code = code
        self.is_blocking = is_blocking


class CheckerConfigError(QualityCheckError):
    """检查器配置错误（应阻塞）"""

    def __init__(self, message: str, checker_name: str):
        super().__init__(
            message,
            code=IssueCode.CHECKER_CONFIG_ERROR,
            is_blocking=True,
        )
        self.checker_name = checker_name


class CheckerTemporaryFailure(QualityCheckError):
    """检查器临时故障（可降级）"""

    def __init__(self, message: str, checker_name: str):
        super().__init__(
            message,
            code=IssueCode.CHECKER_TEMPORARY_FAILURE,
            is_blocking=False,
        )
        self.checker_name = checker_name


class CheckerTimeoutError(QualityCheckError):
    """检查器超时（应重试）"""

    def __init__(self, message: str, checker_name: str, timeout_seconds: float):
        super().__init__(
            message,
            code=IssueCode.CHECKER_TIMEOUT,
            is_blocking=False,
        )
        self.checker_name = checker_name
        self.timeout_seconds = timeout_seconds
