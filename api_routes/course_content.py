"""Course content workflow API — quick search and protected translation."""

from __future__ import annotations

from flask import Blueprint, request, session

from api_routes.helpers import api_login_required, api_permission_required, err, ok
from core.rate_limiter import RateLimiter
from flask_db import get_db
from security.csrf import csrf_required
from services.translation_service import safe_translate_ar_to_en

bp = Blueprint('api_course_content', __name__, url_prefix='/api/course-content')
translation_limiter = RateLimiter(max_requests=60, window_seconds=60)

_TRANSLATION_TARGETS = {
    'course_name': 'course_name_en',
    'course_objective': 'course_objective_en',
    'prerequisites': 'prerequisites_en',
    'textbooks': 'textbooks_en',
    'notes': 'notes_en',
    'theoretical_curriculum_topic': 'theoretical_curriculum_topic_en',
    'practical_curriculum_topic': 'practical_curriculum_topic_en',
    'practical_content': 'practical_content_en',
}
_ROW_TRANSLATION_FIELDS = {'theoretical_curriculum_topic', 'practical_curriculum_topic'}
_MAX_TRANSLATION_CHARS = 5000

_ACTIVE_VERSION = (
    "SELECT id FROM timetable_versions WHERE status = 'active'"
)


def _active_version_filter(alias: str = 'tt') -> str:
    return (
        f"({alias}.version_id IS NULL OR {alias}.version_id IN ({_ACTIVE_VERSION}))"
    )


def _teacher_search_where(search):
    where = ['t.deleted_at IS NULL']
    params = []
    if search:
        where.append('(t.name LIKE ? OR t.academic_number LIKE ?)')
        params.extend([f'%{search}%'] * 2)
    return where, params


@bp.route('/teachers')
@api_permission_required('course_content.view')
def teachers_search():
    db = get_db()
    search = request.args.get('search', '').strip()
    where, params = _teacher_search_where(search)
    where_clause = ' AND '.join(where)
    rows = db.execute(
        f'''SELECT t.id, t.name, t.academic_rank, t.department_id,
                   d.name AS department_name,
                   (SELECT COUNT(*)
                    FROM timetable tt
                    JOIN courses c2 ON tt.course_id = c2.id
                    WHERE tt.teacher_id = t.id
                      AND tt.deleted_at IS NULL
                      AND c2.deleted_at IS NULL
                      AND {_active_version_filter()}) AS course_count
            FROM teachers t
            LEFT JOIN departments d ON t.department_id = d.id
            WHERE {where_clause}
            ORDER BY t.name
            LIMIT 30''',
        params,
    ).fetchall()
    return ok({'teachers': [dict(r) for r in rows]})


@bp.route('/translate', methods=['POST'])
@api_login_required
@api_permission_required('course_content.manage')
@csrf_required
def translate():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return err('صيغة الطلب غير صحيحة', 400)

    field = str(payload.get('field', '')).strip()
    if field not in _TRANSLATION_TARGETS:
        return err('الحقل غير مسموح للترجمة', 422)

    text = payload.get('text')
    if not isinstance(text, str):
        return err('النص العربي مطلوب', 422)
    text = text.strip()
    if not text:
        return err('النص العربي مطلوب', 422)
    if len(text) > _MAX_TRANSLATION_CHARS:
        return err('النص طويل جدًا للترجمة', 422)

    row_index = payload.get('row_index')
    if field in _ROW_TRANSLATION_FIELDS:
        if isinstance(row_index, bool):
            return err('رقم الصف غير صحيح', 422)
        try:
            row_index = int(row_index)
        except (TypeError, ValueError):
            return err('رقم الصف غير صحيح', 422)
        if row_index < 0 or row_index >= 12:
            return err('رقم الصف غير صحيح', 422)
    else:
        row_index = None

    key = f"course-content-translate:{session.get('user_id', '')}"
    if translation_limiter.is_limited(key):
        return err('تم تجاوز عدد طلبات الترجمة، حاول لاحقًا', 429)
    translation_limiter.record(key)

    translated = safe_translate_ar_to_en(text)
    if not translated:
        return err('تعذر إكمال الترجمة الآن', 502)

    return ok({
        'field': field,
        'target': _TRANSLATION_TARGETS[field],
        'row_index': row_index,
        'text': translated,
    })


@bp.route('/courses')
@api_permission_required('course_content.view')
def courses_search():
    db = get_db()
    search = request.args.get('search', '').strip()
    where = ['c.deleted_at IS NULL']
    params = []
    if search:
        where.append('(c.name LIKE ? OR c.code LIKE ?)')
        params.extend([f'%{search}%'] * 2)
    where_clause = ' AND '.join(where)
    rows = db.execute(
        f'''SELECT c.id, c.name, c.code, c.year, c.semester,
                   c.theoretical_hours, c.practical_hours, c.total_hours,
                   c.accreditation AS credits,
                   d.id AS department_id, d.name AS department_name,
                   EXISTS (
                       SELECT 1 FROM course_files cf
                       WHERE cf.course_id = c.id
                         AND cf.file_type = 'form'
                         AND cf.status IN ('approved', 'published')
                   ) AS has_form
            FROM courses c
            LEFT JOIN course_departments cd ON cd.course_id = c.id
            LEFT JOIN departments d ON cd.department_id = d.id
            WHERE {where_clause}
            GROUP BY c.id
            ORDER BY c.name''',
        params,
    ).fetchall()
    items = [dict(r) for r in rows]
    return ok({'courses': items})


@bp.route('/teacher-courses')
@api_permission_required('course_content.view')
def teacher_courses():
    db = get_db()
    teacher_id = request.args.get('teacher_id', type=int)
    if not teacher_id:
        return err('معرّف عضو هيئة التدريس مطلوب', 422)
    rows = db.execute(
        f'''SELECT t.id AS timetable_id, t.course_id, t.semester,
                   t.department_id, t.student_section,
                   c.name AS course_name, c.code AS course_code,
                   c.theoretical_hours, c.practical_hours, c.total_hours,
                   c.accreditation AS credits,
                   d.name AS department_name
            FROM timetable t
            JOIN courses c ON t.course_id = c.id
            LEFT JOIN departments d ON t.department_id = d.id
            WHERE t.teacher_id = ?
              AND t.deleted_at IS NULL
              AND c.deleted_at IS NULL
              AND {_active_version_filter('t')}
            GROUP BY t.id
            ORDER BY c.name''',
        (teacher_id,),
    ).fetchall()
    return ok({'courses': [dict(r) for r in rows]})


@bp.route('/course-teachers')
@api_permission_required('course_content.view')
def course_teachers():
    db = get_db()
    course_id = request.args.get('course_id', type=int)
    if not course_id:
        return err('معرّف المقرر مطلوب', 422)
    rows = db.execute(
        f'''SELECT DISTINCT t.id, t.name, t.academic_rank,
                   d.name AS department_name
            FROM timetable tt
            JOIN teachers t ON tt.teacher_id = t.id
            LEFT JOIN departments d ON t.department_id = d.id
            WHERE tt.course_id = ?
              AND tt.deleted_at IS NULL
              AND t.deleted_at IS NULL
              AND {_active_version_filter()}
            ORDER BY t.name''',
        (course_id,),
    ).fetchall()
    return ok({'teachers': [dict(r) for r in rows]})
