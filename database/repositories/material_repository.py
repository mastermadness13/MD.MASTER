from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository

# /     /     >---- مستودع المواد الدراسية (الملفات المرفوعة)
class MaterialRepository(BaseRepository):
    table = 'teacher_materials'

    # /     /     >---- نجيب مادة بالمعرف
    def find_by_id(self, material_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM teacher_materials WHERE id = ?', (material_id,)
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نجيب مادة بشرط أنها تابعة لقسم معين
    def find_for_dept(self, material_id: int, department_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM teacher_materials WHERE id = ? AND department_id = ?',
            (material_id, department_id),
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نجيب مادة ظاهرة للعامة (is_visible = 1)
    def find_visible(self, material_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT filename, original_filename FROM teacher_materials WHERE id = ? AND is_visible = 1',
            (material_id,),
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نزيد عداد التحميلات
    def increment_download(self, material_id: int) -> None:
        self.db.execute(
            'UPDATE teacher_materials SET download_count = download_count + 1 WHERE id = ?',
            (material_id,),
        )
        self.db.commit()

    # /     /     >---- نحذف المادة نهائياً
    def delete(self, material_id: int) -> None:
        self.db.execute('DELETE FROM teacher_materials WHERE id = ?', (material_id,))
        self.db.commit()

    # /     /     >---- نجيب مواد قسم معين مع اسم المدرس والترقيم
    def list_dept_materials(self, where_clause: str, params: list,
                            page: int = 1, per_page: int = 20) -> tuple:
        base = (
            'SELECT m.*, t.name as teacher_name FROM teacher_materials m '
            'JOIN teachers t ON m.teacher_id = t.id '
            f'WHERE {where_clause} ORDER BY m.created_at DESC'
        )
        return self.paginate(base, params, page, per_page)

    # /     /     >---- المدرسين اللي رفعوا مواد في قسم معين
    def list_dept_teachers(self, department_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT DISTINCT t.id, t.name FROM teacher_materials m '
            'JOIN teachers t ON m.teacher_id = t.id '
            'WHERE m.department_id = ? AND m.deleted_at IS NULL AND t.deleted_at IS NULL',
            (department_id,),
        ).fetchall()]

    # /     /     >---- المدرسين اللي عندهم مواد ظاهرة للعامة
    def list_visible_teachers(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT DISTINCT t.id, t.name FROM teacher_materials m '
            'JOIN teachers t ON m.teacher_id = t.id WHERE m.is_visible = 1 '
            'AND t.deleted_at IS NULL'
        ).fetchall()]

    # /     /     >---- نجيب وثائق قسم معين مع اسم المدرس
    def list_documents(self, department_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            '''SELECT d.*, t.name as teacher_name
               FROM teacher_documents d
               LEFT JOIN teachers t ON d.teacher_id = t.id
               WHERE t.department_id = ? OR ? IS NULL
               ORDER BY d.uploaded_at DESC''',
            (department_id, department_id),
        ).fetchall()]