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
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('hod', 'x', 'head_of_department', 'رئيس القسم')"
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
    conn = sqlite3.connect(flask_db.DATABASE)
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()[0]
    conn.close()
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'head_of_department'
        sess['username'] = 'hod'
        sess['department_id'] = None
        sess['hod_department_id'] = dept_id
        sess['_csrf_token'] = 't'
    return c


def _read_js(name):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', 'static', 'js', name), encoding='utf-8') as fh:
        return fh.read()


def test_combined_page_has_mobile_container_and_js_builder(client):
    """الجدول الموحّد: حاوية كروت الموبايل في القالب + باني الكروت في ملف JS الموحّد."""
    body = client.get('/timetable').get_data(as_text=True)
    assert 'id="mobileGrid"' in body
    assert 'tt-mobile-grid' in body
    assert 'hidden lg:block' in body, 'desktop grid hidden on phones, not removed'
    assert 'min-w-[700px]' in body, 'desktop grid table preserved'
    assert 'timetable_live.js' in body, 'the unified live-sync bundle is wired'
    js = _read_js('timetable_live.js')
    assert 'renderMobileGrid' in js
    assert 'tt-mcard' in js
    assert 'tt-mday-head' in js


def test_combined_page_empty_state_uses_mobile_class(app_fx, db_fx, client):
    """حين لا توجد حصص، يبني الباني الموحّد حالة فارغة لكروت الموبايل."""
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute('DELETE FROM timetable')
    conn.commit()
    conn.close()
    body = client.get('/timetable').get_data(as_text=True)
    assert 'id="mobileGrid"' in body
    assert 'tt-mobile-grid' in body
    js = _read_js('timetable_live.js')
    assert 'tt-mempty' in js
    assert 'لا توجد حصص مجدولة في هذا الجدول' in js


def test_list_page_has_mobile_cards(client):
    """الجدول العام (print/timetable) يملك حاوية كروت الموبايل ويُخفي شبكة سطح المكتب على الهاتف."""
    body = client.get('/print/timetable').get_data(as_text=True)
    assert 'tt-mobile-grid' in body
    assert 'hidden lg:block' in body
    assert 'timetable_pages.js' in body, 'shared pages bundle wired'
    assert 'TIMETABLE_LIST_BOOT' in body, 'list filters + delete handler boot config present'


def test_department_page_has_mobile_container_and_js_builder(client):
    """محرر القسم: حاوية الموبايل في القالب + باني الكروت في الملف الموحّد."""
    body = client.get('/timetable/department').get_data(as_text=True)
    assert 'id="mobileGrid"' in body
    assert 'hidden lg:block' in body
    js = _read_js('timetable_live.js')
    assert 'renderMobileGrid' in js
    assert 'tt-mcard' in js
    assert 'لا توجد حصص مجدولة في هذا الجدول' in js


def test_rnd_page_has_mobile_container_and_js_builder(app_fx, db_fx):
    """جدول البحث والتطوير: حاوية الموبايل + باني كروت للقراءة فقط في الملف الموحّد."""
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'research_development'
        sess['username'] = 'rd'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    body = c.get('/timetable/rnd').get_data(as_text=True)
    assert 'id="mobileGrid"' in body
    assert 'hidden lg:block' in body
    js = _read_js('timetable_live.js')
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