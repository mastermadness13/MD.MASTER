"""Teachers API."""

from __future__ import annotations

from flask import Blueprint, session

from api_routes.helpers import (
    api_login_required,
    api_permission_required,
    body,
    err,
    log_history,
    ok,
    pagination,
)
from flask_db import get_db
from security import current_user
from security import csrf_required
from services import teacher_service

bp = Blueprint('api_teachers', __name__, url_prefix='/api/teachers')


def _teacher_form(data):
    def fk(key, default=None):
        value = data.get(key, default)
        if value in (None, ''):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    department_ids = data.get('department_ids') or []
    if not isinstance(department_ids, (list, tuple)):
        department_ids = [department_ids]
    department_ids = [int(d) for d in department_ids if str(d).isdigit()]
    return {
        'name': (data.get('name') or '').strip(),
        'username': (data.get('username') or '').strip(),
        'email': (data.get('email') or '').strip(),
        'phone': (data.get('phone') or '').strip(),
        'department_id': fk('department_id') or (department_ids[0] if department_ids else None),
        'specialization_id': fk('specialization_id'),
        'academic_number': (data.get('academic_number') or '').strip(),
        'qualification_id': fk('qualification_id'),
        'rank_id': fk('rank_id'),
        'classification_id': fk('classification_id'),
        'national_id': (data.get('national_id') or '').strip(),
        'contract_date': (data.get('contract_date') or '').strip(),
        'tasks': (data.get('tasks') or '').strip(),
        'specialization': (data.get('specialization') or '').strip(),
    }, department_ids


@bp.route('')
@api_permission_required('teachers.view')
def api_teachers_list():
    db = get_db()
    page, per_page, search = pagination()
    dept_filter = session.get('hod_department_id') \
        if session.get('role') == 'head_of_department' else None
    dept_param = dept_filter
    rows, total, pg, pp, departments, applied_filter = teacher_service.list_teachers(
        db, session.get('role', ''), current_user(), search, dept_param, page
    )
    return ok({
        'items': rows,
        'total': total,
        'page': pg,
        'per_page': pp,
        'departments': departments,
    })


@bp.route('', methods=['POST'])
@api_permission_required('teachers.manage')
@csrf_required
def api_teachers_create():
    data = body()
    form, department_ids = _teacher_form(data)
    if not form['name']:
        return err('الاسم مطلوب', 422)
    db = get_db()
    try:
        creds = teacher_service.create_teacher(db, form, department_ids=department_ids)
    except ValueError as exc:
        message = str(exc)
        if 'academic_number' in message:
            return err('الرقم الكلية مستخدم مسبقاً', 422)
        if 'Username' in message:
            return err('نيك نيم الدخول مستخدم مسبقاً — اختر نيك نيم آخر', 422)
        if 'too short' in message:
            return err('نيك نيم الدخول قصير جداً — حرفان على الأقل', 422)
        return err(message, 422)
    log_history(db, 'create', 'teacher', creds.get('id'),
                f'إنشاء عضو هيئة التدريس: {form["name"]}')
    return ok({'id': creds.get('id'), 'username': creds.get('username'),
               'code': creds.get('password')}, status=201)


@bp.route('/<int:teacher_id>')
@api_login_required
@api_permission_required('teachers.view')
def api_teacher_detail(teacher_id):
    db = get_db()
    teacher = teacher_service.get_teacher_detail(db, teacher_id)
    if not teacher:
        return err('عضو هيئة التدريس غير موجود', 404)
    return ok({'teacher': teacher})


@bp.route('/<int:teacher_id>', methods=['PUT'])
@api_permission_required('teachers.manage')
@csrf_required
def api_teacher_update(teacher_id):
    db = get_db()
    t = teacher_service.get_teacher(db, teacher_id)
    if not t:
        return err('عضو هيئة التدريس غير موجود', 404)

    data = body()
    form, department_ids = _teacher_form(data)
    if not form['name']:
        return err('الاسم مطلوب', 422)

    teacher_service.update_teacher(db, teacher_id, form)
    db.execute('DELETE FROM teacher_departments WHERE teacher_id = ?', (teacher_id,))
    if department_ids:
        db.executemany(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
            [(teacher_id, did) for did in department_ids],
        )
    db.commit()
    log_history(db, 'update', 'teacher', teacher_id,
                f'تعديل بيانات عضو هيئة التدريس: {form["name"]}')
    return ok(True)


@bp.route('/<int:teacher_id>', methods=['DELETE'])
@api_permission_required('teachers.manage')
@csrf_required
def api_teacher_delete(teacher_id):
    db = get_db()
    if not teacher_service.get_teacher(db, teacher_id):
        return err('عضو هيئة التدريس غير موجود', 404)
    teacher_service.teacher_delete(
        db, teacher_id,
        lambda db: log_history(db, 'soft_delete', 'teacher', teacher_id, 'حذف عضو هيئة التدريس'),
    )
    return ok(True)


@bp.route('/<int:teacher_id>/restore', methods=['POST'])
@api_permission_required('teachers.manage')
@csrf_required
def api_teacher_restore(teacher_id):
    db = get_db()
    teacher_service.teacher_restore(db, teacher_id)
    return ok(True)


@bp.route('/<int:teacher_id>/permanent', methods=['DELETE'])
@api_permission_required('teachers.manage')
@csrf_required
def api_teacher_hard_delete(teacher_id):
    db = get_db()
    teacher_service.teacher_hard_delete(db, teacher_id)
    return ok(True)
