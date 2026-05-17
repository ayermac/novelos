"""DeadloopDetector - 通用死循环检测与熔断（v6.6.0）"""

from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)


class DeadloopDetector:
    """检测并阻断章节生产死循环"""

    VERSION_THRESHOLD = 20
    FAILED_RUNS_THRESHOLD = 5
    NO_IMPROVEMENT_THRESHOLD = 3

    @staticmethod
    def _count_versions(
        repo: Any,
        project_id: str,
        chapter_number: int,
        since: str | None = None,
    ) -> int:
        if hasattr(repo, "get_chapter_version_count"):
            try:
                return int(repo.get_chapter_version_count(project_id, chapter_number, since=since) or 0)
            except TypeError:
                return int(repo.get_chapter_version_count(project_id, chapter_number) or 0)
        if hasattr(repo, "list_chapter_versions"):
            versions = repo.list_chapter_versions(project_id, chapter_number)
            if since:
                versions = [
                    version
                    for version in versions
                    if str(version.get("created_at") or "") > since
                ]
            return len(versions)
        return 0

    @staticmethod
    def _latest_reset_marker(repo: Any, project_id: str, chapter_number: int) -> str | None:
        if hasattr(repo, "get_latest_chapter_reset_marker"):
            return repo.get_latest_chapter_reset_marker(project_id, chapter_number)
        return None

    @staticmethod
    def _count_failed_runs(
        repo: Any,
        project_id: str,
        chapter_number: int,
        since: str | None = None,
    ) -> int:
        if hasattr(repo, "count_recent_failed_workflow_runs"):
            try:
                return int(repo.count_recent_failed_workflow_runs(project_id, chapter_number, since=since) or 0)
            except TypeError:
                return int(repo.count_recent_failed_workflow_runs(project_id, chapter_number) or 0)
        if hasattr(repo, "get_workflow_runs_for_project"):
            runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=20)
            return sum(
                1
                for run in runs
                if run.get("status") == "failed"
                and (not since or str(run.get("started_at") or "") > since)
            )
        return 0

    @classmethod
    def check_deadloop(
        cls,
        repo: Any,
        project_id: str,
        chapter_number: int,
        recent_scores: list[float] | None = None,
    ) -> dict[str, Any]:
        """
        返回: {"triggered": bool, "reason": str, "action": str}
        """
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return {"triggered": False}

        reset_marker = cls._latest_reset_marker(repo, project_id, chapter_number)
        version_count = cls._count_versions(repo, project_id, chapter_number, since=reset_marker)
        failed_runs = cls._count_failed_runs(repo, project_id, chapter_number, since=reset_marker)

        if version_count > cls.VERSION_THRESHOLD:
            return {
                "triggered": True,
                "reason": f"版本数超过阈值 ({version_count} > {cls.VERSION_THRESHOLD})",
                "action": "进入 human_review 并建议恢复最佳版本",
                "version_count": version_count,
                "failed_runs": failed_runs,
                "reset_marker_at": reset_marker,
            }

        if failed_runs > cls.FAILED_RUNS_THRESHOLD:
            return {
                "triggered": True,
                "reason": f"近期失败 workflow 过多 ({failed_runs})",
                "action": "停止自动重跑；请先恢复最佳版本，或人工确认重置后再开始新的尝试",
                "version_count": version_count,
                "failed_runs": failed_runs,
                "reset_marker_at": reset_marker,
            }

        if recent_scores and len(recent_scores) >= cls.NO_IMPROVEMENT_THRESHOLD:
            if max(recent_scores[-cls.NO_IMPROVEMENT_THRESHOLD:]) <= recent_scores[0]:
                return {
                    "triggered": True,
                    "reason": "连续多次返修分数未提升",
                    "action": "触发熔断，推荐恢复历史最佳版本",
                }

        return {"triggered": False}
