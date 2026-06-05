"""Creative contract CLI commands: show, approve."""

from __future__ import annotations

import json
import sys

from ..common import (
    _get_settings,
    init_db,
    Repository,
)


def cmd_contract_show(args) -> None:
    """Show creative contracts for a project."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    project_id = getattr(args, "project_id", "")

    try:
        repo = Repository(settings.db_path)

        # Check if project exists
        project = repo.get_project(project_id)
        if not project:
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({"ok": False, "error": f"项目不存在: {project_id}", "data": {}}, ensure_ascii=False))
            else:
                print(f"Error: 项目不存在: {project_id}")
            sys.exit(1)

        # Get launch profile and genre contract (parse contract_data JSON)
        import json as _json
        launch_profile_row = repo.get_creative_contract(project_id, "launch_profile")
        genre_contract_row = repo.get_creative_contract(project_id, "genre_contract")

        launch_profile = None
        if launch_profile_row:
            cd = launch_profile_row.get("contract_data", "{}")
            launch_profile = _json.loads(cd) if isinstance(cd, str) else cd

        genre_contract = None
        is_approved = False
        if genre_contract_row:
            cd = genre_contract_row.get("contract_data", "{}")
            genre_contract = _json.loads(cd) if isinstance(cd, str) else cd
            is_approved = genre_contract.get("approved", False) if genre_contract else False

        # Check production readiness
        from ...quality.genesis_quality_gate import check_project_ready_for_production
        is_ready = check_project_ready_for_production(project_id, repo)

        use_json = getattr(args, "json", False)
        if use_json:
            result = {
                "ok": True,
                "error": None,
                "data": {
                    "project_id": project_id,
                    "launch_profile": launch_profile,
                    "genre_contract": genre_contract,
                    "is_approved": is_approved,
                    "is_ready_for_production": is_ready,
                },
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"创作合同 - 项目: {project_id}")
            print("=" * 50)

            if launch_profile:
                print("\n📋 启动配置 (Launch Profile):")
                print(f"  目标读者: {launch_profile.get('target_reader', 'N/A')}")
                print(f"  市场赛道: {launch_profile.get('market_lane', 'N/A')}")
                print(f"  类型家族: {launch_profile.get('genre_family', 'N/A')}")
                print(f"  核心钩子: {launch_profile.get('core_hook', 'N/A')}")
                print(f"  主要回报循环: {launch_profile.get('primary_payoff_loop', 'N/A')}")
                if launch_profile.get('hard_do_not_drift_rules'):
                    print(f"  禁止漂移规则: {', '.join(launch_profile['hard_do_not_drift_rules'])}")
            else:
                print("\n❌ 启动配置: 未生成")

            if genre_contract:
                print("\n📜 类型合同 (Genre Contract):")
                print(f"  类型ID: {genre_contract.get('genre_id', 'N/A')}")
                print(f"  承诺声明: {genre_contract.get('promise_statement', 'N/A')}")
                print(f"  审批状态: {'✅ 已审批' if is_approved else '❌ 未审批'}")
                if genre_contract.get('reader_expectations'):
                    print(f"  读者期望: {', '.join(genre_contract['reader_expectations'][:3])}...")
                if genre_contract.get('must_have_beats'):
                    print(f"  必须包含: {', '.join(genre_contract['must_have_beats'][:3])}...")
                if genre_contract.get('forbidden_drift'):
                    print(f"  禁止漂移: {', '.join(genre_contract['forbidden_drift'][:3])}...")
            else:
                print("\n❌ 类型合同: 未生成")

            print("\n" + "=" * 50)
            print(f"生产就绪: {'✅ 是' if is_ready else '❌ 否'}")

            if not is_ready:
                print("\n缺失要求:")
                if not launch_profile:
                    print("  - 启动配置")
                if not genre_contract:
                    print("  - 类型合同")
                if not is_approved:
                    print("  - 合同审批")

    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)


def cmd_contract_approve(args) -> None:
    """Approve the genre contract for a project."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    project_id = getattr(args, "project_id", "")

    try:
        repo = Repository(settings.db_path)

        # Check if project exists
        project = repo.get_project(project_id)
        if not project:
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({"ok": False, "error": f"项目不存在: {project_id}", "data": {}}, ensure_ascii=False))
            else:
                print(f"Error: 项目不存在: {project_id}")
            sys.exit(1)

        # Check if genre contract exists
        genre_contract_row = repo.get_creative_contract(project_id, "genre_contract")
        if not genre_contract_row:
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({"ok": False, "error": "项目尚未生成类型合同，请先生成合同", "data": {}}, ensure_ascii=False))
            else:
                print("Error: 项目尚未生成类型合同，请先生成合同")
            sys.exit(1)

        # Parse contract_data JSON
        cd = genre_contract_row.get("contract_data", "{}")
        genre_contract = json.loads(cd) if isinstance(cd, str) else cd

        # Check if already approved
        if genre_contract.get("approved", False):
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({"ok": True, "error": None, "data": {"project_id": project_id, "is_approved": True, "message": "类型合同已审批"}}, ensure_ascii=False))
            else:
                print(f"✅ 项目 {project_id} 的类型合同已审批")
            return

        # Approve the contract
        genre_contract["approved"] = True
        repo.upsert_creative_contract(
            project_id=project_id,
            contract_type="genre_contract",
            data=genre_contract,
        )

        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"project_id": project_id, "is_approved": True, "message": "类型合同审批成功"}}, ensure_ascii=False))
        else:
            print(f"✅ 项目 {project_id} 的类型合同审批成功")
            print("项目已准备就绪，可以开始章节生产。")

    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)


def cmd_contract_generate(args) -> None:
    """Generate creative contracts for a project."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    project_id = getattr(args, "project_id", "")
    user_idea = getattr(args, "idea", "")
    genre_profile_id = getattr(args, "profile", "generic")

    try:
        repo = Repository(settings.db_path)

        # Check if project exists
        project = repo.get_project(project_id)
        if not project:
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({"ok": False, "error": f"项目不存在: {project_id}", "data": {}}, ensure_ascii=False))
            else:
                print(f"Error: 项目不存在: {project_id}")
            sys.exit(1)

        # Check if contracts already exist
        existing_launch = repo.get_creative_contract(project_id, "launch_profile")
        existing_contract = repo.get_creative_contract(project_id, "genre_contract")
        if existing_launch or existing_contract:
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({"ok": False, "error": "项目已有创作合同，请先删除现有合同再重新生成", "data": {}}, ensure_ascii=False))
            else:
                print("Error: 项目已有创作合同，请先删除现有合同再重新生成")
            sys.exit(1)

        # Load genre profile
        from ...config.genre_profile_loader import load_genre_profile, get_default_genre_profile
        try:
            genre_profile = load_genre_profile(genre_profile_id)
        except FileNotFoundError:
            genre_profile = get_default_genre_profile()

        # Get LLM mode
        from ...llm.provider import get_llm_provider
        llm_mode = getattr(args, "llm_mode", "stub") or "stub"

        llm_caller = None
        if llm_mode == "real":
            llm_provider = get_llm_provider(settings)
            if llm_provider:
                llm_caller = llm_provider.complete

        # Generate launch profile
        from ...quality.genesis_quality_gate import generate_launch_profile, generate_genre_contract
        launch_profile = generate_launch_profile(
            user_idea=user_idea,
            genre_profile=genre_profile,
            llm_caller=llm_caller,
        )

        # Generate genre contract
        genre_contract = generate_genre_contract(
            launch_profile=launch_profile,
            genre_profile=genre_profile,
            llm_caller=llm_caller,
        )

        # Save to database
        repo.upsert_creative_contract(
            project_id=project_id,
            contract_type="launch_profile",
            data=launch_profile.model_dump() if hasattr(launch_profile, "model_dump") else vars(launch_profile),
        )
        repo.upsert_creative_contract(
            project_id=project_id,
            contract_type="genre_contract",
            data=genre_contract.model_dump() if hasattr(genre_contract, "model_dump") else vars(genre_contract),
        )

        use_json = getattr(args, "json", False)
        if use_json:
            result = {
                "ok": True,
                "error": None,
                "data": {
                    "project_id": project_id,
                    "launch_profile": launch_profile.model_dump() if hasattr(launch_profile, "model_dump") else vars(launch_profile),
                    "genre_contract": genre_contract.model_dump() if hasattr(genre_contract, "model_dump") else vars(genre_contract),
                    "message": "创作合同生成成功",
                },
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 项目 {project_id} 创作合同生成成功")
            print(f"  类型配置: {genre_profile_id}")
            print(f"  核心钩子: {launch_profile.core_hook[:50]}...")
            print(f"  承诺声明: {genre_contract.promise_statement[:50]}...")
            print("\n请使用 'novelos contract show' 查看详细内容。")
            print("使用 'novelos contract approve' 审批合同后开始章节生产。")

    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
