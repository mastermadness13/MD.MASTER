"""Notification service — creation, delivery, user lookups.

Uses ``NotificationRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotificationService:
    """Class-based notification service with repository injection."""

    def __init__(self, db, notification_repo):
        self.db = db
        self._repo = notification_repo

    def create_notification(self, user_id: int, title: str, message: str,
                            notif_type: str = 'info', related_type: str = '',
                            related_id: int = 0) -> None:
        if not user_id:
            return
        self._repo.create(user_id, title, message, notif_type, related_type, related_id)

    def notify_multiple(self, user_ids: list, title: str, message: str,
                        notif_type: str = 'info', related_type: str = '',
                        related_id: int = 0) -> None:
        for uid in user_ids:
            if uid:
                self.create_notification(uid, title, message, notif_type, related_type, related_id)

    def get_user_notifications(self, user_id: int, limit: int = 20) -> List[Dict]:
        return self._repo.get_user_notifications(user_id, limit)

    def get_unread_count(self, user_id: int) -> int:
        return self._repo.get_unread_count(user_id)

    def mark_all_read(self, user_id: int) -> None:
        self._repo.mark_all_read(user_id)

    def get_hod_user_ids(self, department_id: int = None) -> List[int]:
        return self._repo.get_hod_user_ids(department_id)

    def get_admin_user_ids(self) -> List[int]:
        return self._repo.get_admin_user_ids()

    def get_exam_user_ids(self) -> List[int]:
        return self._repo.get_exam_user_ids()

    def get_teacher_user_id(self, teacher_id: int) -> Optional[int]:
        return self._repo.get_teacher_user_id(teacher_id)

    def get_all_teacher_user_ids(self, department_id: int = None) -> List[int]:
        return self._repo.get_all_teacher_user_ids(department_id)


# ── Backward-compatible module-level API ──────────────────────────────────

def create_notification(db, user_id, title, message, notif_type='info',
                        related_type='', related_id=0):
    if not user_id:
        return
    db.execute(
        'INSERT INTO notifications (user_id, title, message, type, related_type, related_id) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (user_id, title, message, notif_type, related_type, related_id or 0),
    )
    db.commit()


def notify_multiple(db, user_ids, title, message, notif_type='info',
                    related_type='', related_id=0):
    for uid in user_ids:
        if uid:
            create_notification(db, uid, title, message, notif_type, related_type, related_id)


def get_user_notifications(db, user_id, limit=20):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_user_notifications(user_id, limit)


def get_unread_count(db, user_id):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_unread_count(user_id)


def mark_all_read(db, user_id):
    from database.repositories.notification_repository import NotificationRepository
    NotificationRepository(db).mark_all_read(user_id)


def get_hod_user_ids(db, department_id=None):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_hod_user_ids(department_id)


def get_admin_user_ids(db):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_admin_user_ids()


def get_exam_user_ids(db):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_exam_user_ids()


def get_rnd_user_ids(db):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_rnd_user_ids()


def get_teacher_user_id(db, teacher_id):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_teacher_user_id(teacher_id)


def get_all_teacher_user_ids(db, department_id=None):
    from database.repositories.notification_repository import NotificationRepository
    return NotificationRepository(db).get_all_teacher_user_ids(department_id)
