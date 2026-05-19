"""Sensitive information redaction utilities.

Ensures API keys, tokens, URL credentials, and query parameters
never leak into logs or user-visible error messages.
"""

from __future__ import annotations

import re


# Ordered by specificity: more specific/longer prefixes first.
# Each replacement is chosen so it will not be re-matched by later patterns.
_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # URL userinfo: https://user:pass@host -> https://***@host
    (re.compile(r"(?<=://)[^@\s:]+:[^@\s]+@"), "***@"),
    # sk-... API keys (OpenAI style) — catch even short placeholders
    (re.compile(r"sk-[a-zA-Z0-9_-]+"), "***"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{10,}", re.IGNORECASE), "Bearer ***"),
    # Env-style key assignments for known providers (before generic query params)
    (re.compile(r"OPENAI_API_KEY=[^\s]+", re.IGNORECASE), "OPENAI_API_KEY=***"),
    (re.compile(r"OPENROUTER_API_KEY=[^\s]+", re.IGNORECASE), "OPENROUTER_API_KEY=***"),
    (re.compile(r"DEEPSEEK_API_KEY=[^\s]+", re.IGNORECASE), "DEEPSEEK_API_KEY=***"),
    # Query param tokens — use negative lookahead to avoid re-matching our own replacements
    (re.compile(r"api_key=(?!\*\*\*)[^&\s]+", re.IGNORECASE), "api_key=***"),
    (re.compile(r"access_token=(?!\*\*\*)[^&\s]+", re.IGNORECASE), "access_token=***"),
    (re.compile(r"token=(?!\*\*\*)[^&\s]+", re.IGNORECASE), "token=***"),
    (re.compile(r"key=(?!\*\*\*)[^&\s]+", re.IGNORECASE), "key=***"),
]


def redact_sensitive_text(value: str) -> str:
    """Remove or mask sensitive tokens from a string.

    Covers:
    - sk-... style API keys
    - Bearer tokens
    - URL userinfo (user:pass@host)
    - Query params: api_key, access_token, token, key
    - Common provider env var assignments

    Args:
        value: Raw string that may contain secrets.

    Returns:
        String with sensitive values replaced by placeholders.
    """
    if not isinstance(value, str):
        value = str(value)
    for pattern, replacement in _REDACTION_PATTERNS:
        value = pattern.sub(replacement, value)
    return value
