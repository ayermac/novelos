"""v6.10.19: BaseStore - aggregation layer over Repository facade.

Store holds a single Repository instance (which combines all domain mixins
via multiple inheritance) and provides cross-repo aggregation queries.
Store does NOT manage multiple repo instances - Repository is already a facade.
"""

from __future__ import annotations

from ..db.repository import Repository


class BaseStore:
    """Base class for aggregation Stores.

    Holds a single Repository facade instance. Subclasses call
    ``self._repo.<method>()`` directly - no _get_repo dispatch needed
    because Repository combines all domain mixins.
    """

    def __init__(self, repo: Repository | None = None) -> None:
        """
        Args:
            repo: Pre-instantiated Repository. If None, creates Repository().
        """
        self._repo = repo if repo is not None else Repository()

    @property
    def repo(self) -> Repository:
        """Expose underlying Repository for writes or fine-grained queries."""
        return self._repo
