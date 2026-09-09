"""Regression: teachers list page shows the full admin table for every role
with ``teachers.view`` (faculty_affairs, super_admin, research_development,
head_of_department), and the compact Quick Member Search / All Members List
has been removed entirely."""

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema

ROLES_WITH_VIEW = [
    'faculty_affairs',
    'super_admin',
    'research_development',
    'head_of_department',
]

FULL_TABLE_MARKERS = [
    'id="teachersSearchForm"',
    'id="selectAllTeachers"',
    'id="bulkDeleteForm"',
    'search-table',
]

COMPACT_MARKERS = ['memberSearch', 'memberCount', 'member-item']


def _mkdb(tmp_path):
    p = tmp_path / 'l'
    p.mkdir(parents=True, exist_ok=True)
    db_path = p / 'list.db'
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('u', 'x', 'faculty_affairs', 'مكتب')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم', 4, 4, 0, 1, 'academic')"
    )
    conn.execute(
        "INSERT INTO teachers (name, department_id) "
        "VALUES ('مدرس', (SELECT id FROM departments LIMIT 1))"
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _login(c, role):
    with c.session_transaction() as s:
        s['user_id'] = 1
        s['role'] = role
        s['username'] = 'u'
        s['department_id'] = None
        s['_csrf_token'] = 't'


@pytest.fixture
def list_setup(tmp_path, monkeypatch, app_fx):
    db_path = _mkdb(tmp_path)
    monkeypatch.setattr(flask_db, 'DATABASE', db_path)
    return app_fx.test_client()


def test_full_table_shown_for_every_role_with_view(list_setup):
    c = list_setup
    for role in ROLES_WITH_VIEW:
        _login(c, role)
        r = c.get('/teachers', follow_redirects=True)
        assert r.status_code == 200, role
        html = r.get_data(as_text=True)
        for marker in FULL_TABLE_MARKERS:
            assert marker in html, f'{role}: missing full-table marker {marker}'


def test_compact_members_list_removed_for_every_role(list_setup):
    c = list_setup
    for role in ROLES_WITH_VIEW:
        _login(c, role)
        r = c.get('/teachers', follow_redirects=True)
        assert r.status_code == 200, role
        html = r.get_data(as_text=True)
        for marker in COMPACT_MARKERS:
            assert marker not in html, f'{role}: compact marker {marker} still present'