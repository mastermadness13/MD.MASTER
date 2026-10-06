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
    conn.execute("INSERT OR IGNORE INTO users (username,password,role,label) VALUES ('office_manager','x','faculty_affairs','مدير مكتب أعضاء هيئة التدريس')")
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
        s['role'] = 'faculty_affairs'
        s['username'] = 'office_manager'
        s['department_id'] = None
        s['_csrf_token'] = 't'
    return c, db_path, tid


def test_save_position_with_date_writes_to_admin_assignments(setup):
    c, db_path, tid = setup
    # Save a position, assignment date, and assigned hours.
    r = _post(c, f'/teachers/edit/{tid}', {
        'name': 'مدرس', 'position': 'رئيس قسم', 'assignment_date': '2026-09-01',
        'admin_hours': '5',
        'email': '', 'phone': '', 'academic_number': '', 'qualification_id': '',
        'rank_id': '', 'classification_id': '', 'national_id': '', 'contract_date': '',
        'tasks': '', 'specialization': '', 'first_lecture_date': '', 'work_start_date': '',
        'general_notes': '',
    })
    assert r.status_code == 200
    rows = _q(db_path, 'SELECT task_name, assignment_date, manual_hours, academic_year, semester FROM faculty_admin_assignments WHERE teacher_id=?', (tid,))
    assert rows, 'expected an admin assignment to be saved'
    assert rows[0]['task_name'] == 'رئيس قسم'
    assert rows[0]['assignment_date'] == '2026-09-01'
    assert rows[0]['manual_hours'] == 5
    edit_html = c.get(f'/teachers/edit/{tid}').get_data(as_text=True)
    hours_field = edit_html[edit_html.index('id="adminHoursInput"'):]
    assert 'value="5"' in hours_field[:180]


def test_create_saves_hours_for_any_administrative_assignment(setup):
    c, db_path, _tid = setup
    response = _post(c, '/teachers/create', {
        'name': 'عضو جديد',
        'username': 'newteacher',
        'password': 'Office123',
        'position': 'مساعد إداري',
        'assignment_date': '2026-09-01',
        'admin_hours': '4',
        'email': '',
        'phone': '',
        'academic_number': '',
        'qualification_id': '',
        'rank_id': '',
        'classification_id': '',
        'national_id': '',
        'contract_date': '',
        'tasks': '',
        'specialization': '',
        'first_lecture_date': '',
        'work_start_date': '',
        'general_notes': '',
    })
    assert response.status_code == 200
    new_teacher_id = _q(
        db_path,
        'SELECT id FROM teachers WHERE name = ?',
        ('عضو جديد',),
    )[0]['id']
    rows = _q(
        db_path,
        'SELECT task_name, assignment_date, manual_hours '
        'FROM faculty_admin_assignments WHERE teacher_id = ?',
        (new_teacher_id,),
    )
    assert rows == [{
        'task_name': 'مساعد إداري',
        'assignment_date': '2026-09-01',
        'manual_hours': 4,
    }]


def test_edit_form_renders_one_hours_field_next_to_assignment_date(setup):
    c, _db_path, tid = setup
    response = c.get(f'/teachers/edit/{tid}')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('id="adminHoursInput"') == 1
    assert html.index('name="assignment_date"') < html.index('id="adminHoursInput"')


def test_research_hours_are_optional_in_teacher_edit_form(setup):
    c, _db_path, tid = setup
    response = c.get(f'/teachers/edit/{tid}')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    research_field = html[html.index('name="research_hours[]"'):]
    assert 'min="0"' in research_field[:250]
    assert 'required' not in research_field[:250]


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
