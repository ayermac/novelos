from novel_factory.agent_runtime.chapter_text import ensure_chapter_heading, is_chapter_heading
from novel_factory.api.routes.projects import _chapter_display_content, _chapter_display_title


def test_chapter_heading_recognizes_placeholder_parentheses():
    assert is_chapter_heading("第 2 章（待命名）", 2)
    assert is_chapter_heading("第二章（未命名）", 2)


def test_ensure_chapter_heading_replaces_placeholder_heading():
    content = "第 2 章（待命名）\n\n林逸盯着手机屏幕。"

    normalized = ensure_chapter_heading(content, "第2章 提交按钮", 2)

    assert normalized == "第2章 提交按钮\n\n林逸盯着手机屏幕。"


def test_project_display_collapses_duplicate_placeholder_headings():
    chapter = {
        "chapter_number": 2,
        "title": "第 2 章（待命名）",
        "content": "第 2 章（待命名）\n\n第 2 章（待命名）\n\n林逸盯着手机屏幕。",
    }

    display_title = _chapter_display_title(chapter)
    display_content = _chapter_display_content(chapter, display_title)

    assert display_title == "第2章 林逸盯着手机屏幕"
    assert display_content == "第2章 林逸盯着手机屏幕\n\n林逸盯着手机屏幕。"
