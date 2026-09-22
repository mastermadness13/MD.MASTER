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
    conn.commit()
    conn.close()
    return db_path


def _client_with_role(app_fx, role):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = role
        sess['username'] = role
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


def test_dean_dashboard_renders(app_fx, db_fx):
    """العميد يهبط على لوحة تحكم خاصة به (قراءة فقط)."""
    r = _client_with_role(app_fx, 'dean').get('/')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'لوحة العميد' in body


def test_visitor_dashboard_renders(app_fx, db_fx):
    """الزائر العام يهبط على بوابة زائر بسعتها العامة."""
    r = _client_with_role(app_fx, 'visitor').get('/')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'بوابة الزائر العام' in body


def test_dean_can_view_teacher_list(app_fx, db_fx):
    """العميد يقرأ قائمة الهيئة التدريسية لكن بلا أزرار إدارة."""
    r = _client_with_role(app_fx, 'dean').get('/teachers')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'أستاذ' in body


def test_visitor_cannot_open_teacher_management(app_fx, db_fx):
    """الزائر العام لا يملك الوصول لإدارة الهيئة التدريسية."""
    c = _client_with_role(app_fx, 'visitor')
    r = c.get('/teachers')
    assert r.status_code == 302
    r2 = c.get('/')
    assert r2.status_code == 200
    assert 'بوابة الزائر العام' in r2.get_data(as_text=True)