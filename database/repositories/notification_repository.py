from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository


class NotificationRepository(BaseRepository):
    table = 'notifications'

    def create(self, user_id: int, title: str, message: str,
               notif_type: str = 'info', related_type: str = '',
               related_id: int = 0) -> None:
        self.db.execute(
            'INSERT INTO notifications (user_id, title, message, type, related_type, related_id) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, title, message, notif_type, related_type, related_id or 0),
        )
        self.db.commit()

    def get_user_notifications(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit),
        ).fetchall()]

    def get_unread_count(self, user_id: int) -> int:
        row = self.db.execute(
            'SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0',
            (user_id,),
        ).fetchone()
        return row['cnt'] if row else 0

    def mark_all_read(self, user_id: int) -> None:
        self.db.execute(
            'UPDATE notifications SET is_read = 1 WHERE user_id = ?', (user_id,)
        )
        self.db.commit()

    def get_hod_user_ids(self, department_id: int = None) -> List[int]:
        query = (
            "SELECT u.id FROM users u JOIN teachers t ON t.user_id = u.id "
            "WHERE u.role = 'head_of_department'"
        )
        params: list = []
        if department_id:
            query += ' AND t.department_id = ?'
            params.append(department_id)
        return [r['id'] for r in self.db.execute(query, params).fetchall()]

    def get_admin_user_ids(self) -> List[int]:
        return [r['id'] for r in self.db.execute(
            "SELECT id FROM users WHERE role = 'super_admin'"
        ).fetchall()]

    def get_rnd_user_ids(self) -> List[int]:
        return [r['id'] for r in self.db.execute(
            "SELECT id FROM users WHERE role = 'research_development'"
        ).fetchall()]

    def get_exam_user_ids(self) -> List[int]:
        return [r['id'] for r in self.db.execute(
            "SELECT id FROM users WHERE role = 'exam'"
        ).fetchall()]

    def get_teacher_user_id(self, teacher_id: int) -> Optional[int]:
        row = self.db.execute(
            'SELECT user_id FROM teachers WHERE id = ?', (teacher_id,)
        ).fetchone()
        return row['user_id'] if row else None

    def get_all_teacher_user_ids(self, department_id: int = None) -> List[int]:
        query = "SELECT u.id FROM users u JOIN teachers t ON t.user_id = u.id WHERE u.role = 'teacher'"
        params: list = []
        if department_id:
            query += ' AND t.department_id = ?'
            params.append(department_id)
        return [r['id'] for r in self.db.execute(query, params).fetchall()]
