"""最佳版本恢复能力（v6.6.0）"""

from __future__ import annotations
from typing import Any, Optional

from ..validators.chapter_checker import count_words


def find_best_chapter_version(
    repo: Any,
    project_id: str,
    chapter_number: int,
    word_target: int | None = None,
) -> Optional[dict[str, Any]]:
    """
    找到最佳历史版本
    评分依据：满足 hard gate > review score > deterministic score > 较新版本
    """
    if hasattr(repo, "get_chapter_versions"):
        versions = repo.get_chapter_versions(project_id, chapter_number)
    else:
        versions = repo.list_chapter_versions(project_id, chapter_number)
    if not versions:
        return None

    best = None
    best_score = -1

    for v in versions:
        if not v.get("content") and hasattr(repo, "get_version_by_id"):
            full = repo.get_version_by_id(project_id, v.get("id"))
            if full:
                v = {**v, **full}
        content = v.get("content", "")
        wc = v.get("word_count") or count_words(content)
        score = v.get("review_score", 0) or 0
        det_score = v.get("deterministic_score", 0) or 0

        # 基础过滤：必须有内容
        if not content or wc < 100:
            continue

        # 优先满足字数
        word_ok = True
        if word_target:
            word_ok = wc >= int(word_target * 0.85)

        recency = float(v.get("version") or 0) * 0.01
        total = (100 if word_ok else 0) + score * 0.6 + det_score * 0.4 + recency

        if total > best_score:
            best_score = total
            best = v

    return best


def restore_best_version(
    repo: Any,
    project_id: str,
    chapter_number: int,
    word_target: int | None = None,
) -> dict[str, Any]:
    """执行恢复操作"""
    best = find_best_chapter_version(repo, project_id, chapter_number, word_target)
    if not best:
        return {"success": False, "error": "未找到可恢复的最佳版本"}

    # 恢复到 chapters 表
    repo.save_chapter_content(
        project_id, chapter_number, best["content"], best.get("title")
    )

    # 记录新版本
    repo.save_version(
        project_id, chapter_number, best["content"],
        created_by="restore_best_version",
        source="restore_best_version",
        summary=f"恢复历史最佳版本 {best.get('version') or best.get('id')}",
    )

    return {
        "success": True,
        "restored_version_id": best.get("id"),
        "word_count": count_words(best["content"]),
        "score": best.get("review_score"),
    }
