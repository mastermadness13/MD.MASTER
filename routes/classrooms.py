from flask import (Blueprint, session, request, render_template,
                   redirect, url_for, flash)
from utils.redirects import redirect_back

from flask_db import get_db
from database.history import add_history
from security import csrf_required, login_required, permission_required
from security import current_user, has_permission
from utils.format import paginate
from services import classroom_service
from services.search import build_room_search, highlight_text

bp = Blueprint('classrooms', __name__, url_prefix='/rooms')


def _full_room_list():
    query, params, _dept_filter = build_room_search('', '', 1)
    db = get_db()
    return [dict(r) for r in db.execute(query, params).fetchall()]


def normalize_room_name(name):
    name = (name or '').strip()
    if name.isdigit() and not name.startswith('قاعة'):
        return f'قاعة {name}'
    return name


@bp.route('', methods=['GET', 'POST'])
@login_required
@permission_required('rooms.view')
@csrf_required
def rooms_list():
    db = get_db()
    room_types, _statuses, _floors, _departments = classroom_service.get_create_lookups(db)
    search = request.args.get('search', '').strip()
    dept_filter = request.args.get('department_id', '')
    page = request.args.get('page', 1, type=int)
    create_error = None
    create_form = {}
    can_manage = has_permission(session.get('role', ''), 'rooms.manage', session.get('department_id'))

    if request.method == 'POST':
        if not has_permission(session.get('role', ''), 'rooms.manage', session.get('department_id')):
            flash('ليس لديك صلاحية لإنشاء القاعات', 'error')
            return redirect(url_for('classrooms.rooms_list'))
        name = normalize_room_name(request.form.get('name', ''))
        quantity = request.form.get('quantity', 1, type=int)
        capacity = request.form.get('capacity', 0, type=int)
        room_type_id = request.form.get('room_type_id') or None
        computers = 1 if request.form.get('computers') == '1' else 0
        create_form = {
            'name': request.form.get('name', ''),
            'quantity': quantity,
            'capacity': capacity,
            'room_type_id': room_type_id,
            'computers': computers,
        }
        if not name or quantity < 1:
            create_error = 'يرجى إدخال اسم القاعة وعدد صحيح من 1 أو أكثر.'
        elif capacity < 1:
            create_error = 'سعة القاعة يجب أن تكون 1 أو أكثر.'
        else:
            try:
                classroom_service.create_room(db, {
                    'name': name,
                    'code': request.form.get('code', '').strip(),
                    'capacity': capacity,
                    'room_type_id': room_type_id,
                    'status_id': request.form.get('status_id', 1, type=int),
                    'floor_id': None,
                    'building': '',
                    'department_id': None,
                    'computers': computers,
                    'quantity': quantity,
                })
                flash(f'تم إنشاء {quantity} قاعة بنجاح.', 'success')
                return redirect(url_for('classrooms.rooms_list'))
            except Exception as e:
                create_error = f'فشل إنشاء القاعات: {str(e)}'

    query, params, dept_filter = build_room_search(search, dept_filter, page)
    rows, total, page, per_page = paginate(query, params, page)

    departments = _departments

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return render_template('classrooms/list_table.html',
                              rooms=rows, total=total, page=page,
                              per_page=per_page, search=search,
                              department_id=dept_filter,
                              departments=departments, user=current_user(),
                              can_manage=can_manage,
                              highlight=highlight_text)

    return render_template('classrooms/list.html', rooms=rows, total=total, page=page,
                          per_page=per_page, search=search, department_id=dept_filter,
                          departments=departments,
                          room_types=room_types,
                          user=current_user(), can_manage=can_manage,
                          create_error=create_error, create_form=create_form,
                          highlight=highlight_text, print_rooms=_full_room_list())


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('rooms.manage')
@csrf_required
def rooms_create():
    db = get_db()
    room_types, _statuses, _floors, _departments = classroom_service.get_create_lookups(db)
    create_error = None
    form = {}
    if request.method == 'POST':
        name = normalize_room_name(request.form.get('name', ''))
        quantity = request.form.get('quantity', 1, type=int)
        capacity = request.form.get('capacity', 0, type=int)
        computers = 1 if request.form.get('computers') == '1' else 0
        form = {
            'name': request.form.get('name', ''),
            'quantity': quantity,
            'capacity': request.form.get('capacity', 0, type=int),
            'room_type_id': request.form.get('room_type_id') or None,
            'status_id': request.form.get('status_id', 1, type=int),
            'floor_id': None,
            'building': '',
            'department_id': None,
            'computers': computers,
        }
        if not name or quantity < 1:
            create_error = 'يرجى إدخال اسم القاعة وعدد صحيح من 1 أو أكثر.'
        elif capacity < 1:
            create_error = 'سعة القاعة يجب أن تكون 1 أو أكثر.'
        else:
            try:
                classroom_service.create_room(db, {
                    'name': name,
                    'code': request.form.get('code', '').strip(),
                    'capacity': form['capacity'],
                    'room_type_id': form['room_type_id'],
                    'status_id': form['status_id'],
                    'floor_id': None,
                    'building': '',
                    'department_id': None,
                    'computers': form['computers'],
                    'quantity': quantity,
                })
            except ValueError as exc:
                create_error = str(exc)
            else:
                flash(f'تم إنشاء {quantity} قاعة بنجاح.', 'success')
                return redirect(url_for('classrooms.rooms_list'))
    return render_template('classrooms/create.html', room_types=room_types,
                          form=form,
                          create_error=create_error,
                          user=current_user())


@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('rooms.manage')
@csrf_required
def rooms_edit(id):
    db = get_db()
    r = classroom_service.get_room(db, id)
    if not r:
        flash('القاعة غير موجودة', 'error')
        return redirect(url_for('classrooms.rooms_list'))
    room_types, statuses, floors, departments = classroom_service.get_create_lookups(db)
    if request.method == 'POST':
        name = normalize_room_name(request.form.get('name', ''))
        department_id = request.form.get('department_id', r['department_id'])
        if department_id == '':
            department_id = None
        room_type_id = request.form.get('room_type_id', r['room_type_id']) or None
        floor_id = request.form.get('floor_id', r['floor_id']) or None
        computers = 1 if request.form.get('computers') == '1' else 0
        form = {
            'id': r['id'],
            'name': name,
            'code': request.form.get('code', '').strip(),
            'capacity': request.form.get('capacity', 0, type=int),
            'room_type_id': room_type_id,
            'status_id': request.form.get('status_id', 1, type=int),
            'floor_id': floor_id,
            'building': '',
            'department_id': department_id,
            'computers': computers,
        }
        if not name:
            return render_template('classrooms/edit.html', room=form, room_types=room_types,
                                  statuses=statuses, floors=floors, departments=departments,
                                  user=current_user())
        classroom_service.update_room(db, id, form)
        flash('تم تحديث القاعة', 'success')
        return redirect(url_for('classrooms.rooms_list'))
    return render_template('classrooms/edit.html', room=dict(r), room_types=room_types,
                          statuses=statuses, floors=floors, departments=departments,
                          user=current_user())


@bp.route('/<int:id>')
@login_required
@permission_required('rooms.manage')
def room_detail(id):
    db = get_db()
    r = classroom_service.get_room_detail(db, id)
    if not r:
        flash('القاعة غير موجودة', 'error')
        return redirect(url_for('classrooms.rooms_list'))
    return render_template('classrooms/detail.html', room=r,
                          user=current_user())


@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('rooms.manage')
@csrf_required
def rooms_delete(id):
    db = get_db()
    classroom_service.room_delete(db, id, lambda db: add_history(
        db, 'soft_delete', 'room', id, session['user_id'], session['username'], f'حذف قاعة'))
    flash('تم نقل القاعة إلى الأرشيف', 'success')
    return redirect_back('classrooms.rooms_list')


@bp.route('/bulk-delete', methods=['POST'])
@login_required
@permission_required('rooms.manage')
@csrf_required
def rooms_bulk_delete():
    ids = request.form.getlist('room_ids')
    ids = [i for i in ids if i.isdigit()]
    if not ids:
        flash('لم يتم تحديد أي قاعة للحذف', 'error')
        return redirect_back('classrooms.rooms_list')
    db = get_db()
    for rid in ids:
        classroom_service.room_delete(db, int(rid), lambda db, rid=rid: add_history(
            db, 'soft_delete', 'room', int(rid), session['user_id'], session['username'], 'حذف قاعة'))
    flash(f'تم نقل {len(ids)} قاعة إلى الأرشيف', 'success')
    return redirect_back('classrooms.rooms_list')


@bp.route('/restore/<int:id>', methods=['POST'])
@login_required
@permission_required('rooms.manage')
@csrf_required
def rooms_restore(id):
    db = get_db()
    classroom_service.room_restore(db, id)
    flash('تم استعادة القاعة', 'success')
    return redirect_back('classrooms.rooms_list')


@bp.route('/delete-permanent/<int:id>', methods=['POST'])
@login_required
@permission_required('rooms.manage')
@csrf_required
def rooms_delete_permanent(id):
    db = get_db()
    classroom_service.room_hard_delete(db, id)
    flash('تم حذف القاعة نهائياً', 'success')
    return redirect_back('classrooms.rooms_list')


@bp.route('/bulk-delete-permanent', methods=['POST'])
@login_required
@permission_required('rooms.manage')
@csrf_required
def rooms_bulk_permanent_delete():
    ids = [i for part in request.form.getlist('room_ids') for i in part.split(',') if i.strip().isdigit()]
    if not ids:
        flash('لم يتم تحديد أي قاعة', 'error')
        return redirect_back('classrooms.rooms_list')
    db = get_db()
    for rid in ids:
        classroom_service.room_hard_delete(db, int(rid))
    flash(f'تم حذف {len(ids)} قاعة نهائياً', 'success')
    return redirect_back('classrooms.rooms_list')

