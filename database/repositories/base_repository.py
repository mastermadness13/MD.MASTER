"""Minimal base repository.

Every repository inherits from this class.  It provides:

  • A lazy ``db`` property (Flask ``g`` connection via ``flask_db.get_db``
    when no connection is injected).
  • A ``paginate`` convenience that delegates to
    :func:`database.repositories._helpers.paginate`.

All other SQL lives in the concrete repositories.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from database.repositories._helpers import paginate as _paginate


class BaseRepository:
    """Abstract base for all repository classes."""

    # Subclasses MUST set this to their table name.
    table: str = ''

    def __init__(self, db=None):
        """
        Args:
            db: A ``sqlite3.Connection`` (with ``row_factory = sqlite3.Row``).
                When *None*, the repository will call ``get_db()`` lazily.
        """
        self._db = db

    @property
    def db(self):
        if self._db is None:
            from flask_db import get_db
            self._db = get_db()
        return self._db

    def paginate(self, base_query: str, params: Sequence = (),
                 page: int = 1, per_page: int = 20) -> Tuple[List[Dict], int, int, int]:
        """Run a paginated query.  Returns ``(rows, total, page, per_page)``."""
        return _paginate(self.db, base_query, params, page, per_page)
