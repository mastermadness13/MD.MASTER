"""Courses API."""

from __future__ import annotations

from flask import Blueprint, request, session

from api_routes.helpers import (
    api_login_required,
    api_permission_required,
    body,
    err,
    log_history,
    ok,
    pagination,
)
from core.validators import integer_between
from flask_db import get_db
from security import current_user
from security import csrf_required
from services import course_service

bp = Blueprint('api_courses', __name__, url_prefix='/api/courses')


def _resolve_department():
    """HOD pages are scoped to the logged-in department; other roles pass ?department_id=."""
    role = session.get('role', '')
    if role == 'head_of_department':
        return session.get('hod_department_id') or session.get('department_id')
    return request.args.get('department_id', type=int) or session.get('department_id')


def _course_form(data, defaults=None):
    defaults = defaults or {}
    placements = data.get('placements')
    if isinstance(placements, list) and placements:
        department_ids = []
        for p in placements:
            did = p.get('department_id') or p.get('dept_id')
            if did and str(did).isdigit():
                department_ids.append(int(did))
    else:
        department_ids = data.get('department_ids') or []
        if not isinstance(department_ids, (list, tuple)):
            department_ids = [department_ids]
        department_ids = [d for d in department_ids if str(d).isdigit()]
        placements = [
            {'department_id': int(d), 'semester': int(data.get('semester') or defaults.get('semester', 1))}
            for d in department_ids
        ]
    prerequisite_id = data.get('prerequisite_id')
    try:
        prerequisite_id = int(prerequisite_id) if prerequisite_id else None
    except (TypeError, ValueError):
        prerequisite_id = None
    form = {
        'code': (data.get('code') or '').strip(),
        'name': (data.get('name') or '').strip(),
        'theoretical_hours': data.get('theoretical_hours', defaults.get('theoretical_hours', 0)),
        'practical_hours': data.get('practical_hours', defaults.get('practical_hours', 0)),
        'total_hours': data.get('total_hours', defaults.get('total_hours', 0)),
        'year': data.get('year', defaults.get('year', 1)),
        'semester': data.get('semester', defaults.get('semester', 1)),
        'icon': (data.get('icon') or defaults.get('icon') or '📖').strip(),
        'notes': (data.get('notes') or '').strip(),
    }
    if isinstance(placements, list) and placements and isinstance(placements[0], dict):
        form['semester'] = placements[0].get('semester', form['semester'])
    return form, placements, prerequisite_id


def _validate_course(form):
    """L5: one shared validation routine for course create + update."""
    errors = []
    if not form['code']:
        errors.append('الكود مطلوب')
    elif len(form['code']) > 30:
        errors.append('الكود يجب ألا يتجاوز 30 حرفاً')
    if not form['name']:
        errors.append('الاسم مطلوب')
    elif len(form['name']) > 255:
        errors.append('اسم المقرر أطول من المسموح (255 حرفاً كحد أقصى)')
    for check in (
        integer_between(form['year'], 1, 20, 'السنة الدراسية'),
        integer_between(form['semester'], 1, 20, 'الفصل الدراسي'),
        integer_between(form['theoretical_hours'], 0, 30, 'الساعات النظرية'),
        integer_between(form['practical_hours'], 0, 30, 'الساعات العملية'),
        integer_between(form['total_hours'], 0, 60, 'إجمالي الساعات'),
    ):
        if check:
            errors.append(check)
    return errors


@bp.route('')
@api_permission_required('courses.view')
def api_courses_list():
    db = get_db()
    page, per_page, search = pagination()
    rows, total, pg, pp, departments, course_depts = course_service.list_courses(
        db, session.get('role', ''), current_user(), search, None, page
    )
    return ok({
        'items': rows,
        'total': total,
        'page': pg,
        'per_page': pp,
        'departments': departments,
        'department_mapping': course_depts,
    })


@bp.route('', methods=['POST'])
@api_permission_required('courses.manage')
@csrf_required
def api_course_create():
    data = body()
    form, department_ids, prerequisite_id = _course_form(data)
    errors = _validate_course(form)
    if errors:
        return err('بيانات غير صحيحة', 422, errors=errors)
    db = get_db()
    course_id = course_service.create_course(db, form, department_ids, prerequisite_id)
    log_history(db, 'create', 'course', course_id, f'إنشاء مقرر: {form["name"]}')
    return ok({'id': course_id}, status=201)


@bp.route('/<int:course_id>')
@api_login_required
@api_permission_required('courses.view')
def api_course_detail(course_id):
    db = get_db()
    course = course_service.get_course_detail(db, course_id)
    if not course:
        return err('المقرر غير موجود', 404)
    return ok({'course': course})


@bp.route('/<int:course_id>', methods=['PUT'])
@api_permission_required('courses.manage')
@csrf_required
def api_course_update(course_id):
    db = get_db()
    c = course_service.get_course(db, course_id)
    if not c:
        return err('المقرر غير موجود', 404)
    data = body()
    form, department_ids, prerequisite_id = _course_form(data, defaults=dict(c))
    errors = _validate_course(form)
    if errors:
        return err('بيانات غير صحيحة', 422, errors=errors)
    course_service.update_course(db, course_id, form, department_ids, prerequisite_id)
    log_history(db, 'update', 'course', course_id, f'تعديل مقرر: {form["name"]}')
    return ok(True)


@bp.route('/<int:course_id>', methods=['DELETE'])
@api_permission_required('courses.manage')
@csrf_required
def api_course_delete(course_id):
    db = get_db()
    if not course_service.get_course(db, course_id):
        return err('المقرر غير موجود', 404)
    course_service.course_delete(
        db, course_id,
        lambda db: log_history(db, 'soft_delete', 'course', course_id, 'حذف مقرر'),
    )
    return ok(True)


@bp.route('/<int:course_id>/restore', methods=['POST'])
@api_permission_required('courses.manage')
@csrf_required
def api_course_restore(course_id):
    db = get_db()
    course_service.course_restore(db, course_id)
    return ok(True)


@bp.route('/<int:course_id>/permanent', methods=['DELETE'])
@api_permission_required('courses.manage')
@csrf_required
def api_course_hard_delete(course_id):
    db = get_db()
    course_service.course_hard_delete(db, course_id)
    return ok(True)


@bp.route('/move', methods=['POST'])
@api_permission_required('courses.manage')
@csrf_required
def api_courses_move():
    data = body()
    try:
        course_id = int(data.get('course_id'))
        dept_id = int(data.get('department_id'))
        semester = int(data.get('semester'))
    except (TypeError, ValueError):
        return err('بيانات غير مكتملة', 422)
    success, message = course_service.move_course_to_semester(get_db(), course_id, dept_id, semester)
    if not success:
        return err(message, 400)
    return ok({'message': message})


@bp.route('/sync-from-timetable', methods=['POST'])
@api_permission_required('courses.manage')
@csrf_required
def api_courses_sync_from_timetable():
    data = body()
    try:
        dept_id = int(data.get('department_id'))
    except (TypeError, ValueError):
        return err('بيانات غير مكتملة', 422)
    result = course_service.sync_courses_from_timetable(get_db(), dept_id)
    lines = [f'تمت مزامنة {result["synced"]} مقرر']
    if result['skipped']:
        lines.append(f'تم تخطي {result["skipped"]} مادة:')
        lines.extend(result['messages'])
    return ok({
        'synced': result['synced'],
        'skipped': result['skipped'],
        'message': '\n'.join(lines),
    })
