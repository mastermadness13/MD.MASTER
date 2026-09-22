# -*- coding: utf-8 -*-
"""Integration tests for the general-department semester rule (Phase 1).

The rule: «القسم العام» (semesters <= 1 or that name) only accepts semester 1;
every other department accepts 2..min(semesters, 8). This file verifies the
enforcement across every write path and the read-path redirect:
  - API create/update   → 422 without touching the database
  - HTML form POST      → error, no row created
  - read views          → 302 redirect to the first allowed semester
  - service layer       → InvalidSemesterError guard
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.repositories.timetable_repository import TimetableRepository
from database.schema import ensure_schema
from services import timetable_service
from services.timetable_scope import InvalidSemesterError, INVALID_SEMESTER_MESSAGE


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_general_rule.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('exam', 'x', 'exam', 'الامتحانات')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('القسم العام', 1, 1, 0, 1, 'academic')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    general_id = conn.execute("SELECT id FROM departments WHERE name='القسم العام'").fetchone()['id']
    computers_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']

    cid = conn.execute(
        "INSERT INTO courses (code, name, department_id) VALUES ('CS1', 'مقرر اختبار', ?)",
        (computers_id,),
    ).lastrowid
    tid = conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('أستاذ', ?)", (computers_id,),
    ).lastrowid
    rid = conn.execute("INSERT INTO rooms (name) VALUES ('قاعة')").lastrowid

    conn.commit()
    conn.close()
    return {
        'db_path': str(db_path),
        'general': general_id, 'computers': computers_id,
        'course': cid, 'teacher': tid, 'room': rid,
    }


@pytest.fixture
def viewer(app_fx, db_fx):
    """بديل قسم الامتحانات للقراءة فقط (يملك timetable.view بدون تعديل)."""
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'research_development'
        sess['username'] = 'rnd'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


@pytest.fixture
def make_client(app_fx):
    """محرّر الجدول الوحيد المتبقّي: رئيس القسم (مقيّد بقسمه)."""
    def _make(dept_id):
        c = app_fx.test_client()
        with c.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'head_of_department'
            sess['username'] = 'hod'
            sess['department_id'] = dept_id
            sess['hod_department_id'] = dept_id
            sess['_csrf_token'] = 't'
        return c
    return _make


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows


def _counts(dept_id, semester):
    rows = _q(
        'SELECT (SELECT COUNT(*) FROM timetable WHERE department_id=? AND semester=?) AS entries, '
        '(SELECT COUNT(*) FROM timetable_versions WHERE department_id=? AND semester=?) AS versions',
        (dept_id, semester, dept_id, semester),
    )
    return rows[0]['entries'], rows[0]['versions']


def _payload(f, dept_id, semester, **over):
    payload = {
        'day': 'السبت',
        'semester': semester,
        'period_code': 'A',
        'course_id': f['course'],
        'teacher_id': f['teacher'],
        'room_id': f['room'],
        'department_id': dept_id,
        'start_time': '08:00',
        'end_time': '09:00',
        '_csrf_token': 't',
    }
    payload.update(over)
    return payload


# ────────────── API create ──────────────

def test_api_create_rejects_semester1_for_regular_dept(make_client, db_fx):
    client = make_client(db_fx['computers'])
    r = client.post('/api/timetable/entries', json=_payload(db_fx, db_fx['computers'], 1))
    assert r.status_code == 422
    assert INVALID_SEMESTER_MESSAGE in r.get_json()['message']
    entries, versions = _counts(db_fx['computers'], 1)
    assert entries == 0 and versions == 0, 'no row and no stray version on rejection'


def test_api_create_accepts_semester5_for_regular_dept(make_client, db_fx):
    client = make_client(db_fx['computers'])
    r = client.post('/api/timetable/entries', json=_payload(db_fx, db_fx['computers'], 5))
    assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))
    entries, _ = _counts(db_fx['computers'], 5)
    assert entries == 1


def test_api_create_rejects_semester2_for_general_dept(make_client, db_fx):
    client = make_client(db_fx['general'])
    r = client.post('/api/timetable/entries', json=_payload(db_fx, db_fx['general'], 2))
    assert r.status_code == 422
    assert INVALID_SEMESTER_MESSAGE in r.get_json()['message']
    entries, versions = _counts(db_fx['general'], 2)
    assert entries == 0 and versions == 0


def test_api_create_accepts_semester1_for_general_dept(make_client, db_fx):
    client = make_client(db_fx['general'])
    r = client.post('/api/timetable/entries', json=_payload(db_fx, db_fx['general'], 1))
    assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))


# ────────────── API update ──────────────

def test_api_update_rejects_invalid_semester(make_client, db_fx):
    client = make_client(db_fx['computers'])
    created = client.post('/api/timetable/entries', json=_payload(db_fx, db_fx['computers'], 5))
    entry_id = created.get_json()['data']['id']

    r = client.put(f'/api/timetable/entries/{entry_id}', json=_payload(db_fx, db_fx['computers'], 1))
    assert r.status_code == 422
    assert INVALID_SEMESTER_MESSAGE in r.get_json()['message']
    rows = _q('SELECT semester FROM timetable WHERE id=?', (entry_id,))
    assert rows[0]['semester'] == 5, 'entry must remain untouched on rejection'


def test_api_update_missing_entry_404(make_client, db_fx):
    client = make_client(db_fx['computers'])
    r = client.put('/api/timetable/entries/999999', json=_payload(db_fx, db_fx['computers'], 2))
    assert r.status_code == 404


# ────────────── HTML form create ──────────────

def test_html_create_form_rejects_invalid_semester(make_client, db_fx):
    client = make_client(db_fx['computers'])
    r = client.post('/timetable/create', data={
        'day': 'الأحد',
        'semester': '1',
        'section': 'A',
        'course_id': db_fx['course'],
        'teacher_id': db_fx['teacher'],
        'room_id': db_fx['room'],
        'department_id': db_fx['computers'],
        'start_time': '08:00',
        'end_time': '09:00',
        '_csrf_token': 't',
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert INVALID_SEMESTER_MESSAGE in body
    entries, versions = _counts(db_fx['computers'], 1)
    assert entries == 0 and versions == 0


# ────────────── read path redirect ──────────────

def test_read_redirects_general_dept_to_semester1(viewer, db_fx):
    r = viewer.get(f"/timetable/?department_id={db_fx['general']}&semester=3")
    assert r.status_code == 302
    assert 'semester=1' in r.headers['Location']


def test_read_redirects_regular_dept_away_from_semester1(viewer, db_fx):
    r = viewer.get(f"/timetable/?department_id={db_fx['computers']}&semester=1")
    assert r.status_code == 302
    assert 'semester=2' in r.headers['Location']


def test_read_department_view_redirects_general_to_semester1(viewer, db_fx):
    r = viewer.get(f"/timetable/department?department_id={db_fx['general']}&semester=5")
    assert r.status_code == 302
    assert 'semester=1' in r.headers['Location']


# ────────────── service layer guard ──────────────

def test_service_create_entry_raises_for_invalid_semester(db_fx):
    conn = connect(db_fx['db_path'])
    svc = timetable_service.TimetableService(conn, TimetableRepository(conn))
    with pytest.raises(InvalidSemesterError):
        svc.create_entry('الأحد', 1, 'A', db_fx['course'], db_fx['teacher'],
                         db_fx['room'], db_fx['computers'])
    conn.close()


def test_service_update_entry_is_accepted_for_allowed_semester(db_fx):
    conn = connect(db_fx['db_path'])
    svc = timetable_service.TimetableService(conn, TimetableRepository(conn))
    entry_id = svc.create_entry('الأحد', 5, 'A', db_fx['course'], db_fx['teacher'],
                                db_fx['room'], db_fx['computers'])
    ok = svc.update_entry(entry_id, 'الأحد', 5, 'B', db_fx['course'], db_fx['teacher'],
                          db_fx['room'], start_time='09:00', end_time='10:00')
    assert ok
    conn.close()