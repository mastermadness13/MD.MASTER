from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository


class ClassroomRequestRepository(BaseRepository):
    table = 'classroom_change_requests'

    def find_by_id(self, request_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            '''SELECT r.*, tc.name as teacher_name, c.name as course_name, t.day, t.period,
                      cr.name as current_room_name, rr.name as requested_room_name,
                      u.username as reviewer_name
               FROM classroom_change_requests r
               LEFT JOIN teachers tc ON r.teacher_id = tc.id
               LEFT JOIN timetable t ON r.schedule_id = t.id
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms cr ON r.current_classroom_id = cr.id
               LEFT JOIN rooms rr ON r.requested_classroom_id = rr.id
               LEFT JOIN users u ON r.reviewed_by = u.id
               WHERE r.id = ?''',
            (request_id,),
        ).fetchone()
        return dict(row) if row else None

    def find_simple(self, request_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT id, user_id, status, schedule_id, current_classroom_id, requested_classroom_id '
            'FROM classroom_change_requests WHERE id = ?',
            (request_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_for_teacher(self, user_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            '''SELECT r.*, c.name as course_name, t.day, t.period,
                      cr.name as current_room_name, rr.name as requested_room_name,
                      u.username as reviewer_name
               FROM classroom_change_requests r
               LEFT JOIN timetable t ON r.schedule_id = t.id
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms cr ON r.current_classroom_id = cr.id
               LEFT JOIN rooms rr ON r.requested_classroom_id = rr.id
               LEFT JOIN users u ON r.reviewed_by = u.id
               WHERE r.user_id = ?
               ORDER BY r.created_at DESC''',
            (user_id,),
        ).fetchall()]

    def list_for_hod(self, department_id: int, status_filter: str = None) -> List[Dict[str, Any]]:
        query = (
            'SELECT r.*, tc.name as teacher_name, c.name as course_name, t.day, t.period, '
            'cr.name as current_room_name, rr.name as requested_room_name '
            'FROM classroom_change_requests r '
            'LEFT JOIN teachers tc ON r.teacher_id = tc.id '
            'LEFT JOIN timetable t ON r.schedule_id = t.id '
            'LEFT JOIN courses c ON t.course_id = c.id '
            'LEFT JOIN rooms cr ON r.current_classroom_id = cr.id '
            'LEFT JOIN rooms rr ON r.requested_classroom_id = rr.id '
            'WHERE r.department_id = ?'
        )
        params: list = [department_id]
        if status_filter:
            query += ' AND r.status = ?'
            params.append(status_filter)
        query += ' ORDER BY r.created_at DESC'
        return [dict(r) for r in self.db.execute(query, params).fetchall()]

    def create(self, data: Dict[str, Any]) -> int:
        self.db.execute(
            'INSERT INTO classroom_change_requests '
            '(teacher_id, user_id, department_id, schedule_id, current_classroom_id, '
            'requested_classroom_id, reason) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (data['teacher_id'], data['user_id'], data['department_id'],
             data['schedule_id'], data['current_classroom_id'],
             data['requested_classroom_id'], data['reason']),
        )
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def approve(self, request_id: int, reviewed_by: int, hod_comment: str = '') -> None:
        self.db.execute(
            "UPDATE classroom_change_requests SET status='Approved', reviewed_by=?, "
            "reviewed_at=CURRENT_TIMESTAMP, hod_comment=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (reviewed_by, hod_comment, request_id),
        )
        self.db.commit()

    def reject(self, request_id: int, reviewed_by: int, hod_comment: str = '') -> None:
        self.db.execute(
            "UPDATE classroom_change_requests SET status='Rejected', reviewed_by=?, "
            "reviewed_at=CURRENT_TIMESTAMP, hod_comment=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (reviewed_by, hod_comment, request_id),
        )
        self.db.commit()

    def cancel(self, request_id: int) -> None:
        self.db.execute(
            "UPDATE classroom_change_requests SET status='Cancelled', "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,)
        )
        self.db.commit()

    def update_timetable_room(self, schedule_id: int, room_id: int) -> None:
        self.db.execute(
            'UPDATE timetable SET room_id=? WHERE id=?', (room_id, schedule_id)
        )
        self.db.commit()

    def check_room_available(self, room_id: int, schedule_id: int) -> bool:
        sched = self.db.execute(
            'SELECT day, start_time, end_time FROM timetable WHERE id=?', (schedule_id,)
        ).fetchone()
        if not sched:
            return False
        if sched['start_time'] and sched['end_time']:
            conflicts = self.db.execute(
                'SELECT 1 FROM timetable WHERE room_id=? AND id!=? AND day=? '
                'AND start_time < ? AND end_time > ? '
                'AND (version_id IS NULL OR version_id IN '
                '(SELECT id FROM timetable_versions WHERE status = \'active\')) LIMIT 1',
                (room_id, schedule_id, sched['day'], sched['end_time'], sched['start_time']),
            ).fetchone()
        else:
            conflicts = self.db.execute(
                'SELECT 1 FROM timetable WHERE room_id=? AND id!=? AND day=? AND period=? '
                'AND (version_id IS NULL OR version_id IN '
                '(SELECT id FROM timetable_versions WHERE status = \'active\')) LIMIT 1',
                (room_id, schedule_id, sched['day'], ''),
            ).fetchone()
        return conflicts is None

    def get_pending_count(self, department_id: int) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) as cnt FROM classroom_change_requests "
            "WHERE department_id=? AND status='Pending'",
            (department_id,),
        ).fetchone()
        return row['cnt'] if row else 0

    def get_recent_pending(self, department_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            '''SELECT r.*, tc.name as teacher_name, c.name as course_name
               FROM classroom_change_requests r
               LEFT JOIN teachers tc ON r.teacher_id = tc.id
               LEFT JOIN timetable t ON r.schedule_id = t.id
               LEFT JOIN courses c ON t.course_id = c.id
               WHERE r.department_id=? AND r.status='Pending'
               ORDER BY r.created_at DESC LIMIT ?''',
            (department_id, limit),
        ).fetchall()]

    def find_schedule_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT id, room_id FROM timetable WHERE id=?', (entry_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_teacher_schedule(self, user_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            '''SELECT t.id, t.day, t.period, t.semester,
                      c.name as course_name, r.name as room_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms r ON t.room_id = r.id
               LEFT JOIN teachers tc ON t.teacher_id = tc.id
               WHERE tc.user_id = ? AND t.deleted_at IS NULL
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY t.day, t.period''',
            (user_id,),
        ).fetchall()]

    def list_all_rooms(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name, type, capacity FROM rooms WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]
