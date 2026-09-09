"""Message service — faculty attendance, teacher messages, requests.

Uses ``MessageRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MessageService:
    """Class-based message service with repository injection."""

    def __init__(self, db, message_repo):
        self.db = db
        self._repo = message_repo

    def update_faculty_attendance(self, attendance_id: int, status: str) -> None:
        self._repo.update_faculty_attendance(attendance_id, status)

    def add_message_reply(self, message_id: int, sender_id: int, reply_text: str) -> None:
        self._repo.add_message_reply(message_id, sender_id, reply_text)

    def resolve_message(self, message_id: int, resolved_by: int) -> None:
        self._repo.resolve_message(message_id, resolved_by)

    def update_teacher_request(self, request_id: int, status: str,
                               reviewed_by: int, admin_reply: str) -> None:
        self._repo.update_request(request_id, status, reviewed_by, admin_reply)

    def list_teacher_requests(self, department_id: int) -> List[Dict]:
        return self._repo.list_requests_for_dept(department_id)

    def list_teacher_documents(self, department_id: int) -> List[Dict]:
        rows = self.db.execute(
            '''SELECT d.*, t.name as teacher_name
               FROM teacher_documents d
               LEFT JOIN teachers t ON d.teacher_id = t.id
               WHERE t.department_id = ? OR ? IS NULL
               ORDER BY d.uploaded_at DESC''',
            (department_id, department_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_teacher_by_user_id(self, user_id: int) -> Optional[Dict]:
        row = self.db.execute(
            'SELECT id, name FROM teachers WHERE user_id = ?', (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def create_teacher_request(self, teacher_id: int, user_id: int,
                               department_id: int, request_type: str,
                               subject: str, message: str) -> int:
        return self._repo.create_request(
            teacher_id, user_id, department_id, request_type, subject, message,
        )

    def list_user_requests(self, user_id: int) -> List[Dict]:
        return self._repo.list_user_requests(user_id)


# ── Backward-compatible module-level API ──────────────────────────────────

def update_faculty_attendance(db, id, status):
    from database.repositories.message_repository import MessageRepository
    MessageRepository(db).update_faculty_attendance(id, status)


def add_message_reply(db, message_id, sender_id, reply_text):
    from database.repositories.message_repository import MessageRepository
    MessageRepository(db).add_message_reply(message_id, sender_id, reply_text)


def resolve_message(db, message_id, resolved_by):
    from database.repositories.message_repository import MessageRepository
    MessageRepository(db).resolve_message(message_id, resolved_by)


def update_teacher_request(db, request_id, status, reviewed_by, admin_reply):
    from database.repositories.message_repository import MessageRepository
    MessageRepository(db).update_request(request_id, status, reviewed_by, admin_reply)


def list_teacher_requests(db, department_id):
    from database.repositories.message_repository import MessageRepository
    return MessageRepository(db).list_requests_for_dept(department_id)


def list_teacher_documents(db, department_id):
    rows = db.execute(
        '''SELECT d.*, t.name as teacher_name
           FROM teacher_documents d
           LEFT JOIN teachers t ON d.teacher_id = t.id
           WHERE t.department_id = ? OR ? IS NULL
           ORDER BY d.uploaded_at DESC''',
        (department_id, department_id),
    ).fetchall()
    return [dict(r) for r in rows]


def get_teacher_by_user_id(db, user_id):
    row = db.execute('SELECT id, name, department_id FROM teachers WHERE user_id = ?', (user_id,)).fetchone()
    return dict(row) if row else None


def create_teacher_request(db, teacher_id, user_id, department_id, request_type, subject, message):
    from database.repositories.message_repository import MessageRepository
    MessageRepository(db).create_request(
        teacher_id, user_id, department_id, request_type or 'objection', subject, message,
    )


def list_user_requests(db, user_id):
    from database.repositories.message_repository import MessageRepository
    return MessageRepository(db).list_user_requests(user_id)
