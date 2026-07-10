"""v6.10.20: Exception Unification Framework tests."""

from __future__ import annotations

import pytest

from novel_factory.exceptions import (
    AgentExecutionError,
    DBTransactionError,
    APIValidationError,
    LLMProviderError,
)


class TestAgentExecutionError:
    """AgentExecutionError carries agent, step, and wrapped error."""

    def test_basic_attributes(self):
        inner = ValueError("bad schema")
        e = AgentExecutionError("author", "invoke_llm", inner)
        assert e.agent == "author"
        assert e.step == "invoke_llm"
        assert e.error is inner
        assert "author" in str(e)
        assert "invoke_llm" in str(e)
        assert "bad schema" in str(e)

    def test_is_caught_by_except_exception(self):
        """Existing `except Exception:` blocks still catch it."""
        with pytest.raises(AgentExecutionError):
            try:
                raise AgentExecutionError("editor", "review", RuntimeError("timeout"))
            except Exception:
                raise

    def test_is_caught_by_specific_type(self):
        """New code can catch the specific type."""
        try:
            raise AgentExecutionError("planner", "plan", KeyError("missing"))
        except AgentExecutionError as e:
            assert e.agent == "planner"

    def test_repr_roundtrip(self):
        e = AgentExecutionError("screenwriter", "outline", TypeError("oops"))
        assert "AgentExecutionError" in repr(e)
        assert "screenwriter" in repr(e)


class TestDBTransactionError:
    """DBTransactionError is a plain Exception subclass."""

    def test_is_caught_by_except_exception(self):
        with pytest.raises(DBTransactionError):
            try:
                raise DBTransactionError("FK constraint failed")
            except Exception:
                raise

    def test_is_caught_by_specific_type(self):
        try:
            raise DBTransactionError("locked")
        except DBTransactionError as e:
            assert "locked" in str(e)


class TestAPIValidationError:
    """APIValidationError marks client-side request problems."""

    def test_is_caught_by_except_exception(self):
        with pytest.raises(APIValidationError):
            try:
                raise APIValidationError("missing field 'project_id'")
            except Exception:
                raise

    def test_is_caught_by_specific_type(self):
        try:
            raise APIValidationError("invalid JSON")
        except APIValidationError as e:
            assert "invalid JSON" in str(e)


class TestLLMProviderError:
    """LLMProviderError marks LLM layer failures."""

    def test_is_caught_by_except_exception(self):
        with pytest.raises(LLMProviderError):
            try:
                raise LLMProviderError("429 rate limit")
            except Exception:
                raise

    def test_is_caught_by_specific_type(self):
        try:
            raise LLMProviderError("timeout after 60s")
        except LLMProviderError as e:
            assert "timeout" in str(e)


class TestExceptionHierarchy:
    """All four types are independent Exception subclasses."""

    def test_all_inherit_from_exception(self):
        assert issubclass(AgentExecutionError, Exception)
        assert issubclass(DBTransactionError, Exception)
        assert issubclass(APIValidationError, Exception)
        assert issubclass(LLMProviderError, Exception)

    def test_can_be_caught_together(self):
        """A tuple catch works for all four types."""
        for exc_class in (
            AgentExecutionError,
            DBTransactionError,
            APIValidationError,
            LLMProviderError,
        ):
            try:
                if exc_class is AgentExecutionError:
                    raise exc_class("test", "step", RuntimeError("inner"))
                else:
                    raise exc_class("test")
            except (AgentExecutionError, DBTransactionError, APIValidationError, LLMProviderError):
                pass
