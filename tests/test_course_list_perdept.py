"""Per-department semester support on the courses management page.

The same course can sit in different semesters in different departments.
The Unified edit modal exposes an «الأقسام والفصول» section that lets you
toggle departments on/off and pick a semester per checked department.

`course_departments.semester` is the source of truth per department;
`courses.semester` is kept in sync with the primary (first checked) department.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'perdept.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير مكتب أعضاء هيئة التدريس')"
    )
    for name, semesters in [('قسم الاتصالات', 7), ('قسم الحاسوب', 7)]:
        conn.execute(
            "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
            "VALUES (?, ?, 7, 0, 1, 'academic')",
            (name, semesters),
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def dept_ids(db_fx):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    ids = {r['name']: r['id'] for r in
           conn.execute("SELECT id, name FROM departments").fetchall()}
    conn.close()
    return ids


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
    conn.commit()
    conn.close()
    return rows


def test_migrated_schema_has_semester_column(db_fx):
    cols = _q('PRAGMA table_info(course_departments)')
    sem = [c for c in cols if c['name'] == 'semester']
    assert sem, 'course_departments.semester column must exist after migration'


def _read_js(relpath):
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', relpath), encoding='utf-8') as fh:
        return fh.read()


def test_list_page_renders_per_dept_modal_and_payload(client):
    res = client.get('/courses')
    body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert 'الأقسام والفصول' in body, 'modal section header renders'
    assert 'COURSES_LIST_BOOT' in body, 'server-rendered data boot is exposed to the page'
    assert 'js/courses_list.js' in body, 'external page script is loaded'
    assert 'mDeptGrid' in body, 'dept grid container renders'
    # The modal logic lives in the external script bundle (static/js).
    js = _read_js('static/js/courses_list.js')
    assert 'renderModalDeptGrid' in js, 'modal dept-grid renderer is present'
    assert 'COURSE_DEPT_PLACEMENTS' in js, 'per-dept semester map is exposed to JS'
    assert 'mDeptGrid' in js, 'dept grid id referenced from JS'


def test_create_with_placements_sets_per_dept_semesters(client, dept_ids):
    comm = dept_ids['قسم الاتصالات']
    comp = dept_ids['قسم الحاسوب']
    placements = [
        {'department_id': comm, 'semester': 3},
        {'department_id': comp, 'semester': 5},
    ]
    data = {
        '_csrf_token': 't',
        'code': 'CMP101',
        'name': 'أنظمة الاتصالات والبرمجة',
        'total_hours': '3',
        'theoretical_hours': '2',
        'practical_hours': '1',
        'year': '2',
        'semester': '3',
        'department_ids': [str(comm), str(comp)],
        'dept_semester': ['3', '5'],
        'placements': __import__('json').dumps(placements),
    }
    r = client.post('/courses/create', data=data)
    assert r.status_code == 302

    cid = _q("SELECT id FROM courses WHERE code='CMP101'")[0]['id']
    rows = _q("SELECT department_id, semester FROM course_departments "
              "WHERE course_id=? ORDER BY department_id", (cid,))
    by_dept = {r['department_id']: r['semester'] for r in rows}
    assert by_dept == {comm: 3, comp: 5}, by_dept

    # global semester syncs to the primary (first checked) department
    c = _q("SELECT semester FROM courses WHERE id=?", (cid,))[0]
    assert c['semester'] == 3


def test_edit_with_placements_updates_and_resyncs_global(client, dept_ids):
    comm = dept_ids['قسم الاتصالات']
    comp = dept_ids['قسم الحاسوب']

    # seed a course shared by both departments
    cid = _q("SELECT id FROM courses WHERE code='CMP101'")[0]['id'] \
        if _q("SELECT id FROM courses WHERE code='CMP101'") else _seed_course(comm, comp)
    # place both depts
    _q("DELETE FROM course_departments WHERE course_id=?", (cid,))
    _q("INSERT INTO course_departments (course_id, department_id, semester) VALUES (?,?,?),(?,?,?)",
       (cid, comm, 2, cid, comp, 4))
    _q("UPDATE courses SET semester=2 WHERE id=?", (cid,))

    # edit to move primary (comm) -> 6, secondary (comp) -> 1
    placements = [
        {'department_id': comm, 'semester': 6},
        {'department_id': comp, 'semester': 1},
    ]
    data = {
        '_csrf_token': 't',
        'code': 'CMP101',
        'name': 'أنظمة الاتصالات والبرمجة',
        'total_hours': '3',
        'theoretical_hours': '2',
        'practical_hours': '1',
        'year': '2',
        'semester': '2',
        'department_ids': [str(comm), str(comp)],
        'dept_semester': ['6', '1'],
        'placements': __import__('json').dumps(placements),
    }
    r = client.post(f'/courses/edit/{cid}', data=data)
    assert r.status_code == 302

    rows = _q("SELECT department_id, semester FROM course_departments "
              "WHERE course_id=? ORDER BY department_id", (cid,))
    by_dept = {r['department_id']: r['semester'] for r in rows}
    assert by_dept == {comm: 6, comp: 1}, by_dept

    c = _q("SELECT semester FROM courses WHERE id=?", (cid,))[0]
    assert c['semester'] == 6, 'global semester follows the primary placement'


def test_moving_secondary_department_keeps_primary_global(client, dept_ids):
    """move_course_to_semester updates only the target department; the global
    semester only follows the primary department."""
    from services import course_service
    comm = dept_ids['قسم الاتصالات']
    comp = dept_ids['قسم الحاسوب']
    cid = _seed_course(comm, comp)
    _q("DELETE FROM course_departments WHERE course_id=?", (cid,))
    _q("INSERT INTO course_departments (course_id, department_id, semester) VALUES (?,?,?),(?,?,?)",
       (cid, comm, 3, cid, comp, 4))
    _q("UPDATE courses SET semester=3 WHERE id=?", (cid,))

    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    ok, _ = course_service.move_course_to_semester(conn, cid, comp, 2)
    conn.close()
    assert ok
    rows = _q("SELECT department_id, semester FROM course_departments "
              "WHERE course_id=? ORDER BY department_id", (cid,))
    by_dept = {r['department_id']: r['semester'] for r in rows}
    assert by_dept == {comm: 3, comp: 2}, by_dept
    c = _q("SELECT semester FROM courses WHERE id=?", (cid,))[0]
    assert c['semester'] == 3, 'primary dept unchanged so global stays 3'


def test_edit_removing_owner_department_reassigns_owner(client, dept_ids):
    """Unchecking the current owner department must update
    ``courses.department_id`` so the course no longer lingers in that
    department's plan (plan membership comes from owner OR placements)."""
    comm = dept_ids['قسم الاتصالات']
    comp = dept_ids['قسم الحاسوب']
    cid = _seed_course(comm, comp)  # owned by comm, placed in comm + comp
    placements = [
        {'department_id': comp, 'semester': 4},
    ]
    data = {
        '_csrf_token': 't',
        'code': 'CMP101',
        'name': 'أنظمة الاتصالات والبرمجة',
        'total_hours': '3',
        'theoretical_hours': '2',
        'practical_hours': '1',
        'year': '2',
        'semester': '4',
        'department_ids': [str(comp)],
        'dept_semester': ['4'],
        'placements': __import__('json').dumps(placements),
    }
    r = client.post(f'/courses/edit/{cid}', data=data)
    assert r.status_code == 302

    rows = _q("SELECT department_id, semester FROM course_departments "
              "WHERE course_id=? ORDER BY department_id", (cid,))
    assert [r['department_id'] for r in rows] == [comp], rows
    owner = _q("SELECT department_id FROM courses WHERE id=?", (cid,))[0]
    assert owner['department_id'] == comp, owner


def test_edit_removing_all_departments_clears_owner(client, dept_ids):
    """With no placements left the course must not keep an owner department
    that would still surface it in that department's plan."""
    comm = dept_ids['قسم الاتصالات']
    comp = dept_ids['قسم الحاسوب']
    cid = _seed_course(comm, comp)
    data = {
        '_csrf_token': 't',
        'code': 'CMP101',
        'name': 'أنظمة الاتصالات والبرمجة',
        'total_hours': '3',
        'theoretical_hours': '2',
        'practical_hours': '1',
        'year': '2',
        'semester': '2',
        'department_ids': [],
        'placements': __import__('json').dumps([]),
    }
    r = client.post(f'/courses/edit/{cid}', data=data)
    assert r.status_code == 302
    rows = _q("SELECT department_id FROM course_departments WHERE course_id=?", (cid,))
    assert rows == [], rows
    owner = _q("SELECT department_id FROM courses WHERE id=?", (cid,))[0]
    assert owner['department_id'] is None, owner


def _seed_course(comm, comp):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute(
        "INSERT INTO courses (code, name, department_id, year, semester, "
        "theoretical_hours, practical_hours, total_hours) "
        "VALUES ('CMP101','أنظمة الاتصالات والبرمجة',?,2,3,2,1,3)",
        (comm,),
    )
    conn.execute(
        "INSERT INTO course_departments (course_id, department_id, semester) VALUES (?,?,?),(?,?,?)",
        (conn.execute("SELECT id FROM courses WHERE code='CMP101'").fetchone()[0], comm, 3,
         conn.execute("SELECT id FROM courses WHERE code='CMP101'").fetchone()[0], comp, 4),
    )
    conn.commit()
    cid = conn.execute("SELECT id FROM courses WHERE code='CMP101'").fetchone()[0]
    conn.close()
    return cid
