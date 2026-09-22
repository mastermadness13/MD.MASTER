"""Timetable API — the weekly grid and department view."""

from __future__ import annotations

from flask import Blueprint, request, session

from api.helpers import (
    api_permission_required,
    body,
    err,
    ok,
)
from core.constants.ui import ARABIC_DAYS, WEEK_DAYS, WEEK_DAYS_ALT
from core.validators import integer_between, valid_time
from flask_db import get_db
from security import csrf_required
from services import notification_service, timetable_service
from services.timetable_scope import (
    INVALID_SEMESTER_MESSAGE,
    InvalidSemesterError,
    allowed_semesters_for,
    semester_token,
    validate_semester_allowed,
)

bp = Blueprint('api_timetable', __name__, url_prefix='/api/timetable')
def _entry_fields(data):
    def fk(key, default=None):
        value = data.get(key, default)
        if value in (None, ''):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    return {
        'day': (data.get('day') or '').strip(),
        'semester': fk('semester', 1) or 1,
        'period_code': (data.get('period_code') or data.get('section') or '').strip(),
        'course_id': fk('course_id'),
        'teacher_id': fk('teacher_id'),
        'room_id': fk('room_id'),
        'department_id': fk('department_id'),
        'start_time': (data.get('start_time') or '').strip(),
        'end_time': (data.get('end_time') or '').strip(),
        'lecture_type': (data.get('lecture_type') or 'theory').strip() or 'theory',
        'hours': fk('hours', 0) or 0,
    }


def _entry_required(fields, include_department=True, include_teacher=True):
    required = ['day', 'course_id', 'room_id', 'period_code']
    if include_department:
        required.append('department_id')
    if include_teacher:
        required.append('teacher_id')
    return not any(fields.get(k) in (None, '', 0) for k in required)


def _entry_times_valid(fields):
    """Return True when both times are present and start < end."""
    start = fields.get('start_time')
    end = fields.get('end_time')
    if not start or not end:
        return True
    try:
        sh, sm = start.split(':'); eh, em = end.split(':')
        return int(sh) * 60 + int(sm) < int(eh) * 60 + int(em)
    except (ValueError, TypeError):
        return False


# /     /     >---- كل أسماء الأيام العربية المسموحة في الجدول (مكتوبة بأي طريقة)
_ALLOWED_TIMETABLE_DAYS = {*set(WEEK_DAYS), *set(WEEK_DAYS_ALT), *set(ARABIC_DAYS.values())}


def _entry_fields_valid(fields):
    """L6: structural validation — day whitelist, time format, hour bounds."""
    errors = []
    day = fields.get('day')
    if day and day not in _ALLOWED_TIMETABLE_DAYS:
        errors.append('اليوم غير مسموح')
    hours = fields.get('hours')
    if hours not in (None, '', 0):
        msg = integer_between(hours, 1, 24, 'عدد الساعات')
        if msg:
            errors.append(msg)
    for key, label in (('start_time', 'وقت البداية'), ('end_time', 'وقت النهاية')):
        msg = valid_time(fields.get(key), label)
        if msg:
            errors.append(msg)
    return errors


def _notify(db, teacher_id, title, message, entry_id):
    uid = notification_service.get_teacher_user_id(db, teacher_id)
    if uid:
        notification_service.create_notification(
            db, uid, title, message, 'schedule', 'timetable', entry_id
        )


def _user_dept():
    """Department the current user is scoped to — HODs always use the
    department they head (hod_department_id), every other role their own."""
    return session.get('hod_department_id') or session.get('department_id')


def _is_hod():
    return session.get('role', '') == 'head_of_department'


@bp.route('')
@api_permission_required('timetable.view')
def api_timetable():
    db = get_db()
    role = session.get('role', '')
    user_dept = _user_dept()
    selected_dept = request.args.get('department', type=int)
    selected_semester = request.args.get('semester', 0, type=int)
    selected_section = request.args.get('section', '').strip() or None
    data = timetable_service.get_timetable_data(
        db, role, user_dept, selected_dept, selected_semester, selected_section
    )
    return ok(data)


@bp.route('/department')
@api_permission_required('timetable.view')
def api_timetable_department():
    db = get_db()
    filter_dept_id = request.args.get('department_id', type=int)
    if _is_hod():
        filter_dept_id = _user_dept()
    semester = request.args.get('semester', type=int)
    version_id = request.args.get('version_id', type=int)
    data = timetable_service.get_department_view(db, filter_dept_id, semester, version_id)
    return ok(data)


@bp.route('/version/token')
@api_permission_required('timetable.view')
def api_timetable_version_token():
    """Live-sync fingerprint: changes whenever the department's active version
    for the semester changes (new edits or a fresh next-year copy)."""
    db = get_db()
    filter_dept_id = request.args.get('department_id', type=int)
    if _is_hod():
        filter_dept_id = _user_dept()
    semester = request.args.get('semester', type=int)

    if not filter_dept_id:
        return err('department_id مطلوب', 400)
    if not semester:
        return err('semester مطلوب', 400)

    dept_row = db.execute(
        'SELECT name, semesters FROM departments WHERE id = ?', (filter_dept_id,)
    ).fetchone()
    if not dept_row:
        return err('القسم غير موجود', 404)

    allowed = allowed_semesters_for(dept_row)
    if semester not in allowed:
        return err(INVALID_SEMESTER_MESSAGE, 422)

    return ok({'token': semester_token(db, filter_dept_id, semester)})


@bp.route('/entries', methods=['POST'])
@api_permission_required('timetable.edit')
@csrf_required
def api_timetable_create_entry():
    fields = _entry_fields(body())
    if not _entry_required(fields, include_department=True, include_teacher=False):
        return err('جميع الحقول المطلوبة يجب ملؤها (بما في ذلك القسم). يمكن حفظ الحصة بدون تعيين عضو هيئة تدريس.', 422)
    entry_errors = _entry_fields_valid(fields)
    if entry_errors:
        return err('بيانات غير صحيحة', 422, errors=entry_errors)
    if not _entry_times_valid(fields):
        return err('وقت النهاية يجب أن يكون بعد وقت البداية.', 422)
    if _is_hod() and fields['department_id'] != _user_dept():
        return err('لا يمكن إنشاء حصص إلا في قسمك.', 403)
    db = get_db()
    try:
        validate_semester_allowed(db, fields['department_id'], fields['semester'])
    except InvalidSemesterError:
        return err(INVALID_SEMESTER_MESSAGE, 422)
    try:
        version_id = None
        if fields['department_id']:
            version_id = timetable_service.ensure_current_version(db, fields['department_id'], fields['semester'])
        entry_id = timetable_service.create_entry(
            db, fields['day'], fields['semester'], fields['period_code'],
            fields['course_id'], fields['teacher_id'], fields['room_id'],
            fields['department_id'], fields['start_time'], fields['end_time'],
            version_id=version_id,
            lecture_type=fields['lecture_type'], hours=fields['hours'],
        )
    except Exception as exc:  # noqa: BLE001
        return err(f'فشل حفظ الحصة: {exc}', 400)
    if not entry_id or not timetable_service.verify_entry(db, entry_id):
        return err('فشل حفظ الحصة. لم يتم العثور على السجل.', 500)
    course = db.execute('SELECT name FROM courses WHERE id = ?', (fields['course_id'],)).fetchone()
    course_name = course['name'] if course else ''
    _notify(db, fields['teacher_id'], 'إضافة محاضرة جديدة',
            f'تمت إضافة محاضرة "{course_name}" يوم {fields["day"]} في الجدول الدراسي', entry_id)
    return ok({'id': entry_id}, status=201)


@bp.route('/entries/<int:entry_id>', methods=['PUT'])
@api_permission_required('timetable.edit')
@csrf_required
def api_timetable_update_entry(entry_id):
    fields = _entry_fields(body())
    if not _entry_required(fields, include_department=False, include_teacher=False):
        return err('جميع الحقول المطلوبة يجب ملؤها', 422)
    entry_errors = _entry_fields_valid(fields)
    if entry_errors:
        return err('بيانات غير صحيحة', 422, errors=entry_errors)
    if not _entry_times_valid(fields):
        return err('وقت النهاية يجب أن يكون بعد وقت البداية.', 422)
    db = get_db()
    existing = db.execute(
        'SELECT department_id FROM timetable WHERE id = ?', (entry_id,)
    ).fetchone()
    if not existing:
        return err('الحصة غير موجودة', 404)
    if _is_hod() and existing['department_id'] != _user_dept():
        return err('لا يمكن تعديل حصص من قسم آخر.', 403)
    try:
        validate_semester_allowed(db, existing['department_id'], fields['semester'])
    except InvalidSemesterError:
        return err(INVALID_SEMESTER_MESSAGE, 422)
    try:
        updated = timetable_service.update_entry(
            db, entry_id, fields['day'], fields['semester'], fields['period_code'],
            fields['course_id'], fields['teacher_id'], fields['room_id'],
            fields['start_time'], fields['end_time'],
            lecture_type=fields['lecture_type'], hours=fields['hours'],
        )
    except Exception as exc:  # noqa: BLE001
        return err(f'فشل تعديل الحصة: {exc}', 400)
    if not updated or not timetable_service.verify_entry(db, entry_id):
        return err('فشل تعديل الحصة.', 404)
    course = db.execute('SELECT name FROM courses WHERE id = ?', (fields['course_id'],)).fetchone()
    course_name = course['name'] if course else ''
    _notify(db, fields['teacher_id'], 'تعديل محاضرة',
            f'تم تعديل محاضرة "{course_name}" في الجدول الدراسي يوم {fields["day"]}', entry_id)
    return ok(True)


@bp.route('/entries/<int:entry_id>', methods=['DELETE'])
@api_permission_required('timetable.edit')
@csrf_required
def api_timetable_delete_entry(entry_id):
    db = get_db()
    entry = db.execute(
        '''SELECT t.teacher_id, t.department_id, c.name AS course_name FROM timetable t
           LEFT JOIN courses c ON t.course_id = c.id WHERE t.id = ?''',
        (entry_id,),
    ).fetchone()
    if not entry:
        return err('الحصة غير موجودة', 404)
    if _is_hod() and entry['department_id'] != _user_dept():
        return err('لا يمكن حذف حصص من قسم آخر.', 403)
    try:
        deleted = timetable_service.delete_entry(db, entry_id)
    except Exception as exc:  # noqa: BLE001
        return err(f'فشل حذف الحصة: {exc}', 400)
    if not deleted or timetable_service.verify_entry(db, entry_id):
        return err('فشل حذف الحصة. السجل لا يزال موجوداً.', 500)
    if entry:
        _notify(db, entry['teacher_id'], 'حذف محاضرة',
                f'تم حذف محاضرة "{entry["course_name"]}" من الجدول الدراسي', entry_id)
    return ok(True)


@bp.route('/entries/<int:entry_id>')
@api_permission_required('timetable.view')
def api_timetable_get_entry(entry_id):
    db = get_db()
    entry = timetable_service.get_entry(db, entry_id)
    if not entry:
        return err('الحصة غير موجودة', 404)
    return ok(entry)


@bp.route('/report-error', methods=['POST'])
@api_permission_required('timetable.view')
@csrf_required
def api_timetable_report_error():
    data = body()
    msg = data.get('message', '')
    url = data.get('url', '')
    ts = data.get('timestamp', '')
    from flask import current_app
    current_app.logger.warning('Timetable error report: %s | URL: %s | Time: %s', msg, url, ts)
    return ok(True)


@bp.route('/versions/create-next', methods=['POST'])
@api_permission_required('timetable.edit')
@csrf_required
def api_timetable_version_create_next():
    data = body()
    source_version_id = data.get('version_id')
    if source_version_id:
        try:
            source_version_id = int(source_version_id)
        except (TypeError, ValueError):
            source_version_id = None
    copy_entries = bool(data.get('copy_entries', False))
    db = get_db()

    source = None
    if source_version_id:
        source = db.execute(
            'SELECT id, department_id, semester FROM timetable_versions WHERE id = ?',
            (source_version_id,),
        ).fetchone()
    if not source:
        return err('نسخة الجدول المطلوبة غير موجودة.', 404)

    dept_id = source['department_id']
    semester = source['semester']
    if not dept_id:
        return err('النسخة لا تنتمي إلى أي قسم.', 400)
    if _is_hod() and dept_id != _user_dept():
        return err('لا يمكن إنشاء نسخة لقسم آخر.', 403)

    try:
        new_version_id, sem_code = timetable_service.create_version_for_next_semester(
            db, dept_id, semester,
            source_version_id=source_version_id if copy_entries else None,
        )
    except Exception as exc:  # noqa: BLE001
        return err(f'فشل إنشاء جدول الفصل القادم: {exc}', 400)

    from utils.format import semester_display_name
    sem_name = semester_display_name(sem_code)

    from flask import url_for
    url = url_for('timetable.timetable_department_view',
                  department_id=dept_id, semester=semester, version_id=new_version_id)
    return ok({
        'version_id': new_version_id,
        'semester_code': sem_code,
        'semester_name_ar': sem_name,
        'message': f'تم إنشاء نسخة الفصل الدراسي {sem_name} بنجاح.'
                   + (' وتم نسخ الحصص من الجدول الأصلي.' if copy_entries else ''),
        'url': url,
    })


@bp.route('/available-rooms')
@api_permission_required('timetable.view')
def api_timetable_available_rooms():
    db = get_db()
    rooms = timetable_service.get_available_rooms(
        db, request.args.get('day', ''), request.args.get('semester', type=int),
        request.args.get('period_code', ''), request.args.get('exclude_id', type=int),
        request.args.get('start_time', ''), request.args.get('end_time', ''),
        request.args.get('hours', 0, type=int),
    )
    return ok({'rooms': rooms})


@bp.route('/available-teachers')
@api_permission_required('timetable.view')
def api_timetable_available_teachers():
    db = get_db()
    teachers = timetable_service.get_available_teachers(
        db, request.args.get('day', ''), request.args.get('semester', type=int),
        request.args.get('period_code', ''), request.args.get('exclude_id', type=int),
        request.args.get('start_time', ''), request.args.get('end_time', ''),
        request.args.get('hours', 0, type=int),
    )
    return ok({'teachers': teachers})
