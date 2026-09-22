"""Exam service — scheduling, settings, hall management.

Uses ``ExamRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.

/     /     >---- خدمة الامتحانات: الجدولة والإعدادات وإدارة القاعات.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.constants.seasons import season_label as core_season_label

logger = logging.getLogger(__name__)

# /     /     >---- ثوابت العرض: أيام وشهور عربية وترتيب أيام الامتحان وحدود الأسابيع
ARABIC_DAYS = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
ARABIC_MONTHS = {
    '01': 'يناير', '02': 'فبراير', '03': 'مارس', '04': 'أبريل',
    '05': 'مايو', '06': 'يونيو', '07': 'يوليو', '08': 'أغسطس',
    '09': 'سبتمبر', '10': 'أكتوبر', '11': 'نوفمبر', '12': 'ديسمبر',
}
ARABIC_WEEKDAYS = {5: 'السبت', 6: 'الأحد', 0: 'الإثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس'}
EXAM_DAYS_ORDER = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
MAX_EXAM_WEEKS = 5


# /     /     >---- اسم اليوم بالعربي من التاريخ
def _day_ar_from_date(date_str):
    if not date_str:
        return ''
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return ''
    return ARABIC_WEEKDAYS.get(d.weekday(), '').replace('الإثنين', 'الاثنين')


# /     /     >---- ملصقات الحالات العربية للمخطط الامتحاني
STATUS_LABELS = {
    'draft': 'مسودة', 'planned': 'مخطط', 'scheduled': 'مجدول',
    'published': 'منشور', 'completed': 'مكتمل',
}
STATUS_ALL = ('draft', 'planned', 'scheduled', 'published', 'completed')
STATUS_ACTIVE = ('planned', 'scheduled', 'published', 'completed')
STATUS_UNPUBLISHED = ('planned', 'scheduled')


# /     /     >---- عرض التاريخ كاملاً: يوم + شهر عربي + سنة
def _date_display(date_str):
    if not date_str:
        return ''
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return f'{d.day} {ARABIC_MONTHS.get(d.strftime("%m"), "")} {d.year}'
    except (ValueError, TypeError):
        return date_str


# /     /     >---- عرض التاريخ مختصر وبدون سنة: "2025-12-09" → "9 ديسمبر"
def _date_short_display(date_str):
    """"2025-12-09" → "9 ديسمبر" (day + Arabic month, no year)."""
    if not date_str:
        return ''
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return f'{d.day} {ARABIC_MONTHS.get(d.strftime("%m"), "")}'.strip()
    except (ValueError, TypeError):
        return date_str


# /     /     >---- الأعداد الترتيبية العربية للفصول
ARABIC_ORDINALS = ['الأول', 'الثاني', 'الثالث', 'الرابع',
                   'الخامس', 'السادس', 'السابع', 'الثامن', 'التاسع', 'العاشر']


# /     /     >---- اسم الفصل بالعربي (الفصل الأول ... الفصل العاشر)
def semester_label(sem):
    if 1 <= sem <= len(ARABIC_ORDINALS):
        return 'الفصل ' + ARABIC_ORDINALS[sem - 1]
    return f'الفصل {sem}'


# /     /     >---- تجهيز بيانات امتحانات الأقسام للواجهة (JSON جاهز للعرض)
def build_exam_schedule_view(db, departments, dept_stats):
    """Shape department exam data into a JSON-friendly payload for the workspace UI."""
    period = get_exam_period(db)
    start = period.get('exam_start_date', '')
    end = period.get('exam_end_date', '')

    year_label = ''
    if start:
        try:
            sy = int(start[:4])
            ey = int(end[:4]) if end and len(end) >= 4 else sy
            year_label = f'{sy}' if sy == ey else f'{sy}–{ey}'
        except (ValueError, TypeError):
            year_label = ''

    # /     /     >---- أسماء القاعات وخياراتها مع السعة
    room_names = sorted({r['name'] for r in get_exam_halls(db)})
    room_options = [
        {'id': r['id'], 'name': r['name'], 'capacity': r['capacity']}
        for r in get_exam_halls(db)
    ]
    period_times = get_exam_period(db)
    period_start_time = period_times.get('exam_start_time') or '09:00'
    period_end_time = period_times.get('exam_end_time') or '17:00'

    depts = []
    for dept in departments:
        weeks, seen_weeks = [], set()
        days, seen_days = [], set()
        exams = []
        date_map = {}
        date_display_map = {}
        for slot in dept.get('time_slots', []):
            wn = slot.get('week_number', 1)
            if wn not in seen_weeks:
                seen_weeks.add(wn)
                weeks.append(wn)
            day = slot.get('day_ar', '')
            if day and day not in seen_days:
                seen_days.add(day)
                days.append(day)
            exam_date = slot.get('exam_date', '')
            if wn and day and exam_date:
                date_map.setdefault(str(wn), {})[day] = exam_date
                date_display_map.setdefault(str(wn), {})[day] = _date_short_display(exam_date)
            for sem, cell in (slot.get('cells') or {}).items():
                if not cell:
                    continue
                st = cell.get('start_time') or ''
                et = cell.get('end_time') or ''
                cell_type = (cell.get('exam_type') or '').strip() or ('practical' if cell.get('practical_hours') else 'written')
                exams.append({
                    'id': cell.get('id'),
                    'week': wn,
                    'day': day,
                    'date': slot.get('exam_date', ''),
                    'semester': int(sem) if sem is not None else 1,
                    'course': cell.get('course_name') or '',
                    'code': cell.get('course_code') or '',
                    'type': cell_type,
                    'time': f'{st} - {et}' if st and et else st,
                    'start_time': st,
                    'end_time': et,
                    'hall': cell.get('room_name') or '',
                    'room_id': cell.get('room_id'),
                    'course_id': cell.get('course_id'),
                    'status': cell.get('status') or '',
                })
        # /     /     >---- حالة القسم: معتمد إذا كل عموده منشور أو مكتمل
        if exams and all(e['status'] in ('published', 'completed') for e in exams):
            dept_status = 'approved'
        else:
            dept_status = 'pending'
        stats = dept_stats.get(dept['id'], {})
        sem_start = dept.get('sem_start', 1)
        sem_end = dept.get('sem_end', 1)
        depts.append({
            'id': dept['id'],
            'key': f"dept-{dept['id']}",
            'name': dept['name'],
            'isGeneral': bool(dept.get('is_general')),
            'semStart': sem_start,
            'semEnd': sem_end,
            'semesterLabels': [semester_label(s) for s in range(sem_start, sem_end + 1)],
            'examCount': stats.get('exam_count', len(exams)),
            'roomCount': stats.get('room_count', 0),
            'status': dept_status,
            'weeks': sorted(weeks),
            'days': days,
            'exams': exams,
            'dateMap': date_map,
            'dateDisplayMap': date_display_map,
        })

    # Read semester exam dates for display
    # /     /     >---- تواريخ امتحانات الفصل الأكاديمي للعرض (من إعدادات الامتحانات)
    sem_exam_start, sem_exam_end = '', ''
    try:
        settings_row = db.execute(
            'SELECT exam_start_date, exam_end_date FROM exam_settings LIMIT 1'
        ).fetchone()
        if settings_row:
            sem_exam_start = settings_row['exam_start_date'] or ''
            sem_exam_end = settings_row['exam_end_date'] or ''
    except Exception:
        pass

    return {
        'period': {
            'start': start,
            'end': end,
            'startDisplay': _date_display(start),
            'endDisplay': _date_display(end),
            'yearLabel': year_label,
            'startTime': period_start_time,
            'endTime': period_end_time,
        },
        'semesterExamStart': sem_exam_start,
        'semesterExamEnd': sem_exam_end,
        'rooms': room_names,
        'roomOptions': room_options,
        'departments': depts,
    }


# /     /     >---- منسّق التاريخ العربي العام للاستخدام الخارجي
def format_exam_date(date_str):
    """Public Arabic date formatter (e.g. ``2025-09-15`` → ``15 سبتمبر 2025``)."""
    return _date_display(date_str)


# /     /     >---- بناء عرض الطباعة: بيانات القسم مع إحصائيات ثم تجهيز العرض
def build_exam_print_view(db, dept_id=None):
    """Build the exam schedule view for printing/embedding.

    Combines department exam data with per-department counts and shapes
    it into the same view consumed by the print template.  When *dept_id*
    is given only that department is included.
    """
    departments = build_dept_exam_data(db, filter_dept_id=dept_id) if dept_id else build_dept_exam_data(db)
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
    view = build_exam_schedule_view(db, departments, dept_stats)
    period = resolve_academic_period(db)
    if period.get('yearLabel'):
        view.setdefault('period', {})['yearLabel'] = period['yearLabel']
    return view


# /     /     >---- تحديد الفترة الأكاديمية الموضحة في ترويسة الفضاء/الطباعة
def resolve_academic_period(db) -> Dict[str, str]:
    """Resolve the academic period shown in the exam workspace/print header.

    The active semester (season + year) is computed from today's date and
    drives the label; its exam window comes from ``exam_settings``.
    Returns ``{'start', 'yearLabel', 'seasonWord'}``.
    """
    from core.constants.seasons import SEASON_FALL, SEASON_SPRING

    now = datetime.now()
    season = 'fall' if now.month >= 9 else 'spring'
    year = now.year

    settings = get_exam_period(db)
    start = settings.get('exam_start_date') or ''
    end = settings.get('exam_end_date') or ''

    # /     /     >---- كلمة الفصل من شخصية الفصل النشط
    season_word = {
        'fall': SEASON_FALL, 'spring': SEASON_SPRING,
    }.get(str(season).strip().lower(), season) or ''
    if not season_word and start:
        season_word = (core_season_label(start) or '').split(' ')[0]
    year_label = str(year)

    return {
        'start': start,
        'yearLabel': year_label,
        'seasonWord': season_word,
    }


class ExamService:
    """Class-based exam service with repository injection.

    /     /     >---- الخدمة بشكل كلاس مع حقن مستودع الامتحانات.
    """

    def __init__(self, db, exam_repo):
        self.db = db
        self._repo = exam_repo

    # /     /     >---- بناء بيانات امتحانات الأقسام: فترات مخزنّة + خلايا زمنية + تواريخ
    def build_dept_exam_data(self, filter_dept_id=None, published_only=False):
        if filter_dept_id:
            departments = [self._repo.find_department(filter_dept_id)]
            departments = [d for d in departments if d]
        else:
            departments = self._repo.list_visible_departments()

        # /     /     >---- الفترة: من الفصل النشط أولاً ثم من إعدادات الامتحانات
        sem_start, sem_end = self._get_semester_exam_dates()
        if sem_start and sem_end:
            start_str, end_str = sem_start, sem_end
        else:
            settings = self.get_exam_period()
            start_str = settings.get('exam_start_date') or ''
            end_str = settings.get('exam_end_date') or ''

        # Resolve (week, day) → concrete date when an exam period is set.
        # Start from the Saturday of the week containing start_dt so every
        # exam day (Sat-Thu) in every week always gets a mapped date.
        # /     /     >---- ربط (الأسبوع، اليوم) بتواريخ فعلية بدءاً من السبت
        date_map = {}
        if start_str and end_str:
            try:
                start_dt = datetime.strptime(start_str, '%Y-%m-%d')
                end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                start_dt = end_dt = None
            if start_dt and end_dt:
                days_to_saturday = (start_dt.weekday() + 2) % 7
                cur = start_dt - timedelta(days=days_to_saturday)
                week = 1
                last_thursday = end_dt
                while cur <= last_thursday:
                    wd = cur.weekday()
                    if wd in ARABIC_WEEKDAYS:
                        day_ar = ARABIC_WEEKDAYS[wd].replace('الإثنين', 'الاثنين')
                        date_map[(week, day_ar)] = cur.strftime('%Y-%m-%d')
                        # /     /     >---- الخميس = آخر يوم في الأسبوع فنتنقل للأسبوع اللي بعده
                        if day_ar == 'الخميس':
                            week += 1
                            if cur > end_dt:
                                last_thursday = cur
                    cur += timedelta(days=1)

        dept_list = []
        for dept in departments:
            dept_name = dept['name']
            is_general = ('عام' in dept_name)
            if is_general:
                sem_start, sem_end = (1, 1)
            else:
                sem_start, sem_end = (2, int(dept.get('semesters') or 7))

            # /     /     >---- سجلات الامتحانات المخزنة للقسم
            status_filter = ''
            params = [dept['id']]
            if published_only:
                status_filter = " AND es.status IN ('published', 'completed')"
            rows = self.db.execute(
                f'''SELECT es.*, c.name as course_name, c.code as course_code,
                          r.name as room_name, c.practical_hours
                   FROM exam_schedule es
                   LEFT JOIN courses c ON es.course_id = c.id
                   LEFT JOIN rooms r ON es.room_id = r.id
                   WHERE es.department_id = ?{status_filter}
                   ORDER BY es.week, es.day_ar, es.start_time, es.semester''',
                params,
            ).fetchall()

            # /     /     >---- فهرسة السجلات حسب الخلية (أسبوع، يوم، فصل)
            stored_weeks = set()
            exam_by_cell = {}
            for r in rows:
                d = dict(r)
                week = int(d.get('week') or 1)
                if week < 1:
                    week = 1
                stored_weeks.add(week)
                day_ar = (d.get('day_ar') or '').replace('الإثنين', 'الاثنين')
                if not day_ar:
                    day_ar = _day_ar_from_date(d.get('exam_date'))
                sem = d.get('semester', 1)
                exam_by_cell.setdefault((week, day_ar), {})[sem] = d

            max_week = max(stored_weeks) if stored_weeks else 1
            max_week = min(max_week, MAX_EXAM_WEEKS)

            # /     /     >---- بناء شبكة الفترات الفارغة لملء الخلايا في الواجهة
            time_slots = []
            for week in range(1, max_week + 1):
                for day_ar in EXAM_DAYS_ORDER:
                    exam_date = date_map.get((week, day_ar), '')
                    display = _date_display(exam_date)
                    time_slots.append({
                        'exam_date': exam_date, 'day_ar': day_ar,
                        'date_display': display, 'date_display_full': display,
                        'week_number': week,
                        'day_number': '',
                        'month_short': '',
                        'cells': exam_by_cell.get((week, day_ar), {}),
                    })

            dept_list.append({
                'id': dept['id'], 'name': dept_name, 'is_general': is_general,
                'sem_start': sem_start, 'sem_end': sem_end, 'time_slots': time_slots,
            })

        return dept_list

    # /     /     >---- تعديل قاعة الامتحان وإرجاع الاسم المحدّث
    def update_exam_room(self, schedule_id, room_id):
        self._repo.update_room(schedule_id, room_id or None)
        row = self.db.execute(
            'SELECT r.name as room_name FROM exam_schedule es '
            'LEFT JOIN rooms r ON es.room_id = r.id WHERE es.id = ?',
            (schedule_id,),
        ).fetchone()
        return {'room_name': row['room_name'] if row and row['room_name'] else '', 'room_id': room_id}

    # /     /     >---- إعدادات الامتحانات مع حساب عدد الأيام
    def get_exam_settings(self):
        settings = self._repo.get_settings() or {}
        total_days = 0
        if settings.get('exam_start_date') and settings.get('exam_end_date'):
            try:
                s = datetime.strptime(settings['exam_start_date'], '%Y-%m-%d')
                e = datetime.strptime(settings['exam_end_date'], '%Y-%m-%d')
                total_days = (e - s).days + 1
            except (ValueError, TypeError):
                total_days = 0
        return settings, total_days

    def save_exam_settings(self, data):
        self._repo.save_settings(data)

    # /     /     >---- قاعات الامتحانات النشطة
    def get_exam_halls(self):
        return self._repo.get_active_rooms()

    def create_exam_hall(self, name, capacity, status):
        self.db.execute(
            'INSERT INTO rooms (name, capacity, status) VALUES (?, ?, ?)',
            (name, capacity, status),
        )
        self.db.commit()

    # /     /     >---- فحص وجود اسم قاعة مكرر
    def hall_name_exists(self, name, exclude_id=None):
        if exclude_id:
            return self.db.execute(
                'SELECT id FROM rooms WHERE name = ? AND id != ?', (name, exclude_id)
            ).fetchone()
        return self.db.execute('SELECT id FROM rooms WHERE name = ?', (name,)).fetchone()

    def update_exam_hall(self, id, name, capacity, status):
        self.db.execute(
            'UPDATE rooms SET name = ?, capacity = ?, status = ? WHERE id = ?',
            (name, capacity, status, id),
        )
        self.db.commit()

    # /     /     >---- قراءة فترة الامتحانات مع قيم افتراضية
    def get_exam_period(self):
        row = self.db.execute('SELECT * FROM exam_settings LIMIT 1').fetchone()
        if not row:
            return {
                'exam_start_date': '', 'exam_end_date': '',
                'exam_start_time': '09:00', 'exam_end_time': '17:00',
                'period_status': 'draft', 'last_modified_by': '', 'last_modified_at': '',
            }
        return dict(row)

    # /     /     >---- تاريخي امتحانات الفصل النشط (من إعدادات الامتحانات)
    def _get_semester_exam_dates(self):
        """Read exam period dates from ``exam_settings``.

        Returns (start_date, end_date) tuple.
        """
        settings = self.get_exam_period()
        return settings.get('exam_start_date') or '', settings.get('exam_end_date') or ''

    # /     /     >---- رفض تواريخ خارج فترة الامتحانات المحددة
    def validate_exam_date(self, exam_date):
        """Reject exam dates outside the configured examination period.

        Reads the exam window from ``exam_settings``.
        Raises ValueError with an Arabic message if the date is out of range.
        """
        if not exam_date:
            return
        sem_start, sem_end = self._get_semester_exam_dates()
        if sem_start and sem_end:
            if exam_date < sem_start or exam_date > sem_end:
                raise ValueError(
                    f'التاريخ خارج الفترة المحددة للامتحانات. '
                    f'فترة الامتحانات: {sem_start} — {sem_end}'
                )
            return
        settings = self.get_exam_period()
        es = settings.get('exam_start_date', '')
        ee = settings.get('exam_end_date', '')
        if es and ee and (exam_date < es or exam_date > ee):
            raise ValueError(
                f'التاريخ خارج الفترة المحددة للامتحانات. '
                f'فترة الامتحانات: {es} — {ee}'
            )

    # /     /     >---- حفظ فترة الامتحانات (المصدر الوحيد: إعدادات الامتحانات)
    def save_exam_period(self, data, username):
        is_resave = data.get('resave')
        status = 'draft' if is_resave else data.get('period_status', 'draft')
        now = "datetime('now', 'localtime')"
        existing = self.db.execute('SELECT id FROM exam_settings LIMIT 1').fetchone()
        if existing:
            self.db.execute(
                f'''UPDATE exam_settings SET
                       exam_start_date = ?, exam_end_date = ?,
                       exam_start_time = ?, exam_end_time = ?,
                       period_status = ?,
                       last_modified_by = ?,
                       last_modified_at = {now},
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (data['exam_start_date'], data['exam_end_date'],
                 data['exam_start_time'], data['exam_end_time'], status, username,
                 existing['id']),
            )
        else:
            self.db.execute(
                f'''INSERT INTO exam_settings
                       (exam_start_date, exam_end_date, exam_start_time, exam_end_time,
                        period_status, last_modified_by, last_modified_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, {now}, CURRENT_TIMESTAMP)''',
                (data['exam_start_date'], data['exam_end_date'],
                 data['exam_start_time'], data['exam_end_time'], status, username),
            )
        self.db.commit()

    # /     /     >---- نشر فترة الامتحانات
    def publish_exam_period(self, username):
        now = "datetime('now', 'localtime')"
        existing = self.db.execute('SELECT id FROM exam_settings LIMIT 1').fetchone()
        if existing:
            self.db.execute(
                f'''UPDATE exam_settings SET
                       period_status = 'published',
                       last_modified_by = ?,
                       last_modified_at = {now},
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (username, existing['id']),
            )
        else:
            self.db.execute(
                f'''INSERT INTO exam_settings
                       (period_status, last_modified_by, last_modified_at, updated_at)
                   VALUES ('published', ?, {now}, CURRENT_TIMESTAMP)''',
                (username,),
            )
        self.db.commit()

    # /     /     >---- مقررات قسم معيّن في فصل معيّن
    def get_department_courses(self, dept_id, semester):
        return self._repo.get_department_courses(dept_id, semester)

    # /     /     >---- توكيلات الامتحانات النشطة للقسم/الفصل
    def get_department_exam_assignments(self, dept_id, semester):
        rows = self.db.execute(
            '''SELECT es.*, c.name as course_name, c.code as course_code,
                      r.name as room_name
               FROM exam_schedule es
               JOIN courses c ON es.course_id = c.id
               LEFT JOIN rooms r ON es.room_id = r.id
               WHERE es.department_id = ? AND es.semester = ?
                 AND es.status IN ('planned', 'scheduled', 'published', 'completed')
               ORDER BY es.exam_date''',
            (dept_id, semester),
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- حفظ توكيل امتحان: إدراج/تحديث/حذف حسب الوجود والحالة
    def save_exam_assignment(self, course_id, dept_id, semester, exam_date, user_id):
        self.validate_exam_date(exam_date)
        existing = self.db.execute(
            '''SELECT id, status FROM exam_schedule
               WHERE course_id = ? AND department_id = ? AND semester = ?
                 AND status IN ('planned', 'scheduled', 'published', 'completed')''',
            (course_id, dept_id, semester),
        ).fetchone()
        if existing:
            # /     /     >---- المقررات المنشورة/المكتملة لا تُعدل
            if existing['status'] in ('published', 'completed'):
                return
            if exam_date:
                new_status = 'planned' if existing['status'] != 'published' else existing['status']
                self.db.execute(
                    'UPDATE exam_schedule SET exam_date = ?, status = ? WHERE id = ?',
                    (exam_date, new_status, existing['id']),
                )
            else:
                # /     /     >---- إلغاء التاريخ يعني حذف التوكيل
                self.db.execute('DELETE FROM exam_schedule WHERE id = ?', (existing['id'],))
        else:
            if exam_date:
                self.db.execute(
                    '''INSERT INTO exam_schedule
                       (course_id, department_id, exam_date, semester, status, created_by_user_id)
                       VALUES (?, ?, ?, ?, 'planned', ?)''',
                    (course_id, dept_id, exam_date, semester, user_id),
                )
        self.db.commit()

    # /     /     >---- الامتحانات قيد التخطيط (مخطط أو مجدول)
    def get_planning_exams(self):
        rows = self.db.execute(
            '''SELECT es.*, c.name as course_name, c.code as course_code,
                      d.name as dept_name, d.id as dept_id, r.name as room_name
               FROM exam_schedule es
               JOIN courses c ON es.course_id = c.id
               JOIN departments d ON es.department_id = d.id
               LEFT JOIN rooms r ON es.room_id = r.id
               WHERE es.status IN ('planned', 'scheduled')
               ORDER BY es.exam_date, d.name, c.name'''
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- عدد الطلاب: أُزيل مع إعادة هيكلة الأدوار فيُترك صفراً
    def get_student_count(self, dept_id, semester):
        # Student role/tables were removed in the role overhaul — no student
        # counts exist anymore.  Kept as 0 so capacity/planning flows still work.
        return 0

    def get_exam_rooms(self):
        return self._repo.get_active_rooms()

    # /     /     >---- إسناد قاعة ووقت للامتحان وتحديث الحالة لمجدول
    def assign_exam_resources(self, schedule_id, room_id, start_time, end_time):
        if start_time and end_time:
            self.db.execute(
                '''UPDATE exam_schedule SET
                       room_id = ?, start_time = ?, end_time = ?, status = 'scheduled'
                   WHERE id = ? AND status IN ('planned', 'scheduled')''',
                (room_id, start_time, end_time, schedule_id),
            )
        else:
            self.db.execute(
                "UPDATE exam_schedule SET room_id = ? WHERE id = ? AND status = 'planned'",
                (room_id, schedule_id),
            )
        self.db.commit()

    # /     /     >---- الفترات الزمنية (جلسات) المحددة في إعدادات الامتحانات
    def get_exam_sessions(self):
        settings = self.db.execute(
            'SELECT session_a, session_b, session_c FROM exam_settings WHERE id = 1'
        ).fetchone()
        sessions = []
        if settings:
            settings = dict(settings)
            for key, label in [('session_a', 'الفترة الأولى'), ('session_b', 'الفترة الثانية'), ('session_c', 'الفترة الثالثة')]:
                if settings.get(key):
                    sessions.append({'value': settings[key], 'label': label})
        return sessions

    # /     /     >---- استغلال القاعات حسب اليوم (يومياً للعرض)
    def get_room_day_usage(self):
        rooms = self.get_exam_rooms()
        usage = {}
        for r in rooms:
            usage[r['id']] = {'name': r['name'], 'capacity': r['capacity'], 'days': {}}
        rows = self.db.execute(
            '''SELECT es.room_id, es.exam_date, es.semester, es.department_id
               FROM exam_schedule es
               WHERE es.room_id IS NOT NULL AND es.status IN ('scheduled', 'published')'''
        ).fetchall()
        for row in rows:
            rid = row['room_id']
            date = row['exam_date']
            cnt = self.get_student_count(row['department_id'], row['semester'])
            if rid in usage:
                days = usage[rid]['days']
                days[date] = days.get(date, 0) + cnt
        return usage

    # /     /     >---- فحص تعارضات الامتحان: قاعة/فصل/قسم/أستاذ/سعة/تكرار
    def check_exam_conflicts(self, schedule_id, room_id=None, start_time=None, end_time=None):
        exam = self.db.execute(
            'SELECT * FROM exam_schedule WHERE id = ?', (schedule_id,)
        ).fetchone()
        if not exam:
            return []
        exam = dict(exam)
        conflicts = []
        exam_date = exam['exam_date']
        dept_id = exam['department_id']
        semester = exam['semester']
        course_id = exam['course_id']

        # /     /     >---- كل الامتحانات المجدولة/المنشورة ما عدا الحالي
        assigned = self.db.execute(
            '''SELECT es.*, c.name as course_name, c.code as course_code
               FROM exam_schedule es
               JOIN courses c ON c.id = es.course_id
               WHERE es.status IN ('scheduled', 'published') AND es.id != ?''',
            (schedule_id,)
        ).fetchall()

        # /     /     >---- تعارض قاعة: نفس القاعة وفي نفس الوقت
        if room_id:
            for a in assigned:
                if a['room_id'] == room_id and a['exam_date'] == exam_date:
                    if start_time and a['start_time'] and a['start_time'] < end_time and a['end_time'] > start_time:
                        conflicts.append({
                            'type': 'room_occupied',
                            'message': f"القاعة مشغولة في هذا الوقت — {a['course_name']}",
                        })
                    elif not start_time:
                        conflicts.append({
                            'type': 'room_occupied',
                            'message': f"القاعة محجوزة في هذا اليوم — {a['course_name']}",
                        })

        # /     /     >---- تعارض فصل: نفس الفصل يمتحن مقررين في وقت واحد
        for a in assigned:
            if a['department_id'] == dept_id and a['exam_date'] == exam_date and a['semester'] == semester:
                if a['start_time'] and start_time and a['start_time'] < end_time and a['end_time'] > start_time:
                    conflicts.append({
                        'type': 'semester_conflict',
                        'message': f"الفصل يمتحن امتحاناً آخر في نفس الوقت — {a['course_name']}",
                    })

        # /     /     >---- تعارض قسم: القسم يمتحن فصلاً آخر في نفس الوقت
        for a in assigned:
            if a['department_id'] == dept_id and a['exam_date'] == exam_date and a['semester'] != semester:
                if a['start_time'] and start_time and a['start_time'] < end_time and a['end_time'] > start_time:
                    conflicts.append({
                        'type': 'dept_conflict',
                        'message': f"القسم يمتحن فصلاً آخر في نفس الوقت — {a['course_name']} ({a['semester']})",
                    })

        # /     /     >---- تعارض أستاذ: نفس عضو هيئة التدريس مراقب لامتحان آخر
        teacher = self.db.execute(
            'SELECT teacher_id FROM timetable WHERE course_id = ? '
            'AND (version_id IS NULL OR version_id IN '
            '(SELECT id FROM timetable_versions WHERE status = \'active\')) LIMIT 1',
            (course_id,)
        ).fetchone()
        if teacher:
            teacher_id = teacher['teacher_id']
            for a in assigned:
                if a['start_time'] and start_time and a['start_time'] < end_time and a['end_time'] > start_time and a['exam_date'] == exam_date:
                    other_teacher = self.db.execute(
                        'SELECT teacher_id FROM timetable WHERE course_id = ? '
                        'AND (version_id IS NULL OR version_id IN '
                        '(SELECT id FROM timetable_versions WHERE status = \'active\')) LIMIT 1',
                        (a['course_id'],)
                    ).fetchone()
                    if other_teacher and other_teacher['teacher_id'] == teacher_id:
                        conflicts.append({
                            'type': 'teacher_conflict',
                            'message': f"عضو هيئة التدريس مكلف بامتحان آخر في نفس الوقت — {a['course_name']}",
                        })

        # /     /     >---- تعارض السعة: عدد الطلاب أكبر من سعة القاعة
        if room_id:
            room = self.db.execute('SELECT capacity FROM rooms WHERE id = ?', (room_id,)).fetchone()
            if room:
                student_count = self.get_student_count(dept_id, semester)
                if student_count > room['capacity']:
                    conflicts.append({
                        'type': 'capacity',
                        'message': f"سعة القاعة ({room['capacity']}) أقل من عدد الطلاب ({student_count})",
                    })

        # /     /     >---- تكرار: أكثر من امتحان في نفس القاعة بنفس اليوم
        if room_id and exam_date:
            dup = self.db.execute(
                '''SELECT COUNT(*) as cnt FROM exam_schedule
                   WHERE room_id = ? AND exam_date = ? AND status IN ('scheduled', 'published')
                   AND id != ?''',
                (room_id, exam_date, schedule_id)
            ).fetchone()
            if dup and dup['cnt'] > 0 and not start_time:
                conflicts.append({
                    'type': 'duplicate',
                    "message": "يوجد امتحان آخر مخصص لهذه القاعة في نفس اليوم",
                })

        return conflicts

    # /     /     >---- تحويل خلية الجدول (أسبوع، يوم) إلى تاريخ امتحان فعلّي
    def resolve_exam_date(self, week_number, day_ar):
        """Map a (week, day) table cell back to a concrete exam date."""
        sem_start, sem_end = self._get_semester_exam_dates()
        if sem_start and sem_end:
            start_str, end_str = sem_start, sem_end
        else:
            settings = self.get_exam_period()
            start_str = settings.get('exam_start_date', '')
            end_str = settings.get('exam_end_date', '')
        if not start_str or not end_str:
            return None
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            return None

        norm = lambda d: (d or '').replace('الإثنين', 'الاثنين')
        day_map = {5: 'السبت', 6: 'الأحد', 0: 'الإثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس'}
        cur = start_dt
        week = 1
        while cur <= end_dt:
            wd = cur.weekday()
            if wd in day_map:
                if week == week_number and norm(day_map[wd]) == norm(day_ar):
                    return cur.strftime('%Y-%m-%d')
                if day_map[wd] == 'الخميس':
                    week += 1
            cur += timedelta(days=1)
        return None

    # /     /     >---- تعارضات للخلية قبل الحفظ: (أسبوع، يوم) مشترك بين كل الأقسام
    def check_cell_conflicts(self, dept_id, semester, week, day_ar, room_id, start_time, end_time, exclude_id=None):
        """Conflicts for a proposed cell exam before it is saved.

        A cell is identified by (week, day_ar); when an exam period is set the
        same pair maps to one concrete date shared by every department.
        """
        conflicts = []
        day_norm = (day_ar or '').replace('الإثنين', 'الاثنين')
        exclude_id = exclude_id if exclude_id is not None else -1

        # /     /     >---- كل الامتحانات في نفس الخلية (الأسبوع واليوم)
        assigned = self.db.execute(
            '''SELECT es.*, c.name as course_name, c.code as course_code
               FROM exam_schedule es
               JOIN courses c ON c.id = es.course_id
               WHERE es.status IN ('scheduled', 'published') AND es.id != ?
                 AND es.week = ? AND REPLACE(es.day_ar, 'الإثنين', 'الاثنين') = ?''',
            (exclude_id, week, day_norm)
        ).fetchall()

        for a in assigned:
            overlap = (a['start_time'] and start_time
                       and a['start_time'] < end_time and a['end_time'] > start_time)
            # /     /     >---- تعارض داخل نفس القسم والفصل
            if a['department_id'] == dept_id and a['semester'] == semester:
                if overlap:
                    conflicts.append({
                        'type': 'semester_conflict',
                        'message': f"الفصل {semester} يمتحن امتحاناً آخر في نفس الوقت — {a['course_name']}",
                    })
                else:
                    conflicts.append({
                        'type': 'semester_day_conflict',
                        'message': f"الفصل {semester} لديه امتحان في نفس اليوم — {a['course_name']}",
                    })
            # /     /     >---- تعارض قاعة في نفس الخلية
            if room_id and a['room_id'] == room_id:
                if overlap:
                    conflicts.append({
                        'type': 'room_occupied',
                        'message': f"القاعة مشغولة في هذا الوقت — {a['course_name']}",
                    })
                elif not a['start_time']:
                    conflicts.append({
                        'type': 'room_occupied',
                        'message': f"القاعة محجوزة في هذا اليوم — {a['course_name']}",
                    })
        return conflicts

    # /     /     >---- إنشاء/تحديث امتحان داخل خلية واحدة (أسبوع × يوم × فصل)
    def save_cell_exam(self, dept_id, semester, week, day_ar, exam_date, course_id, room_id, start_time, end_time, exam_type, user_id, schedule_id=None):
        """Create or update an exam in a single (week × day × semester) cell."""
        self.validate_exam_date(exam_date)
        day_norm = (day_ar or '').replace('الإثنين', 'الاثنين')
        if schedule_id:
            row = self.db.execute(
                'SELECT * FROM exam_schedule WHERE id = ?', (schedule_id,)
            ).fetchone()
            if not row or row['department_id'] != dept_id:
                raise ValueError('الامتحان غير موجود في قسمك')
            self.db.execute(
                '''UPDATE exam_schedule SET
                       course_id = ?, semester = ?, week = ?, day_ar = ?, exam_date = ?,
                       room_id = ?, start_time = ?, end_time = ?, exam_type = ?, status = 'scheduled'
                   WHERE id = ?''',
                (course_id, semester, week, day_norm, exam_date,
                 room_id, start_time, end_time, exam_type, schedule_id),
            )
        else:
            cur = self.db.execute(
                '''INSERT INTO exam_schedule
                   (course_id, department_id, week, day_ar, exam_date, semester, start_time, end_time,
                    room_id, exam_type, status, created_by_user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)''',
                (course_id, dept_id, week, day_norm, exam_date, semester,
                 start_time, end_time, room_id, exam_type, user_id),
            )
            schedule_id = cur.lastrowid
        self.db.commit()
        return schedule_id

    # /     /     >---- حذف امتحان من خلية مع التحقق من ملكية القسم
    def delete_cell_exam(self, schedule_id, dept_id):
        row = self.db.execute(
            'SELECT * FROM exam_schedule WHERE id = ?', (schedule_id,)
        ).fetchone()
        if not row or row['department_id'] != dept_id:
            raise ValueError('الامتحان غير موجود في قسمك')
        self.db.execute('DELETE FROM exam_schedule WHERE id = ?', (schedule_id,))
        self.db.commit()

    # /     /     >---- اقتراح توزيع الامتحانات على القاعات تلقائياً
    def suggest_distribution(self):
        # /     /     >---- الامتحانات المخططة بلا قاعة بعد
        exams = [e for e in self.get_planning_exams() if e['status'] == 'planned' and not e['room_id']]
        for ex in exams:
            ex['student_count'] = self.get_student_count(ex['department_id'], ex['semester'])
        rooms = self.get_exam_rooms()
        rooms.sort(key=lambda r: r['capacity'])
        usage = {r['id']: {'capacity': r['capacity'], 'days': {}} for r in rooms}
        assigned = self.db.execute(
            '''SELECT es.room_id, es.exam_date, es.start_time, es.end_time,
                      es.department_id, es.semester
               FROM exam_schedule es
               WHERE es.room_id IS NOT NULL AND es.status IN ('scheduled', 'published')'''
        ).fetchall()
        room_schedule = {}
        for a in assigned:
            rid = a['room_id']
            if rid not in room_schedule:
                room_schedule[rid] = []
            room_schedule[rid].append(dict(a))

        # /     /     >---- منع امتحانين لنفس القسم والفصل في نفس اليوم
        dept_same_day = {}
        for a in assigned:
            key = (a['department_id'], a['semester'], a['exam_date'])
            dept_same_day[key] = dept_same_day.get(key, 0) + 1

        suggestions = []
        # /     /     >---- أكثر الامتحانات عدداً أولاً، وأفضل ملاءمة للسعة
        for ex in sorted(exams, key=lambda x: x['student_count'], reverse=True):
            day = ex.get('exam_date', '')
            dept_id = ex['department_id']
            semester = ex['semester']
            student_count = ex['student_count']
            best_room = None
            best_fit = float('inf')
            for r in rooms:
                day_used = usage[r['id']]['days'].get(day, 0)
                cap = r['capacity']
                if day_used + student_count > cap:
                    continue
                if r['id'] in room_schedule:
                    time_ok = True
                    for a in room_schedule[r['id']]:
                        if a['exam_date'] == day and a.get('start_time'):
                            time_ok = False
                            break
                    if not time_ok:
                        continue
                same_key = (dept_id, semester, day)
                if dept_same_day.get(same_key, 0) > 0:
                    continue
                remaining = cap - day_used
                if remaining < best_fit:
                    best_fit = remaining
                    best_room = r
            if best_room:
                usage[best_room['id']]['days'][day] = usage[best_room['id']]['days'].get(day, 0) + student_count
                suggestions.append({
                    'schedule_id': ex['id'], 'room_id': best_room['id'],
                    'room_name': best_room['name'], 'capacity': best_room['capacity'],
                    'student_count': student_count, 'course_name': ex['course_name'],
                    'exam_date': ex['exam_date'],
                })
        return suggestions

    # /     /     >---- نشر الجدول: تحويل كل المجدول إلى منشور وإرجاع عدد الصفوف
    def publish_schedule(self):
        self.db.execute("UPDATE exam_schedule SET status = 'published' WHERE status = 'scheduled'")
        self.db.commit()
        return self.db.execute('SELECT changes()').fetchone()[0]

    # /     /     >---- بيانات التخطيط الكاملة مقسمة حسب اليوم/القاعة/القسم
    def get_planning_data(self):
        exams = self.get_planning_exams()
        rooms = self.get_exam_rooms()
        sessions = self.get_exam_sessions()
        usage = self.get_room_day_usage()
        for ex in exams:
            ex['student_count'] = self.get_student_count(ex['department_id'], ex['semester'])
            ex['date_display'] = _date_display(ex.get('exam_date', ''))
        by_day, by_room, by_dept = {}, {}, {}
        for ex in exams:
            day = ex.get('exam_date', '')
            rid = ex.get('room_id')
            dept_id = ex.get('department_id')
            by_day.setdefault(day, []).append(ex)
            if rid:
                room_info = next((r for r in rooms if r['id'] == rid), None)
                if rid not in by_room:
                    by_room[rid] = {'name': room_info['name'] if room_info else '',
                                    'capacity': room_info['capacity'] if room_info else 0, 'exams': []}
                by_room[rid]['exams'].append(ex)
            by_dept.setdefault(dept_id, {'name': ex['dept_name'], 'exams': []})['exams'].append(ex)
        return {
            'by_day': {d: by_day[d] for d in sorted(by_day.keys())},
            'by_room': by_room, 'by_dept': by_dept,
            'rooms': rooms, 'sessions': sessions, 'usage': usage,
        }


# ── Backward-compatible module-level API ──────────────────────────────────
# /     /     >---- دوال مستوى الوحدة للتوافق مع المسارات القديمة


def build_dept_exam_data(db, filter_dept_id=None, published_only=False):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).build_dept_exam_data(filter_dept_id, published_only)


def update_exam_room(db, schedule_id, room_id):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).update_exam_room(schedule_id, room_id)


def get_exam_settings(db):
    from database.repositories.exam_repository import ExamRepository
    settings, total_days = ExamService(db, ExamRepository(db)).get_exam_settings()
    halls_raw = db.execute('SELECT id, name, capacity, status FROM rooms WHERE deleted_at IS NULL ORDER BY name').fetchall()
    return settings, [dict(r) for r in halls_raw], total_days


def save_exam_settings(db, data):
    from database.repositories.exam_repository import ExamRepository
    ExamRepository(db).save_settings(data)


def get_exam_halls(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamRepository(db).get_active_rooms()


def create_exam_hall(db, name, capacity, status):
    db.execute('INSERT INTO rooms (name, capacity, status) VALUES (?, ?, ?)', (name, capacity, status))
    db.commit()


def hall_name_exists(db, name, exclude_id=None):
    if exclude_id:
        return db.execute('SELECT id FROM rooms WHERE name = ? AND id != ?', (name, exclude_id)).fetchone()
    return db.execute('SELECT id FROM rooms WHERE name = ?', (name,)).fetchone()


def update_exam_hall(db, id, name, capacity, status):
    db.execute('UPDATE rooms SET name = ?, capacity = ?, status = ? WHERE id = ?', (name, capacity, status, id))
    db.commit()


def get_exam_period(db):
    row = db.execute('SELECT * FROM exam_settings LIMIT 1').fetchone()
    if not row:
        return {
            'exam_start_date': '', 'exam_end_date': '',
            'exam_start_time': '09:00', 'exam_end_time': '17:00',
            'period_status': 'draft', 'last_modified_by': '', 'last_modified_at': '',
        }
    return dict(row)


def save_exam_period(db, data, username):
    from database.repositories.exam_repository import ExamRepository
    ExamService(db, ExamRepository(db)).save_exam_period(data, username)


def publish_exam_period(db, username):
    from database.repositories.exam_repository import ExamRepository
    ExamService(db, ExamRepository(db)).publish_exam_period(username)


def get_department_courses(db, dept_id, semester):
    from database.repositories.exam_repository import ExamRepository
    return ExamRepository(db).get_department_courses(dept_id, semester)


def get_department_exam_assignments(db, dept_id, semester):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).get_department_exam_assignments(dept_id, semester)


def save_exam_assignment(db, course_id, dept_id, semester, exam_date, user_id):
    from database.repositories.exam_repository import ExamRepository
    ExamService(db, ExamRepository(db)).save_exam_assignment(course_id, dept_id, semester, exam_date, user_id)


def get_planning_exams(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).get_planning_exams()


def get_student_count(db, dept_id, semester):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).get_student_count(dept_id, semester)


def get_exam_rooms(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamRepository(db).get_active_rooms()


def assign_exam_resources(db, schedule_id, room_id, start_time, end_time):
    from database.repositories.exam_repository import ExamRepository
    ExamService(db, ExamRepository(db)).assign_exam_resources(schedule_id, room_id, start_time, end_time)


def get_exam_sessions(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).get_exam_sessions()


def get_room_day_usage(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).get_room_day_usage()


def suggest_distribution(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).suggest_distribution()


def publish_schedule(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).publish_schedule()


def get_planning_data(db):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).get_planning_data()


def check_exam_conflicts(db, schedule_id, room_id=None, start_time=None, end_time=None):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).check_exam_conflicts(schedule_id, room_id, start_time, end_time)


def resolve_exam_date(db, week_number, day_ar):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).resolve_exam_date(week_number, day_ar)


def update_exam_room(db, schedule_id, room_id):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).update_exam_room(schedule_id, room_id)


def check_cell_conflicts(db, dept_id, semester, week, day_ar, room_id, start_time, end_time, exclude_id=None):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).check_cell_conflicts(
        dept_id, semester, week, day_ar, room_id, start_time, end_time, exclude_id)


def save_cell_exam(db, dept_id, semester, week, day_ar, exam_date, course_id, room_id, start_time, end_time, exam_type, user_id, schedule_id=None):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).save_cell_exam(
        dept_id, semester, week, day_ar, exam_date, course_id, room_id, start_time, end_time, exam_type, user_id, schedule_id)


def delete_cell_exam(db, schedule_id, dept_id):
    from database.repositories.exam_repository import ExamRepository
    return ExamService(db, ExamRepository(db)).delete_cell_exam(schedule_id, dept_id)