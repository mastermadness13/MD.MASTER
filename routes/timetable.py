import logging

from flask import Blueprint, session, request, render_template, redirect, url_for, flash, jsonify

from api.helpers import ok

from flask_db import get_db
from security import csrf_required, login_required, permission_required
from security import current_user, has_permission
from services import timetable_service, notification_service, public_service
from services.timetable_scope import (
    INVALID_SEMESTER_MESSAGE,
    InvalidSemesterError,
    allowed_semesters_for,
    semester_token,
    validate_semester_allowed,
)

logger = logging.getLogger(__name__)

bp = Blueprint('timetable', __name__, url_prefix='/timetable')


def _user_dept():
    """Return the department restriction that applies to the active role.

    Only a head of department is restricted to one department. Teachers and
    read-only administrative roles may view all permitted timetable data.
    """
    if session.get('role', '') == 'head_of_department':
        return session.get('hod_department_id') or session.get('department_id')
    return None


def _is_hod():
    return session.get('role', '') == 'head_of_department'


def _hod_dept():
    return session.get('hod_department_id')


def _first_department_id(db):
    first = db.execute(
        'SELECT id FROM departments WHERE hidden=0 AND deleted_at IS NULL ORDER BY name LIMIT 1'
    ).fetchone()
    return first['id'] if first else None


def _file_maps(db):
    """form / vocab / syllabus maps shared by every unified timetable view."""
    forms, vocab, syllabi_files = public_service.get_course_content_files(db)
    form = {
        cid: {
            'id': item['id'],
            'url': url_for('public_library.course_file', file_id=item['id']),
            'submission_id': item.get('submission_id'),
        }
        for cid, item in forms.items()
    }
    published_contents = public_service.get_published_course_contents(db)
    for cid, item in published_contents.items():
        form.setdefault(cid, {
            'id': item['id'],
            'url': url_for(
                'public_library.course_content',
                submission_id=item['id'],
            ),
            'submission_id': item['id'],
            'is_document': True,
        })
    vocab_map = {
        cid: {
            'id': item['id'],
            'originalFilename': item['original_filename'],
            'url': url_for('public_library.course_file', file_id=item['id']),
        }
        for cid, item in vocab.items()
    }
    syllabi = {}
    for key, item in syllabi_files.items():
        entry = {
            'id': item['id'],
            'url': url_for('public_library.course_file', file_id=item['id']),
            'teacher_id': item.get('teacher_id'),
            'course_id': item['course_id'],
        }
        syllabi[key] = entry
        if item.get('teacher_id') is None:
            syllabi['*:{}'.format(item['course_id'])] = entry
    return form, vocab_map, syllabi


def _teacher_id_for_user(db, uid):
    if not uid:
        return None
    trow = db.execute('SELECT id FROM teachers WHERE user_id = ?', (uid,)).fetchone()
    return trow['id'] if trow else None


def _render_unified(db, role, user_data, dept_id, semester, version_id,
                    can_manage, can_switch_department, nav_active,
                    is_rd=False, current_teacher_id=None):
    """Shared renderer for all timetable personas — one unified page that is
    a full editor (can_manage), a locked read-only table (old version), or a
    read-only R&D/audit view (can_manage=False). With ``?format=json`` it
    returns the same payload as JSON for the live-sync poller."""
    payload = timetable_service.get_department_view(db, dept_id, semester, version_id)
    payload['can_manage'] = can_manage
    payload['can_switch_department'] = can_switch_department

    form, vocab_map, syllabi = _file_maps(db)
    payload['form'] = form
    payload['vocab'] = vocab_map
    payload['syllabus'] = syllabi

    if request.args.get('format') == 'json':
        return ok(payload)

    initial_token = ''
    if dept_id:
        try:
            initial_token = semester_token(
                db, dept_id, payload.get('selected_semester') or 1)
        except InvalidSemesterError:
            initial_token = ''
    payload['fingerprint'] = initial_token

    rd_upload = url_for('teacher_pages.super_admin_course_syllabus_upload', course_id=0)
    rd_delete = url_for('teacher_pages.super_admin_course_syllabus_delete', course_id=0)
    tf_delete = url_for('teacher_pages.teacher_syllabus_delete', tf_id=0)
    syllabus_urls = {
        'rdUpload': rd_upload.replace('/course/0/', '/course/{cid}/'),
        'rdDelete': rd_delete.replace('/course/0/', '/course/{cid}/'),
        'teacherUpload': url_for('teacher_pages.teacher_syllabus_upload'),
        'teacherDelete': tf_delete.replace('/syllabus/0', '/syllabus/{tfid}'),
    }

    return render_template(
        'timetable/unified.html',
        payload=payload,
        user=user_data,
        nav_active=nav_active,
        is_rd=is_rd,
        current_teacher_id=current_teacher_id,
        initial_token=initial_token,
        syllabus_urls=syllabus_urls,
    )


@bp.route('')
@bp.route('/')
@login_required
@permission_required('timetable.view')
def timetable():
    role = session.get('role', '')
    user_dept = _user_dept()
    db = get_db()

    dept_id = request.args.get('department_id', type=int)
    if user_dept:
        dept_id = user_dept
    if not dept_id:
        dept_id = _first_department_id(db)

    semester = request.args.get('semester', type=int)
    version_id = request.args.get('version_id', type=int)

    if dept_id:
        dept_row = db.execute(
            'SELECT name, semesters FROM departments WHERE id = ?', (dept_id,)
        ).fetchone()
        if dept_row:
            allowed = allowed_semesters_for(dept_row)
            if semester is not None and semester not in allowed:
                return redirect(url_for('timetable.timetable',
                                        department_id=dept_id,
                                        semester=allowed[0],
                                        version_id=version_id))

    return _render_unified(
        db, role, current_user(), dept_id, semester, version_id,
        can_manage=has_permission(role, 'timetable.edit'),
        can_switch_department=not user_dept,
        nav_active='timetable.timetable',
        is_rd=(role == 'research_development'),
        current_teacher_id=_teacher_id_for_user(db, session.get('user_id')),
    )


@bp.route('/department')
@login_required
@permission_required('timetable.view')
def timetable_department_view():
    role = session.get('role', '')
    user_data = current_user()
    db = get_db()
    can_manage = has_permission(role, 'timetable.edit')

    user_dept_id = _user_dept()
    dept_id = request.args.get('department_id', type=int)
    if user_dept_id:
        dept_id = user_dept_id

    if not dept_id:
        dept_id = _first_department_id(db)

    semester = request.args.get('semester', type=int)
    version_id = request.args.get('version_id', type=int)

    if dept_id:
        dept_row = db.execute(
            'SELECT name, semesters FROM departments WHERE id = ?', (dept_id,)
        ).fetchone()
        if dept_row:
            allowed = allowed_semesters_for(dept_row)
            if semester is not None and semester not in allowed:
                return redirect(url_for('timetable.timetable_department_view',
                                        department_id=dept_id,
                                        semester=allowed[0],
                                        version_id=version_id))

    return _render_unified(
        db, role, user_data, dept_id, semester, version_id,
        can_manage=can_manage,
        can_switch_department=not user_dept_id,
        nav_active='timetable.timetable',
        is_rd=(role == 'research_development'),
        current_teacher_id=_teacher_id_for_user(db, session.get('user_id')),
    )


@bp.route('/rnd')
@login_required
@permission_required('timetable.view')
def rnd_timetable():
    """Read-only single-table timetable view for the research & development role."""
    role = session.get('role', '')
    if role != 'research_development':
        return redirect(url_for('timetable.timetable'))
    db = get_db()
    user_data = current_user()

    dept_id = request.args.get('department_id', type=int)
    if not dept_id:
        dept_id = _first_department_id(db)

    semester = request.args.get('semester', type=int)
    version_id = request.args.get('version_id', type=int)

    if dept_id:
        dept_row = db.execute(
            'SELECT name, semesters FROM departments WHERE id = ?', (dept_id,)
        ).fetchone()
        if dept_row:
            allowed = allowed_semesters_for(dept_row)
            if semester is not None and semester not in allowed:
                return redirect(url_for('timetable.rnd_timetable',
                                        department_id=dept_id,
                                        semester=allowed[0],
                                        version_id=version_id))

    return _render_unified(
        db, role, user_data, dept_id, semester, version_id,
        can_manage=False,
        can_switch_department=True,
        nav_active='timetable.rnd_timetable',
        is_rd=(role == 'research_development'),
        current_teacher_id=_teacher_id_for_user(db, session.get('user_id')),
    )


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('timetable.edit')
@csrf_required
def timetable_create():
    db = get_db()
    role = session.get('role', '')
    user_dept = _user_dept()
    is_modal = request.args.get('modal') or request.form.get('modal')

    departments_list = [dict(r) for r in db.execute(
        'SELECT id, name FROM departments WHERE hidden=0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()]

    def _form_context(day, semester, period_code, dept_id, start_time, end_time, form_error):
        dept_name, enabled_periods, courses_list, teachers_list, rooms_list = \
            timetable_service.get_create_form_data(db, dept_id, day, semester, period_code, user_dept)
        available_semesters = [1]
        if dept_id:
            dept_row = db.execute('SELECT name, semesters FROM departments WHERE id=?', (dept_id,)).fetchone()
            if dept_row:
                available_semesters = allowed_semesters_for(dept_row)
        return dict(entry=None, days=timetable_service.DAYS,
                    default_day=day, default_semester=semester, default_period_code=period_code,
                    enabled_periods=enabled_periods, courses=courses_list,
                    teachers=teachers_list, initial_rooms=rooms_list,
                    selected_department_name=dept_name, selected_department_id=dept_id,
                    departments=departments_list, is_modal=is_modal,
                    form_start_time=start_time, form_end_time=end_time,
                    available_semesters=available_semesters, form_error=form_error,
                    user=current_user())

    if request.method == 'POST':
        day = request.form.get('day', '').strip()
        semester = request.form.get('semester', type=int) or 1
        period_code = request.form.get('section', '').strip()
        course_id = request.form.get('course_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int)
        room_id = request.form.get('room_id', type=int)
        department_id = request.form.get('department_id', type=int) or user_dept
        if _is_hod() and department_id != _hod_dept():
            msg = 'لا يمكن إنشاء حصص إلا في قسمك (قسم الرئاسة).'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            flash(msg, 'error')
            return redirect(url_for('timetable.timetable'))
        start_time = request.form.get('start_time', '').strip()
        end_time = request.form.get('end_time', '').strip()

        if not day or not course_id or not room_id or not period_code or not department_id:
            msg = 'جميع الحقول المطلوبة يجب ملؤها (بما في ذلك القسم). يمكن حفظ الحصة بدون تعيين عضو هيئة تدريس، ويمكن تعيينه لاحقًا من تعديل الحصة.'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            return render_template('timetable/form.html', **_form_context(
                day, semester, period_code, department_id, start_time, end_time, msg))

        try:
            validate_semester_allowed(db, department_id, semester)
        except InvalidSemesterError:
            msg = INVALID_SEMESTER_MESSAGE
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            return render_template('timetable/form.html', **_form_context(
                day, semester, period_code, department_id, start_time, end_time, msg))

        try:
            version_id = None
            if department_id:
                version_id = timetable_service.ensure_current_version(db, department_id, semester)
            entry_id = timetable_service.create_entry(
                db, day, semester, period_code, course_id, teacher_id,
                room_id, department_id, start_time, end_time,
                version_id=version_id,
                lecture_type=request.form.get('lecture_type', 'theory').strip() or 'theory',
                hours=request.form.get('hours', 0, type=int) or 0,
            )
        except Exception as e:
            logger.exception('Failed to create timetable entry')
            msg = f'❌ فشل حفظ الحصة. السبب: {str(e)}'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            return render_template('timetable/form.html', **_form_context(
                day, semester, period_code, department_id, start_time, end_time, msg))

        if not entry_id or not timetable_service.verify_entry(db, entry_id):
            msg = '❌ فشل حفظ الحصة. لم يتم العثور على السجل في قاعدة البيانات.'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            return render_template('timetable/form.html', **_form_context(
                day, semester, period_code, department_id, start_time, end_time, msg))

        course = db.execute('SELECT name FROM courses WHERE id=?', (course_id,)).fetchone()
        course_name = course['name'] if course else ''
        teacher_uid = notification_service.get_teacher_user_id(db, teacher_id)
        if teacher_uid:
            notification_service.create_notification(
                db, teacher_uid,
                'إضافة محاضرة جديدة',
                f'تمت إضافة محاضرة "{course_name}" يوم {day} في الجدول الدراسي',
                'schedule', 'timetable', entry_id
            )

        warnings = timetable_service.get_last_conflict_warnings()
        warning_text = '؛ '.join(warnings) if warnings else ''

        if is_modal:
            resp = {'ok': True, 'message': '✅ تم حفظ الحصة بنجاح. تم تخزين الجدول بشكل دائم في قاعدة البيانات.'}
            if warning_text:
                resp['warning'] = warning_text
            return jsonify(resp)
        flash('✅ تم حفظ الحصة بنجاح. تم تخزين الجدول بشكل دائم في قاعدة البيانات.', 'success')
        if warning_text:
            flash(f'⚠️ {warning_text}', 'warning')
        return redirect(url_for('timetable.timetable'))

    day = request.args.get('day', timetable_service.DAYS[0])
    sem = request.args.get('semester', 1, type=int)
    period_code = request.args.get('period', 'A')
    dept_id = request.args.get('department_id', user_dept, type=int)
    if _is_hod():
        dept_id = _hod_dept()
    return render_template('timetable/form.html', **_form_context(
        day, sem, period_code, dept_id, '', '', None))


@bp.route('/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('timetable.edit')
@csrf_required
def timetable_edit(entry_id):
    db = get_db()
    role = session.get('role', '')
    entry = timetable_service.get_entry(db, entry_id)
    if not entry:
        flash('الحصة غير موجودة', 'danger')
        return redirect(url_for('timetable.timetable'))
    if _is_hod() and entry.get('department_id') != _hod_dept():
        flash('لا يمكن تعديل حصص من قسم آخر.', 'error')
        return redirect(url_for('timetable.timetable'))
    is_modal = request.args.get('modal') or request.form.get('modal')
    if request.method == 'POST':
        day = request.form.get('day', '').strip()
        semester = request.form.get('semester', type=int) or 1
        period_code = request.form.get('section', '').strip()
        course_id = request.form.get('course_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int)
        room_id = request.form.get('room_id', type=int)
        start_time = request.form.get('start_time', '').strip()
        end_time = request.form.get('end_time', '').strip()
        if not day or not course_id or not room_id or not period_code:
            msg = 'جميع الحقول المطلوبة يجب ملؤها. يمكن حفظ الحصة بدون تعيين عضو هيئة تدريس، ويمكن تعيينه لاحقًا.'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            flash(msg, 'error')
            return redirect(url_for('timetable.timetable'))

        try:
            validate_semester_allowed(db, entry.get('department_id'), semester)
        except InvalidSemesterError:
            msg = INVALID_SEMESTER_MESSAGE
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            flash(msg, 'error')
            return redirect(url_for('timetable.timetable'))

        try:
            updated = timetable_service.update_entry(
                db, entry_id, day, semester, period_code, course_id,
                teacher_id, room_id, start_time, end_time,
                request.form.get('lecture_type', 'theory').strip() or 'theory',
                request.form.get('hours', 0, type=int) or 0,
            )
        except Exception as e:
            logger.exception('Failed to update timetable entry')
            msg = f'❌ فشل تعديل الحصة. السبب: {str(e)}'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            flash(msg, 'error')
            return redirect(url_for('timetable.timetable'))

        if not updated:
            msg = '❌ فشل تعديل الحصة. السجل غير موجود.'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            flash(msg, 'error')
            return redirect(url_for('timetable.timetable'))

        if not timetable_service.verify_entry(db, entry_id):
            msg = '❌ فشل تعديل الحصة. لم يتم العثور على السجل المحدث.'
            if is_modal:
                return jsonify({'ok': False, 'message': msg})
            flash(msg, 'error')
            return redirect(url_for('timetable.timetable'))

        course = db.execute('SELECT name FROM courses WHERE id=?', (course_id,)).fetchone()
        course_name = course['name'] if course else ''
        teacher_uid = notification_service.get_teacher_user_id(db, teacher_id)
        if teacher_uid:
            notification_service.create_notification(
                db, teacher_uid,
                'تعديل محاضرة',
                f'تم تعديل محاضرة "{course_name}" في الجدول الدراسي يوم {day}',
                'schedule', 'timetable', entry_id
            )

        warnings = timetable_service.get_last_conflict_warnings()
        warning_text = '؛ '.join(warnings) if warnings else ''

        if is_modal:
            resp = {'ok': True, 'message': '✅ تم تعديل الحصة بنجاح.'}
            if warning_text:
                resp['warning'] = warning_text
            return jsonify(resp)
        flash('✅ تم تعديل الحصة بنجاح.', 'success')
        if warning_text:
            flash(f'⚠️ {warning_text}', 'warning')
        return redirect(url_for('timetable.timetable'))
    dept_id = entry.get('department_id')
    dept_name, enabled_periods, courses_list, teachers_list, rooms_list = \
        timetable_service.get_create_form_data(db, dept_id, entry.get('day'), entry.get('semester'), entry.get('period'), None)
    if dept_id and entry.get('course_id') and not any(
            c['id'] == entry['course_id'] for c in courses_list):
        row = db.execute(
            'SELECT id, name, code FROM courses WHERE id = ? AND deleted_at IS NULL',
            (entry['course_id'],),
        ).fetchone()
        if row:
            courses_list.append(dict(row))

    available_semesters = [1]
    if dept_id:
        dept_row = db.execute('SELECT name, semesters FROM departments WHERE id=?', (dept_id,)).fetchone()
        if dept_row:
            available_semesters = allowed_semesters_for(dept_row)

    return render_template('timetable/form.html', entry=entry, days=timetable_service.DAYS,
                          default_day=entry.get('day'), default_semester=entry.get('semester'),
                          default_period_code=entry.get('period'),
                          enabled_periods=enabled_periods, courses=courses_list,
                          teachers=teachers_list, initial_rooms=rooms_list,
                          selected_department_name=dept_name, selected_department_id=dept_id,
                          departments=[], is_modal=is_modal,
                          form_start_time=entry.get('start_time', ''),
                          form_end_time=entry.get('end_time', ''),
                          available_semesters=available_semesters,
                          form_error=None,
                          user=current_user())


@bp.route('/api/get-entry/<int:entry_id>')
@login_required
@permission_required('timetable.view')
def timetable_get_entry(entry_id):
    db = get_db()
    entry = timetable_service.get_entry(db, entry_id)
    if not entry:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(entry)


@bp.route('/api/report-error', methods=['POST'])
@login_required
@permission_required('timetable.view')
@csrf_required
def timetable_report_error():
    data = request.get_json(silent=True) or {}
    msg = data.get('message', '')
    url = data.get('url', '')
    ts = data.get('timestamp', '')
    from flask import current_app
    current_app.logger.warning('Timetable error report: %s | URL: %s | Time: %s', msg, url, ts)
    return jsonify({'ok': True})


@bp.route('/api/delete-entry', methods=['POST'])
@login_required
@permission_required('timetable.edit')
@csrf_required
def timetable_delete_entry():
    data = request.get_json(silent=True) or {}
    lecture_id = data.get('lecture_id')
    if not lecture_id:
        return jsonify({'ok': False, 'message': 'معرف الحصة مطلوب'})
    db = get_db()

    entry = db.execute(
        '''SELECT t.teacher_id, t.department_id, c.name as course_name FROM timetable t
           LEFT JOIN courses c ON t.course_id = c.id WHERE t.id=?''',
        (lecture_id,)
    ).fetchone()
    if _is_hod() and entry and entry['department_id'] != _hod_dept():
        return jsonify({'ok': False, 'message': 'لا يمكن حذف حصص من قسم آخر.'})

    try:
        deleted = timetable_service.delete_entry(db, lecture_id)
    except Exception as e:
        logger.exception('Failed to delete timetable entry')
        return jsonify({'ok': False, 'message': f'❌ فشل حذف الحصة. السبب: {str(e)}'})

    if not deleted:
        return jsonify({'ok': False, 'message': '❌ فشل حذف الحصة. السجل غير موجود.'})

    still_exists = timetable_service.verify_entry(db, lecture_id)
    if still_exists:
        return jsonify({'ok': False, 'message': '❌ فشل حذف الحصة. السجل لا يزال موجوداً في قاعدة البيانات.'})

    if entry:
        teacher_uid = notification_service.get_teacher_user_id(db, entry['teacher_id'])
        if teacher_uid:
            notification_service.create_notification(
                db, teacher_uid,
                'حذف محاضرة',
                f'تم حذف محاضرة "{entry["course_name"]}" من الجدول الدراسي',
                'schedule', 'timetable', lecture_id
            )
    return jsonify({'ok': True, 'message': '✅ تم حذف الحصة بنجاح. السجل محذوف من قاعدة البيانات.'})


@bp.route('/api/version/create-next', methods=['POST'])
@login_required
@permission_required('timetable.edit')
@csrf_required
def timetable_version_create_next():
    """Open a fresh version for the next academic year for a department+semester,
    optionally copying entries from an existing source version.

    An explicit ``season`` (fall/spring) + ``year`` may be sent to choose the
    target term freely; otherwise the next season is derived automatically.
    If a version already exists for the chosen season+year, the request is
    rejected so the caller can ask for a different date.
    """
    data = request.get_json(silent=True) or {}
    source_version_id = data.get('version_id')
    if source_version_id:
        try:
            source_version_id = int(source_version_id)
        except (TypeError, ValueError):
            source_version_id = None
    copy_entries = bool(data.get('copy_entries', False))
    season = (data.get('season') or '').strip().lower()
    raw_year = data.get('year')
    year = None
    if raw_year is not None:
        try:
            year = int(raw_year)
        except (TypeError, ValueError):
            year = None
    db = get_db()

    source = None
    if source_version_id:
        source = db.execute(
            'SELECT id, department_id, semester FROM timetable_versions WHERE id = ?',
            (source_version_id,),
        ).fetchone()
    if not source:
        return jsonify({'ok': False, 'message': 'نسخة الجدول المطلوبة غير موجودة.'})

    dept_id = source['department_id']
    semester = source['semester']
    if not dept_id:
        return jsonify({'ok': False, 'message': 'النسخة لا تنتمي إلى أي قسم.'})
    if _is_hod() and dept_id != _hod_dept():
        return jsonify({'ok': False, 'message': 'لا يمكن إنشاء نسخة لقسم آخر.'})

    try:
        if season in ('fall', 'spring') and year:
            code = '{}_{}'.format(season, year)
            new_version_id, code = timetable_service.create_version_for_semester_code(
                db, dept_id, semester, code,
                source_version_id=source_version_id if copy_entries else None,
            )
            if not new_version_id:
                return jsonify({
                    'ok': False,
                    'duplicate': True,
                    'message': 'توجد نسخة لنفس «الفصل/العام» (' + code + ') مسبقًا — اختر تاريخًا أو فصلًا مختلفًا.',
                })
            url = url_for('timetable.timetable_department_view',
                          department_id=dept_id, semester=semester, version_id=new_version_id)
            return jsonify({
                'ok': True,
                'version_id': new_version_id,
                'academic_year': code,
                'message': '✅ تم إنشاء نسخة ' + code + ' بنجاح.'
                            + (' وتم نسخ الحصص من الجدول الأصلي.' if copy_entries else ''),
                'url': url,
            })
        new_version_id, year = timetable_service.create_version_for_next_year(
            db, dept_id, semester,
            source_version_id=source_version_id if copy_entries else None,
        )
    except Exception as e:
        logger.exception('Failed to create next-year version')
        return jsonify({'ok': False, 'message': f'❌ فشل إنشاء جدول العام القادم. السبب: {str(e)}'})

    url = url_for('timetable.timetable_department_view',
                  department_id=dept_id, semester=semester, version_id=new_version_id)
    return jsonify({
        'ok': True,
        'version_id': new_version_id,
        'academic_year': year,
        'message': f'✅ تم إنشاء نسخة العام الدراسي {year} بنجاح.'
                    + (' وتم نسخ الحصص من الجدول الأصلي.' if copy_entries else ''),
        'url': url,
    })


@bp.route('/api/available-rooms')
@login_required
@permission_required('timetable.view')
def timetable_available_rooms():
    db = get_db()
    day = request.args.get('day', '')
    semester = request.args.get('semester', type=int)
    period_code = request.args.get('period_code', '')
    exclude_id = request.args.get('exclude_id', type=int)
    start_time = request.args.get('start_time', '')
    end_time = request.args.get('end_time', '')
    hours = request.args.get('hours', 0, type=int)
    rooms = timetable_service.get_available_rooms(db, day, semester, period_code, exclude_id, start_time, end_time, hours)
    return ok({'rooms': rooms})


@bp.route('/api/available-teachers')
@login_required
@permission_required('timetable.view')
def timetable_available_teachers():
    db = get_db()
    day = request.args.get('day', '')
    semester = request.args.get('semester', type=int)
    period_code = request.args.get('period_code', '')
    exclude_id = request.args.get('exclude_id', type=int)
    start_time = request.args.get('start_time', '')
    end_time = request.args.get('end_time', '')
    hours = request.args.get('hours', 0, type=int)
    teachers = timetable_service.get_available_teachers(db, day, semester, period_code, exclude_id, start_time, end_time, hours)
    return ok({'teachers': teachers})


@bp.route('/teachers-schedule')
@login_required
@permission_required('timetable.view')
def teachers_schedule():
    db = get_db()
    user = current_user()
    teacher = db.execute('SELECT id, name, department_id FROM teachers WHERE user_id = ?', (session['user_id'],)).fetchone()
    days_order = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
    dept_colors = {}
    weekly = {d: [] for d in days_order}
    if teacher:
        rows = db.execute(
            '''SELECT t.id, t.period, t.semester, t.day, c.year, t.department_id,
                      t.course_id, t.teacher_id,
                      c.name as course_name, c.code as course_code,
                      r.name as room_name, r.capacity as room_capacity,
                      t.start_time, t.end_time,
                      d.name as department_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms r ON t.room_id = r.id
               LEFT JOIN departments d ON t.department_id = d.id
               WHERE t.teacher_id = ?
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY t.day, t.start_time''',
            (teacher['id'],)
        ).fetchall()
        for r in rows:
            if r['day'] in weekly:
                weekly[r['day']].append(dict(r))
    all_dept_names = set()
    for day_entries in weekly.values():
        for e in day_entries:
            if e.get('department_name'):
                all_dept_names.add(e['department_name'])
    palette = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#795548', '#607D8B']
    for i, name in enumerate(sorted(all_dept_names)):
        dept_colors[name] = palette[i % len(palette)]
    return render_template('timetable/teacher.html', user=user,
                          teacher=dict(teacher) if teacher else None,
                          weekly_schedule=weekly, days_order=days_order,
                          dept_colors=dept_colors)


@bp.route('/department-exam-view')
@login_required
@permission_required('timetable.view')
def department_exam_view():
    """Read-only department timetable view (exam/audit access)."""
    user_data = current_user()
    db = get_db()

    user_dept_id = _user_dept()
    dept_id = request.args.get('department_id', type=int)
    if user_dept_id:
        dept_id = user_dept_id

    if not dept_id:
        dept_id = _first_department_id(db)

    semester = request.args.get('semester', type=int)
    version_id = request.args.get('version_id', type=int)

    return _render_unified(
        db, session.get('role', ''), user_data, dept_id, semester, version_id,
        can_manage=False,
        can_switch_department=not user_dept_id,
        nav_active='timetable.timetable',
        is_rd=False,
    )