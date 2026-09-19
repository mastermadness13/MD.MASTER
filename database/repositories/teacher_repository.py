from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.constants.seasons import LEGACY_PERIOD_CODE
from database.repositories.base_repository import BaseRepository

# /     /     >---- مستودع أعضاء هيئة التدريس — كل العمليات على جدول teachers
class TeacherRepository(BaseRepository):
    table = 'teachers'

    # /     /     >---- نجيب أستاذ بالمعرف (مع اسم المستخدم)
    def find_by_id(self, teacher_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT t.*, u.username as username FROM teachers t LEFT JOIN users u ON t.user_id = u.id WHERE t.id = ?',
            (teacher_id,),
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نجيب أستاذ حسب معرف المستخدم (للوحة المدرس)
    def find_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT id, name, department_id FROM teachers WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- ندوّر على أساتذة بنفس الرقم الأكاديمي (للتأكد من التكرار)
    def find_by_academic_number(self, academic_number: str) -> List[Dict[str, Any]]:
        """Find teachers by exact academic_number match."""
        rows = self.db.execute(
            'SELECT id, name, user_id, email FROM teachers WHERE academic_number = ?',
            (academic_number,),
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- ندوّر على أساتذة بنفس الاسم المطبّع (تحذير فقط)
    def find_by_name_normalized(self, normalized_name: str) -> List[Dict[str, Any]]:
        """Find teachers whose normalized name matches.

        Returns candidates for warning — NOT proof of identity.
        """
        from utils.text import normalize_arabic_name

        rows = self.db.execute(
            'SELECT id, name, user_id, academic_number FROM teachers'
        ).fetchall()
        return [
            dict(r) for r in rows
            if normalize_arabic_name(r['name']) == normalized_name
        ]

    # /     /     >---- كل تفاصيل الأستاذ (القسم، التخصص، المؤهل، الرتبة، التصنيف)
    def find_detail(self, teacher_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT t.*, d.name as dept_name, hd.name as hod_dept_name, q.name_ar as qual_name,\n'
            '               r.name_ar as rank_name, c.name_ar as class_name,\n'
            '               s.name as specialization_name,\n'
            '               u.supervisor_admin_dept\n'
            '               FROM teachers t\n'
            '               LEFT JOIN departments d ON t.department_id = d.id\n'
            '               LEFT JOIN departments hd ON hd.id = t.hod_department_id\n'
            '               LEFT JOIN specializations s ON t.specialization_id = s.id\n'
            '               LEFT JOIN qualifications q ON t.qualification_id = q.id\n'
            '               LEFT JOIN academic_ranks r ON t.rank_id = r.id\n'
            '               LEFT JOIN classifications c ON t.classification_id = c.id\n'
            '               LEFT JOIN users u ON t.user_id = u.id\n'
            '               WHERE t.id = ?',
            (teacher_id,),
        ).fetchone()
        if not row:
            return None
        detail = dict(row)
        # /     /     >---- نزيد أسماء الأقسام المرتبطة بالأستاذ
        linked = self.db.execute(
            'SELECT d.name FROM teacher_departments td\n'
            '               JOIN departments d ON td.department_id = d.id\n'
            '               WHERE td.teacher_id = ? ORDER BY d.name',
            (teacher_id,),
        ).fetchall()
        detail['dept_names'] = [r['name'] for r in linked]
        return detail

    # /     /     >---- المقررات اللي يدرّسها الأستاذ حالياً في الجدول الفعّال
    def get_courses_for_teacher(self, teacher_id: int) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT c.* FROM courses c\n"
            "               INNER JOIN timetable tt ON tt.course_id = c.id\n"
            "               WHERE tt.teacher_id = ? AND c.deleted_at IS NULL\n"
            "               AND (tt.version_id IS NULL OR tt.version_id IN\n"
            "                   (SELECT id FROM timetable_versions WHERE status = 'active'))\n"
            "               GROUP BY c.id",
            (teacher_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- عدد الحصص في الجدول الفعّال للأستاذ
    def count_timetable_entries(self, teacher_id: int) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) AS cnt FROM timetable WHERE teacher_id = ? AND (version_id IS NULL OR version_id IN (SELECT id FROM timetable_versions WHERE status = 'active'))",
            (teacher_id,),
        ).fetchone()
        return row['cnt'] or 0

    # /     /     >---- نجيب الأساتذة مع الترقيم (حسب شروط البحث)
    def list_teachers(
        self,
        where_clause: str,
        params: Sequence,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple:
        base = (
            'SELECT t.*, d.name as dept_name, hd.name as hod_dept_name, u.username as username, '
            'u.supervisor_admin_dept FROM teachers t '
            'LEFT JOIN departments d ON t.department_id = d.id '
            'LEFT JOIN departments hd ON hd.id = t.hod_department_id '
            'LEFT JOIN users u ON t.user_id = u.id WHERE '
            f'{where_clause}'
        )
        return self.paginate(base, params, page, per_page)

    # /     /     >---- الأقسام المظهرة
    def list_visible_departments(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- كل القيم المساعدة لنماذج الإنشاء والتعديل
    def get_form_lookups(self) -> Dict[str, list]:
        # /     /     >---- الأقسام
        departments = self.db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()
        departments = [dict(r) for r in departments]

        # /     /     >---- المؤهلات العلمية
        qualifications = self.db.execute(
            'SELECT * FROM qualifications ORDER BY name_ar'
        ).fetchall()
        qualifications = [dict(r) for r in qualifications]

        # /     /     >---- الرتب الأكاديمية
        ranks = self.db.execute(
            'SELECT * FROM academic_ranks ORDER BY sort_order'
        ).fetchall()
        ranks = [dict(r) for r in ranks]

        # /     /     >---- التصنيفات
        classifications = self.db.execute(
            'SELECT * FROM classifications ORDER BY name_ar'
        ).fetchall()
        classifications = [dict(r) for r in classifications]

        # /     /     >---- المقررات
        courses = self.db.execute(
            'SELECT * FROM courses WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()
        courses = [dict(r) for r in courses]

        # /     /     >---- التخصصات المرتبطة بالأقسام
        specializations = self.db.execute(
            'SELECT s.id, s.department_id, s.name\n'
            '                   FROM specializations s\n'
            '                   JOIN departments d ON d.id = s.department_id\n'
            '                   WHERE d.deleted_at IS NULL\n'
            '                   ORDER BY s.department_id, s.sort_order'
        ).fetchall()
        specializations = [dict(r) for r in specializations]

        return {
            'departments': departments,
            'qualifications': qualifications,
            'ranks': ranks,
            'classifications': classifications,
            'courses': courses,
            'specializations': specializations,
        }

    # /     /     >---- نصنع أستاذ جديد ونرجع معرّفه
    def create(self, data: Dict[str, Any]) -> int:
        from utils.text import normalize_academic_number

        # /     /     >---- نطبّع الرقم الأكاديمي (نحذف الفراغات)
        an = normalize_academic_number(data.get('academic_number'))
        self.db.execute(
            'INSERT INTO teachers (name, email, phone, department_id, hod_department_id, academic_number,\n'
            '               qualification_id, rank_id, classification_id, national_id,\n'
            '               contract_date, tasks, position, specialization, specialization_id,\n'
            '               semester, first_lecture_date, work_start_date, general_notes)\n'
            '               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                data['name'],
                data['email'],
                data['phone'],
                data['department_id'],
                data.get('hod_department_id'),
                an,
                data['qualification_id'],
                data['rank_id'],
                data['classification_id'],
                data['national_id'],
                data['contract_date'],
                data['tasks'],
                data.get('position', ''),
                data.get('specialization', ''),
                data.get('specialization_id'),
                data.get('semester', ''),
                data.get('first_lecture_date', ''),
                data.get('work_start_date', ''),
                data.get('general_notes', ''),
            ),
        )
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    # /     /     >---- نحدّث بيانات أستاذ (حقول أساسية + اختيارية)
    def update(self, teacher_id: int, data: Dict[str, Any]) -> None:
        # /     /     >---- الحقول الأساسية الدائمة
        cols = [
            'name', 'email', 'phone', 'department_id', 'academic_number',
            'qualification_id', 'rank_id', 'classification_id', 'national_id',
            'contract_date', 'tasks',
        ]
        params = [data[c] for c in cols]
        # /     /     >---- الحقول الاختيارية (تضاف بس لو موجودة)
        for optional in [
            'specialization', 'specialization_id', 'position', 'photo_filename',
            'semester', 'first_lecture_date', 'work_start_date', 'general_notes',
            'hod_department_id',
        ]:
            if optional in data:
                cols.append(optional)
                params.append(data[optional])
        params.append(teacher_id)
        set_sql = ', '.join(f'{col}=?' for col in cols)
        self.db.execute(
            f'UPDATE teachers SET {set_sql} WHERE id=?',
            params,
        )
        self.db.commit()

    # /     /     >---- نربط الأستاذ بحساب مستخدم
    def link_user(self, teacher_id: int, user_id: int) -> None:
        self.db.execute(
            'UPDATE teachers SET user_id = ? WHERE id = ?',
            (user_id, teacher_id),
        )
        self.db.commit()

    # /     /     >---- السجل التدريسي التاريخي للأستاذ (بالسنوات والأقسام)
    def get_teaching_record(
        self,
        teacher_id: int,
        year_filter: str = '',
        semester_filter: int = None,
    ) -> List[Dict[str, Any]]:
        """Historical teaching record: teacher → semester_code → semester → department → course.

        Read from ``teacher_taught_courses`` (the historical ledger).
        """
        params = [teacher_id]
        where = 'ttc.teacher_id = ?'
        # /     /     >---- فلتر السنة (معاملة خاصة للبيانات المهاجرة)
        if year_filter == LEGACY_PERIOD_CODE:
            where += " AND semester_code LIKE 'migrated%'"
        elif year_filter:
            where += ' AND semester_code = ?'
            params.append(year_filter)
        # /     /     >---- فلتر الفصل الدراسي
        if semester_filter:
            where += ' AND ttc.semester = ?'
            params.append(semester_filter)
        rows = self.db.execute(
            '\n            SELECT semester_code,\n'
            '                   semester,\n'
            '                   department_id,\n'
            '                   (SELECT name FROM departments WHERE id = ttc.department_id) AS department_name,\n'
            '                   course_id,\n'
            '                   (SELECT code FROM courses WHERE id = ttc.course_id) AS course_code,\n'
            '                   (SELECT name FROM courses WHERE id = ttc.course_id) AS course_name,\n'
            '                   SUM(COALESCE(NULLIF(ttc.hours, 0), 0)) AS hours,\n'
            '                   COUNT(*) AS entry_count,\n'
            '                   SUM(CASE WHEN ttc.hours = 0 THEN 1 ELSE 0 END) AS missing_hours,\n'
            '                   MAX(COALESCE(ttc.lecture_type, \'\')) AS lecture_type\n'
            '            FROM teacher_taught_courses ttc\n'
            '            WHERE '
            f'{where}'
            '            GROUP BY semester_code, semester, department_id, course_id\n'
            '            ORDER BY semester_code DESC, semester ASC, department_name, course_name\n'
            '            ',
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- السنوات الدراسية اللي عندها سجل تدريسي للأستاذ
    def get_teaching_years(self, teacher_id: int) -> List[str]:
        rows = self.db.execute(
            '\n            SELECT DISTINCT semester_code\n'
            '            FROM teacher_taught_courses\n'
            '            WHERE teacher_id = ? AND semester_code != \'\'\n'
            '            ORDER BY semester_code DESC\n'
            '            ',
            (teacher_id,),
        ).fetchall()
        return [r['semester_code'] for r in rows]

    # /     /     >---- الفصول الدراسية المتوفرة في سجل الأستاذ
    def get_teaching_semesters(self, teacher_id: int) -> List[int]:
        rows = self.db.execute(
            '\n            SELECT DISTINCT semester\n'
            '            FROM teacher_taught_courses\n'
            '            WHERE teacher_id = ?\n'
            '            ORDER BY semester\n'
            '            ',
            (teacher_id,),
        ).fetchall()
        return [r['semester'] for r in rows]

    # /     /     >---- مجموع الساعات التدريسية للأستاذ
    def count_teaching_hours(self, teacher_id: int) -> int:
        row = self.db.execute(
            'SELECT SUM(COALESCE(hours, 0)) AS h FROM teacher_taught_courses WHERE teacher_id = ?',
            (teacher_id,),
        ).fetchone()
        return int(row['h'] or 0)

    # /     /     >---- المقررات في الجدول الفعّال للأستاذ
    def get_timetable_courses(self, teacher_id: int) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT course_id FROM timetable WHERE teacher_id = ? AND (version_id IS NULL OR version_id IN (SELECT id FROM timetable_versions WHERE status = 'active'))",
            (teacher_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- السجل التدريسي مفلتر بالسنة والفصل والقسم
    def get_teaching_record_filtered(
        self,
        teacher_id: int,
        semester: int,
        semester_code: str,
        department_id: int = None,
    ) -> List[Dict[str, Any]]:
        """Teaching record filtered by year level and period (optionally one department)."""
        params = [teacher_id, semester]
        extra = ''
        # /     /     >---- شروط رمز السنة (معاملة البيانات المهاجرة)
        if semester_code == LEGACY_PERIOD_CODE:
            code_clause = "semester_code LIKE 'migrated%'"
        else:
            code_clause = 'semester_code = ?'
            params.append(semester_code)
        # /     /     >---- فلتر اختياري بالقسم
        if department_id is not None:
            extra = ' AND ttc.department_id = ?'
            params.append(department_id)
        rows = self.db.execute(
            '\n            SELECT ttc.semester_code,\n'
            '                   ttc.semester,\n'
            '                   ttc.department_id,\n'
            '                   (SELECT name FROM departments WHERE id = ttc.department_id) AS department_name,\n'
            '                   ttc.course_id,\n'
            '                   (SELECT code FROM courses WHERE id = ttc.course_id) AS course_code,\n'
            '                   (SELECT name FROM courses WHERE id = ttc.course_id) AS course_name,\n'
            '                   COALESCE(NULLIF(ttc.hours, 0), 0) AS hours,\n'
            '                   ttc.day,\n'
            '                   ttc.start_time,\n'
            '                   ttc.end_time,\n'
            '                   ttc.lecture_type AS type,\n'
            '                   ttc.student_section AS group_number\n'
            '            FROM teacher_taught_courses ttc\n'
            '            WHERE ttc.teacher_id = ?\n'
            '              AND ttc.semester = ?\n'
            '              AND '
            f'{code_clause}'
            '              '
            f'{extra}'
            '\n            ORDER BY department_name, course_name\n'
            '            ',
            tuple(params),
        ).fetchall()
        return [dict(r) for r in rows]

    # /     /     >---- الاسم العربي لعرض رمز الفصل الدراسي
    def get_semester_display_name(self, semester_code: str) -> str:
        """Arabic display name for a semester_code (format-derived)."""
        if not semester_code:
            return ''
        from utils.format import semester_display_name
        return semester_display_name(semester_code)