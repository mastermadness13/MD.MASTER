"""Dean + Visitor dashboards — role landing pages render and are read-only.

The dean (العميد) has oversight-only permissions; the visitor (الزائر العام)
sees only public listings. Both land on their dedicated dashboard templates
without an access-denied redirect.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'dean_visitor.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 7, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO courses (code, name, department_id) VALUES ('CS1', 'مقرر', ?)",
        (dept_id,),
    )
    conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('أستاذ', ?)", (dept_id,),
    )
    conn.executemany(
        "INSERT INTO users (username, password, role, label) VALUES (?, 'x', ?, ?)",
        [
            ('dashboard_dean', 'dean', 'العميد'),
            ('dashboard_visitor', 'visitor', 'الزائر العام'),
        ],
    )
    conn.executemany(
        "INSERT INTO user_roles (user_id, role) "
        "SELECT id, role FROM users WHERE username = ?",
        [('dashboard_dean',), ('dashboard_visitor',)],
    )
    conn.commit()
    conn.close()
    return db_path


def _client_with_role(app_fx, db_path, role):
    username = {
        'dean': 'dashboard_dean',
        'visitor': 'dashboard_visitor',
    }[role]
    conn = sqlite3.connect(db_path)
    user = conn.execute(
        'SELECT id, session_version FROM users WHERE username = ?', (username,)
    ).fetchone()
    conn.close()
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = user[0]
        sess['role'] = role
        sess['roles'] = [role]
        sess['username'] = username
        sess['session_version'] = user[1]
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


def test_dean_dashboard_renders(app_fx, db_fx):
    """العميد يهبط على لوحة تحكم خاصة به (قراءة فقط)."""
    r = _client_with_role(app_fx, db_fx, 'dean').get('/')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'لوحة عميد الكلية' in body


def test_renamed_dean_role_updates_dashboard_and_all_role_labels(app_fx, db_fx):
    conn = sqlite3.connect(db_fx)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """UPDATE admin_assignment_types
           SET name = 'عميد الكلية المكلّف'
           WHERE id = (
             SELECT id FROM admin_assignment_types
             WHERE internal_code = 'dean' AND is_system_linked = 1
             ORDER BY sort_order, id LIMIT 1
           )"""
    )
    conn.commit()
    conn.close()

    client = _client_with_role(app_fx, db_fx, 'dean')
    dashboard = client.get('/')
    assert dashboard.status_code == 200
    assert '<h1 class="page-title">لوحة عميد الكلية المكلّف</h1>' in (
        dashboard.get_data(as_text=True)
    )
    assert 'لوحة تحكم عميد الكلية المكلّف' in dashboard.get_data(as_text=True)

    session_info = client.get('/api/auth/me')
    assert session_info.status_code == 200
    assert session_info.get_json()['data']['role_label'] == 'عميد الكلية المكلّف'


def test_visitor_dashboard_renders(app_fx, db_fx):
    """الزائر العام يهبط على بوابة زائر بسعتها العامة."""
    r = _client_with_role(app_fx, db_fx, 'visitor').get('/')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'بوابة الزائر العام' in body


def test_dean_can_view_teacher_list(app_fx, db_fx):
    """العميد يقرأ قائمة الهيئة التدريسية لكن بلا أزرار إدارة."""
    r = _client_with_role(app_fx, db_fx, 'dean').get('/teachers')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'أستاذ' in body


def test_visitor_cannot_open_teacher_management(app_fx, db_fx):
    """الزائر العام لا يملك الوصول لإدارة الهيئة التدريسية."""
    c = _client_with_role(app_fx, db_fx, 'visitor')
    r = c.get('/teachers')
    assert r.status_code == 302
    r2 = c.get('/')
    assert r2.status_code == 200
    assert 'بوابة الزائر العام' in r2.get_data(as_text=True)