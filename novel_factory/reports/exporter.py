"""Report exporter utilities for Secretary agent.

Provides additional export formats and utilities for generating
reports and exports from the novel factory data.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def export_chapter_markdown(
    chapter_data: dict[str, Any],
    output_path: Path | None = None,
) -> str:
    """Export chapter to Markdown format.

    Args:
        chapter_data: Chapter export data.
        output_path: Optional path to write the file.

    Returns:
        Markdown string.
    """
    lines = [
        f"# {chapter_data.get('title', 'Untitled')}",
        "",
        f"**章节**: 第 {chapter_data.get('chapter_number', 0)} 章",
        f"**字数**: {chapter_data.get('word_count', 0)}",
        f"**导出时间**: {chapter_data.get('exported_at', datetime.now().isoformat())}",
        "",
        "---",
        "",
        chapter_data.get('content', ''),
    ]
    
    markdown = "\n".join(lines)
    
    if output_path:
        output_path.write_text(markdown, encoding="utf-8")
    
    return markdown


def export_report_json(
    report_data: dict[str, Any],
    output_path: Path | None = None,
) -> str:
    """Export report to JSON format.

    Args:
        report_data: Report data.
        output_path: Optional path to write the file.

    Returns:
        JSON string.
    """
    json_str = json.dumps(report_data, ensure_ascii=False, indent=2)
    
    if output_path:
        output_path.write_text(json_str, encoding="utf-8")
    
    return json_str


def format_daily_report_summary(report_data: dict[str, Any]) -> str:
    """Format daily report as human-readable summary.

    Args:
        report_data: Daily report data.

    Returns:
        Formatted summary string.
    """
    lines = [
        f"日报 - {report_data.get('date', 'N/A')}",
        f"项目: {report_data.get('project_id', 'N/A')}",
        "",
        f"总运行数: {report_data.get('total_runs', 0)}",
        f"成功: {report_data.get('successful_runs', 0)}",
        f"失败: {report_data.get('failed_runs', 0)}",
        "",
        "章节状态分布:",
    ]
    
    status_dist = report_data.get("chapter_status_distribution", {})
    for status, count in sorted(status_dist.items()):
        lines.append(f"  - {status}: {count}")
    
    recent_errors = report_data.get("recent_errors", [])
    if recent_errors:
        lines.extend([
            "",
            "最近错误:",
        ])
        for error in recent_errors[:5]:
            lines.append(f"  - {error[:100]}")
    
    return "\n".join(lines)
