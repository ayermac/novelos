"""v4.2 Style Sample CLI commands.

Provides:
- style sample import: Import a local text file as style sample
- style sample analyze: Analyze an imported sample
- style sample list: List samples for a project
- style sample show: Show sample details
- style sample delete: Soft-delete a sample
- style sample propose: Generate proposals from samples
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

from ..output import print_error_and_exit, print_json_envelope

# File size limit: 200KB
MAX_FILE_SIZE = 200 * 1024


def cmd_style_sample_import(args) -> None:
    """Import a local text file as a style sample."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ...style_bible.sample_analyzer import analyze_style_sample_text
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")
    name = getattr(args, "name", "")
    file_path = getattr(args, "file", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return
    if not file_path:
        print_error_and_exit("--file is required", use_json)
        return

    # Validate file exists
    if not os.path.isfile(file_path):
        print_error_and_exit(f"File not found: {file_path}", use_json)
        return

    # Check file size
    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        print_error_and_exit(
            f"File too large ({file_size} bytes). Maximum: {MAX_FILE_SIZE} bytes (200KB)",
            use_json,
        )
        return

    # Read file content
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        print_error_and_exit("File is not valid UTF-8 text (binary file?)", use_json)
        return
    except Exception as e:
        print_error_and_exit(f"Failed to read file: {e}", use_json)
        return

    if not content.strip():
        print_error_and_exit("File is empty", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        # Check Style Bible exists
        bible = repo.get_style_bible(project_id)
        if not bible:
            print_error_and_exit(
                f"No Style Bible found for project '{project_id}'",
                use_json,
            )
            return

        # Compute hash and preview
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        content_preview = content[:500]

        # Auto-name if not provided
        if not name:
            name = os.path.basename(file_path)

        # Run analysis immediately on import
        analysis_result = analyze_style_sample_text(content)
        if not analysis_result.get("ok"):
            print_error_and_exit(
                analysis_result.get("error", "Analysis failed"), use_json,
            )
            return

        metrics_data = analysis_result["data"]["metrics"]
        analysis_data = analysis_result["data"]["analysis"]

        # Save sample with analysis in a single INSERT (status='analyzed')
        try:
            sample_id = repo.save_style_sample(
                project_id=project_id,
                name=name,
                source_type="local_text",
                content_hash=content_hash,
                content_preview=content_preview,
                metrics_json=json.dumps(metrics_data, ensure_ascii=False),
                analysis_json=json.dumps(analysis_data, ensure_ascii=False),
                status="analyzed",
            )
        except ValueError as e:
            # Duplicate hash
            print_error_and_exit(str(e), use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {
                    "sample_id": sample_id,
                    "name": name,
                    "content_hash": content_hash,
                    "content_preview_length": len(content_preview),
                    "status": "analyzed",
                    "metrics_summary": {
                        "char_count": metrics_data.get("char_count", 0),
                        "avg_sentence_length": metrics_data.get("avg_sentence_length", 0),
                        "dialogue_ratio": metrics_data.get("dialogue_ratio", 0),
                        "ai_trace_risk": metrics_data.get("ai_trace_risk", "unknown"),
                    },
                },
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style sample imported and analyzed: {sample_id}")
            print(f"  Name: {name}")
            print(f"  Chars: {metrics_data.get('char_count', 0)}")
            print(f"  Avg sentence length: {metrics_data.get('avg_sentence_length', 0):.1f}")
            print(f"  AI trace risk: {metrics_data.get('ai_trace_risk', 'unknown')}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_sample_analyze(args) -> None:
    """Re-analyze an existing style sample.

    Without --file: returns the currently stored analysis (read-only, no overwrite).
    With --file: re-reads the original file, verifies hash, and updates analysis.
    """
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    sample_id = getattr(args, "sample_id", "")
    file_path = getattr(args, "file", None)

    if not sample_id:
        print_error_and_exit("--sample-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        sample = repo.get_style_sample(sample_id)
        if not sample:
            print_error_and_exit(f"Sample '{sample_id}' not found", use_json)
            return

        if sample["status"] == "deleted":
            print_error_and_exit("Cannot analyze a deleted sample", use_json)
            return

        if file_path:
            # Re-analyze from original file with hash verification
            if not os.path.isfile(file_path):
                print_error_and_exit(f"File not found: {file_path}", use_json)
                return

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                print_error_and_exit("File is not valid UTF-8 text (binary file?)", use_json)
                return
            except Exception as e:
                print_error_and_exit(f"Failed to read file: {e}", use_json)
                return

            # Verify hash matches the stored sample
            file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if file_hash != sample["content_hash"]:
                print_error_and_exit(
                    "File content hash does not match the stored sample. "
                    "The file may have been modified since import.",
                    use_json,
                )
                return

            # Re-analyze from full text
            from ...style_bible.sample_analyzer import analyze_style_sample_text
            result = analyze_style_sample_text(content)
            if not result.get("ok"):
                print_error_and_exit(result.get("error", "Analysis failed"), use_json)
                return

            metrics_data = result["data"]["metrics"]
            analysis_data = result["data"]["analysis"]

            ok = repo.update_style_sample_analysis(
                sample_id,
                json.dumps(metrics_data, ensure_ascii=False),
                json.dumps(analysis_data, ensure_ascii=False),
                status="analyzed",
            )
            if not ok:
                print_error_and_exit("Failed to update sample analysis", use_json)
                return

            if use_json:
                print(json.dumps({
                    "ok": True,
                    "error": None,
                    "data": {
                        "sample_id": sample_id,
                        "metrics": metrics_data,
                        "analysis": analysis_data,
                        "status": "analyzed",
                        "source": "file_reanalysis",
                    },
                }, ensure_ascii=False, indent=2))
            else:
                print(f"Sample '{sample_id}' re-analyzed from file")
                print(f"  Chars: {metrics_data.get('char_count', 0)}")
                print(f"  Avg sentence length: {metrics_data.get('avg_sentence_length', 0):.1f}")
        else:
            # Read-only: return currently stored analysis without overwriting
            metrics_data = sample.get("metrics", {})
            analysis_data = sample.get("analysis", {})

            if use_json:
                print(json.dumps({
                    "ok": True,
                    "error": None,
                    "data": {
                        "sample_id": sample_id,
                        "metrics": metrics_data,
                        "analysis": analysis_data,
                        "status": sample["status"],
                        "source": "stored",
                    },
                }, ensure_ascii=False, indent=2))
            else:
                print(f"Sample '{sample_id}' current analysis:")
                print(f"  Status: {sample['status']}")
                print(f"  Chars: {metrics_data.get('char_count', 0)}")
                print(f"  Avg sentence length: {metrics_data.get('avg_sentence_length', 0):.1f}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_sample_list(args) -> None:
    """List style samples for a project."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        samples = repo.list_style_samples(project_id)

        # Strip full metrics/analysis from list view
        summaries = []
        for s in samples:
            summaries.append({
                "id": s["id"],
                "name": s["name"],
                "source_type": s["source_type"],
                "status": s["status"],
                "created_at": s["created_at"],
                "analyzed_at": s.get("analyzed_at", ""),
                "char_count": s.get("metrics", {}).get("char_count", 0),
            })

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {"samples": summaries, "total": len(summaries)},
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Samples for '{project_id}' ({len(summaries)}):")
            for s in summaries:
                status = s["status"]
                chars = s["char_count"]
                print(f"  [{status}] {s['name']} ({chars} chars)")
                print(f"    ID: {s['id']}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_sample_show(args) -> None:
    """Show details of a style sample (no full text, only preview)."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    sample_id = getattr(args, "sample_id", "")

    if not sample_id:
        print_error_and_exit("--sample-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        sample = repo.get_style_sample(sample_id)
        if not sample:
            print_error_and_exit(f"Sample '{sample_id}' not found", use_json)
            return

        # Build output without full text
        output = {
            "id": sample["id"],
            "project_id": sample["project_id"],
            "name": sample["name"],
            "source_type": sample["source_type"],
            "content_hash": sample["content_hash"],
            "content_preview": sample.get("content_preview", ""),
            "metrics": sample.get("metrics", {}),
            "analysis": sample.get("analysis", {}),
            "status": sample["status"],
            "created_at": sample["created_at"],
            "analyzed_at": sample.get("analyzed_at", ""),
        }

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": output,
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Style Sample: {sample['name']}")
            print(f"  ID: {sample['id']}")
            print(f"  Status: {sample['status']}")
            print(f"  Source: {sample['source_type']}")
            print(f"  Content Hash: {sample['content_hash'][:16]}...")
            if sample.get("content_preview"):
                preview = sample["content_preview"][:200]
                print(f"  Preview: {preview}...")
            metrics = sample.get("metrics", {})
            if metrics:
                print(f"  Avg Sentence Length: {metrics.get('avg_sentence_length', 0)}")
                print(f"  Dialogue Ratio: {metrics.get('dialogue_ratio', 0)}")
                print(f"  AI Trace Risk: {metrics.get('ai_trace_risk', 'unknown')}")
            analysis = sample.get("analysis", {})
            if analysis.get("tone_keywords"):
                print(f"  Tone: {', '.join(analysis['tone_keywords'])}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_sample_delete(args) -> None:
    """Soft-delete a style sample."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    sample_id = getattr(args, "sample_id", "")

    if not sample_id:
        print_error_and_exit("--sample-id is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        # Check exists
        sample = repo.get_style_sample(sample_id)
        if not sample:
            print_error_and_exit(f"Sample '{sample_id}' not found", use_json)
            return

        if sample["status"] == "deleted":
            print_error_and_exit("Sample is already deleted", use_json)
            return

        ok = repo.delete_style_sample(sample_id)
        if not ok:
            print_error_and_exit("Failed to delete sample", use_json)
            return

        if use_json:
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": {"sample_id": sample_id, "status": "deleted"},
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Sample '{sample_id}' deleted")
    except Exception as e:
        print_error_and_exit(str(e), use_json)


def cmd_style_sample_propose(args) -> None:
    """Generate style evolution proposals from analyzed samples."""
    from ...db.repository import Repository
    from ...db.connection import init_db
    from ...style_bible.sample_proposal import propose_style_from_samples
    from ..common import _get_settings

    use_json = getattr(args, "json", False)
    project_id = getattr(args, "project_id", "")

    # Support --sample-id (single) or --sample-ids (comma-separated)
    sample_id = getattr(args, "sample_id", None)
    sample_ids_str = getattr(args, "sample_ids", None)

    if not project_id:
        print_error_and_exit("--project-id is required", use_json)
        return

    # Build sample_ids list
    ids: list[str] = []
    if sample_ids_str:
        ids = [s.strip() for s in sample_ids_str.split(",") if s.strip()]
    elif sample_id:
        ids = [sample_id]

    if not ids:
        print_error_and_exit("--sample-id or --sample-ids is required", use_json)
        return

    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)

        result = propose_style_from_samples(project_id, ids, repo)

        if not result.get("ok"):
            print_error_and_exit(
                result.get("error", "Unknown error"), use_json,
                data=result.get("data", {}),
            )
            return

        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            data = result.get("data", {})
            print(f"Style Sample Proposals for '{project_id}':")
            print(f"  Created: {data.get('proposals_created', 0)}")
            for pid in data.get("proposal_ids", []):
                print(f"    - {pid}")
    except Exception as e:
        print_error_and_exit(str(e), use_json)
