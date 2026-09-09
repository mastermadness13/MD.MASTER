from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class TimetableRepository(BaseRepository):
    table = 'timetable'

    def find_by_id(self, entry_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM timetable WHERE id = ?', (entry_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_entry_detail(self, entry_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            '''SELECT t.*, c.name as course_name, c.code as course_code,
               tc.name as teacher_name, r.name as room_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN teachers tc ON t.teacher_id = tc.id
               LEFT JOIN rooms r ON t.room_id = r.id
               WHERE t.id=?''',
            (entry_id,),
        ).fetchone()
        return dict(row) if row else None

    def query_entries(self, where_clause: str, params: list) -> List[Dict[str, Any]]:
        base = (
            'SELECT t.*, c.name as course_name, c.code as course_code, '
            'tc.name as teacher_name, r.name as room_name, '
            't.start_time as start_time, t.end_time as end_time '
            'FROM timetable t '
            'LEFT JOIN courses c ON t.course_id = c.id '
            'LEFT JOIN teachers tc ON t.teacher_id = tc.id '
            'LEFT JOIN rooms r ON t.room_id = r.id '
            f'WHERE {where_clause} ORDER BY t.day, t.start_time'
        )
        return [dict(r) for r in self.db.execute(base, params).fetchall()]

    def query_entries_simple(self, where_clause: str, params: list) -> List[Dict[str, Any]]:
        base = (
            'SELECT t.*, c.name as course_name, c.code as course_code, '
            'tc.name as teacher_name, r.name as room_name '
            'FROM timetable t '
            'LEFT JOIN courses c ON t.course_id = c.id '
            'LEFT JOIN teachers tc ON t.teacher_id = tc.id '
            'LEFT JOIN rooms r ON t.room_id = r.id '
            f'WHERE {where_clause} ORDER BY t.day, t.start_time'
        )
        return [dict(r) for r in self.db.execute(base, params).fetchall()]

    def create(self, data: Dict[str, Any]) -> int:
        """Insert a new timetable entry. Returns the new row id."""
        cursor = self.db.execute(
            'INSERT INTO timetable (day, semester, period, course_id, teacher_id, '
            'room_id, department_id, start_time, end_time, lecture_type, hours, version_id) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (data['day'], data['semester'], data['period'],
             data['course_id'], data['teacher_id'], data['room_id'],
             data.get('department_id'), data.get('start_time', ''), data.get('end_time', ''),
             data.get('lecture_type', 'theory'), data.get('hours', 0),
             data.get('version_id')),
        )
        self.db.commit()
        row_id = cursor.lastrowid
        return row_id

    def verify_exists(self, entry_id: int) -> bool:
        """Verify a timetable entry exists in the database."""
        row = self.db.execute(
            'SELECT 1 FROM timetable WHERE id = ?', (entry_id,)
        ).fetchone()
        return row is not None

    def update(self, entry_id: int, data: Dict[str, Any]) -> bool:
        """Update an existing timetable entry. Returns True if row was updated."""
        cursor = self.db.execute(
            'UPDATE timetable SET day=?, semester=?, period=?, course_id=?, '
            'teacher_id=?, room_id=?, start_time=?, end_time=?, lecture_type=?, '
            'hours=? WHERE id=?',
            (data['day'], data['semester'], data['period'],
             data['course_id'], data['teacher_id'], data['room_id'],
             data.get('start_time', ''), data.get('end_time', ''),
             data.get('lecture_type', 'theory'), data.get('hours', 0), entry_id),
        )
        self.db.commit()
        return cursor.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        """Delete a timetable entry. Returns True if row was deleted."""
        cursor = self.db.execute('DELETE FROM timetable WHERE id=?', (entry_id,))
        self.db.commit()
        return cursor.rowcount > 0

    def is_room_conflicted(self, room_id: int, day: str, period_code: str,
                           exclude_id: int = None) -> bool:
        """Check if a room is already booked for the same day + period.

        This is the ONLY conflict check. No time-overlap logic.
        A room is unavailable if ANY current entry exists for the same day + period.
        """
        if exclude_id:
            row = self.db.execute(
                'SELECT 1 FROM timetable WHERE room_id = ? AND day = ? AND period = ? AND id != ? '
                'AND (version_id IS NULL OR version_id IN '
                '(SELECT id FROM timetable_versions WHERE status = \'active\')) LIMIT 1',
                (room_id, day, period_code, exclude_id)
            ).fetchone()
        else:
            row = self.db.execute(
                'SELECT 1 FROM timetable WHERE room_id = ? AND day = ? AND period = ? '
                'AND (version_id IS NULL OR version_id IN '
                '(SELECT id FROM timetable_versions WHERE status = \'active\')) LIMIT 1',
                (room_id, day, period_code)
            ).fetchone()
        return row is not None

    def is_room_available(self, room_id: int, day: str, period_code: str,
                          exclude_id: int = None) -> bool:
        """Check if a room is available (not conflicted)."""
        return not self.is_room_conflicted(room_id, day, period_code, exclude_id)

    def _enabled_period_index(self) -> Dict[str, int]:
        return {p['code']: i for i, p in enumerate(self.get_enabled_periods())}

    @staticmethod
    def _span_overlaps(a_start: int, a_hours: int, b_start: int, b_hours: int) -> bool:
        a_end = a_start + max(a_hours, 1) - 1
        b_end = b_start + max(b_hours, 1) - 1
        return a_start <= b_end and b_start <= a_end

    @staticmethod
    def _time_to_minutes(value) -> Optional[int]:
        """Parse an 'HH:MM' (or 'HH:MM:SS') wall-clock time into minutes.

        Returns ``None`` when the value is absent or unparseable so callers can
        fall back to period-span logic.
        """
        if not value:
            return None
        parts = str(value).split(':')
        if len(parts) < 2:
            return None
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _times_overlap(req_start, req_end, book_start, book_end) -> bool:
        """Half-open overlap test — an ending at 12:00 does NOT occupy 12:00.

        Returns False when any time is missing so callers can fall back.
        """
        rs = TimetableRepository._time_to_minutes(req_start)
        re = TimetableRepository._time_to_minutes(req_end)
        bs = TimetableRepository._time_to_minutes(book_start)
        be = TimetableRepository._time_to_minutes(book_end)
        if rs is None or re is None or bs is None or be is None:
            return False
        return rs < be and bs < re

    def get_available_resources(self, resource: str, day: str, semester: int,
                                period_code: str, exclude_id: int = None,
                                start_time: str = '', end_time: str = '',
                                hours: int = 0) -> List[Dict[str, Any]]:
        """Get rooms or teachers, marking availability for day + time overlap.

        Availability is determined by ACTUAL wall-clock time when both the
        requested slot and an existing booking carry start/end times
        (half-open overlap: an end equal to the next start does NOT overlap).
        Rooms/teachers are shared college-wide, so bookings from every
        department count.

        For rows without times (legacy data) falls back to the period-span
        logic: a booking occupies ``hours`` consecutive periods starting at its
        period code, and unknown period codes fall back to exact-period matching.
        """
        if resource == 'room':
            base_sql = ('SELECT id, name as name_ar, code FROM rooms '
                        'WHERE deleted_at IS NULL')
            fk_col = 'room_id'
        else:
            base_sql = 'SELECT id, name as name_ar FROM teachers WHERE deleted_at IS NULL'
            fk_col = 'teacher_id'
        resources = [dict(r) for r in self.db.execute(base_sql).fetchall()]

        bookings = self.db.execute(
            f'SELECT id, {fk_col} as fk, period, hours, start_time, end_time FROM timetable '
            'WHERE day = ? '
            'AND (version_id IS NULL OR version_id IN '
            '(SELECT id FROM timetable_versions WHERE status = \'active\'))',
            (day,),
        ).fetchall()

        order = self._enabled_period_index()
        req_idx = order.get(period_code)
        req_hours = max(int(hours or 1), 1)

        busy: Dict[Any, bool] = {}
        for b in bookings:
            if exclude_id and b['id'] == exclude_id:
                continue
            conflicted = False
            if start_time and end_time and b['start_time'] and b['end_time']:
                conflicted = self._times_overlap(
                    start_time, end_time, b['start_time'], b['end_time']
                )
            else:
                b_idx = order.get(b['period'])
                b_hours = max(int(b['hours'] or 1), 1)
                if req_idx is None or b_idx is None:
                    conflicted = (b['period'] == period_code)
                else:
                    conflicted = self._span_overlaps(
                        req_idx, req_hours, b_idx, b_hours
                    )
            if conflicted:
                busy[b['fk']] = True

        for res in resources:
            res['is_available'] = 0 if busy.get(res['id']) else 1
        return resources

    def get_only_available_resources(self, resource: str, day: str, semester: int,
                                     period_code: str, exclude_id: int = None,
                                     start_time: str = '', end_time: str = '',
                                     hours: int = 0) -> List[Dict[str, Any]]:
        """Return only available resources (conflicted ones removed entirely)."""
        all_resources = self.get_available_resources(
            resource, day, semester, period_code, exclude_id, start_time, end_time, hours
        )
        available = [r for r in all_resources if r.get('is_available', 0) == 1]
        return available

    def get_conflicting_entries(self, fk_col: str, fk_id: int, day: str,
                                period_code: str, exclude_id: int = None,
                                start_time: str = '', end_time: str = '',
                                hours: int = 0) -> List[Dict[str, Any]]:
        """Return active-timetable entries for a room/teacher that overlap the
        requested slot on the same day, joined with display names.

        Overlap is decided by actual wall-clock time (half-open) when both the
        requested slot and the entry carry times; legacy rows without times use
        the period-span rule. Used to build advisory warnings (not to block
        saving).
        """
        fk_col = 'room_id' if fk_col == 'room' else 'teacher_id'
        rows = self.db.execute(
            'SELECT t.id, t.day, t.period, t.hours, t.start_time, t.end_time, '
            't.department_id, t.semester, t.teacher_id, t.room_id, '
            'c.name as course_name, c.code as course_code, '
            'tc.name as teacher_name, r.name as room_name, '
            'd.name as department_name '
            'FROM timetable t '
            'LEFT JOIN courses c ON t.course_id = c.id '
            'LEFT JOIN teachers tc ON t.teacher_id = tc.id '
            'LEFT JOIN rooms r ON t.room_id = r.id '
            'LEFT JOIN departments d ON t.department_id = d.id '
            'WHERE t.day = ? '
            'AND (t.version_id IS NULL OR t.version_id IN '
            "(SELECT id FROM timetable_versions WHERE status = 'active'))",
            (day,),
        ).fetchall()
        order = self._enabled_period_index()
        req_idx = order.get(period_code)
        req_hours = max(int(hours or 1), 1)
        result: List[Dict[str, Any]] = []
        for b in rows:
            if exclude_id and b['id'] == exclude_id:
                continue
            if b[fk_col] != fk_id:
                continue
            if start_time and end_time and b['start_time'] and b['end_time']:
                conflicts = self._times_overlap(
                    start_time, end_time, b['start_time'], b['end_time']
                )
            else:
                b_idx = order.get(b['period'])
                b_hours = max(int(b['hours'] or 1), 1)
                if req_idx is None or b_idx is None:
                    conflicts = (b['period'] == period_code)
                else:
                    conflicts = self._span_overlaps(
                        req_idx, req_hours, b_idx, b_hours
                    )
            if conflicts:
                result.append(dict(b))
        return result

    def get_department_view_data(self, dept_id: int, semester: int = None,
                                 version_id: int = None,
                                 include_legacy: bool = False) -> List[Dict[str, Any]]:
        conditions = ['t.department_id = ?']
        params = [dept_id]
        if semester is not None:
            conditions.append('t.semester = ?')
            params.append(semester)
        if version_id is not None:
            if include_legacy:
                conditions.append('(t.version_id = ? OR t.version_id IS NULL)')
            else:
                conditions.append('t.version_id = ?')
            params.append(version_id)
        return self.query_entries_simple(' AND '.join(conditions), params)

    def get_period_settings(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM period_settings ORDER BY sort_order'
        ).fetchall()]

    def get_enabled_periods(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM period_settings WHERE is_enabled=1 ORDER BY sort_order'
        ).fetchall()]

    def list_all_courses(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name, code FROM courses WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    def list_department_courses(self, dept_id) -> List[Dict[str, Any]]:
        """Courses tied to a department, so the lecture form never offers the
        whole master course list.  A department sees a course when it is
        linked via ``course_departments``, linked as primary
        (``courses.department_id``) or already used in the department's active
        timetable (chosen during lecture determination)."""
        if not dept_id:
            return self.list_all_courses()
        return [dict(r) for r in self.db.execute(
            '''SELECT id, name, code FROM (
                   SELECT c.id, c.name, c.code FROM courses c
                   JOIN course_departments cd ON cd.course_id = c.id
                   WHERE cd.department_id = ? AND c.deleted_at IS NULL
                   UNION
                   SELECT c.id, c.name, c.code FROM courses c
                   WHERE c.department_id = ? AND c.deleted_at IS NULL
                   UNION
                   SELECT c.id, c.name, c.code FROM courses c
                   WHERE c.deleted_at IS NULL AND c.id IN (
                       SELECT t.course_id FROM timetable t
                       WHERE t.department_id = ? AND t.deleted_at IS NULL
                         AND (t.version_id IS NULL OR t.version_id IN
                             (SELECT id FROM timetable_versions WHERE status = 'active'))
                   )
               ) ORDER BY name''',
            (dept_id, dept_id, dept_id),
        ).fetchall()]

    def list_all_teachers(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name, department_id FROM teachers WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    def list_all_rooms(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name FROM rooms WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    def list_all_rooms_with_code(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name as name_ar, code FROM rooms WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    def find_teacher_for_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT t.teacher_id, c.name FROM timetable t '
            'LEFT JOIN courses c ON t.course_id = c.id WHERE t.id=?',
            (entry_id,),
        ).fetchone()
        return dict(row) if row else None
