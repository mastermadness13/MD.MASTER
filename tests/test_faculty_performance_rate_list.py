"""Smoke tests for the super-admin قائمة معدل الأداء (performance-rate list).

Covers: sidebar nav visibility, page rendering with a member row + totals,
and permission gating (faculty_affairs lacks ``view_summary``).
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'performance_rate.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('superadmin', 'x', 'super_admin', 'مدير')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, department_id, academic_number) VALUES (?, ?, ?)",
        ('محمد أحمد', dept_id, '12345'),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'super_admin'
        sess['username'] = 'superadmin'
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


def test_super_admin_sees_rate_list_nav_item(app_fx):
    """عنوان «قائمة معدل الأداء» يظهر في شريط تنقل السوبر أدمن."""
    from flask import session
    from security.authorization import inject_navigation
    with app_fx.test_request_context('/'):
        session['role'] = 'super_admin'
        session['roles'] = ['super_admin']
        eps = {i['endpoint'] for i in inject_navigation()['nav_items']}
    assert 'faculty_performance.performance_rate_list' in eps


def test_faculty_affairs_does_not_see_rate_list_nav_item(app_fx):
    """مكتب أعضاء هيئة التدريس لا يرى عنصر «قائمة معدل الأداء»."""
    from flask import session
    from security.authorization import inject_navigation
    with app_fx.test_request_context('/'):
        session['role'] = 'faculty_affairs'
        session['roles'] = ['faculty_affairs']
        eps = {i['endpoint'] for i in inject_navigation()['nav_items']}
    assert 'faculty_performance.performance_rate_list' not in eps


def test_performance_rate_list_renders_with_member(client):
    """الصفحة تعرض العضو مع ساعاته والإجمالي الكلي."""
    r = client.get('/faculty-performance/performance-rate-list')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'قائمة معدل الأداء' in body
    assert 'محمد أحمد' in body
    assert 'قسم الحاسوب' in body
    # Column headers + total row
    assert 'الأساسي' in body
    assert 'الإجمالي الكلي' in body


def test_performance_rate_list_gated_for_office(app_fx):
    """مكتب أعضاء هيئة التدريس لا يستطيع فتح صفحة القائمة (403/redirect)."""
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'faculty_affairs'
        sess['username'] = 'office'
        sess['department_id'] = None
    r = c.get('/faculty-performance/performance-rate-list')
    assert r.status_code in (302, 403)