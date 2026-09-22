"""Academic calendar — semester overview + per-semester details.

Rebuilt on the current data model: the semester dimension lives in
``academic_periods`` (year + term خريف/ربيع) and is linked to course/timetable
activity through ``semester_code`` codes (``fall_YYYY`` / ``spring_YYYY``)
on ``timetable_versions`` and ``teacher_taught_courses``.

The index page renders one card per period with live stats, and the detail
page (``view_semester``) shows the period's courses, timetable, exams,
teachers and departments.

/     /     >---- التقويم الأكاديمي: بطاقات فصول + إحصائيات حية + صفحة تفاصيل لكل فصل.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, url_for

from flask_db import get_db
from security import current_user, login_required, permission_required

bp = Blueprint('academic_calendar', __name__, url_prefix='/academic-calendar')

TERM_TO_SEASON = {'خريف': 'fall', 'ربيع': 'spring'}
SEASON_TO_TERM = {'fall': 'خريف', 'spring': 'ربيع'}
SEASON_AR = {'fall': 'خريفي', 'spring': 'ربيعي'}
SEASON_FULL_AR = {'fall': 'خريف', 'spring': 'ربيع'}


# /     /     >---- رسمياً الفصل النشط يُحدد من الأقدم وليس من التاريخ فقط
def _computed_semester_code() -> str:
    """Current semester code using the August 1 boundary (fall starts ≥ Aug)."""
    today = date.today()
    season = 'fall' if today.month >= 8 else 'spring'
    return f'{season}_{today.year}'


def _period_to_code(year: int, term: str) -> str:
    """Map an academic_periods row (year + term) to a semester_code string."""
    season = TERM_TO_SEASON.get(term)
    if not season:
        return ''
    return f'{season}_{year}'


def _period_status(code: str, current: str) -> str:
    """active / upcoming / past — compared by (year, season) sort position."""
    if not code:
        return 'past'
    if code == current:
        return 'active'

    def _pos(c: str):
        season, _, year = c.partition('_')
        return (int(year) if year.isdigit() else 0, 2 if season == 'fall' else 1)

    return 'past' if _pos(code) < _pos(current) else 'upcoming'


# /     /     >---- كل الإحصائيات تُحسب استعلاماً واحداً لكل الفصول
def _get_semester_stats(db):
    """Aggregate per-semester_code stats from all activity tables."""
    stats = {}

    for r in db.execute(
        '''SELECT semester_code,
                  COUNT(DISTINCT course_id)   AS courses_count,
                  COUNT(DISTINCT teacher_id)  AS teachers_count,
                  COUNT(DISTINCT department_id) AS departments_count
           FROM teacher_taught_courses
           WHERE semester_code != ''
           GROUP BY semester_code'''
    ):
        stats.setdefault(r['semester_code'], {})
        stats[r['semester_code']]['courses_count'] = r['courses_count']
        stats[r['semester_code']]['teachers_count'] = r['teachers_count']
        stats[r['semester_code']]['departments_count'] = r['departments_count']

    for r in db.execute(
        '''SELECT v.semester_code AS semester_code, COUNT(*) AS versions_count
           FROM timetable_versions v
           WHERE v.semester_code != ''
           GROUP BY v.semester_code'''
    ):
        stats.setdefault(r['semester_code'], {})
        stats[r['semester_code']]['versions_count'] = r['versions_count']
        stats[r['semester_code']]['departments_count'] = max(
            stats[r['semester_code']].get('departments_count', 0),
            db.execute(
                'SELECT COUNT(DISTINCT department_id) FROM timetable_versions '
                'WHERE semester_code = ?',
                (r['semester_code'],),
            ).fetchone()[0],
        )

    for r in db.execute(
        '''SELECT v.semester_code AS semester_code, COUNT(t.id) AS entries_count
           FROM timetable t
           JOIN timetable_versions v ON t.version_id = v.id
           WHERE t.deleted_at IS NULL AND v.semester_code != ''
           GROUP BY v.semester_code'''
    ):
        stats.setdefault(r['semester_code'], {})
        stats[r['semester_code']]['entries_count'] = r['entries_count']

    for r in db.execute(
        '''SELECT v.semester_code AS semester_code, COUNT(es.id) AS exams_count
           FROM exam_schedule es
           JOIN timetable_versions v
             ON v.department_id = es.department_id AND v.semester = es.semester
           WHERE v.semester_code != ''
           GROUP BY v.semester_code'''
    ):
        stats.setdefault(r['semester_code'], {})
        stats[r['semester_code']]['exams_count'] = r['exams_count']

    return stats


# /     /     >---- نصنع بطاقة الفصل/الفترة مع كل الإحصائيات
def _semester_cards(db):
    """Build semester cards from academic_periods (newest first)."""
    periods = [dict(r) for r in db.execute(
        '''SELECT id, year, term, label FROM academic_periods
           ORDER BY year DESC, CASE term WHEN 'خريف' THEN 0 ELSE 1 END'''
    )]
    stats = _get_semester_stats(db)
    current = _computed_semester_code()

    cards = []
    for p in periods:
        code = _period_to_code(p['year'], p['term'])
        season = TERM_TO_SEASON.get(p['term'], '')
        s = stats.get(code) or {}
        cards.append({
            'id': p['id'],
            'code': code,
            'term': p['term'],
            'season': season,
            'year': p['year'],
            'name_ar': p['label'] or f"{p['term']} {p['year']}",
            'name_en': f"{SEASON_AR.get(season, '')} {p['year']}".strip() if season else '',
            'status': _period_status(code, current),
            'is_active': code == current,
            'courses_count': s.get('courses_count', 0),
            'teachers_count': s.get('teachers_count', 0),
            'departments_count': s.get('departments_count', 0),
            'versions_count': s.get('versions_count', 0),
            'entries_count': s.get('entries_count', 0),
            'exams_count': s.get('exams_count', 0),
        })
    return cards, current


@bp.route('')
@login_required
@permission_required('academic_calendar.manage')
def index():
    db = get_db()
    cards, current_code = _semester_cards(db)

    active = next((c for c in cards if c['is_active']), None)
    upcoming = [c for c in cards if c['status'] == 'upcoming']
    past = [c for c in cards if c['status'] == 'past']

    stats = {
        'total': len(cards),
        'active': active,
        'upcoming': len(upcoming),
        'past': len(past),
    }

    return render_template(
        'academic_calendar/index.html',
        semesters=[c for c in cards if c['status'] != 'past'],
        past_semesters=past,
        stats=stats,
        season_ar=SEASON_AR,
        season_full_ar=SEASON_FULL_AR,
        user=current_user(),
    )


@bp.route('/<semester_code>')
@login_required
@permission_required('academic_calendar.manage')
def view_semester(semester_code: str):
    db = get_db()
    current = _computed_semester_code()

    # /     /     >---- نبحث عن الفترة المطابقة في academic_periods أو أي نشاط مطابق
    period = None
    for r in db.execute(
        "SELECT id, year, term, label FROM academic_periods "
        "WHERE (CASE WHEN term = 'خريف' THEN 'fall_' || year ELSE 'spring_' || year END) = ?",
        (semester_code,),
    ):
        period = dict(r)
        break

    code = semester_code
    season, _, year_str = code.partition('_')
    if season not in SEASON_TO_TERM or not year_str.isdigit():
        flash('الفصل غير موجود', 'error')
        return redirect(url_for('academic_calendar.index'))
    year = int(year_str)

    semester = {
        'code': code,
        'term': SEASON_TO_TERM.get(season, ''),
        'season': season,
        'year': year,
        'name_ar': (period['label'] if period else '') or (
            f'{SEASON_FULL_AR.get(season, "")} {year}'.strip() if year else code
        ),
        'name_en': f"{SEASON_AR.get(season, '')} {year}".strip() if (season and year) else code,
        'status': _period_status(code, current),
        'is_active': code == current,
    }

    stats_rows = _get_semester_stats(db)
    s = stats_rows.get(code) or {}
    semester.update({
        'courses_count': s.get('courses_count', 0),
        'teachers_count': s.get('teachers_count', 0),
        'departments_count': s.get('departments_count', 0),
        'versions_count': s.get('versions_count', 0),
        'entries_count': s.get('entries_count', 0),
        'exams_count': s.get('exams_count', 0),
    })

    courses = [dict(r) for r in db.execute(
        '''SELECT DISTINCT c.id, c.code, c.name, COALESCE(d.name, '') AS dept_name
           FROM courses c
           JOIN teacher_taught_courses ttc ON ttc.course_id = c.id
           LEFT JOIN departments d ON c.department_id = d.id
           WHERE ttc.semester_code = ?
           ORDER BY c.name''',
        (code,),
    )]

    # إذا ما في نشاط مسجّل في teacher_taught_courses نجرب الجدول
    if not courses:
        courses = [dict(r) for r in db.execute(
            '''SELECT DISTINCT c.id, c.code, c.name, COALESCE(d.name, '') AS dept_name
               FROM timetable t
               JOIN timetable_versions v ON t.version_id = v.id
               JOIN courses c ON t.course_id = c.id
               LEFT JOIN departments d ON v.department_id = d.id
               WHERE v.semester_code = ? AND t.deleted_at IS NULL
               ORDER BY c.name''',
            (code,),
        )]

    teachers = [dict(r) for r in db.execute(
        '''SELECT DISTINCT t.id, t.name
           FROM teachers t
           JOIN teacher_taught_courses ttc ON ttc.teacher_id = t.id
           WHERE ttc.semester_code = ?
           ORDER BY t.name''',
        (code,),
    )]

    departments = [dict(r) for r in db.execute(
        '''SELECT DISTINCT d.id, d.name
           FROM departments d
           JOIN teacher_taught_courses ttc ON ttc.department_id = d.id
           WHERE ttc.semester_code = ?
           ORDER BY d.name''',
        (code,),
    )]

    timetable_entries = [dict(r) for r in db.execute(
        '''SELECT t.id, t.day AS day_name, t.start_time, t.end_time, t.period,
                  c.code AS course_code, c.name AS course_name,
                  COALESCE(te.name, '') AS teacher_name,
                  COALESCE(r.name, '') AS room_name
           FROM timetable t
           JOIN timetable_versions v ON t.version_id = v.id
           JOIN courses c ON t.course_id = c.id
           LEFT JOIN teachers te ON t.teacher_id = te.id
           LEFT JOIN rooms r ON t.room_id = r.id
           WHERE v.semester_code = ? AND t.deleted_at IS NULL
           ORDER BY t.day, t.start_time''',
        (code,),
    )]

    exams = [dict(r) for r in db.execute(
        '''SELECT es.id, es.exam_date, es.start_time, es.end_time, es.status,
                  c.code AS course_code, c.name AS course_name,
                  COALESCE(r.name, '') AS room_name,
                  COALESCE(d.name, '') AS dept_name
           FROM exam_schedule es
           JOIN timetable_versions v
             ON v.department_id = es.department_id AND v.semester = es.semester
           LEFT JOIN courses c ON es.course_id = c.id
           LEFT JOIN rooms r ON es.room_id = r.id
           LEFT JOIN departments d ON es.department_id = d.id
           WHERE v.semester_code = ? AND es.status != 'deleted'
           ORDER BY es.exam_date, es.start_time''',
        (code,),
    )]

    return render_template(
        'academic_calendar/view.html',
        semester=semester,
        courses=courses,
        teachers=teachers,
        departments=departments,
        timetable_entries=timetable_entries,
        exams=exams,
        season_ar=SEASON_AR,
        user=current_user(),
    )