from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository

# /     /     >---- مستودع الإشعارات — كل العمليات على جدول notifications
class NotificationRepository(BaseRepository):
    table = 'notifications'

    # /     /     >---- نصنع إشعار جديد
    def create(self, user_id: int, title: str, message: str,
               notif_type: str = 'info', related_type: str = '',
               related_id: int = 0) -> None:
        self.db.execute(
            'INSERT INTO notifications (user_id, title, message, type, related_type, related_id) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, title, message, notif_type, related_type, related_id or 0),
        )
        self.db.commit()

    # /     /     >---- نجيب إشعارات مستخدم معين (الأحدث أولاً)
    def get_user_notifications(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit),
        ).fetchall()]

    # /     /     >---- عدد الإشعارات الغير مقروءة
    def get_unread_count(self, user_id: int) -> int:
        row = self.db.execute(
            'SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0',
            (user_id,),
        ).fetchone()
        return row['cnt'] if row else 0

    # /     /     >---- نعلّم كل الإشعارات كمقروءة
    def mark_all_read(self, user_id: int) -> None:
        self.db.execute(
            'UPDATE notifications SET is_read = 1 WHERE user_id = ?', (user_id,)
        )
        self.db.commit()

    # /     /     >---- معرفات رؤساء الأقسام (اختيارياً حسب القسم)
    # المسار الأساسي: أستاذ حاصل على القسم (teachers.hod_department_id).
    # المسار الاحتياطي: حساب head_of_department بدون ملف أستاذ (users.department_id).
    def get_hod_user_ids(self, department_id: int = None) -> List[int]:
        ids: List[int] = []
        if department_id is None:
            rows = self.db.execute(
                "SELECT u.id FROM users u JOIN teachers t ON t.user_id = u.id "
                "WHERE u.role = 'head_of_department' AND t.hod_department_id IS NOT NULL "
                "AND t.deleted_at IS NULL"
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT u.id FROM users u JOIN teachers t ON t.user_id = u.id "
                "WHERE u.role = 'head_of_department' AND t.hod_department_id = ? "
                "AND t.deleted_at IS NULL",
                (department_id,),
            ).fetchall()
        ids = [r['id'] for r in rows]
        existing = set(ids)

        if department_id is None:
            fallback = self.db.execute(
                "SELECT id FROM users WHERE role = 'head_of_department'"
            ).fetchall()
        else:
            fallback = self.db.execute(
                "SELECT id FROM users WHERE role = 'head_of_department' AND department_id = ?",
                (department_id,),
            ).fetchall()
        for row in fallback:
            if row['id'] not in existing:
                ids.append(row['id'])
                existing.add(row['id'])
        return ids

    # /     /     >---- معرفات مديري النظام
    def get_admin_user_ids(self) -> List[int]:
        return [r['id'] for r in self.db.execute(
            "SELECT id FROM users WHERE role = 'super_admin'"
        ).fetchall()]

    # /     /     >---- معرفات قسم البحث والتطوير
    def get_rnd_user_ids(self) -> List[int]:
        return [r['id'] for r in self.db.execute(
            "SELECT id FROM users WHERE role = 'research_development'"
        ).fetchall()]

    # /     /     >---- معرفات قسم الامتحانات
    def get_exam_user_ids(self) -> List[int]:
        return [r['id'] for r in self.db.execute(
            "SELECT id FROM users WHERE role = 'exam'"
        ).fetchall()]

    # /     /     >---- معرف المستخدم المرتبط بأستاذ معين
    def get_teacher_user_id(self, teacher_id: int) -> Optional[int]:
        row = self.db.execute(
            'SELECT user_id FROM teachers WHERE id = ?', (teacher_id,)
        ).fetchone()
        return row['user_id'] if row else None

    # /     /     >---- معرفات كل المدرسين (اختيارياً حسب القسم)
    def get_all_teacher_user_ids(self, department_id: int = None) -> List[int]:
        query = "SELECT u.id FROM users u JOIN teachers t ON t.user_id = u.id WHERE u.role = 'teacher'"
        params: list = []
        if department_id:
            query += ' AND t.department_id = ?'
            params.append(department_id)
        return [r['id'] for r in self.db.execute(query, params).fetchall()]