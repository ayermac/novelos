"""v6.10.20: Exception Unification Framework — layered exception types for Novelos.

Provides 4 domain-specific exception layers so callers can distinguish
between DB failures, LLM failures, API validation errors, and Agent
execution errors without parsing string messages.

All types inherit from Exception so existing `except Exception:` blocks
continue to work. New code should catch the specific type when possible.
"""

from __future__ import annotations


class AgentExecutionError(Exception):
    """Agent execution failed at a named step.

    Attributes:
        agent:   Agent ID (e.g. "author", "editor")
        step:    Step name (e.g. "invoke_llm", "validate_output")
        error:   Original exception that caused the failure
    """

    def __init__(self, agent: str, step: str, error: Exception) -> None:
        self.agent = agent
        self.step = step
        self.error = error
        super().__init__(f"[{agent}] {step} failed: {error}")

    def __repr__(self) -> str:
        return (
            f"AgentExecutionError(agent={self.agent!r}, step={self.step!r}, "
            f"error={self.error!r})"
        )


class DBTransactionError(Exception):
    """SQLite / repository-level transaction failure.

    Raised when a DB operation violates a constraint, times out, or
    otherwise fails at the repository layer.
    """

    pass


class APIValidationError(Exception):
    """API request validation failure (bad payload, missing field, etc.).

    This is a *client* error (4xx class), not a server crash.
    """

    pass


class LLMProviderError(Exception):
    """LLM provider call failure (rate limit, timeout, malformed response).

    Raised by the LLM layer when the remote provider or local SDK
    returns an error that cannot be retried into success.
    """

    pass
