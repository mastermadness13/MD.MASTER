"""Course content workflow API — quick search for the launcher.

Every endpoint here is read-only and protected by ``course_content.view``.
The launcher uses these to look up teachers / courses (linked only through
the active timetable) before sending a course to a teacher.
"""

from __future__ import annotations

from flask import Blueprint, request

from api.helpers import api_permission_required, err, ok
from flask_db import get_db

bp = Blueprint('api_course_content', __name__, url_prefix='/api/course-content')

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
