"""Public portal data access — read-only queries for the college public site.

All queries here are safe to run without an authenticated session.
"""

from __future__ import annotations

from typing import Dict, List

from services.timetable_service import active_version_condition


def get_departments(db) -> List[Dict]:
    return [dict(r) for r in db.execute(
        'SELECT id, name, semesters, has_sections FROM departments '
        'WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()]


def get_department(db, department_id: int) -> Dict | None:
    row = db.execute(
        'SELECT id, name, semesters, has_sections FROM departments '
        'WHERE id = ? AND hidden = 0 AND deleted_at IS NULL',
        (department_id,),
    ).fetchone()
    return dict(row) if row else None


def get_majors(db, department_id: int) -> List[str]:
    return [r['name'] for r in db.execute(
        'SELECT name FROM department_majors WHERE department_id = ? ORDER BY name',
        (department_id,),
    ).fetchall()]


def get_periods(db) -> List[Dict]:
    return [dict(r) for r in db.execute(
        'SELECT * FROM period_settings ORDER BY sort_order'
    ).fetchall()]


def get_active_entries(db, department_id: int | None = None,
                       semester: int | None = None) -> List[Dict]:
    conditions = ['t.deleted_at IS NULL', active_version_condition('t')]
    params: list = []
    if department_id:
        conditions.append('(t.department_id = ? OR t.department_id IS NULL)')
        params.append(department_id)
    if semester:
        conditions.append('t.semester = ?')
        params.append(semester)
    where = ' AND '.join(conditions)
    return [dict(r) for r in db.execute(
        'SELECT t.*, c.name as course_name, c.code as course_code, '
        'tc.name as teacher_name, r.name as room_name, '
        't.start_time as start_time, t.end_time as end_time '
        'FROM timetable t '
        'LEFT JOIN courses c ON t.course_id = c.id '
        'LEFT JOIN teachers tc ON t.teacher_id = tc.id '
        'LEFT JOIN rooms r ON t.room_id = r.id '
        f'WHERE {where} ORDER BY t.day, t.start_time',
        params,
    ).fetchall()]


def get_active_timetable_course_ids(db) -> set:
    """Set of course ids that appear in the active timetable."""
    rows = db.execute(
        'SELECT DISTINCT course_id FROM timetable t '
        f'WHERE t.deleted_at IS NULL AND t.course_id IS NOT NULL AND {active_version_condition("t")}'
    ).fetchall()
    return {r['course_id'] for r in rows}


def get_course_department_ids(db) -> Dict[int, int]:
    """Map ``course_id`` -> ``department_id`` from the ``course_departments`` table."""
    result: Dict[int, int] = {}
    for r in db.execute(
        'SELECT course_id, department_id FROM course_departments '
        'WHERE course_id IS NOT NULL AND department_id IS NOT NULL '
        'ORDER BY id'
    ).fetchall():
        result.setdefault(r['course_id'], r['department_id'])
    return result


def get_course_files(db, course_id=None, file_type=None, status=('approved', 'published')) -> List[Dict]:
    """Course-owned files from the unified ``course_files`` store.

    Every file belongs to a course; the uploader (teacher/R&D) is metadata
    only.  ``status`` filters visibility (default: public ``approved`` /
    ``published``).  Rows are ordered ``(course_id, id ASC)`` so callers that
    collapse to one file per course keep the newest one.
    """
    conditions = []
    params: list = []
    if course_id is not None:
        conditions.append('cf.course_id = ?')
        params.append(course_id)
    if file_type:
        conditions.append('cf.file_type = ?')
        params.append(file_type)
    if status is not None:
        if isinstance(status, (list, tuple)):
            conditions.append('cf.status IN (%s)' % ','.join('?' * len(status)))
            params.extend(status)
        else:
            conditions.append('cf.status = ?')
            params.append(status)
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    return [dict(r) for r in db.execute(
        'SELECT cf.id, cf.course_id, cf.file_type, cf.filename, '
        'cf.original_filename, cf.file_size, cf.uploaded_by, cf.teacher_id, '
        'cf.submission_id, cf.status, cf.created_at, cf.updated_at, '
        't.name AS teacher_name, COALESCE(u.label, u.username) AS uploader_name '
        'FROM course_files cf '
        'LEFT JOIN teachers t ON cf.teacher_id = t.id '
        'LEFT JOIN users u ON cf.uploaded_by = u.id '
        f'{where} ORDER BY cf.course_id, cf.id ASC',
        params,
    ).fetchall()]


def get_course_file(db, file_id: int, status=('approved', 'published')) -> Dict | None:
    """Single ``course_files`` row (for the download route)."""
    params: list = [file_id]
    status_clause = ''
    if status is not None:
        if isinstance(status, (list, tuple)):
            status_clause = ' AND cf.status IN (%s)' % ','.join('?' * len(status))
            params.extend(status)
        else:
            status_clause = ' AND cf.status = ?'
            params.append(status)
    row = db.execute(
        'SELECT cf.id, cf.course_id, cf.file_type, cf.filename, '
        'cf.original_filename, cf.file_size, cf.uploaded_by, cf.teacher_id, '
        'cf.submission_id, cf.status, cf.created_at, cf.updated_at, '
        'c.name AS course_name, c.code AS course_code, '
        't.name AS teacher_name '
        'FROM course_files cf '
        'LEFT JOIN courses c ON cf.course_id = c.id '
        'LEFT JOIN teachers t ON cf.teacher_id = t.id '
        f'WHERE cf.id = ?{status_clause}',
        params,
    ).fetchone()
    return dict(row) if row else None


def get_course_vocabularies(db) -> Dict[int, Dict]:
    rows = get_course_files(db, file_type='vocabulary', status='approved')
    return {r['course_id']: r for r in rows}


def get_approved_course_forms(db) -> Dict[int, Dict]:
    rows = get_course_files(db, file_type='form', status=('approved', 'published'))
    return {r['course_id']: r for r in rows}


def get_course_content_files(db) -> tuple:
    """One-pass loader of public course files, split by type.

    Returns ``(forms, vocab, syllabi)`` with identical contents and ordering
    semantics as calling ``get_approved_course_forms``,
    ``get_course_vocabularies`` and ``get_teacher_syllabus_files``
    individually, but with a single ``course_files`` scan.
    """
    rows = get_course_files(db, status=('approved', 'published'))
    forms: Dict[int, Dict] = {}
    vocab: Dict[int, Dict] = {}
    syllabi: Dict[str, Dict] = {}
    for r in rows:
        ft = r['file_type']
        if ft == 'form':
            forms[r['course_id']] = r
        elif ft == 'vocabulary' and r['status'] == 'approved':
            vocab[r['course_id']] = r
        elif ft == 'syllabus' and r['status'] == 'approved':
            syllabi[f"{r['teacher_id']}:{r['course_id']}"] = r
    return forms, vocab, syllabi


def get_teacher_syllabus_files(db) -> Dict[str, Dict]:
    rows = get_course_files(db, file_type='syllabus', status='approved')
    return {f"{r['teacher_id']}:{r['course_id']}": r for r in rows}


def get_course_syllabus_files(db) -> Dict[int, List[Dict]]:
    rows = get_course_files(db, file_type='syllabus', status='approved')
    files: Dict[int, List[Dict]] = {}
    for r in rows:
        files.setdefault(r['course_id'], []).append(r)
    return files


def get_published_exams(db) -> List[Dict]:
    """Public exam schedule: confirmed ('scheduled') and officially 'published' rows."""
    return [dict(r) for r in db.execute(
        'SELECT es.*, d.name as department_name, c.name as course_name, '
        'c.code as course_code, r.name as room_name '
        'FROM exam_schedule es '
        'LEFT JOIN departments d ON es.department_id = d.id '
        'LEFT JOIN courses c ON es.course_id = c.id '
        'LEFT JOIN rooms r ON es.room_id = r.id '
        "WHERE es.status IN ('scheduled', 'published') "
        'ORDER BY es.exam_date, es.start_time, es.department_id, es.semester'
    ).fetchall()]


def get_courses(db) -> List[Dict]:
    return [dict(r) for r in db.execute(
        'SELECT id, code, name, department_id, department, year, semester, '
        'theoretical_hours, practical_hours, total_hours, accreditation, icon '
        'FROM courses WHERE deleted_at IS NULL ORDER BY year, semester, name'
    ).fetchall()]


def get_active_semester(db) -> Dict:
    """Return the currently active semester label (e.g. ``خريف 2026``) plus its code.

    Falls back to a season+year derived from the current date so the public
    portal can always show a meaningful term name.
    """
    row = db.execute(
        'SELECT code, season, year, name_ar FROM semesters '
        'WHERE is_active = 1 AND deleted_at IS NULL LIMIT 1'
    ).fetchone()
    if row:
        name_ar = (row['name_ar'] or '').strip()
        if not name_ar:
            season_ar = 'خريف' if (row['season'] or '').lower() == 'fall' else 'ربيع'
            name_ar = f'{season_ar} {row["year"]}'
        return {'code': row['code'], 'label': name_ar}
    from datetime import date
    today = date.today()
    season = 'fall' if today.month >= 9 else 'spring'
    year = today.year
    season_ar = 'خريف' if season == 'fall' else 'ربيع'
    return {'code': f'{season}_{year}', 'label': f'{season_ar} {year}'}


def get_home_stats(db) -> Dict:
    return {
        'departments': db.execute(
            'SELECT COUNT(*) FROM departments WHERE hidden = 0 AND deleted_at IS NULL'
        ).fetchone()[0],
        'courses': db.execute(
            'SELECT COUNT(*) FROM courses WHERE deleted_at IS NULL'
        ).fetchone()[0],
        'teachers': db.execute(
            'SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL'
        ).fetchone()[0],
        'rooms': db.execute(
            'SELECT COUNT(*) FROM rooms WHERE deleted_at IS NULL'
        ).fetchone()[0],
    }
