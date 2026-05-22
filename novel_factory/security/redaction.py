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
    # HTTP headers with secrets
    (re.compile(r"Authorization\s*:\s*[a-zA-Z0-9_\-\.]{10,}", re.IGNORECASE), "Authorization: ***"),
    (re.compile(r"x-api-key\s*:\s*[a-zA-Z0-9_\-]+", re.IGNORECASE), "x-api-key: ***"),
    # Env-style key assignments for known providers (before generic patterns)
    (re.compile(r"OPENAI_API_KEY\s*=\s*[^\s]+", re.IGNORECASE), "OPENAI_API_KEY=***"),
    (re.compile(r"OPENROUTER_API_KEY\s*=\s*[^\s]+", re.IGNORECASE), "OPENROUTER_API_KEY=***"),
    (re.compile(r"DEEPSEEK_API_KEY\s*=\s*[^\s]+", re.IGNORECASE), "DEEPSEEK_API_KEY=***"),
    # Generic env-style assignments with flexible spacing (after specific providers)
    (re.compile(r"([A-Z_]+API_KEY)\s*=\s*[^\s]+", re.IGNORECASE), r"\1=***"),
    # Query param tokens — use negative lookahead to avoid re-matching our own replacements
    (re.compile(r"api_key\s*[=:]\s*(?!\*\*\*)[^&\s]+", re.IGNORECASE), "api_key=***"),
    (re.compile(r"access_token\s*[=:]\s*(?!\*\*\*)[^&\s]+", re.IGNORECASE), "access_token=***"),
    (re.compile(r"token\s*[=:]\s*(?!\*\*\*)[^&\s]+", re.IGNORECASE), "token=***"),
    (re.compile(r"key\s*[=:]\s*(?!\*\*\*)[^&\s]+", re.IGNORECASE), "key=***"),
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
