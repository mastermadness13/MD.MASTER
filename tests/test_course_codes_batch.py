"""Batch course-codes editor (/courses/codes).

Admin can re-write course codes inline (one input per course) or by pasting a
list of ``code, name`` lines. Validation rejects blank codes, duplicates within
the batch, and codes already used by courses that are not part of the change.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'codes.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير مكتب أعضاء هيئة التدريس')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الاتصالات', 8, 7, 0, 1, 'academic')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 8, 7, 0, 1, 'academic')"
    )
    ids = {r['name']: r['id'] for r in conn.execute(
        "SELECT id, name FROM departments").fetchall()}
    conn.execute(
        "INSERT INTO courses (code, name, department_id, department, year) "
        "VALUES ('OLD1', 'شبكات', ?, 'قسم الاتصالات', 2), "
        "('OLD2', 'برمجة', ?, 'قسم الحاسوب', 1), "
        "('OLD3', 'رياضيات', ?, 'قسم الاتصالات', 1)",
        (ids['قسم الاتصالات'], ids['قسم الحاسوب'], ids['قسم الاتصالات']),
    )
    for cid in conn.execute("SELECT id FROM courses").fetchall():
        conn.execute(
            "INSERT INTO course_departments (course_id, department_id, semester) VALUES (?, ?, 1)",
            (cid[0], ids['قسم الاتصالات'] if cid[0] != 2 else ids['قسم الحاسوب']),
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'faculty_affairs'
        sess['username'] = 'office_manager'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def test_codes_page_renders(client):
    r = client.get('/courses/codes')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'أكواد المقررات' in body
    assert 'name="code_1"' in body
    assert 'name="bulk_text"' in body
    assert 'OLD1' in body


def test_codes_page_department_filter(client):
    dept_comm = _q("SELECT id FROM departments WHERE name = 'قسم الاتصالات'")[0]['id']
    r = client.get(f'/courses/codes?dept={dept_comm}')
    body = r.get_data(as_text=True)
    assert 'شبكات' in body
    assert 'برمجة' not in body


def test_inline_update_sets_codes(client):
    r = client.post('/courses/codes', data={
        '_csrf_token': 't',
        'code_1': 'NET101',
        'code_2': 'OLD2',
    })
    assert r.status_code == 302
    codes = _q('SELECT code FROM courses ORDER BY id')
    assert [c['code'] for c in codes] == ['NET101', 'OLD2', 'OLD3']


def test_inline_update_rejects_duplicate(client):
    r = client.post('/courses/codes', data={
        '_csrf_token': 't',
        'code_1': 'SAME',
        'code_2': 'SAME',
    })
    assert r.status_code == 302
    codes = _q('SELECT code FROM courses ORDER BY id')
    assert [c['code'] for c in codes] == ['OLD1', 'OLD2', 'OLD3']


def test_inline_update_rejects_conflict_outside_batch(client):
    # OLD3 is not part of the change; OLD1 cannot take its code.
    r = client.post('/courses/codes', data={
        '_csrf_token': 't',
        'code_1': 'OLD3',
        'code_2': 'OLD2',
    })
    assert r.status_code == 302
    codes = _q('SELECT code FROM courses ORDER BY id')
    assert [c['code'] for c in codes] == ['OLD1', 'OLD2', 'OLD3']


def test_paste_mode_matches_by_name(client):
    r = client.post('/courses/codes', data={
        '_csrf_token': 't',
        'bulk_text': 'CS101 | برمجة\nMATH200\tرياضيات',
    })
    assert r.status_code == 302
    codes = _q('SELECT code, name FROM courses ORDER BY id')
    assert [c['code'] for c in codes] == ['OLD1', 'CS101', 'MATH200']


def test_paste_unmatched_name_reported(client):
    r = client.post('/courses/codes', data={
        '_csrf_token': 't',
        'bulk_text': 'XX1 ، مادة غير موجودة',
    })
    assert r.status_code == 302
    codes = _q('SELECT code FROM courses ORDER BY id')
    assert [c['code'] for c in codes] == ['OLD1', 'OLD2', 'OLD3']


def test_hod_cannot_open_codes_page(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'head_of_department'
        sess['roles'] = ['head_of_department']
        sess['username'] = 'hod'
        sess['hod_department_id'] = None
        sess['_csrf_token'] = 't'
    r = c.get('/courses/codes')
    assert r.status_code == 302, 'HOD lacks courses.manage and must be turned away'
    assert r.headers['Location'] != '/courses/codes'


def test_codes_tab_embedded_in_courses_page(client):
    r = client.get('/courses')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'viewCodes' in body, 'embedded codes editor container renders'
    assert 'tabCodesBtn' in body, 'codes tab button renders'
    assert 'name="code_1"' in body, 'inline code input renders'
    assert 'name="embed" value="1"' in body, 'embedded-editor forms carry the embed marker'


def test_codes_embed_post_redirects_back(client):
    r = client.post('/courses/codes', data={
        '_csrf_token': 't',
        'embed': '1',
        'code_1': 'NET101',
        'code_2': 'OLD2',
    })
    assert r.status_code == 302
    assert 'view=codes' in r.headers['Location'], \
        'embedded submit must return to the main courses page codes tab'
    codes = _q('SELECT code FROM courses ORDER BY id')
    assert [c['code'] for c in codes] == ['NET101', 'OLD2', 'OLD3']


def test_view_only_role_has_no_codes_tab(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'exam'
        sess['username'] = 'exam_user'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    r = c.get('/courses')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'viewCodes' not in body, 'codes editor is hidden for view-only roles'
    assert 'tabCodesBtn' not in body