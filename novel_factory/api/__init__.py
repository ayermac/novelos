"""v5.1 JSON API Backend for Novel Factory.

Provides RESTful JSON API with:
- Unified envelope: {ok, error, data}
- Standardized error codes/messages
- No traceback exposure
- No API key/secret exposure
- Stub mode safety (no real LLM calls)
"""

from .envelope import EnvelopeResponse, envelope_response, error_response
from .deps import get_repo, get_settings, get_dispatcher, get_llm_mode

__all__ = [
    "EnvelopeResponse",
    "envelope_response",
    "error_response",
    "get_repo",
    "get_settings",
    "get_dispatcher",
    "get_llm_mode",
]
