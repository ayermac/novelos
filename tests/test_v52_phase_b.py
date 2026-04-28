"""v5.2 Phase B tests: Token tracking and error handling.

Tests for:
1. Token usage accumulation in workflow state
2. Token usage saved to workflow_runs table
3. LLM error handling with Chinese messages
"""

from __future__ import annotations

import os
import tempfile
import pytest

from novel_factory.db.repository import Repository
from novel_factory.db.connection import init_db
from novel_factory.llm.openai_compatible import (
    OpenAICompatibleProvider,
    TokenUsage,
    InvalidAPIKeyError,
    InsufficientBalanceError,
    LLMTimeoutError,
    RateLimitError,
    OutputValidationError,
)


class TestTokenUsage:
    """Test TokenUsage class."""

    def test_token_usage_creation(self):
        """Test basic TokenUsage creation."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            duration_ms=1234,
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.duration_ms == 1234

    def test_token_usage_to_dict(self):
        """Test TokenUsage serialization."""
        usage = TokenUsage(
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            duration_ms=5000,
        )
        d = usage.to_dict()
        assert d["prompt_tokens"] == 200
        assert d["completion_tokens"] == 100
        assert d["total_tokens"] == 300
        assert d["duration_ms"] == 5000


class TestCustomExceptions:
    """Test custom LLM exceptions with Chinese messages."""

    def test_invalid_api_key_error(self):
        """Test InvalidAPIKeyError has Chinese message."""
        try:
            raise InvalidAPIKeyError("API Key 无效或已过期，请检查配置")
        except InvalidAPIKeyError as e:
            assert "API Key" in str(e)
            assert "无效" in str(e)

    def test_insufficient_balance_error(self):
        """Test InsufficientBalanceError has Chinese message."""
        try:
            raise InsufficientBalanceError("API 余额不足，请充值后重试")
        except InsufficientBalanceError as e:
            assert "余额" in str(e)

    def test_rate_limit_error(self):
        """Test RateLimitError has Chinese message."""
        try:
            raise RateLimitError("API 请求频率超限，请稍后重试")
        except RateLimitError as e:
            assert "频率超限" in str(e)

    def test_timeout_error(self):
        """Test LLMTimeoutError has Chinese message."""
        try:
            raise LLMTimeoutError("LLM 响应超时（>60秒），请稍后重试")
        except LLMTimeoutError as e:
            assert "超时" in str(e)

    def test_output_validation_error(self):
        """Test OutputValidationError has Chinese message."""
        try:
            raise OutputValidationError("LLM 输出不是有效的 JSON 格式")
        except OutputValidationError as e:
            assert "JSON" in str(e)


class TestWorkflowRunsTokenTracking:
    """Test token tracking in workflow_runs table."""

    def test_update_workflow_run_with_tokens(self):
        """Test updating workflow run with token usage."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            # Create project and workflow run
            repo.create_project(
                project_id="test-project",
                name="Test Project",
                genre="urban",
                description="Test",
                total_chapters_planned=100,
                target_words=100000,
            )
            run_id = repo.create_workflow_run("test-project", 1)

            # Update with token usage
            ok = repo.update_workflow_run(
                run_id,
                status="completed",
                prompt_tokens=500,
                completion_tokens=250,
                total_tokens=750,
                duration_ms=3500,
            )
            assert ok

            # Verify tokens were saved
            conn = repo._conn()
            try:
                row = conn.execute(
                    "SELECT * FROM workflow_runs WHERE id=?",
                    (run_id,),
                ).fetchone()
                assert row["prompt_tokens"] == 500
                assert row["completion_tokens"] == 250
                assert row["total_tokens"] == 750
                assert row["duration_ms"] == 3500
                assert row["status"] == "completed"
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_get_workflow_runs_returns_tokens(self):
        """Test that get_workflow_runs_for_project returns token fields."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            # Create project and workflow run
            repo.create_project(
                project_id="test-project",
                name="Test Project",
                genre="urban",
                description="Test",
                total_chapters_planned=100,
                target_words=100000,
            )
            run_id = repo.create_workflow_run("test-project", 1)

            # Update with token usage
            repo.update_workflow_run(
                run_id,
                status="completed",
                prompt_tokens=1000,
                completion_tokens=500,
                total_tokens=1500,
                duration_ms=5000,
            )

            # Get runs and verify token fields
            runs = repo.get_workflow_runs_for_project("test-project")
            assert len(runs) == 1
            assert runs[0]["prompt_tokens"] == 1000
            assert runs[0]["completion_tokens"] == 500
            assert runs[0]["total_tokens"] == 1500
            assert runs[0]["duration_ms"] == 5000
        finally:
            os.unlink(db_path)


class TestOpenAICompatibleProvider:
    """Test OpenAI compatible provider features."""

    def test_provider_has_last_token_usage(self):
        """Test that provider has last_token_usage attribute."""
        from novel_factory.config.settings import LLMConfig
        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            model="gpt-4",
        )
        provider = OpenAICompatibleProvider(config)
        assert provider.last_token_usage is None

    def test_extract_json_from_markdown(self):
        """Test JSON extraction from markdown code blocks."""
        text = '''```json
{"key": "value"}
```'''
        result = OpenAICompatibleProvider._extract_json(text)
        assert result == '{"key": "value"}'

    def test_extract_json_from_plain(self):
        """Test JSON extraction from plain text with braces."""
        text = 'Here is the result: {"name": "test", "count": 42}'
        result = OpenAICompatibleProvider._extract_json(text)
        assert '"name": "test"' in result
        assert '"count": 42' in result

    def test_extract_json_from_array(self):
        """Test JSON extraction from array."""
        text = 'Results: [1, 2, 3]'
        result = OpenAICompatibleProvider._extract_json(text)
        assert result == '[1, 2, 3]'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
