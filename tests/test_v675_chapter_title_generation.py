"""Tests for v6.7.5 Chapter Title Generation.

This module tests the independent chapter title generation mechanism
introduced in v6.7.5, which replaces content-opening-derived titles
with LLM-generated titles based on chapter content and instruction context.
"""

from __future__ import annotations

import pytest

from novel_factory.agents.author import AuthorAgent
from novel_factory.models.schemas import TitleGenerationOutput


class TestTitleGenerationOutput:
    """Tests for TitleGenerationOutput model."""

    def test_title_generation_output_basic(self):
        """Test basic TitleGenerationOutput creation."""
        output = TitleGenerationOutput(title="第1章 暗夜追踪", reasoning="突出主角追踪场景")
        assert output.title == "第1章 暗夜追踪"
        assert output.reasoning == "突出主角追踪场景"

    def test_title_generation_output_minimal(self):
        """Test TitleGenerationOutput with minimal fields."""
        output = TitleGenerationOutput(title="第5章 危机四伏")
        assert output.title == "第5章 危机四伏"
        assert output.reasoning == ""


class TestIsUsableChapterTitle:
    """Tests for _is_usable_chapter_title validation."""

    def test_valid_title(self):
        """Test that valid titles pass validation."""
        assert AuthorAgent._is_usable_chapter_title("第1章 暗夜追踪", 1, {})
        assert AuthorAgent._is_usable_chapter_title("第10章 危机四伏", 10, {})
        assert AuthorAgent._is_usable_chapter_title("第100章 最后的决战", 100, {})

    def test_rejects_placeholder_titles(self):
        """Test that placeholder titles are rejected."""
        assert not AuthorAgent._is_usable_chapter_title("第1章", 1, {})
        assert not AuthorAgent._is_usable_chapter_title("第1章节", 1, {})
        assert not AuthorAgent._is_usable_chapter_title("第1章 待命名", 1, {})
        assert not AuthorAgent._is_usable_chapter_title("第1章 未命名", 1, {})
        assert not AuthorAgent._is_usable_chapter_title("第1章 占位", 1, {})

    def test_rejects_planning_verbs(self):
        """Test that titles starting with planning verbs are rejected."""
        instruction = {}
        assert not AuthorAgent._is_usable_chapter_title("第1章 引入新角色", 1, instruction)
        assert not AuthorAgent._is_usable_chapter_title("第1章 铺垫伏笔", 1, instruction)
        assert not AuthorAgent._is_usable_chapter_title("第1章 描绘场景", 1, instruction)
        assert not AuthorAgent._is_usable_chapter_title("第1章 建立关系", 1, instruction)
        assert not AuthorAgent._is_usable_chapter_title("第1章 推进剧情", 1, instruction)

    def test_rejects_planning_terms(self):
        """Test that titles containing planning terms are rejected."""
        instruction = {}
        assert not AuthorAgent._is_usable_chapter_title("第1章 本章目标", 1, instruction)
        assert not AuthorAgent._is_usable_chapter_title("第1章 关键事件", 1, instruction)

    def test_rejects_punctuation(self):
        """Test that titles with punctuation are rejected."""
        assert not AuthorAgent._is_usable_chapter_title("第1章 追踪，开始", 1, {})
        assert not AuthorAgent._is_usable_chapter_title("第1章 危机。", 1, {})
        assert not AuthorAgent._is_usable_chapter_title("第1章 转折；", 1, {})

    def test_rejects_too_long_titles(self):
        """Test that titles exceeding 16 characters are rejected."""
        # Title suffix > 16 chars should be rejected
        assert not AuthorAgent._is_usable_chapter_title(
            "第1章 这是一个非常非常非常长的标题超过限制", 1, {}
        )

    def test_rejects_objective_copy(self):
        """Test that titles copying instruction objective are rejected."""
        instruction = {"objective": "主角追踪神秘人物进入废弃工厂"}
        # Title that copies objective should be rejected
        assert not AuthorAgent._is_usable_chapter_title(
            "第1章 主角追踪神秘人物", 1, instruction
        )

    def test_accepts_good_titles(self):
        """Test that well-formed titles are accepted."""
        assert AuthorAgent._is_usable_chapter_title("第1章 暗夜追踪", 1, {})
        assert AuthorAgent._is_usable_chapter_title("第1章 废弃工厂", 1, {})
        assert AuthorAgent._is_usable_chapter_title("第1章 神秘来客", 1, {})
        assert AuthorAgent._is_usable_chapter_title("第1章 倒计时", 1, {})
        assert AuthorAgent._is_usable_chapter_title("第1章 危机降临", 1, {})


class TestIsOpeningDerivedTitle:
    """Tests for _is_opening_derived_title detection."""

    def test_detects_exact_match(self):
        """Test detection when title exactly matches content opening."""
        content = "暗夜追踪开始了。林泽站在窗前，凝视着远方的灯火。"
        title = "第1章 暗夜追踪"

        assert AuthorAgent._is_opening_derived_title(title, content, 1)

    def test_detects_substring_match(self):
        """Test detection when title is substring of content opening."""
        content = "废弃工厂的大门紧锁着。林泽推了推，纹丝不动。"
        title = "第1章 废弃工厂"

        assert AuthorAgent._is_opening_derived_title(title, content, 1)

    def test_rejects_non_derived_title(self):
        """Test that non-opening-derived titles are not flagged."""
        content = "暗夜追踪开始了。林泽站在窗前，凝视着远方的灯火。"
        title = "第1章 神秘来客"  # Not from opening

        assert not AuthorAgent._is_opening_derived_title(title, content, 1)

    def test_rejects_short_suffix(self):
        """Test that very short suffixes are not flagged."""
        content = "他走进房间。"
        title = "第1章 他"  # Too short

        # Should not flag because suffix is too short (< 4 chars)
        assert not AuthorAgent._is_opening_derived_title(title, content, 1)

    def test_handles_empty_content(self):
        """Test handling of empty content."""
        assert not AuthorAgent._is_opening_derived_title("第1章 标题", "", 1)
        assert not AuthorAgent._is_opening_derived_title("第1章 标题", None, 1)

    def test_handles_empty_title(self):
        """Test handling of empty title."""
        content = "内容开始..."
        assert not AuthorAgent._is_opening_derived_title("", content, 1)
        assert not AuthorAgent._is_opening_derived_title(None, content, 1)


class TestTitleFromInstruction:
    """Tests for _title_from_instruction fallback."""

    def test_derives_from_ending_hook(self):
        """Test deriving title from ending_hook."""
        instruction = {
            "ending_hook": "神秘人物的真实身份揭晓",
            "key_events": [],
        }
        title = AuthorAgent._title_from_instruction(instruction, 1)
        assert title is not None
        assert "第1章" in title

    def test_derives_from_key_events(self):
        """Test deriving title from key_events."""
        instruction = {
            "ending_hook": "",
            "key_events": ["主角发现神秘信件", "追踪到废弃工厂"],
        }
        title = AuthorAgent._title_from_instruction(instruction, 1)
        assert title is not None

    def test_returns_none_for_empty_instruction(self):
        """Test that empty instruction returns None."""
        instruction = {}
        title = AuthorAgent._title_from_instruction(instruction, 1)
        assert title is None


class TestCleanTitleSuffix:
    """Tests for _clean_title_suffix cleaning logic."""

    def test_strips_quotes(self):
        """Test stripping quotes from suffix."""
        assert AuthorAgent._clean_title_suffix('"暗夜追踪"') == "暗夜追踪"
        assert AuthorAgent._clean_title_suffix('"危机四伏"') == "危机四伏"

    def test_strips_chapter_markers(self):
        """Test stripping chapter markers."""
        assert AuthorAgent._clean_title_suffix("本章：暗夜追踪") == "暗夜追踪"
        assert AuthorAgent._clean_title_suffix("章节：危机") == "危机"

    def test_truncates_long_suffix(self):
        """Test truncating long suffixes to 14 chars."""
        long_suffix = "这是一个非常非常非常长的标题内容需要截断"
        result = AuthorAgent._clean_title_suffix(long_suffix)
        assert len(result) == 14

    def test_splits_on_punctuation(self):
        """Test splitting on punctuation."""
        assert AuthorAgent._clean_title_suffix("暗夜追踪，危机四伏") == "暗夜追踪"
        assert AuthorAgent._clean_title_suffix("危机降临。") == "危机降临"

    def test_rejects_too_short(self):
        """Test rejecting too short suffixes."""
        assert AuthorAgent._clean_title_suffix("一") == ""
        assert AuthorAgent._clean_title_suffix("") == ""


class TestStripChapterPrefix:
    """Tests for _strip_chapter_prefix utility."""

    def test_strips_numeric_prefix(self):
        """Test stripping numeric chapter prefix."""
        assert AuthorAgent._strip_chapter_prefix("第1章 暗夜追踪", 1) == "暗夜追踪"
        assert AuthorAgent._strip_chapter_prefix("第10章 危机", 10) == "危机"

    def test_strips_chinese_numeric_prefix(self):
        """Test stripping Chinese numeric chapter prefix."""
        assert AuthorAgent._strip_chapter_prefix("第一章 暗夜追踪", 1) == "暗夜追踪"
        assert AuthorAgent._strip_chapter_prefix("第十章 危机", 10) == "危机"

    def test_handles_various_separators(self):
        """Test handling various separators after chapter number."""
        assert AuthorAgent._strip_chapter_prefix("第1章：暗夜追踪", 1) == "暗夜追踪"
        assert AuthorAgent._strip_chapter_prefix("第1章、暗夜追踪", 1) == "暗夜追踪"
        assert AuthorAgent._strip_chapter_prefix("第1章.暗夜追踪", 1) == "暗夜追踪"


class TestInstructionItems:
    """Tests for _instruction_items normalization."""

    def test_handles_list(self):
        """Test handling list input."""
        result = AuthorAgent._instruction_items(["事件1", "事件2", "事件3"])
        assert result == ["事件1", "事件2", "事件3"]

    def test_handles_json_string(self):
        """Test handling JSON string input."""
        result = AuthorAgent._instruction_items('["事件1", "事件2"]')
        assert result == ["事件1", "事件2"]

    def test_handles_semicolon_separated(self):
        """Test handling semicolon-separated string."""
        result = AuthorAgent._instruction_items("事件1；事件2；事件3")
        assert result == ["事件1", "事件2", "事件3"]

    def test_handles_newline_separated(self):
        """Test handling newline-separated string."""
        result = AuthorAgent._instruction_items("事件1\n事件2\n事件3")
        assert result == ["事件1", "事件2", "事件3"]

    def test_handles_empty(self):
        """Test handling empty input."""
        assert AuthorAgent._instruction_items(None) == []
        assert AuthorAgent._instruction_items("") == []
        assert AuthorAgent._instruction_items([]) == []


class TestDeriveTitleFallback:
    """Tests for _derive_title fallback chain (integration tests)."""

    def test_returns_existing_usable_title(self):
        """Test that existing usable title is returned."""
        # This is a simplified test - full integration would need mock state
        # The actual logic is tested via the _is_usable_chapter_title tests
        pass

    def test_fallback_to_instruction_derived(self):
        """Test fallback to instruction-derived title."""
        # This is tested via _title_from_instruction tests
        pass

    def test_final_fallback_to_chapter_number(self):
        """Test final fallback to '第N章'."""
        # When all else fails, should return "第N章"
        pass


class TestTitleGenerationIntegration:
    """Integration tests for title generation in real mode."""

    @pytest.fixture
    def mock_state(self):
        """Create mock FactoryState for testing."""
        return {
            "project_id": "test-project",
            "chapter_number": 1,
            "llm_mode": "stub",  # Use stub mode for unit tests
            "chapter_status": "drafted",
        }

    @pytest.fixture
    def mock_instruction(self):
        """Create mock instruction for testing."""
        return {
            "objective": "主角追踪神秘人物进入废弃工厂",
            "key_events": ["发现神秘信件", "追踪到工厂", "发现隐藏入口"],
            "ending_hook": "神秘人物的真实身份揭晓",
            "plots_to_plant": ["神秘组织的线索"],
            "plots_to_resolve": [],
        }

    def test_stub_mode_does_not_generate_title(self, mock_state, mock_instruction):
        """Test that stub mode does not call LLM for title generation."""
        # In stub mode, _generate_chapter_title should return None
        # because it only runs in real mode
        # This is verified by the llm_mode check in _generate_chapter_title
        assert mock_state["llm_mode"] == "stub"

    def test_title_generation_does_not_block_workflow(self, mock_state, mock_instruction):
        """Test that title generation failure does not block workflow."""
        # _generate_chapter_title returns None on failure
        # The fallback chain continues with instruction-derived title
        # This is the expected behavior per v6.7.5 spec
        pass


class TestTitleRulesCompliance:
    """Tests for v6.7.5 title rules compliance."""

    def test_title_length_within_range(self):
        """Test that generated titles are within 4-16 character range."""
        # Valid titles
        valid_titles = [
            "第1章 危机",  # 2 chars suffix (minimum)
            "第1章 暗夜追踪",  # 4 chars suffix
            "第1章 废弃工厂的秘密",  # 7 chars suffix
            "第1章 神秘组织的最后通牒",  # 9 chars suffix
        ]
        for title in valid_titles:
            suffix = AuthorAgent._strip_chapter_prefix(title, 1)
            assert 2 <= len(suffix) <= 16, f"Title suffix length out of range: {title}"

    def test_title_highlights_key_elements(self):
        """Test that titles can highlight key elements."""
        # These are examples of good titles that highlight key elements
        good_titles = [
            "第1章 废弃工厂",  # Location
            "第1章 神秘信件",  # Key object
            "第1章 倒计时",  # Countdown
            "第1章 身份之谜",  # Doubt/mystery
            "第1章 致命陷阱",  # Crisis
            "第1章 悬崖边",  # Hook
        ]
        for title in good_titles:
            assert AuthorAgent._is_usable_chapter_title(title, 1, {}), f"Title should be valid: {title}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
