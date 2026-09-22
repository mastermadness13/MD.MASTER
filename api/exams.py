"""Exams API — the single exam workspace data source.

The `/exams` page is a client-rendered workspace: every tab (schedule, period,
planning, department schedule, settings) reads from and mutates this API.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, request, session

from api.helpers import (
    api_permission_required,
    body,
    err,
    ok,
)
from core.validators import integer_between, valid_date_range, valid_time
from flask_db import get_db
from security import csrf_required
from security import current_user
from services import exam_service, notification_service

bp = Blueprint('api_exams', __name__, url_prefix='/api/exams')


def _dept_exam_data_for_user(db):
    role = session.get('role', '')
    user_data = current_user()
    if role == 'exam':
        return exam_service.build_dept_exam_data(db)
    user_dept_id = user_data.get('department_id') if user_data else None
    if not user_dept_id:
        return []
    return exam_service.build_dept_exam_data(db, filter_dept_id=user_dept_id)


def _notify_all(db, title, message, link, level):
    uids = list(set(
        notification_service.get_all_teacher_user_ids(db)
        + notification_service.get_hod_user_ids(db)
    ))
    if uids:
        notification_service.notify_multiple(
            db, uids, title, message, 'exams', link, level
        )


@bp.route('')
@api_permission_required('exams.view')
def api_exams():
    db = get_db()
    return ok({'departments': _dept_exam_data_for_user(db)})


@bp.route('/schedule')
@api_permission_required('exams.view')
def api_exam_schedule():
    db = get_db()
    departments = _dept_exam_data_for_user(db)
    dept_stats = {}
    for dept in departments:
        did = dept['id']
        total = 0
        rooms = set()
        for slot in dept.get('time_slots', []):
            for cell in slot.get('cells', {}).values():
                if cell:
                    total += 1
                    if cell.get('room_name'):
                        rooms.add(cell['room_name'])
        dept_stats[did] = {'exam_count': total, 'room_count': len(rooms)}
    return ok(exam_service.build_exam_schedule_view(db, departments, dept_stats))


@bp.route('/planning')
@api_permission_required('exams.planning')
def api_exam_planning_data():
    return ok(exam_service.get_planning_data(get_db()))


@bp.route('/department-schedule')
@api_permission_required('exams.department_schedule')
def api_exam_department_schedule():
    db = get_db()
    role = session.get('role', '')
    user_data = current_user()
    user_dept_id = user_data.get('department_id') if user_data else None

    if role == 'exam':
        departments = [dict(r) for r in db.execute(
            'SELECT id, name, semesters FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]
    elif role == 'head_of_department' and user_dept_id:
        departments = [dict(r) for r in db.execute(
            'SELECT id, name, semesters FROM departments WHERE id = ? AND hidden = 0 AND deleted_at IS NULL',
            (user_dept_id,)
        ).fetchall()]
    else:
        departments = []

    selected_dept = request.args.get('dept_id', type=int)
    selected_sem = request.args.get('semester', type=int)

    courses = []
    assignments = {}
    exam_days = []
    dept_semesters = 1

    if selected_dept:
        dept = db.execute('SELECT semesters FROM departments WHERE id = ?', (selected_dept,)).fetchone()
        dept_semesters = dept['semesters'] if dept else 1

        period = exam_service.get_exam_period(db)
        if period.get('exam_start_date') and period.get('exam_end_date'):
            try:
                start = datetime.strptime(period['exam_start_date'], '%Y-%m-%d')
                end = datetime.strptime(period['exam_end_date'], '%Y-%m-%d')
            except (ValueError, TypeError):
                start = end = None
            if start and end:
                arabic_days = {5: 'السبت', 6: 'الأحد', 0: 'الإثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس'}
                arabic_months = {'01': 'يناير', '02': 'فبراير', '03': 'مارس', '04': 'أبريل',
                                 '05': 'مايو', '06': 'يونيو', '07': 'يوليو', '08': 'أغسطس',
                                 '09': 'سبتمبر', '10': 'أكتوبر', '11': 'نوفمبر', '12': 'ديسمبر'}
                cur = start
                while cur <= end:
                    wd = cur.weekday()
                    if wd in arabic_days:
                        month_ar = arabic_months.get(cur.strftime('%m'), '')
                        exam_days.append({
                            'date': cur.strftime('%Y-%m-%d'),
                            'day_ar': arabic_days[wd],
                            'display': f"{cur.day} {month_ar}",
                        })
                    cur += timedelta(days=1)

        if selected_sem:
            courses = exam_service.get_department_courses(db, selected_dept, selected_sem)
            assignments_raw = exam_service.get_department_exam_assignments(db, selected_dept, selected_sem)
            assignments = {a['course_id']: a for a in assignments_raw}

    return ok({
        'departments': departments,
        'selected_dept': selected_dept,
        'selected_sem': selected_sem,
        'dept_semesters': dept_semesters,
        'courses': courses,
        'assignments': assignments,
        'exam_days': exam_days,
    })


@bp.route('/department-schedule/cell-options')
@api_permission_required('exams.department_schedule')
def api_exam_department_cell_options():
    db = get_db()
    role = session.get('role', '')
    user_data = current_user()
    user_dept_id = user_data.get('department_id') if user_data else None

    dept_id = request.args.get('dept_id', type=int)
    semester = request.args.get('semester', type=int)
    if not dept_id or not semester:
        return err('بيانات غير صالحة', 422)
    if role == 'head_of_department' and dept_id != user_dept_id:
        return err('لا يمكنك تعديل جدول قسم آخر', 403)

    courses = exam_service.get_department_courses(db, dept_id, semester)
    rooms = exam_service.get_exam_rooms(db)
    return ok({'courses': courses, 'rooms': rooms})


@bp.route('/department-schedule/cell', methods=['POST'])
@api_permission_required('exams.department_schedule')
@csrf_required
def api_exam_department_cell_save():
    data = body()
    db = get_db()
    role = session.get('role', '')
    user_data = current_user()
    user_dept_id = user_data.get('department_id') if user_data else None

    def fk(key):
        value = data.get(key)
        try:
            return int(value) if value not in (None, '') else None
        except (TypeError, ValueError):
            return None

    dept_id = fk('dept_id')
    semester = fk('semester')
    week = fk('week')
    day = (data.get('day') or '').strip()
    course_id = fk('course_id')
    room_id = fk('room_id')
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()
    exam_type = (data.get('exam_type') or '').strip() or 'written'
    schedule_id = fk('schedule_id')

    if not dept_id or not semester or not week or not course_id:
        return err('بيانات غير صالحة', 422)
    if role == 'head_of_department' and dept_id != user_dept_id:
        return err('لا يمكنك تعديل جدول قسم آخر', 403)
    if week < 1 or week > 5:
        return err('رقم الأسبوع غير صالح (1-5)', 422)
    if day not in ('السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس'):
        return err('اليوم غير صالح', 422)
    if not start_time or not end_time:
        return err('يرجى تحديد وقت البداية والنهاية', 422)
    if start_time >= end_time:
        return err('وقت النهاية يجب أن يكون بعد وقت البداية', 422)
    if exam_type not in ('written', 'practical', 'lab', 'field'):
        return err('نوع الامتحان غير صالح', 422)

    course = db.execute('SELECT id FROM courses WHERE id = ? AND deleted_at IS NULL', (course_id,)).fetchone()
    if not course:
        return err('المادة غير موجودة', 404)
    if room_id:
        room = db.execute('SELECT id FROM rooms WHERE id = ? AND deleted_at IS NULL', (room_id,)).fetchone()
        if not room:
            return err('القاعة غير موجودة', 404)

    exam_date = exam_service.resolve_exam_date(db, week, day) or ''

    conflicts = exam_service.check_cell_conflicts(
        db, dept_id, semester, week, day, room_id, start_time, end_time, exclude_id=schedule_id,
    )
    if conflicts:
        return ok({'has_conflicts': True, 'conflicts': conflicts})

    try:
        schedule_id = exam_service.save_cell_exam(
            db, dept_id, semester, week, day, exam_date, course_id, room_id,
            start_time, end_time, exam_type, session.get('user_id'), schedule_id,
        )
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 400)
    return ok({'saved': True, 'exam_date': exam_date, 'id': schedule_id})


@bp.route('/department-schedule/cell/<int:schedule_id>/room', methods=['PATCH'])
@api_permission_required('exams.assign_room')
@csrf_required
def api_exam_department_cell_room(schedule_id):
    """Room-only update used by the Exam Department role."""
    data = body()
    db = get_db()
    role = session.get('role', '')
    if role == 'head_of_department':
        return err('لا يمكنك استخدام هذا الإجراء', 403)

    room_id = data.get('room_id')
    try:
        room_id = int(room_id) if room_id not in (None, '') else None
    except (TypeError, ValueError):
        return err('معرف القاعة غير صالح', 422)
    if room_id:
        room = db.execute('SELECT id FROM rooms WHERE id = ? AND deleted_at IS NULL', (room_id,)).fetchone()
        if not room:
            return err('القاعة غير موجودة', 404)

    row = db.execute('SELECT id, department_id FROM exam_schedule WHERE id = ?', (schedule_id,)).fetchone()
    if not row:
        return err('الامتحان غير موجود', 404)

    try:
        result = exam_service.update_exam_room(db, schedule_id, room_id)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 400)
    return ok({'updated': True, 'room_id': result['room_id'], 'room_name': result['room_name']})


@bp.route('/department-schedule/cell/<int:schedule_id>', methods=['DELETE'])
@api_permission_required('exams.department_schedule')
@csrf_required
def api_exam_department_cell_delete(schedule_id):
    db = get_db()
    role = session.get('role', '')
    user_data = current_user()
    user_dept_id = user_data.get('department_id') if user_data else None
    row = db.execute(
        'SELECT department_id FROM exam_schedule WHERE id = ?', (schedule_id,)
    ).fetchone()
    if not row:
        return err('الامتحان غير موجود', 404)
    if role == 'head_of_department' and row['department_id'] != user_dept_id:
        return err('لا يمكنك تعديل جدول قسم آخر', 403)
    try:
        exam_service.delete_cell_exam(db, schedule_id, row['department_id'])
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 400)
    return ok({'deleted': True})


@bp.route('/department-schedule/send', methods=['POST'])
@api_permission_required('exams.department_schedule')
@csrf_required
def api_exam_department_schedule_send():
    data = body()
    try:
        dept_id = int(data.get('dept_id')) if data.get('dept_id') else None
    except (TypeError, ValueError):
        return err('معرف القسم غير صالح', 422)
    if not dept_id:
        return err('يرجى اختيار القسم أولاً', 422)

    db = get_db()
    role = session.get('role', '')
    user_data = current_user()
    if role == 'head_of_department':
        if dept_id != (user_data.get('department_id') if user_data else None):
            return err('لا يمكنك إرسال جدول قسم آخر', 403)

    dept = db.execute('SELECT name, semesters FROM departments WHERE id = ?', (dept_id,)).fetchone()
    dept_name = dept['name'] if dept else f'#{dept_id}'
    semesters = int(dept['semesters']) if dept and dept['semesters'] else 1

    assigned_count = 0
    for sem in range(1, semesters + 1):
        for a in exam_service.get_department_exam_assignments(db, dept_id, sem):
            if a.get('exam_date'):
                assigned_count += 1

    uids = notification_service.get_exam_user_ids(db)
    if uids:
        notification_service.notify_multiple(
            db, uids,
            'إرسال جدول الامتحانات',
            f'قام رئيس {dept_name} بإرسال جدول الامتحانات ({assigned_count} مادة بموعد محدد) للمراجعة في جدول القسم',
            'exams', 'exam_dept_send', dept_id,
        )
    return ok({'sent_to': len(uids), 'assigned_count': assigned_count})


@bp.route('/department-schedule/send-exam', methods=['POST'])
@api_permission_required('exams.department_schedule')
@csrf_required
def api_exam_department_schedule_send_exam():
    data = body()
    try:
        schedule_id = int(data.get('schedule_id')) if data.get('schedule_id') else None
    except (TypeError, ValueError):
        return err('معرف الامتحان غير صالح', 422)
    if not schedule_id:
        return err('يرجى تحديد الامتحان أولاً', 422)

    db = get_db()
    role = session.get('role', '')
    user_data = current_user()
    row = db.execute(
        '''SELECT es.*, c.name as course_name, c.code as course_code,
                  d.name as dept_name, r.name as room_name
           FROM exam_schedule es
           JOIN courses c ON es.course_id = c.id
           JOIN departments d ON es.department_id = d.id
           LEFT JOIN rooms r ON es.room_id = r.id
           WHERE es.id = ?''',
        (schedule_id,),
    ).fetchone()
    if not row:
        return err('الامتحان غير موجود', 404)
    exam = dict(row)

    if role == 'head_of_department':
        if exam['department_id'] != (user_data.get('department_id') if user_data else None):
            return err('لا يمكنك إرسال امتحان من قسم آخر', 403)

    uids = notification_service.get_exam_user_ids(db)
    if uids:
        message = (
            f"قام رئيس {exam['dept_name']} بإرسال امتحان المادة "
            f"«{exam['course_name']}» ({exam['course_code'] or 'بدون رمز'})"
            + (f" بتاريخ {exam['exam_date']}" if exam.get('exam_date') else '')
            + ' للمراجعة في جدول القسم'
        )
        notification_service.notify_multiple(
            db, uids, 'إرسال امتحان للمراجعة', message, 'exams', 'exam_dept_send', exam['id'],
        )
    return ok({'sent_to': len(uids), 'schedule_id': schedule_id})


@bp.route('/planning/suggest', methods=['POST'])
@api_permission_required('exams.planning')
@csrf_required
def api_exam_planning_suggest():
    db = get_db()
    suggestions = exam_service.suggest_distribution(db)
    return ok({'suggestions': suggestions, 'count': len(suggestions)})


@bp.route('/planning/apply-suggestions', methods=['POST'])
@api_permission_required('exams.planning')
@csrf_required
def api_exam_planning_apply():
    db = get_db()
    data = body()
    suggestions = data.get('suggestions') or []
    applied = 0
    for s in suggestions:
        schedule_id = s.get('schedule_id')
        room_id = s.get('room_id')
        if schedule_id and room_id:
            exam_service.assign_exam_resources(db, schedule_id, room_id, '', '')
            applied += 1
    return ok({'applied': applied})


@bp.route('/settings')
@api_permission_required('exams.manage')
def api_exam_settings():
    db = get_db()
    settings, halls, total_days = exam_service.get_exam_settings(db)
    return ok({'settings': settings, 'halls': halls, 'total_days': total_days})


@bp.route('/settings', methods=['PUT'])
@api_permission_required('exams.manage')
@csrf_required
def api_exam_settings_save():
    data = body()
    payload = {
        'exam_start_date': (data.get('exam_start_date') or '').strip(),
        'exam_end_date': (data.get('exam_end_date') or '').strip(),
        'session_a': data.get('session_a', '08:30'),
        'session_b': data.get('session_b', '11:30'),
        'session_c': data.get('session_c', '14:30'),
        'proctors_per_room': data.get('proctors_per_room', 2),
        'avoid_relatives': 1 if data.get('avoid_relatives') else 0,
        'auto_notify': 1 if data.get('auto_notify') else 0,
    }
    errors = [
        e for e in (
            valid_time(payload['session_a'], 'الجلسة الأولى'),
            valid_time(payload['session_b'], 'الجلسة الثانية'),
            valid_time(payload['session_c'], 'الجلسة الثالثة'),
            integer_between(payload['proctors_per_room'], 1, 10, 'عدد المراقبين لكل قاعة'),
            valid_date_range(payload['exam_start_date'], payload['exam_end_date'],
                             'تاريخ بداية الامتحانات', 'تاريخ نهاية الامتحانات'),
        ) if e
    ]
    if errors:
        return err('بيانات غير صحيحة', 422, errors=errors)
    db = get_db()
    exam_service.save_exam_settings(db, payload)
    return ok(True)


@bp.route('/halls')
@api_permission_required('exams.assign_room')
def api_exam_halls():
    db = get_db()
    return ok({'halls': exam_service.get_exam_halls(db)})


@bp.route('/halls', methods=['POST'])
@api_permission_required('exams.assign_room')
@csrf_required
def api_exam_hall_create():
    data = body()
    name = (data.get('name') or '').strip()
    try:
        capacity = int(data.get('capacity', 0))
    except (TypeError, ValueError):
        return err('السعة يجب أن تكون رقماً', 422)
    status = data.get('status', 'active')
    if not name:
        return err('اسم القاعة مطلوب', 422)
    if capacity < 1:
        return err('السعة يجب أن تكون 1 على الأقل', 422)
    db = get_db()
    if exam_service.hall_name_exists(db, name):
        return err('اسم القاعة موجود مسبقاً', 409)
    exam_service.create_exam_hall(db, name, capacity, status)
    return ok(True, status=201)


@bp.route('/halls/<int:hall_id>', methods=['PUT'])
@api_permission_required('exams.assign_room')
@csrf_required
def api_exam_hall_update(hall_id):
    data = body()
    name = (data.get('name') or '').strip()
    try:
        capacity = int(data.get('capacity', 0))
    except (TypeError, ValueError):
        return err('السعة يجب أن تكون رقماً', 422)
    status = data.get('status', 'active')
    if not name:
        return err('اسم القاعة مطلوب', 422)
    if capacity < 1:
        return err('السعة يجب أن تكون 1 على الأقل', 422)
    db = get_db()
    if exam_service.hall_name_exists(db, name, exclude_id=hall_id):
        return err('اسم القاعة موجود مسبقاً', 409)
    exam_service.update_exam_hall(db, hall_id, name, capacity, status)
    return ok(True)


@bp.route('/period')
@api_permission_required('exams.period')
def api_exam_period():
    db = get_db()
    return ok({'period': exam_service.get_exam_period(db)})


@bp.route('/period', methods=['PUT'])
@api_permission_required('exams.period')
@csrf_required
def api_exam_period_save():
    data = body()
    db = get_db()
    payload = {
        'exam_start_date': (data.get('exam_start_date') or '').strip(),
        'exam_end_date': (data.get('exam_end_date') or '').strip(),
        'exam_start_time': data.get('exam_start_time', '09:00'),
        'exam_end_time': data.get('exam_end_time', '17:00'),
        'resave': data.get('resave'),
    }
    errors = [
        e for e in (
            valid_time(payload['exam_start_time'], 'وقت بداية الامتحانات'),
            valid_time(payload['exam_end_time'], 'وقت نهاية الامتحانات'),
            valid_date_range(payload['exam_start_date'], payload['exam_end_date'],
                             'تاريخ بداية الامتحانات', 'تاريخ نهاية الامتحانات'),
        ) if e
    ]
    if errors:
        return err('بيانات غير صحيحة', 422, errors=errors)
    exam_service.save_exam_period(db, payload, session.get('username', ''))
    return ok(True)


@bp.route('/period/publish', methods=['POST'])
@api_permission_required('exams.period')
@csrf_required
def api_exam_period_publish():
    db = get_db()
    period = exam_service.get_exam_period(db)
    if not period.get('exam_start_date') or not period.get('exam_end_date'):
        return err('يجب تحديد تاريخ البداية والنهاية قبل النشر', 422)
    exam_service.publish_exam_period(db, session.get('username', ''))
    period = exam_service.get_exam_period(db)
    _notify_all(
        db, 'نشر فترة الامتحانات',
        f'تم نشر فترة الامتحانات من {period.get("exam_start_date", "")} إلى {period.get("exam_end_date", "")}',
        'exam_settings', 1,
    )
    return ok(True)


@bp.route('/semester-period')
@api_permission_required('exams.period')
def api_exam_semester_period():
    db = get_db()
    from datetime import date
    today = date.today()
    season = 'fall' if today.month >= 9 else 'spring'
    year = today.year
    code = f'{season}_{year}'
    from utils.format import semester_display_name
    settings = exam_service.get_exam_period(db)
    sem = {
        'id': None,
        'code': code,
        'season': season,
        'year': year,
        'name_ar': semester_display_name(code),
        'exam_start_date': settings.get('exam_start_date') or '',
        'exam_end_date': settings.get('exam_end_date') or '',
    }
    return ok({'semester': sem})


@bp.route('/semester-period', methods=['PUT'])
@api_permission_required('exams.period')
@csrf_required
def api_exam_semester_period_save():
    data = body()
    db = get_db()
    exam_start = (data.get('exam_start_date') or '').strip()
    exam_end = (data.get('exam_end_date') or '').strip()

    if exam_start and exam_end and exam_start > exam_end:
        return err('تاريخ النهاية يجب أن يكون بعد تاريخ البداية', 422)

    existing = db.execute('SELECT id FROM exam_settings LIMIT 1').fetchone()
    if existing:
        db.execute(
            'UPDATE exam_settings SET exam_start_date = ?, exam_end_date = ?, '
            'updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (exam_start, exam_end, existing['id']),
        )
    else:
        db.execute(
            "INSERT INTO exam_settings "
            "(exam_start_date, exam_end_date, exam_start_time, exam_end_time) "
            "VALUES (?, ?, '09:00', '17:00')",
            (exam_start, exam_end),
        )
    db.commit()
    return ok({'saved': True})


@bp.route('/department-schedule/assign', methods=['POST'])
@api_permission_required('exams.department_schedule')
@csrf_required
def api_exam_assign():
    data = body()

    def fk(key):
        value = data.get(key)
        try:
            return int(value) if value not in (None, '') else None
        except (TypeError, ValueError):
            return None

    course_id = fk('course_id')
    dept_id = fk('dept_id')
    semester = fk('semester')
    exam_date = (data.get('exam_date') or '').strip() or None
    if not course_id or not dept_id or not semester:
        return err('بيانات غير صالحة', 422)
    db = get_db()
    user_data = current_user()
    role = session.get('role', '')
    if role == 'head_of_department' and dept_id != user_data.get('department_id'):
        return err('لا يمكنك تعديل جدول قسم آخر', 403)
    try:
        exam_service.save_exam_assignment(db, course_id, dept_id, semester, exam_date, session.get('user_id'))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 400)
    return ok({'exam_date': exam_date})


@bp.route('/planning/assign', methods=['POST'])
@api_permission_required('exams.planning')
@csrf_required
def api_exam_planning_assign():
    data = body()

    def fk(key):
        value = data.get(key)
        try:
            return int(value) if value not in (None, '') else None
        except (TypeError, ValueError):
            return None

    schedule_id = fk('schedule_id')
    room_id = fk('room_id')
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()
    if not schedule_id or not room_id or not start_time or not end_time:
        return err('يرجى اختيار القاعة والفترة الزمنية', 422)
    db = get_db()
    exam_service.assign_exam_resources(db, schedule_id, room_id, start_time, end_time)
    return ok(True)


@bp.route('/planning/publish', methods=['POST'])
@api_permission_required('exams.planning')
@csrf_required
def api_exam_planning_publish():
    db = get_db()
    count = exam_service.publish_schedule(db)
    if count > 0:
        _notify_all(db, 'نشر جدول الامتحانات',
                    f'تم نشر {count} امتحان في الجدول النهائي', 'exam_schedule', 0)
    return ok({'published': count})


@bp.route('/schedule/<int:schedule_id>/room', methods=['POST'])
@api_permission_required('exams.assign_room')
@csrf_required
def api_exam_update_room(schedule_id):
    data = body()
    try:
        room_id = int(data.get('room_id')) if data.get('room_id') else None
    except (TypeError, ValueError):
        return err('معرف القاعة غير صالح', 422)
    db = get_db()
    result = exam_service.update_exam_room(db, schedule_id, room_id)
    return ok(result)


@bp.route('/conflicts', methods=['POST'])
@api_permission_required('exams.assign_room')
@csrf_required
def api_exam_conflicts():
    data = body()

    def fk(key):
        value = data.get(key)
        try:
            return int(value) if value not in (None, '') else None
        except (TypeError, ValueError):
            return None

    schedule_id = fk('schedule_id')
    room_id = fk('room_id')
    if not schedule_id:
        return err('معرف الامتحان مطلوب', 422)
    db = get_db()
    conflicts = exam_service.check_exam_conflicts(
        db, schedule_id, room_id,
        (data.get('start_time') or '').strip(),
        (data.get('end_time') or '').strip(),
    )
    return ok({'conflicts': conflicts, 'has_conflicts': len(conflicts) > 0})
