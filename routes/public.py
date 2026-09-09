from flask import Blueprint, jsonify, redirect, url_for

from flask_db import get_db
from services import public_service, exam_service

bp = Blueprint('public', __name__)

_DEPT_STYLE = {
    'القسم العام': {'icon': 'school', 'accentColor': '#6b21a8'},
    'قسم الاتصالات': {'icon': 'settings_input_antenna', 'accentColor': '#d97706'},
    'قسم الحاسوب': {'icon': 'memory', 'accentColor': '#7c3aed'},
    'قسم المدني': {'icon': 'architecture', 'accentColor': '#ea580c'},
    'قسم المعماري': {'icon': 'domain', 'accentColor': '#059669'},
    'قسم النفط': {'icon': 'oil_barrel', 'accentColor': '#92400e'},
}


def _dept_style(name):
    return _DEPT_STYLE.get(name or '', {'icon': 'domain', 'accentColor': '#6b21a8'})


@bp.route('/public/departments')
def departments():
    return redirect('/index.html#home')


@bp.route('/public/departments/<int:department_id>')
def department_detail(department_id):
    return redirect('/index.html#home')


@bp.route('/public/timetables')
def timetables():
    return redirect('/index.html#timetables')


@bp.route('/public/api/timetables')
def public_timetables_api():
    db = get_db()
    departments = []
    for d in public_service.get_departments(db):
        style = _dept_style(d['name'])
        departments.append({
            'id': d['id'],
            'name': d['name'],
            'semesters': d['semesters'],
            'hasSections': bool(d['has_sections']),
            'icon': d.get('icon') or style['icon'],
            'accentColor': d.get('accent_color') or style['accentColor'],
        })
    periods = []
    for p in public_service.get_periods(db):
        if p.get('is_enabled') is False:
            continue
        periods.append({
            'code': p['code'],
            'label': p.get('label') or ('الفترة ' + p['code']),
            'startTime': p.get('start_time') or '',
            'endTime': p.get('end_time') or '',
        })
    vocab = {}
    for course_id, item in public_service.get_course_vocabularies(db).items():
        vocab[course_id] = {
            'id': item['id'],
            'originalFilename': item['original_filename'],
            'url': url_for('public_library.course_file', file_id=item['id']),
        }
    syllabi = {}
    for key, item in public_service.get_teacher_syllabus_files(db).items():
        entry = {
            'id': item['id'],
            'url': url_for('public_library.course_file', file_id=item['id']),
        }
        syllabi[key] = entry
        if item.get('teacher_id') is None:
            syllabi[f"*:{item['course_id']}"] = entry
    forms = {}
    for course_id, item in public_service.get_approved_course_forms(db).items():
        forms[course_id] = {
            'id': item['id'],
            'url': url_for('public_library.course_file', file_id=item['id']),
        }
    entries = []
    for e in public_service.get_active_entries(db):
        cid = e.get('course_id')
        tid = e.get('teacher_id')
        entries.append({
            'id': e['id'],
            'day': e['day'],
            'semester': e['semester'],
            'departmentId': e['department_id'],
            'studentSection': e['student_section'],
            'courseId': cid,
            'teacherId': tid,
            'courseName': e.get('course_name'),
            'courseCode': e.get('course_code'),
            'teacherName': e.get('teacher_name'),
            'roomName': e.get('room_name'),
            'period': e['period'],
            'startTime': e.get('start_time') or '',
            'endTime': e.get('end_time') or '',
            'formFile': forms.get(cid) if cid else None,
            'vocabFile': vocab.get(cid) if cid else None,
            'syllabusFile': (syllabi.get(f'{tid}:{cid}') or syllabi.get(f'*:{cid}')) if cid else None,
        })
    active_sem = public_service.get_active_semester(db)
    return jsonify({'departments': departments, 'periods': periods, 'entries': entries,
                    'vocab': vocab, 'syllabus': syllabi,
                    'academic_semester': active_sem})


@bp.route('/public/api/courses')
def public_courses_api():
    db = get_db()
    depts = public_service.get_departments(db)
    departments = [{'id': d['id'], 'name': d['name']} for d in depts]
    dept_names = {d['id']: d['name'] for d in depts}
    course_dept = public_service.get_course_department_ids(db)
    vocab = {}
    for course_id, item in public_service.get_course_vocabularies(db).items():
        vocab[course_id] = {
            'id': item['id'],
            'originalFilename': item['original_filename'],
            'url': url_for('public_library.course_file', file_id=item['id']),
        }
    files_by_course = public_service.get_course_syllabus_files(db)
    forms_by_course = public_service.get_approved_course_forms(db)
    timetable_course_ids = public_service.get_active_timetable_course_ids(db)
    courses = []
    for c in public_service.get_courses(db):
        cid = c['id']
        syllabus_files = []
        for item in files_by_course.get(cid, []):
            syllabus_files.append({
                'id': item['id'],
                'teacherId': item['teacher_id'],
                'teacherName': item['teacher_name'],
                'url': url_for('public_library.course_file', file_id=item['id']),
            })
        form_item = forms_by_course.get(cid)
        did = c['department_id'] or course_dept.get(cid)
        department_name = dept_names.get(did)
        if not department_name and isinstance(c.get('department'), str):
            department_name = c.get('department')
        courses.append({
            'id': cid,
            'code': c['code'],
            'name': c['name'],
            'departmentId': did,
            'departmentName': department_name or '',
            'year': c['year'],
            'semester': c['semester'],
            'theoreticalHours': c['theoretical_hours'],
            'practicalHours': c['practical_hours'],
            'totalHours': c['total_hours'],
            'accreditation': c.get('accreditation'),
            'icon': c.get('icon'),
            'inTimetable': cid in timetable_course_ids,
            'vocabFile': vocab.get(cid),
            'syllabusFiles': syllabus_files,
            'formFile': {
                'id': form_item['id'],
                'originalFilename': form_item['original_filename'],
                'url': url_for('public_library.course_file', file_id=form_item['id']),
            } if form_item else None,
        })
    return jsonify({'departments': departments, 'courses': courses})


@bp.route('/public/api/exams')
def public_exams_api():
    """Published exam schedule only — real rows from exam_schedule."""
    db = get_db()
    exams = []
    for e in public_service.get_published_exams(db):
        exams.append({
            'id': e['id'],
            'courseId': e.get('course_id'),
            'courseName': e.get('course_name'),
            'courseCode': e.get('course_code'),
            'departmentId': e.get('department_id'),
            'examDate': e.get('exam_date') or '',
            'startTime': e.get('start_time') or '',
            'endTime': e.get('end_time') or '',
            'roomId': e.get('room_id'),
            'roomName': e.get('room_name'),
            'semester': e.get('semester'),
            'status': e.get('status'),
        })
    settings_row = db.execute(
        'SELECT session_a, session_b, session_c FROM exam_settings LIMIT 1'
    ).fetchone()
    sessions = []
    if settings_row:
        for key, label in [
            ('session_a', 'الفترة الأولى'),
            ('session_b', 'الفترة الثانية'),
            ('session_c', 'الفترة الثالثة'),
        ]:
            val = settings_row[key] if key in settings_row.keys() else ''
            if val:
                sessions.append({'label': label, 'time': val})
    return jsonify({'exams': exams, 'sessions': sessions})


@bp.route('/public/api/exam-schedule')
def public_exam_schedule_api():
    """Public exam schedule — same data shape as /api/exams/schedule (read-only)."""
    db = get_db()
    departments = exam_service.build_dept_exam_data(db)
    dept_stats = {}
    for dept in departments:
        did = dept['id']
        total = 0
        rooms = set()
        for slot in dept.get('time_slots', []):
            for cell in (slot.get('cells') or {}).values():
                if cell:
                    total += 1
                    if cell.get('room_name'):
                        rooms.add(cell['room_name'])
        dept_stats[did] = {'exam_count': total, 'room_count': len(rooms)}
    return jsonify(exam_service.build_exam_schedule_view(db, departments, dept_stats))


@bp.route('/public/exams')
def exams():
    return redirect('/index.html#exams')


@bp.route('/public/courses')
def courses():
    return redirect('/index.html#library')


def home_context():
    db = get_db()
    return {
        'departments': public_service.get_departments(db),
        'stats': public_service.get_home_stats(db),
    }
