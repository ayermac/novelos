"""v6.8.1 — Style Detector Unit Tests

Tests for deterministic style detection from project metadata.
"""

import pytest

from novel_factory.quality.style_detector import (
    StyleProfile,
    detect_style_from_text,
    get_editor_weight_multiplier,
    get_style_prompt_injection,
)


# ── detect_style_from_text ─────────────────────────────────────────


class TestDetectStyleFromText:
    """Tests for keyword-based style detection."""

    def test_webnovel_single_keyword(self):
        """Single webnovel keyword triggers webnovel_excitement."""
        result = detect_style_from_text("这是一个逆袭的故事")
        assert result.primary_style == "webnovel_excitement"
        assert result.excitement_level == "high"
        assert result.opening_hook_required is True
        assert result.excitement_density_target == "every_500_chars"
        assert result.pacing_preference == "fast"
        assert "逆袭" in result.keywords_detected

    def test_webnovel_multiple_keywords(self):
        """Multiple webnovel keywords increase confidence."""
        result = detect_style_from_text("逆袭打脸金手指系统爽文")
        assert result.primary_style == "webnovel_excitement"
        assert len(result.keywords_detected) >= 5

    def test_webnovel_all_keywords(self):
        """All webnovel keywords detected."""
        text = " ".join([
            "逆袭", "打脸", "金手指", "升级", "碾压", "爽文", "开局",
            "系统", "签到", "抽奖", "重生", "穿越", "赘婿", "退婚",
            "龙王", "战神", "医神", "神豪", "装逼", "装弱", "扮猪吃虎",
        ])
        result = detect_style_from_text(text)
        assert result.primary_style == "webnovel_excitement"
        assert len(result.keywords_detected) == 21

    def test_suspense_single_keyword(self):
        """Single suspense keyword triggers suspense style."""
        result = detect_style_from_text("一个悬疑推理故事")
        assert result.primary_style == "suspense"
        assert result.excitement_level == "medium"
        assert result.opening_hook_required is True
        assert result.excitement_density_target == "every_1000_chars"
        assert result.pacing_preference == "moderate"
        assert "悬疑" in result.keywords_detected

    def test_suspense_multiple_keywords(self):
        """Multiple suspense keywords."""
        result = detect_style_from_text("悬疑推理烧脑反转暗黑")
        assert result.primary_style == "suspense"
        assert len(result.keywords_detected) >= 4

    def test_romance_single_keyword(self):
        """Single romance keyword triggers romance style."""
        result = detect_style_from_text("一个爱情故事")
        assert result.primary_style == "romance"
        assert result.excitement_level == "medium"
        assert result.opening_hook_required is True
        assert result.excitement_density_target == "every_1000_chars"
        assert result.pacing_preference == "moderate"
        assert "爱情" in result.keywords_detected

    def test_romance_multiple_keywords(self):
        """Multiple romance keywords."""
        result = detect_style_from_text("甜宠虐恋言情总裁豪门")
        assert result.primary_style == "romance"
        assert len(result.keywords_detected) >= 4

    def test_general_no_keywords(self):
        """No keywords → general style."""
        result = detect_style_from_text("一个普通的故事关于成长")
        assert result.primary_style == "general"
        assert result.excitement_level == "low"
        assert result.opening_hook_required is False
        assert result.excitement_density_target == "chapter_end_only"
        assert result.pacing_preference == "moderate"
        assert result.keywords_detected == []

    def test_general_empty_text(self):
        """Empty text → general style."""
        result = detect_style_from_text("")
        assert result.primary_style == "general"
        assert result.excitement_level == "low"

    def test_webnovel_wins_over_suspense(self):
        """Webnovel keywords outnumber suspense → webnovel wins."""
        result = detect_style_from_text("逆袭打脸金手指 悬疑")
        assert result.primary_style == "webnovel_excitement"

    def test_suspense_wins_over_webnovel(self):
        """Suspense keywords outnumber webnovel → suspense wins."""
        result = detect_style_from_text("悬疑推理烧脑 逆袭")
        assert result.primary_style == "suspense"

    def test_romance_wins_over_general(self):
        """Romance keywords present, no others → romance wins."""
        result = detect_style_from_text("爱情甜宠虐恋")
        assert result.primary_style == "romance"

    def test_case_insensitive(self):
        """Detection is case-insensitive."""
        result = detect_style_from_text("REBIRTH 逆袭")
        assert result.primary_style == "webnovel_excitement"
        assert "逆袭" in result.keywords_detected

    def test_mixed_text_with_keywords(self):
        """Keywords embedded in longer text."""
        result = detect_style_from_text(
            "主角重生回到十年前，获得金手指系统，开始逆袭打脸之路"
        )
        assert result.primary_style == "webnovel_excitement"
        assert "重生" in result.keywords_detected
        assert "金手指" in result.keywords_detected
        assert "系统" in result.keywords_detected
        assert "逆袭" in result.keywords_detected
        assert "打脸" in result.keywords_detected

    def test_tie_webnovel_over_suspense(self):
        """Equal count: webnovel takes precedence over suspense."""
        # 1 webnovel + 1 suspense → webnovel wins (>=)
        result = detect_style_from_text("逆袭 悬疑")
        assert result.primary_style == "webnovel_excitement"

    def test_tie_webnovel_over_romance(self):
        """Equal count: webnovel takes precedence over romance."""
        result = detect_style_from_text("逆袭 爱情")
        assert result.primary_style == "webnovel_excitement"

    def test_tie_suspense_over_romance(self):
        """Equal count: suspense takes precedence over romance."""
        result = detect_style_from_text("悬疑 爱情")
        assert result.primary_style == "suspense"


# ── get_style_prompt_injection ─────────────────────────────────────


class TestGetStylePromptInjection:
    """Tests for style-specific prompt injection."""

    def test_webnovel_planner(self):
        profile = StyleProfile(primary_style="webnovel_excitement")
        prompt = get_style_prompt_injection(profile, "planner")
        assert "爽文" in prompt
        assert "逆袭预期" in prompt
        assert "打脸" in prompt

    def test_webnovel_screenwriter(self):
        profile = StyleProfile(primary_style="webnovel_excitement")
        prompt = get_style_prompt_injection(profile, "screenwriter")
        assert "爽文节奏" in prompt
        assert "爽点 beat" in prompt

    def test_webnovel_author(self):
        profile = StyleProfile(primary_style="webnovel_excitement")
        prompt = get_style_prompt_injection(profile, "author")
        assert "爽文写作" in prompt
        assert "钩子" in prompt

    def test_webnovel_editor(self):
        profile = StyleProfile(primary_style="webnovel_excitement")
        prompt = get_style_prompt_injection(profile, "editor")
        assert "爽文审核" in prompt
        assert "pacing" in prompt

    def test_suspense_planner(self):
        profile = StyleProfile(primary_style="suspense")
        prompt = get_style_prompt_injection(profile, "planner")
        assert "悬疑" in prompt
        assert "悬念" in prompt

    def test_suspense_screenwriter(self):
        profile = StyleProfile(primary_style="suspense")
        prompt = get_style_prompt_injection(profile, "screenwriter")
        assert "悬疑节奏" in prompt

    def test_suspense_author(self):
        profile = StyleProfile(primary_style="suspense")
        prompt = get_style_prompt_injection(profile, "author")
        assert "悬疑写作" in prompt

    def test_romance_planner(self):
        profile = StyleProfile(primary_style="romance")
        prompt = get_style_prompt_injection(profile, "planner")
        assert "言情" in prompt
        assert "情感" in prompt

    def test_romance_screenwriter(self):
        profile = StyleProfile(primary_style="romance")
        prompt = get_style_prompt_injection(profile, "screenwriter")
        assert "言情节奏" in prompt

    def test_romance_author(self):
        profile = StyleProfile(primary_style="romance")
        prompt = get_style_prompt_injection(profile, "author")
        assert "言情写作" in prompt

    def test_general_returns_empty(self):
        profile = StyleProfile(primary_style="general")
        assert get_style_prompt_injection(profile, "planner") == ""
        assert get_style_prompt_injection(profile, "screenwriter") == ""
        assert get_style_prompt_injection(profile, "author") == ""
        assert get_style_prompt_injection(profile, "editor") == ""

    def test_unknown_agent_returns_empty(self):
        profile = StyleProfile(primary_style="webnovel_excitement")
        assert get_style_prompt_injection(profile, "unknown_agent") == ""

    def test_unknown_style_returns_empty(self):
        profile = StyleProfile(primary_style="unknown_style")
        assert get_style_prompt_injection(profile, "planner") == ""


# ── get_editor_weight_multiplier ───────────────────────────────────


class TestGetEditorWeightMultiplier:
    """Tests for editor scoring weight multipliers."""

    def test_high_excitement_pacing_doubled(self):
        """High excitement → pacing weight doubled (30/15 = 2.0)."""
        profile = StyleProfile(excitement_level="high")
        weights = get_editor_weight_multiplier(profile)
        assert weights["pacing"] == pytest.approx(2.0)

    def test_high_excitement_setting_reduced(self):
        """High excitement → setting weight reduced (20/25 = 0.8)."""
        profile = StyleProfile(excitement_level="high")
        weights = get_editor_weight_multiplier(profile)
        assert weights["setting"] == pytest.approx(0.8)

    def test_high_excitement_logic_reduced(self):
        """High excitement → logic weight reduced (20/25 = 0.8)."""
        profile = StyleProfile(excitement_level="high")
        weights = get_editor_weight_multiplier(profile)
        assert weights["logic"] == pytest.approx(0.8)

    def test_high_excitement_poison_reduced(self):
        """High excitement → poison weight reduced (15/20 = 0.75)."""
        profile = StyleProfile(excitement_level="high")
        weights = get_editor_weight_multiplier(profile)
        assert weights["poison"] == pytest.approx(0.75)

    def test_high_excitement_text_unchanged(self):
        """High excitement → text weight unchanged (15/15 = 1.0)."""
        profile = StyleProfile(excitement_level="high")
        weights = get_editor_weight_multiplier(profile)
        assert weights["text"] == pytest.approx(1.0)

    def test_medium_excitement_all_default(self):
        """Medium excitement → all weights 1.0."""
        profile = StyleProfile(excitement_level="medium")
        weights = get_editor_weight_multiplier(profile)
        for dim in ("setting", "logic", "poison", "text", "pacing"):
            assert weights[dim] == pytest.approx(1.0)

    def test_low_excitement_all_default(self):
        """Low excitement → all weights 1.0."""
        profile = StyleProfile(excitement_level="low")
        weights = get_editor_weight_multiplier(profile)
        for dim in ("setting", "logic", "poison", "text", "pacing"):
            assert weights[dim] == pytest.approx(1.0)

    def test_all_dimensions_present(self):
        """All five dimensions present in output."""
        profile = StyleProfile(excitement_level="high")
        weights = get_editor_weight_multiplier(profile)
        assert set(weights.keys()) == {"setting", "logic", "poison", "text", "pacing"}


# ── StyleProfile defaults ─────────────────────────────────────────


class TestStyleProfileDefaults:
    """Tests for StyleProfile dataclass defaults."""

    def test_default_values(self):
        profile = StyleProfile()
        assert profile.primary_style == "general"
        assert profile.excitement_level == "low"
        assert profile.opening_hook_required is False
        assert profile.excitement_density_target == "chapter_end_only"
        assert profile.pacing_preference == "moderate"
        assert profile.keywords_detected == []

    def test_keywords_default_is_empty_list(self):
        """keywords_detected default is a new list each time (field default_factory)."""
        p1 = StyleProfile()
        p2 = StyleProfile()
        assert p1.keywords_detected is not p2.keywords_detected

    def test_custom_values(self):
        profile = StyleProfile(
            primary_style="webnovel_excitement",
            excitement_level="high",
            opening_hook_required=True,
            excitement_density_target="every_500_chars",
            pacing_preference="fast",
            keywords_detected=["逆袭", "打脸"],
        )
        assert profile.primary_style == "webnovel_excitement"
        assert profile.keywords_detected == ["逆袭", "打脸"]
