"""Tests for JSON extraction and repair utilities (v6.6.21)."""

from __future__ import annotations

import json

import pytest

from novel_factory.llm.json_resilience import (
    extract_json,
    parse_json,
    safe_parse_json,
    JSONParseResult,
)


class TestExtractJson:
    """Test JSON extraction from various LLM output formats."""

    def test_plain_json(self):
        text = '{"scene_beats": [{"sequence": 1, "scene_goal": "test"}]}'
        result = extract_json(text)
        assert result == text

    def test_json_with_code_fence(self):
        text = '```json\n{"scene_beats": [{"sequence": 1}]}\n```'
        result = extract_json(text)
        assert result == '{"scene_beats": [{"sequence": 1}]}'

    def test_json_with_explanatory_text(self):
        text = 'Here is the output:\n\n```json\n{"key": "value"}\n```\n\nHope this helps!'
        result = extract_json(text)
        assert result == '{"key": "value"}'

    def test_json_without_fence_but_with_preamble(self):
        text = 'Here is the scene plan:\n\n{"scene_beats": [{"sequence": 1, "scene_goal": "g"}]}'
        result = extract_json(text)
        assert result == '{"scene_beats": [{"sequence": 1, "scene_goal": "g"}]}'

    def test_json_array(self):
        text = 'Some text before [1, 2, 3] and after'
        result = extract_json(text)
        assert result == '[1, 2, 3]'

    def test_bom_stripping(self):
        text = '\ufeff{"key": "value"}'
        result = extract_json(text)
        assert result == '{"key": "value"}'

    def test_nested_json_in_text(self):
        text = 'First {"a": 1} then {"b": 2}'
        result = extract_json(text)
        assert result == '{"a": 1}'


class TestParseJson:
    """Test JSON parsing with repair and diagnostics."""

    def test_valid_json(self):
        text = '{"scene_beats": [{"sequence": 1}]}'
        result = parse_json(text)
        assert result == {"scene_beats": [{"sequence": 1}]}

    def test_trailing_comma_repair(self):
        text = '{"scene_beats": [{"sequence": 1,}],}'
        result = parse_json(text)
        assert result == {"scene_beats": [{"sequence": 1}]}

    def test_single_quoted_repair(self):
        text = "{'scene_beats': [{'sequence': 1}]}"
        result = parse_json(text)
        assert result == {"scene_beats": [{"sequence": 1}]}

    def test_invalid_json_raises(self):
        text = '{"scene_beats": [invalid]}'
        with pytest.raises(json.JSONDecodeError) as exc_info:
            parse_json(text, agent_id="screenwriter", schema_name="ScreenwriterOutput")
        assert "screenwriter" in str(exc_info.value)
        assert "ScreenwriterOutput" in str(exc_info.value)

    def test_parse_error_includes_attempt(self):
        text = '{broken'
        with pytest.raises(json.JSONDecodeError) as exc_info:
            parse_json(text, attempt=2, max_attempts=3)
        assert "attempt 2/3" in str(exc_info.value)

    def test_safe_parse_json_success(self):
        text = '{"ok": true}'
        result = safe_parse_json(text)
        assert result.ok is True
        assert result.data == {"ok": True}

    def test_safe_parse_json_failure(self):
        text = '{broken'
        result = safe_parse_json(text, agent_id="test")
        assert result.ok is False
        assert result.error is not None
        assert result.attempt == 1


class TestParseJsonCodeFence:
    """Test parsing JSON wrapped in markdown code fences."""

    def test_code_fence_json(self):
        text = '```json\n{"scene_beats": [{"sequence": 1, "scene_goal": "g", "conflict": "c", "turn": "t", "hook": "h"}]}\n```'
        result = parse_json(text)
        assert "scene_beats" in result

    def test_code_fence_with_explanation(self):
        text = (
            "The scene plan is below:\n"
            "```json\n"
            '{"scene_beats": [{"sequence": 1, "scene_goal": "g"}]}\n'
            "```\n"
            "Let me know if you need changes."
        )
        result = parse_json(text)
        assert result == {"scene_beats": [{"sequence": 1, "scene_goal": "g"}]}


class TestParseJsonTrailingComma:
    """Test repair of trailing commas."""

    def test_trailing_comma_in_array(self):
        text = '{"beats": [1, 2, 3,]}'
        result = parse_json(text)
        assert result == {"beats": [1, 2, 3]}

    def test_trailing_comma_in_object(self):
        text = '{"a": 1, "b": 2,}'
        result = parse_json(text)
        assert result == {"a": 1, "b": 2}


class TestParseJsonUnquotedValues:
    """Test repair of unquoted scalar values."""

    def test_unquoted_string_value(self):
        text = '{"scene_goal": 这是目标}'
        result = parse_json(text)
        assert result["scene_goal"] == "这是目标"
