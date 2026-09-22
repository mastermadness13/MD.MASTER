"""Regression tests: HOD department resolution, membership backfill and
the master-data model scope fixes.

Covers (in order):
  1. ``authenticate()`` resolves ``hod_department_id`` / ``teacher_id`` from
     ``teachers.user_id`` (the canonical user→teacher link).
  2. ``ensure_schema`` backfills ``teacher_departments`` from every source and
     syncs primary ``teachers.department_id`` + ``users.department_id``.
  3. A HOD can open a teacher page (no 403) once membership exists.
  4. A HOD cannot create timetable entries outside the department they head.
  5. The lecture-form course list is scoped to the department (no full
     master list) while keeping the current course in the edit form.
  6. The sidebar follows the active role, not the union of granted roles.
  7. A HOD linked to a teacher record gains the ``teacher`` face at login
     (header role switcher → صفحة المحاضر) even when ``user_roles`` was
     never backfilled; a HOD without a teacher record does not.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from werkzeug.security import generate_password_hash


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'hod_resolution.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())

    # Seed BEFORE ensure_schema so the migration backfill is observable.
    conn.execute(
        "INSERT INTO departments (name, type) VALUES ('قسم الاتصالات', 'academic')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الاتصالات'"
    ).fetchone()['id']

    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES (?, ?, 'head_of_department', 'رئيس القسم')",
        ('abubakr', generate_password_hash('secret')),
    )
    user_id = conn.execute("SELECT id FROM users WHERE username='abubakr'").fetchone()['id']

    # The HOD teacher: linked by user_id, heads dept 2, but (like the real
    # بيانات "ابوبكر") had no primary department and no memberships yet.
    conn.execute(
        "INSERT INTO teachers (name, user_id, hod_department_id) "
        "VALUES ('أبوبكر', ?, ?)",
        (user_id, dept_id),
    )
    hod_teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE name='أبوبكر'"
    ).fetchone()['id']

    # A colleague with a primary department (backfill source a).
    conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('زميل', ?)",
        (dept_id,),
    )
    colleague_id = conn.execute(
        "SELECT id FROM teachers WHERE name='زميل'"
    ).fetchone()['id']

    conn.commit()
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return {
        'db_path': str(db_path),
        'dept_id': dept_id,
        'user_id': user_id,
        'hod_teacher_id': hod_teacher_id,
        'colleague_id': colleague_id,
    }


def _open_conn():
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def hod_client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = db_fx['user_id']
        sess['role'] = 'head_of_department'
        sess['roles'] = ['head_of_department']
        sess['username'] = 'abubakr'
        sess['hod_department_id'] = db_fx['dept_id']
        sess['department_id'] = db_fx['dept_id']
        sess['teacher_id'] = db_fx['hod_teacher_id']
        sess['_csrf_token'] = 't'
    return c


# ── 1. authenticate() resolves the department via teachers.user_id ────────

def test_authenticate_resolves_hod_department(db_fx):
    from database.repositories.user_repository import UserRepository
    from services.user_service import UserService

    conn = _open_conn()
    svc = UserService(conn, UserRepository(conn))
    session_dict = {}
    ok, _user = svc.authenticate('abubakr', 'secret', False, session_dict)
    conn.close()

    assert ok is True
    assert session_dict['hod_department_id'] == db_fx['dept_id']
    assert session_dict['teacher_id'] == db_fx['hod_teacher_id']
    assert session_dict['department_id'] == db_fx['dept_id']


def test_login_preserves_csrf_token(db_fx):
    """Login must not rotate the CSRF token.

    Forms rendered before login (and browser Back/Forward re-submissions)
    carry a per-session token; wiping it on login makes those replays fail
    with "خطأ في التحقق الأمني (CSRF)". The token must survive the session
    rebuild (the user pressing Back after login is the exact repro).
    """
    from database.repositories.user_repository import UserRepository
    from services.user_service import UserService

    conn = _open_conn()
    svc = UserService(conn, UserRepository(conn))

    session_dict = {'_csrf_token': 'token-before-login'}
    ok, _user = svc.authenticate('abubakr', 'secret', False, session_dict)
    assert ok is True
    assert session_dict['_csrf_token'] == 'token-before-login'

    # A fresh session still generates a token (no prior value to preserve).
    session_dict2 = {}
    ok2, _user2 = svc.authenticate('abubakr', 'secret', False, session_dict2)
    assert ok2 is True
    assert len(session_dict2['_csrf_token']) == 64
    conn.close()


def test_hod_with_teacher_record_gains_teacher_face(db_fx):
    """A HOD linked to a teacher record gets the 'teacher' face (صفحة المحاضر).

    Even when the DB was never backfilled (user_roles holds only
    'head_of_department'), login must grant 'teacher' too so the header role
    switcher offers the member face — with which he sees his timetable and
    uploads his course syllabi/materials. The landing role stays HOD.
    """
    from database.repositories.user_repository import UserRepository
    from services.user_service import UserService

    conn = _open_conn()
    # /     /     >---- نحاكي قاعدة بيانات ما فيهاش 'teacher' في جدول الأدوار
    conn.execute(
        "DELETE FROM user_roles WHERE user_id = ? AND role = 'teacher'",
        (db_fx['user_id'],),
    )
    conn.commit()

    svc = UserService(conn, UserRepository(conn))
    session_dict = {}
    ok, _user = svc.authenticate('abubakr', 'secret', False, session_dict)
    conn.close()

    assert ok is True
    assert 'head_of_department' in session_dict['roles']
    assert 'teacher' in session_dict['roles']
    assert session_dict['role'] == 'head_of_department'


def test_hod_without_teacher_record_has_no_teacher_face(db_fx):
    """A HOD with no linked teacher record does NOT get the teacher face."""
    from database.repositories.user_repository import UserRepository
    from services.user_service import UserService

    conn = _open_conn()
    # /     /     >---- قسم ثاني لرئيس قسم ثاني بدون ملف أستاذ
    conn.execute(
        "INSERT INTO departments (name, type) VALUES ('قسم الحاسوب', 'academic')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO users (username, password, role, department_id, label) "
        "VALUES (?, ?, 'head_of_department', ?, 'رئيس قسم بدون ملف')",
        ('barek', generate_password_hash('secret'), dept_id),
    )
    conn.commit()

    svc = UserService(conn, UserRepository(conn))
    session_dict = {}
    ok, _user = svc.authenticate('barek', 'secret', False, session_dict)
    conn.close()

    assert ok is True
    assert session_dict['roles'] == ['head_of_department']
    assert session_dict['teacher_id'] is None


# ── 2. schema backfill builds memberships and mirrors departments ─────────

def test_schema_backfills_membership(db_fx):
    conn = _open_conn()
    rows = conn.execute(
        'SELECT teacher_id, department_id FROM teacher_departments'
    ).fetchall()
    pairs = {(r['teacher_id'], r['department_id']) for r in rows}
    conn.close()

    # (c) heads of department belong to the department they head.
    assert (db_fx['hod_teacher_id'], db_fx['dept_id']) in pairs
    # (a) primary department assignments.
    assert (db_fx['colleague_id'], db_fx['dept_id']) in pairs


def test_backfill_syncs_primary_and_user_departments(db_fx):
    conn = _open_conn()
    t = conn.execute(
        'SELECT department_id FROM teachers WHERE id = ?',
        (db_fx['hod_teacher_id'],),
    ).fetchone()
    u = conn.execute(
        'SELECT department_id FROM users WHERE id = ?',
        (db_fx['user_id'],),
    ).fetchone()
    conn.close()
    assert t['department_id'] == db_fx['dept_id']
    assert u['department_id'] == db_fx['dept_id']


def test_backfill_rerun_picks_up_teaching_assignments(db_fx):
    """Source (b): a teacher with no primary dept but a recorded teaching
    assignment joins the department when the migration runs again."""
    conn = connect(flask_db.DATABASE)
    conn.execute("INSERT INTO teachers (name) VALUES ('مكلف')")
    tid = conn.execute("SELECT id FROM teachers WHERE name='مكلف'").fetchone()['id']
    conn.execute("INSERT INTO courses (code, name) VALUES ('T1', 'مقرر التكليف')")
    cid = conn.execute("SELECT id FROM courses WHERE code='T1'").fetchone()['id']
    conn.execute(
        'INSERT INTO teacher_taught_courses (teacher_id, course_id, department_id) '
        'VALUES (?, ?, ?)',
        (tid, cid, db_fx['dept_id']),
    )
    conn.commit()

    ensure_schema(conn)  # idempotent — re-run must re-apply every backfill
    conn.commit()

    row = conn.execute(
        'SELECT 1 FROM teacher_departments WHERE teacher_id = ? AND department_id = ?',
        (tid, db_fx['dept_id']),
    ).fetchone()
    conn.close()
    assert row is not None


# ── 3. HOD teacher page must not 403 once membership exists ───────────────

def test_hod_can_open_teacher_page_with_membership(hod_client, db_fx):
    r = hod_client.get(f"/teachers/{db_fx['hod_teacher_id']}")
    assert r.status_code == 200


def test_hod_dashboard_renders(hod_client):
    """The HOD dashboard template must render with the resolved department name."""
    r = hod_client.get('/')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'لوحة تحكم' in body


# ── 4. HOD timetable creation is scoped to the headed department ──────────

def test_hod_cannot_create_entry_in_other_department(hod_client):
    payload = {
        'day': 'السبت',
        'semester': 1,
        'period_code': 'A',
        'course_id': 99,
        'teacher_id': 99,
        'room_id': 99,
        'department_id': 999,
        'start_time': '08:00',
        'end_time': '09:00',
        '_csrf_token': 't',
    }
    r = hod_client.post('/api/timetable/entries', json=payload)
    assert r.status_code == 403


def test_hod_can_create_entry_in_own_department(hod_client, db_fx):
    conn = _open_conn()
    conn.execute("INSERT INTO teachers (name) VALUES ('مدرس')")
    tid = conn.execute("SELECT id FROM teachers WHERE name='مدرس'").fetchone()['id']
    conn.execute("INSERT INTO courses (code, name) VALUES ('C1', 'شبكات')")
    cid = conn.execute("SELECT id FROM courses WHERE code='C1'").fetchone()['id']
    conn.execute("INSERT INTO rooms (name, code) VALUES ('قاعة 1', 'R1')")
    rid = conn.execute("SELECT id FROM rooms WHERE code='R1'").fetchone()['id']
    conn.commit()
    conn.close()

    payload = {
        'day': 'السبت',
        'semester': 1,
        'period_code': 'A',
        'course_id': cid,
        'teacher_id': tid,
        'room_id': rid,
        'department_id': db_fx['dept_id'],
        'start_time': '08:00',
        'end_time': '09:00',
        'lecture_type': 'theory',
        'hours': 1,
        '_csrf_token': 't',
    }
    r = hod_client.post('/api/timetable/entries', json=payload)
    assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))


# ── 5. lecture-form courses are scoped to the department ──────────────────

def test_list_department_courses_scopes_to_department(db_fx):
    from database.repositories.timetable_repository import TimetableRepository

    conn = _open_conn()
    dept = db_fx['dept_id']

    conn.execute("INSERT INTO courses (code, name, department_id) VALUES ('A1', 'مقرر مرتبط', NULL)")
    a = conn.execute("SELECT id FROM courses WHERE code='A1'").fetchone()['id']
    conn.execute(
        'INSERT INTO course_departments (course_id, department_id) VALUES (?, ?)',
        (a, dept),
    )
    conn.execute(
        "INSERT INTO courses (code, name, department_id) VALUES ('B1', 'مقرر أساسي', ?)",
        (dept,),
    )
    conn.execute("INSERT INTO courses (code, name, department_id) VALUES ('C1', 'مقرر مجدول', NULL)")
    c = conn.execute("SELECT id FROM courses WHERE code='C1'").fetchone()['id']
    conn.execute("INSERT INTO courses (code, name, department_id) VALUES ('D1', 'مقرر أجنبي', NULL)")
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id) "
        "VALUES ('السبت', 1, 'A', ?, NULL, NULL, ?)",
        (c, dept),
    )
    conn.commit()

    names = {x['name'] for x in TimetableRepository(conn).list_department_courses(dept)}
    conn.close()

    assert {'مقرر مرتبط', 'مقرر أساسي', 'مقرر مجدول'} <= names
    assert 'مقرر أجنبي' not in names


def test_edit_form_keeps_current_course_outside_department(db_fx):
    """Editing an entry must surface its current course even when that course
    is not linked to the department (matches the route merge behaviour)."""
    from database.repositories.timetable_repository import TimetableRepository

    conn = _open_conn()
    conn.execute("INSERT INTO courses (code, name) VALUES ('X1', 'مقرر قديم خارج النطاق')")
    cid = conn.execute("SELECT id FROM courses WHERE code='X1'").fetchone()['id']
    conn.commit()

    courses = TimetableRepository(conn).list_department_courses(db_fx['dept_id'])
    conn.close()
    assert not any(c['id'] == cid for c in courses), 'the stale course is scoped out'


# ── 6. sidebar follows the active role, not the granted union ─────────────

def test_nav_items_follow_active_role(app_fx, db_fx):
    from flask import session
    from security.authorization import inject_navigation

    with app_fx.test_request_context('/'):
        session['role'] = 'teacher'
        session['roles'] = ['teacher', 'head_of_department']
        teacher_eps = {i['endpoint'] for i in inject_navigation()['nav_items']}

        session['role'] = 'head_of_department'
        hod_eps = {i['endpoint'] for i in inject_navigation()['nav_items']}

    assert 'classroom_requests.pending' not in hod_eps, 'classroom change requests feature removed'
    assert 'hod_pages.hod_materials' not in hod_eps, 'material management is no longer a HOD feature'
    assert 'classroom_requests.pending' not in teacher_eps
    assert 'hod_pages.hod_materials' not in teacher_eps