"""JSON extraction and sanitization helpers for LLM outputs."""

from __future__ import annotations

import re


def extract_json(text: str) -> str:
    """Extract JSON from potentially markdown-wrapped text."""
    # Strip BOM and leading/trailing whitespace
    text = text.lstrip("\ufeff").strip()

    # Try fenced blocks first. Models often return variants such as
    # ```json, ``` json, ```JSON, or even an unclosed fence.
    match = re.match(
        r"^\s*(```|~~~)[^\r\n]*[\r\n]+(.*?)(?:[\r\n]+\1\s*)?\s*$",
        text,
        re.DOTALL,
    )
    if match:
        text = match.group(2).strip()

    # If a fence appears later in explanatory text, prefer its body.
    match = re.search(
        r"(```|~~~)[^\r\n]*[\r\n]+(.*?)(?:[\r\n]+\1)",
        text,
        re.DOTALL,
    )
    if match:
        text = match.group(2).strip()

    # Try finding the first { ... } or [ ... ], respecting strings
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start != -1:
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
                    candidate = text[start : i + 1]
                    return sanitize_json(candidate)

    # Fallback: return sanitized text
    return sanitize_json(text.strip())


def sanitize_json(text: str) -> str:
    """Attempt to fix common LLM JSON output issues before parsing.

    Handles: trailing commas, single-quoted strings, JS-style comments,
    and unescaped newlines in strings.
    """
    # Remove JS-style single-line comments (// ...) outside of strings
    result_lines = []
    in_string = False
    for line in text.split("\n"):
        new_line = []
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

    # Replace single-quoted keys/values with double-quoted (simple heuristic)
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

    # Some models emit prose scalar values without quotes, for example:
    # {"turn": 林澈发现线索}. Wrap those values before json.loads().
    text = re.sub(
        r'(:[^\S\r\n]*)([^,\n\r}\]]+)(?=,|\n|\r|}|\])',
        _quote_unquoted_value,
        text,
    )

    return text
