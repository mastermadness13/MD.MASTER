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


# ────────────── placeholder expiry ──────────────
#
# محاضرة بلا أستاذ مؤقتة: يختارها القسم عند خلو_section من محاضر للمادة،
# فتبقى أياماً ثم تختفي من كل الشاشات إن لم يُعيَّن لها محاضر. الفلترة وقت
# الطلب فقط — لا حذف ولا جدولة دورية.

def _place_holder(db_fx, teacher=None):
    """Create one entry and return (conn, repo, entry_id) — all still open."""
    conn = connect(db_fx['db_path'])
    repo = TimetableRepository(conn)
    svc = timetable_service.TimetableService(conn, repo)
    eid = svc.create_entry('السبت', 2, 'A', db_fx['course'], teacher,
                           db_fx['room'], db_fx['computers'])
    return conn, repo, eid


def _shift_expiry(conn, eid, days):
    """Move a placeholder's stamp by `days` (positive = further into the future).

    Runs on the SAME connection on purpose: writing through a second one
    leaves this one holding a read snapshot, so it would keep seeing the old
    value and the assertion would be testing nothing.
    """
    conn.execute("UPDATE timetable SET expires_at=datetime('now', ?) WHERE id=?",
                 (f'{days:+d} days', eid))
    conn.commit()


def _expiry_of(conn, eid):
    return conn.execute('SELECT expires_at FROM timetable WHERE id=?',
                        (eid,)).fetchone()['expires_at']


def test_placeholder_gets_expiry_but_real_lecture_does_not(db_fx):
    conn, repo, ph = _place_holder(db_fx, None)
    conn.close()
    conn, repo, real = _place_holder(db_fx, db_fx['teacher'])
    conn.close()

    assert _expiry_of(connect(db_fx['db_path']), ph)
    assert _expiry_of(connect(db_fx['db_path']), real) is None


def test_placeholder_visible_within_seven_days_on_all_read_paths(db_fx):
    conn, repo, eid = _place_holder(db_fx, None)
    _shift_expiry(conn, eid, 1)  # باقي يوم واحد من نافذة السبعة

    ids = [e['id'] for e in repo.get_department_view_data(db_fx['computers'], 2, None)]
    assert eid in ids, 'grid/API/print path'

    import services.public_service as public_service
    pub = {e['id'] for e in public_service.get_active_entries(conn)}
    assert eid in pub, 'public site path'
    conn.close()


def test_expired_placeholder_hidden_but_row_not_deleted(db_fx):
    conn, repo, eid = _place_holder(db_fx, None)
    _shift_expiry(conn, eid, -1)

    ids = [e['id'] for e in repo.get_department_view_data(db_fx['computers'], 2, None)]
    assert eid not in ids
    # /     /     >---- الفلترة وقت العرض فقط: الصف يبقى في القاعدة
    assert conn.execute('SELECT COUNT(*) c FROM timetable WHERE id=?',
                        (eid,)).fetchone()['c'] == 1
    conn.close()


def test_assigning_teacher_cancels_expiry_so_lecture_never_disappears(db_fx):
    conn, repo, eid = _place_holder(db_fx, None)
    repo.update(eid, {'day': 'السبت', 'semester': 2, 'period': 'A',
                      'course_id': db_fx['course'], 'teacher_id': db_fx['teacher'],
                      'room_id': db_fx['room'], 'start_time': '08:00',
                      'end_time': '09:00', 'lecture_type': 'theory', 'hours': 1})
    assert _expiry_of(conn, eid) is None

    # /     /     >---- لو خُتم времен من قبله يبقى ظاهراً: له محاضر
    _shift_expiry(conn, eid, -30)
    ids = [e['id'] for e in repo.get_department_view_data(db_fx['computers'], 2, None)]
    assert eid in ids
    conn.close()


def test_clearing_teacher_re_arms_expiry(db_fx):
    conn, repo, eid = _place_holder(db_fx, db_fx['teacher'])
    repo.update(eid, {'day': 'السبت', 'semester': 2, 'period': 'A',
                      'course_id': db_fx['course'], 'teacher_id': None,
                      'room_id': db_fx['room'], 'start_time': '08:00',
                      'end_time': '09:00', 'lecture_type': 'theory', 'hours': 1})
    # /     /     >---- تفريغ المحاضر يعيد العدّاد، وإلا بقيت المحاضرة بلا
    # /     /     >---- مدرس في الجدول إلى الأبد
    assert _expiry_of(conn, eid)
    conn.close()


def test_expired_placeholder_does_not_hold_its_room(db_fx):
    """A lecture nobody can see must not block a room they are trying to book.

    The row survives in the database, so without this filter the department
    would get a conflict warning pointing at a lecture that is not on screen.
    """
    conn, repo, eid = _place_holder(db_fx, None)
    room, day, period = db_fx['room'], 'السبت', 'A'

    assert repo.is_room_conflicted(room, day, period) is True
    assert repo.is_room_available(room, day, period) is False

    _shift_expiry(conn, eid, -1)
    assert repo.is_room_conflicted(room, day, period) is False
    assert repo.is_room_available(room, day, period) is True

    # /     /     >---- الصف ما زال موجوداً، فقط لا يحجز شيئاً
    assert conn.execute('SELECT COUNT(*) c FROM timetable WHERE id=?',
                        (eid,)).fetchone()['c'] == 1
    conn.close()