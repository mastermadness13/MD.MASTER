"""Phase 5 — H1 path-traversal on uploads, M1 public draft-exam leak, M9 PII.

H1: /uploads/<path:filename> re-checks the folder AND rejects traversal before
    the ownership gate.
M1: /public/api/exam-schedule must expose only published/completed exams while
    the internal schedule builder keeps drafts.
M9: static public teachers.json carries no PII fields.
"""

import json
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema
from services import exam_service


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'phase5.db'
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
        "('t1', 'x', 'teacher', 'أ. أحمد')")
    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES "
        "('قسم الحاسوب', 8, 8, 0, 1, 'academic')")
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.execute(
        "INSERT OR IGNORE INTO courses (code, name, year, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('CS101', 'مقرر منشور', 1, 2, 0, 2)")
    conn.execute(
        "INSERT OR IGNORE INTO courses (code, name, year, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('CS202', 'مقرر مسودة', 2, 2, 0, 2)")
    conn.execute("INSERT OR IGNORE INTO rooms (name) VALUES ('قاعة 101')")
    conn.commit()
    conn.close()
    return db_path


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows


def _seed_results(db_fx):
    dept_id = _q("SELECT id FROM departments WHERE name='قسم الحاسوب'")[0]['id']
    pub = _q("SELECT id FROM courses WHERE code='CS101'")[0]['id']
    draft = _q("SELECT id FROM courses WHERE code='CS202'")[0]['id']
    room_id = _q("SELECT id FROM rooms WHERE name='قاعة 101'")[0]['id']
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute(
        '''INSERT INTO exam_schedule (course_id, department_id, exam_date, start_time, end_time, room_id, semester, status)
           VALUES (?, ?, '2026-06-10', '08:30', '10:30', ?, 2, 'published')''',
        (pub, dept_id, room_id))
    conn.execute(
        '''INSERT INTO exam_schedule (course_id, department_id, exam_date, start_time, end_time, room_id, semester, status)
           VALUES (?, ?, '2026-06-11', '08:30', '10:30', ?, 2, 'draft')''',
        (draft, dept_id, room_id))
    conn.commit()
    conn.close()


def _teacher_client(app_fx, db_fx):
    uid = _q("SELECT id FROM users WHERE username='t1'")[0]['id']
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = 'teacher'
        sess['username'] = 't1'
        sess['_csrf_token'] = 't'
    return c


# ── H1: uploads path traversal / IDOR ───────────────────────────────────────


def _staff_client(app_fx, db_fx, username='office_manager', role='faculty_affairs'):
    """Client for a role that actually holds ``uploads.serve``.

    A ``teacher`` session is redirected away by ``@permission_required`` before
    the traversal check runs, so traversal must be exercised with a role that
    can reach the view.
    """
    uid = _q("SELECT id FROM users WHERE username=?", (username,))[0]['id']
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = role
        sess['username'] = username
        sess['_csrf_token'] = 't'
    return c


def test_uploads_rejects_traversal(app_fx, db_fx, tmp_path, monkeypatch):
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    c = _staff_client(app_fx, db_fx)
    for evil in [
        '/uploads/../../etc/passwd',
        '/uploads/teacher_1/../../../secret.db',
        '/uploads/photos/../../teacher_2/file.pdf',
        '/uploads/photos\\..\\..\\secret.db',
    ]:
        r = c.get(evil)
        assert r.status_code == 403, f'{evil} must be rejected, got {r.status_code}'


def test_uploads_denies_role_without_serve_permission(app_fx, db_fx, tmp_path, monkeypatch):
    """``teacher`` does not hold uploads.serve, so the endpoint must not serve."""
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    (tmp_path / 'photos').mkdir()
    (tmp_path / 'photos' / 'a.png').write_bytes(b'img')
    c = _teacher_client(app_fx, db_fx)
    assert c.get('/uploads/photos/a.png').status_code != 200


def test_uploads_blocks_other_teachers_folder(app_fx, db_fx, tmp_path, monkeypatch):
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    (tmp_path / 'teacher_999').mkdir()
    (tmp_path / 'teacher_999' / 'secret.pdf').write_bytes(b'secret')
    c = _staff_client(app_fx, db_fx)
    r = c.get('/uploads/teacher_999/secret.pdf')
    assert r.status_code == 403, 'cross-teacher file must be denied'


def test_uploads_allows_own_folder(app_fx, db_fx, tmp_path, monkeypatch):
    """A staff account may read the folder of a teacher linked to it, plus the
    shared photos/ folder (both are the documented allowances)."""
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute(
        "INSERT INTO teachers (user_id, name) "
        "SELECT id, 'أ. أحمد' FROM users WHERE username='office_manager'"
    )
    conn.commit()
    conn.close()
    tid = _q(
        "SELECT t.id FROM teachers t JOIN users u ON u.id = t.user_id "
        "WHERE u.username='office_manager'"
    )[0]['id']

    (tmp_path / f'teacher_{tid}').mkdir(exist_ok=True)
    (tmp_path / f'teacher_{tid}' / 'y.pdf').write_bytes(b'%PDF')
    (tmp_path / 'photos').mkdir(exist_ok=True)
    (tmp_path / 'photos' / 'a.png').write_bytes(b'img')

    c = _staff_client(app_fx, db_fx)
    assert c.get(f'/uploads/teacher_{tid}/y.pdf').status_code == 200
    assert c.get('/uploads/photos/a.png').status_code == 200


def test_uploads_shared_photos_still_readable(app_fx, db_fx, tmp_path, monkeypatch):
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(tmp_path))
    (tmp_path / 'photos').mkdir()
    (tmp_path / 'photos' / 'a.png').write_bytes(b'img')
    uid = _q("SELECT id FROM users WHERE username='office_manager'")[0]['id']
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = 'faculty_affairs'
        sess['username'] = 'office_manager'
        sess['_csrf_token'] = 't'
    assert c.get('/uploads/photos/a.png').status_code == 200


# ── M1: public exam schedule must exclude drafts ────────────────────────────


def test_public_exam_schedule_hides_drafts(app_fx, db_fx):
    _seed_results(db_fx)
    r = app_fx.test_client().get('/public/api/exam-schedule')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'مقرر منشور' in body or 'CS101' in body
    assert 'مقرر مسودة' not in body, 'draft exam leaked to public API'
    assert 'CS202' not in body, 'draft exam code leaked to public API'


def test_internal_builder_keeps_drafts(db_fx):
    _seed_results(db_fx)
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    all_data = exam_service.build_dept_exam_data(conn)
    pub_data = exam_service.build_dept_exam_data(conn, published_only=True)
    conn.close()
    assert 'مقرر مسودة' in json.dumps(all_data, ensure_ascii=False)
    assert 'مقرر مسودة' not in json.dumps(pub_data, ensure_ascii=False)
    assert 'مقرر منشور' in json.dumps(pub_data, ensure_ascii=False)


# ── M9: public teachers.json has no PII ─────────────────────────────────────


@pytest.mark.parametrize('path', [
    'static/public/data/teachers.json',
])
def test_public_teachers_json_has_no_pii(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    forbidden = {'email', 'phone', 'academicNumber', 'nationalId', 'userId'}
    present = set()
    for t in data['teachers']:
        present |= forbidden.intersection(t.keys())
    assert not present, f'{path} exposes PII keys: {present}'
    assert data['teachers'], 'expected non-empty teachers list'