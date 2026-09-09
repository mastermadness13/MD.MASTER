from datetime import datetime

from services import classroom_request_service as crs
from services import notification_service
from services import course_service


def get_exam_dept_dashboard_data(db):
    """Data for the Exam Department sub-admin dashboard."""
    data = {}
    today_str = datetime.now().strftime('%Y-%m-%d')

    data['total_exams'] = db.execute(
        'SELECT COUNT(*) FROM exam_schedule'
    ).fetchone()[0]

    data['upcoming_exams'] = db.execute(
        "SELECT COUNT(*) FROM exam_schedule WHERE date(exam_date) >= date('now')"
    ).fetchone()[0]

    data['past_exams'] = db.execute(
        "SELECT COUNT(*) FROM exam_schedule WHERE date(exam_date) < date('now')"
    ).fetchone()[0]

    data['total_rooms'] = db.execute(
        'SELECT COUNT(*) FROM rooms WHERE deleted_at IS NULL'
    ).fetchone()[0]

    data['total_courses'] = db.execute(
        'SELECT COUNT(*) FROM courses WHERE deleted_at IS NULL'
    ).fetchone()[0]

    data['total_departments'] = db.execute(
        'SELECT COUNT(*) FROM departments WHERE deleted_at IS NULL'
    ).fetchone()[0]

    data['exam_periods'] = db.execute(
        'SELECT COUNT(*) FROM exam_settings'
    ).fetchone()[0]

    rows = db.execute(
        '''SELECT es.*, c.name as course_name, c.code as course_code,
                  r.name as room_name
           FROM exam_schedule es
           LEFT JOIN courses c ON es.course_id = c.id
           LEFT JOIN rooms r ON es.room_id = r.id
           WHERE es.exam_date >= ?
           ORDER BY es.exam_date ASC LIMIT 10''',
        (today_str,)
    ).fetchall()
    data['upcoming_exams_list'] = [dict(r) for r in rows]

    rows = db.execute(
        '''SELECT es.*, c.name as course_name, c.code as course_code,
                  r.name as room_name
           FROM exam_schedule es
           LEFT JOIN courses c ON es.course_id = c.id
           LEFT JOIN rooms r ON es.room_id = r.id
           WHERE es.exam_date >= ?
           ORDER BY es.exam_date ASC LIMIT 5''',
        (today_str,)
    ).fetchall()
    data['next_exams'] = [dict(r) for r in rows]

    return data


def get_rnd_dept_dashboard_data(db):
    """Data for the R&D Department sub-admin dashboard."""
    data = {}

    data['total_courses'] = db.execute(
        'SELECT COUNT(*) FROM courses WHERE deleted_at IS NULL'
    ).fetchone()[0]

    data['total_departments'] = db.execute(
        "SELECT COUNT(*) FROM departments WHERE type = 'academic' AND deleted_at IS NULL"
    ).fetchone()[0]

    data['total_teachers'] = db.execute(
        'SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL'
    ).fetchone()[0]

    data['total_timetable_entries'] = db.execute(
        'SELECT COUNT(*) FROM timetable WHERE deleted_at IS NULL '
        'AND (version_id IS NULL OR version_id IN '
        '(SELECT id FROM timetable_versions WHERE status = \'active\'))'
    ).fetchone()[0]

    rows = db.execute(
        '''SELECT c.*, d.name as department_name,
                  CASE WHEN EXISTS (
                      SELECT 1 FROM course_files cf
                      WHERE cf.course_id = c.id AND cf.file_type = 'syllabus'
                  ) THEN 1 ELSE 0 END AS has_syllabus,
                  (SELECT cf2.id FROM course_files cf2
                   WHERE cf2.course_id = c.id AND cf2.file_type = 'syllabus'
                   ORDER BY cf2.created_at DESC LIMIT 1) AS syllabus_file_id,
                  (SELECT cf3.id FROM course_files cf3
                   WHERE cf3.course_id = c.id AND cf3.file_type = 'form'
                     AND cf3.status IN ('approved', 'published')
                   ORDER BY cf3.created_at DESC LIMIT 1) AS form_file_id,
                  (SELECT cs.id FROM course_content_submissions cs
                   WHERE cs.course_id = c.id
                   ORDER BY COALESCE(cs.submitted_at, cs.created_at) DESC
                   LIMIT 1) AS form_submission_id
           FROM courses c
           LEFT JOIN departments d ON c.department_id = d.id
           WHERE c.deleted_at IS NULL
           ORDER BY has_syllabus DESC, c.name'''
    ).fetchall()
    data['courses_list'] = course_service.attach_course_related_data(
        db, [dict(r) for r in rows])

    dept_rows = db.execute(
        """SELECT d.id, d.name,
                  (SELECT COUNT(*) FROM courses WHERE department_id = d.id AND deleted_at IS NULL) as course_count
           FROM departments d
           WHERE d.type = 'academic' AND d.deleted_at IS NULL
           ORDER BY d.name"""
    ).fetchall()
    data['departments'] = [dict(r) for r in dept_rows]

    return data


def get_hod_dashboard_data(db, dept_id):
    hod_data = {}
    dept_row = db.execute('SELECT name FROM departments WHERE id = ?', (dept_id,)).fetchone()
    hod_data['department_name'] = dept_row['name'] if dept_row else None
    hod_data['department_id'] = dept_id
    today_str = datetime.now().strftime('%Y-%m-%d')
    arabic_days = {0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس', 4: 'الجمعة', 5: 'السبت', 6: 'الأحد'}
    today_day = arabic_days.get(datetime.now().weekday())
    if today_day == 'الجمعة':
        today_day = None

    if today_day is not None:
        rows = db.execute(
            '''SELECT fa.*, t.name as teacher_name
               FROM faculty_attendance fa
               LEFT JOIN teachers t ON fa.teacher_id = t.id
               WHERE fa.date = ? AND (
                   SELECT COUNT(*) FROM teacher_departments td
                   WHERE td.teacher_id = fa.teacher_id AND td.department_id = ?
               ) > 0
               ORDER BY fa.created_at DESC''',
            (today_str, dept_id)
        ).fetchall()
        hod_data['faculty_attendance'] = [dict(r) for r in rows]
        hod_data['faculty_present'] = sum(1 for r in rows if r['status'] == 'present')
        hod_data['faculty_late'] = sum(1 for r in rows if r['status'] == 'late')
        hod_data['faculty_absent'] = sum(1 for r in rows if r['status'] == 'absent')
    else:
        hod_data['faculty_attendance'] = []
        hod_data['faculty_present'] = hod_data['faculty_late'] = hod_data['faculty_absent'] = 0

    if today_day is not None:
        rows = db.execute(
            '''SELECT t.*, c.name as course_name, tc.name as teacher_name, r.name as room_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN teachers tc ON t.teacher_id = tc.id
               LEFT JOIN rooms r ON t.room_id = r.id
               WHERE t.day = ? AND (t.department_id = ? OR ? IS NULL)
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY t.period''',
            (today_day, dept_id, dept_id)
        ).fetchall()
        hod_data['occupied_rooms'] = [dict(r) for r in rows]
        hod_data['occupied_rooms_count'] = len(rows)
    else:
        hod_data['occupied_rooms'] = []
        hod_data['occupied_rooms_count'] = 0

    rows = db.execute('SELECT * FROM rooms WHERE deleted_at IS NULL ORDER BY name').fetchall()
    hod_data['all_rooms'] = [dict(r) for r in rows]
    hod_data['total_rooms'] = len(rows)
    occupied_room_ids = {r['room_id'] for r in hod_data['occupied_rooms'] if r.get('room_id')}
    hod_data['occupied_room_ids'] = list(occupied_room_ids)
    hod_data['available_rooms'] = [r for r in hod_data['all_rooms'] if r['id'] not in occupied_room_ids]

    weekly_rows = db.execute(
        '''SELECT t.day, t.period, t.room_id, c.name as course_name, tc.name as teacher_name, r.name as room_name
           FROM timetable t
           LEFT JOIN courses c ON t.course_id = c.id
           LEFT JOIN teachers tc ON t.teacher_id = tc.id
           LEFT JOIN rooms r ON t.room_id = r.id
           WHERE (t.department_id = ? OR ? IS NULL)
           AND (t.version_id IS NULL OR t.version_id IN
               (SELECT id FROM timetable_versions WHERE status = 'active'))
           ORDER BY t.day, t.period''',
        (dept_id, dept_id)
    ).fetchall()
    weekly_timetable = {}
    for row in weekly_rows:
        day = row['day']
        if day not in weekly_timetable:
            weekly_timetable[day] = []
        weekly_timetable[day].append(dict(row))
    hod_data['weekly_timetable'] = weekly_timetable
    hod_data['periods'] = [dict(r) for r in db.execute(
        'SELECT * FROM period_settings ORDER BY sort_order'
    ).fetchall()]
    hod_data['active_days'] = list(hod_data['weekly_timetable'].keys())
    room_schedule = {}
    for day_name, day_entries in hod_data['weekly_timetable'].items():
        for entry in day_entries:
            rid = entry.get('room_id')
            if rid:
                if rid not in room_schedule:
                    room_schedule[rid] = {}
                if day_name not in room_schedule[rid]:
                    room_schedule[rid][day_name] = []
                room_schedule[rid][day_name].append({
                    'period': entry.get('period', ''),
                    'teacher_name': entry.get('teacher_name', ''),
                })
    hod_data['room_schedule'] = room_schedule

    rows = db.execute(
        '''SELECT r.*, t.name as teacher_name
           FROM teacher_requests r
           LEFT JOIN teachers t ON r.teacher_id = t.id
           WHERE r.status = 'pending' AND (r.department_id = ? OR ? IS NULL)
           ORDER BY r.created_at DESC LIMIT 10''',
        (dept_id, dept_id)
    ).fetchall()
    hod_data['pending_requests'] = [dict(r) for r in rows]
    hod_data['pending_requests_count'] = len(rows)

    hod_data['departments'] = [dict(r) for r in db.execute(
        'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()]
    dept_rows_raw = db.execute(
        '''SELECT d.id,
                  (SELECT COUNT(*) FROM course_departments WHERE department_id = d.id) as total,
                  (SELECT COUNT(DISTINCT course_id) FROM timetable WHERE department_id = d.id
                   AND (version_id IS NULL OR version_id IN
                       (SELECT id FROM timetable_versions WHERE status = 'active'))) as assigned
           FROM departments d
           WHERE d.hidden = 0 AND d.deleted_at IS NULL'''
    ).fetchall()
    dept_courses = {}
    for dr in dept_rows_raw:
        total = dr['total']
        assigned = dr['assigned']
        dept_courses[dr['id']] = {
            'total': total,
            'assigned': assigned,
            'percentage': round((assigned / total * 100)) if total > 0 else 0
        }
    hod_data['dept_courses'] = dept_courses
    hod_data['total_courses'] = db.execute(
        'SELECT COUNT(*) FROM course_departments WHERE department_id = ?', (dept_id,)
    ).fetchone()[0]
    if today_day is not None:
        hod_data['today_entries_count'] = db.execute(
            '''SELECT COUNT(*) FROM timetable t
               WHERE t.day = ? AND (t.department_id = ? OR ? IS NULL)
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))''',
            (today_day, dept_id, dept_id)
        ).fetchone()[0]
    else:
        hod_data['today_entries_count'] = 0
    hod_data['pending_messages_count'] = db.execute(
        '''SELECT COUNT(*) FROM teacher_messages
           WHERE status = 'pending' AND (department_id = ? OR ? IS NULL)''',
        (dept_id, dept_id)
    ).fetchone()[0]

    hod_data['pending_classroom_changes_count'] = crs.get_pending_count(db, dept_id)
    hod_data['pending_classroom_changes'] = crs.get_recent_pending(db, dept_id)

    hod_data['teachers_list'] = [dict(r) for r in db.execute(
        '''SELECT tc.id, tc.name, d.name AS department_name,
                  (SELECT COUNT(*) FROM timetable t
                   WHERE t.teacher_id = tc.id AND t.deleted_at IS NULL
                   AND (t.version_id IS NULL OR t.version_id IN
                       (SELECT id FROM timetable_versions WHERE status = 'active'))) AS course_count
           FROM teachers tc
           LEFT JOIN departments d ON tc.department_id = d.id
           WHERE tc.deleted_at IS NULL
           AND (? IS NULL OR EXISTS (
               SELECT 1 FROM teacher_departments tdx
               WHERE tdx.teacher_id = tc.id AND tdx.department_id = ?
           ))
           ORDER BY tc.name''',
        (dept_id, dept_id)
    ).fetchall()]

    return hod_data


def get_teacher_dashboard_data(db, user_id):
    teacher_data = {}
    teacher_row = db.execute('SELECT * FROM teachers WHERE user_id = ?', (user_id,)).fetchone()
    teacher_data['teacher'] = dict(teacher_row) if teacher_row else None
    teacher_id = teacher_row['id'] if teacher_row else None

    dept_name = None
    if teacher_row and teacher_row['department_id']:
        dept = db.execute('SELECT name FROM departments WHERE id = ?', (teacher_row['department_id'],)).fetchone()
        dept_name = dept['name'] if dept else teacher_row['department']
    elif teacher_row and teacher_row['department']:
        dept_name = teacher_row['department']
    teacher_data['dept_name'] = dept_name

    arabic_days = {0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس', 4: 'الجمعة', 5: 'السبت', 6: 'الأحد'}
    days_order = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
    today_day = arabic_days.get(datetime.now().weekday())
    now = datetime.now()
    current_time = now.strftime('%H:%M')

    # ── Today's entries with period times ──────────────────────────
    if teacher_id and today_day and today_day != 'الجمعة':
        rows = db.execute(
            '''SELECT t.*, c.name as course_name, c.year as course_year, c.code as course_code,
                      r.name as room_name, r.capacity as room_capacity,
                      t.start_time, t.end_time,
                      d.name as department_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms r ON t.room_id = r.id
               LEFT JOIN departments d ON t.department_id = d.id
               WHERE t.teacher_id = ? AND t.day = ?
               AND t.deleted_at IS NULL
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY t.start_time''',
            (teacher_id, today_day)
        ).fetchall()
        teacher_data['today_entries'] = [dict(r) for r in rows]
        # Current lecture detection
        current_lecture = None
        for entry in teacher_data['today_entries']:
            if entry.get('start_time') and entry.get('end_time'):
                if entry['start_time'] <= current_time < entry['end_time']:
                    current_lecture = entry
                    break
        # If no current lecture, find the next one
        if not current_lecture:
            next_lecture = None
            for entry in teacher_data['today_entries']:
                if entry.get('start_time') and entry['start_time'] > current_time:
                    next_lecture = entry
                    break
            teacher_data['next_lecture'] = next_lecture
        teacher_data['current_lecture'] = current_lecture
        teacher_data['lecture_state'] = (
            'in_class' if current_lecture
            else 'upcoming' if teacher_data.get('next_lecture')
            else 'free_day'
        )
    else:
        teacher_data['today_entries'] = []
        teacher_data['current_lecture'] = None
        teacher_data['next_lecture'] = None
        teacher_data['lecture_state'] = 'free_day'

    # ── Full weekly schedule ──────────────────────────────────────
    weekly_schedule = {}
    if teacher_id:
        for day_name in days_order:
            day_entries = db.execute(
                '''SELECT t.period, t.semester, c.name as course_name, c.year as course_year,
                          r.name as room_name, t.start_time, t.end_time
                   FROM timetable t
                   LEFT JOIN courses c ON t.course_id = c.id
                   LEFT JOIN rooms r ON t.room_id = r.id
                   WHERE t.teacher_id = ? AND t.day = ? AND t.deleted_at IS NULL
                   AND (t.version_id IS NULL OR t.version_id IN
                       (SELECT id FROM timetable_versions WHERE status = 'active'))
                   ORDER BY t.start_time''',
                (teacher_id, day_name)
            ).fetchall()
            weekly_schedule[day_name] = [dict(r) for r in day_entries]
    teacher_data['weekly_schedule'] = weekly_schedule
    teacher_data['days_order'] = days_order

    # ── Teaching assignments (courses with rooms/semesters) ───────
    if teacher_id:
        rows = db.execute(
            '''SELECT DISTINCT c.id, c.name, c.code, c.year, c.semester, c.department,
                      t.room_id, r.name as room_name, t.day, t.period,
                      t.start_time, t.end_time
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms r ON t.room_id = r.id
               WHERE t.teacher_id = ? AND t.deleted_at IS NULL
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY c.name''',
            (teacher_id,)
        ).fetchall()
        teacher_data['assignments'] = [dict(r) for r in rows if r['id']]
    else:
        teacher_data['assignments'] = []

    # ── Classroom change requests ─────────────────────────────────
    if teacher_id:
        rows = db.execute(
            '''SELECT r.*, cr.name as current_room_name, rr.name as requested_room_name,
                      c.name as course_name
               FROM classroom_change_requests r
               LEFT JOIN timetable t ON r.schedule_id = t.id
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms cr ON r.current_classroom_id = cr.id
               LEFT JOIN rooms rr ON r.requested_classroom_id = rr.id
               WHERE r.teacher_id = ?
               ORDER BY r.created_at DESC LIMIT 5''',
            (teacher_id,)
        ).fetchall()
        teacher_data['classroom_requests'] = [dict(r) for r in rows]

        counts = db.execute(
            '''SELECT status, COUNT(*) as cnt
               FROM classroom_change_requests
               WHERE teacher_id = ?
               GROUP BY status''',
            (teacher_id,)
        ).fetchall()
        teacher_data['classroom_request_counts'] = {r['status']: r['cnt'] for r in counts}
    else:
        teacher_data['classroom_requests'] = []
        teacher_data['classroom_request_counts'] = {}

    # ── Upcoming exams ────────────────────────────────────────────
    if teacher_id:
        today_str = now.strftime('%Y-%m-%d')
        rows = db.execute(
            '''SELECT DISTINCT es.*, c.name as course_name, r.name as room_name
               FROM exam_schedule es
               LEFT JOIN courses c ON es.course_id = c.id
               LEFT JOIN rooms r ON es.room_id = r.id
               INNER JOIN timetable t ON t.course_id = es.course_id AND t.teacher_id = ?
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               WHERE es.exam_date >= ?
               ORDER BY es.exam_date LIMIT 5''',
            (teacher_id, today_str)
        ).fetchall()
        teacher_data['upcoming_exams'] = [dict(r) for r in rows]
    else:
        teacher_data['upcoming_exams'] = []

    # ── Notifications ─────────────────────────────────────────────
    if user_id:
        teacher_data['notifications'] = notification_service.get_user_notifications(db, user_id, limit=10)
        teacher_data['unread_count'] = notification_service.get_unread_count(db, user_id)
    else:
        teacher_data['notifications'] = []
        teacher_data['unread_count'] = 0

    # ── Department announcements ──────────────────────────────────
    if teacher_data['teacher'] and teacher_data['teacher'].get('department_id'):
        dept_id = teacher_data['teacher']['department_id']
        rows = db.execute(
            '''SELECT * FROM department_announcements
               WHERE department_id = ? AND is_published = 1
               ORDER BY created_at DESC LIMIT 5''',
            (dept_id,)
        ).fetchall()
        teacher_data['announcements'] = [dict(r) for r in rows]
    else:
        teacher_data['announcements'] = []

    # ── Recent activity (history) ─────────────────────────────────
    if teacher_id:
        rows = db.execute(
            '''SELECT * FROM history
               WHERE (entity_type = 'classroom_change_request'
                      AND entity_id IN (SELECT id FROM classroom_change_requests WHERE teacher_id = ?))
                  OR (entity_type = 'teacher' AND entity_id = ?)
                  OR (actor_user_id = ?)
               ORDER BY created_at DESC LIMIT 10''',
            (teacher_id, teacher_id, user_id)
        ).fetchall()
        teacher_data['recent_activity'] = [dict(r) for r in rows]
    else:
        teacher_data['recent_activity'] = []

    # ── Pending requests count (teacher → department) ──────────────
    if teacher_id:
        teacher_data['pending_requests_count'] = db.execute(
            'SELECT COUNT(*) FROM teacher_messages WHERE teacher_id = ? AND status = ?',
            (teacher_id, 'pending')
        ).fetchone()[0]
    else:
        teacher_data['pending_requests_count'] = 0

    return teacher_data


def get_faculty_affairs_dashboard_data(db):
    """Data for the Faculty Affairs office dashboard — teacher-focused.

    Includes overall counts plus a teaching-load table (per-teacher weekly
    hours, scheduled lectures, assigned courses) consistent with the stats
    shown on the teacher detail page.
    """
    data = {}

    data['total_teachers'] = db.execute(
        'SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL'
    ).fetchone()[0]

    data['total_departments'] = db.execute(
        'SELECT COUNT(*) FROM departments WHERE hidden = 0 AND deleted_at IS NULL'
    ).fetchone()[0]

    data['timetable_count'] = db.execute(
        'SELECT COUNT(*) FROM timetable WHERE deleted_at IS NULL '
        'AND (version_id IS NULL OR version_id IN '
        '(SELECT id FROM timetable_versions WHERE status = \'active\'))'
    ).fetchone()[0]

    rows = db.execute(
        '''SELECT t.id, t.name, t.academic_number,
                  COALESCE(d.name, '') AS dept_name,
                  (SELECT COUNT(DISTINCT course_id) FROM timetable tt
                   WHERE tt.teacher_id = t.id AND tt.deleted_at IS NULL
                   AND tt.course_id IS NOT NULL
                   AND (tt.version_id IS NULL OR tt.version_id IN
                       (SELECT id FROM timetable_versions WHERE status = 'active'))) AS course_count,
                  (SELECT COUNT(*) FROM timetable tt
                   WHERE tt.teacher_id = t.id AND tt.deleted_at IS NULL
                   AND (tt.version_id IS NULL OR tt.version_id IN
                       (SELECT id FROM timetable_versions WHERE status = 'active'))) AS timetable_count,
                  (SELECT SUM(COALESCE(NULLIF(tt.hours, 0), NULLIF(c.total_hours, 0), COALESCE(c.theoretical_hours, 0) + COALESCE(c.practical_hours, 0), 0)) FROM timetable tt
                   LEFT JOIN courses c ON tt.course_id = c.id
                   WHERE tt.teacher_id = t.id) AS hours_count
           FROM teachers t
           LEFT JOIN departments d ON t.department_id = d.id
           WHERE t.deleted_at IS NULL
           ORDER BY t.name'''
    ).fetchall()
    data['teachers'] = [dict(r) for r in rows]

    recent_rows = db.execute(
        '''SELECT t.id, t.name, d.name AS dept_name, t.created_at
           FROM teachers t
           LEFT JOIN departments d ON t.department_id = d.id
           WHERE t.deleted_at IS NULL
           ORDER BY t.created_at DESC LIMIT 5'''
    ).fetchall()
    data['recent_teachers'] = [dict(r) for r in recent_rows]

    return data


def get_dashboard_stats(role: str, show: int = 5) -> dict:
    """Aggregate counts + recent activity for the generic dashboard home.

    The *role* argument is accepted for signature compatibility with the
    original helper and is currently unused.
    """
    from flask_db import get_db

    db = get_db()
    stats = {
        'users': db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'departments': db.execute(
            'SELECT COUNT(*) FROM departments WHERE deleted_at IS NULL'
        ).fetchone()[0],
        'teachers': db.execute(
            'SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL'
        ).fetchone()[0],
        'rooms': db.execute(
            'SELECT COUNT(*) FROM rooms WHERE deleted_at IS NULL'
        ).fetchone()[0],
        'courses': db.execute(
            'SELECT COUNT(*) FROM courses WHERE deleted_at IS NULL'
        ).fetchone()[0],
        'exams': db.execute('SELECT COUNT(*) FROM exam_schedule').fetchone()[0],
        'history': db.execute('SELECT COUNT(*) FROM history').fetchone()[0],
        'upcoming_exams': db.execute(
            "SELECT COUNT(*) FROM exam_schedule WHERE date(exam_date) >= date('now')"
        ).fetchone()[0],
    }
    stats['recent_activity'] = [
        dict(r)
        for r in db.execute(
            'SELECT * FROM history ORDER BY created_at DESC LIMIT ?', (show,)
        ).fetchall()
    ]
    return stats

