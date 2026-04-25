"""Hash utilities for content integrity and idempotency.

v1.1 provides stable JSON hashing for artifact deduplication
and version idempotency.
"""

from __future__ import annotations

import hashlib
import json


def stable_json_hash(payload: dict) -> str:
    """Compute a SHA-256 hash of a dict, with deterministic key ordering.

    The hash is insensitive to JSON key order — two dicts with the same
    content but different key order produce the same hash.

    Args:
        payload: Dict to hash.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
