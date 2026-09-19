"""Search suggestions service — thin wrapper over ``services/search.py``.

Keeps the shared search builders untouched; normalises their varying
signatures to a uniform ``(query, params)`` pair and exposes a session-free
``suggest`` used by the search API and the client-side autocomplete.

No Flask session access here: HOD department pinning is applied by the caller
(via ``user_dept_id``) so every method stays testable without a request
context.

/     /     >---- خدمة اقتراحات البحث: غطاء رفيع فوق خدمات البحث المشتركة.
"""

from __future__ import annotations

from typing import List

from flask_db import get_db

from services.search import (
    build_course_search,
    build_department_search,
    build_room_search,
    build_teacher_search,
    build_user_search,
)


# /     /     >---- مخفّفات: بوحّدوا التوقيعات المختلفة في (query, params)
def _course(search='', dept_filter='', user_dept_id=None, page=1):
    query, params, _ = build_course_search(search, dept_filter, user_dept_id, page)
    return query, params


def _teacher(search='', dept_filter='', user_dept_id=None, page=1):
    query, params, _ = build_teacher_search(search, dept_filter, user_dept_id, page)
    return query, params


def _room(search='', dept_filter='', user_dept_id=None, page=1):
    query, params, _ = build_room_search(search, dept_filter or '', page)
    return query, params


def _department(search='', dept_filter='', user_dept_id=None, page=1):
    return build_department_search(search, page)


def _user(search='', dept_filter='', user_dept_id=None, page=1):
    return build_user_search(search, page)


# /     /     >---- جدول ربط نطاق البحث بالدالة البانية تبعو
_BUILDERS = {
    'courses': _course,
    'teachers': _teacher,
    'rooms': _room,
    'departments': _department,
    'users': _user,
}


class SearchService:
    """Suggest matching rows for a search domain, ordered by its default sort."""

    # /     /     >---- يرجع صفوف مطابقة للنطاق المطلوب (الحد الأقصى 1..50)
    def suggest(self, domain: str, search: str = '', dept_filter: str = '',
                user_dept_id: int = None, limit: int = 8) -> List[dict]:
        """Return up to ``limit`` rows for ``domain`` (clamped to 1..50)."""
        builder = _BUILDERS.get(domain)
        if builder is None:
            raise ValueError(f'Unknown search domain: {domain}')
        query, params = builder(
            search=search, dept_filter=dept_filter, user_dept_id=user_dept_id, page=1,
        )
        # /     /     >---- تقييد الحد في المدى المسموح ثم تنفيذ الاستعلام
        limit = max(1, min(int(limit or 8), 50))
        db = get_db()
        rows = db.execute(f'{query} LIMIT ?', (params or []) + [limit]).fetchall()
        return [dict(r) for r in rows]