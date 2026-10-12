"""Rooms management pages — «القاعات».

Two routes render this one page: ``/rooms`` (the canonical entry, the print
surface and the POST target of the create form) and ``/exams/rooms`` (the same
page inside the Exams section).  The body therefore lives in
``render_rooms_page`` instead of in a view, so the two can never drift.

Every write declares its **own** permission (rooms.create / rooms.edit /
rooms.delete) rather than one coarse rooms.manage, so an account can hold
exactly one of them.
"""

from flask import (Blueprint, session, request, render_template,
                   redirect, url_for, flash)
from utils.redirects import redirect_back

from database.flask_db import get_db
from database.history import add_history
from security import csrf_required, login_required, permission_required
from security import current_user, has_permission
from security.authorization import get_active_roles
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


def _can_manage_rooms() -> bool:
    """May this visitor add / edit / delete rooms (any of the three doors)?

    ``rooms.manage`` is the coarse name and it expands to the three granular
    ones, so asking for it here is exactly "holds a rooms write" — and it is
    still answered by ``has_permission``, so a read-only assignment hides the
    buttons.
    """
    return has_permission(get_active_roles(), 'rooms.manage',
                          session.get('department_id'))


def render_rooms_page(active_nav_key='rooms', create_error=None, create_form=None):
    """The rooms page, shared by ``/rooms`` and ``/exams/rooms``.

    *active_nav_key* names the navigation entry the page belongs to.  The
    templates read it under that name because their own top-level
    ``{% set sidebar_active %}`` would shadow a context variable of the same
    name — that shadowing is why the two are deliberately different.
    """
    db = get_db()
    room_types, _statuses, _floors, departments = classroom_service.get_create_lookups(db)
    search = request.args.get('search', '').strip()
    dept_filter = request.args.get('department_id', '')
    page = request.args.get('page', 1, type=int)
    can_manage = _can_manage_rooms()

    query, params, dept_filter = build_room_search(search, dept_filter, page)
    rows, total, page, per_page = paginate(query, params, page)
    # /     /     >---- عدّاد الاستخدام للصفحة كلها بثلاثة استعلامات مُجمّعة
    usage = classroom_service.rooms_usage(db, [r['id'] for r in rows])

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return render_template('classrooms/list_table.html',
                               rooms=rows, total=total, page=page,
                               per_page=per_page, search=search,
                               department_id=dept_filter,
                               departments=departments, user=current_user(),
                               can_manage=can_manage,
                               usage=usage,
                               highlight=highlight_text)

    return render_template('classrooms/list.html', rooms=rows, total=total, page=page,
                           per_page=per_page, search=search, department_id=dept_filter,
                           departments=departments,
                           room_types=room_types,
                           user=current_user(), can_manage=can_manage,
                           active_nav_key=active_nav_key,
                           section_tab='rooms',
                           usage=usage,
                           create_error=create_error, create_form=create_form or {},
                           highlight=highlight_text, print_rooms=_full_room_list())


@bp.route('', methods=['GET', 'POST'])
@login_required
@permission_required('rooms.view')
@csrf_required
def rooms_list():
    # /     /     >---- مسار واحد يجمع القراءة (rooms.view على الديكوريتور)
    # /     /     >---- مع الإنشاء (rooms.create على فرع POST)، لأن نموذج
    # /     /     >---- الإنشاء معروض داخل الصفحة نفسها.
    create_error = None
    create_form = {}
    if request.method == 'POST':
        if not has_permission(get_active_roles(), 'rooms.create',
                              session.get('department_id')):
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
                classroom_service.create_room(get_db(), {
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
    return render_rooms_page('rooms', create_error=create_error,
                            create_form=create_form)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('rooms.create')
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
            'capacity': capacity,
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
                    'computers': computers,
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
@permission_required('rooms.edit')
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
@permission_required('rooms.view')
def room_detail(id):
    db = get_db()
    r = classroom_service.get_room_detail(db, id)
    if not r:
        flash('القاعة غير موجودة', 'error')
        return redirect(url_for('classrooms.rooms_list'))
    return render_template('classrooms/detail.html', room=r,
                          user=current_user(),
                          usage=classroom_service.room_usage(db, id),
                          can_manage=_can_manage_rooms())


# /     /     >---- الحذف الناعم مسموح لقاعة مستخدمة، لكنه لا ينزل إلا بتأكيد:
# /     /     >---- النموذج يعيد إرسال confirm_usage=1 بعد قراءة الأعداد.
def _usage_confirmed() -> bool:
    return request.form.get('confirm_usage') == '1'


def _refuse_soft_delete(counts):
    flash('تعذّر الحذف — ' + classroom_service.usage_summary(counts)
          + '. أكّد الحذف في النافذة لتأكيده.', 'error')
    return redirect_back('classrooms.rooms_list')


@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('rooms.delete')
@csrf_required
def rooms_delete(id):
    db = get_db()
    counts = classroom_service.room_usage(db, id)
    if counts['total'] and not _usage_confirmed():
        return _refuse_soft_delete(counts)
    classroom_service.room_delete(db, id, lambda db: add_history(
        db, 'soft_delete', 'room', id, session['user_id'], session['username'], f'حذف قاعة'))
    flash('تم الحذف بنجاح', 'success')
    return redirect_back('classrooms.rooms_list')


@bp.route('/bulk-delete', methods=['POST'])
@login_required
@permission_required('rooms.delete')
@csrf_required
def rooms_bulk_delete():
    ids = request.form.getlist('room_ids')
    ids = [i for i in ids if i.isdigit()]
    if not ids:
        flash('لم يتم تحديد أي قاعة للحذف', 'error')
        return redirect_back('classrooms.rooms_list')
    db = get_db()
    usage = classroom_service.rooms_usage(db, ids)
    if not _usage_confirmed():
        # /     /     >---- نرفض الدفعة كلها إن مرّرت قاعة واحدة مرتبطة، حتى
        # /     /     >---- لا يُحذف نصفُ تحديدٍ ويترك الباقي بلا سبب.
        blocked = [counts for counts in usage.values() if counts['total']]
        if blocked:
            return _refuse_soft_delete(blocked[0])
    for rid in ids:
        classroom_service.room_delete(db, int(rid), lambda db, rid=rid: add_history(
            db, 'soft_delete', 'room', int(rid), session['user_id'], session['username'], 'حذف قاعة'))
    flash(f'تم الحذف بنجاح', 'success')
    return redirect_back('classrooms.rooms_list')


@bp.route('/restore/<int:id>', methods=['POST'])
@login_required
@permission_required('rooms.delete')
@csrf_required
def rooms_restore(id):
    db = get_db()
    classroom_service.room_restore(db, id)
    flash('تم استعادة القاعة', 'success')
    return redirect_back('classrooms.rooms_list')


# /     /     >---- الحذف النهائي ممنوع ما دامت القاعة مرتبطة: حذف الصف نفسه
# /     /     >---- يترك exam_schedule يتيماً ويفرغ exam.hall بصمت، لأن
# /     /     >---- خدمات الحذف لا تفحص مراجع ولا تف تفعيل مفاتيح SQLite.
def _refuse_hard_delete(counts):
    flash('لا يمكن الحذف النهائي — ' + classroom_service.usage_summary(counts)
          + '. انقل القاعات إلى قاعة أخرى أولاً.', 'error')
    return redirect_back('classrooms.rooms_list')


@bp.route('/delete-permanent/<int:id>', methods=['POST'])
@login_required
@permission_required('rooms.delete')
@csrf_required
def rooms_delete_permanent(id):
    db = get_db()
    counts = classroom_service.room_usage(db, id)
    if counts['total']:
        return _refuse_hard_delete(counts)
    classroom_service.room_hard_delete(db, id)
    flash('تم حذف القاعة نهائياً', 'success')
    return redirect_back('classrooms.rooms_list')


@bp.route('/bulk-delete-permanent', methods=['POST'])
@login_required
@permission_required('rooms.delete')
@csrf_required
def rooms_bulk_permanent_delete():
    ids = [i for part in request.form.getlist('room_ids') for i in part.split(',') if i.strip().isdigit()]
    if not ids:
        flash('لم يتم تحديد أي قاعة', 'error')
        return redirect_back('classrooms.rooms_list')
    db = get_db()
    usage = classroom_service.rooms_usage(db, ids)
    blocked = [counts for counts in usage.values() if counts['total']]
    if blocked:
        flash('لا يمكن الحذف النهائي — '
              + ' '.join(classroom_service.usage_summary(c) for c in blocked)
              + '. انقل القاعات إلى قاعة أخرى أولاً.', 'error')
        return redirect_back('classrooms.rooms_list')
    for rid in ids:
        classroom_service.room_hard_delete(db, int(rid))
    flash(f'تم حذف {len(ids)} قاعة نهائياً', 'success')
    return redirect_back('classrooms.rooms_list')