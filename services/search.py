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

/     /     >---- خدمة البحث الموحدة: توليد استعلامات LIKE للبحث الجزئي مع الشروط.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.text import escape_like, normalize_search_text


@dataclass
class SearchConfig:
    """Declarative search configuration for a list view.

    /     /     >---- إعدادات بحث صريحة لصفحة قائمة.
    """

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

    # ── Opt-in folded ("smart") search; see build_text_search_where ──
    smart_search: bool = False                 # off by default for every other page
    smart_sql_fn: str = 'normalize_search'     # UDF registered in database/connection.py
    smart_max_tokens: int = 4


# /     /     >---- فلتر مسجّل: يربط متغير الطلب بعمود SQL
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


# /     /     >---- بناء استعلام SELECT كامل (JOINs + WHERE + ORDER BY) جاهز للترقيم
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

    # /     /     >---- شرط الحذف الناعم
    if config.soft_delete:
        where.append(config.soft_delete)

    # /     /     >---- البحث: مطابقة OR على كل أعمدة البحث
    if search and config.search_columns:
        if config.smart_search:
            # /     /     >---- البحث الذكي: طيّ عربي + تقسيم كلمات
            clause, clause_params = build_text_search_where(
                config.search_columns, search,
                sql_fn=config.smart_sql_fn,
                max_tokens=config.smart_max_tokens,
            )
            if clause:
                where.append(clause)
                params.extend(clause_params)
        else:
            conditions = ' OR '.join(f'{col} LIKE ?' for col in config.search_columns)
            where.append(f'({conditions})')
            params.extend([f'%{search}%'] * len(config.search_columns))

    # /     /     >---- شروط إضافية من المستدعي
    if extra_where:
        where.extend(extra_where)
    if extra_params:
        params.extend(extra_params)

    where_clause = ' AND '.join(where) if where else '1=1'

    # /     /     >---- استخراج الاسم المستعار من الجدول ('courses c' → 'c')
    table_parts = config.table.strip().split()
    alias = table_parts[-1] if len(table_parts) > 1 else table_parts[0]
    cols = f'{alias}.*'
    if config.select_extra:
        cols += ', ' + ', '.join(config.select_extra)
    select_keyword = 'SELECT DISTINCT' if config.distinct else 'SELECT'

    # /     /     >---- تجميع وصلات الجداول
    join_sql = ' '.join(j[0] for j in config.joins) if config.joins else ''

    # /     /     >---- الاستعلام الأساسي
    query = f'{select_keyword} {cols} FROM {config.table} {join_sql} WHERE {where_clause}'

    # /     /     >---- الترتيب (افتراضي أو مخصص)
    ord = order or config.default_order
    if ord:
        query += f' ORDER BY {ord}'

    return query, params


# ─────────────────────────────────────────────

# /     /     >---- سقف طول البحث: يمنع طلبات ضخمة وقنابل LIKE
MAX_SEARCH_LENGTH = 120

# /     /     >---- نتعرّف هل النص فيه حروف عربية (نحتاج الطيّة) ولا ASCII فقط
_ARABIC_RE = re.compile(
    '[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF'
    '\uFB50-\uFDFF\uFE70-\uFEFF]'
)

# /     /     >---- محرف واحد على الأقل داخل الكلمة (نتجاهل علامات الترقيم)
_TOKEN_OK_RE = re.compile(r'\w', re.UNICODE)


# /     /     >---- نقسّم استعلام المستخدم إلى كلمات بحث مطلوبة معاً (AND)
def search_terms(search: str, max_tokens: int = 4) -> List[str]:
    """Split a raw user query into AND'ed, folded search tokens.

    ``'رئيس قسم الرياضيات'`` -> ``['رئيس', 'قسم', 'الرياضيات']``.

    Returns ``[]`` for empty / punctuation-only input so the caller can drop
    the search clause entirely instead of emitting a predicate that matches
    everything.
    """
    if not search:
        return []
    # /     /     >---- نقصّ الطول قبل أي معالجة
    folded = normalize_search_text(str(search)[:MAX_SEARCH_LENGTH])
    # /     /     >---- نقسّم بعد الطيّة فتصير "قسم" و"القسم" كلمة واحدة
    tokens: List[str] = []
    for chunk in folded.split(' '):
        if not chunk or not _TOKEN_OK_RE.search(chunk):
            continue
        if chunk not in tokens:          # إزالة التكرار مع الحفاظ على الترتيب
            tokens.append(chunk)
        if len(tokens) >= max_tokens:
            break
    return tokens


# /     /     >---- نبني شرط البحث المطويّ: AND بين الكلمات، OR بين الأعمدة
def build_text_search_where(
    columns: Sequence[str],
    search: str,
    *,
    sql_fn: str = 'normalize_search',
    max_tokens: int = 4,
) -> Tuple[str, List[Any]]:
    """Build an AND'ed-terms folded LIKE predicate over a per-row text blob.

    The Arabic branch concatenates the row's searchable columns once and folds
    the result with a single ``sql_fn`` call, so the number of Python UDF
    invocations per row equals the number of tokens, NOT (columns x tokens).
    That is a ~40x reduction on a wide table and is the difference between
    21 s and a usable request.

    Returns ``('', [])`` when *search* has no usable token, so the caller can
    drop the clause. Every emitted ``LIKE`` carries ``ESCAPE '\\'`` because
    SQLite has no default LIKE escape character.
    """
    terms = search_terms(search, max_tokens)
    if not terms or not columns:
        return '', []

    # /     /     >---- مسارات ASCII فقط: LIKE عادي بلا نداء دالة SQL
    if not any(_ARABIC_RE.search(term) for term in terms):
        or_cols = ' OR '.join(f"{col} LIKE ? ESCAPE '\\'" for col in columns)
        groups = ['(' + or_cols + ')' for _ in terms]
        params: List[Any] = []
        for term in terms:
            params.extend([f'%{escape_like(term)}%'] * len(columns))
        return '(' + ' AND '.join(groups) + ')', params

    # /     /     >---- ندمج أعمدة الصف في نص واحد ونطويّه بنداء واحد
    concat = " || ' ' || ".join(f"COALESCE({col}, '')" for col in columns)
    blob = f'{sql_fn}({concat})'
    groups = [f"({blob} LIKE ? ESCAPE '\\')" for _ in terms]
    params = [f'%{escape_like(term)}%' for term in terms]
    return '(' + ' AND '.join(groups) + ')', params


# /     /     >---- حد SQLite للأعداد الصحيحة (INTEGER 64-bit)
_SQLITE_MAX_INT = 2 ** 63 - 1


# /     /     >---- نتحقق إن رقم القسم صحيح وإلا نتجاهله بدل ما نرمي خطأ
def _coerce_dept_id(value) -> Optional[int]:
    """Return a positive, SQLite-representable int for *value*, else None."""
    try:
        dept_id = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return dept_id if 0 < dept_id <= _SQLITE_MAX_INT else None


# /     /     >---- استعلام بحث الأساتذة مع ربط القسم (أساسي أو من جدول الأقسام)
def build_teacher_search(
    search: str = '',
    dept_filter: str = '',
    user_dept_id: Optional[int] = None,
    page: int = 1,
) -> Tuple[str, List[Any], str]:
    """Build search query for teachers list.

    Opts into the folded ("smart") search engine, so a query matches after
    Arabic folding (taa-marbuta, hamza, Persian letterforms, tatweel, Arabic
    digits) and every resulting token must appear somewhere in the row's
    mirrored text.  ``teacher_departments`` deliberately stays inside the
    ``EXISTS`` subquery — a JOIN would multiply rows and, with
    ``distinct=False``, corrupt both ``COUNT(*)`` and pagination.
    """
    config = SearchConfig(
        table='teachers t',
        search_columns=[
            # /     /     >---- بيانات الأستاذ نفسها
            't.name', 't.email', 't.phone',
            't.academic_number',
            # /     /     >---- المسميات الوظيفية (نصوص مرآة)
            't.position', 't.specialization', 't.qualification',
            't.academic_rank', 't.classification',
            # /     /     >---- الحساب المرتبط (لا يوجد users.name)
            'u.username', 'u.email', 'u.label', 'u.supervisor_admin_dept',
            # /     /     >---- الأقسام (أساسي ورئاسته)
            'd.name', 'hd.name',
            # /     /     >---- القوائم المرجعية (كلها 1:1 عبر مفتاح أساسي)
            'q.name_ar', 'r.name_ar', 'c.name_ar', 'sp.name', 'aat.name',
        ],
        default_order='t.name',
        soft_delete='t.deleted_at IS NULL',
        joins=[
            ('LEFT JOIN departments d ON t.department_id = d.id',),
            ('LEFT JOIN departments hd ON t.hod_department_id = hd.id',),
            ('LEFT JOIN users u ON t.user_id = u.id',),
            ('LEFT JOIN qualifications q ON t.qualification_id = q.id',),
            ('LEFT JOIN academic_ranks r ON t.rank_id = r.id',),
            # /     /     >---- قوائم إضافية: كلها many-to-one على مفتاح أساسي
            ('LEFT JOIN classifications c ON t.classification_id = c.id',),
            ('LEFT JOIN specializations sp ON t.specialization_id = sp.id',),
            ('LEFT JOIN admin_assignment_types aat ON t.admin_assignment_type_id = aat.id',),
        ],
        select_extra=['d.name as dept_name', 'hd.name as hod_dept_name',
                      'u.username as username', 'u.supervisor_admin_dept',
                      'q.name_ar as qual_name', 'r.name_ar as rank_name'],
        distinct=False,
        # /     /     >---- البحث الذكي مفعّل لصفحة أعضاء هيئة التدريس فقط
        smart_search=True,
    )
    extra_where = []
    extra_params = []

    # /     /     >---- فلتر القسم: العمود الأساسي أو جدول الأقسام المتعددة
    dept_id = _coerce_dept_id(user_dept_id if user_dept_id else dept_filter)
    effective_dept = str(dept_id) if dept_id else ''
    if dept_id:
        extra_where.append(
            '(t.department_id = ? OR EXISTS ('
            'SELECT 1 FROM teacher_departments tdx '
            'WHERE tdx.teacher_id = t.id AND tdx.department_id = ?))')
        extra_params.extend([dept_id, dept_id])

    query, params = build_search_query(
        config, search, extra_where=extra_where, extra_params=extra_params
    )
    return query, params, effective_dept


# /     /     >---- استعلام بحث المقررات مع فلتر القسم
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

    dept_id = _coerce_dept_id(user_dept_id if user_dept_id else dept_filter)
    effective_dept = str(dept_id) if dept_id else ''
    if dept_id:
        extra_where.append('cd.department_id = ?')
        extra_params.append(dept_id)

    query, params = build_search_query(
        config, search, extra_where=extra_where, extra_params=extra_params
    )
    return query, params, effective_dept


# /     /     >---- استعلام بحث القاعات مع أسمائها المعرّبة ومعلوماتها
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


# /     /     >---- استعلام بحث المستخدمين
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


# /     /     >---- استعلام بحث الأقسام
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


# /     /     >---- تعليم كلمات البحث بتظليل HTML آمن (للاستخدام في القوالب)
def highlight_text(text: str, search: str) -> str:
    """HTML-highlight search terms in text (for template use).

    Output is intended to be rendered with the ``| safe`` filter, so the
    input is HTML-escaped first: only the ``<mark>`` wrapper tag is emitted,
    never raw text content. Escaping both sides keeps the match working on
    escaped characters (e.g. ``<`` → ``&lt;``).
    """
    import html as html_module
    import re
    if not search or not text:
        return html_module.escape(text or '')
    escaped_text = html_module.escape(text)
    pattern = re.compile(re.escape(html_module.escape(search)), re.IGNORECASE)
    return pattern.sub(
        lambda m: f'<mark class="search-highlight">{m.group()}</mark>',
        escaped_text,
    )


# /     /     >---- تظليل يتعرف على المطابقة بعد الطيّ (يستخدمه البحث الذكي)
def highlight_search_terms(
    text: str,
    search: str,
    terms: Optional[Sequence[str]] = None,
) -> str:
    """Fold-aware HTML highlight, used by the smart teachers list only.

    :func:`highlight_text` matches the literal search string, so a row that
    only matched *after* folding (``search='احمد'``, cell ``'أحمد'``) rendered
    with no highlight at all.  This version folds the cell, keeps an index map
    back to the original characters, locates each term in the folded string,
    maps the span back, then escapes and wraps.

    Output is safe to render with ``|safe``: every segment is HTML-escaped
    before the ``<mark>`` wrapper is added.
    """
    import html as html_module
    # /     /     >---- لا نص → نرجّع فاضي
    if not text:
        return ''
    raw = str(text)
    if not search and not terms:
        return html_module.escape(raw)

    # /     /     >---- نبني النص المطويّ مع خريطة فهرس → موضع الحرف الأصلي
    folded_chars: List[str] = []
    index_map: List[int] = []
    for i, ch in enumerate(raw):
        try:
            f = normalize_search_text(ch)
        except (ValueError, TypeError):
            f = ch
        for fc in f:
            folded_chars.append(fc)
            index_map.append(i)

    needles = [t for t in (list(terms) if terms is not None else search_terms(search)) if t]
    if not needles or not folded_chars:
        return html_module.escape(raw)

    pattern = re.compile('|'.join(re.escape(t) for t in needles))
    # /     /     >---- نحوّل كل مدى مطابقة إلى مدى على النص الأصلي
    spans: List[Tuple[int, int]] = []
    for m in pattern.finditer(''.join(folded_chars)):
        if not m.group():
            continue
        spans.append((index_map[m.start()], index_map[m.end() - 1] + 1))
    if not spans:
        return html_module.escape(raw)

    # /     /     >---- ندمج المدى المتداخلة
    spans.sort()
    merged: List[List[int]] = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    # /     /     >---- نركّب الهTML مع تهريب كل جزء
    out: List[str] = []
    cursor = 0
    for start, end in merged:
        out.append(html_module.escape(raw[cursor:start]))
        out.append('<mark class="search-highlight">'
                   + html_module.escape(raw[start:end]) + '</mark>')
        cursor = end
    out.append(html_module.escape(raw[cursor:]))
    return ''.join(out)