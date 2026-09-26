"""Regression tests for the HOD dashboard data fixes.

Covers:
  1. The attendance feature is cancelled — no attendance keys are computed.
  2. "القاعات المشغولة الآن" lists only entries currently in progress
     (filtered by start_time / end_time), and the count is unique rooms.
  3. The weekly timetable keeps every entry of a day+period cell
     (multiple sections are no longer dropped).
  4. A semester filter narrows the weekly timetable (and occupied list)
     to the selected semester.
"""

import sqlite3
from datetime import datetime, timedelta

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from werkzeug.security import generate_password_hash

_today_arabic = {
    0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس',
    4: 'الجمعة', 5: 'السبت', 6: 'الأحد',
}


@pytest.fixture
def hod_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'hod_dashboard.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())

    conn.execute("INSERT INTO departments (name, type) VALUES ('قسم الاتصالات', 'academic')")
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الاتصالات'"
    ).fetchone()['id']

    conn.execute(
        "INSERT INTO users (username, password, role, label) VALUES (?, ?, 'head_of_department', 'رئيس القسم')",
        ('hod_dash', generate_password_hash('secret')),
    )
    user_id = conn.execute("SELECT id FROM users WHERE username='hod_dash'").fetchone()['id']

    conn.execute(
        "INSERT INTO teachers (name, user_id, hod_department_id) VALUES ('رئيس القسم', ?, ?)",
        (user_id, dept_id),
    )
    hod_teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE name='رئيس القسم'"
    ).fetchone()['id']

    # A colleague linked to the department (backfill source (a)).
    conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('زميل أول', ?)",
        (dept_id,),
    )
    colleague_id = conn.execute(
        "SELECT id FROM teachers WHERE name='زميل أول'"
    ).fetchone()['id']

    conn.execute("INSERT INTO rooms (name, code, department_id) VALUES ('قاعة 1', 'R1', ?)", (dept_id,))
    r1 = conn.execute("SELECT id FROM rooms WHERE code='R1'").fetchone()['id']
    conn.execute("INSERT INTO rooms (name, code, department_id) VALUES ('قاعة 2', 'R2', ?)", (dept_id,))
    r2 = conn.execute("SELECT id FROM rooms WHERE code='R2'").fetchone()['id']

    conn.execute("INSERT INTO courses (code, name) VALUES ('C1', 'شبكات')")
    c1 = conn.execute("SELECT id FROM courses WHERE code='C1'").fetchone()['id']
    conn.execute("INSERT INTO courses (code, name) VALUES ('C2', 'دارات')")
    c2 = conn.execute("SELECT id FROM courses WHERE code='C2'").fetchone()['id']

    conn.commit()
    ensure_schema(conn)
    conn.commit()
    conn.close()

    return {
        'db_path': str(db_path),
        'dept_id': dept_id,
        'hod_teacher_id': hod_teacher_id,
        'colleague_id': colleague_id,
        'r1': r1,
        'r2': r2,
        'c1': c1,
        'c2': c2,
    }


def _connect():
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _today_ar():
    day_key = datetime.now().weekday()
    if day_key == 4:  # الجمعة — عطلة، والخدمة تُعدّ صفراً
        pytest.skip('اليوم جمعة: الخدمة لا تعرض قاعات/محاضرات في العطلة')
    return _today_arabic[day_key]


def test_create_app_migrates_legacy_database(tmp_path, monkeypatch):
    """Legacy sqlite databases missing soft-delete columns should still boot."""
    db_path = tmp_path / 'legacy_dashboard.db'
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT, hidden INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)"
    )
    conn.execute(
        "CREATE TABLE teachers (id INTEGER PRIMARY KEY, name TEXT, user_id INTEGER, department_id INTEGER)"
    )
    conn.execute(
        "CREATE TABLE rooms (id INTEGER PRIMARY KEY, name TEXT, department_id INTEGER)"
    )
    conn.execute(
        "CREATE TABLE courses (id INTEGER PRIMARY KEY, code TEXT, name TEXT)"
    )
    conn.execute(
        "CREATE TABLE exam_schedule (id INTEGER PRIMARY KEY, exam_date TEXT)"
    )
    conn.execute(
        "CREATE TABLE history (id INTEGER PRIMARY KEY, created_at TEXT)"
    )
    conn.commit(); conn.close()

    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    # ensure_database_schema() is exactly what flask_db.init_app() runs on boot.
    # Calling it directly proves the migration path without building a second
    # app, which would re-register error handlers on the global blueprints.
    from flask_db import ensure_database_schema
    ensure_database_schema()

    conn = sqlite3.connect(str(db_path))
    cols = [row[1] for row in conn.execute('PRAGMA table_info(departments)').fetchall()]
    conn.close()
    assert 'deleted_at' in cols


# ── 1. Attendance is cancelled ────────────────────────────────────────────

def test_hod_attendance_feature_removed(hod_db):
    """Attendance was dropped from the project — no data must be computed."""
    from services.dashboard_service import get_hod_dashboard_data
    conn = _connect()
    data = get_hod_dashboard_data(conn, hod_db['dept_id'])
    conn.close()

    assert 'faculty_attendance' not in data
    assert 'faculty_present' not in data
    assert 'faculty_late' not in data
    assert 'faculty_absent' not in data


# ── 2. "القاعات المشغولة الآن" = entries in progress only ________________

def test_hod_occupied_rooms_only_current(hod_db):
    now = datetime.now()
    active_start = (now - timedelta(minutes=30)).strftime('%H:%M')
    active_end = (now + timedelta(minutes=30)).strftime('%H:%M')
    past_start = (now - timedelta(hours=3)).strftime('%H:%M')
    past_end = (now - timedelta(hours=2)).strftime('%H:%M')
    day = _today_ar()

    conn = _connect()
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, start_time, end_time) "
        "VALUES (?, 1, 'A', ?, ?, ?, ?, ?, ?)",
        (day, hod_db['c1'], hod_db['hod_teacher_id'], hod_db['r1'], hod_db['dept_id'], active_start, active_end),
    )
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, start_time, end_time) "
        "VALUES (?, 1, 'B', ?, ?, ?, ?, ?, ?)",
        (day, hod_db['c2'], hod_db['colleague_id'], hod_db['r2'], hod_db['dept_id'], past_start, past_end),
    )
    conn.commit()
    conn.close()

    from services.dashboard_service import get_hod_dashboard_data
    conn = _connect()
    data = get_hod_dashboard_data(conn, hod_db['dept_id'])
    conn.close()

    room_ids = {e['room_id'] for e in data['occupied_rooms']}
    assert room_ids == {hod_db['r1']}, f'من المتوقع قاعة R1 فقط، وجدت: {room_ids}'
    assert data['occupied_rooms_count'] == 1
    assert data['today_entries_count'] == 2
    assert len(data['today_lectures']) == 2


# ── 3. Weekly timetable keeps all entries of a cell ───────────────────────

def test_hod_weekly_timetable_keeps_multiple_entries(hod_db):
    day = _today_ar()
    conn = _connect()
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id) "
        "VALUES (?, 1, 'A', ?, ?, ?, ?)",
        (day, hod_db['c1'], hod_db['hod_teacher_id'], hod_db['r1'], hod_db['dept_id']),
    )
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id) "
        "VALUES (?, 1, 'A', ?, ?, ?, ?)",
        (day, hod_db['c2'], hod_db['colleague_id'], hod_db['r2'], hod_db['dept_id']),
    )
    conn.commit()
    conn.close()

    from services.dashboard_service import get_hod_dashboard_data
    conn = _connect()
    data = get_hod_dashboard_data(conn, hod_db['dept_id'])
    conn.close()

    cell = [e for e in data['weekly_timetable'].get(day, []) if e['period'] == 'A']
    assert len(cell) == 2
    assert {e['room_name'] for e in cell} == {'قاعة 1', 'قاعة 2'}


# ── 4. Semester filter ────────────────────────────────────────────────────

def _insert_entry(conn, hod_db, day, semester, period, course, teacher, room,
                  start_time=None, end_time=None):
    if start_time and end_time:
        conn.execute(
            "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, start_time, end_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (day, semester, period, course, teacher, room, hod_db['dept_id'], start_time, end_time),
        )
    else:
        conn.execute(
            "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (day, semester, period, course, teacher, room, hod_db['dept_id']),
        )


def test_hod_weekly_timetable_semester_filter(hod_db):
    day = _today_ar()
    conn = _connect()
    _insert_entry(conn, hod_db, day, 1, 'A', hod_db['c1'], hod_db['hod_teacher_id'], hod_db['r1'])
    _insert_entry(conn, hod_db, day, 2, 'A', hod_db['c2'], hod_db['colleague_id'], hod_db['r2'])
    conn.commit()
    conn.close()

    from services.dashboard_service import get_hod_dashboard_data
    conn = _connect()
    data = get_hod_dashboard_data(conn, hod_db['dept_id'], semester=1)
    conn.close()

    assert data['selected_semester'] == 1
    assert data['selected_semester_label'] == 'الفصل الأول'
    cell = [e for e in data['weekly_timetable'].get(day, []) if e['period'] == 'A']
    assert len(cell) == 1
    assert cell[0]['course_name'] == 'شبكات'
    assert {s['code'] for s in data['semesters']} == {1, 2, 3, 4, 5, 6, 7, 8}
    assert {s['label'] for s in data['semesters']} == {
        'الفصل الأول', 'الفصل الثاني', 'الفصل الثالث', 'الفصل الرابع',
        'الفصل الخامس', 'الفصل السادس', 'الفصل السابع', 'الفصل الثامن',
    }

    # بلا فلتر: نعرض كل الفصول
    conn = _connect()
    data_all = get_hod_dashboard_data(conn, hod_db['dept_id'])
    conn.close()
    cell_all = [e for e in data_all['weekly_timetable'].get(day, []) if e['period'] == 'A']
    assert len(cell_all) == 2


def test_hod_occupied_rooms_respect_semester_filter(hod_db):
    now = datetime.now()
    active_start = (now - timedelta(minutes=30)).strftime('%H:%M')
    active_end = (now + timedelta(minutes=30)).strftime('%H:%M')
    day = _today_ar()

    conn = _connect()
    _insert_entry(conn, hod_db, day, 1, 'A', hod_db['c1'], hod_db['hod_teacher_id'],
                  hod_db['r1'], active_start, active_end)
    _insert_entry(conn, hod_db, day, 2, 'B', hod_db['c2'], hod_db['colleague_id'],
                  hod_db['r2'], active_start, active_end)
    conn.commit()
    conn.close()

    from services.dashboard_service import get_hod_dashboard_data
    conn = _connect()
    data = get_hod_dashboard_data(conn, hod_db['dept_id'], semester=1)
    conn.close()

    room_ids = {e['room_id'] for e in data['occupied_rooms']}
    assert room_ids == {hod_db['r1']}
    assert data['occupied_rooms_count'] == 1