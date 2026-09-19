from flask import Blueprint, request, session, render_template, url_for

from flask_db import get_db
from security import login_required, permission_required
from security import current_user
from services import timetable_service, course_service, department_service, exam_service, public_service
from services.search import build_course_search, build_teacher_search, build_room_search

bp = Blueprint('print_routes', __name__, url_prefix='/print')


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


# /     /     >---- طباعة جدول امتحانات الأقسام (لرئيس القسم قسمه فقط)
@bp.route('/exams/schedule')
@login_required
@permission_required('exams.view')
def print_exams_schedule():
    db = get_db()
    dept_id = request.args.get('dept_id', type=int)
    role = session.get('role', '')
    user_data = current_user()
    if role == 'head_of_department':
        dept_id = session.get('hod_department_id')
    view = exam_service.build_exam_print_view(db, dept_id=dept_id if dept_id else None)
    return render_template('print/exams/schedule.html', view=view,
                           user=current_user())


# /     /     >---- طباعة جدول قسم محدد حسب النسخة النشطة
@bp.route('/timetables/department')
@login_required
@permission_required('timetable.view')
def print_timetable_department():
    db = get_db()
    dept_id = request.args.get('department_id', type=int) or session.get('hod_department_id')
    semester = request.args.get('semester', type=int) or 1
    version_id = request.args.get('version_id', type=int)
    payload = timetable_service.get_department_view(db, dept_id, semester, version_id)
    return render_template('print/timetables/department.html', payload=payload,
                           user=current_user())


# /     /     >---- طباعة جدول أستاذ أسبوعياً مع ألوان حسب القسم
@bp.route('/timetables/teacher')
@login_required
@permission_required('timetable.view')
def print_timetable_teacher():
    db = get_db()
    teacher_id = request.args.get('teacher_id', type=int)
    teacher = None
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
    weekly = timetable_service.build_teacher_weekly(db, teacher['id'], days_order) if teacher else {}
    all_dept_names = sorted({e['department_name'] for day_entries in weekly.values() for e in day_entries if e.get('department_name')})
    # /     /     >---- لوحة ألوان لأسماء الأقسام المختلفة
    palette = [
        '#166534', '#0e7490', '#b45309', '#7c3aed',
        '#be123c', '#1d4ed8', '#15803d', '#c2410c',
    ]
    dept_colors = {name: palette[i % len(palette)] for i, name in enumerate(all_dept_names)}
    return render_template('print/timetables/teacher.html', user=current_user(),
                           teacher=dict(teacher) if teacher else None,
                           weekly_schedule=weekly, days_order=days_order,
                           dept_colors=dept_colors)


# /     /     >---- طباعة جميع جداول الأقسام في عرض واحد
@bp.route('/timetables/all')
@login_required
@permission_required('timetable.view')
def print_timetable_all():
    db = get_db()
    role = session.get('role', '')
    user_dept = session.get('department_id')
    view = timetable_service.get_combined_timetable_view(db, role, user_dept)
    return render_template('print/timetables/all.html', sections=view['departments'],
                           days=view['days'], academic_label=view.get('academic_label', ''),
                           user=current_user())