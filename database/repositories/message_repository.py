from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository

# /     /     >---- مستودع الرسائل والطلبات — المواضيع المرتبطة بالتواصل
class MessageRepository(BaseRepository):
    table = 'teacher_requests'

    # /     /     >---- نحدّث حالة الحضور في جدول الحضور
    def update_faculty_attendance(self, attendance_id: int, status: str) -> None:
        self.db.execute(
            'UPDATE faculty_attendance SET status=? WHERE id=?', (status, attendance_id)
        )
        self.db.commit()

    # /     /     >---- نضيف رد على رسالة
    def add_message_reply(self, message_id: int, sender_id: int, reply_text: str) -> None:
        self.db.execute(
            'INSERT INTO message_replies (message_id, sender_id, reply_text) VALUES (?, ?, ?)',
            (message_id, sender_id, reply_text),
        )
        self.db.commit()

    # /     /     >---- نعلّم رسالة كمحلولة
    def resolve_message(self, message_id: int, resolved_by: int) -> None:
        self.db.execute(
            "UPDATE teacher_messages SET status=?, resolved_at=CURRENT_TIMESTAMP, resolved_by=? WHERE id=?",
            ('resolved', resolved_by, message_id),
        )
        self.db.commit()

    # /     /     >---- نحدّث حالة طلب (بعد المراجعة من المدير)
    def update_request(self, request_id: int, status: str, reviewed_by: int,
                       admin_reply: str) -> None:
        self.db.execute(
            'UPDATE teacher_requests SET status=?, reviewed_by=?, '
            'reviewed_at=CURRENT_TIMESTAMP, admin_reply=? WHERE id=?',
            (status, reviewed_by, admin_reply, request_id),
        )
        self.db.commit()

    # /     /     >---- نجيب طلبات قسم معين مع اسم المدرس
    def list_requests_for_dept(self, department_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            '''SELECT r.*, t.name as teacher_name, u.username as sender_name
               FROM teacher_requests r
               LEFT JOIN teachers t ON r.teacher_id = t.id
               LEFT JOIN users u ON r.user_id = u.id
               WHERE r.department_id = ? OR r.department_id IS NULL
               ORDER BY r.created_at DESC''',
            (department_id,),
        ).fetchall()]

    # /     /     >---- نجيب طلبات المستخدم نفسه
    def list_user_requests(self, user_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            '''SELECT r.*, u.username as reviewer_name
               FROM teacher_requests r
               LEFT JOIN users u ON r.reviewed_by = u.id
               WHERE r.user_id = ?
               ORDER BY r.created_at DESC''',
            (user_id,),
        ).fetchall()]

    # /     /     >---- نصنع طلب جديد ونرجع معرّفه
    def create_request(self, teacher_id: int, user_id: int, department_id: int,
                       request_type: str, subject: str, message: str) -> int:
        self.db.execute(
            'INSERT INTO teacher_requests (teacher_id, user_id, department_id, '
            'request_type, subject, message) VALUES (?, ?, ?, ?, ?, ?)',
            (teacher_id, user_id, department_id, request_type or 'objection', subject, message),
        )
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    # /     /     >---- نجيب طلب واحد بالمعرف
    def find_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM teacher_requests WHERE id = ?', (request_id,)
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- ردّ رئيس القسم على طلب، مقيّداً بقسمه
    # /     /     >---- The single write path for an HOD reply. Scoped to
    # /     /     >---- *department_id* so one department head cannot read or
    # /     /     >---- resolve another department's request by guessing a
    # /     /     >---- sequential id. Returns the request row on success and
    # /     /     >---- ``None`` when no such request exists in that
    # /     /     >---- department, so the caller can answer 404 instead of
    # /     /     >---- silently reporting success.
    #
    # /     /     >---- ملاحظة: الجداول teacher_messages و message_replies
    # /     /     >---- قديمة ولم يعد يُكتب فيها شيء؛ كان الكود يستدعي
    # /     /     >---- add_message_reply و resolve_message على معرف من
    # /     /     >---- teacher_requests فيرمي خطأ مفتاح أجنبي ويفشل الرد كله.
    def reply_to_request(self, request_id: int, department_id: Optional[int],
                         admin_reply: str, reviewed_by: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT id, user_id, subject FROM teacher_requests '
            'WHERE id = ? AND (department_id = ? OR (? IS NULL AND department_id IS NULL))',
            (request_id, department_id, department_id),
        ).fetchone()
        if row is None:
            return None
        self.db.execute(
            'UPDATE teacher_requests SET status=?, reviewed_by=?, '
            'reviewed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP, '
            'admin_reply=? WHERE id = ?',
            ('resolved', reviewed_by, admin_reply, request_id),
        )
        self.db.commit()
        return dict(row)
