"""Classroom change request service — workflow management.

Uses ``ClassroomRequestRepository`` for data access.  Module-level functions
are kept for backward compatibility with existing routes.

/     /     >---- خدمة طلبات تغيير القاعة: إدارة سير العمل (إنشاء، موافقة، رفض، إلغاء).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database.history import add_history

logger = logging.getLogger(__name__)


class ClassroomRequestService:
    """Class-based classroom request service with repository injection.

    /     /     >---- الخدمة بشكل كلاس مع حقن المستودع.
    """

    def __init__(self, db, classroom_request_repo):
        self.db = db
        self._repo = classroom_request_repo

    # /     /     >---- إنشاء طلب تغيير قاعة وتسجيله في سجل العمليات
    def create_request(self, teacher_id: int, user_id: int, department_id: int,
                       schedule_id: int, current_room_id: int,
                       requested_room_id: int, reason: str) -> int:
        request_id = self._repo.create({
            'teacher_id': teacher_id, 'user_id': user_id,
            'department_id': department_id, 'schedule_id': schedule_id,
            'current_classroom_id': current_room_id,
            'requested_classroom_id': requested_room_id, 'reason': reason,
        })
        add_history(
            self.db, 'create', 'classroom_change_request', request_id, user_id, None,
            'طلب تغيير قاعة', None,
            f'timetable={schedule_id} from_room={current_room_id} to_room={requested_room_id}',
        )
        return request_id

    def list_for_teacher(self, user_id: int) -> List[Dict]:
        return self._repo.list_for_teacher(user_id)

    def list_for_hod(self, department_id: int, status_filter: str = None) -> List[Dict]:
        return self._repo.list_for_hod(department_id, status_filter)

    def get_by_id(self, request_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(request_id)

    # /     /     >---- موافقة الراتب: نحدّث قاعة الجدول فعليةً للقاعة المطلوبة
    def approve_request(self, request_id: int, reviewed_by: int,
                        hod_comment: str = '') -> Optional[Dict]:
        self._repo.approve(request_id, reviewed_by, hod_comment)
        req = self._repo.find_by_id(request_id)
        if req:
            self._repo.update_timetable_room(req['schedule_id'], req['requested_classroom_id'])
        add_history(
            self.db, 'approve', 'classroom_change_request', request_id, reviewed_by, None,
            'تم الموافقة على طلب تغيير قاعة', None,
            f'timetable={req["schedule_id"]} new_room={req["requested_classroom_id"]}' if req else '',
        )
        return req

    # /     /     >---- رفض الطلب مع تعليق رئيس القسم
    def reject_request(self, request_id: int, reviewed_by: int,
                       hod_comment: str = '') -> None:
        self._repo.reject(request_id, reviewed_by, hod_comment)
        add_history(
            self.db, 'reject', 'classroom_change_request', request_id, reviewed_by, None,
            'تم رفض طلب تغيير قاعة', None, f'reason={hod_comment}',
        )

    # /     /     >---- إلغاء الطلب: للطالب نفسه فقط وحالة Pending فقط
    def cancel_request(self, request_id: int, user_id: int) -> bool:
        req = self._repo.find_simple(request_id)
        if not req or req['user_id'] != user_id:
            return False
        if req['status'] != 'Pending':
            return False
        self._repo.cancel(request_id)
        return True

    # /     /     >---- هل القاعة متاحة في نفس موعد الجدول
    def check_room_available(self, room_id: int, schedule_id: int) -> bool:
        return self._repo.check_room_available(room_id, schedule_id)

    def get_pending_count(self, department_id: int) -> int:
        return self._repo.get_pending_count(department_id)

    def get_recent_pending(self, department_id: int, limit: int = 5) -> List[Dict]:
        return self._repo.get_recent_pending(department_id, limit)

    def list_teacher_schedule(self, user_id: int) -> List[Dict]:
        return self._repo.list_teacher_schedule(user_id)

    def list_all_rooms(self) -> List[Dict]:
        return self._repo.list_all_rooms()


# /     /     >---- دوال مستوى الوحدة المحافظة على التوافق مع المسارات القديمة

def create_request(db, teacher_id, user_id, department_id, schedule_id, current_room_id, requested_room_id, reason):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    ClassroomRequestService(db, ClassroomRequestRepository(db)).create_request(
        teacher_id, user_id, department_id, schedule_id, current_room_id, requested_room_id, reason,
    )


def list_for_teacher(db, user_id):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).list_for_teacher(user_id)


def list_for_hod(db, department_id, status_filter=None):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).list_for_hod(department_id, status_filter)


def get_by_id(db, request_id):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).find_by_id(request_id)


def approve_request(db, request_id, reviewed_by, hod_comment=''):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestService(db, ClassroomRequestRepository(db)).approve_request(
        request_id, reviewed_by, hod_comment,
    )


def reject_request(db, request_id, reviewed_by, hod_comment=''):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    ClassroomRequestService(db, ClassroomRequestRepository(db)).reject_request(
        request_id, reviewed_by, hod_comment,
    )


def cancel_request(db, request_id, user_id):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestService(db, ClassroomRequestRepository(db)).cancel_request(
        request_id, user_id,
    )


def check_room_available(db, room_id, schedule_id):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).check_room_available(room_id, schedule_id)


def get_pending_count(db, department_id):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).get_pending_count(department_id)


def get_recent_pending(db, department_id, limit=5):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).get_recent_pending(department_id, limit)


def list_teacher_schedule(db, user_id):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).list_teacher_schedule(user_id)


def list_all_rooms(db):
    from database.repositories.classroom_request_repository import ClassroomRequestRepository
    return ClassroomRequestRepository(db).list_all_rooms()