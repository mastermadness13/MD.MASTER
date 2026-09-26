"""HOD dashboard renders real data.

The template used to be entirely hardcoded: a fixed instructor name, a fixed
date, and "0" / "لا توجد محاضرات" for every figure, while
dashboard_service.get_hod_dashboard_data() returned 24 keys that the template
never referenced. These tests seed a department with real rows and assert the
numbers reach the page.
"""

import pytest
import re
from datetime import datetime

import flask_db
from database.connection import connect
from database.schema import ensure_schema

# Mirrors dashboard_service.get_hod_dashboard_data's own mapping.
_ARABIC_DAYS = {
    0: 'الإثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس',
    4: 'الجمعة', 5: 'السبت', 6: 'الأحد',
}


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'hod_dash.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('hod_dash_user', 'x', 'head_of_department', 'أ. رئيس القسم')"
    )
    hod_uid = conn.execute(
        "SELECT id FROM users WHERE username='hod_dash_user'"
    ).fetchone()['id']
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, "
        "has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO rooms (name, capacity, type) "
        "VALUES ('قاعة 101', 40, 'lecture')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    room_id = conn.execute("SELECT id FROM rooms").fetchone()['id']

    conn.execute(
        "INSERT OR IGNORE INTO teachers (name, academic_number, department_id) "
        "VALUES ('أ. سارة Sasha', 'AN-HOD-1', ?)",
        (dept_id,),
    )
    teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE academic_number='AN-HOD-1'"
    ).fetchone()['id']

    # dashboard_service filters teachers_list through teacher_departments, not
    # teachers.department_id, so the link row has to exist or the list is empty.
    conn.execute(
        'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) '
        'VALUES (?, ?)',
        (teacher_id, dept_id),
    )

    conn.execute(
        "INSERT OR IGNORE INTO courses (code, name, department_id) "
        "VALUES ('CS101', 'أساسيات الحاسوب', ?)",
        (dept_id,),
    )
    course_id = conn.execute(
        "SELECT id FROM courses WHERE code='CS101'"
    ).fetchone()['id']
    conn.execute(
        'INSERT OR IGNORE INTO course_departments (course_id, department_id) '
        'VALUES (?, ?)',
        (course_id, dept_id),
    )

    conn.execute(
        "INSERT OR IGNORE INTO timetable_versions (department_id, semester, "
        "semester_code, status) VALUES (?, 1, 'fall_2026', 'active')",
        (dept_id,),
    )
    version_id = conn.execute("SELECT id FROM timetable_versions").fetchone()['id']

    # Two lectures on Saturday plus one on Sunday, so the weekly table has to
    # loop over more than one row per day to render all three.
    for period in ('1', '2'):
        conn.execute(
            'INSERT INTO timetable (day, period, start_time, end_time, course_id, '
            'teacher_id, room_id, department_id, version_id, semester) '
            "VALUES ('السبت', ?, '08:00', '09:30', ?, ?, ?, ?, ?, 1)",
            (period, course_id, teacher_id, room_id, dept_id, version_id),
        )
    conn.execute(
        'INSERT INTO timetable (day, period, start_time, end_time, course_id, '
        'teacher_id, room_id, department_id, version_id, semester) '
        "VALUES ('الأحد', '1', '10:00', '11:30', ?, ?, ?, ?, ?, 1)",
        (course_id, teacher_id, room_id, dept_id, version_id),
    )

    # pending_requests is read from teacher_requests, not teacher_messages.
    conn.execute(
        'INSERT INTO teacher_requests (teacher_id, user_id, department_id, '
        "request_type, subject, message, status) "
        "VALUES (?, ?, ?, 'general', 'طلب اعتماد', 'نص الطلب', 'pending')",
        (teacher_id, hod_uid, dept_id),
    )

    # How the page is *supposed* to read today: the number of rows on today's
    # weekday. The service maps weekday() to these names and reports nothing on
    # Friday, which has no school.
    today_ar = _ARABIC_DAYS.get(datetime.now().weekday())
    if today_ar == 'الجمعة':
        expected_today = 0
    else:
        expected_today = conn.execute(
            'SELECT COUNT(*) AS c FROM timetable WHERE day = ? '
            'AND department_id = ?',
            (today_ar, dept_id),
        ).fetchone()['c']

    # One lecture on *today's* weekday so the figure is deterministic whatever
    # day the suite runs. Saturday and Sunday already have rows above, so adding
    # one more there would change the seeded count; Friday gets none on purpose.
    if today_ar and today_ar not in ('السبت', 'الأحد', 'الجمعة'):
        conn.execute(
            'INSERT INTO timetable (day, period, start_time, end_time, course_id, '
            'teacher_id, room_id, department_id, version_id, semester) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)',
            (today_ar, '3', '11:00', '12:30', course_id, teacher_id, room_id,
             dept_id, version_id),
        )
        expected_today = 1

    conn.commit()
    conn.close()
    return str(db_path), dept_id, teacher_id, expected_today


@pytest.fixture
def hod_client(app_fx, db_fx):
    db_path, dept_id, teacher_id, expected_today = db_fx
    conn = connect(db_path)
    uid = conn.execute(
        "SELECT id FROM users WHERE username='hod_dash_user'"
    ).fetchone()['id']
    conn.close()

    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = 'head_of_department'
        sess['username'] = 'hod_dash_user'
        sess['department_id'] = dept_id
        sess['hod_department_id'] = dept_id
        sess['_csrf_token'] = 't'
    c.hod_teacher_id = teacher_id
    c.hod_expected_today = expected_today
    return c


def _body(hod_client):
    resp = hod_client.get('/')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _text(body):
    """Flatten to visible text so assertions can cross element boundaries -
    a figure and its label render in sibling elements, not one string."""
    stripped = re.sub(r'<[^>]+>', ' ', body)
    return re.sub(r'\s+', ' ', stripped)


def test_dashboard_renders(hod_client):
    assert 'لوحة تحكم' in _body(hod_client)


def test_department_name_comes_from_the_database_without_doubling(hod_client):
    body = _body(hod_client)
    assert 'قسم الحاسوب' in body
    assert 'قسم قسم' not in body, (
        'the header prefixes "قسم" onto a department name that already has it'
    )


def test_signed_in_hod_name_is_shown_not_a_hardcoded_one(hod_client):
    body = _body(hod_client)
    assert 'أ. رئيس القسم' in body
    assert 'الهام' not in body, (
        'a previous instructor name is still hardcoded in the header'
    )


def test_date_chip_is_computed_not_fixed(hod_client):
    """The old template hardcoded "الخميس، 24 سبتمبر"."""
    body = _body(hod_client)
    assert '24 سبتمبر' not in body
    assert 'todayDateChip' in body


def test_weekly_schedule_rows_come_from_the_timetable(hod_client):
    body = _body(hod_client)
    assert 'السبت' in body
    assert 'الأحد' in body
    assert '08:00' in body and '09:30' in body
    assert 'أساسيات الحاسوب' in body
    # A day with no lectures must not be invented.
    assert 'الثلاثاء' not in body


def test_lecture_count_is_real(hod_client):
    """The figure has to match the rows seeded for today - never the literal 0
    the old template hardcoded."""
    text = _text(_body(hod_client))
    expected = hod_client.hod_expected_today
    assert '%d محاضرات اليوم' % expected in text, (
        'the today count does not match the timetable rows (%d)' % expected
    )
    assert '0 محاضرات اليوم' not in text or expected == 0
    assert '08:00' in text or '11:00' in text, "no lecture times reached the page"


def test_course_and_teacher_counts_are_real(hod_client):
    text = _text(_body(hod_client))
    assert '1 مقررات القسم' in text
    assert 'أ. سارة' in text


def test_pending_request_is_surfaced(hod_client):
    body = _body(hod_client)
    assert 'طلب اعتماد' in body
    assert 'طلب معلّق' in body


def test_no_hardcoded_zero_counts_remain(hod_client):
    """The regression this fixes: every figure was a literal in the template."""
    text = _text(_body(hod_client))
    if hod_client.hod_expected_today != 0:
        assert '0 محاضرات اليوم' not in text
    assert '0 مقررات القسم' not in text


def test_course_coverage_progressbar_is_labelled(hod_client):
    body = _body(hod_client)
    assert 'role="progressbar"' in body
    assert 'aria-valuenow=' in body
    assert 'نسبة المقررات المجدولة' in body


def test_links_point_at_real_endpoints(hod_client):
    """url_for raises at render time for a bad endpoint, so a 200 already
    proves the names resolve; assert the paths to catch a silent swap."""
    body = _body(hod_client)
    assert '/print/timetables/department' in body
    assert '/hod/messages' in body
    # Rendered from teachers_list, which the fixture populates, so this also
    # proves the teacher load breakdown is not silently empty.
    assert '/teachers/%d' % hod_client.hod_teacher_id in body
