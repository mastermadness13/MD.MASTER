"""Smoke tests for the قائمة معدل الأداء (performance-rate list).

Covers: sidebar nav visibility, page rendering with a member row + totals,
the search box, and permission gating.  Only the faculty-affairs office
(مكتب أعضاء هيئة التدريس) can open the list; research_development and exam
are turned away (they lack ``view_summary``).
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
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('exam', 'x', 'exam', 'قسم الامتحانات')"
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
        sess['role'] = 'faculty_affairs'
        sess['username'] = 'office'
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


def test_office_sees_rate_list_nav_item(app_fx):
    """عنوان «قائمة معدل الأداء» يظهر في شريط تنقل مكتب أعضاء هيئة التدريس."""
    from flask import session
    from security.authorization import inject_navigation
    with app_fx.test_request_context('/'):
        session['role'] = 'faculty_affairs'
        session['roles'] = ['faculty_affairs']
        eps = {i['endpoint'] for i in inject_navigation()['nav_items']}
    assert 'faculty_performance.performance_rate_list' in eps


def test_exam_does_not_see_rate_list_nav_item(app_fx):
    """قسم الامتحانات لا يرى عنصر «قائمة معدل الأداء»."""
    from flask import session
    from security.authorization import inject_navigation
    with app_fx.test_request_context('/'):
        session['role'] = 'exam'
        session['roles'] = ['exam']
        eps = {i['endpoint'] for i in inject_navigation()['nav_items']}
    assert 'faculty_performance.performance_rate_list' not in eps


def test_research_development_does_not_see_rate_list_nav_item(app_fx):
    """البحث والتطوير لا يرى عنصر «قائمة معدل الأداء»."""
    from flask import session
    from security.authorization import inject_navigation
    with app_fx.test_request_context('/'):
        session['role'] = 'research_development'
        session['roles'] = ['research_development']
        eps = {i['endpoint'] for i in inject_navigation()['nav_items']}
    assert 'faculty_performance.performance_rate_list' not in eps


def test_performance_rate_list_renders_with_member(client):
    """مكتب أعضاء هيئة التدريس يفتح القائمة: تعرض العضو مع ساعاته والإجمالي الكلي والبحث."""
    r = client.get('/faculty-performance/performance-rate-list')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'قائمة معدل الأداء' in body
    assert 'محمد أحمد' in body
    assert 'قسم الحاسوب' in body
    # Column headers + total row
    assert 'الأساسي' in body
    assert 'الإجمالي الكلي' in body
    # البحث متوفر في القائمة
    assert 'rateListSearch' in body
    assert 'ابحث بالاسم أو القسم أو الرقم الكلية' in body


def _gated_for(app_fx, db_fx, role):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = role
        sess['username'] = role
        sess['department_id'] = None
    return c.get('/faculty-performance/performance-rate-list')


def test_performance_rate_list_gated_for_other_roles(app_fx, db_fx):
    """البحث والتطوير وقسم الامتحانات لا يستطيعان فتح صفحة القائمة (302/403)."""
    for role in ('research_development', 'exam'):
        r = _gated_for(app_fx, db_fx, role)
        assert r.status_code in (302, 403)


def test_leaves_report_fallback_shows_ministry_name(app_fx, db_fx, monkeypatch):
    """«اسم المؤسسة» في تقرير الإجازات يبقى «وزارة التعليم التقني والفني»
    حتى حين لا تتوفر بيانات نموذج الأداء (المسار الاحتياطي)."""
    from services import faculty_performance_service as fps
    monkeypatch.setattr(fps, 'get_performance_form_data', lambda *a, **k: None)

    conn = sqlite3.connect(flask_db.DATABASE)
    teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE name='محمد أحمد'").fetchone()[0]
    conn.close()

    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'faculty_affairs'
        sess['username'] = 'office'
        sess['department_id'] = None

    r = c.get('/faculty-performance/leaves/{}/print'.format(teacher_id))
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'وزارة التعليم التقني والفني' in body
    assert 'كلية التقنية الهندسية زوارة' not in body