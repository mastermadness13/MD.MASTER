"""Smoke tests for the Phase 2 mobile timetable cards.

On phones (<1024px) the scrollable weekly grid is replaced by a vertical
card feed: the desktop table gets wrapped in ``hidden lg:block`` and a
``tt-mobile-grid`` card list is rendered (server-side for combined/list,
client-side for department/rnd). Desktop markup must remain untouched.
"""

import os
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_cards.db'
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
        "INSERT INTO timetable_versions (department_id, semester, semester_code, status) VALUES (?, 2, 'fall_2026', 'active')",
        (dept_id,),
    )
    c = conn.execute(
        "INSERT INTO courses (code, name, department_id, year, semester, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('TT-C1', 'مقرر التجربة', ?, 1, 2, 2, 1, 3)",
        (dept_id,),
    )
    cid = c.lastrowid
    t = conn.execute("INSERT INTO teachers (name, department_id) VALUES (?, ?)", ('أ. أحمد', dept_id))
    tid = t.lastrowid
    r = conn.execute("INSERT INTO rooms (name, code) VALUES (?, ?)", ('قاعة 1', 'R1'))
    rid = r.lastrowid
    v = conn.execute("SELECT id FROM timetable_versions WHERE department_id=? AND status='active'", (dept_id,)).fetchone()['id']
    conn.execute(
        "INSERT INTO timetable (day, semester, period, course_id, teacher_id, room_id, department_id, version_id, start_time, end_time) "
        "VALUES ('الأحد', 2, 'A', ?, ?, ?, ?, ?, '09:00', '12:00')",
        (cid, tid, rid, dept_id, v),
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


def _read_js(name):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', 'static', 'js', name), encoding='utf-8') as fh:
        return fh.read()


def test_combined_page_has_mobile_cards_and_desktop_grid(client):
    """الجدول الموحّد: كروت الموبايل موجودة مع بقاء شبكة سطح المكتب كما هي."""
    body = client.get('/timetable').get_data(as_text=True)
    assert 'tt-mobile-grid' in body
    assert 'tt-mcard' in body, 'seeded entry must render a mobile card'
    assert 'tt-mday-head' in body
    assert 'hidden lg:block' in body, 'desktop grid hidden on phones, not removed'
    assert 'min-w-[760px]' in body, 'desktop grid table preserved'


def test_combined_page_empty_state_uses_mobile_class(app_fx, db_fx, client):
    """حين لا توجد حصص، تظهر حالة فارغة بكروت الموبايل لا سطح الجدول."""
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute('DELETE FROM timetable')
    conn.commit()
    conn.close()
    body = client.get('/timetable').get_data(as_text=True)
    assert 'tt-mobile-grid' in body
    assert 'tt-mcard' not in body
    assert 'tt-mempty' in body


def test_list_page_has_mobile_cards(client):
    """الجدول العام (print/timetable) يملك حاوية كروت الموبايل ويُخفي شبكة سطح المكتب على الهاتف."""
    body = client.get('/print/timetable').get_data(as_text=True)
    assert 'tt-mobile-grid' in body
    assert 'hidden lg:block' in body
    assert 'timetable_list.js' in body, 'list filters + delete handler still wired'


def test_department_page_has_mobile_container_and_js_builder(client):
    """محرر القسم: حاوية الموبايل في القالب + باني الكروت في ملف JS المعني."""
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'id="mobileGrid"' in body
    assert 'hidden lg:block' in body
    js = _read_js('timetable_department.js')
    assert 'renderMobileGrid' in js
    assert 'tt-mcard' in js
    assert 'لا توجد حصص مجدولة في هذا الجدول' in js


def test_rnd_page_has_mobile_container_and_js_builder(client):
    """جدول البحث والتطوير: حاوية الموبايل + باني كروت للقراءة فقط."""
    body = client.get('/timetable/rnd').get_data(as_text=True)
    assert 'id="mobileGrid"' in body
    assert 'hidden lg:block' in body
    js = _read_js('timetable_rnd.js')
    assert 'renderMobileGrid' in js
    assert 'tt-mcard' in js


def test_teacher_page_has_mobile_cards(app_fx, db_fx):
    """جدولي الأسبوعي: كروت الموبايل داخل أكورديون اليوم لدور المعلم."""
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute("INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('t1', 'x', 'teacher', 'معلم')")
    uid = conn.execute("SELECT id FROM users WHERE username='t1'").fetchone()[0]
    tid = conn.execute("SELECT id FROM teachers WHERE name='أ. أحمد'").fetchone()[0]
    conn.execute('UPDATE teachers SET user_id=? WHERE id=?', (uid, tid))
    conn.commit()
    conn.close()

    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = 'teacher'
        sess['username'] = 't1'
        sess['_csrf_token'] = 't'
    body = c.get('/teacher/my-schedule').get_data(as_text=True)
    assert 'tt-mcard' in body, 'seeded entry renders a mobile card in the day accordion'
    assert 'overflow-x-auto hidden lg:block' in body, 'desktop accordion table hidden on phones'