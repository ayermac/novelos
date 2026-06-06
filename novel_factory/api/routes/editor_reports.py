"""Editor lens reports API endpoints.

v6.9.0: Provides access to specialized editor lens reports for chapters.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/chapters/{chapter_number}/editor-reports")
async def get_editor_reports(
    request: Request,
    project_id: str,
    chapter_number: int,
) -> EnvelopeResponse:
    """Get editor lens reports for a chapter.

    Returns all lens reports (type, continuity, commercial, pacing, character, mystery, style)
    and the aggregated chief editor result.

    Args:
        project_id: Project identifier
        chapter_number: Chapter number
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Get all editor lens reports for this chapter
        reports = repo.get_editor_lens_reports(project_id, chapter_number)

        # Get the aggregated result from the latest workflow run
        aggregated = None
        for report in reports:
            report_data = report.get("report_data", {})
            if isinstance(report_data, str):
                import json
                report_data = json.loads(report_data)

            # Build aggregated from individual reports if not already set
            if aggregated is None:
                aggregated = {
                    "project_id": project_id,
                    "chapter_number": chapter_number,
                    "lens_reports": [],
                }

            aggregated["lens_reports"].append({
                "lens_type": report.get("lens_type"),
                "passed": report_data.get("passed", False),
                "score": report_data.get("score", 0.0),
                "findings": report_data.get("findings", []),
                "summary": report_data.get("summary", ""),
                "created_at": report.get("created_at"),
            })

        # If we have reports, compute the chief editor summary
        if aggregated and aggregated.get("lens_reports"):
            from ...agents.editor_lenses.chief_editor import ChiefEditor

            # Convert to EditorLensReport objects
            from ...models.chapter_contracts import EditorLensReport
            lens_reports = []
            for lr in aggregated["lens_reports"]:
                findings = []
                for f in lr.get("findings", []):
                    from ...models.chapter_contracts import EditorLensFinding
                    findings.append(EditorLensFinding(
                        severity=f.get("severity", "info"),
                        code=f.get("code", ""),
                        message=f.get("message", ""),
                        suggestion=f.get("suggestion", ""),
                    ))
                lens_reports.append(EditorLensReport(
                    lens_type=lr["lens_type"],
                    passed=lr["passed"],
                    score=lr["score"],
                    findings=findings,
                    summary=lr.get("summary", ""),
                ))

            # Aggregate
            chief = ChiefEditor()
            result = chief.aggregate(lens_reports)
            aggregated["aggregated"] = result
            aggregated["total_reports"] = len(reports)

        return envelope_response(aggregated or {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "lens_reports": [],
            "aggregated": None,
            "total_reports": 0,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取编辑审核报告失败: {str(e)}")


@router.get("/projects/{project_id}/editor-reports/summary")
async def get_editor_reports_summary(
    request: Request,
    project_id: str,
    limit: int = 20,
) -> EnvelopeResponse:
    """Get summary of editor lens reports for a project.

    Returns aggregated scores for recent chapters.

    Args:
        project_id: Project identifier
        limit: Number of recent chapters to include (default 20)
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Get chapters for this project
        chapters = repo.list_chapters(project_id)

        # Get editor lens reports for recent chapters
        summaries = []
        for ch in chapters[-limit:]:
            chapter_number = ch.get("chapter_number", 0)
            reports = repo.get_editor_lens_reports(project_id, chapter_number)

            if not reports:
                continue

            # Compute aggregated score for this chapter
            from ...agents.editor_lenses.chief_editor import ChiefEditor
            from ...models.chapter_contracts import EditorLensReport, EditorLensFinding

            lens_reports = []
            for report in reports:
                report_data = report.get("report_data", {})
                if isinstance(report_data, str):
                    import json
                    report_data = json.loads(report_data)

                findings = []
                for f in report_data.get("findings", []):
                    findings.append(EditorLensFinding(
                        severity=f.get("severity", "info"),
                        code=f.get("code", ""),
                        message=f.get("message", ""),
                        suggestion=f.get("suggestion", ""),
                    ))

                lens_reports.append(EditorLensReport(
                    lens_type=report.get("lens_type", "unknown"),
                    passed=report_data.get("passed", False),
                    score=report_data.get("score", 0.0),
                    findings=findings,
                    summary=report_data.get("summary", ""),
                ))

            if lens_reports:
                chief = ChiefEditor()
                result = chief.aggregate(lens_reports)
                summaries.append({
                    "chapter_number": chapter_number,
                    "status": ch.get("status", ""),
                    "passed": result["passed"],
                    "score": result["score"],
                    "blocking_count": result["blocking_count"],
                    "warning_count": result["warning_count"],
                    "lens_count": len(lens_reports),
                })

        return envelope_response({
            "project_id": project_id,
            "chapters": summaries,
            "total_chapters": len(summaries),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取编辑审核摘要失败: {str(e)}")
