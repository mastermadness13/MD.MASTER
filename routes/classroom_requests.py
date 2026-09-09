from flask import (Blueprint, session, request, render_template,
                   redirect, url_for, flash, abort)

from flask_db import get_db
from security import csrf_required, login_required, permission_required
from security import current_user
from core.rate_limiter import RateLimiter
from services import classroom_request_service
from services.search import highlight_text
from utils.format import paginate
from utils.redirects import redirect_back

bp = Blueprint('classroom_requests', __name__, url_prefix='/classroom-requests')

_create_limiter = RateLimiter(max_requests=10, window_seconds=3600)


def _current_teacher(db):
    """Return the teachers row for the logged-in user (None if not a teacher)."""
    return db.execute(
        'SELECT id, user_id, department_id FROM teachers WHERE user_id = ?',
        (session['user_id'],),
    ).fetchone()


@bp.route('/')
@bp.route('/my-requests')
@login_required
@permission_required('classroom_requests.view')
def my_requests():
    db = get_db()
    requests = classroom_request_service.list_for_teacher(db, session['user_id'])
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    allowed_statuses = {'Pending', 'Approved', 'Rejected', 'Cancelled'}
    if status_filter and status_filter in allowed_statuses:
        requests = [r for r in requests if r['status'] == status_filter]
    if search:
        low = search.lower()
        requests = [r for r in requests if (
            low in (r.get('course_name') or '').lower()
            or low in (r.get('reason') or '').lower()
            or low in (r.get('current_room_name') or '').lower()
            or low in (r.get('requested_room_name') or '').lower()
        )]
    return render_template('classroom_requests/list_teacher.html',
                           requests=requests, search=search,
                           status_filter=status_filter if status_filter in allowed_statuses else '',
                           user=current_user())


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('classroom_requests.view')
@csrf_required
def create():
    db = get_db()
    teacher = _current_teacher(db)
    if not teacher:
        flash('لم يتم العثور على بيانات عضو هيئة التدريس', 'error')
        return redirect_back()

    schedule = classroom_request_service.list_teacher_schedule(db, session['user_id'])
    available_rooms = classroom_request_service.list_all_rooms(db)

    if request.method == 'POST':
        client_ip = request.remote_addr
        if _create_limiter.is_limited(client_ip):
            abort(429)
        _create_limiter.record(client_ip)
        form = {
            'schedule_id': request.form.get('schedule_id', type=int),
            'requested_room_id': request.form.get('requested_room_id', type=int),
            'reason': request.form.get('reason', '').strip(),
        }
        if not form['schedule_id'] or not form['requested_room_id'] or not form['reason']:
            return render_template('classroom_requests/create.html',
                                   schedule=schedule, available_rooms=available_rooms,
                                   form=form, form_error='يرجى تعبئة جميع الحقول المطلوبة',
                                   user=current_user())

        entry = db.execute(
            '''SELECT t.id, t.room_id, t.department_id, t.teacher_id
               FROM timetable t WHERE t.id = ? AND t.teacher_id = ?''',
            (form['schedule_id'], teacher['id']),
        ).fetchone()
        if not entry:
            return render_template('classroom_requests/create.html',
                                   schedule=schedule, available_rooms=available_rooms,
                                   form=form, form_error='المحاضرة المحددة غير موجودة في جدولك',
                                   user=current_user())
        if not entry['room_id']:
            return render_template('classroom_requests/create.html',
                                   schedule=schedule, available_rooms=available_rooms,
                                   form=form, form_error='المحاضرة المحددة لا تملك قاعة حالية',
                                   user=current_user())
        if not classroom_request_service.check_room_available(
                db, form['requested_room_id'], form['schedule_id']):
            return render_template('classroom_requests/create.html',
                                   schedule=schedule, available_rooms=available_rooms,
                                   form=form, form_error='القاعة المطلوبة محجوزة في نفس الموعد',
                                   user=current_user())

        classroom_request_service.create_request(
            db, teacher['id'], session['user_id'],
            entry['department_id'] or teacher['department_id'],
            form['schedule_id'], entry['room_id'],
            form['requested_room_id'], form['reason'],
        )
        flash('تم إرسال طلب تغيير القاعة', 'success')
        return redirect(url_for('classroom_requests.my_requests'))

    return render_template('classroom_requests/create.html',
                           schedule=schedule, available_rooms=available_rooms,
                           form={}, user=current_user())


@bp.route('/<int:request_id>/cancel', methods=['POST'])
@login_required
@permission_required('classroom_requests.view')
@csrf_required
def cancel(request_id):
    db = get_db()
    ok = classroom_request_service.cancel_request(db, request_id, session['user_id'])
    if ok:
        flash('تم إلغاء الطلب', 'success')
    else:
        flash('تعذر إلغاء الطلب — تأكد من أنه ما زال قيد المراجعة', 'error')
    return redirect(url_for('classroom_requests.my_requests'))


@bp.route('/pending')
@login_required
@permission_required('classroom_requests.manage')
def pending():
    db = get_db()
    dept_id = session.get('hod_department_id')
    if not dept_id:
        flash('لم يتم تحديد القسم الخاص بك', 'error')
        return redirect_back()

    status = request.args.get('status', 'Pending')
    allowed = {'Pending', 'Approved', 'Rejected'}
    if status not in allowed:
        status = 'Pending'
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int) or 1
    per_page = 20

    where = 'r.department_id = ? AND r.status = ?'
    params = [dept_id, status]
    if search:
        where += (' AND (tc.name LIKE ? OR c.name LIKE ? '
                  'OR r.reason LIKE ? OR rr.name LIKE ? OR cr.name LIKE ?)')
        like = f'%{search}%'
        params += [like, like, like, like, like]

    query = (
        f'''SELECT r.*, tc.name as teacher_name, c.name as course_name, t.day, t.period,
                   cr.name as current_room_name, rr.name as requested_room_name
            FROM classroom_change_requests r
            LEFT JOIN teachers tc ON r.teacher_id = tc.id
            LEFT JOIN timetable t ON r.schedule_id = t.id
            LEFT JOIN courses c ON t.course_id = c.id
            LEFT JOIN rooms cr ON r.current_classroom_id = cr.id
            LEFT JOIN rooms rr ON r.requested_classroom_id = rr.id
            WHERE {where}
            ORDER BY r.created_at DESC'''
    )
    rows, total, page, per_page = paginate(query, params, page, per_page)

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    context = dict(requests=rows, total=total, page=page, per_page=per_page,
                   search=search, current_filter=status,
                   highlight=highlight_text, user=current_user())
    if is_ajax:
        return render_template('classroom_requests/list_table.html', **context)
    return render_template('classroom_requests/list_hod.html', **context)


@bp.route('/<int:request_id>/review', methods=['POST'])
@login_required
@permission_required('classroom_requests.manage')
@csrf_required
def review(request_id):
    db = get_db()
    action = request.form.get('action', '')
    comment = request.form.get('hod_comment', '').strip()

    req = classroom_request_service.get_by_id(db, request_id)
    if not req:
        flash('الطلب غير موجود', 'error')
        return redirect(url_for('classroom_requests.pending'))
    if req.get('department_id') != session.get('hod_department_id'):
        flash('الطلب لا يتبع قسمك', 'error')
        return redirect(url_for('classroom_requests.pending'))
    if req.get('status') != 'Pending':
        flash('تمت معالجة هذا الطلب مسبقاً', 'error')
        return redirect(url_for('classroom_requests.pending'))

    if action == 'approve':
        classroom_request_service.approve_request(
            db, request_id, session['user_id'], comment)
        flash('تمت الموافقة على الطلب وتحديث قاعة المحاضرة', 'success')
    elif action == 'reject':
        classroom_request_service.reject_request(
            db, request_id, session['user_id'], comment)
        flash('تم رفض الطلب', 'success')
    else:
        flash('إجراء غير معروف', 'error')
    return redirect(url_for('classroom_requests.pending'))
