"""v6.9.0: Genesis Contract generation and approval tests.

Covers:
- generate_launch_profile (stub mode)
- generate_genre_contract (stub mode)
- check_project_ready_for_production
- GenreProfile and GenreContract models
- ProjectLaunchProfile model
"""

from __future__ import annotations

import json
import pytest

from novel_factory.models.creative_contracts import (
    GenreProfile,
    ProjectLaunchProfile,
    GenreContract,
    PayoffCadence,
    PressureLimits,
)
from novel_factory.quality.genesis_quality_gate import (
    generate_launch_profile,
    generate_genre_contract,
    check_project_ready_for_production,
)


def _sample_genre_profile() -> GenreProfile:
    return GenreProfile(
        profile_id="urban_sign_in_power_fantasy",
        default_reader_expectations=["爽感", "升级", "反转"],
        default_payoff_loop="被小看 → 展示实力 → 打脸 → 新危机",
        opening_requirements=["第一章展示主角处境"],
        chapter_rhythm_defaults={
            "minor_payoff_frequency": 1,
            "visible_upgrade_frequency": 3,
            "max_consecutive_pressure": 3,
        },
        common_poison_points=["逻辑崩坏"],
        style_noise_patterns=["过度心理描写"],
        editor_weight_profile={"logic": 25},
        profile_specific_rules={
            "must_have_tropes": ["打脸", "装逼"],
            "avoid_patterns": ["系统流", "穿越"],
            "style_constraints": ["快节奏"],
        },
    )


class TestGenreProfile:
    def test_model_creation(self):
        profile = _sample_genre_profile()
        assert profile.profile_id == "urban_sign_in_power_fantasy"
        assert len(profile.default_reader_expectations) == 3
        assert profile.chapter_rhythm_defaults["minor_payoff_frequency"] == 1

    def test_default_values(self):
        profile = GenreProfile(profile_id="test")
        assert profile.default_reader_expectations == []
        assert profile.default_payoff_loop == ""

    def test_serialization(self):
        profile = _sample_genre_profile()
        data = profile.model_dump()
        assert "profile_id" in data
        assert isinstance(data["chapter_rhythm_defaults"], dict)
        restored = GenreProfile(**data)
        assert restored.profile_id == profile.profile_id


class TestProjectLaunchProfile:
    def test_model_creation(self):
        profile = ProjectLaunchProfile(
            target_reader="网络小说读者",
            market_lane="urban_sign_in",
            core_hook="废柴逆袭",
        )
        assert profile.target_reader == "网络小说读者"
        assert profile.core_hook == "废柴逆袭"

    def test_default_values(self):
        profile = ProjectLaunchProfile()
        assert profile.target_reader == ""
        assert profile.secondary_payoff_loops == []
        assert profile.hard_do_not_drift_rules == []

    def test_serialization(self):
        profile = ProjectLaunchProfile(core_hook="test hook")
        data = profile.model_dump()
        assert data["core_hook"] == "test hook"
        restored = ProjectLaunchProfile(**data)
        assert restored.core_hook == "test hook"


class TestGenreContract:
    def test_model_creation(self):
        contract = GenreContract(
            genre_id="urban_sign_in",
            promise_statement="爽文承诺",
            reader_expectations=["爽感"],
            payoff_cadence=PayoffCadence(minor_payoff="每章"),
            pressure_limits=PressureLimits(max_consecutive_heavy=3),
        )
        assert contract.genre_id == "urban_sign_in"
        assert contract.payoff_cadence.minor_payoff == "每章"

    def test_nested_models(self):
        contract = GenreContract()
        assert isinstance(contract.payoff_cadence, PayoffCadence)
        assert isinstance(contract.pressure_limits, PressureLimits)

    def test_serialization(self):
        contract = GenreContract(genre_id="test", promise_statement="承诺")
        data = contract.model_dump()
        assert data["genre_id"] == "test"
        assert "payoff_cadence" in data


class TestGenerateLaunchProfile:
    def test_stub_mode_basic(self):
        profile = generate_launch_profile(
            "一个废柴觉醒了灵力",
            _sample_genre_profile(),
            llm_caller=None,
        )
        assert isinstance(profile, ProjectLaunchProfile)
        assert profile.target_reader != ""
        assert profile.market_lane == "urban_sign_in_power_fantasy"

    def test_stub_mode_uses_user_idea(self):
        profile = generate_launch_profile(
            "一个少年获得了神秘传承",
            _sample_genre_profile(),
            llm_caller=None,
        )
        assert "少年" in profile.core_hook or "传承" in profile.core_hook

    def test_stub_mode_empty_idea(self):
        profile = generate_launch_profile(
            "",
            _sample_genre_profile(),
            llm_caller=None,
        )
        assert isinstance(profile, ProjectLaunchProfile)
        assert profile.core_hook != ""  # falls back to default_payoff_loop

    def test_different_genres(self):
        for pid in ["urban_sign_in_power_fantasy", "suspense_mystery", "cultivation_upgrade"]:
            genre = GenreProfile(
                profile_id=pid,
                default_payoff_loop="test loop",
                default_reader_expectations=["expectation"],
                chapter_rhythm_defaults={},
                profile_specific_rules={},
            )
            profile = generate_launch_profile("测试创意", genre, llm_caller=None)
            assert profile.market_lane == pid


class TestGenerateGenreContract:
    def test_stub_mode_basic(self):
        launch = ProjectLaunchProfile(
            target_reader="读者",
            primary_payoff_loop="升级",
            core_hook="hook",
        )
        contract = generate_genre_contract(launch, _sample_genre_profile())
        assert isinstance(contract, GenreContract)
        assert contract.genre_id == "urban_sign_in_power_fantasy"
        assert "升级" in contract.promise_statement

    def test_contract_has_forbidden_drift(self):
        launch = ProjectLaunchProfile()
        contract = generate_genre_contract(launch, _sample_genre_profile())
        assert "系统流" in contract.forbidden_drift

    def test_contract_has_editor_weights(self):
        launch = ProjectLaunchProfile()
        contract = generate_genre_contract(launch, _sample_genre_profile())
        assert "logic" in contract.editor_weights

    def test_payoff_cadence_populated(self):
        launch = ProjectLaunchProfile()
        contract = generate_genre_contract(launch, _sample_genre_profile())
        assert contract.payoff_cadence.minor_payoff != ""


class TestCheckProjectReadyForProduction:
    def test_no_contracts_not_ready(self):
        """No contracts → not ready."""
        class MockRepo:
            def get_creative_contract(self, pid, ctype):
                return None
        assert check_project_ready_for_production("proj1", MockRepo()) is False

    def test_has_launch_not_approved_not_ready(self):
        """Has launch profile but genre contract not approved → not ready."""
        import json
        class MockRepo:
            def get_creative_contract(self, pid, ctype):
                if ctype == "launch_profile":
                    return {"contract_data": "{}"}
                if ctype == "genre_contract":
                    return {"contract_data": json.dumps({"approved": False})}
                return None
        assert check_project_ready_for_production("proj1", MockRepo()) is False

    def test_approved_ready(self):
        """Both contracts present and approved → ready."""
        import json
        class MockRepo:
            def get_creative_contract(self, pid, ctype):
                if ctype == "launch_profile":
                    return {"contract_data": "{}"}
                if ctype == "genre_contract":
                    return {"contract_data": json.dumps({"approved": True})}
                return None
        assert check_project_ready_for_production("proj1", MockRepo()) is True

    def test_exception_returns_false(self):
        """Repository exception → not ready."""
        class BrokenRepo:
            def get_creative_contract(self, pid, ctype):
                raise RuntimeError("db error")
        assert check_project_ready_for_production("proj1", BrokenRepo()) is False


class TestProjectCreationFlow:
    """Test complete project creation flow: idea → launch profile → genre contract → approval → ready."""
    
    def test_full_flow_stub_mode(self):
        """Test complete flow in stub mode."""
        # Step 1: Generate launch profile from user idea
        genre_profile = _sample_genre_profile()
        user_idea = "一个废柴少年觉醒了灵力，开始逆袭之路"
        
        launch_profile = generate_launch_profile(user_idea, genre_profile, llm_caller=None)
        assert isinstance(launch_profile, ProjectLaunchProfile)
        assert launch_profile.market_lane == "urban_sign_in_power_fantasy"
        assert "废柴" in launch_profile.core_hook or "灵力" in launch_profile.core_hook
        
        # Step 2: Generate genre contract from launch profile
        genre_contract = generate_genre_contract(launch_profile, genre_profile)
        assert isinstance(genre_contract, GenreContract)
        assert genre_contract.genre_id == "urban_sign_in_power_fantasy"
        
        # Step 3: Simulate repository storage and approval
        class MockRepo:
            def __init__(self):
                self.contracts = {}
            
            def get_creative_contract(self, pid, ctype):
                return self.contracts.get((pid, ctype))
            
            def upsert_creative_contract(self, project_id, contract_type, data):
                self.contracts[(project_id, contract_type)] = {
                    "contract_data": json.dumps(data) if isinstance(data, dict) else data
                }
        
        repo = MockRepo()
        project_id = "test_project"
        
        # Save launch profile
        repo.upsert_creative_contract(project_id, "launch_profile", launch_profile.model_dump())
        
        # Save genre contract (not approved)
        contract_data = genre_contract.model_dump()
        contract_data["approved"] = False
        repo.upsert_creative_contract(project_id, "genre_contract", contract_data)
        
        # Step 4: Check project not ready (not approved)
        assert check_project_ready_for_production(project_id, repo) is False
        
        # Step 5: Approve contract
        contract_data["approved"] = True
        repo.upsert_creative_contract(project_id, "genre_contract", contract_data)
        
        # Step 6: Check project ready
        assert check_project_ready_for_production(project_id, repo) is True
    
    def test_different_genres_flow(self):
        """Test flow with different genre profiles."""
        genres = [
            ("urban_sign_in_power_fantasy", "都市签到流"),
            ("suspense_mystery", "悬疑推理"),
            ("cultivation_upgrade", "修仙升级"),
        ]
        
        for genre_id, genre_name in genres:
            # Create genre profile
            genre_profile = GenreProfile(
                profile_id=genre_id,
                default_reader_expectations=["爽感"],
                default_payoff_loop="升级打怪",
                chapter_rhythm_defaults={"minor_payoff_frequency": 1},
                profile_specific_rules={"must_have_tropes": ["打脸"]},
            )
            
            # Generate launch profile
            launch_profile = generate_launch_profile(f"测试{genre_name}创意", genre_profile)
            assert launch_profile.market_lane == genre_id
            
            # Generate genre contract
            genre_contract = generate_genre_contract(launch_profile, genre_profile)
            assert genre_contract.genre_id == genre_id
    
    def test_flow_with_empty_idea(self):
        """Test flow handles empty user idea gracefully."""
        genre_profile = _sample_genre_profile()
        
        # Generate launch profile with empty idea
        launch_profile = generate_launch_profile("", genre_profile)
        assert isinstance(launch_profile, ProjectLaunchProfile)
        assert launch_profile.core_hook != ""  # Should fall back to default
        
        # Generate genre contract
        genre_contract = generate_genre_contract(launch_profile, genre_profile)
        assert isinstance(genre_contract, GenreContract)


class TestUnapprovedBlocking:
    """Test that unapproved projects are blocked from production."""
    
    def test_unapproved_project_blocked(self):
        """Test that project without approved contract cannot start production."""
        class MockRepo:
            def __init__(self):
                self.contracts = {}
            
            def get_creative_contract(self, pid, ctype):
                return self.contracts.get((pid, ctype))
            
            def upsert_creative_contract(self, project_id, contract_type, data):
                self.contracts[(project_id, contract_type)] = {
                    "contract_data": json.dumps(data) if isinstance(data, dict) else data
                }
        
        repo = MockRepo()
        project_id = "blocked_project"
        
        # Generate and save contracts
        genre_profile = _sample_genre_profile()
        launch_profile = generate_launch_profile("测试创意", genre_profile)
        genre_contract = generate_genre_contract(launch_profile, genre_profile)
        
        # Save launch profile
        repo.upsert_creative_contract(project_id, "launch_profile", launch_profile.model_dump())
        
        # Save genre contract (NOT approved)
        contract_data = genre_contract.model_dump()
        contract_data["approved"] = False
        repo.upsert_creative_contract(project_id, "genre_contract", contract_data)
        
        # Verify project is NOT ready
        assert check_project_ready_for_production(project_id, repo) is False
    
    def test_missing_launch_profile_blocked(self):
        """Test that project without launch profile cannot start production."""
        class MockRepo:
            def __init__(self):
                self.contracts = {}
            
            def get_creative_contract(self, pid, ctype):
                return self.contracts.get((pid, ctype))
        
        repo = MockRepo()
        project_id = "no_launch_project"
        
        # Only save genre contract (approved)
        repo.contracts[(project_id, "genre_contract")] = {
            "contract_data": json.dumps({"approved": True})
        }
        
        # Verify project is NOT ready (missing launch profile)
        assert check_project_ready_for_production(project_id, repo) is False
    
    def test_missing_genre_contract_blocked(self):
        """Test that project without genre contract cannot start production."""
        class MockRepo:
            def __init__(self):
                self.contracts = {}
            
            def get_creative_contract(self, pid, ctype):
                return self.contracts.get((pid, ctype))
        
        repo = MockRepo()
        project_id = "no_contract_project"
        
        # Only save launch profile
        repo.contracts[(project_id, "launch_profile")] = {
            "contract_data": json.dumps({})
        }
        
        # Verify project is NOT ready (missing genre contract)
        assert check_project_ready_for_production(project_id, repo) is False
    
    def test_approval_enables_production(self):
        """Test that approving contract enables production."""
        class MockRepo:
            def __init__(self):
                self.contracts = {}
            
            def get_creative_contract(self, pid, ctype):
                return self.contracts.get((pid, ctype))
            
            def upsert_creative_contract(self, project_id, contract_type, data):
                self.contracts[(project_id, contract_type)] = {
                    "contract_data": json.dumps(data) if isinstance(data, dict) else data
                }
        
        repo = MockRepo()
        project_id = "approval_test_project"
        
        # Generate and save contracts
        genre_profile = _sample_genre_profile()
        launch_profile = generate_launch_profile("测试创意", genre_profile)
        genre_contract = generate_genre_contract(launch_profile, genre_profile)
        
        # Save both contracts
        repo.upsert_creative_contract(project_id, "launch_profile", launch_profile.model_dump())
        repo.upsert_creative_contract(project_id, "genre_contract", genre_contract.model_dump())
        
        # Initially not ready (not approved)
        assert check_project_ready_for_production(project_id, repo) is False
        
        # Approve contract
        contract_data = genre_contract.model_dump()
        contract_data["approved"] = True
        repo.upsert_creative_contract(project_id, "genre_contract", contract_data)
        
        # Now ready
        assert check_project_ready_for_production(project_id, repo) is True
