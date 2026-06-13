"""Shared safety gates for MemoryCurator API entry points.

v6.6.7: Enhanced trusted/untrusted/fallback classification with
three-category result taxonomy:
  - trusted_extraction: real LLM succeeded, patches validated
  - fallback_candidate: extraction failed, state-card fallback only
  - failed_no_memory: no patches and no fallback available
"""

from __future__ import annotations

from typing import Any

_TRUSTED_MEMORY_MIN_CONFIDENCE = 0.75


# ── Classification ───────────────────────────────────────────────


def _is_trusted_memory_item(item: dict[str, Any]) -> bool:
    """Return True if a single memory item qualifies as trusted.

    Strictly aligned with context_builder._is_trusted_memory_item so
    API/UI classification never diverges from what the Planner inherits.
    """
    confidence = float(item.get("confidence") or 0)
    if confidence < _TRUSTED_MEMORY_MIN_CONFIDENCE:
        return False
    evidence = str(item.get("evidence_text") or "").strip()
    if not evidence:
        return False
    rationale = str(item.get("rationale") or "").lower()
    if "状态卡兜底" in rationale or "fallback" in rationale or "degraded" in rationale:
        return False
    if "no-op" in rationale or " degraded " in rationale:
        return False
    return True


def is_trusted_memory_batch(repo: Any, batch: dict) -> bool:
    """Return True only when every item in the batch is trusted.

    v6.6.7-fix: Requires confidence >= 0.75 and non-empty evidence_text
    per item, matching the Planner's trusted memory rules.
    """
    if str(batch.get("status") or "") == "ignored":
        return False
    summary = str(batch.get("summary") or "")
    if "状态卡兜底" in summary:
        return False
    if "fallback" in summary.lower():
        return False
    if "degraded" in summary.lower():
        return False
    try:
        items = repo.list_memory_items(batch["id"])
    except Exception:
        items = []
    if not items:
        return False
    for item in items:
        if not _is_trusted_memory_item(item):
            return False
    return True


def is_state_card_fallback_batch(repo: Any, batch: dict) -> bool:
    """Return True when a batch is a low-confidence state-card fallback."""
    summary = str(batch.get("summary") or "")
    if "状态卡兜底" in summary:
        return True
    if "fallback" in summary.lower():
        return True
    try:
        items = repo.list_memory_items(batch["id"])
    except Exception:
        items = []
    for item in items:
        rationale = str(item.get("rationale") or "")
        confidence = float(item.get("confidence") or 0)
        if "状态卡兜底候选" in rationale or "fallback" in rationale.lower():
            return True
        if confidence <= 0.45 and "MemoryCurator LLM 复核" in rationale:
            return True
    return False


def classify_memory_batch(repo: Any, batch: dict) -> str:
    """Classify a batch into trusted / fallback / empty.

    Returns one of: "trusted", "fallback", "empty", "ignored".
    """
    if str(batch.get("status") or "") == "ignored":
        return "ignored"
    try:
        items = repo.list_memory_items(batch["id"])
    except Exception:
        items = []
    if not items:
        return "empty"
    if is_state_card_fallback_batch(repo, batch):
        return "fallback"
    if is_trusted_memory_batch(repo, batch):
        return "trusted"
    # Has items but neither trusted nor fallback → mixed/unclassified
    return "fallback"


def get_memory_status_for_chapter(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Return canonical memory status for a chapter.

    Returns dict with:
    - memory_status: trusted / fallback / failed / missing
    - memory_trusted: bool
    - latest_memory_batch_id: str | None
    - batch_count: int
    - trusted_batch_count: int
    - fallback_batch_count: int

    If run_id is provided, prefer batches created by that workflow run. Legacy
    batches without run_id are considered only when the chapter has no run-bound
    batches at all, so old timeline records are not made green by a later
    backfill run.
    """
    try:
        batches = repo.list_memory_batches(project_id)
    except Exception:
        return {
            "memory_status": "missing",
            "memory_trusted": False,
            "latest_memory_batch_id": None,
            "batch_count": 0,
            "trusted_batch_count": 0,
            "fallback_batch_count": 0,
        }

    chapter_batches_all = [
        b for b in batches
        if int(b.get("chapter_number") or 0) == int(chapter_number)
        and str(b.get("status") or "") != "ignored"
    ]
    chapter_batches = chapter_batches_all
    if run_id:
        run_batches = [
            b for b in chapter_batches_all
            if str(b.get("run_id") or "") == str(run_id)
        ]
        has_run_bound_batches = any(str(b.get("run_id") or "") for b in chapter_batches_all)
        if run_batches:
            chapter_batches = run_batches
        elif has_run_bound_batches:
            chapter_batches = []
        else:
            chapter_batches = [
                b for b in chapter_batches_all
                if not str(b.get("run_id") or "")
            ]

    trusted_count = 0
    fallback_count = 0
    latest_batch = None
    latest_time = ""

    for batch in chapter_batches:
        cls = classify_memory_batch(repo, batch)
        if cls == "trusted":
            trusted_count += 1
        elif cls == "fallback":
            fallback_count += 1
        created = str(batch.get("created_at") or "")
        if created > latest_time:
            latest_time = created
            latest_batch = batch

    if trusted_count > 0:
        status = "trusted"
        trusted = True
    elif fallback_count > 0:
        status = "fallback"
        trusted = False
    elif chapter_batches:
        status = "failed"
        trusted = False
    else:
        status = "missing"
        trusted = False

    return {
        "memory_status": status,
        "memory_trusted": trusted,
        "latest_memory_batch_id": latest_batch["id"] if latest_batch else None,
        "batch_count": len(chapter_batches),
        "trusted_batch_count": trusted_count,
        "fallback_batch_count": fallback_count,
    }


def ignore_duplicate_state_card_fallback_batches(
    repo: Any,
    project_id: str,
    chapter_number: int | None = None,
    *,
    keep_latest: bool = True,
) -> int:
    """Mark duplicate state-card fallback batches ignored.

    Repeated failed extraction attempts used to create one pending fallback
    batch per retry, which made the memory inbox look like real work. Keep at
    most one newest fallback per chapter so retrying stays visible but does not
    pollute the queue.
    """
    try:
        batches = repo.list_memory_batches(project_id)
    except Exception:
        return 0

    grouped: dict[int, list[dict]] = {}
    for batch in batches:
        if str(batch.get("status") or "") == "ignored":
            continue
        batch_chapter = int(batch.get("chapter_number") or 0)
        if chapter_number is not None and batch_chapter != int(chapter_number):
            continue
        if is_state_card_fallback_batch(repo, batch):
            grouped.setdefault(batch_chapter, []).append(batch)

    ignored = 0
    for fallback_batches in grouped.values():
        fallback_batches.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        to_ignore = fallback_batches[1:] if keep_latest else fallback_batches
        for batch in to_ignore:
            try:
                repo.update_memory_batch(batch["id"], {"status": "ignored"})
                ignored += 1
            except Exception:
                continue
    return ignored


def ignore_state_card_fallback_batches_for_chapter(
    repo: Any,
    project_id: str,
    chapter_number: int,
) -> int:
    """Ignore all fallback batches for a chapter after trusted extraction succeeds."""
    try:
        batches = repo.list_memory_batches(project_id)
    except Exception:
        return 0

    ignored = 0
    for batch in batches:
        if int(batch.get("chapter_number") or 0) != int(chapter_number):
            continue
        if str(batch.get("status") or "") == "ignored":
            continue
        if not is_state_card_fallback_batch(repo, batch):
            continue
        try:
            repo.update_memory_batch(batch["id"], {"status": "ignored"})
            ignored += 1
        except Exception:
            continue
    return ignored


def has_trusted_memory_batch(repo: Any, project_id: str, chapter_number: int) -> bool:
    """Return True when a chapter has a trusted memory inbox batch."""
    try:
        for batch in repo.list_memory_batches(project_id):
            if (
                int(batch.get("chapter_number") or 0) == int(chapter_number)
                and is_trusted_memory_batch(repo, batch)
            ):
                return True
    except Exception:
        pass
    return False


def _run_has_memory_batch_result(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str,
) -> bool:
    """Return True when the run already created visible memory candidates."""
    if not run_id:
        return False
    try:
        batches = repo.list_memory_batches(project_id)
    except Exception:
        return False
    for batch in batches:
        if int(batch.get("chapter_number") or 0) != int(chapter_number):
            continue
        if str(batch.get("status") or "") == "ignored":
            continue
        if str(batch.get("run_id") or "") != str(run_id):
            continue
        try:
            items = repo.list_memory_items(batch["id"])
        except Exception:
            items = []
        if items:
            return True
    return False


def _has_memory_curator_recovery_evidence(repo: Any, run: dict, run_id: str) -> bool:
    """Return True when a MemoryCurator run is an old failure/recovery target.

    Trusted chapter memory should clear stale recovery prompts, but it must not
    auto-complete a fresh MemoryCurator run that is still actively extracting.
    """
    status = str(run.get("status") or "")
    if status in {"blocked", "failed"}:
        return True

    error_message = str(run.get("error_message") or "").lower()
    if "memory_curator" in error_message or "记忆" in error_message:
        if "timeout" in error_message or "超时" in error_message or "failed" in error_message or "失败" in error_message:
            return True

    try:
        events = repo.get_workflow_node_events(run_id)
    except Exception:
        events = []
    for event in events:
        if str(event.get("node_name") or "") != "memory_curator":
            continue
        event_type = str(event.get("event_type") or "")
        event_status = str(event.get("status") or "")
        message = str(event.get("message") or "").lower()
        if event_type == "failed" or event_status in {"failed", "error", "blocked"}:
            return True
        if "timeout" in message or "超时" in message:
            return True

    try:
        conn = repo._conn()
        try:
            rows = conn.execute(
                "SELECT status, error_message FROM task_status "
                "WHERE workflow_run_id=? AND agent_id='memory_curator'",
                (run_id,),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []
    for row in rows:
        task_status = str(row["status"] if hasattr(row, "keys") else row[0])
        task_error = str((row["error_message"] if hasattr(row, "keys") else row[1]) or "").lower()
        if task_status in {"failed", "blocked"}:
            return True
        if "timeout" in task_error or "超时" in task_error or "failed" in task_error or "失败" in task_error:
            return True

    return False


def _complete_memory_curator_run(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str,
    resolved_node: str,
    message: str,
) -> bool:
    try:
        updated = repo.update_workflow_run(
            run_id,
            status="completed",
            current_node=resolved_node,
            clear_error=True,
        )
    except Exception:
        updated = False
    if not updated:
        return False

    if hasattr(repo, "release_memory_curator_lock"):
        try:
            repo.release_memory_curator_lock(project_id, chapter_number, run_id=run_id)
        except Exception:
            pass
    try:
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE task_status SET status='completed', "
                "completed_at=COALESCE(completed_at, datetime('now','+8 hours')), "
                "error_message=NULL "
                "WHERE workflow_run_id=? AND agent_id='memory_curator' "
                "AND status IN ('running', 'failed', 'blocked')",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
    if hasattr(repo, "create_workflow_node_event"):
        try:
            repo.create_workflow_node_event(
                run_id=run_id,
                project_id=project_id,
                chapter_number=chapter_number,
                node_name="memory_curator",
                event_type="completed",
                status="completed",
                message=message,
            )
        except Exception:
            pass
    return True


def complete_memory_curator_run_if_batch_exists(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
) -> int:
    """Close a zombie MemoryCurator run after it already created a batch.

    This covers the failure window where the MemoryCurator writes a memory
    batch/items successfully, but the outer workflow process is interrupted
    before it can write the final node/run completion event.
    """
    try:
        chapter = repo.get_chapter(project_id, chapter_number)
    except Exception:
        chapter = None
    chapter_status = str((chapter or {}).get("status") or "")
    if chapter_status not in {"reviewed", "awaiting_publish", "published"}:
        return 0

    try:
        runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=50)
    except Exception:
        runs = []
    if run_id:
        runs = [run for run in runs if str(run.get("id") or run.get("run_id") or "") == str(run_id)]

    resolved_node = "publish" if chapter_status == "published" else "awaiting_publish"
    completed = 0
    for run in runs:
        if str(run.get("status") or "") not in {"running", "blocked", "failed"}:
            continue
        current_run_id = str(run.get("id") or run.get("run_id") or "")
        if not current_run_id:
            continue
        if str(run.get("current_node") or "") != "memory_curator":
            continue
        if not _run_has_memory_batch_result(repo, project_id, chapter_number, current_run_id):
            continue
        if _complete_memory_curator_run(
            repo,
            project_id,
            chapter_number,
            current_run_id,
            resolved_node,
            "检测到该运行已生成记忆批次，记忆整理运行状态已自动收尾",
        ):
            completed += 1
    return completed


def complete_memory_curator_recovery_if_trusted(
    repo: Any,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
) -> int:
    """Close stale MemoryCurator recovery runs once trusted memory exists.

    A timed-out MemoryCurator run can remain blocked after a later manual
    backfill succeeds. Chapter-level trusted memory is then the source of truth:
    the old run should no longer surface a backfill CTA or block publishing.
    """
    try:
        chapter = repo.get_chapter(project_id, chapter_number)
    except Exception:
        chapter = None
    chapter_status = str((chapter or {}).get("status") or "")
    if chapter_status not in {"reviewed", "awaiting_publish", "published"}:
        return 0
    if not has_trusted_memory_batch(repo, project_id, chapter_number):
        return 0

    try:
        runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=50)
    except Exception:
        runs = []
    if run_id:
        runs = [run for run in runs if str(run.get("id") or run.get("run_id") or "") == str(run_id)]

    try:
        from ...workflow.node_recovery import resolve_failed_node_from_events
    except Exception:
        resolve_failed_node_from_events = None  # type: ignore[assignment]

    resolved_node = "publish" if chapter_status == "published" else "awaiting_publish"
    completed = 0
    for run in runs:
        if str(run.get("status") or "") not in {"blocked", "failed", "running"}:
            continue
        current_run_id = str(run.get("id") or run.get("run_id") or "")
        if not current_run_id:
            continue
        recoverable_node = str(run.get("current_node") or "")
        if resolve_failed_node_from_events is not None:
            try:
                recoverable_node = resolve_failed_node_from_events(
                    repo.get_workflow_node_events(current_run_id),
                    run.get("current_node"),
                ) or recoverable_node
            except Exception:
                pass
        if recoverable_node != "memory_curator":
            continue
        if not _has_memory_curator_recovery_evidence(repo, run, current_run_id):
            continue

        if _complete_memory_curator_run(
            repo,
            project_id,
            chapter_number,
            current_run_id,
            resolved_node,
            "检测到可信记忆批次，旧记忆整理阻塞已自动恢复",
        ):
            completed += 1
    return completed


def memory_result_is_incomplete(repo: Any, project_id: str, chapter_number: int, result: dict) -> bool:
    """Return True when a MemoryCurator run did not produce trusted memory."""
    if result.get("memory_curator_locked"):
        return False
    if result.get("error"):
        return True
    if (
        result.get("memory_curator_degraded")
        or result.get("fallback_created")
        or result.get("memory_curator_fallback")
        or result.get("extraction_success") is False
    ):
        return True
    if not result.get("memory_batch_id") or int(result.get("memory_items_count") or 0) <= 0:
        return True
    return not has_trusted_memory_batch(repo, project_id, chapter_number)


def memory_incomplete_message(result: dict) -> str:
    """Build a user-facing reason for incomplete memory extraction."""
    warning = result.get("memory_curator_warning")
    if warning:
        return str(warning)
    if result.get("fallback_created") or result.get("memory_curator_fallback"):
        return "记忆提取未成功：仅生成状态卡兜底候选，不能作为后续章节的可信记忆。"
    if result.get("memory_curator_degraded"):
        return "记忆提取未成功：MemoryCurator 已降级，未生成可信记忆批次。"
    if result.get("extraction_success") is False:
        return "记忆提取未成功：LLM 未生成可应用的可信记忆。"
    return "记忆提取未成功：没有生成可信记忆批次。"


def memory_incomplete_details(
    result: dict,
    *,
    project_id: str,
    chapter_number: int,
    run_id: str | None = None,
) -> dict:
    """Return structured debug details for incomplete memory extraction."""
    return {
        "project_id": project_id,
        "chapter": chapter_number,
        "run_id": run_id or result.get("run_id") or result.get("memory_run_id"),
        "memory_batch_id": result.get("memory_batch_id"),
        "memory_items_count": result.get("memory_items_count", 0),
        "extraction_success": result.get("extraction_success"),
        "fallback_created": result.get("fallback_created", False),
        "memory_curator_degraded": result.get("memory_curator_degraded", False),
        "memory_curator_fallback": result.get("memory_curator_fallback"),
        "memory_curator_warning": result.get("memory_curator_warning"),
    }
