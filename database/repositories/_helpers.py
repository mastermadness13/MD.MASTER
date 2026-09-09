"""Standalone query helpers shared by repositories.

These are module-level functions so they can be used without instantiating a
repository (e.g. inside service functions that receive a raw connection).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def paginate(db, base_query: str, params: Sequence = (),
             page: int = 1, per_page: int = 20) -> Tuple[List[Dict], int, int, int]:
    """Run a paginated query.  Returns ``(rows, total, page, per_page)``.

    ``base_query`` should **not** include ``ORDER BY`` with ``LIMIT``;
    the helper appends them automatically.
    """
    # Split off ORDER BY if present so we can wrap for counting.
    if 'ORDER BY' in base_query.upper():
        cut = base_query.upper().index('ORDER BY')
        count_part = base_query[:cut]
        order_part = base_query[cut:]
    else:
        count_part = base_query
        order_part = ''

    count_sql = f'SELECT COUNT(*) FROM ({count_part}) AS _cnt'
    total = db.execute(count_sql, params or []).fetchone()[0]

    offset = (page - 1) * per_page
    rows_sql = f'{count_part} {order_part} LIMIT ? OFFSET ?'.strip()
    rows = db.execute(
        rows_sql, list(params or []) + [per_page, offset]
    ).fetchall()
    return [dict(r) for r in rows], total, page, per_page


def build_where(conditions: Dict[str, Any],
                allowlist: Optional[Sequence[str]] = None) -> Tuple[str, List[Any]]:
    """Build a parameterised ``WHERE`` clause from a dict of column → value.

    Only keys in *allowlist* (when provided) are used.  Returns
    ``(where_sql, params)``; ``where_sql`` is ``''`` when nothing matches.
    """
    clauses: List[str] = []
    params: List[Any] = []
    for key, value in conditions.items():
        if allowlist is not None and key not in allowlist:
            continue
        if value is None:
            continue
        clauses.append(f'{key} = ?')
        params.append(value)
    if not clauses:
        return '', []
    return ' WHERE ' + ' AND '.join(clauses), params


def build_order(column: str = 'id', direction: str = 'ASC') -> str:
    """Build an ``ORDER BY`` clause with a whitelisted column name.

    Falls back to ``id ASC`` for anything that is not a bare identifier, so
    user input can never inject SQL.
    """
    direction = (direction or 'ASC').upper()
    if direction not in ('ASC', 'DESC'):
        direction = 'ASC'
    if not column or not column.replace('_', '').replace('.', '').isalnum():
        column = 'id'
    return f'ORDER BY {column} {direction}'
