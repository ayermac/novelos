"""Creative contract CLI commands: show, approve, generate.

All output-formatting logic (JSON vs human-readable) goes through
``_cli_output``, keeping the main command functions focused on business
logic rather than format branching.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from ..common import (
    _get_settings,
    init_db,
    Repository,
)


# ── Output helpers (single source of truth for JSON / text formatting) ─


def _cli_exit(message: str, json_mode: bool = False) -> None:
    """Print an error and exit with code 1."""
    if json_mode:
        print(json.dumps({"ok": False, "error": message, "data": {}}, ensure_ascii=False))
    else:
        print(f"Error: {message}")
    sys.exit(1)


def _cli_output(
    json_mode: bool,
    text_parts: list[str],
    data: dict[str, Any] | None = None,
    *,
    indent: int = 2,
) -> None:
    """Unified output for JSON or human-readable text.

    Args:
        json_mode: If True, prints data as JSON.
        text_parts: Lines to ``print()`` when *json_mode* is False.
        data: Payload to serialize when *json_mode* is True.
        indent: Indent level for JSON pretty-print.
    """
    if json_mode:
        payload: dict[str, Any] = {"ok": True, "error": None, "data": data or {}}
        print(json.dumps(payload, ensure_ascii=False, indent=indent))
    else:
        for line in text_parts:
            print(line)


# ── Shared helpers ───────────────────────────────────────────────────────


def _get_project(repo: Repository, project_id: str, json_mode: bool) -> dict | None:
    """Return a project row or exit with an error."""
    project = repo.get_project(project_id)
    if not project:
        _cli_exit(f"项目不存在: {project_id}", json_mode)
    return project


def _json_mode(args: Any) -> bool:
    return getattr(args, "json", False)


def _serialize(obj: Any) -> dict:
    """Return a plain dict from a model, regardless of Pydantic version."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return vars(obj)


def _parse_contract_data(row: dict | None) -> tuple[dict | None, bool]:
    """Parse contract_data from a db row, returning ``(data, is_approved)``."""
    if not row:
        return None, False
    cd = row.get("contract_data", "{}")
    if isinstance(cd, str):
        data = json.loads(cd)
    else:
        data = cd
    is_approved = data.get("approved", False) if data else False
    return data, is_approved


# ── Commands ─────────────────────────────────────────────────────────────


def cmd_contract_show(args: Any) -> None:
    """Show creative contracts for a project."""
    use_json = _json_mode(args)
    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)
        project_id = getattr(args, "project_id", "")

        _get_project(repo, project_id, use_json)

        launch_data, _ = _parse_contract_data(repo.get_creative_contract(project_id, "launch_profile"))
        genre_data, is_approved = _parse_contract_data(repo.get_creative_contract(project_id, "genre_contract"))

        # Check production readiness
        from ...quality.genesis_quality_gate import check_project_ready_for_production
        is_ready = check_project_ready_for_production(project_id, repo)

        _cli_output(
            use_json,
            text_parts=[
                f"创作合同 - 项目: {project_id}",
                "=" * 50,
                *(_format_launch_profile(launch_data) if launch_data else ["\n❌ 启动配置: 未生成"]),
                *(_format_genre_contract(genre_data, is_approved) if genre_data else ["\n❌ 类型合同: 未生成"]),
                "",
                "=" * 50,
                f"生产就绪: {'✅ 是' if is_ready else '❌ 否'}",
                *(_format_readiness_gaps(launch_data, genre_data, is_approved) if not is_ready else []),
            ],
            data={
                "project_id": project_id,
                "launch_profile": launch_data,
                "genre_contract": genre_data,
                "is_approved": is_approved,
                "is_ready_for_production": is_ready,
            },
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _cli_exit(str(exc), use_json)


def _format_launch_profile(data: dict) -> list[str]:
    return [
        "\n📋 启动配置 (Launch Profile):",
        f"  目标读者: {data.get('target_reader', 'N/A')}",
        f"  市场赛道: {data.get('market_lane', 'N/A')}",
        f"  类型家族: {data.get('genre_family', 'N/A')}",
        f"  核心钩子: {data.get('core_hook', 'N/A')}",
        f"  主要回报循环: {data.get('primary_payoff_loop', 'N/A')}",
        *([f"  禁止漂移规则: {', '.join(data['hard_do_not_drift_rules'])}"] if data.get('hard_do_not_drift_rules') else []),
    ]


def _format_genre_contract(data: dict, is_approved: bool) -> list[str]:
    lines = [
        "\n📜 类型合同 (Genre Contract):",
        f"  类型ID: {data.get('genre_id', 'N/A')}",
        f"  承诺声明: {data.get('promise_statement', 'N/A')}",
        f"  审批状态: {'✅ 已审批' if is_approved else '❌ 未审批'}",
    ]
    if data.get("reader_expectations"):
        lines.append(f"  读者期望: {', '.join(data['reader_expectations'][:3])}...")
    if data.get("must_have_beats"):
        lines.append(f"  必须包含: {', '.join(data['must_have_beats'][:3])}...")
    if data.get("forbidden_drift"):
        lines.append(f"  禁止漂移: {', '.join(data['forbidden_drift'][:3])}...")
    return lines


def _format_readiness_gaps(launch_data: dict | None, genre_data: dict | None, is_approved: bool) -> list[str]:
    gaps = ["\n缺失要求:"]
    if not launch_data:
        gaps.append("  - 启动配置")
    if not genre_data:
        gaps.append("  - 类型合同")
    if not is_approved:
        gaps.append("  - 合同审批")
    return gaps


def cmd_contract_approve(args: Any) -> None:
    """Approve the genre contract for a project."""
    use_json = _json_mode(args)
    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)
        project_id = getattr(args, "project_id", "")

        _get_project(repo, project_id, use_json)

        genre_contract_row = repo.get_creative_contract(project_id, "genre_contract")
        if not genre_contract_row:
            _cli_exit("项目尚未生成类型合同，请先生成合同", use_json)

        contract_data, is_approved = _parse_contract_data(genre_contract_row)

        if is_approved:
            _cli_output(
                use_json,
                text_parts=[f"✅ 项目 {project_id} 的类型合同已审批"],
                data={"project_id": project_id, "is_approved": True, "message": "类型合同已审批"},
            )
            return

        # Approve
        contract_data["approved"] = True
        repo.upsert_creative_contract(
            project_id=project_id,
            contract_type="genre_contract",
            contract_data=contract_data,
        )

        _cli_output(
            use_json,
            text_parts=[
                f"✅ 项目 {project_id} 的类型合同审批成功",
                "项目已准备就绪，可以开始章节生产。",
            ],
            data={"project_id": project_id, "is_approved": True, "message": "类型合同审批成功"},
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _cli_exit(str(exc), use_json)


def cmd_contract_generate(args: Any) -> None:
    """Generate creative contracts for a project."""
    use_json = _json_mode(args)
    try:
        settings = _get_settings(args)
        init_db(settings.db_path)
        repo = Repository(settings.db_path)
        project_id = getattr(args, "project_id", "")
        user_idea = getattr(args, "idea", "")
        genre_profile_id = getattr(args, "profile", "generic")

        _get_project(repo, project_id, use_json)

        # Prevent overwriting
        if repo.get_creative_contract(project_id, "launch_profile") or repo.get_creative_contract(project_id, "genre_contract"):
            _cli_exit("项目已有创作合同，请先删除现有合同再重新生成", use_json)

        # Load genre profile
        from ...config.genre_profile_loader import load_genre_profile, get_default_genre_profile
        try:
            genre_profile = load_genre_profile(genre_profile_id)
        except FileNotFoundError:
            genre_profile = get_default_genre_profile()

        # LLM caller (real mode)
        llm_caller = None
        llm_mode = getattr(args, "llm_mode", "stub") or "stub"
        if llm_mode == "real":
            from ...llm.provider import get_llm_provider
            provider = get_llm_provider(settings)
            if provider:
                llm_caller = provider.complete

        from ...quality.genesis_quality_gate import generate_launch_profile, generate_genre_contract
        launch_profile = generate_launch_profile(
            user_idea=user_idea,
            genre_profile=genre_profile,
            llm_caller=llm_caller,
        )
        genre_contract = generate_genre_contract(
            launch_profile=launch_profile,
            genre_profile=genre_profile,
            llm_caller=llm_caller,
        )

        # Persist
        lp_data = _serialize(launch_profile)
        gc_data = _serialize(genre_contract)
        repo.upsert_creative_contract(project_id, "launch_profile", contract_data=lp_data)
        repo.upsert_creative_contract(project_id, "genre_contract", contract_data=gc_data)

        _cli_output(
            use_json,
            text_parts=[
                f"✅ 项目 {project_id} 创作合同生成成功",
                f"  类型配置: {genre_profile_id}",
                f"  核心钩子: {launch_profile.core_hook[:50]}...",
                f"  承诺声明: {genre_contract.promise_statement[:50]}...",
                "请使用 'novelos contract show' 查看详细内容。",
                "使用 'novelos contract approve' 审批合同后开始章节生产。",
            ],
            data={
                "project_id": project_id,
                "launch_profile": lp_data,
                "genre_contract": gc_data,
                "message": "创作合同生成成功",
            },
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _cli_exit(str(exc), use_json)