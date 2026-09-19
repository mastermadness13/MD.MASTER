"""Timetable service — schedule data, CRUD, availability checks.

Uses ``TimetableRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.

/     /     >---- خدمة الجدول الدراسي: بيانات الجدول والإضافة والتعديل والحذف وفحص التوفر.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any, Dict, List, Optional

from utils.format import semester_code_next, semester_display_name

logger = logging.getLogger(__name__)

# /     /     >---- أيام الأسبوع بالعربي من السبت إلى الخميس
DAYS = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']

# Semester numbers for courses whose year is known but semester column is NULL.
# /     /     >---- رقم الفصل للمقرر اللي سنة الحديث معلومة لكن عمود الفصل فاضي
YEAR_TO_SEMESTER = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7}


# /     /     >---- الفصل الدراسي النشط حالياً (محسوب من تاريخ اليوم)
def current_active_semester(db) -> dict:
    """Return the currently active named semester, computed from today's date."""
    from datetime import date
    today = date.today()
    season = 'fall' if today.month >= 9 else 'spring'
    year = today.year if today.month >= 9 else today.year
    code = f'{season}_{year}'
    return {
        'id': None, 'code': code, 'season': season, 'year': year,
        'name_ar': f'{"خريف" if season == "fall" else "ربيع"} {year}',
        'name_en': f'{"Fall" if season == "fall" else "Spring"} {year}',
    }


# /     /     >---- كود الفصل الدراسي النشط حالياً
def current_semester_code(db) -> str:
    """Return the code of the currently active named semester."""
    sem = current_active_semester(db)
    return sem['code'] if sem else 'fall_2026'


# /     /     >---- الاسم العربي للفصل (من رمز الفصل مباشرة)
def semester_display_name_from_db(db, code: str) -> str:
    """Return the Arabic display name for a semester code."""
    if not code:
        return ''
    return semester_display_name(code)


# /     /     >---- الأسماء العربية لمجموعة أكواد
def semester_names_from_db(db, codes) -> Dict[str, str]:
    """Arabic display names for a collection of semester codes."""
    codes = [c for c in set(codes) if c]
    return {code: semester_display_name(code) for code in codes}


# /     /     >---- شرط SQL يكيّد على صفوف الجدول الحالية أو الموروثة فقط
def active_version_condition(alias: str = 't') -> str:
    """SQL fragment selecting only current/legacy timetable rows.

    Rows are "current" when they carry no version (legacy rows) or
    when their version is the active one. Other snapshots are excluded.

    /     /     >---- الصفوف الحالية هي اللي ما معاهاش نسخة (موروثة) أو نُسختها النشطة.
    """
    return (f"({alias}.version_id IS NULL OR {alias}.version_id IN "
            f"(SELECT id FROM timetable_versions WHERE status = 'active'))")


class TimetableService:
    """Class-based timetable service with repository injection.

    /     /     >---- الخدمة بشكل كلاس مع حقن مستودع الجدول.
    """

    def __init__(self, db, timetable_repo):
        self.db = db
        self._repo = timetable_repo
        self._sem_code_cache: Dict[tuple, str] = {}
        self.last_conflict_warnings: List[str] = []

    # /     /     >---- بيانات الجدول: المصادر والمقررات والأساتذة والقاعات والفلاتر
    def get_timetable_data(self, role: str, user_dept: int, selected_dept: int,
                           selected_semester: int,
                           selected_section: str = None) -> Dict[str, Any]:
        params: list = []
        selected_dept_name = None
        dept_semesters = 1
        has_sections = False

        effective_dept = selected_dept or user_dept

        # /     /     >---- معلومات القسم: عدد الفصول ووجود الأقسام الفرعية
        if effective_dept:
            row = self.db.execute(
                'SELECT name, semesters, has_sections FROM departments WHERE id=?',
                (effective_dept,),
            ).fetchone()
            if row:
                selected_dept_name = row['name']
                dept_semesters = row['semesters']
                has_sections = bool(row['has_sections'])

        available_semesters = list(range(2, min(dept_semesters, 8) + 1))
        if not available_semesters:
            available_semesters = [1]

        # /     /     >---- تثبيت الفصل إذا كان القسم بفصل وحدة
        semester_fixed = len(available_semesters) == 1
        if semester_fixed:
            selected_semester = available_semesters[0]
        else:
            if selected_semester not in available_semesters:
                selected_semester = available_semesters[0] if available_semesters else 2

        available_sections = []
        if effective_dept and has_sections:
            majors = self.db.execute(
                'SELECT name FROM department_majors WHERE department_id = ? ORDER BY name',
                (effective_dept,),
            ).fetchall()
            available_sections = [m['name'] for m in majors]

        # /     /     >---- تثبيت الشعبة إذا كان للقسم شعبة وحدة فقط
        section_fixed = len(available_sections) == 1
        if section_fixed:
            selected_section = available_sections[0]

        # /     /     >---- شروط التصفية: الفصل + القسم + الشعبة + النسخة النشطة
        conditions = ['t.semester = ?']
        params.append(selected_semester)
        if role in ('teacher', 'head_of_department') and user_dept:
            conditions.append('t.department_id = ?')
            params.append(user_dept)
        elif selected_dept:
            conditions.append('(t.department_id = ? OR t.department_id IS NULL)')
            params.append(selected_dept)
        if selected_section and has_sections:
            conditions.append('t.student_section = ?')
            params.append(selected_section)

        conditions.append(active_version_condition('t'))

        where_clause = ' AND '.join(conditions)
        entries = self._repo.query_entries(where_clause, params)

        departments = [dict(r) for r in self.db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]
        periods = self._repo.get_period_settings()
        courses = self._repo.list_all_courses()
        teachers = self._repo.list_all_teachers()
        rooms = self._repo.list_all_rooms()

        return {
            'entries': entries,
            'departments': departments,
            'periods': periods,
            'courses': courses,
            'teachers': teachers,
            'rooms': rooms,
            'selected_dept': selected_dept,
            'selected_dept_name': selected_dept_name,
            'selected_semester': selected_semester,
            'available_semesters': available_semesters,
            'semester_fixed': semester_fixed,
            'selected_section': selected_section,
            'has_sections': has_sections,
            'available_sections': available_sections,
            'section_fixed': section_fixed,
        }

    # /     /     >---- الفصول المتاحة للقسم حسب عدد سنوات الدراسة
    def available_semesters_for(self, dept: Dict[str, Any]) -> List[int]:
        total = dept.get('semesters') or 1
        if total <= 1:
            return [1]
        return list(range(2, min(total, 8) + 1))

    # /     /     >---- هل توجد نسخة جاهزة لهذا الفصل؟
    def _version_exists(self, dept_id: int, semester: int, semester_code: str) -> bool:
        row = self.db.execute(
            'SELECT 1 FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? AND semester_code = ?',
            (dept_id, semester, semester_code),
        ).fetchone()
        return row is not None

    # /     /     >---- التأكد من وجود نسخة وإلا إنشاؤها (تعامل مع سباق الكتابة)
    def _ensure_version(self, dept_id: int, semester: int, semester_code: str) -> int:
        row = self.db.execute(
            'SELECT id FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? AND semester_code = ?',
            (dept_id, semester, semester_code),
        ).fetchone()
        if row:
            return row['id']
        try:
            cur = self.db.execute(
                'INSERT INTO timetable_versions (department_id, semester, semester_code, status) '
                'VALUES (?, ?, ?, ?)',
                (dept_id, semester, semester_code, 'active'),
            )
            self.db.commit()
            return cur.lastrowid
        except Exception:
            row = self.db.execute(
                'SELECT id FROM timetable_versions '
                'WHERE department_id = ? AND semester = ? AND semester_code = ?',
                (dept_id, semester, semester_code),
            ).fetchone()
            if row:
                return row['id']
            raise

    # /     /     >---- كود الفصل للنسخة النشطة (الأحدث يفوز + حفظ ذاكر في الطلب نفسه)
    def _current_semester_code_for(self, dept_id: int, semester: int) -> str:
        """Named semester code of the active version for a department + semester.

        When several rows are marked active (legacy/duplicated data) the newest
        one wins so the UI always lands on the most recently created table.
        Results are memoized per service instance to avoid duplicate lookups
        within a single request (e.g. also called by ``ensure_current_version``).
        """
        key = (dept_id, semester)
        if key in self._sem_code_cache:
            return self._sem_code_cache[key]
        row = self.db.execute(
            'SELECT semester_code FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? AND status = \'active\' '
            'ORDER BY id DESC LIMIT 1',
            (dept_id, semester),
        ).fetchone()
        if row and row['semester_code']:
            code = row['semester_code']
            self._sem_code_cache[key] = code
            return code
        row = self.db.execute(
            'SELECT semester_code FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? '
            'AND semester_code IS NOT NULL AND semester_code != "" '
            'ORDER BY id DESC LIMIT 1',
            (dept_id, semester),
        ).fetchone()
        if row and row['semester_code']:
            code = row['semester_code']
            self._sem_code_cache[key] = code
            return code
        code = current_semester_code(self.db)
        self._sem_code_cache[key] = code
        return code

    # /     /     >---- ضمان نسخة نشطة للعرض: إرجاعها أو تفعيل/إنشاء واحدة
    def ensure_current_version(self, dept_id: int, semester: int) -> int:
        """Return the active version for a department+semester, creating or
        activating one so newly saved lectures are always visible.
        """
        sem_code = self._current_semester_code_for(dept_id, semester)
        dept = self.db.execute('SELECT id FROM departments WHERE id = ?', (dept_id,)).fetchone()
        if not dept:
            return None
        row = self.db.execute(
            'SELECT id, status FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? AND semester_code = ?',
            (dept_id, semester, sem_code),
        ).fetchone()
        if row:
            if row['status'] != 'active':
                self._activate_version(dept_id, semester, row['id'])
            return row['id']
        return self._ensure_version(dept_id, semester, sem_code)

    # /     /     >---- تفعيل نسخة معينة وتجاوز أي نسخة نشطة أخرى
    def _activate_version(self, dept_id: int, semester: int, version_id: int) -> None:
        """Make a version the active (editable) one; supersede others."""
        self.db.execute(
            "UPDATE timetable_versions SET status = 'superseded' "
            "WHERE department_id = ? AND semester = ? AND status = 'active' AND id != ?",
            (dept_id, semester, version_id),
        )
        self.db.execute(
            "UPDATE timetable_versions SET status = 'active' WHERE id = ?",
            (version_id,),
        )
        self.db.commit()

    # /     /     >---- إنشاء/إرجاع نسخة ونقل صفوف مصدر وتفعيل اختياري
    def ensure_version_for_semester(self, dept_id: int, semester: int,
                                    semester_code: str,
                                    source_version_id: int = None,
                                    activate: bool = True) -> int:
        """Create/return a version for the given semester, copying rows when a source is given."""
        new_version_id = self._ensure_version(dept_id, semester, semester_code)
        if source_version_id:
            self.db.execute(
                'INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, '
                'department_id, student_section, start_time, end_time, lecture_type, hours, version_id) '
                'SELECT day, semester, period, course_id, teacher_id, room_id, '
                'department_id, student_section, start_time, end_time, lecture_type, hours, ? '
                'FROM timetable WHERE version_id = ?',
                (new_version_id, source_version_id),
            )
            self.db.commit()

            # /     /     >---- تسجيل المواد المُدرَّسة للصفوف المنسوخة
            copied = self.db.execute(
                'SELECT id, day, course_id, teacher_id, department_id, semester, '
                '       start_time, end_time, period, room_id, student_section, '
                '       lecture_type, hours '
                'FROM timetable WHERE version_id = ? AND deleted_at IS NULL',
                (new_version_id,),
            ).fetchall()
            for row in copied:
                self._record_taught_course(
                    row['teacher_id'], row['course_id'], row['department_id'],
                    row['semester'], new_version_id,
                    day=row['day'], start_time=row['start_time'], end_time=row['end_time'],
                    period=row['period'], room_id=row['room_id'],
                    student_section=row['student_section'] or 'أ',
                    lecture_type=row['lecture_type'] or 'theory',
                    hours=row['hours'] or 0,
                    timetable_entry_id=row['id'],
                )

        if activate:
            self._activate_version(dept_id, semester, new_version_id)
        return new_version_id

    # /     /     >---- فتح أول فصل فارغ بعد الحالي كنسخة نشطة جديدة
    def create_version_for_next_semester(self, dept_id: int, semester: int,
                                         source_version_id: int = None) -> tuple:
        """Open the first empty semester after the current one as the new active version."""
        sem_code = self._current_semester_code_for(dept_id, semester)
        next_code = semester_code_next(sem_code)
        if not next_code or next_code == sem_code:
            # Legacy/migrated codes (e.g. "migrated_38_3") cannot be stepped;
            # start from the globally active semester instead.
            next_code = current_semester_code(self.db)
        safety = 0
        while self._version_exists(dept_id, semester, next_code) and safety < 10:
            next_code = semester_code_next(next_code)
            safety += 1
        version_id = self.ensure_version_for_semester(dept_id, semester, next_code, source_version_id)
        return version_id, next_code

    # /     /     >---- عرض جدول القسم: فئات فارغة + سجلات + إصدارات قديمة (قفل عند غير النشط)
    def get_department_view(self, dept_id: int, semester: int = None,
                            version_id: int = None) -> Dict[str, Any]:
        all_depts = [dict(r) for r in self.db.execute(
            'SELECT id, name, semesters FROM departments WHERE hidden=0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]

        def _empty_view():
            return {
                'departments': all_depts, 'dept': None, 'selected_semester': None,
                'available_semesters': [], 'periods': [], 'days': DAYS,
                'entries': [], 'courses': [], 'teachers': [], 'rooms': [],
                'teacherCourses': [], 'versions': [], 'semester_code': None,
                'semester_name_ar': None, 'viewing_semester_code': None,
                'viewing_semester_name': None, 'locked': True,
                'current_version_id': None, 'viewing_version_id': None,
            }

        if not dept_id:
            return _empty_view()

        dept = self.db.execute(
            'SELECT id, name, semesters FROM departments WHERE id = ?', (dept_id,)
        ).fetchone()
        if not dept:
            return _empty_view()
        dept = dict(dept)

        available_semesters = self.available_semesters_for(dept)
        if semester is None or semester not in available_semesters:
            semester = available_semesters[0] if available_semesters else 1

        current_code = self._current_semester_code_for(dept_id, semester)
        current_name = semester_display_name_from_db(self.db, current_code)
        current_version_id = self.ensure_current_version(dept_id, semester)
        academic = self._active_semester_row()
        academic_label = academic.get('name_ar') if academic else (current_name or current_code)

        # /     /     >---- عند اختيار نسخة قديمة: العرض للقراءة فقط ومقفول
        viewing_version_id = current_version_id
        viewing_code = current_code
        viewing_name = current_name
        locked = False
        if version_id is not None and version_id != current_version_id:
            vrow = self.db.execute(
                'SELECT id, semester_code, status FROM timetable_versions '
                'WHERE id = ? AND department_id = ? AND semester = ?',
                (version_id, dept_id, semester),
            ).fetchone()
            if vrow:
                viewing_version_id = vrow['id']
                viewing_code = vrow['semester_code']
                viewing_name = semester_display_name_from_db(self.db, viewing_code)
                locked = vrow['status'] != 'active'

        periods = self._repo.get_period_settings()
        entries = self._repo.get_department_view_data(
            dept_id, semester, viewing_version_id, include_legacy=not locked
        )

        # /     /     >---- قائمة النسخ السابقة المحفوظة مع عدد السجلات والاسم العربي
        versions = [dict(r) for r in self.db.execute(
            'SELECT v.id, v.semester_code, v.updated_at, '
            '(SELECT COUNT(*) FROM timetable t WHERE t.version_id = v.id) AS cnt '
            'FROM timetable_versions v '
            'WHERE v.department_id = ? AND v.semester = ? AND v.status != \'active\' '
            'ORDER BY v.id DESC',
            (dept_id, semester),
        ).fetchall()]
        name_map = semester_names_from_db(
            self.db, (v.get('semester_code', '') for v in versions)
        )
        for v in versions:
            v['semester_name_ar'] = name_map.get(v.get('semester_code', ''), '')
        versions = [v for v in versions if v['cnt'] > 0]

        # /     /     >---- تواريخ الفصل الأكاديمي والامتحانات للعرض
        sem_start_date, sem_end_date, ex_start, ex_end = '', '', '', ''
        if academic:
            sem_start_date = academic.get('start_date') or ''
            sem_end_date = academic.get('end_date') or ''
            ex_start = academic.get('exam_start_date') or ''
            ex_end = academic.get('exam_end_date') or ''

        return {
            'departments': all_depts,
            'dept': dept,
            'selected_semester': semester,
            'available_semesters': available_semesters,
            'periods': periods,
            'days': DAYS,
            'entries': entries,
            'courses': self._build_course_payload(),
            'teachers': self._repo.list_all_teachers(),
            'rooms': self._repo.list_all_rooms(),
            'teacherCourses': self._build_teacher_courses(),
            'versions': versions,
            'semester_code': current_code,
            'semester_name_ar': current_name,
            'viewing_semester_code': viewing_code,
            'viewing_semester_name': viewing_name,
            'locked': locked,
            'current_version_id': current_version_id,
            'viewing_version_id': viewing_version_id,
            'semester_start_date': sem_start_date,
            'semester_end_date': sem_end_date,
            'exam_start_date': ex_start,
            'exam_end_date': ex_end,
            'active_academic_semester': academic,
            'active_academic_label': academic_label,
        }

    # /     /     >---- معرف النسخة النشطة للقراءة فقط (ما ينشئ نسخة جديدة)
    def _active_version_id(self, dept_id: int, semester: int) -> Optional[int]:
        """Read-only lookup of the active version id (never creates one)."""
        row = self.db.execute(
            'SELECT id FROM timetable_versions '
            'WHERE department_id = ? AND semester = ? AND status = \'active\' LIMIT 1',
            (dept_id, semester),
        ).fetchone()
        return row['id'] if row else None

    # /     /     >---- صف الفصل النشط أكاديمياً (محسوب) مع حقول التواريخ
    def _active_semester_row(self) -> Optional[Dict[str, Any]]:
        """The computed active semester row, including default date fields."""
        from datetime import date
        today = date.today()
        season = 'fall' if today.month >= 9 else 'spring'
        year = today.year if today.month >= 9 else today.year
        code = f'{season}_{year}'
        name_ar = f'{"خريف" if season == "fall" else "ربيع"} {year}'
        name_en = f'{"Fall" if season == "fall" else "Spring"} {year}'
        if season == 'fall':
            start_date = f'{year}-09-01'
            end_date = f'{year + 1}-01-31'
            exam_start_date = f'{year + 1}-01-10'
            exam_end_date = f'{year + 1}-01-25'
        else:
            start_date = f'{year}-02-15'
            end_date = f'{year}-06-30'
            exam_start_date = f'{year}-06-01'
            exam_end_date = f'{year}-06-20'
        return {
            'id': None, 'code': code, 'season': season, 'year': year,
            'name_ar': name_ar, 'name_en': name_en, 'is_active': 1,
            'start_date': start_date, 'end_date': end_date,
            'exam_start_date': exam_start_date, 'exam_end_date': exam_end_date,
        }

    # /     /     >---- عرض موحّد للقراءة فقط لكل أقسام الجدول
    def get_combined_timetable_view(self, role: str, user_dept: int = None,
                                    selected_semester: int = None) -> Dict[str, Any]:
        """Combined read-only view of every department's timetable."""
        if user_dept:
            dept_rows = self.db.execute(
                'SELECT id, name, semesters FROM departments '
                'WHERE id = ? AND hidden = 0 AND deleted_at IS NULL',
                (user_dept,),
            ).fetchall()
        else:
            dept_rows = self.db.execute(
                'SELECT id, name, semesters FROM departments '
                'WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
            ).fetchall()

        sections = []
        for row in dept_rows:
            dept = dict(row)
            semesters = self.available_semesters_for(dept)
            semester = (selected_semester if selected_semester in semesters
                        else (semesters[0] if semesters else 1))

            active_version_id = self._active_version_id(dept['id'], semester)
            entries = self._repo.get_department_view_data(
                dept['id'], semester, active_version_id, include_legacy=bool(active_version_id)
            )
            sem_code = self._current_semester_code_for(dept['id'], semester)

            sections.append({
                'department': dept,
                'semester': semester,
                'available_semesters': semesters,
                'semester_code': sem_code,
                'semester_name_ar': semester_display_name_from_db(self.db, sem_code),
                'version_id': active_version_id,
                'entries': entries,
                'periods': self._repo.get_period_settings(),
            })

        return {
            'departments': sections,
            'days': DAYS,
            'selected_semester': selected_semester,
            'academic_label': (current_active_semester(self.db).get('name_ar')),
        }

    # /     /     >---- قائمة المقررات مع أقسامها وترتيبها (سنة أو فصل)
    def _build_course_payload(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            'SELECT c.id, c.code, c.name, c.year, c.semester, '
            'c.theoretical_hours, c.practical_hours, c.department_id '
            'FROM courses c WHERE c.deleted_at IS NULL ORDER BY c.name'
        ).fetchall()
        ids = [r['id'] for r in rows]
        dept_ids_map = {}
        dept_sem_map = {}
        if ids:
            ph = ','.join('?' * len(ids))
            for r in self.db.execute(
                'SELECT cd.course_id, d.id AS did, cd.semester '
                'FROM course_departments cd JOIN departments d ON cd.department_id = d.id '
                f'WHERE cd.course_id IN ({ph})',
                ids,
            ).fetchall():
                dept_ids_map.setdefault(r['course_id'], set()).add(r['did'])
                if r['semester']:
                    dept_sem_map.setdefault(r['course_id'], {})[r['did']] = r['semester']
        courses = []
        for r in rows:
            sem = r['semester']
            if not sem and r['year']:
                sem = YEAR_TO_SEMESTER.get(r['year'])
            dids = set(dept_ids_map.get(r['id'], set()))
            if r['department_id']:
                dids.add(r['department_id'])
            courses.append({
                'id': r['id'], 'code': r['code'], 'name': r['name'],
                'year': r['year'], 'semester': sem,
                'theory': r['theoretical_hours'] or 0,
                'practical': r['practical_hours'] or 0,
                'deptIds': sorted(dids),
                'deptSemesters': dept_sem_map.get(r['id'], {}),
            })
        return courses

    # /     /     >---- الأزواج (أستاذ، مقرر) للتحقق السريع في الواجهة
    def _build_teacher_courses(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            'SELECT t.teacher_id, c.code FROM timetable t '
            'JOIN courses c ON c.id = t.course_id '
            'WHERE c.deleted_at IS NULL AND t.deleted_at IS NULL '
            "AND (t.version_id IS NULL OR t.version_id IN "
            "(SELECT id FROM timetable_versions WHERE status = 'active'))"
        ).fetchall()
        seen = set()
        out = []
        for r in rows:
            key = (r['teacher_id'], r['code'])
            if key in seen:
                continue
            seen.add(key)
            out.append({'teacherId': r['teacher_id'], 'code': r['code']})
        return out

    # /     /     >---- بيانات نموذج إضافة حصة: قاعة/مقررات/أساتذة حسب القسم
    def get_create_form_data(self, dept_id: int, day: str, semester: int,
                             period_code: str, user_dept: int) -> tuple:
        dept_name = None
        if dept_id:
            row = self.db.execute(
                'SELECT name FROM departments WHERE id=?', (dept_id,)
            ).fetchone()
            if row:
                dept_name = row['name']
        courses_list = self._repo.list_all_courses()
        scope_dept = user_dept or dept_id
        if scope_dept:
            courses_list = self._repo.list_department_courses(scope_dept)
        return (
            dept_name,
            self._repo.get_period_settings(),
            courses_list,
            self._repo.list_all_teachers(),
            self._repo.list_all_rooms_with_code(),
        )

    # /     /     >---- حفظ سجل تدريس: أفضل جهد ولا يكسر حفظ الجدول أبداً
    def _record_taught_course(self, teacher_id, course_id, department_id,
                              semester, version_id=None,
                              day='', start_time='', end_time='', period='',
                              room_id=None, student_section='أ',
                              lecture_type='theory', hours=0,
                              timetable_entry_id=None):
        """Persist a teaching-assignment record.

        Best-effort: never breaks the timetable save that triggered it.
        Uses INSERT OR REPLACE so edits update the existing assignment.

        /     /     >---- INSERT OR REPLACE حتى التعديل يشتغل على نفس السجل.
        """
        try:
            if not teacher_id or not course_id:
                return
            code = ''
            if version_id:
                vrow = self.db.execute(
                    'SELECT semester_code FROM timetable_versions WHERE id = ?',
                    (version_id,),
                ).fetchone()
                if vrow and vrow['semester_code']:
                    code = vrow['semester_code']
            if not code:
                try:
                    code = self._current_semester_code_for(department_id or 0, semester) or ''
                except Exception:
                    logger.debug('Failed to resolve semester code for dept=%s sem=%s', department_id, semester)
                    code = ''
            # /     /     >---- حساب الساعات من وقت البداية/النهاية إذا فاضية
            if not hours and start_time and end_time:
                try:
                    s_parts = start_time.split(':')
                    e_parts = end_time.split(':')
                    minutes = (int(e_parts[0]) * 60 + int(e_parts[1])) - (int(s_parts[0]) * 60 + int(s_parts[1]))
                    hours = max(1, round(minutes / 60)) if minutes > 0 else 1
                except Exception:
                    hours = 1
            self.db.execute(
                'INSERT OR REPLACE INTO teacher_taught_courses '
                '(teacher_id, course_id, department_id, semester, semester_code, version_id, '
                ' day, start_time, end_time, period, room_id, student_section, '
                ' lecture_type, hours, timetable_entry_id) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (teacher_id, course_id, department_id, int(semester or 1), code,
                 version_id, day, start_time, end_time, period, room_id,
                 student_section, lecture_type, hours, timetable_entry_id),
            )
            self.db.commit()
        except Exception:
            logger.exception('Failed to record taught course (non-fatal)')

    # /     /     >---- ربط الأستاذ بالقسم تلقائياً عند الإسناد
    def _link_teacher_department(self, teacher_id, department_id) -> None:
        """Auto-link a department into a teacher's departments on assignment."""
        if not teacher_id or not department_id:
            return
        self.db.execute(
            'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
            'VALUES (?, ?)',
            (teacher_id, department_id),
        )

    # /     /     >---- تحذيرات تعارض (إرشادية فقط) لأستاذ/قاعة في نفس الفترة
    def _collect_conflict_warnings(self, day, semester, period_code, teacher_id,
                                   room_id, entry_id, start_time='', end_time='',
                                   hours=0) -> List[str]:
        """Advisory Arabic warnings for overlapping teacher/room bookings.

        Saving is never blocked; these are informational only. Adjacent slots
        (non-overlapping half-open times) must NOT warn.

        /     /     >---- الحفظ لازم ما يتحجبش، التنبيهات معلومة فقط والجوار يتم تجاهله.
        """
        warnings: List[str] = []
        conflict_rows = self._repo.get_conflicting_entries(
            'teacher', teacher_id, day, period_code, exclude_id=entry_id,
            start_time=start_time, end_time=end_time, hours=hours,
        )
        for row in conflict_rows:
            window = (row.get('start_time') and row.get('end_time')
                      and f"من {row['start_time']} إلى {row['end_time']}" or '')
            warnings.append(
                f"المحاضر {row['teacher_name']} لديه حصة متعارضة يوم {row['day']} "
                f"في {row['room_name'] or 'قاعة غير محددة'} {window}".strip()
            )
        conflict_rows = self._repo.get_conflicting_entries(
            'room', room_id, day, period_code, exclude_id=entry_id,
            start_time=start_time, end_time=end_time, hours=hours,
        )
        for row in conflict_rows:
            window = (row.get('start_time') and row.get('end_time')
                      and f"من {row['start_time']} إلى {row['end_time']}" or '')
            warnings.append(
                f"القاعة {row['room_name']} محجوزة في حصة متعارضة يوم {row['day']} "
                f"— {row['course_name'] or ''} {window}".strip()
            )
        seen = set()
        unique = []
        for w in warnings:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return unique

    # /     /     >---- إضافة حصة جديدة مع الربط والتسجيل والتحذيرات
    def create_entry(self, day, semester, period_code, course_id, teacher_id,
                     room_id, department_id, start_time='', end_time='',
                     version_id=None, lecture_type='theory', hours=0):
        """Insert a timetable entry, link teacher→department, record the taught
        course, and collect advisory conflict warnings."""
        entry_id = self._repo.create({
            'day': day, 'semester': semester, 'period': period_code,
            'course_id': course_id, 'teacher_id': teacher_id, 'room_id': room_id,
            'department_id': department_id, 'start_time': start_time,
            'end_time': end_time, 'lecture_type': lecture_type,
            'hours': hours, 'version_id': version_id,
        })
        self._link_teacher_department(teacher_id, department_id)
        self._record_taught_course(
            teacher_id, course_id, department_id, semester, version_id,
            day=day, start_time=start_time, end_time=end_time, period=period_code,
            room_id=room_id, student_section='أ',
            lecture_type=lecture_type, hours=hours, timetable_entry_id=entry_id,
        )
        self.last_conflict_warnings = self._collect_conflict_warnings(
            day, semester, period_code, teacher_id, room_id, entry_id,
            start_time, end_time, hours,
        )
        return entry_id

    # /     /     >---- تعديل حصة مع إعادة الربط والتسجيل والتحذيرات
    def update_entry(self, entry_id, day, semester, period_code, course_id,
                     teacher_id, room_id, start_time='', end_time='',
                     lecture_type='theory', hours=0):
        """Update a timetable entry, re-link teacher→department, re-record the
        taught course, and refresh advisory conflict warnings."""
        existing = self._repo.find_by_id(entry_id)
        if not existing:
            return False
        dept_id = existing.get('department_id')
        ok = self._repo.update(entry_id, {
            'day': day, 'semester': semester, 'period': period_code,
            'course_id': course_id, 'teacher_id': teacher_id, 'room_id': room_id,
            'start_time': start_time, 'end_time': end_time,
            'lecture_type': lecture_type, 'hours': hours,
        })
        self._link_teacher_department(teacher_id, dept_id)
        self._record_taught_course(
            teacher_id, course_id, dept_id, semester, existing.get('version_id'),
            day=day, start_time=start_time, end_time=end_time, period=period_code,
            room_id=room_id, student_section='أ',
            lecture_type=lecture_type, hours=hours, timetable_entry_id=entry_id,
        )
        self.last_conflict_warnings = self._collect_conflict_warnings(
            day, semester, period_code, teacher_id, room_id, entry_id,
            start_time, end_time, hours,
        )
        return ok

    def delete_entry(self, entry_id) -> bool:
        """Delete a timetable entry. Returns True if a row was removed."""
        return self._repo.delete(entry_id)

    def get_last_conflict_warnings(self) -> List[str]:
        """Return (and clear) this instance's advisory warnings."""
        warnings = list(self.last_conflict_warnings)
        self.last_conflict_warnings = []
        return warnings


# /     /     >---- دوال مستوى الوحدة للتوافق مع المسارات القديمة


def get_timetable_data(db, role, user_dept, selected_dept, selected_semester, selected_section=None):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    return svc.get_timetable_data(role, user_dept, selected_dept, selected_semester, selected_section)


def get_department_view(db, filter_dept_id, semester=None, version_id=None):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    return svc.get_department_view(filter_dept_id, semester, version_id)


def get_combined_timetable_view(db, role, user_dept=None, selected_semester=None):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    return svc.get_combined_timetable_view(role, user_dept, selected_semester)


def get_create_form_data(db, dept_id, day, semester, period_code, user_dept):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    return svc.get_create_form_data(dept_id, day, semester, period_code, user_dept)


# Conflict-warning storage is context-local so concurrent requests (threaded
# dev server / multiple workers) never read another request's warnings.
# /     /     >---- تخزين التحذيرات في سياق الطلب حتى الطلبات المتوازية ما تخلط بيناتها
_warnings_context: contextvars.ContextVar = contextvars.ContextVar(
    'timetable_conflict_warnings', default=[]
)


def get_last_conflict_warnings(db=None) -> List[str]:
    """Return (and clear) the advisory conflict warnings from the most recent
    create/update entry call (scoped to the current request/context)."""
    warnings = list(_warnings_context.get())
    _warnings_context.set([])
    return warnings


def create_entry(db, day, semester, period_code, course_id, teacher_id, room_id, department_id, start_time='', end_time='', version_id=None, lecture_type='theory', hours=0):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    entry_id = svc.create_entry(day, semester, period_code, course_id, teacher_id, room_id, department_id, start_time, end_time, version_id, lecture_type, hours)
    _warnings_context.set(list(svc.get_last_conflict_warnings()))
    return entry_id


def get_entry(db, entry_id):
    from database.repositories.timetable_repository import TimetableRepository
    return TimetableRepository(db).find_entry_detail(entry_id)


def verify_entry(db, entry_id):
    from database.repositories.timetable_repository import TimetableRepository
    return TimetableRepository(db).verify_exists(entry_id)


def update_entry(db, entry_id, day, semester, period_code, course_id, teacher_id, room_id, start_time='', end_time='', lecture_type='theory', hours=0):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    ok = svc.update_entry(entry_id, day, semester, period_code, course_id, teacher_id, room_id, start_time, end_time, lecture_type, hours)
    _warnings_context.set(list(svc.get_last_conflict_warnings()))
    return ok


def delete_entry(db, lecture_id):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    return svc.delete_entry(lecture_id)


def ensure_current_version(db, dept_id, semester):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    return svc.ensure_current_version(dept_id, semester)


def create_version_for_next_semester(db, dept_id, semester, source_version_id=None):
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    return svc.create_version_for_next_semester(dept_id, semester, source_version_id)


# Keep old name as alias for backward compatibility
# /     /     >---- الاسم القديم كاسم اختصاري للتوافق
create_version_for_next_year = create_version_for_next_semester


# /     /     >---- إنشاء نسخة لكود موسم/سنة صريح مع منع التكرار
def create_version_for_semester_code(db, dept_id, semester, semester_code,
                                     source_version_id=None):
    """Create a timetable version for an explicit season+year code.

    Returns ``(version_id, semester_code)`` on success, or ``(None, code)``
    when a version for the same code already exists for this department+
    semester — the caller must block the duplicate and ask for a different
    term/year.

    /     /     >---- إذا النسخة موجودة نرجع None والمتصل يمنع التكرار.
    """
    from database.repositories.timetable_repository import TimetableRepository
    svc = TimetableService(db, TimetableRepository(db))
    existing = db.execute(
        'SELECT id FROM timetable_versions '
        'WHERE department_id = ? AND semester = ? AND semester_code = ?',
        (dept_id, semester, semester_code),
    ).fetchone()
    if existing:
        return None, semester_code
    version_id = svc.ensure_version_for_semester(
        dept_id, semester, semester_code, source_version_id)
    return version_id, semester_code


def get_version(db, version_id):
    row = db.execute(
        'SELECT id, department_id, semester, semester_code, status, created_at, updated_at '
        'FROM timetable_versions WHERE id = ?',
        (version_id,),
    ).fetchone()
    return dict(row) if row else None


# /     /     >---- القاعات المتاحة في فترة معينة
def get_available_rooms(db, day, semester, period_code, exclude_id, start_time='', end_time='', hours=0):
    from database.repositories.timetable_repository import TimetableRepository
    return TimetableRepository(db).get_only_available_resources(
        'room', day, semester, period_code, exclude_id, start_time, end_time, hours
    )


# /     /     >---- الأساتذة المتاحين في فترة معينة
def get_available_teachers(db, day, semester, period_code, exclude_id, start_time='', end_time='', hours=0):
    from database.repositories.timetable_repository import TimetableRepository
    return TimetableRepository(db).get_only_available_resources(
        'teacher', day, semester, period_code, exclude_id, start_time, end_time, hours
    )


# /     /     >---- جدول أسبوعي لأستاذ معيّن: {اليوم: [الحصص]}
def build_teacher_weekly(db, teacher_id, days_order=None):
    """Build {day: [entries]} for a teacher's weekly schedule."""
    if days_order is None:
        days_order = DAYS
    weekly = {}
    for day in days_order:
        rows = db.execute(
            '''SELECT t.id, t.course_id, t.teacher_id, t.period, t.semester,
                      c.year, t.department_id,
                      c.name as course_name, c.code as course_code,
                      r.name as room_name, r.capacity as room_capacity,
                      t.start_time, t.end_time,
                      d.name as department_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms r ON t.room_id = r.id
               LEFT JOIN departments d ON t.department_id = d.id
               WHERE t.teacher_id = ? AND t.day = ?
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY t.start_time''',
            (teacher_id, day)
        ).fetchall()
        weekly[day] = [dict(r) for r in rows]
    return weekly