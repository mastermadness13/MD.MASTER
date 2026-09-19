"""Faculty Affairs Office service — teaching assignments and dashboard data.

Module-level functions take a database connection as the first argument and
run raw SQL, mirroring the other domain services in this package.

/     /     >---- خدمة شؤون هيئة التدريس: التكليفات التدريسية وبيانات اللوحات.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from utils.format import paginate

# /     /     >---- الساعات النظرية تُحسب 1.0 والعملية 0.75 من العبء الأسبوعي
PRACTICAL_WEIGHT = 0.75
# /     /     >---- من تجاوز هذا العبء المحسوب يُعتبر محمّلاً بشكل زائد
OVERLOAD_THRESHOLD = 18


# /     /     >---- بناء شروط استعلام التكليفات (بحث + قسم + رتبة)
def _assignments_where(search='', department_id=None, rank_id=None):
    where = ['t.deleted_at IS NULL']
    params: list = []
    if search:
        where.append('(t.name LIKE ? OR t.academic_number LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%'])
    if department_id:
        where.append('t.department_id = ?')
        params.append(department_id)
    if rank_id:
        where.append('t.rank_id = ?')
        params.append(rank_id)
    return where, params


# /     /     >---- الإجمالات التدريسية لكل أستاذ + بيانات الفلاتر للصفحة
def get_teaching_assignments(
    db,
    search: str = '',
    department_id: Optional[int] = None,
    rank_id: Optional[int] = None,
    page: int = 1,
) -> Tuple[List[Dict[str, Any]], int, int, int, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return per-teacher teaching load aggregates plus filter dropdown data."""
    where, params = _assignments_where(search, department_id, rank_id)

    base = (
        'SELECT t.id, t.name, t.academic_number, t.phone, '
        'd.name AS dept_name, r.name_ar AS rank_name, '
        'COUNT(tt.id) AS assignment_count, '
        'COALESCE(SUM(c.theoretical_hours), 0) AS theory_hours, '
        'COALESCE(SUM(c.practical_hours), 0) AS practical_hours '
        'FROM teachers t '
        'LEFT JOIN departments d ON t.department_id = d.id '
        'LEFT JOIN academic_ranks r ON t.rank_id = r.id '
        'LEFT JOIN timetable tt ON tt.teacher_id = t.id AND tt.deleted_at IS NULL '
        'AND (tt.version_id IS NULL OR tt.version_id IN '
        "(SELECT id FROM timetable_versions WHERE status = 'active')) "
        'LEFT JOIN courses c ON tt.course_id = c.id AND c.deleted_at IS NULL '
        f'WHERE {" AND ".join(where)} '
        'GROUP BY t.id ORDER BY t.name'
    )

    rows, total, pg, pp = paginate(base, params, page)
    for row in rows:
        # /     /     >---- حساب العبء الموزون وتحديد المُحمّلين زائداً
        weighted = row['theory_hours'] + PRACTICAL_WEIGHT * row['practical_hours']
        row['weighted_hours'] = round(weighted, 1)
        row['overloaded'] = weighted > OVERLOAD_THRESHOLD

    departments = [
        dict(r) for r in db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()
    ]
    ranks = [
        dict(r) for r in db.execute(
            'SELECT * FROM academic_ranks ORDER BY sort_order'
        ).fetchall()
    ]
    return rows, total, pg, pp, departments, ranks


# /     /     >---- إجماليات ملخصة لرأس صفحة التكليفات
def get_teaching_assignments_summary(
    db,
    search: str = '',
    department_id: Optional[int] = None,
    rank_id: Optional[int] = None,
) -> Dict[str, int]:
    """Aggregate summary counts for the assignments page header."""
    where, params = _assignments_where(search, department_id, rank_id)
    where_clause = ' AND '.join(where)

    total_faculty = db.execute(
        f'SELECT COUNT(*) FROM teachers t WHERE {where_clause}',
        params,
    ).fetchone()[0]

    row = db.execute(
        f'''SELECT COUNT(tt.id) AS assigned,
                   COUNT(DISTINCT CASE WHEN tt.teacher_id IS NOT NULL THEN t.id END) AS with_assignments
            FROM teachers t
            LEFT JOIN timetable tt ON tt.teacher_id = t.id AND tt.deleted_at IS NULL
         AND (tt.version_id IS NULL OR tt.version_id IN
             (SELECT id FROM timetable_versions WHERE status = 'active'))
            WHERE {where_clause}''',
        params,
    ).fetchone()
    assigned = row['with_assignments'] or 0

    # /     /     >---- عدد المحمّلين زائداً حسب العبء الموزون
    overloaded = db.execute(
        f'''SELECT COUNT(*) FROM (
                SELECT t.id
                FROM teachers t
                LEFT JOIN timetable tt ON tt.teacher_id = t.id AND tt.deleted_at IS NULL
         AND (tt.version_id IS NULL OR tt.version_id IN
             (SELECT id FROM timetable_versions WHERE status = 'active'))
                LEFT JOIN courses c ON tt.course_id = c.id AND c.deleted_at IS NULL
                WHERE {where_clause}
                GROUP BY t.id
                HAVING (COALESCE(SUM(c.theoretical_hours), 0)
                        + ? * COALESCE(SUM(c.practical_hours), 0)) > ?
            )''',
        params + [PRACTICAL_WEIGHT, OVERLOAD_THRESHOLD],
    ).fetchone()[0]

    return {
        'total_faculty': total_faculty,
        'assigned_faculty': assigned,
        'overloaded_count': overloaded,
    }


# /     /     >---- بيانات لوحة شؤون هيئة التدريس (العدادات والتفاصيل)
def get_faculty_dept_dashboard_data(db):
    """Data for the Faculty Affairs Office sub-admin dashboard."""
    data = {}

    data['total_faculty'] = db.execute(
        'SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL'
    ).fetchone()[0]

    data['total_assignments'] = db.execute(
        'SELECT COUNT(*) FROM timetable WHERE deleted_at IS NULL '
        'AND (version_id IS NULL OR version_id IN '
        '(SELECT id FROM timetable_versions WHERE status = \'active\'))'
    ).fetchone()[0]

    data['assigned_faculty'] = db.execute(
        'SELECT COUNT(DISTINCT teacher_id) FROM timetable '
        'WHERE deleted_at IS NULL AND teacher_id IS NOT NULL '
        'AND (version_id IS NULL OR version_id IN '
        '(SELECT id FROM timetable_versions WHERE status = \'active\'))'
    ).fetchone()[0]

    # /     /     >---- إجمالي الساعات النظرية والعملية والحد الموزون والمتوسط
    load_row = db.execute(
        '''SELECT COALESCE(SUM(c.theoretical_hours), 0) AS theory,
                  COALESCE(SUM(c.practical_hours), 0) AS practical
           FROM timetable tt
           LEFT JOIN courses c ON tt.course_id = c.id
           WHERE tt.deleted_at IS NULL
           AND (tt.version_id IS NULL OR tt.version_id IN
               (SELECT id FROM timetable_versions WHERE status = 'active'))'''
    ).fetchone()
    theory = load_row['theory'] or 0
    practical = load_row['practical'] or 0
    total_weighted = theory + PRACTICAL_WEIGHT * practical
    data['total_theory_hours'] = theory
    data['total_practical_hours'] = practical
    data['total_weighted_hours'] = round(total_weighted, 1)
    data['avg_weighted_hours'] = (
        round(total_weighted / data['assigned_faculty'], 1)
        if data['assigned_faculty'] else 0
    )

    data['overloaded_count'] = db.execute(
        '''SELECT COUNT(*) FROM (
               SELECT t.id
               FROM teachers t
               LEFT JOIN timetable tt ON tt.teacher_id = t.id AND tt.deleted_at IS NULL
         AND (tt.version_id IS NULL OR tt.version_id IN
             (SELECT id FROM timetable_versions WHERE status = 'active'))
               LEFT JOIN courses c ON tt.course_id = c.id AND c.deleted_at IS NULL
               WHERE t.deleted_at IS NULL
               GROUP BY t.id
               HAVING (COALESCE(SUM(c.theoretical_hours), 0)
                       + ? * COALESCE(SUM(c.practical_hours), 0)) > ?
           )''',
        (PRACTICAL_WEIGHT, OVERLOAD_THRESHOLD),
    ).fetchone()[0]

    # /     /     >---- عدد أعضاء الهيئة لكل قسم أكاديمي
    dept_rows = db.execute(
        '''SELECT d.id, d.name, COUNT(t.id) AS faculty_count
           FROM departments d
           LEFT JOIN teachers t ON t.department_id = d.id AND t.deleted_at IS NULL
           WHERE d.type = 'academic' AND d.deleted_at IS NULL
           GROUP BY d.id
           ORDER BY d.name'''
    ).fetchall()
    data['departments'] = [dict(r) for r in dept_rows]

    recent = db.execute(
        '''SELECT t.id, t.name, t.academic_number, d.name AS dept_name, t.created_at
           FROM teachers t
           LEFT JOIN departments d ON t.department_id = d.id
           WHERE t.deleted_at IS NULL
           ORDER BY t.created_at DESC, t.id DESC
           LIMIT 5'''
    ).fetchall()
    data['recent_faculty'] = [dict(r) for r in recent]

    return data