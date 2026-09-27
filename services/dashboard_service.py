# /     /     >---- خدمات لوحات المعلومات: تجهيز بيانات كل لوحة حسب الدور
from datetime import datetime

from core.constants import SEMESTER_LABELS
from services import notification_service
from services import course_service
from utils.format import semester_label

COURSES_PER_PAGE = 30


# /     /     >---- بيانات لوحة إدارة الامتحانات
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


# /     /     >---- بيانات لوحة قسم البحث والتطوير
def get_rnd_dept_dashboard_data(db, page=1, per_page=COURSES_PER_PAGE):
    """Data for the R&D Department sub-admin dashboard.

    ``page`` is 1-based and clamped to the available range, so a stale or
    hand-edited ``?page=`` can never raise or return an empty table.
    """
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

    # /     /     >---- جدول المقررات: صفحة واحدة فقط من الاستعلام (LIMIT/OFFSET)
    total = data['total_courses']
    per_page = per_page or COURSES_PER_PAGE
    total_pages = (total + per_page - 1) // per_page
    page = max(1, min(page or 1, total_pages or 1))
    offset = (page - 1) * per_page

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
                      AND cf3.status = 'published'
                    ORDER BY cf3.created_at DESC LIMIT 1) AS form_file_id,
                  (SELECT cs.id FROM course_content_submissions cs
                   WHERE cs.course_id = c.id
                   ORDER BY COALESCE(cs.submitted_at, cs.created_at) DESC
                   LIMIT 1) AS form_submission_id
           FROM courses c
           LEFT JOIN departments d ON c.department_id = d.id
           WHERE c.deleted_at IS NULL
           ORDER BY has_syllabus DESC, c.name, c.id
           LIMIT ? OFFSET ?''',
        (per_page, offset)
    ).fetchall()
    data['courses_list'] = course_service.attach_course_related_data(
        db, [dict(r) for r in rows])
    data['page'] = page
    data['per_page'] = per_page
    data['total'] = total
    data['total_pages'] = total_pages

    dept_rows = db.execute(
        """SELECT d.id, d.name,
                  (SELECT COUNT(*) FROM courses WHERE department_id = d.id AND deleted_at IS NULL) as course_count
           FROM departments d
           WHERE d.type = 'academic' AND d.deleted_at IS NULL
           ORDER BY d.name"""
    ).fetchall()
    data['departments'] = [dict(r) for r in dept_rows]

    return data


# /     /     >---- بيانات لوحة رئيس القسم (القاعات، الجدول، الطلبات)
def get_hod_dashboard_data(db, dept_id, semester=None):
    hod_data = {}
    dept_row = db.execute('SELECT name FROM departments WHERE id = ?', (dept_id,)).fetchone()
    hod_data['department_name'] = dept_row['name'] if dept_row else None
    hod_data['department_id'] = dept_id
    arabic_days = {0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس', 4: 'الجمعة', 5: 'السبت', 6: 'الأحد'}
    today_day = arabic_days.get(datetime.now().weekday())
    if today_day == 'الجمعة':
        today_day = None

    # /     /     >---- القاعات المشغولة الآن (الحصص الجارية حسب الوقت الحالي)
    def _to_minutes(t):
        if not t:
            return None
        try:
            h, m = t.split(':')
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return None

    now_time = datetime.now().strftime('%H:%M') if today_day is not None else None
    now_min = _to_minutes(now_time)
    if today_day is not None:
        rows = db.execute(
            '''SELECT t.*, c.name as course_name, tc.name as teacher_name, r.name as room_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN teachers tc ON t.teacher_id = tc.id
               LEFT JOIN rooms r ON t.room_id = r.id
               WHERE t.day = ? AND (t.department_id = ? OR ? IS NULL)
               AND (? IS NULL OR t.semester = ?)
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY t.period''',
            (today_day, dept_id, dept_id, semester, semester)
        ).fetchall()
        today_entries = [dict(r) for r in rows]
        occupied_now = []
        for entry in today_entries:
            st = _to_minutes(entry.get('start_time') or '')
            et = _to_minutes(entry.get('end_time') or '')
            if st is None or now_min is None:
                continue
            if et is None:
                ongoing = now_min >= st
            elif st <= et:
                ongoing = st <= now_min <= et
            else:
                ongoing = now_min >= st or now_min <= et  # حصة عبر منتصف الليل
            if ongoing:
                occupied_now.append(entry)
        hod_data['occupied_rooms'] = occupied_now
        hod_data['today_entries_count'] = len(today_entries)
        hod_data['today_lectures'] = today_entries
        hod_data['occupied_rooms_count'] = len({
            entry.get('room_id') for entry in occupied_now if entry.get('room_id')
        })
    else:
        hod_data['occupied_rooms'] = []
        hod_data['occupied_rooms_count'] = 0
        hod_data['today_entries_count'] = 0
        hod_data['today_lectures'] = []

    rows = db.execute(
        'SELECT * FROM rooms WHERE deleted_at IS NULL '
        'AND (department_id = ? OR department_id IS NULL) ORDER BY name',
        (dept_id,)
    ).fetchall()
    hod_data['all_rooms'] = [dict(r) for r in rows]
    hod_data['total_rooms'] = len(rows)
    occupied_room_ids = {r['room_id'] for r in hod_data['occupied_rooms'] if r.get('room_id')}
    hod_data['occupied_room_ids'] = list(occupied_room_ids)
    hod_data['available_rooms'] = [r for r in hod_data['all_rooms'] if r['id'] not in occupied_room_ids]

    # /     /     >---- الجدول الأسبوعي الكامل للقسم (حسب الفصل المختار)
    weekly_rows = db.execute(
        '''SELECT t.day, t.period, t.semester, t.room_id, c.name as course_name,
                  tc.name as teacher_name, r.name as room_name
           FROM timetable t
           LEFT JOIN courses c ON t.course_id = c.id
           LEFT JOIN teachers tc ON t.teacher_id = tc.id
           LEFT JOIN rooms r ON t.room_id = r.id
           WHERE (t.department_id = ? OR ? IS NULL)
           AND (? IS NULL OR t.semester = ?)
           AND (t.version_id IS NULL OR t.version_id IN
               (SELECT id FROM timetable_versions WHERE status = 'active'))
           ORDER BY t.day, t.period''',
        (dept_id, dept_id, semester, semester)
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

    # /     /     >---- الفصول الدراسية (1..8) للتبديل بين جداول الأقسام
    hod_data['semesters'] = [
        {'code': s, 'label': semester_label(s)}
        for s in sorted(SEMESTER_LABELS)
    ]
    hod_data['selected_semester'] = semester
    hod_data['selected_semester_label'] = semester_label(semester) if semester else ''
    # /     /     >---- جدول القاعات: لكل قاعة ولكل يوم مداخل الحصص
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

    # /     /     >---- الطلبات المعلّقة من الأساتذة
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
    # /     /     >---- كان هنا pending_messages_count يقرأ من teacher_messages،
    # /     /     >---- جدول قديم لا يكتب فيه شيء فكان دائماً صفراً.
    # /     /     >---- الطلبات نفسها هي teacher_requests التي فوق، ولا حاجة
    # /     /     >---- لعداد موازٍ يعرض الرقم نفسه تحت اسم آخر.
    hod_data['departments'] = [dict(r) for r in db.execute(
        'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()]
    # /     /     >---- نسبة المقررات المجدولة من إجمالي مقررات كل قسم
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


# /     /     >---- بيانات لوحة الأستاذ (محاضرات اليوم، الجدول، الامتحانات، الإشعارات)
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

    # /     /     >---- محاضرات اليوم مع تحديد المحاضرة الحالية أو التالية
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
        # /     /     >---- كشف المحاضرة اللي وقع جارية فيها الآن
        current_lecture = None
        for entry in teacher_data['today_entries']:
            if entry.get('start_time') and entry.get('end_time'):
                if entry['start_time'] <= current_time < entry['end_time']:
                    current_lecture = entry
                    break
        # /     /     >---- إذا مافيش محاضرة حالية، نلقى التالية
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

    # /     /     >---- الجدول الأسبوعي الكامل للأستاذ
    weekly_schedule = {}
    if teacher_id:
        for day_name in days_order:
            day_entries = db.execute(
                '''SELECT t.period, t.semester, t.course_id, c.name as course_name, c.year as course_year,
                          c.code as course_code,
                          r.name as room_name, t.start_time, t.end_time,
                          d.name as department_name
                   FROM timetable t
                   LEFT JOIN courses c ON t.course_id = c.id
                   LEFT JOIN rooms r ON t.room_id = r.id
                   LEFT JOIN departments d ON t.department_id = d.id
                   WHERE t.teacher_id = ? AND t.day = ? AND t.deleted_at IS NULL
                   AND (t.version_id IS NULL OR t.version_id IN
                       (SELECT id FROM timetable_versions WHERE status = 'active'))
                   ORDER BY t.start_time''',
                (teacher_id, day_name)
            ).fetchall()
            entries = []
            for r in day_entries:
                entry = dict(r)
                entry['semester_display'] = semester_label(entry.get('semester'))
                entries.append(entry)
            weekly_schedule[day_name] = entries
    teacher_data['weekly_schedule'] = weekly_schedule
    teacher_data['days_order'] = days_order

    teacher_data['course_files'] = {}
    if teacher_id:
        file_rows = db.execute(
            '''SELECT cf.id, cf.course_id, cf.original_filename
               FROM course_files cf
               WHERE cf.teacher_id = ? AND cf.file_type = 'syllabus'
                 AND cf.status IN ('approved', 'published')
               ORDER BY cf.updated_at DESC, cf.id DESC''',
            (teacher_id,),
        ).fetchall()
        for row in file_rows:
            teacher_data['course_files'].setdefault(
                row['course_id'], dict(row)
            )

    # /     /     >---- نموذج المقرر المنشور لكل مادة (للتحميل من لوحة الأستاذ)
    teacher_data['course_forms'] = {}
    if teacher_id:
        form_rows = db.execute(
            '''SELECT cf.course_id, cf.id AS file_id
               FROM course_files cf
               WHERE cf.file_type = 'form' AND cf.status = 'published'
               AND EXISTS (
                   SELECT 1 FROM timetable t
                   WHERE t.teacher_id = ? AND t.course_id = cf.course_id
                     AND t.deleted_at IS NULL
                     AND (t.version_id IS NULL OR t.version_id IN
                         (SELECT id FROM timetable_versions WHERE status = 'active'))
               )
               ORDER BY cf.created_at DESC, cf.id DESC''',
            (teacher_id,),
        ).fetchall()
        for row in form_rows:
            teacher_data['course_forms'].setdefault(
                row['course_id'], dict(row)
            )

    # /     /     >---- تكليفات التدريس المميزة (المقررات مع محاضراتها الأسبوعية)
    teacher_data['assignments'] = []
    if teacher_id:
        rows = db.execute(
            '''SELECT c.id, c.name, c.code, c.year, c.semester,
                      d.name as department_name,
                      t.day, t.start_time, t.end_time,
                      r.name as room_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms r ON t.room_id = r.id
               LEFT JOIN departments d ON t.department_id = d.id
               WHERE t.teacher_id = ? AND t.deleted_at IS NULL
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY c.name, t.start_time''',
            (teacher_id,)
        ).fetchall()
        assignments = []
        by_course = {}
        for r in rows:
            if not r['id']:
                continue
            course = by_course.get(r['id'])
            if course is None:
                course = {
                    'id': r['id'],
                    'name': r['name'],
                    'code': r['code'],
                    'year': r['year'],
                    'semester': r['semester'],
                    'semester_display': semester_label(r['semester']),
                    'department_name': r['department_name'],
                    'lectures': [],
                }
                by_course[r['id']] = course
                assignments.append(course)
            course['lectures'].append({
                'day': r['day'],
                'start_time': r['start_time'],
                'end_time': r['end_time'],
                'room_name': r['room_name'],
            })
        teacher_data['assignments'] = assignments

    # /     /     >---- الامتحانات القادمة للمقررات المتعلقة بالأستاذ
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

    # /     /     >---- الإشعارات وعدد غير المقروء
    if user_id:
        teacher_data['notifications'] = notification_service.get_user_notifications(db, user_id, limit=10)
        teacher_data['unread_count'] = notification_service.get_unread_count(db, user_id)
    else:
        teacher_data['notifications'] = []
        teacher_data['unread_count'] = 0

    # /     /     >---- إعلانات القسم المنشورة
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

    # /     /     >---- آخر النشاطات من سجل العمليات
    if teacher_id:
        rows = db.execute(
            '''SELECT * FROM history
               WHERE (entity_type = 'teacher' AND entity_id = ?)
                  OR (actor_user_id = ?)
               ORDER BY created_at DESC LIMIT 10''',
            (teacher_id, user_id)
        ).fetchall()
        teacher_data['recent_activity'] = [dict(r) for r in rows]
    else:
        teacher_data['recent_activity'] = []

    # /     /     >---- عدد طلبات الأستاذ المعلّقة
    # /     /     >---- الطلبات تعيش في teacher_requests (ينشئها
    # /     /     >---- page_routes/teacher_pages.teacher_messages). كان هذا
    # /     /     >---- العدد يقرأ teacher_messages — جدولاً قديماً لا يُكتب
    # /     /     >---- فيه — فكان يرجع صفراً دائماً.
    if teacher_id:
        teacher_data['pending_requests_count'] = db.execute(
            'SELECT COUNT(*) FROM teacher_requests WHERE teacher_id = ? AND status = ?',
            (teacher_id, 'pending')
        ).fetchone()[0]
    else:
        teacher_data['pending_requests_count'] = 0

    return teacher_data


# /     /     >---- بيانات لوحة شؤون هيئة التدريس (الأساتذة + جدول الأعباء)
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

    # /     /     >---- جدول الأعباء: لكل أستاذ عدد المقررات والمحاضرات والساعات
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


# /     /     >---- إحصائيات عامة + آخر النشاطات للوحة الرئيسية
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


# ══════════════════════════════════════════════════════════════════════
#  لوحة العميد — نظرة إشرافية شاملة على النطاقات الستة للمنصة (قراءة فقط)
# ══════════════════════════════════════════════════════════════════════

# /     /     >---- فلتر «المحاضرات المعتمدة» لمقارنة الجدول. يؤخذ اسم اللقب
# /     /     >---- كوسيط لأن نفس الفلتر يُستخدم على عدة ألقاب مختلفة
# /     /     >---- (t في العدّ العام، وtt داخل استعلامات أعباء التدريس)
def _active_tt(alias: str = 't') -> str:
    """Return the WHERE fragment selecting live (non-deleted, active-version)
    timetable rows for *alias*.

    Without this, a superseded copy of a lecture would be counted alongside the
    live one and every department's coverage ratio would exceed reality.
    """
    return (
        f'({alias}.deleted_at IS NULL AND ({alias}.version_id IS NULL OR '
        f'{alias}.version_id IN '
        f"(SELECT id FROM timetable_versions WHERE status = 'active')))"
    )


def _scalar(db, sql: str, params=()) -> int:
    """Run a single-value ``COUNT`` query and return it as ``int``.

    Centralised so every overview count degrades to ``0`` on a missing table
    rather than raising a 500 on the dean's landing page.
    """
    try:
        row = db.execute(sql, params).fetchone()
    except Exception:
        return 0
    return int(row[0]) if row and row[0] is not None else 0


def _rows(db, sql: str, params=()) -> list:
    """Run a query and return a list of dicts, or ``[]`` if the schema differs."""
    try:
        return [dict(r) for r in db.execute(sql, params).fetchall()]
    except Exception:
        return []


# /     /     >---- نطاق ١: الهوية — الحسابات وتوزيع الأدوار
def _dean_identity(db) -> dict:
    return {
        'users': _scalar(db, 'SELECT COUNT(*) FROM users'),
        'active_users': _scalar(
            db, 'SELECT COUNT(*) FROM users WHERE is_active = 1'),
        'multi_role_users': _scalar(
            db, 'SELECT COUNT(*) FROM (SELECT user_id FROM user_roles '
                'GROUP BY user_id HAVING COUNT(*) > 1)'),
        'by_role': _rows(db, '''
            SELECT ur.role AS role, COUNT(DISTINCT ur.user_id) AS count
            FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            WHERE u.is_active = 1
            GROUP BY ur.role
            ORDER BY count DESC, ur.role
        '''),
    }


# /     /     >---- نطاق ٢: الأكاديمية — الأقسام والمقررات وهيئة التدريس
def _dean_academic(db) -> dict:
    return {
        'departments': _scalar(
            db, 'SELECT COUNT(*) FROM departments WHERE deleted_at IS NULL'),
        'academic_departments': _scalar(
            db, "SELECT COUNT(*) FROM departments WHERE deleted_at IS NULL "
                "AND type = 'academic'"),
        'teachers': _scalar(
            db, 'SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL'),
        'courses': _scalar(
            db, 'SELECT COUNT(*) FROM courses WHERE deleted_at IS NULL'),
        'majors': _scalar(
            db, 'SELECT COUNT(*) FROM department_majors'),
        'by_rank': _rows(db, '''
            SELECT COALESCE(NULLIF(academic_rank, ''), 'غير محدد') AS label,
                   COUNT(*) AS count
            FROM teachers WHERE deleted_at IS NULL
            GROUP BY COALESCE(NULLIF(academic_rank, ''), 'غير محدد')
            ORDER BY count DESC, label
        '''),
        'by_qualification': _rows(db, '''
            SELECT COALESCE(NULLIF(qualification, ''), 'غير محدد') AS label,
                   COUNT(*) AS count
            FROM teachers WHERE deleted_at IS NULL
            GROUP BY COALESCE(NULLIF(qualification, ''), 'غير محدد')
            ORDER BY count DESC, label
        '''),
    }


# /     /     >---- نطاق ٣: الجدولة — القاعات والفترات ونِسَب تغطية الجدول
def _dean_scheduling(db) -> dict:
    live = _active_tt('t')
    rows = _rows(db, f'''
        SELECT d.id AS id, d.name AS name, d.type AS type,
               (SELECT COUNT(*) FROM course_departments cd
                 WHERE cd.department_id = d.id) AS courses,
               (SELECT COUNT(*) FROM teacher_departments td
                 WHERE td.department_id = d.id) AS teachers,
               (SELECT COUNT(*) FROM timetable t
                 WHERE t.department_id = d.id AND {live}) AS lectures,
               (SELECT COUNT(*) FROM rooms r
                 WHERE r.department_id = d.id AND r.deleted_at IS NULL) AS rooms
        FROM departments d
        WHERE d.deleted_at IS NULL AND d.hidden = 0
        ORDER BY d.name
    ''')
    # /     /     >---- نسبة تغطية الجدول لكل قسم (0-100) — مقررات لها محاضرة فعلية
    for r in rows:
        r['coverage'] = round((r['lectures'] / r['courses'] * 100)) if r['courses'] else 0
    return {
        'rooms': _scalar(
            db, 'SELECT COUNT(*) FROM rooms WHERE deleted_at IS NULL'),
        'room_capacity': _scalar(
            db, 'SELECT COALESCE(SUM(capacity), 0) FROM rooms WHERE deleted_at IS NULL'),
        'periods': _scalar(
            db, 'SELECT COUNT(*) FROM period_settings WHERE is_enabled = 1'),
        'lectures': _scalar(
            db, f'SELECT COUNT(*) FROM timetable t WHERE {_active_tt("t")}'),
        'active_versions': _scalar(
            db, "SELECT COUNT(*) FROM timetable_versions WHERE status = 'active'"),
        'departments': rows,
    }


# /     /     >---- نطاق ٤: الامتحانات — المجدول والقادم وتوزيعه على الأيام
def _dean_examinations(db) -> dict:
    return {
        'total': _scalar(db, 'SELECT COUNT(*) FROM exam_schedule'),
        'upcoming': _scalar(
            db, "SELECT COUNT(*) FROM exam_schedule "
                "WHERE date(exam_date) >= date('now')"),
        'past': _scalar(
            db, "SELECT COUNT(*) FROM exam_schedule "
                "WHERE date(exam_date) < date('now')"),
        'published': _scalar(
            db, "SELECT COUNT(*) FROM exam_schedule WHERE status = 'published'"),
        'periods_configured': _scalar(db, 'SELECT COUNT(*) FROM exam_settings'),
        'by_status': _rows(db, '''
            SELECT COALESCE(NULLIF(status, ''), 'غير محدد') AS label,
                   COUNT(*) AS count
            FROM exam_schedule
            GROUP BY COALESCE(NULLIF(status, ''), 'غير محدد')
            ORDER BY count DESC, label
        '''),
        'by_day': _rows(db, '''
            SELECT COALESCE(NULLIF(day_ar, ''), 'غير محدد') AS label,
                   COUNT(*) AS count
            FROM exam_schedule
            GROUP BY COALESCE(NULLIF(day_ar, ''), 'غير محدد')
            ORDER BY count DESC, label
        '''),
        'next_exams': _rows(db, '''
            SELECT es.exam_date AS exam_date, es.start_time AS start_time,
                   es.end_time AS end_time, es.day_ar AS day_ar,
                   c.name AS course_name, c.code AS course_code,
                   r.name AS room_name
            FROM exam_schedule es
            LEFT JOIN courses c ON c.id = es.course_id
            LEFT JOIN rooms r ON r.id = es.room_id
            WHERE date(es.exam_date) >= date('now')
            ORDER BY es.exam_date ASC, es.start_time ASC
            LIMIT 8
        '''),
    }


# /     /     >---- نطاق ٥: التواصل — الرسائل والطلبات والإعلانات
def _dean_communication(db) -> dict:
    # /     /     >---- كان هنا messages / messages_pending يقرآن من
    # /     /     >---- teacher_messages (جدول قديم لا يُكتب فيه)، فكان الرقمان
    # /     /     >---- صفراً دائماً بينما الطلبات الحقيقية في teacher_requests.
    # /     /     >---- حُذف Card الرسائل المعلّقة من القالب لأنه يكرّر رقم
    # /     /     >---- الطلبات تحت اسم مختلف.
    return {
        'requests': _scalar(db, 'SELECT COUNT(*) FROM teacher_requests'),
        'requests_pending': _scalar(
            db, "SELECT COUNT(*) FROM teacher_requests WHERE status = 'pending'"),
        'announcements': _scalar(
            db, 'SELECT COUNT(*) FROM department_announcements WHERE is_published = 1'),
        'notifications': _scalar(db, 'SELECT COUNT(*) FROM notifications'),
        'recent_announcements': _rows(db, '''
            SELECT da.title AS title, da.priority AS priority,
                   da.created_at AS created_at, d.name AS department_name
            FROM department_announcements da
            LEFT JOIN departments d ON d.id = da.department_id
            WHERE da.is_published = 1
            ORDER BY da.created_at DESC
            LIMIT 5
        '''),
    }


# /     /     >---- نطاق ٦: التدقيق — سجل العمليات
def _dean_auditing(db, show: int) -> dict:
    return {
        'total': _scalar(db, 'SELECT COUNT(*) FROM history'),
        'recent': _rows(db, '''
            SELECT h.created_at AS created_at, h.actor_username AS actor_username,
                   h.message AS message, h.action AS action,
                   h.entity_type AS entity_type, h.entity_id AS entity_id
            FROM history h
            ORDER BY h.created_at DESC
            LIMIT ?
        ''', (show,)),
        'by_entity': _rows(db, '''
            SELECT COALESCE(NULLIF(entity_type, ''), 'غير محدد') AS label,
                   COUNT(*) AS count
            FROM history
            GROUP BY COALESCE(NULLIF(entity_type, ''), 'غير محدد')
            ORDER BY count DESC, label
            LIMIT 8
        '''),
    }


# /     /     >---- أعباء التدريس لكل أستاذ (نفس استعلام مكتب شؤون التدريس)
def _dean_teaching_load(db) -> list:
    live = _active_tt('t')
    return _rows(db, f'''
        SELECT t.id AS id, t.name AS name, t.academic_number AS academic_number,
               COALESCE(d.name, '') AS dept_name,
               (SELECT COUNT(DISTINCT x.course_id) FROM timetable x
                 WHERE x.teacher_id = t.id AND {_active_tt("x")}
                   AND x.course_id IS NOT NULL) AS course_count,
               (SELECT COUNT(*) FROM timetable x
                 WHERE x.teacher_id = t.id AND {_active_tt("x")}) AS lecture_count,
               (SELECT COALESCE(SUM(COALESCE(NULLIF(x.hours, 0),
                          NULLIF(c.total_hours, 0),
                          COALESCE(c.theoretical_hours, 0)
                            + COALESCE(c.practical_hours, 0), 0)), 0)
                  FROM timetable x
                  LEFT JOIN courses c ON c.id = x.course_id
                 WHERE x.teacher_id = t.id AND {_active_tt("x")}) AS hours_count
        FROM teachers t
        LEFT JOIN departments d ON d.id = t.department_id
        WHERE t.deleted_at IS NULL
        ORDER BY hours_count DESC, t.name
    ''')


# /     /     >---- البيانات الكاملة للوحة العميد (قراءة فقط، تغطّي نطاقات المنصة الستة)
def get_dean_overview_data(db, show: int = 8) -> dict:
    """College-wide read-only overview for the dean.

    Aggregates every domain of the platform into a single payload so the dean
    can see the state of the whole college from one page, plus a directory of
    the read-only pages he is allowed to open.

    Read-only by construction: every statement is a ``SELECT``. Counts use
    :func:`_scalar` and lists use :func:`_rows`, so a column that a partially
    migrated schema lacks degrades to ``0`` / ``[]`` instead of 500-ing the
    landing page.
    """
    show = max(1, int(show or 1))
    return {
        'identity': _dean_identity(db),
        'academic': _dean_academic(db),
        'scheduling': _dean_scheduling(db),
        'examinations': _dean_examinations(db),
        'communication': _dean_communication(db),
        'auditing': _dean_auditing(db, show),
        'teaching_load': _dean_teaching_load(db),
    }