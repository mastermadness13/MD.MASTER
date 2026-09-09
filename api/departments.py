"""Departments API."""

from __future__ import annotations

from flask import Blueprint

from api.helpers import (
    api_permission_required,
    body,
    err,
    log_history,
    ok,
)
from database.repositories.department_repository import DepartmentRepository
from flask_db import get_db
from security import csrf_required
from services import department_service

bp = Blueprint('api_departments', __name__, url_prefix='/api/departments')


@bp.route('')
@api_permission_required('departments.view')
def api_departments_list():
    db = get_db()
    return ok({'items': department_service.list_departments(db)})


@bp.route('', methods=['POST'])
@api_permission_required('departments.manage')
@csrf_required
def api_department_create():
    data = body()
    name = (data.get('name') or '').strip()
    semesters = data.get('semesters', 1)
    majors = data.get('majors', 7)
    try:
        semesters = int(semesters)
        majors = int(majors)
    except (TypeError, ValueError):
        return err('قيم الفصول والأقسام يجب أن تكون أرقاماً', 422)
    if not name:
        return err('اسم القسم مطلوب', 422)
    if len(name) > 255:
        return err('اسم القسم أطول من المسموح (255 حرفاً كحد أقصى)', 422)
    db = get_db()
    if department_service.department_exists_by_name(db, name):
        return err('القسم موجود مسبقاً', 409)
    dept_id = department_service.create_department(db, name, semesters, majors)
    log_history(db, 'create', 'department', dept_id, f'إنشاء قسم: {name}')
    return ok({'id': dept_id}, status=201)


@bp.route('/<int:dept_id>')
@api_permission_required('departments.view')
def api_department_detail(dept_id):
    db = get_db()
    dept = department_service.get_department(db, dept_id)
    if not dept:
        return err('القسم غير موجود', 404)
    majors = DepartmentRepository(db).get_majors(dept_id)
    return ok({'department': dept, 'majors': majors})


@bp.route('/<int:dept_id>', methods=['PUT'])
@api_permission_required('departments.manage')
@csrf_required
def api_department_update(dept_id):
    db = get_db()
    d = department_service.get_department(db, dept_id)
    if not d:
        return err('القسم غير موجود', 404)
    data = body()
    name = (data.get('name') or '').strip()
    semesters = data.get('semesters', d['semesters'])
    majors = data.get('majors', d['majors'])
    try:
        semesters = int(semesters)
        majors = int(majors)
    except (TypeError, ValueError):
        return err('قيم الفصول والأقسام يجب أن تكون أرقاماً', 422)
    if not name:
        return err('اسم القسم مطلوب', 422)
    if len(name) > 255:
        return err('اسم القسم أطول من المسموح (255 حرفاً كحد أقصى)', 422)
    department_service.update_department(db, dept_id, name, semesters, majors)
    log_history(db, 'update', 'department', dept_id, f'تعديل قسم: {name}')
    return ok(True)


@bp.route('/<int:dept_id>', methods=['DELETE'])
@api_permission_required('departments.manage')
@csrf_required
def api_department_delete(dept_id):
    db = get_db()
    if not department_service.get_department(db, dept_id):
        return err('القسم غير موجود', 404)
    department_service.department_delete(
        db, dept_id,
        lambda db: log_history(db, 'soft_delete', 'department', dept_id, 'حذف قسم'),
    )
    return ok(True)


@bp.route('/<int:dept_id>/restore', methods=['POST'])
@api_permission_required('departments.manage')
@csrf_required
def api_department_restore(dept_id):
    db = get_db()
    department_service.department_restore(db, dept_id)
    return ok(True)


@bp.route('/<int:dept_id>/permanent', methods=['DELETE'])
@api_permission_required('departments.manage')
@csrf_required
def api_department_hard_delete(dept_id):
    db = get_db()
    department_service.department_hard_delete(db, dept_id)
    return ok(True)


@bp.route('/<int:dept_id>/majors', methods=['POST'])
@api_permission_required('departments.manage')
@csrf_required
def api_department_add_major(dept_id):
    db = get_db()
    name = (body().get('name') or '').strip()
    if not name:
        return err('اسم الشعبة مطلوب', 422)
    department_service.add_major(db, dept_id, name)
    return ok(True, status=201)


@bp.route('/<int:dept_id>/majors/<int:major_id>', methods=['DELETE'])
@api_permission_required('departments.manage')
@csrf_required
def api_department_delete_major(dept_id, major_id):
    db = get_db()
    department_service.delete_major(db, major_id, dept_id)
    return ok(True)
