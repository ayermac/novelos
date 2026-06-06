"""VersionRegressionGuard - 通用版本退化保护（v6.6.0）

防止返修稿比当前版本更差时覆盖正文。
适用于所有项目、所有章节。
"""

from __future__ import annotations
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class VersionRegressionGuard:
    """通用版本退化保护器"""

    @staticmethod
    def should_reject_new_draft(
        current_content: str,
        new_content: str,
        word_target: int,
        editor_suggestions: list[str] | None = None,
        current_score: float | None = None,
        new_score: float | None = None,
        allow_system_compression: bool = False,
    ) -> tuple[bool, str]:
        """
        判断是否应该拒绝新稿覆盖当前正文。

        返回: (should_reject, reason)
        """
        from ..validators.chapter_checker import count_words
        from ..validators.word_count_policy import DEFAULT_POLICY

        current_wc = count_words(current_content)
        new_wc = count_words(new_content)

        # 规则1: 当前已过 hard gate，新稿未过
        passed = DEFAULT_POLICY.evaluate(current_wc, word_target, "revision_guard")[1] != "hard_fail"
        new_passed = DEFAULT_POLICY.evaluate(new_wc, word_target, "revision_guard")[1] != "hard_fail"
        if passed and not new_passed:
            return True, f"新稿未满足字数硬门（当前 {current_wc}，新稿 {new_wc}，目标 {word_target}）"

        # 规则2: 新稿显著变短且 Editor 未明确要求压缩
        #
        # Internal hard-gate repair is also an explicit compression request.
        # Without this exception, an author/polisher draft can be compressed to
        # satisfy the canonical word-count gate and then immediately rejected as
        # a version regression, creating a retry loop.
        if current_wc > 0:
            shrink_ratio = (current_wc - new_wc) / current_wc
            compress_requested = any(
                "压缩" in s or "缩短" in s or "精简" in s
                for s in (editor_suggestions or [])
            )
            if shrink_ratio > 0.15 and not compress_requested and not allow_system_compression:
                return True, f"新稿比当前短 {shrink_ratio:.1%}，且 Editor 未要求压缩"

        # 规则3: deterministic score 显著下降
        if current_score is not None and new_score is not None:
            if new_score < current_score - 10:
                return True, f"新稿质量分下降超过10分（{current_score} → {new_score}）"

        return False, ""


def apply_regression_protection(
    repo: Any,
    project_id: str,
    chapter_number: int,
    new_content: str,
    word_target: int,
    **kwargs
) -> dict[str, Any]:
    """在保存前调用此函数进行退化保护"""
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter or not chapter.get("content"):
        return {"reject": False, "reason": "无历史版本，直接保存"}

    current_content = chapter["content"]
    guard = VersionRegressionGuard()
    reject, reason = guard.should_reject_new_draft(
        current_content, new_content, word_target, **kwargs
    )

    if reject:
        # 保存为 rejected artifact
        repo.save_artifact(
            project_id, chapter_number, "author", "rejected_regression",
            content_json={"content": new_content, "rejection_reason": reason}
        )
        logger.warning("VersionRegressionGuard 拒绝覆盖: %s", reason)
        return {"reject": True, "reason": reason, "kept_previous": True}

    return {"reject": False, "reason": ""}
