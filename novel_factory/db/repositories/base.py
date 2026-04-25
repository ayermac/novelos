"""Base repository with shared connection and utility methods."""

from __future__ import annotations

from ..connection import get_connection, row_to_dict


class BaseRepository:
    """Base class providing DB connection and utility helpers."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)
