"""Rooms API."""

from __future__ import annotations

from flask import Blueprint

from api.helpers import (
    api_login_required,
    api_permission_required,
    body,
    err,
    log_history,
    ok,
    pagination,
)
from flask_db import get_db
from security import csrf_required
from services import classroom_service

bp = Blueprint('api_rooms', __name__, url_prefix='/api/rooms')


def _room_form(data, defaults=None):
    defaults = defaults or {}

    def fk(key, default=None):
        value = data.get(key, default)
        if value in (None, ''):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    department_id = data.get('department_id', defaults.get('department_id'))
    if department_id == '':
        department_id = None
    computers = data.get('computers', defaults.get('computers', 0))
    capacity_raw = data.get('capacity', defaults.get('capacity', 0))
    if capacity_raw in (None, ''):
        capacity_raw = 0
    try:
        capacity = int(capacity_raw)
    except (TypeError, ValueError):
        capacity = 0
    return {
        'name': (data.get('name') or '').strip(),
        'code': (data.get('code') or '').strip(),
        'capacity': capacity,
        'room_type_id': fk('room_type_id', defaults.get('room_type_id')),
        'status_id': fk('status_id', defaults.get('status_id', 1)),
        'floor_id': fk('floor_id', defaults.get('floor_id')),
        'building': (data.get('building') or '').strip(),
        'department_id': department_id,
        'computers': 1 if computers in (1, '1', True) else 0,
    }


MAX_ROOM_CAPACITY = 500


@bp.route('')
@api_permission_required('rooms.view')
def api_rooms_list():
    db = get_db()
    page, per_page, search = pagination()
    dept_filter = None
    rows, total, pg, pp, departments = classroom_service.list_rooms(
        db, search, dept_filter, page
    )
    return ok({
        'items': rows,
        'total': total,
        'page': pg,
        'per_page': pp,
        'departments': departments,
    })


@bp.route('', methods=['POST'])
@api_permission_required('rooms.manage')
@csrf_required
def api_room_create():
    data = body()
    form = _room_form(data)
    if not form['name']:
        return err('اسم القاعة مطلوب', 422)
    if form['capacity'] < 1:
        return err('سعة القاعة يجب أن تكون 1 أو أكثر.', 422)
    if form['capacity'] > MAX_ROOM_CAPACITY:
        return err(f'سعة القاعة يجب ألا تتجاوز {MAX_ROOM_CAPACITY}.', 422)
    db = get_db()
    room_id = classroom_service.create_room(db, form)
    log_history(db, 'create', 'room', room_id, f'إنشاء قاعة: {form["name"]}')
    return ok({'id': room_id}, status=201)


@bp.route('/<int:room_id>')
@api_login_required
@api_permission_required('rooms.view')
def api_room_detail(room_id):
    db = get_db()
    room = classroom_service.get_room_detail(db, room_id)
    if not room:
        return err('القاعة غير موجودة', 404)
    return ok({'room': room})


@bp.route('/<int:room_id>', methods=['PUT'])
@api_permission_required('rooms.manage')
@csrf_required
def api_room_update(room_id):
    db = get_db()
    r = classroom_service.get_room(db, room_id)
    if not r:
        return err('القاعة غير موجودة', 404)
    data = body()
    form = _room_form(data, defaults=dict(r))
    if not form['name']:
        return err('اسم القاعة مطلوب', 422)
    if form['capacity'] < 1:
        return err('سعة القاعة يجب أن تكون 1 أو أكثر.', 422)
    if form['capacity'] > MAX_ROOM_CAPACITY:
        return err(f'سعة القاعة يجب ألا تتجاوز {MAX_ROOM_CAPACITY}.', 422)
    classroom_service.update_room(db, room_id, form)
    log_history(db, 'update', 'room', room_id, f'تعديل قاعة: {form["name"]}')
    return ok(True)


@bp.route('/<int:room_id>', methods=['DELETE'])
@api_permission_required('rooms.manage')
@csrf_required
def api_room_delete(room_id):
    db = get_db()
    if not classroom_service.get_room(db, room_id):
        return err('القاعة غير موجودة', 404)
    classroom_service.room_delete(
        db, room_id,
        lambda db: log_history(db, 'soft_delete', 'room', room_id, 'حذف قاعة'),
    )
    return ok(True)


@bp.route('/<int:room_id>/restore', methods=['POST'])
@api_permission_required('rooms.manage')
@csrf_required
def api_room_restore(room_id):
    db = get_db()
    classroom_service.room_restore(db, room_id)
    return ok(True)


@bp.route('/<int:room_id>/permanent', methods=['DELETE'])
@api_permission_required('rooms.manage')
@csrf_required
def api_room_hard_delete(room_id):
    db = get_db()
    classroom_service.room_hard_delete(db, room_id)
    return ok(True)
