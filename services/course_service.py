"""Course service — CRUD, department mappings, prerequisites.

Uses ``CourseRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.

/     /     >---- خدمة المقررات: عمليات الإضافة والتعديل والحذف وربط الأقسام والمتطلبات.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from flask import session

from utils.format import SUBMISSION_STATUS_COLORS, SUBMISSION_STATUS_LABELS

logger = logging.getLogger(__name__)


class CourseService:
    """Class-based course service with repository injection.

    /     /     >---- الخدمة بشكل كلاس مع حقن المستودع.
    """

    def __init__(self, db, course_repo):
        self.db = db
        self._repo = course_repo

    # /     /     >---- قائمة المقررات: مع فلترة حسب القسم ورئيس القسم
    def list_courses(self, role: str, user_data: dict, search: str,
                     dept_filter: str, page: int = 1) -> tuple:
        where = ['c.deleted_at IS NULL']
        params: list = []
        if role == 'head_of_department':
            user_dept_id = (session.get('hod_department_id')
                            or session.get('department_id')
                            or (user_data.get('department_id') if user_data else None))
            if user_dept_id:
                dept_filter = str(user_dept_id)
        if search:
            where.append('(c.name LIKE ? OR c.code LIKE ?)')
            params.extend([f'%{search}%'] * 2)
        where_clause = ' AND '.join(where) if where else '1=1'
        dept_join = ''
        if dept_filter:
            dept_join = (
                'JOIN course_departments cd_filter '
                'ON c.id = cd_filter.course_id AND cd_filter.department_id = ?'
            )
            params.append(dept_filter)
        rows, total, pg, pp = self._repo.list_courses(where_clause, params, dept_join, page)
        departments = self._repo.list_visible_departments()
        course_depts = self._repo.get_dept_mapping([r['id'] for r in rows])
        return rows, total, pg, pp, departments, course_depts

    def get_course_dept_mapping(self, course_ids: list) -> Dict[int, List[str]]:
        return self._repo.get_dept_mapping(course_ids)

    def get_course_dept_id_mapping(self, course_ids: list) -> Dict[int, List[int]]:
        return self._repo.get_dept_id_mapping(course_ids)

    def get_create_form_data(self) -> Dict[str, Any]:
        return self._repo.get_create_form_data()

    # /     /     >---- إنشاء مقرر مع أقسامه ومتطلباته
    def create_course(self, data: Dict[str, Any], department_ids: list,
                      prerequisite_id: int = None) -> int:
        course_id = self._repo.create(data)
        self._repo.set_departments(course_id, department_ids)
        self._repo.set_prerequisites(course_id, prerequisite_id)
        return course_id

    def get_course(self, course_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(course_id)

    def get_edit_form_data(self, course_id: int) -> Dict[str, Any]:
        data = self._repo.get_edit_form_data(course_id)
        course_dept_map = self._repo.get_dept_id_mapping(
            [c['id'] for c in data['courses']]
        )
        data['course_dept_map'] = course_dept_map
        return data

    # /     /     >---- تحديث المقرر مع أقسامه ومتطلباته
    def update_course(self, course_id: int, data: Dict[str, Any],
                      department_ids: list, prerequisite_id: int = None) -> None:
        self._repo.update(course_id, data)
        self._repo.set_departments(course_id, department_ids)
        self._repo.set_prerequisites(course_id, prerequisite_id)

    def get_course_detail(self, course_id: int) -> Optional[Dict]:
        return self._repo.get_detail(course_id)

    def course_delete(self, course_id: int, history_callback=None) -> None:
        self._repo.soft_delete(course_id)
        if history_callback:
            history_callback(self.db)

    def course_restore(self, course_id: int) -> None:
        self._repo.restore(course_id)

    def course_hard_delete(self, course_id: int) -> None:
        self._repo.delete(course_id)


# /     /     >---- دوال مستوى الوحدة المحافظة على التوافق مع المسارات القديمة

def list_courses(db, role, user_data, search, dept_filter, page):
    from database.repositories.course_repository import CourseRepository
    return CourseService(db, CourseRepository(db)).list_courses(
        role, user_data, search, dept_filter, page
    )


def get_course_dept_mapping(db, course_ids):
    from database.repositories.course_repository import CourseRepository
    return CourseRepository(db).get_dept_mapping(course_ids)


def get_course_dept_id_mapping(db, course_ids):
    from database.repositories.course_repository import CourseRepository
    return CourseRepository(db).get_dept_id_mapping(course_ids)


def get_course_dept_placement_mapping(db, course_ids):
    from database.repositories.course_repository import CourseRepository
    return CourseRepository(db).get_dept_placement_mapping(course_ids)


# /     /     >---- جداول خطة الدراسة الخاصة برئيس القسم

# /     /     >---- عناوين الفصول الدراسية
SEMESTER_TITLES = {
    1: 'الفصل الأول',
    2: 'الفصل الثاني',
    3: 'الفصل الثالث',
    4: 'الفصل الرابع',
    5: 'الفصل الخامس',
    6: 'الفصل السادس',
    7: 'الفصل السابع',
    8: 'الفصل الثامن',
}

# /     /     >---- الأقسام غير العامة تبدؤ من الفصل الثاني (السنة → الفصل)
_YEAR_TO_SEMESTER = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8}

# /     /     >---- شرط الجدول الفعّال: نأخدو صفوفه النشطة فقط
_ACTIVE_TIMETABLE_WHERE = (
    'tt.deleted_at IS NULL '
    "AND (tt.version_id IS NULL OR tt.version_id IN "
    "(SELECT id FROM timetable_versions WHERE status = 'active'))"
)


# /     /     >---- خريطة course_id لأسماء الأساتذة اللي يدرّسوه هذا الفصل
def get_course_teachers_map(db, course_ids: Optional[List[int]] = None) -> Dict[int, List[str]]:
    """Map course_id -> names of teachers currently teaching it.

    Teachers come from the active timetable snapshot so the list reflects
    who is actually assigned to the course this period.
    """
    sql = (
        'SELECT tt.course_id, t.name AS teacher_name '
        'FROM timetable tt '
        'JOIN teachers t ON t.id = tt.teacher_id AND t.deleted_at IS NULL '
        f'WHERE {_ACTIVE_TIMETABLE_WHERE}'
    )
    params: list = []
    if course_ids:
        ph = ','.join('?' * len(course_ids))
        sql += f' AND tt.course_id IN ({ph})'
        params = list(course_ids)
    sql += (
        " AND (tt.department_id IS NULL "
        "OR EXISTS (SELECT 1 FROM course_departments cd "
        "WHERE cd.course_id = tt.course_id AND cd.department_id = tt.department_id) "
        "OR EXISTS (SELECT 1 FROM courses c "
        "WHERE c.id = tt.course_id AND c.department_id = tt.department_id))"
    )
    sql += ' ORDER BY t.name'

    mapping: Dict[int, List[str]] = {}
    for r in db.execute(sql, params).fetchall():
        name = (r['teacher_name'] or '').strip()
        if not name:
            continue
        names = mapping.setdefault(r['course_id'], [])
        if name not in names:
            names.append(name)
    return mapping


# /     /     >---- خريطة course_id لملخص تسليمات نماذج المحتوى
def get_course_submissions_map(db, course_ids: Optional[List[int]] = None,
                               teacher_id: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
    """Map course_id -> summary of its course-content form submissions.

    Each value carries ``latest_status``/``latest_teacher`` (the newest
    submission by sent date) and ``count``.  Pass ``teacher_id`` to restrict
    the forms counted to a single teacher's submissions.
    """
    sql = (
        'SELECT s.id, s.course_id, s.status, '
        'COALESCE(s.submitted_at, s.created_at) AS sent_at, '
        't.name AS teacher_name '
        'FROM course_content_submissions s '
        'LEFT JOIN teachers t ON t.id = s.teacher_id'
    )
    where: list = []
    params: list = []
    if course_ids:
        ph = ','.join('?' * len(course_ids))
        where.append(f's.course_id IN ({ph})')
        params.extend(course_ids)
    if teacher_id is not None:
        where.append('s.teacher_id = ?')
        params.append(teacher_id)
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY sent_at DESC'

    mapping: Dict[int, Dict[str, Any]] = {}
    for r in db.execute(sql, params).fetchall():
        info = mapping.setdefault(r['course_id'], {
            'latest_status': '', 'latest_teacher': '', 'count': 0,
        })
        info['count'] += 1
        if not info['latest_status']:
            info['latest_status'] = r['status'] or ''
            info['latest_teacher'] = (r['teacher_name'] or '').strip()
    return mapping


# /     /     >---- ترفّع بيانات المقررات بالأساتذة وحالة النموذج (استعلامان)
def attach_course_related_data(db, courses: List[Dict[str, Any]],
                               teacher_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Enrich course dicts with teachers + content-form status (two queries).

    Adds ``teachers``, ``form_status``, ``form_teacher`` and ``form_count``
    keys so any course table can show who teaches the course and whether its
    content form was filled.
    """
    ids = [c.get('id') for c in courses if c.get('id') is not None]
    teachers_map = get_course_teachers_map(db, ids) if ids else {}
    subs_map = get_course_submissions_map(db, ids, teacher_id=teacher_id) if ids else {}
    for c in courses:
        subs = subs_map.get(c.get('id'), {})
        c['teachers'] = teachers_map.get(c.get('id'), [])
        c['form_status'] = subs.get('latest_status', '')
        c['form_teacher'] = subs.get('latest_teacher', '')
        c['form_count'] = subs.get('count', 0)
    return courses


# /     /     >---- مجموع وحدات المقرر (مع خياري من الساعات النظرية+العملية)
def _course_units(course: Dict[str, Any]) -> int:
    """Total course units, falling back to theoretical + practical hours."""
    return (course.get('total_hours') or 0) \
        or ((course.get('theoretical_hours') or 0)
            + (course.get('practical_hours') or 0))


# /     /     >---- تجميع مقررات القسم (المملوكة + المعتمدة) في جداول فصول
def get_department_course_tables(db, dept_id: Optional[int]):
    """Group a department's own + signed courses into semester tables.

    The semester range comes from ``departments.semesters``: the general
    department (semesters=1) shows a single ``الفصل الأول`` table; academic
    departments show every semester ``1..semesters`` (e.g. ``1..8``) even when
    a semester has no courses yet, so الفصل الثامن (تدريب ميداني/مشروع تخرج)
    stays visible and can receive new courses.
    """
    if not dept_id:
        return {'department': None, 'semesters': []}

    dept_row = db.execute(
        'SELECT * FROM departments WHERE id = ? AND deleted_at IS NULL', (dept_id,)
    ).fetchone()
    if not dept_row:
        return {'department': None, 'semesters': []}
    dept = dict(dept_row)

    rows = db.execute(
        'SELECT DISTINCT c.id, c.code, c.name, c.year, c.semester, '
        'c.theoretical_hours, c.practical_hours, c.total_hours, c.icon, c.notes, '
        'd.name AS owner_department_name, '
        'cd.semester AS cd_semester, '
        'CASE WHEN cd.id IS NOT NULL THEN 1 ELSE 0 END AS is_signed '
        'FROM courses c '
        'LEFT JOIN departments d ON c.department_id = d.id '
        'LEFT JOIN course_departments cd '
        '  ON cd.course_id = c.id AND cd.department_id = ? '
        'WHERE c.deleted_at IS NULL '
        '  AND (c.department_id = ? OR cd.department_id = ?) '
        'ORDER BY c.year, c.code',
        (dept_id, dept_id, dept_id),
    ).fetchall()

    courses = [dict(r) for r in rows]

    attach_course_related_data(db, courses)
    teacher_map = {c['id']: c.get('teachers', []) for c in courses}
    form_map = {c['id']: c.get('form_status', '') for c in courses}

    prereq_map = {}
    if courses:
        ids = ','.join('?' * len(courses))
        prereq_rows = db.execute(
            'SELECT cp.course_id, c.code AS prereq_code '
            'FROM course_prerequisites cp '
            'JOIN courses c ON c.id = cp.prerequisite_id '
            f'WHERE cp.course_id IN ({ids})',
            [c['id'] for c in courses],
        ).fetchall()
        for r in prereq_rows:
            prereq_map.setdefault(r['course_id'], []).append(r['prereq_code'])

    is_general = (dept.get('semesters') or 0) <= 1
    tables = {}
    for c in courses:
        # /     /     >---- فصل القسم (course_departments.semester) هو المرجع لهذا القسم
        if is_general:
            sem = 1
        else:
            sem = c['cd_semester'] or c['semester'] or _YEAR_TO_SEMESTER.get(c['year'])
        if sem is None:
            continue
        theory = c['theoretical_hours'] or 0
        practical = c['practical_hours'] or 0
        total = c['total_hours'] or (theory + practical)
        tables.setdefault(sem, []).append({
            'id': c['id'],
            'code': c['code'],
            'name': c['name'],
            'icon': c['icon'] or '📖',
            'year': c['year'],
            'semester': sem,
            'units': _course_units(c),
            'theory': theory,
            'practical': practical,
            'weekly_hours': total,
            'notes': c['notes'] or '',
            'owner_department_name': c['owner_department_name'],
            'is_signed': bool(c['is_signed']),
            'requires': prereq_map.get(c['id'], []),
            'teachers': teacher_map.get(c['id'], []),
            'form_status': form_map.get(c['id'], ''),
        })

    semesters = []
    # كل الأقسام الأكاديمية تعرض فصولها كاملة (1..عدد الفصول المكوّن)، حتى لو
    # كان الفصل فارغاً — مثل الفصل الثامن (تدريب ميداني/مشروع تخرج) — ليبقى
    # ظاهراً مع زر الإضافة وأهداف السحب والنقل.
    configured = int(dept.get('semesters') or 1)
    if is_general:
        semester_range = [1]
    else:
        highest = max(tables) if tables else 0
        semester_range = list(range(1, max(configured, highest, 1) + 1))

    for sem in semester_range:
        items = sorted(tables.get(sem, []), key=lambda x: (x['code'] or ''))
        semesters.append({
            'semester': sem,
            'title': SEMESTER_TITLES.get(sem, f'الفصل {sem}'),
            'courses': items,
            'count': len(items),
            'units': sum(x['units'] for x in items),
        })

    return {
        'department': {
            'id': dept['id'],
            'name': dept['name'],
            'semesters': dept.get('semesters'),
        },
        'semesters': semesters,
    }


# /     /     >---- نقل مقرر داخل فصول نفس القسم (يرفض التنقل بين الأقسام)
def move_course_to_semester(db, course_id: int, dept_id: int,
                            semester: int):
    """Move a course into a given semester table of the SAME department.

    Only departments the course belongs to (as owner or signed) are allowed;
    cross-department moves are rejected.  Returns ``(ok, message)``.

    The move updates only the (course, department) placement
    (``course_departments.semester``).  If the department is the course's
    primary (first checked) department, ``courses.semester`` is kept in sync
    so downstream consumers (exams, public, print, timetable-sync) still work.
    """
    dept = db.execute(
        'SELECT * FROM departments WHERE id = ? AND deleted_at IS NULL', (dept_id,)
    ).fetchone()
    if not dept:
        return False, 'القسم غير موجود'
    dept = dict(dept)

    row = db.execute(
        'SELECT cd.id AS cd_id, cd.semester AS cd_semester '
        'FROM courses c '
        'LEFT JOIN course_departments cd '
        '  ON cd.course_id = c.id AND cd.department_id = ? '
        'WHERE c.id = ? AND c.deleted_at IS NULL '
        '  AND (c.department_id = ? OR cd.department_id IS NOT NULL)',
        (dept_id, course_id, dept_id),
    ).fetchone()
    if not row:
        return False, 'لا يمكن نقل المادة إلى قسم آخر — المادة لا تنتمي إلى هذا القسم'

    is_general = (dept.get('semesters') or 0) <= 1
    if is_general:
        target_semester = 1
    else:
        target_semester = semester
        if target_semester < 1 or target_semester > 8:
            return False, 'الفصل الدراسي غير صحيح'

    if row['cd_id'] is not None:
        db.execute(
            'UPDATE course_departments SET semester = ? WHERE id = ?',
            (target_semester, row['cd_id']),
        )
    else:
        # /     /     >---- قسم مالك بدون صف في course_departments: نضيف صف لتسجيل الحالة
        db.execute(
            'INSERT INTO course_departments (course_id, department_id, semester) '
            'VALUES (?, ?, ?)',
            (course_id, dept_id, target_semester),
        )

    # /     /     >---- نزامن الفصل العام لما يكون القسم هو الأساسي
    primary = db.execute(
        'SELECT cd.department_id FROM course_departments cd '
        'WHERE cd.course_id = ? ORDER BY cd.id LIMIT 1',
        (course_id,),
    ).fetchone()
    if primary and primary['department_id'] == dept_id:
        db.execute('UPDATE courses SET semester = ? WHERE id = ?',
                   (target_semester, course_id))

    db.commit()
    return True, 'تم نقل المادة بنجاح'


# /     /     >---- مزامنة سنة المقرر من فصول الجدول الفعلي
def sync_courses_from_timetable(db, dept_id: int):
    """Sync courses.year to match timetable semesters for a department.

    Reads timetable entries to determine which semester each course is
    actually scheduled under, then updates courses.year accordingly.
    Does NOT modify timetable entries.

    Returns dict with synced count, skipped count, and message list.
    """
    dept = db.execute(
        'SELECT * FROM departments WHERE id = ? AND deleted_at IS NULL', (dept_id,)
    ).fetchone()
    if not dept:
        return {'synced': 0, 'skipped': 0, 'messages': ['القسم غير موجود']}

    is_general = (dict(dept).get('semesters') or 0) <= 1
    if is_general:
        return {'synced': 0, 'skipped': 0, 'messages': ['القسم العام لا يحتاج مزامنة']}

    courses = db.execute(
        'SELECT DISTINCT c.id, c.name, c.year '
        'FROM courses c '
        'LEFT JOIN course_departments cd ON cd.course_id = c.id AND cd.department_id = ? '
        'WHERE c.deleted_at IS NULL '
        '  AND (c.department_id = ? OR cd.department_id = ?)',
        (dept_id, dept_id, dept_id),
    ).fetchall()

    synced = 0
    skipped = 0
    messages = []

    for course in courses:
        cid = course['id']
        cname = course['name']

        timetable_rows = db.execute(
            'SELECT semester, COUNT(*) as cnt FROM timetable '
            'WHERE course_id = ? AND department_id = ? AND deleted_at IS NULL '
            'GROUP BY semester ORDER BY cnt DESC',
            (cid, dept_id),
        ).fetchall()

        if not timetable_rows:
            skipped += 1
            messages.append(f'{cname} — لا توجد لها محاضرات في الجدول')
            continue

        if len(timetable_rows) == 1:
            target_sem = timetable_rows[0]['semester']
        else:
            max_count = timetable_rows[0]['cnt']
            winners = [r for r in timetable_rows if r['cnt'] == max_count]
            if len(winners) > 1:
                skipped += 1
                sem_names = ' و'.join([str(w['semester']) for w in winners])
                messages.append(f'{cname} — موجودة في السيمستر {sem_names}')
                continue
            target_sem = winners[0]['semester']

        new_year = target_sem - 1
        if new_year < 1 or new_year > 6:
            skipped += 1
            messages.append(f'{cname} — السيمستر {target_sem} خارج النطاق')
            continue

        if course['year'] != new_year:
            db.execute('UPDATE courses SET year = ? WHERE id = ?', (new_year, cid))
            synced += 1

    db.commit()

    result = {'synced': synced, 'skipped': skipped, 'messages': messages}
    return result


def get_create_form_data(db):
    from database.repositories.course_repository import CourseRepository
    data = CourseRepository(db).get_create_form_data()
    return data['departments'], data['courses'], data['course_dept_map']


def create_course(db, data, department_ids, prerequisite_id):
    from database.repositories.course_repository import CourseRepository
    repo = CourseRepository(db)
    course_id = repo.create(data)
    repo.set_departments(course_id, department_ids)
    repo.set_prerequisites(course_id, prerequisite_id)
    return course_id


def get_course(db, id):
    return db.execute('SELECT * FROM courses WHERE id = ?', (id,)).fetchone()


def get_edit_form_data(db, id):
    from database.repositories.course_repository import CourseRepository
    repo = CourseRepository(db)
    data = repo.get_edit_form_data(id)
    course_dept_map = repo.get_dept_id_mapping([c['id'] for c in data['courses']])
    return (
        data['departments'], data['courses'], course_dept_map,
        data['prereq_ids'], data['current_dept_ids'],
    )


def update_course(db, id, data, department_ids, prerequisite_id):
    from database.repositories.course_repository import CourseRepository
    repo = CourseRepository(db)
    repo.update(id, data)
    repo.set_departments(id, department_ids)
    repo.set_prerequisites(id, prerequisite_id)


def get_course_detail(db, id):
    from database.repositories.course_repository import CourseRepository
    result = CourseRepository(db).get_detail(id)
    if result is None:
        return None
    return result['course'], result['departments'], result['prerequisites']


def course_delete(db, id, history_callback):
    from services.base_service import soft_delete
    soft_delete(db, 'courses', id, history_callback)


def course_restore(db, id):
    from services.base_service import restore
    restore(db, 'courses', id)


def course_hard_delete(db, id):
    from services.base_service import hard_delete
    hard_delete(db, 'courses', id)


# /     /     >---- بيانات صفحة قائمة الإدارة (منقولة من routes/courses.py)

# /     /     >---- خريطة كلمة القسم ← أيقونة Material
DEPARTMENT_ICON_MAP = [
    ('عام', 'school'),
    ('حاسوب', 'computer'),
    ('اتصال', 'cell_tower'),
    ('نفط', 'oil_barrel'),
    ('مدني', 'engineering'),
    ('معمار', 'apartment'),
    ('بحث', 'science'),
    ('تطوير', 'science'),
    ('ميكانيك', 'precision_manufacturing'),
]


# /     /     >---- أيقونة قسم حسب الكلمة المفتاحية في الاسم
def _dept_icon(name):
    """Material Symbol icon name for a department, matched by keyword."""
    if not name:
        return 'account_balance'
    for keyword, icon in DEPARTMENT_ICON_MAP:
        if keyword in name:
            return icon
    return 'account_balance'


# /     /     >---- إرفاق الأيقونة والمجموعات لبيانات خطة القسم
def dept_plan_with_icon(data):
    """Attach an icon and totals to a department plan payload."""
    dept = dict(data.get('department') or {})
    semesters = data.get('semesters') or []
    dept['icon'] = _dept_icon(dept.get('name'))
    return {
        'department': dept,
        'semesters': semesters,
        'total_courses': sum(s['count'] for s in semesters),
        'total_units': sum(s['units'] for s in semesters),
    }


# /     /     >---- بناء خطة الدراسة لكل الأقسام الظاهرة
def build_dept_plans(db):
    """Build a per-department study-plan structure for all visible departments."""
    depts = db.execute(
        'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY id'
    ).fetchall()
    plans = []
    for d in depts:
        data = get_department_course_tables(db, d['id'])
        if data.get('department'):
            plans.append(dept_plan_with_icon(data))
    return plans


# /     /     >---- القائمة المسطحة للمقررات مع خيارات المتطلبات
def build_list_payload(db):
    """Flat course list for the management view + prerequisite lookup options.

    ``public_service`` helpers are imported inside the function to avoid a
    circular import chain (``public_service`` -> ``timetable_service``).
    """
    from services.public_service import get_approved_course_forms, get_course_syllabus_files

    rows = db.execute(
        'SELECT c.id, c.code, c.name, c.year, c.semester, '
        'c.theoretical_hours, c.practical_hours, c.total_hours, c.icon '
        'FROM courses c WHERE c.deleted_at IS NULL ORDER BY c.name'
    ).fetchall()
    courses = [dict(r) for r in rows]
    ids = [c['id'] for c in courses]

    dept_names = {}
    dept_ids = {}
    dept_semesters = {}
    if ids:
        ph = ','.join('?' * len(ids))
        for r in db.execute(
            'SELECT cd.course_id, d.name AS dept_name, d.id AS dept_id, '
            'cd.semester AS dept_semester '
            'FROM course_departments cd '
            'JOIN departments d ON cd.department_id = d.id '
            f'WHERE cd.course_id IN ({ph}) ORDER BY d.id',
            ids,
        ).fetchall():
            dept_names.setdefault(r['course_id'], []).append(r['dept_name'])
            dept_ids.setdefault(r['course_id'], []).append(r['dept_id'])
            dept_semesters.setdefault(r['course_id'], []).append({
                'dept_id': r['dept_id'],
                'dept_name': r['dept_name'],
                'semester': r['dept_semester'] or 1,
            })

    prereq_codes = {}
    if ids:
        ph = ','.join('?' * len(ids))
        for r in db.execute(
            'SELECT cp.course_id, c.code AS prereq_code '
            'FROM course_prerequisites cp '
            'JOIN courses c ON c.id = cp.prerequisite_id '
            f'WHERE cp.course_id IN ({ph})',
            ids,
        ).fetchall():
            prereq_codes.setdefault(r['course_id'], []).append(r['prereq_code'])

    prereq_options = [dict(r) for r in db.execute(
        'SELECT id, code, name FROM courses WHERE deleted_at IS NULL ORDER BY code'
    ).fetchall()]

    forms = get_approved_course_forms(db)
    syllabi_by_course = get_course_syllabus_files(db)

    attach_course_related_data(db, courses)

    year_to_semester = _YEAR_TO_SEMESTER
    titles = SEMESTER_TITLES

    flat = []
    for c in courses:
        theory = c.get('theoretical_hours') or 0
        practical = c.get('practical_hours') or 0
        total = c.get('total_hours') or (theory + practical)
        year = c.get('year')
        sem = c.get('semester') or (year_to_semester.get(year) if year else None)
        form = forms.get(c['id'])
        syllabi = syllabi_by_course.get(c['id'], [])
        flat.append({
            'id': c['id'],
            'code': c['code'],
            'name': c['name'],
            'icon': c['icon'] or '📖',
            'year': year,
            'semester': sem,
            'table_title': titles.get(sem, f'الفصل {sem}') if sem else '—',
            'units': total,
            'theory': theory,
            'practical': practical,
            'weekly_hours': total,
            'dept_names': dept_names.get(c['id'], []),
            'dept_ids': dept_ids.get(c['id'], []),
            'dept_semesters': dept_semesters.get(c['id'], []),
            'requires': prereq_codes.get(c['id'], []),
            'teachers': c.get('teachers', []),
            'form_status': c.get('form_status', ''),
            'form_teacher': c.get('form_teacher', ''),
            'form': {
                'id': form['id'],
                'originalFilename': form['original_filename'],
            } if form else None,
            'syllabus': {
                'id': syllabi[0]['id'],
                'teacherName': syllabi[0].get('teacher_name'),
            } if syllabi else None,
            'syllabusCount': len(syllabi),
        })
    status_meta = {
        k: {'label': v, 'class': SUBMISSION_STATUS_COLORS.get(k, '')}
        for k, v in SUBMISSION_STATUS_LABELS.items()
    }
    return {'courses': flat, 'prereqOptions': prereq_options, 'statusMeta': status_meta}