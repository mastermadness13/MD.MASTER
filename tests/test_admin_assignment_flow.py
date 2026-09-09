"""Functional verification: saving a teacher position + assignment_date writes
to faculty_admin_assignments so it appears in the official form section 4."""

import sqlite3

import pytest

import flask_db
from database.connection import connect


def _mkdb(dirname):
    import pathlib
    from database.schema import ensure_schema
    p = pathlib.Path(dirname)
    p.mkdir(parents=True, exist_ok=True)
    db_path = p / 'func.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute("INSERT OR IGNORE INTO users (username,password,role,label) VALUES ('superadmin','x','super_admin','مدير')")
    conn.execute("INSERT OR IGNORE INTO departments (name,semesters,majors,hidden,has_sections,type) VALUES ('قسم',4,4,0,1,'academic')")
    conn.execute("INSERT INTO teachers (name, department_id) VALUES ('مدرس', (SELECT id FROM departments LIMIT 1))")
    conn.commit()
    conn.close()
    return str(db_path)


def _q(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def _post(client, url, data):
    data['_csrf_token'] = 't'
    data['department_ids[]'] = ''
    if data.get('position') == 'رئيس قسم' and 'hod_department_id' not in data:
        data['hod_department_id'] = '1'
    return client.post(url, data=data, follow_redirects=True)


@pytest.fixture
def setup(tmp_path, monkeypatch, app_fx):
    db_path = _mkdb(tmp_path / 'a')
    monkeypatch.setattr(flask_db, 'DATABASE', db_path)
    tid = _q(db_path, 'SELECT id FROM teachers LIMIT 1')[0]['id']
    c = app_fx.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 1
        s['role'] = 'super_admin'
        s['username'] = 'superadmin'
        s['department_id'] = None
        s['_csrf_token'] = 't'
    return c, db_path, tid


def test_save_position_with_date_writes_to_admin_assignments(setup):
    c, db_path, tid = setup
    # Save a position and an assignment_date
    r = _post(c, f'/teachers/edit/{tid}', {
        'name': 'مدرس', 'position': 'رئيس قسم', 'assignment_date': '2026-09-01',
        'email': '', 'phone': '', 'academic_number': '', 'qualification_id': '',
        'rank_id': '', 'classification_id': '', 'national_id': '', 'contract_date': '',
        'tasks': '', 'specialization': '', 'first_lecture_date': '', 'work_start_date': '',
        'general_notes': '',
    })
    assert r.status_code == 200
    rows = _q(db_path, 'SELECT task_name, assignment_date, academic_year, semester FROM faculty_admin_assignments WHERE teacher_id=?', (tid,))
    assert rows, 'expected an admin assignment to be saved'
    assert rows[0]['task_name'] == 'رئيس قسم'
    assert rows[0]['assignment_date'] == '2026-09-01'


def test_clearing_position_deletes_admin_assignment(setup):
    c, db_path, tid = setup
    _post(c, f'/teachers/edit/{tid}', {
        'name': 'مدرس', 'position': 'رئيس قسم', 'assignment_date': '2026-09-01',
        'email': '', 'phone': '', 'academic_number': '', 'qualification_id': '',
        'rank_id': '', 'classification_id': '', 'national_id': '', 'contract_date': '',
        'tasks': '', 'specialization': '', 'first_lecture_date': '', 'work_start_date': '',
        'general_notes': '',
    })
    assert _q(db_path, 'SELECT COUNT(*) c FROM faculty_admin_assignments WHERE teacher_id=?', (tid,))[0]['c'] == 1
    # Clear position
    _post(c, f'/teachers/edit/{tid}', {
        'name': 'مدرس', 'position': '', 'assignment_date': '',
        'email': '', 'phone': '', 'academic_number': '', 'qualification_id': '',
        'rank_id': '', 'classification_id': '', 'national_id': '', 'contract_date': '',
        'tasks': '', 'specialization': '', 'first_lecture_date': '', 'work_start_date': '',
        'general_notes': '',
    })
    assert _q(db_path, 'SELECT COUNT(*) c FROM faculty_admin_assignments WHERE teacher_id=?', (tid,))[0]['c'] == 0
