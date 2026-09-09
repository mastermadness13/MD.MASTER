# -*- coding: utf-8 -*-
"""Tests for timetable conflict advisory warnings + auto teacher-department link.

Covers the change where teacher/room scheduling overlaps no longer BLOCK saving;
instead the entry is saved and an advisory warning (with details) is produced.
Also verifies that assigning a teacher to a department auto-links the department
into the teacher's ``teacher_departments`` data (create + edit).
"""

import sqlite3

import pytest

from database.connection import connect
from database.repositories.timetable_repository import TimetableRepository
from database.schema import ensure_schema
from services import timetable_service


@pytest.fixture
def svc_fx(tmp_path):
    db_path = tmp_path / 'tt_conflict.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('superadmin', 'x', 'super_admin', 'مدير')"
    )
    dept_id = conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    ).lastrowid

    teacher1 = conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('مدرس الأول', ?)", (dept_id,)
    ).lastrowid
    teacher2 = conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('مدرس الثاني', ?)", (dept_id,)
    ).lastrowid

    room1 = conn.execute("INSERT INTO rooms (name) VALUES ('قاعة 101')").lastrowid
    room2 = conn.execute("INSERT INTO rooms (name) VALUES ('قاعة 102')").lastrowid

    course_id = conn.execute(
        "INSERT INTO courses (code, name, year, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('CS101', 'مقرر اختبار', 1, 2, 0, 2)"
    ).lastrowid

    version_id = conn.execute(
        "INSERT INTO timetable_versions (department_id, semester, semester_code, status) "
        "VALUES (?, 1, 'fall_2026', 'active')",
        (dept_id,),
    ).lastrowid

    conn.commit()
    repo = TimetableRepository(conn)
    svc = timetable_service.TimetableService(conn, repo)
    yield {
        'db': conn, 'svc': svc,
        'dept_id': dept_id, 'teacher1': teacher1, 'teacher2': teacher2,
        'room1': room1, 'room2': room2, 'course_id': course_id, 'version_id': version_id,
    }
    conn.close()


def _entry(svc_fx, teacher, room, day='الأحد', period='A', course=None,
           start='08:00', end='09:00'):
    f = svc_fx
    return timetable_service.create_entry(
        f['db'], day, 1, period, course or f['course_id'], teacher, room,
        f['dept_id'], start_time=start, end_time=end,
        version_id=f['version_id'], lecture_type='theory', hours=1,
    )


def test_teacher_same_period_second_entry_allowed_with_warning(svc_fx):
    """نفس المحاضر في حصة ثانية بنفس الفترة: تُحفظ وتظهر رسالة تحذير."""
    f = svc_fx
    first = _entry(f, f['teacher1'], f['room1'], period='A')
    assert first

    second = _entry(f, f['teacher1'], f['room2'], period='A')
    assert second, 'teacher double-booking must NOT be blocked'

    warnings = timetable_service.get_last_conflict_warnings()
    assert any('المحاضر' in w and 'قاعة 101' in w for w in warnings), warnings


def test_room_same_period_second_entry_allowed_with_warning(svc_fx):
    """نفس القاعة في حصة ثانية بنفس الفترة: تُحفظ وتظهر رسالة تحذير (لا منع)."""
    f = svc_fx
    first = _entry(f, f['teacher1'], f['room1'], period='A')
    assert first

    second = _entry(f, f['teacher2'], f['room1'], period='A')
    assert second, 'room double-booking must NOT be blocked'

    warnings = timetable_service.get_last_conflict_warnings()
    assert any('القاعة' in w and 'قاعة 101' in w for w in warnings), warnings


def test_no_warning_when_no_overlap(svc_fx):
    """حصة بلا تعارض لا تُنتج أي تحذير."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='A')
    _entry(f, f['teacher2'], f['room2'], period='B')
    warnings = timetable_service.get_last_conflict_warnings()
    assert warnings == []


def test_create_links_teacher_to_department(svc_fx):
    """عند تعيين محاضر في قسم خلال إنشاء حصة، يُضاف القسم إلى بياناته."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='A')
    row = f['db'].execute(
        'SELECT 1 FROM teacher_departments WHERE teacher_id=? AND department_id=?',
        (f['teacher1'], f['dept_id']),
    ).fetchone()
    assert row, 'teacher_departments link must be created on entry create'


def test_update_links_teacher_to_department(svc_fx):
    """عند تعديل حصة وتعيين محاضر/قسم، يُضاف القسم إلى بيانات المحاضر."""
    f = svc_fx
    entry_id = _entry(f, f['teacher1'], f['room1'], period='A')
    ok = timetable_service.update_entry(
        f['db'], entry_id, 'الأحد', 1, 'B', f['course_id'], f['teacher2'], f['room2'],
        start_time='09:00', end_time='10:00', lecture_type='theory', hours=1,
    )
    assert ok
    row = f['db'].execute(
        'SELECT 1 FROM teacher_departments WHERE teacher_id=? AND department_id=?',
        (f['teacher2'], f['dept_id']),
    ).fetchone()
    assert row, 'teacher_departments link must exist after edit'


def _available_teacher_ids(svc_fx, period, start, end):
    f = svc_fx
    repo = TimetableRepository(f['db'])
    teachers = repo.get_only_available_resources(
        'teacher', 'الأحد', 1, period, start_time=start, end_time=end
    )
    return [t['id'] for t in teachers]


def test_teacher_available_when_request_starts_at_booking_end(svc_fx):
    """الأستاذة: 09:00→12:00 ثم طلب 12:00→13:00 ⇒ متاحة (نهاية حصرية)."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='A', start='09:00', end='12:00')
    ids = _available_teacher_ids(svc_fx, 'B', '12:00', '13:00')
    assert f['teacher1'] in ids, 'teacher must be selectable the instant the booking ends'


def test_teacher_hidden_when_times_overlap(svc_fx):
    """الأستاذة: 09:00→12:00 ثم طلب 11:00→12:00 ⇒ مخفية."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='A', start='09:00', end='12:00')
    ids = _available_teacher_ids(svc_fx, 'A', '11:00', '12:00')
    assert f['teacher1'] not in ids, 'overlapping request must hide the teacher'


def test_teacher_availability_is_cross_department(svc_fx):
    """الأستاذة محجوبة عالمياً بالتداخل الزمني، لا بمفاهيم الأقسام."""
    f = svc_fx
    dept_b = f['db'].execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم المدني', 8, 8, 0, 1, 'academic')"
    ).lastrowid
    _entry(f, f['teacher1'], f['room1'], period='A', start='09:00', end='12:00')
    second = timetable_service.create_entry(
        f['db'], 'الأحد', 1, 'B', f['course_id'], f['teacher1'], f['room2'],
        dept_b, start_time='12:00', end_time='13:00',
        version_id=f['version_id'], lecture_type='theory', hours=1,
    )
    assert second, 'same teacher may teach adjacent slot right after 09:00→12:00'


def _available_room_ids(svc_fx, period, start, end):
    f = svc_fx
    repo = TimetableRepository(f['db'])
    rooms = repo.get_only_available_resources(
        'room', 'الأحد', 1, period, start_time=start, end_time=end
    )
    return [r['id'] for r in rooms]


def test_room_available_when_request_starts_at_booking_end(svc_fx):
    """09:00→12:00 ثم طلب 12:00→13:00 ⇒ القاعة متاحة (نهاية حصرية)."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='A', start='09:00', end='12:00')
    assert f['room1'] in _available_room_ids(svc_fx, 'B', '12:00', '13:00'), \
        'room must be selectable the instant the previous booking ends'


def test_room_hidden_when_times_overlap(svc_fx):
    """09:00→12:00 ثم 11:00→12:00 ⇒ القاعة محجوبة. 09:00→12:00 ثم 12:00→13:00 متاحة."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='A', start='09:00', end='12:00')
    assert f['room1'] not in _available_room_ids(svc_fx, 'A', '11:00', '12:00'), \
        'overlapping request must hide the room'


def test_room_available_across_departments_at_adjacent_slot(svc_fx):
    """قسم A يحجز 09:00→12:00 ثم قسم B يستطيع الحجز 12:00→13:00 مباشرة."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='A', start='09:00', end='12:00')

    dept_b = f['db'].execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم المدني', 8, 8, 0, 1, 'academic')"
    ).lastrowid
    second = timetable_service.create_entry(
        f['db'], 'الأحد', 1, 'B', f['course_id'], f['teacher2'], f['room1'],
        dept_b, start_time='12:00', end_time='13:00',
        version_id=f['version_id'], lecture_type='theory', hours=1,
    )
    assert second, 'adjacent booking from another department must be allowed'
    warnings = timetable_service.get_last_conflict_warnings()
    assert not any('القاعة' in w and 'قاعة 101' in w for w in warnings), warnings


def test_room_available_for_chained_adjacent_slots(svc_fx):
    """12:00→13:00 ثم طلب 13:00→15:00 ⇒ القاعة متاحة."""
    f = svc_fx
    _entry(f, f['teacher1'], f['room1'], period='B', start='12:00', end='13:00')
    assert f['room1'] in _available_room_ids(svc_fx, 'B', '13:00', '15:00'), \
        'chained adjacent bookings must stay available'


def test_legacy_booking_without_times_blocks_period_span(svc_fx):
    """حجز قديم بلا أوقات (period A, hours=3) ⇒ الفترة B تبقى محجوبة (توافق عكسي)."""
    f = svc_fx
    f['db'].execute(
        'INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, '
        'department_id, start_time, end_time, lecture_type, hours) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        ('الأحد', 1, 'A', f['course_id'], f['teacher1'], f['room1'],
         f['dept_id'], '', '', 'theory', 3),
    )
    f['db'].commit()
    ids = _available_room_ids(svc_fx, 'B', '12:01', '14:00')
    assert ids != [] and f['room1'] not in ids, \
        'legacy span booking must keep hiding the room'
