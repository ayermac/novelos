"""Internal tool handlers for chapter/version/diff queries."""

from __future__ import annotations

from typing import Any


def handle_chapter_version_diff(payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
    if repo is None:
        return {"error": "Repository not available"}
    project_id = payload.get("project_id", "")
    chapter_number = payload.get("chapter_number", 0)

    try:
        chapter = repo.get_chapter(project_id, chapter_number)
        versions = repo.list_chapter_versions(project_id, chapter_number)
    except Exception as e:
        return {"error": str(e)}

    return {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "current_status": chapter.get("status") if chapter else None,
        "version_count": len(versions) if versions else 0,
        "latest_version_id": versions[0]["id"] if versions else None,
    }


def handle_local_rewrite(payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
    if repo is None:
        return {"error": "Repository not available"}
    project_id = payload.get("project_id", "")
    chapter_number = payload.get("chapter_number", 0)
    target = payload.get("target", "")
    replacement = payload.get("replacement", "")

    try:
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter or not chapter.get("content"):
            return {"error": "Chapter content not found"}
        content = chapter["content"]
        if target not in content:
            return {"error": "Target text not found in chapter content", "target": target}
        new_content = content.replace(target, replacement, 1)
        repo.save_chapter_content(project_id, chapter_number, new_content, chapter.get("title", ""))
        repo.save_version(project_id, chapter_number, new_content, created_by="local_rewrite")
        return {"ok": True, "replaced": True, "old_length": len(content), "new_length": len(new_content)}
    except Exception as e:
        return {"error": str(e)}
