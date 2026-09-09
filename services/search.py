"""Unified search service — raw SQL LIKE builder with partial matches, OR'd
search conditions, AND'd filters, DISTINCT, and eager loading.

Usage in routes::

    from services.search import SearchConfig, build_search_query

    config = SearchConfig(
        table='courses c',
        search_columns=['c.name', 'c.code'],
        default_order='c.name',
        joins=[
            ('LEFT JOIN course_departments cd ON c.id = cd.course_id',
             'LEFT JOIN departments d ON cd.department_id = d.id'),
        ],
        select_extra=['d.name as dept_name'],
        soft_delete='c.deleted_at IS NULL',
    )
    where, params = build_search_query(config, search='phy', filters={'department_id': 42})
    rows, total, page, per_page = paginate(query, params, page)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class SearchConfig:
    """Declarative search configuration for a list view."""

    # Required
    table: str                              # e.g. 'courses c' or 'students s'
    search_columns: List[str]               # columns to OR-match against

    # Query options
    default_order: str = ''                 # ORDER BY clause (without keyword)
    soft_delete: str = ''                   # e.g. 'c.deleted_at IS NULL'
    distinct: bool = True                   # SELECT DISTINCT by default

    # JOINs — each tuple is (join_sql, conditionally_applied)
    # or just (join_sql,) if always applied
    joins: List[Tuple[str, ...]] = field(default_factory=list)

    # Extra SELECT columns beyond the main table.*
    select_extra: List[str] = field(default_factory=list)

    # Pre-built filter map: filter_name -> (column, params_value)
    # Built dynamically per-request via build_search_query


class SearchFilter:
    """Named filter that maps a request param to a WHERE condition."""

    def __init__(self, param: str, column: str, param_value: Any = None):
        """
        Args:
            param: Request parameter name (e.g. 'department_id')
            column: SQL column to filter on (e.g. 'c.department_id')
            param_value: Fixed value override (if not from request)
        """
        self.param = param
        self.column = column
        self.param_value = param_value


def build_search_query(
    config: SearchConfig,
    search: str = '',
    filters: Optional[Dict[str, Any]] = None,
    extra_where: Optional[List[str]] = None,
    extra_params: Optional[List[Any]] = None,
    order: str = '',
) -> Tuple[str, List[Any]]:
    """Build a WHERE clause and params list from config + request values.

    Returns:
        (full_query, params) — a complete SELECT query with all JOINs,
        WHERE, ORDER BY applied, ready for paginate().
    """
    where: List[str] = []
    params: List[Any] = []

    # Soft delete
    if config.soft_delete:
        where.append(config.soft_delete)

    # Search — OR'd across all search_columns
    if search and config.search_columns:
        conditions = ' OR '.join(f'{col} LIKE ?' for col in config.search_columns)
        where.append(f'({conditions})')
        params.extend([f'%{search}%'] * len(config.search_columns))

    # Extra where
    if extra_where:
        where.extend(extra_where)
    if extra_params:
        params.extend(extra_params)

    where_clause = ' AND '.join(where) if where else '1=1'

    # SELECT — extract alias from table if present (e.g. 'courses c' -> 'c')
    table_parts = config.table.strip().split()
    alias = table_parts[-1] if len(table_parts) > 1 else table_parts[0]
    cols = f'{alias}.*'
    if config.select_extra:
        cols += ', ' + ', '.join(config.select_extra)
    select_keyword = 'SELECT DISTINCT' if config.distinct else 'SELECT'

    # JOINs
    join_sql = ' '.join(j[0] for j in config.joins) if config.joins else ''

    # Base query
    query = f'{select_keyword} {cols} FROM {config.table} {join_sql} WHERE {where_clause}'

    # ORDER BY
    ord = order or config.default_order
    if ord:
        query += f' ORDER BY {ord}'

    return query, params


def build_teacher_search(
    search: str = '',
    dept_filter: str = '',
    user_dept_id: Optional[int] = None,
    page: int = 1,
) -> Tuple[str, List[Any], str]:
    """Build search query for teachers list."""
    config = SearchConfig(
        table='teachers t',
        search_columns=['t.name', 't.email', 't.academic_number'],
        default_order='t.name',
        soft_delete='t.deleted_at IS NULL',
        joins=[
            ('LEFT JOIN departments d ON t.department_id = d.id',),
            ('LEFT JOIN users u ON t.user_id = u.id',),
            ('LEFT JOIN qualifications q ON t.qualification_id = q.id',),
            ('LEFT JOIN academic_ranks r ON t.rank_id = r.id',),
        ],
        select_extra=['d.name as dept_name', 'u.username as username', 'u.supervisor_admin_dept',
                      'q.name_ar as qual_name', 'r.name_ar as rank_name'],
        distinct=False,
    )
    extra_where = []
    extra_params = []

    # Department filter
    effective_dept = str(user_dept_id) if user_dept_id else dept_filter
    if effective_dept:
        # Teacher may belong to many departments (primary column OR the
        # teacher_departments many-to-many table).
        extra_where.append(
            '(t.department_id = ? OR EXISTS ('
            'SELECT 1 FROM teacher_departments tdx '
            'WHERE tdx.teacher_id = t.id AND tdx.department_id = ?))')
        extra_params.extend([int(effective_dept), int(effective_dept)])

    query, params = build_search_query(
        config, search, extra_where=extra_where, extra_params=extra_params
    )
    return query, params, effective_dept


def build_course_search(
    search: str = '',
    dept_filter: str = '',
    user_dept_id: Optional[int] = None,
    page: int = 1,
) -> Tuple[str, List[Any], str]:
    """Build search query for courses list."""
    config = SearchConfig(
        table='courses c',
        search_columns=[
            'c.name', 'c.code',
            'd.name', 'c.notes',
        ],
        default_order='c.name',
        soft_delete='c.deleted_at IS NULL',
        joins=[
            ('LEFT JOIN course_departments cd ON c.id = cd.course_id',),
            ('LEFT JOIN departments d ON cd.department_id = d.id',),
        ],
        select_extra=[],
        distinct=True,
    )
    extra_where = []
    extra_params = []

    effective_dept = str(user_dept_id) if user_dept_id else dept_filter
    if effective_dept:
        extra_where.append('cd.department_id = ?')
        extra_params.append(int(effective_dept))

    query, params = build_search_query(
        config, search, extra_where=extra_where, extra_params=extra_params
    )
    return query, params, effective_dept


def build_room_search(
    search: str = '',
    dept_filter: str = '',
    page: int = 1,
) -> Tuple[str, List[Any], str]:
    """Build search query for rooms list."""
    config = SearchConfig(
        table='rooms r',
        search_columns=[
            'r.name', 'r.code',
            'rt.name_ar', 'd.name',
        ],
        default_order=(
            "CASE WHEN COALESCE(rt.css_class,'') = 'lab' THEN 1 ELSE 0 END, "
            'length(r.name), r.name'
        ),
        soft_delete='r.deleted_at IS NULL',
        joins=[
            ('LEFT JOIN room_types rt ON r.room_type_id = rt.id',),
            ('LEFT JOIN room_statuses rs ON r.status_id = rs.id',),
            ('LEFT JOIN floors f ON r.floor_id = f.id',),
            ('LEFT JOIN departments d ON r.department_id = d.id',),
        ],
        select_extra=[
            'rt.name_ar as type_name',
            'rs.name_ar as status_name',
            'f.name_ar as floor_name',
            'd.name as dept_name',
        ],
        distinct=False,
    )
    extra_where = []
    extra_params = []
    if dept_filter:
        extra_where.append('r.department_id = ?')
        extra_params.append(int(dept_filter))

    query, params = build_search_query(
        config, search, extra_where=extra_where, extra_params=extra_params
    )
    return query, params, dept_filter


def build_user_search(
    search: str = '',
    page: int = 1,
) -> Tuple[str, List[Any]]:
    """Build search query for users list."""
    config = SearchConfig(
        table='users u',
        search_columns=['u.username', 'u.email', 'u.label'],
        default_order='u.username',
        soft_delete='',
        joins=[
            ('LEFT JOIN departments d ON u.department_id = d.id',),
        ],
        select_extra=['d.name AS department_name'],
        distinct=False,
    )
    query, params = build_search_query(config, search)
    return query, params


def build_department_search(
    search: str = '',
    page: int = 1,
) -> Tuple[str, List[Any]]:
    """Build search query for departments list."""
    config = SearchConfig(
        table='departments d',
        search_columns=['d.name'],
        default_order='d.name',
        soft_delete='d.deleted_at IS NULL',
        distinct=False,
    )
    query, params = build_search_query(config, search)
    return query, params


def highlight_text(text: str, search: str) -> str:
    """HTML-highlight search terms in text (for template use)."""
    if not search or not text:
        return text or ''
    import re
    pattern = re.compile(re.escape(search), re.IGNORECASE)
    return pattern.sub(lambda m: f'<mark class="search-highlight">{m.group()}</mark>', text)
