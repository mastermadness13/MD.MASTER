"""Phase 3 — uniform input validation (L4/L5/L6).

Locks down that:
  - the vendored ``core.validators`` helpers are real and behave (L4);
  - course create/update share one validation routine (L5);
  - API mutation endpoints reject out-of-range numbers, bad times and
    whitelisted days instead of silently coercing (L6).

All HTTP tests hit rejection paths that fire BEFORE any DB/service side effect,
so a minimal schema DB is enough.
"""

import sqlite3

import pytest

import flask_db
from api_routes.courses import _validate_course
from api_routes.timetable import _entry_fields_valid
from core.validators import (
    in_choices,
    integer_between,
    valid_date_range,
    valid_time,
)
from database.connection import connect
from database.schema import ensure_schema


# ── core.validators (L4) ────────────────────────────────────────────────────


def test_integer_between_accepts_bounds():
    assert integer_between(5, 1, 10, 'x') is None
    assert integer_between(1, 1, 10, 'x') is None
    assert integer_between(10, 1, 10, 'x') is None


@pytest.mark.parametrize('bad', [0, -1, 11, 'abc', 1.5, True])
def test_integer_between_rejects(bad):
    assert integer_between(bad, 1, 10, 'عدد') is not None


def test_integer_between_missing_is_permitted():
    assert integer_between(None, 1, 10, 'عدد') is None
    assert integer_between('', 1, 10, 'عدد') is None


def test_integer_between_accepts_numeric_strings():
    assert integer_between('7', 1, 10, 'x') is None
    assert integer_between('25', 1, 10, 'x') is not None


def test_valid_time_accepts_24h():
    for t in ['08:30', '14:00', '00:00', '23:59', '9:05']:
        assert valid_time(t, 'الوقت') is None, t


@pytest.mark.parametrize('bad', ['25:99', '12:60', '10:5', 'abc', '8', '24:00'])
def test_valid_time_rejects_malformed(bad):
    assert valid_time(bad, 'الوقت') is not None


def test_valid_time_allows_missing():
    assert valid_time(None) is None
    assert valid_time('') is None


def test_in_choices_whitelists():
    assert in_choices('الأحد', ['الأحد', 'الاثنين'], 'اليوم') is None
    assert in_choices('sunday', ['الأحد'], 'اليوم') is not None
    assert in_choices(None, ['الأحد'], 'اليوم') is None


def test_valid_date_range():
    assert valid_date_range('2026-06-01', '2026-06-10') is None
    assert valid_date_range('2026-06-10', '2026-06-01') is not None
    assert valid_date_range('', '') is None


# ── L5: shared course form validation ────────────────────────────────────────


def test_course_form_valid():
    form = {'code': 'CS101', 'name': 'برمجة', 'year': 2, 'semester': 3,
            'theoretical_hours': 3, 'practical_hours': 1, 'total_hours': 4}
    assert _validate_course(form) == []


def test_course_form_missing_code_and_name():
    errors = _validate_course({'code': '', 'name': '', 'year': 1, 'semester': 1,
                               'theoretical_hours': 0, 'practical_hours': 0,
                               'total_hours': 0})
    assert any('الكود' in e for e in errors)
    assert any('الاسم' in e for e in errors)


def test_course_form_name_length_and_numeric_bounds():
    errors = _validate_course({'code': 'A', 'name': 'ن' * 256, 'year': 99,
                               'semester': 0, 'theoretical_hours': 999,
                               'practical_hours': -1, 'total_hours': 'abc'})
    assert len(errors) >= 5
    assert any('255' in e for e in errors)
    assert any('السنة' in e for e in errors)
    assert any('إجمالي الساعات' in e for e in errors)


def test_course_form_accepts_string_numerics():
    form = {'code': 'CS101', 'name': 'برمجة', 'year': '2', 'semester': '3',
            'theoretical_hours': '3', 'practical_hours': '1', 'total_hours': '4'}
    assert _validate_course(form) == []


# ── L6: timetable structural validation ──────────────────────────────────────


def test_timetable_entry_valid():
    fields = {'day': 'الأحد', 'hours': 3, 'start_time': '08:30', 'end_time': '09:30'}
    assert _entry_fields_valid(fields) == []


def test_timetable_entry_rejects_bad_day():
    errors = _entry_fields_valid({'day': 'sunday', 'hours': 3,
                                  'start_time': '08:30', 'end_time': '09:30'})
    assert any('اليوم' in e for e in errors)


def test_timetable_entry_rejects_bad_time_and_hours():
    errors = _entry_fields_valid({'day': 'الأحد', 'hours': 99,
                                  'start_time': '25:99', 'end_time': '12:60'})
    assert any('الوقت' in e or 'عدد الساعات' in e for e in errors)
    assert len(errors) >= 2


def test_timetable_entry_accepts_missing_times():
    assert _entry_fields_valid({'day': 'الأحد', 'hours': 0,
                                'start_time': '', 'end_time': ''}) == []


# ── L5/L6 HTTP: rejections happen before side effects ────────────────────────


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'validation.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES "
        "('office_manager', 'x', 'faculty_affairs', 'مكتب أعضاء هيئة التدريس')")
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES "
        "('hod', 'x', 'head_of_department', 'رئيس القسم')")
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES "
        "('exam_officer', 'x', 'exam', 'شعبة الامتحانات')")
    # courses.manage is held only by research_development, so course-write
    # validation tests need a real R&D account to reach the handler.
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES "
        "('rd_officer', 'x', 'research_development', 'مستثير التطوير و التقنية')")
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES "
        "('قسم الحاسوب', 8, 8, 0, 1, 'academic')")
    conn.commit()
    conn.close()
    return db_path


def _client(app_fx, user_id, role=None):
    """Build a logged-in test client.

    *user_id* may be an int (legacy) or a role name. Passing the role name is
    preferred: the seeded ids depend on what ensure_schema() already inserted,
    and a session pointing at a non-existent user_id is cleared by
    app.before_request's enforce_session_version, which turns an expected
    4xx into a 302 to /login.
    """
    if not isinstance(user_id, int):
        role = user_id
        conn = sqlite3.connect(flask_db.DATABASE)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT id FROM users WHERE role = ? ORDER BY id LIMIT 1', (role,)
        ).fetchone()
        conn.close()
        assert row is not None, f'no seeded user with role {role!r}'
        user_id = row['id']
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['role'] = role
        sess['username'] = 'x'
        sess['department_id'] = 1
        sess['_csrf_token'] = 't'
    return c


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows


def _session_headers():
    return {'Accept': 'application/json'}


def test_course_create_rejects_bad_year_http(app_fx, db_fx):
    c = _client(app_fx, 'research_development')
    r = c.post('/api/courses', json={
        'code': 'X1', 'name': 'مادة', 'year': 99, 'semester': 1,
        'theoretical_hours': 0, 'practical_hours': 0, 'total_hours': 0,
        '_csrf_token': 't',
    }, headers=_session_headers())
    assert r.status_code == 422
    body = r.get_json()
    assert body['ok'] is False
    assert any('السنة' in e for e in body['errors'])
    assert _q('SELECT COUNT(*) AS n FROM courses')[0]['n'] == 0


def test_room_create_rejects_huge_capacity_http(app_fx, db_fx):
    c = _client(app_fx, 1, 'faculty_affairs')
    r = c.post('/api/rooms', json={
        'name': 'قاعة كبيرة', 'capacity': 100000, '_csrf_token': 't',
    }, headers=_session_headers())
    assert r.status_code == 422
    assert r.get_json()['ok'] is False
    assert _q('SELECT COUNT(*) AS n FROM rooms')[0]['n'] == 0


def test_exam_settings_reject_bad_session_time_http(app_fx, db_fx):
    c = _client(app_fx, 3, 'exam')
    r = c.put('/api/exams/settings', json={
        'session_a': '08:30', 'session_b': '25:99', 'session_c': '14:30',
        'proctors_per_room': 99, '_csrf_token': 't',
    }, headers=_session_headers())
    assert r.status_code == 422
    body = r.get_json()
    assert body['ok'] is False
    assert any('الجلسة' in e for e in body['errors'])
    assert any('مراقب' in e for e in body['errors'])


def test_exam_period_rejects_reversed_dates_http(app_fx, db_fx):
    c = _client(app_fx, 3, 'exam')
    r = c.put('/api/exams/period', json={
        'exam_start_date': '2026-07-01', 'exam_end_date': '2026-06-01',
        'exam_start_time': '09:00', 'exam_end_time': '17:00', '_csrf_token': 't',
    }, headers=_session_headers())
    assert r.status_code == 422
    assert r.get_json()['ok'] is False


def test_timetable_entry_update_rejects_bad_time_http(app_fx, db_fx):
    c = _client(app_fx, 'head_of_department')
    r = c.put('/api/timetable/entries/1', json={
        'day': 'الأحد', 'course_id': 1, 'room_id': 1, 'period_code': 'أ',
        'start_time': '25:99', 'end_time': '09:00', 'hours': 3,
        '_csrf_token': 't',
    }, headers=_session_headers())
    assert r.status_code == 422
    assert r.get_json()['ok'] is False