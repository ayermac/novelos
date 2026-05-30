"""JSON extraction and repair utilities for LLM agent outputs (v6.6.21).

Provides robust parsing of JSON from model responses that may include:
- Markdown code fences
- Explanatory prose before/after the JSON
- Trailing commas
- Single-quoted strings
- BOM prefixes
- Unquoted scalar values

All repair operations are conservative: they only fix syntactic issues that
are unambiguously safe, and leave semantic validation to callers.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel for unrecoverable JSON
UNRECOVERABLE = object()


def extract_json(text: str) -> str:
    """Extract the first well-formed JSON object or array from text.

    Handles:
    - BOM stripping
    - Markdown code fences (```json ... ```)
    - Prose before/after JSON
    - Finds first { ... } or [ ... ] respecting string boundaries

    Returns the candidate JSON string (may still need _repair_json).
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    # Strip BOM and leading whitespace
    text = text.lstrip("\ufeff").strip()

    # Try fenced blocks first (models often wrap JSON in markdown)
    match = re.match(
        r"^\s*(```|~~~)[^\r\n]*[\r\n]+(.*?)(?:[\r\n]+\1\s*)?\s*$",
        text,
        re.DOTALL,
    )
    if match:
        text = match.group(2).strip()

    # If a fence appears later in explanatory text, prefer its body
    match = re.search(
        r"(```|~~~)[^\r\n]*[\r\n]+(.*?)(?:[\r\n]+\1)",
        text,
        re.DOTALL,
    )
    if match:
        text = match.group(2).strip()

    # Find first { ... } or [ ... ], respecting strings and escapes
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                escape_next = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_char:
                depth += 1
            elif c == end_char:
                depth -= 1
            if depth == 0:
                return text[start : i + 1]

    # Fallback: return sanitized text
    return text.strip()


def _pre_repair_json(text: str) -> str:
    """Fix common LLM JSON malformations before standard repair.

    Handles patterns common with GLM-5 and similar models:
    - Quoted booleans: "true" -> true, "false" -> false
    - Quoted null: "null" -> null
    - Quoted numbers in value position: "88" -> 88
    - Trailing comma inside quotes: "false," -> false,
    - Colon inside key name: "score:" -> "score"
    """
    # Fix quoted booleans/nulls with optional trailing comma inside quotes
    # Matches: "true" "false" "null" "true," "false," "null,"
    # Lookahead: comma/bracket/newline OR whitespace before next quote (key)
    text = re.sub(r':\s*"(true|false|null),?"\s*(?=[,}\]\n\r]|\s")', r': \1', text)
    # Fix quoted integers in value positions (with optional trailing comma)
    text = re.sub(r':\s*"(\d+),?"\s*(?=[,}\]\n\r]|\s")', r': \1', text)
    # Fix colon bleeding into key name: "score:" -> "score"
    text = re.sub(r'"(\w+):"\s*:', r'"\1":', text)
    return text


def _repair_json(text: str) -> str:
    """Attempt to fix common LLM JSON output issues before parsing.

    Safe repairs only:
    - Remove JS-style single-line comments outside strings
    - Remove trailing commas before } or ]
    - Replace simple single-quoted strings with double-quoted
    - Wrap unquoted scalar values in quotes

    Does NOT attempt structural changes (e.g. adding missing braces).
    """
    # Remove JS-style single-line comments (// ...) outside of strings
    result_lines = []
    for line in text.split("\n"):
        new_line = []
        in_string = False
        escape_next = False
        i = 0
        while i < len(line):
            c = line[i]
            if escape_next:
                new_line.append(c)
                escape_next = False
                i += 1
                continue
            if c == "\\":
                new_line.append(c)
                escape_next = True
                i += 1
                continue
            if c == '"':
                in_string = not in_string
                new_line.append(c)
                i += 1
                continue
            if not in_string and c == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            new_line.append(c)
            i += 1
        result_lines.append("".join(new_line))
    text = "\n".join(result_lines)

    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Replace simple single-quoted keys/values with double-quoted
    text = re.sub(r"(?<=[\[{,:\s])'([^']*)'(?=[\]},:\s])", r'"\1"', text)

    def _quote_unquoted_value(match: re.Match) -> str:
        prefix = match.group(1)
        value = match.group(2).strip()
        if not value:
            return match.group(0)
        if value[0] in '"{[0123456789-tfn':
            return match.group(0)
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{prefix}"{escaped}"'

    # Wrap prose scalar values without quotes
    text = re.sub(
        r'(:[^\S\r\n]*)([^,\n\r}\]]+)(?=,|\n|\r|}|\])',
        _quote_unquoted_value,
        text,
    )

    return text


def parse_json(
    text: str,
    *,
    agent_id: str = "unknown",
    schema_name: str | None = None,
    attempt: int = 1,
    max_attempts: int = 1,
) -> dict[str, Any]:
    """Parse JSON from LLM text with extraction and repair.

    Args:
        text: Raw LLM response text.
        agent_id: Agent name for diagnostic messages.
        schema_name: Expected schema name for diagnostics.
        attempt: Current parse attempt number.
        max_attempts: Max attempts for diagnostics.

    Returns:
        Parsed JSON dict.

    Raises:
        json.JSONDecodeError: If JSON cannot be extracted or repaired.
    """
    candidate = extract_json(text)
    pre_repaired = _pre_repair_json(candidate)
    repaired = _repair_json(pre_repaired)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        # Try one more time on original candidate (in case repair made it worse)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Build a rich diagnostic error
        error_loc = ""
        if hasattr(e, "lineno") and hasattr(e, "colno"):
            error_loc = f" line {e.lineno}, column {e.colno}"
        elif hasattr(e, "pos"):
            pos = e.pos  # type: ignore[attr-defined]
            error_loc = f" position {pos}"

        preview = text[:400].replace("\n", " ")
        schema_hint = f" schema={schema_name}" if schema_name else ""
        raise json.JSONDecodeError(
            msg=(
                f"JSON parse failed{error_loc} (attempt {attempt}/{max_attempts})"
                f" agent={agent_id}{schema_hint}"
                f" | preview: {preview!r}..."
            ),
            doc=text,
            pos=getattr(e, "pos", 0),
        ) from e


class JSONParseResult:
    """Result of a JSON parse attempt with diagnostics."""

    def __init__(
        self,
        ok: bool,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        raw_text: str = "",
        attempt: int = 0,
    ) -> None:
        self.ok = ok
        self.data = data or {}
        self.error = error
        self.raw_text = raw_text
        self.attempt = attempt

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error": self.error,
            "attempt": self.attempt,
            "raw_preview": self.raw_text[:500] if self.raw_text else None,
        }


def safe_parse_json(
    text: str,
    *,
    agent_id: str = "unknown",
    schema_name: str | None = None,
    attempt: int = 1,
    max_attempts: int = 1,
) -> JSONParseResult:
    """Safe JSON parse that never raises; returns JSONParseResult.

    Use when you need to inspect the result without try/except.
    """
    try:
        data = parse_json(
            text,
            agent_id=agent_id,
            schema_name=schema_name,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        return JSONParseResult(ok=True, data=data, raw_text=text, attempt=attempt)
    except json.JSONDecodeError as e:
        return JSONParseResult(
            ok=False,
            error=str(e),
            raw_text=text,
            attempt=attempt,
        )
