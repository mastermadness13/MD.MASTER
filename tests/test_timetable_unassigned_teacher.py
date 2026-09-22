# -*- coding: utf-8 -*-
"""«محاضرة بدون أستاذ» — timetable entries may be saved with NO teacher
(teacher_id NULL, assignment_status='unassigned' conceptually) and the
teacher assigned later via edit. This file verifies:
  - service create/update accept teacher_id=None without teacher warnings
  - API create/update accept a missing teacher_id
  - the HTML form POST stores teacher_id NULL
  - a teacher-conflict warning appears only once a teacher is assigned
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.repositories.timetable_repository import TimetableRepository
from database.schema import ensure_schema
from services import timetable_service


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_unassigned.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('hod', 'x', 'head_of_department', 'رئيس القسم')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 8, 8, 0, 2, 'academic')"
    )
    computers_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']

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
        'computers': computers_id,
        'course': cid, 'teacher': tid, 'room': rid,
    }


@pytest.fixture
def client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'head_of_department'
        sess['username'] = 'hod'
        sess['department_id'] = None
        sess['hod_department_id'] = db_fx['computers']
        sess['_csrf_token'] = 't'
    return c


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows


def _svc(db_fx):
    conn = connect(db_fx['db_path'])
    return conn, timetable_service.TimetableService(conn, TimetableRepository(conn))


def _payload(f, **over):
    payload = {
        'day': 'السبت',
        'semester': 2,
        'period_code': 'A',
        'course_id': f['course'],
        'teacher_id': f['teacher'],
        'room_id': f['room'],
        'department_id': f['computers'],
        'start_time': '08:00',
        'end_time': '09:00',
        '_csrf_token': 't',
    }
    payload.update(over)
    return payload


# ────────────── service layer ──────────────

def test_service_create_without_teacher_stores_null_and_no_warning(db_fx):
    conn, svc = _svc(db_fx)
    eid = svc.create_entry('السبت', 2, 'A', db_fx['course'], None,
                           db_fx['room'], db_fx['computers'])
    warnings = svc.get_last_conflict_warnings()
    rows = _q('SELECT teacher_id FROM timetable WHERE id=?', (eid,))
    assert rows[0]['teacher_id'] is None
    assert warnings == []
    conn.close()


def test_service_assign_teacher_later_raises_conflict_warning(db_fx):
    conn, svc = _svc(db_fx)
    # حصة بلا أستاذ في نفس المكان والزمان الذي يشغله الأستاذ
    eid_unassigned = svc.create_entry('السبت', 2, 'A', db_fx['course'], None,
                                      db_fx['room'], db_fx['computers'])
    eid_teacher = svc.create_entry('السبت', 2, 'B', db_fx['course'], db_fx['teacher'],
                                   db_fx['room'], db_fx['computers'],
                                   start_time='08:00', end_time='09:00')
    svc.get_last_conflict_warnings()
    # تعيين الأستاذ لاحقًا على الحصة الأولى → تنبيه تعارض محاضر يجب أن يظهر
    svc.update_entry(eid_unassigned, 'السبت', 2, 'A', db_fx['course'], db_fx['teacher'],
                     db_fx['room'], start_time='08:00', end_time='09:00')
    warnings = svc.get_last_conflict_warnings()
    rows = _q('SELECT teacher_id FROM timetable WHERE id=?', (eid_unassigned,))
    assert rows[0]['teacher_id'] == db_fx['teacher']
    assert any('المحاضر' in w for w in warnings), warnings
    conn.close()


def test_service_updating_teacher_to_none_removes_assignment(db_fx):
    conn, svc = _svc(db_fx)
    eid = svc.create_entry('السبت', 2, 'A', db_fx['course'], db_fx['teacher'],
                           db_fx['room'], db_fx['computers'])
    assert _q('SELECT teacher_id FROM timetable WHERE id=?', (eid,))[0]['teacher_id']
    svc.update_entry(eid, 'السبت', 2, 'A', db_fx['course'], None,
                     db_fx['room'])
    rows = _q('SELECT teacher_id FROM timetable WHERE id=?', (eid,))
    assert rows[0]['teacher_id'] is None
    assert svc.get_last_conflict_warnings() == []
    conn.close()


# ────────────── API layer ──────────────

def test_api_create_without_teacher_succeeds(client, db_fx):
    r = client.post('/api/timetable/entries',
                    json=_payload(db_fx, teacher_id=''))
    assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))
    entry_id = r.get_json()['data']['id']
    rows = _q('SELECT teacher_id FROM timetable WHERE id=?', (entry_id,))
    assert rows[0]['teacher_id'] is None


def test_api_update_assigns_teacher(client, db_fx):
    r = client.post('/api/timetable/entries',
                    json=_payload(db_fx, teacher_id=''))
    entry_id = r.get_json()['data']['id']

    r = client.put(f'/api/timetable/entries/{entry_id}',
                   json=_payload(db_fx, teacher_id=db_fx['teacher']))
    assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
    rows = _q('SELECT teacher_id FROM timetable WHERE id=?', (entry_id,))
    assert rows[0]['teacher_id'] == db_fx['teacher']


# ────────────── HTML form layer ──────────────

def test_html_form_create_without_teacher_succeeds(client, db_fx):
    r = client.post('/timetable/create', data={
        'day': 'الأحد',
        'semester': '2',
        'section': 'A',
        'course_id': db_fx['course'],
        'room_id': db_fx['room'],
        'department_id': db_fx['computers'],
        'start_time': '10:00',
        'end_time': '11:00',
        '_csrf_token': 't',
    })
    assert r.status_code == 302, (r.status_code, r.get_data(as_text=True))
    rows = _q('SELECT teacher_id FROM timetable WHERE department_id=?',
              (db_fx['computers'],))
    assert rows and rows[0]['teacher_id'] is None