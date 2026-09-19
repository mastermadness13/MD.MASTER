from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository

# /     /     >---- مستودع الامتحانات — كل العمليات على جدول exam_schedule
class ExamRepository(BaseRepository):
    table = 'exam_schedule'

    # /     /     >---- نجيب امتحان بالمعرف
    def find_by_id(self, exam_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM exam_schedule WHERE id = ?', (exam_id,)
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نجيب امتحان مع اسم القسم والمقرر
    def find_with_details(self, exam_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            '''SELECT es.*, d.name as dept_name, c.name as course_name
               FROM exam_schedule es
               LEFT JOIN departments d ON es.department_id = d.id
               LEFT JOIN courses c ON es.course_id = c.id
               WHERE es.id = ?''',
            (exam_id,),
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- امتحانات قسم معين مرتبة حسب التاريخ والوقت
    def list_by_department(self, dept_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            '''SELECT es.*, c.name as course_name, c.code as course_code
               FROM exam_schedule es
               LEFT JOIN courses c ON es.course_id = c.id
               WHERE es.department_id = ?
               ORDER BY es.exam_date, es.start_time''',
            (dept_id,),
        ).fetchall()]

    # /     /     >---- الأقسام الظاهرة اللي عندها امتحانات
    def list_visible_departments(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name, semesters FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    # /     /     >---- نجيب قسم بالمعرف (المظاهر فقط)
    def find_department(self, dept_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT id, name, semesters FROM departments WHERE id = ? AND hidden = 0 AND deleted_at IS NULL',
            (dept_id,),
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نخصص قاعة لامتحان
    def update_room(self, schedule_id: int, room_id: int) -> None:
        self.db.execute(
            'UPDATE exam_schedule SET room_id = ? WHERE id = ?', (room_id, schedule_id)
        )
        self.db.commit()

    # /     /     >---- نجيب إعدادات الامتحانات
    def get_settings(self) -> Optional[Dict[str, Any]]:
        row = self.db.execute('SELECT * FROM exam_settings LIMIT 1').fetchone()
        return dict(row) if row else None

    # /     /     >---- نحفظ الإعدادات (تحديث أو إدخال جديد)
    def save_settings(self, data: Dict[str, Any]) -> None:
        existing = self.db.execute('SELECT id FROM exam_settings LIMIT 1').fetchone()
        if existing:
            # /     /     >---- إذا موجودة نحدثها
            set_clause = ', '.join(f'{k} = ?' for k in data.keys())
            self.db.execute(
                f'UPDATE exam_settings SET {set_clause} WHERE id = ?',
                list(data.values()) + [existing['id']],
            )
        else:
            # /     /     >---- إذا لأ نعمل إدخال جديد
            cols = ', '.join(data.keys())
            ph = ', '.join(['?'] * len(data))
            self.db.execute(
                f'INSERT INTO exam_settings ({cols}) VALUES ({ph})',
                list(data.values()),
            )
        self.db.commit()

    # /     /     >---- القاعات المتاحة (غير المحذوفة)
    def get_active_rooms(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name, capacity FROM rooms WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    # /     /     >---- مقررات قسم معين (للامتحانات) مع فلتر اختياري بالسنوات
    def get_department_courses(self, dept_id: int, semester: int = None) -> List[Dict[str, Any]]:
        query = '''SELECT DISTINCT c.id, c.name, c.code, c.year, c.practical_hours FROM courses c
               LEFT JOIN course_departments cd ON c.id = cd.course_id
               WHERE (cd.department_id = ? OR c.department_id = ?) AND c.deleted_at IS NULL'''
        params: list = [dept_id, dept_id]
        if semester is not None:
            # /     /     >---- السنة الدراسية = الفصل - 1
            course_year = semester - 1
            query += ' AND c.year = ?'
            params.append(course_year)
        query += ' ORDER BY c.name'
        return [dict(r) for r in self.db.execute(query, params).fetchall()]