"""Output helpers for CLI commands.

Provides JSON envelope printing and human-readable output formatting.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _print_output(data: Any, use_json: bool = False) -> None:
    """Print output in human-readable or JSON format."""
    if use_json:
        print(json.dumps(data, ensure_ascii=False, default=str, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list):
                    print(f"{k}:")
                    for item in v:
                        print(f"  - {item}")
                else:
                    print(f"{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                print(item)
        else:
            print(data)


def print_json_envelope(ok: bool, error: str | None, data: Any, *, indent: int | None = None) -> None:
    """Print a JSON envelope to stdout.

    Args:
        ok: Success flag.
        error: Error message (None if no error).
        data: Response data payload.
        indent: Optional indent for pretty-printing.
    """
    envelope = {"ok": ok, "error": error, "data": data}
    print(json.dumps(envelope, ensure_ascii=False, indent=indent))


def print_error_and_exit(error_msg: str, use_json: bool, *, exit_code: int = 1, data: Any = None) -> None:
    """Print an error message and exit.

    In JSON mode, prints a JSON envelope. Otherwise prints human-readable text.
    """
    if use_json:
        envelope = {"ok": False, "error": error_msg, "data": data or {}}
        print(json.dumps(envelope, ensure_ascii=False))
    else:
        print(f"Error: {error_msg}")
    sys.exit(exit_code)


def print_llm_runtime_error(e: Exception, use_json: bool) -> None:
    """Handle LLM runtime exceptions with JSON envelope output."""
    error_msg = f"LLM runtime error: {type(e).__name__}: {e}"
    if use_json:
        print(json.dumps({
            "ok": False,
            "error": error_msg,
            "data": {"error_type": type(e).__name__},
        }, ensure_ascii=False))
    else:
        print(f"Error: {error_msg}")
    sys.exit(1)
