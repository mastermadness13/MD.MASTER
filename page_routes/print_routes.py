from flask import Blueprint, request, session, render_template, url_for, redirect, current_app

from flask_db import get_db
from security import login_required, permission_required
from security import current_user
from services import timetable_service, course_service, department_service, exam_service, public_service
from services import pdf_service
from services.search import build_course_search, build_teacher_search, build_room_search
from services.timetable_scope import (
    INVALID_SEMESTER_MESSAGE,
    InvalidSemesterError,
    allowed_semesters_for,
    semester_token,
)

bp = Blueprint('print_routes', __name__, url_prefix='/print')

DEPARTMENT_PALETTE = (
    '#166534', '#0e7490', '#b45309', '#7c3aed',
    '#be123c', '#1d4ed8', '#15803d', '#c2410c',
)


def _row_get(row, key, default=''):
    """قراءة حقل من صف قاعدة البيانات أو من قاموس."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


# /     /     >---- طباعة الجدول العام
@bp.route('/timetable')
@login_required
@permission_required('timetable.view')
def print_timetable():
    role = session.get('role', '')
    user_dept = session.get('department_id')
    selected_dept = None
    selected_semester = 1
    selected_section = None
    db = get_db()
    data = timetable_service.get_timetable_data(db, role, user_dept, selected_dept, selected_semester, selected_section)
    forms, vocab, syllabi_files = public_service.get_course_content_files(db)
    content_maps = {
        'form': {
            cid: {'id': item['id'], 'url': url_for('public_library.course_file', file_id=item['id'])}
            for cid, item in forms.items()
        },
        'vocab': {
            cid: {
                'id': item['id'],
                'originalFilename': item['original_filename'],
                'url': url_for('public_library.course_file', file_id=item['id']),
            }
            for cid, item in vocab.items()
        },
        'syllabus': {},
    }
    for key, item in syllabi_files.items():
        entry = {
            'id': item['id'],
            'url': url_for('public_library.course_file', file_id=item['id']),
            'teacher_id': item.get('teacher_id'),
            'course_id': item['course_id'],
        }
        content_maps['syllabus'][key] = entry
        if item.get('teacher_id') is None:
            content_maps['syllabus']['*:{}'.format(item['course_id'])] = entry
    return render_template('timetable/list.html', days_list=timetable_service.DAYS,
                           user=current_user(), content_maps=content_maps, **data)


# /     /     >---- طباعة قائمة المقررات مع الأقسام المرتبطة
@bp.route('/courses')
@login_required
@permission_required('reports.view')
def print_courses():
    db = get_db()
    query, params, _dept_filter = build_course_search('', '', None, 1)
    rows = [dict(r) for r in db.execute(query, params).fetchall()]
    departments = [dict(r) for r in db.execute(
        'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()]
    course_depts = course_service.get_course_dept_mapping(db, [r['id'] for r in rows])
    course_service.attach_course_related_data(db, rows)
    return render_template('print/lists/course.html', courses=rows,
                           course_depts=course_depts, departments=departments,
                           user=current_user())


# /     /     >---- طباعة قائمة الأقسام
@bp.route('/lists/departments')
@login_required
@permission_required('departments.view')
def print_list_departments():
    db = get_db()
    departments = department_service.list_departments(db)
    return render_template('print/lists/department.html', departments=departments,
                           user=current_user())


# /     /     >---- طباعة قائمة الأساتذة
@bp.route('/lists/teachers')
@login_required
@permission_required('teachers.view')
def print_list_teachers():
    db = get_db()
    query, params, _dept_filter = build_teacher_search('', '', None, 1)
    teachers = [dict(r) for r in db.execute(query, params).fetchall()]
    return render_template('print/lists/teacher.html', teachers=teachers,
                           user=current_user())


# /     /     >---- طباعة قائمة القاعات
@bp.route('/lists/rooms')
@login_required
@permission_required('rooms.view')
def print_list_rooms():
    db = get_db()
    query, params, _dept_filter = build_room_search('', '', 1)
    rooms = [dict(r) for r in db.execute(query, params).fetchall()]
    return render_template('print/lists/room.html', rooms=rooms,
                           user=current_user())


# /     /     >---- بيانات جدول الامتحانات (مشتركة بين المعاينة و PDF)
def _exam_schedule_view():
    db = get_db()
    dept_id = request.args.get('dept_id', type=int)
    role = session.get('role', '')
    if role == 'head_of_department':
        dept_id = session.get('hod_department_id')
    return exam_service.build_exam_print_view(db, dept_id=dept_id if dept_id else None)


# /     /     >---- جدول امتحانات الأقسام (لرئيس القسم قسمه فقط)
@bp.route('/exams/schedule')
@login_required
@permission_required('exams.view')
def print_exams_schedule():
    return render_template('print/exams/schedule.html', view=_exam_schedule_view(),
                           user=current_user())


# /     /     >---- جدول الامتحانات كملف PDF جاهز للتنزيل
@bp.route('/exams/schedule.pdf')
@login_required
@permission_required('exams.view')
def pdf_exams_schedule():
    view = _exam_schedule_view()
    departments = view.get('departments') or []
    name = _row_get(departments[0], 'name') if len(departments) == 1 else ''
    label = 'جدول الامتحانات%s' % (' - %s' % name if name else '')
    return pdf_service.template_pdf_response(
        'print/pdf/exams_schedule.html', download_name=label, view=view)


# /     /     >---- بيانات جدول قسم محدد حسب النسخة النشطة
def _department_timetable_payload():
    """(payload, redirect) — واحد منهما فقط غير None."""
    db = get_db()
    role = session.get('role', '')
    dept_id = request.args.get('department_id', type=int)
    if role == 'head_of_department':
        dept_id = session.get('hod_department_id')
    else:
        dept_id = dept_id or session.get('department_id')
    if not dept_id:
        return None, redirect(url_for('timetable.timetable_department_view'))
    dept_row = db.execute(
        'SELECT name, semesters FROM departments WHERE id = ?', (dept_id,)
    ).fetchone()
    if not dept_row:
        return None, redirect(url_for('timetable.timetable_department_view'))
    semester = request.args.get('semester', type=int)
    version_id = request.args.get('version_id', type=int)
    current_app.logger.debug(
        '[TIMETABLE PRINT] dept=%s semester=%s version=%s', dept_id, semester, version_id)
    if semester is None:
        # لا فصل صريح في الرابط — نعيد إلى الجدول الموحّد ليقرر حالة الواجهة
        return None, redirect(url_for('timetable.timetable_department_view',
                                      department_id=dept_id, version_id=version_id))
    allowed = allowed_semesters_for(dept_row)
    if semester not in allowed:
        return None, redirect(url_for('print_routes.print_timetable_department',
                                      department_id=dept_id, semester=allowed[0],
                                      version_id=version_id))
    payload = timetable_service.get_department_view(db, dept_id, semester, version_id)
    try:
        payload['fingerprint'] = semester_token(db, dept_id, semester)
    except InvalidSemesterError:
        payload['fingerprint'] = ''
    return payload, None


# /     /     >---- طباعة جدول قسم محدد حسب النسخة النشطة
@bp.route('/timetables/department')
@login_required
@permission_required('timetable.view')
def print_timetable_department():
    payload, redirect_response = _department_timetable_payload()
    if redirect_response is not None:
        return redirect_response
    return render_template('print/timetables/department.html', payload=payload,
                           user=current_user())


# /     /     >---- جدول القسم كملف PDF جاهز للتنزيل
@bp.route('/timetables/department.pdf')
@login_required
@permission_required('timetable.view')
def pdf_timetable_department():
    payload, redirect_response = _department_timetable_payload()
    if redirect_response is not None:
        return redirect_response
    dept_name = _row_get(_row_get(payload, 'dept'), 'name')
    return pdf_service.template_pdf_response(
        'print/pdf/timetable_department.html',
        download_name='الجدول الأسبوعي%s' % (' - %s' % dept_name if dept_name else ''),
        payload=payload)


# /     /     >---- بيانات جدول أستاذ أسبوعياً مع ألوان حسب القسم
def _teacher_timetable_data():
    db = get_db()
    teacher_id = request.args.get('teacher_id', type=int)
    if teacher_id:
        teacher = db.execute(
            'SELECT id, name, department_id FROM teachers WHERE id = ?',
            (teacher_id,)
        ).fetchone()
    else:
        teacher = db.execute(
            'SELECT id, name, department_id FROM teachers WHERE user_id = ?',
            (session['user_id'],)
        ).fetchone()
    days_order = list(timetable_service.DAYS)
    weekly = timetable_service.build_teacher_weekly(
        db, teacher['id'], days_order) if teacher else {}
    all_dept_names = sorted({e['department_name'] for day_entries in weekly.values()
                             for e in day_entries if e.get('department_name')})
    dept_colors = {name: DEPARTMENT_PALETTE[i % len(DEPARTMENT_PALETTE)]
                   for i, name in enumerate(all_dept_names)}
    return dict(teacher) if teacher else None, days_order, weekly, dept_colors


# /     /     >---- طباعة جدول أستاذ أسبوعياً مع ألوان حسب القسم
@bp.route('/timetables/teacher')
@login_required
@permission_required('timetable.view')
def print_timetable_teacher():
    teacher, days_order, weekly, dept_colors = _teacher_timetable_data()
    return render_template('print/timetables/teacher.html', user=current_user(),
                           teacher=teacher,
                           weekly_schedule=weekly, days_order=days_order,
                           dept_colors=dept_colors)


# /     /     >---- جدول الأستاذ كملف PDF جاهز للتنزيل
@bp.route('/timetables/teacher.pdf')
@login_required
@permission_required('timetable.view')
def pdf_timetable_teacher():
    teacher, days_order, weekly, dept_colors = _teacher_timetable_data()
    return pdf_service.template_pdf_response(
        'print/pdf/timetable_teacher.html',
        download_name='الجدول الأسبوعي%s' % (
            ' - %s' % _row_get(teacher, 'name') if teacher else ''),
        teacher=teacher, weekly_schedule=weekly, days_order=days_order,
        dept_colors=dept_colors)


# /     /     >---- بيانات جميع جداول الأقسام في عرض واحد
def _all_timetable_data():
    db = get_db()
    role = session.get('role', '')
    user_dept = session.get('department_id')
    view = timetable_service.get_combined_timetable_view(db, role, user_dept)
    return (view['departments'], view['days'],
            view.get('academic_label', ''))


# /     /     >---- طباعة جميع جداول الأقسام في عرض واحد
@bp.route('/timetables/all')
@login_required
@permission_required('timetable.view')
def print_timetable_all():
    sections, days, academic_label = _all_timetable_data()
    return render_template('print/timetables/all.html', sections=sections,
                           days=days, academic_label=academic_label,
                           user=current_user())


# /     /     >---- جداول كل الأقسام كملف PDF جاهز للتنزيل
@bp.route('/timetables/all.pdf')
@login_required
@permission_required('timetable.view')
def pdf_timetable_all():
    sections, days, academic_label = _all_timetable_data()
    return pdf_service.template_pdf_response(
        'print/pdf/timetable_all.html',
        download_name='الجداول الدراسية - جميع الأقسام',
        sections=sections, days=days, academic_label=academic_label)