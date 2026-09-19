"""Smoke tests for the mobile app bottom navigation shell.

Covers: the bar renders on authenticated app pages (role-aware tabs and
FAB + quick-sheet), it is absent on the login screen (auth layout), and
roles without ``tools.view`` get the "more" fallback instead of a direct
reports link.
"""

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'bn.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('superadmin', 'x', 'super_admin', 'مدير')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('hod', 'x', 'head_of_department', 'رئيس قسم')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.execute(
        "INSERT INTO timetable_versions (department_id, semester, semester_code, status) VALUES (?, 2, 'fall_2026', 'active')",
        (dept_id,),
    )
    conn.commit()
    conn.close()
    return db_path


def _user_id(db_path, username):
    conn = connect(db_path)
    row = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    return row['id']


def _client_for(app_fx, user_id, role, username, dept_id=None):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['role'] = role
        sess['username'] = username
        sess['department_id'] = dept_id
        sess['_csrf_token'] = 't'
    return c


@pytest.fixture
def client(app_fx, db_fx):
    return _client_for(app_fx, _user_id(db_fx, 'superadmin'), 'super_admin', 'superadmin')


def test_bottom_nav_renders_on_app_page(client):
    """صفحة تطبيقية مسجّلة تعرض الشريط السفلي وزر FAB وورقتي القائمة."""
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'id="bottomNav"' in body
    assert 'class="bottom-nav no-print"' in body
    assert 'bn-fab' in body
    assert 'data-bn-section="quick"' in body
    assert 'data-bn-section="more"' in body
    # The desktop sidebar is still rendered — nothing was replaced.
    assert 'id="appSidebar"' in body


def test_bottom_nav_new_tab_follows_role(app_fx, db_fx):
    """رئيس القسم (بدون tools.view) يرى تبويب «المزيد» لا رابط التقارير المباشر."""
    client = _client_for(app_fx, _user_id(db_fx, 'hod'), 'head_of_department', 'hod', dept_id=1)
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'id="bottomNav"' in body
    assert "toggleBnSheet('more')" in body, 'HOD gets the more fallback button'
    assert '/tools/html-to-pdf' not in body, 'no direct reports link for roles without tools.view'


def test_bottom_nav_absent_on_login(app_fx, db_fx):
    """صفحة تسجيل الدخول (auth layout) لا تعرض الشريط السفلي."""
    body = app_fx.test_client().get('/login').get_data(as_text=True)
    assert 'bottomNav' not in body


def test_bottom_nav_quick_sheet_has_print_action(app_fx, db_fx):
    """الورقة السريعة تحوي دائماً «طباعة الصفحة الحالية» لكل الأدوار."""
    body = _client_for(app_fx, _user_id(db_fx, 'superadmin'), 'super_admin', 'superadmin').get('/timetable/department').get_data(as_text=True)
    assert 'window.print()' in body