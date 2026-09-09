"""Faculty Performance Evaluation service — كشف العبء التدريسي.

Assembles all data for the ministry-standard performance form.
Module-level functions take a database connection as the first argument.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.faculty_performance_repository import (
    FacultyPerformanceRepository,
    semester_bounds,
)
from core.constants.seasons import (
    LEGACY_PERIOD_LABEL,
    is_legacy_period_code,
    period_label as _season_period_label,
)

# ── Constants ────────────────────────────────────────────────────

YEAR_LABELS = {
    1: 'السنة الأولى', 2: 'السنة الثانية', 3: 'السنة الثالثة',
    4: 'السنة الرابعة', 5: 'السنة الخامسة', 6: 'السنة السادسة',
    7: 'السنة السابعة',
}

LECTURE_TYPE_MAP = {
    'theory': 'نظري',
    'practical': 'عملي',
    'نظري': 'نظري',
    'عملي': 'عملي',
}


RESEARCH_ACTIVITY_TYPES = [
    'مشروع تخرج',
    'دراسات ميدانية',
    'مجموعات بحثية',
    'دراسة حقلية',
    'بحث علمي',
    'الإرشاد الكلية',
]

COLLEGE_NAME = 'كلية التقنية الهندسية زوارة'

SEMESTER_LABELS = {
    1: 'الفصل الأول',
    2: 'الفصل الثاني',
}

# ── Ministry workload baseline ────────────────────────────────────
# الأساسي يُعرض حتى 10 (حسب عنوان النموذج "4-10 ساعات"),
# البحثي يُعرض حتى 10، والمواد الزائدة عن حد الأساسي تُنقل كاملة
# إلى الساعات الإضافية. التكليف الإداري منفصل تمامًا عن هذه الساعات.
TARGET_TOTAL = 14
BASIC_CAP = 10
RESEARCH_CAP = 10


def academic_year_label(code: str) -> str:
    """Arabic-only display label for a term code.

    ``fall_2026`` becomes a season+year phrase; raw codes are never
    shown in English inside the interface or printed documents.
    """
    lbl = _season_period_label(code)
    if lbl:
        return lbl
    if is_legacy_period_code(code):
        return LEGACY_PERIOD_LABEL
    return (code or '').strip()


def _repo(db):
    return FacultyPerformanceRepository(db)


def _clean_field(value: Any) -> str:
    """Display-safe string: never print ``None`` / the literal string ``'None'``."""
    if value is None:
        return ''
    if isinstance(value, str) and value.strip().lower() == 'none':
        return ''
    return str(value)


# ── Data Assembly ────────────────────────────────────────────────

def get_performance_form_data(
    db, teacher_id: int, academic_year: str, semester: int,
    department_id: int = None,
) -> Optional[Dict[str, Any]]:
    """Build the complete form data dict for a teacher + semester.

    ``department_id`` optionally scopes the form to one of the teacher's
    departments (validated against their assignments); when omitted the
    primary department is used.
    """
    repo = _repo(db)

    teacher = repo.get_teacher_profile(teacher_id)
    if not teacher:
        return None

    # Departments: primary assignment + additional memberships (issue 9 M2M)
    # + departments from teaching assignments (a teacher may have courses in
    #   departments they are not formally linked to via teacher_departments)
    m2m_rows = db.execute(
        'SELECT department_id FROM teacher_departments WHERE teacher_id = ?',
        (teacher_id,),
    ).fetchall()
    tt_dept_rows = db.execute(
        'SELECT DISTINCT department_id FROM teacher_taught_courses '
        'WHERE teacher_id = ? AND department_id IS NOT NULL',
        (teacher_id,),
    ).fetchall()
    dept_ids = []
    for d in [teacher.get('department_id')] + \
            [r['department_id'] for r in m2m_rows] + \
            [r['department_id'] for r in tt_dept_rows]:
        if d and d not in dept_ids:
            dept_ids.append(d)

    if department_id is not None and department_id in dept_ids:
        dept_ids = [department_id]

    # Workload rules
    rank_id = teacher.get('rank_id')
    rules_raw = repo.get_workload_rules(rank_id, academic_year) if rank_id else []
    rules = {}
    for r in rules_raw:
        rules[r['category']] = {'min': r['min_hours'], 'max': r['max_hours']}
    for cat in ('basic', 'research', 'additional'):
        if cat not in rules:
            rules[cat] = {'min': 0, 'max': 999}

    # Timetable entries from the teaching-assignment ledger
    timetable_entries = repo.get_timetable_entries(
        teacher_id, dept_ids, academic_year
    )
    # The fallback widens to every department the teacher has taught in that
    # semester. It is intentionally NOT applied when the form was explicitly
    # scoped to one department, otherwise the scope would silently leak.
    if not timetable_entries and department_id is None:
        tt_dept_rows = db.execute(
            'SELECT DISTINCT department_id FROM teacher_taught_courses '
            'WHERE teacher_id = ? AND department_id IS NOT NULL '
            'AND semester_code = ?',
            (teacher_id, academic_year),
        ).fetchall()
        fallback_ids = [r['department_id'] for r in tt_dept_rows if r['department_id']]
        if fallback_ids:
            timetable_entries = repo.get_timetable_entries(
                teacher_id, fallback_ids, academic_year
            )

    # Cross-department teaching vs the member's primary department
    primary_dept_id = teacher.get('department_id')
    extra_depts = sorted({
        str(entry.get('department_id')) for entry in timetable_entries
        if primary_dept_id and entry.get('department_id')
        and entry.get('department_id') != primary_dept_id
    })

    # Build basic teaching table
    basic_teaching = []
    total_raw_hours = 0
    for entry in timetable_entries:
        # Skip orphan rows (teaching-assignment ledger rows whose course no
        # longer exists / was never linked to a course).
        if not entry.get('course_id') or not entry.get('course_name'):
            continue
        idx = len(basic_teaching) + 1
        lecture_type = entry.get('lecture_type') or ''
        if lecture_type == 'practical':
            hours = entry.get('practical_hours') or 0
        else:
            hours = entry.get('theoretical_hours') or 0
        if hours <= 0:
            hours = _calculate_hours(entry.get('start_time'), entry.get('end_time'))
        hours = int(hours) if hours else 0
        total_raw_hours += hours
        basic_teaching.append({
            'index': idx,
            'course_name': entry.get('course_name') or '',
            'course_code': entry.get('course_code') or '',
            'lecture_type': LECTURE_TYPE_MAP.get(entry.get('lecture_type') or '', ''),
            'course_phase': YEAR_LABELS.get(entry.get('course_year'), str(entry.get('course_year') or '')),
            'department': entry.get('dept_name') or '',
            'group_number': entry.get('student_section') or '',
            'student_count': '',
            'day': entry.get('day') or '',
            'start_time': entry.get('start_time') or '',
            'end_time': entry.get('end_time') or '',
            'hours': hours,
        })

    # Workload split — basic capped at BASIC_CAP (10); any ENTIRE course
    # that would push the running basic total past the cap moves to the
    # additional table. Basic courses are never split in half.
    additional_teaching = []
    _scratch = []
    _running = 0
    for entry in basic_teaching:
        hours = entry.get('hours') or 0
        if _running + hours > BASIC_CAP:
            additional_teaching.append(entry)
        else:
            _running += hours
            _scratch.append(entry)
    basic_teaching = _scratch
    basic_total = _running

    # Research activities (only those active in this semester)
    research_raw = repo.get_research_activities(teacher_id, academic_year, semester)
    research = []
    research_total = 0
    for r in research_raw:
        research.append({'type': r['activity_type'], 'hours': r['hours'], 'notes': r.get('notes', '')})
        research_total += r['hours']

    # Admin assignments (only those active in this semester)
    admin_raw = repo.get_admin_assignments(teacher_id, academic_year, semester)
    admin_assignments = []
    admin_total = 0
    for a in admin_raw:
        is_active = repo.is_assignment_active_for_semester(
            a['start_date'], a.get('end_date'), academic_year, semester
        )
        if is_active:
            admin_assignments.append({
                'task': a['task_name'],
                'hours_used': a['hours_used'],
                'assignment_date': a.get('assignment_date', ''),
                'start_date': a['start_date'],
                'end_date': a.get('end_date'),
                'is_active': True,
            })
            admin_total += a['hours_used']

    # Leaves (only those active in this semester)
    leaves_raw = repo.get_leaves(teacher_id, academic_year, semester)
    leaves = []
    leaves_total = 0
    for lv in leaves_raw:
        is_active = repo.is_leave_active_for_semester(
            lv['start_date'], lv.get('end_date'), academic_year, semester
        )
        if is_active:
            lv_hours = int(lv.get('hours', 0) or 0)
            leaves_total += lv_hours
            leaves.append({
                'type': lv['leave_type'],
                'decision_number': lv.get('decision_number', ''),
                'decision_authority': lv.get('decision_authority', ''),
                'decision_date': lv.get('decision_date', ''),
                'hours': lv_hours,
            })

    # Fixed six activity rows of the official paper form
    research_rows = []
    for name in RESEARCH_ACTIVITY_TYPES:
        match = next(
            (r for r in research if r['type'].strip() == name), None)
        research_rows.append({
            'type': name,
            'hours': match['hours'] if match else '',
        })
    for r in research:
        if r['type'].strip() not in RESEARCH_ACTIVITY_TYPES:
            research_rows.append({'type': r['type'], 'hours': r['hours']})

    # Research total is shown whole up to the research cap (10).
    research_raw_total = research_total
    research_total = min(research_total, RESEARCH_CAP)

    # Additional total = sum of the whole courses moved past the basic cap.
    additional_total = sum(
        (e.get('hours') or 0) for e in additional_teaching
        if isinstance(e.get('hours'), (int, float)))

    # Warnings
    warnings = []
    if total_raw_hours > BASIC_CAP:
        warnings.append({
            'type': 'basic_exceeded',
            'message': f'الساعات التدريسية الفعلية ({total_raw_hours}) تتجاوز الحد الأساسي ({BASIC_CAP}) — يُضاف الفائض كساعات إضافية',
            'severity': 'info',
        })
    if research_raw_total > RESEARCH_CAP:
        warnings.append({
            'type': 'research_exceeded',
            'message': f'الساعات البحثية ({research_raw_total}) تتجاوز الحد الأقصى ({RESEARCH_CAP}) — يُحول الفائض إلى ساعات إضافية',
            'severity': 'warning',
        })
    if extra_depts:
        warnings.append({
            'type': 'cross_department',
            'message': 'العضو لديه محاضرات في أقسام أخرى غير قسمه الأساسي — تُعرض ضمن نطاق القسم الأساسي فقط',
            'severity': 'warning',
        })

    grand_total = (basic_total + research_total + additional_total
                   + admin_total + leaves_total)

    # Semester label
    semester_label = 'الفصل الأول' if semester == 1 else 'الفصل الثاني'

    # Official paper layout always shows at least 6 rows
    # (padding is added LAST so hour arithmetic never sees blanks)
    while len(basic_teaching) < 6:
        basic_teaching.append({
            'index': len(basic_teaching) + 1,
            'course_name': '', 'course_code': '',
            'lecture_type': '', 'course_phase': '',
            'department': '', 'group_number': '',
            'student_count': '', 'day': '',
            'start_time': '', 'end_time': '', 'hours': '',
        })

    return {
        'teacher': teacher,
        'header': {
            'org_name': COLLEGE_NAME,
            'college_name': COLLEGE_NAME,
            'teacher_name': teacher.get('name', ''),
            'department': teacher.get('dept_name', ''),
            'section': '',
            'qualification': teacher.get('qual_name', ''),
            'academic_number': _clean_field(teacher.get('academic_number')),
            'national_id': _clean_field(teacher.get('national_id')),
            'specialization': teacher.get('specialization_name') or _clean_field(teacher.get('specialization')),
            'rank': teacher.get('rank_name', ''),
            'academic_year': academic_year,
            'semester_label': SEMESTER_LABELS.get(semester, semester_label),
            'semester_number': semester,
            'academic_year_label': academic_year_label(academic_year),
            'contract_date': _clean_field(teacher.get('contract_date')),
            'first_lecture_date': _clean_field(teacher.get('first_lecture_date')),
            'work_start_date': _clean_field(teacher.get('work_start_date') or teacher.get('contract_date')),
        },
        'basic_teaching': basic_teaching,
        'basic_total': basic_total,
        'total_raw_hours': total_raw_hours,
        'research': research,
        'research_rows': research_rows,
        'research_total': research_total,
        'additional_teaching': additional_teaching,
        'additional_total': additional_total,
        'admin_assignments': admin_assignments,
        'admin_total': admin_total,
        'leaves': leaves,
        'leaves_total': leaves_total,
        'grand_total': grand_total,
        'workload_rules': rules,
        'warnings': warnings,
    }


def _calculate_hours(start_time: Optional[str], end_time: Optional[str]) -> float:
    """Calculate whole hours from HH:MM start to HH:MM end. Returns an int."""
    if not start_time or not end_time:
        return 0
    try:
        parts_s = start_time.split(':')
        parts_e = end_time.split(':')
        start_min = int(parts_s[0]) * 60 + int(parts_s[1])
        end_min = int(parts_e[0]) * 60 + int(parts_e[1])
        diff = end_min - start_min
        if diff <= 0:
            return 0
        return int(diff / 60)
    except (ValueError, IndexError):
        return 0


# ── Save Functions ───────────────────────────────────────────────

def get_active_semester(db) -> Dict[str, Any]:
    """Return the currently active semester as ``{academic_year, semester}``.

    ``academic_year`` is the named-term code (e.g. ``fall_2026``) used to
    store research activities, derived from the active ``semesters`` row.
    ``semester`` is the logical 1/2 (Fall → 1, Spring → 2).
    """
    row = db.execute(
        'SELECT code, season FROM semesters '
        'WHERE is_active = 1 AND deleted_at IS NULL LIMIT 1'
    ).fetchone()
    if row and row['code']:
        season = (row['season'] or '').lower()
        return {
            'academic_year': row['code'],
            'semester': 1 if season == 'fall' else 2,
        }
    from datetime import date
    today = date.today()
    season = 'fall' if today.month >= 9 else 'spring'
    year = today.year if today.month >= 9 else today.year
    return {
        'academic_year': f'{season}_{year}',
        'semester': 1 if season == 'fall' else 2,
    }


def save_research_data(
    db, teacher_id: int, academic_year: str, semester: int,
    activities: List[Dict[str, Any]],
) -> None:
    _repo(db).upsert_research_activities(teacher_id, academic_year, semester, activities)


def get_research_types(db) -> List[Dict[str, Any]]:
    """Return the six fixed research activity types for the member edit form.

    The official paper form always shows these six rows in order, regardless
    of what is persisted in the lookup table.
    """
    return [{'id': i, 'name': name} for i, name in enumerate(RESEARCH_ACTIVITY_TYPES)]


def get_research_activities_for_semester(db, teacher_id: int) -> List[Dict[str, Any]]:
    """Research activities for the active semester, as a list of activity types + hours."""
    sem = get_active_semester(db)
    return _repo(db).get_research_activities(
        teacher_id, sem['academic_year'], sem['semester']
    )


def save_admin_data(
    db, teacher_id: int, assignments: List[Dict[str, Any]]
) -> None:
    _repo(db).upsert_admin_assignments(teacher_id, assignments)


def save_leaves_data(
    db, teacher_id: int, leaves: List[Dict[str, Any]]
) -> None:
    _repo(db).upsert_leaves(teacher_id, leaves)


# ── Dropdowns ────────────────────────────────────────────────────

def get_select_data(db) -> Dict[str, Any]:
    repo = _repo(db)
    admin_types = repo.list_admin_assignment_types()
    admin_task_hours = {t['name']: t['default_hours'] for t in admin_types}
    return {
        'departments': repo.list_academic_departments(),
        'academic_years': [
            {'code': y, 'label': academic_year_label(y)}
            for y in repo.list_academic_years()
        ],
        'research_types': repo.list_research_activity_types(),
        'admin_task_types': admin_types,
        'admin_task_hours': admin_task_hours,
        'leave_types': ['تفرغ علمي', 'تفرغ دراسي', 'إيفاد بالداخل'],
    }


def get_teachers_by_dept(db, department_id: int) -> List[Dict[str, Any]]:
    return _repo(db).list_teachers_by_department(department_id)


# ── Faculty Affairs Office (مكتب إدارة أعضاء هيئة التدريس) ──────

def list_members_summary(db) -> List[Dict[str, Any]]:
    """All active teaching members with display fields (member pickers)."""
    return _repo(db).list_members_summary()


def compute_leave_status(
    start_date: str, end_date: Optional[str], today: Optional[str] = None,
) -> str:
    """Leave status derived from dates only (حالية / قادمة / منتهية)."""
    from datetime import date
    if not start_date:
        return 'حالية'
    if today is None:
        today = date.today().isoformat()
    if end_date and end_date < today:
        return 'منتهية'
    if start_date > today:
        return 'قادمة'
    return 'حالية'


def leave_duration_days(
    start_date: str, end_date: Optional[str],
) -> int:
    """Inclusive day count between start and end (at least 1)."""
    from datetime import date
    if not start_date:
        return 0
    try:
        s = date.fromisoformat(start_date)
    except ValueError:
        return 0
    if not end_date:
        return 1
    try:
        e = date.fromisoformat(end_date)
    except ValueError:
        return 1
    return max(0, (e - s).days + 1)


def get_leave_report_data(db, teacher_id: int) -> Optional[Dict[str, Any]]:
    """تقرير إجازات عضو: بياناته + مقرراته (الفصل النشط) + إجازاته مع الحالة والمدة."""
    repo = _repo(db)
    teacher = repo.get_teacher_profile(teacher_id)
    if not teacher:
        return None

    active = get_active_semester(db)
    academic_year = active.get('academic_year', '')
    semester = active.get('semester', 1)

    form = None
    try:
        form = get_performance_form_data(db, teacher_id, academic_year, semester)
    except Exception:
        form = None

    header = None
    courses = []
    if form:
        header = form.get('header')
        courses = form.get('basic_teaching') or []

    # Full detail list (status, duration, notes) for companion views.
    detail_leaves = []
    for lv in repo.get_leaves(teacher_id, academic_year, semester):
        start_date = lv.get('start_date') or ''
        end_date = lv.get('end_date') or None
        detail_leaves.append({
            'type': _clean_field(lv.get('leave_type')),
            'leave_type': lv.get('leave_type', ''),
            'decision_number': lv.get('decision_number') or '',
            'decision_authority': lv.get('decision_authority') or '',
            'decision_date': lv.get('decision_date') or '',
            'start_date': start_date,
            'end_date': lv.get('end_date') or '',
            'hours': lv.get('hours') or 0,
            'notes': lv.get('notes') or '',
            'status': compute_leave_status(start_date, end_date),
            'duration_days': leave_duration_days(start_date, end_date),
        })

    # Leaves for the official خامساً section: prefer the semester-filtered
    # rows from the performance form so the printed report matches the form.
    leaves = form.get('leaves') if form and form.get('leaves') else detail_leaves

    return {
        'teacher': teacher,
        'header': header,
        'college_name': COLLEGE_NAME,
        'semester_label': SEMESTER_LABELS.get(semester, ''),
        'academic_year': academic_year,
        'semester': semester,
        'courses': courses,
        'leaves': leaves,
        'leaves_details': detail_leaves,
        'leaves_count': len(leaves),
        'grand_total': (form.get('grand_total') if form else None),
    }


# ── Course-Level Report (محضر مقرر) ──────────────────────────────

def get_course_report_data(
    db, course_id: int, academic_year: str, semester: int,
    department_id: int = None,
) -> Optional[Dict[str, Any]]:
    """Assemble the official course report data for ONE course across
    every teacher assigned to it in the selected term + department."""
    repo = _repo(db)

    course = repo.get_course_by_id(course_id)
    if not course:
        return None

    dept_name = course.get('dept_name') or ''
    if department_id:
        row = db.execute(
            'SELECT name FROM departments '
            'WHERE id = ? AND deleted_at IS NULL',
            (department_id,),
        ).fetchone()
        if row:
            dept_name = row['name']

    raw_entries = repo.get_course_teaching_entries(
        course_id, academic_year, department_id)

    entries = []
    total_hours = 0.0
    for idx, e in enumerate(raw_entries, 1):
        lt_raw = e.get('lecture_type') or ''
        if lt_raw == 'practical':
            hours = e.get('practical_hours') or 0
        else:
            hours = e.get('theoretical_hours') or 0
        if hours <= 0:
            hours = _calculate_hours(
                e.get('start_time'), e.get('end_time'))
        hours = int(hours) if hours else 0
        total_hours += hours
        entries.append({
            'index': idx,
            'teacher_name': e.get('teacher_name') or '',
            'teacher_rank': e.get('teacher_rank') or '',
            'lecture_type': LECTURE_TYPE_MAP.get(lt_raw, lt_raw),
            'course_phase': YEAR_LABELS.get(
                e.get('course_year'), str(e.get('course_year') or '')),
            'department': e.get('dept_name') or '',
            'group_number': e.get('student_section') or '',
            'student_count': '',
            'day': e.get('day') or '',
            'start_time': e.get('start_time') or '',
            'end_time': e.get('end_time') or '',
            'hours': hours,
        })

    # Official paper layout always shows at least 6 rows
    while len(entries) < 6:
        entries.append({
            'index': len(entries) + 1,
            'teacher_name': '', 'teacher_rank': '',
            'lecture_type': '', 'course_phase': '',
            'department': '', 'group_number': '',
            'student_count': '', 'day': '',
            'start_time': '', 'end_time': '', 'hours': '',
        })

    th = course.get('theoretical_hours') or 0
    ph = course.get('practical_hours') or 0
    if th and ph:
        type_label = (
            'نظري (' + str(th) + ') / '
            'عملي (' + str(ph) + ')')
    elif th:
        type_label = 'نظري'
    elif ph:
        type_label = 'عملي'
    else:
        type_label = ''

    total_val = int(total_hours) \
        if float(total_hours).is_integer() else total_hours

    return {
        'course': {
            'id': course['id'],
            'name': course.get('name', ''),
            'code': course.get('code', ''),
            'phase': YEAR_LABELS.get(course.get('year'), ''),
            'department': dept_name,
            'type_label': type_label,
            'credit_hours': (th + ph) if (th or ph) else '',
        },
        'entries': entries,
        'total_hours': total_val,
        'header': {
            'org_name': COLLEGE_NAME,
            'college_name': COLLEGE_NAME,
            'academic_year': academic_year,
            'academic_year_label': academic_year_label(academic_year),
            'semester_number': semester,
            'semester_label': SEMESTER_LABELS.get(semester, ''),
            'term_start_date': _clean_field(semester_bounds(academic_year, semester)[0]),
            'term_end_date': _clean_field(semester_bounds(academic_year, semester)[1]),
        },
    }
